#!/usr/bin/env python3
"""Server-side Data Economy EMISS refresh; validated current data survive source outages.

python scripts/refresh_dataeconomy_emiss.py [--source 62803] [--strict]

GitHub Pages serves the resulting static files. This script runs in the existing
scheduled GitHub workflow or locally, not from a visitor's browser. A source
failure cannot replace or erase its last verified observations. Source titles,
units, dimensions, methodology and period labels must match their contracts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import html
from emiss_adapter.client import Client, query_plan, redact, title_key
from emiss_adapter.metadata import parse_indicator_metadata
from emiss_adapter.errors import EmissConnectorError
from emiss_adapter.sdmx import parse_sdmx
from dataeconomy_formats import parse_excel, parse_grid
from dataeconomy_data import ROOT, DATA, DOWNLOADS, load, atomic, sha256, region_aliases, territory_key, normalize_record, merge_observations, series_flags, decode_period
from build_dataeconomy_analytics import build


def clean(text):
    return ' '.join((text or '').split())


class DataeconomyClient(Client):
    def metadata(self, indicator_id):
        if not re.fullmatch(r'\d{1,12}', str(indicator_id)):
            raise EmissConnectorError('Некорректный ID источника.', category='invalid_id')
        source = next(s for s in self.config['sources'] if s['indicator_id'] == str(indicator_id))
        page = self.request('GET', '/indicator/' + str(indicator_id)).decode('utf-8', errors='replace')
        tree = html.fromstring(page)
        methods = tree.xpath('//*[@id="methodologyFull"]')
        method = clean(methods[0].text_content()) if methods else ''
        if source.get('methodology') and method != clean(source['methodology']):
            raise EmissConnectorError('Методика расчёта изменилась или отсутствует; необходима проверка сопоставимости перед публикацией.', category='methodology_contract_changed')
        unit_nodes = tree.xpath('//*[normalize-space(text())="Единицы измерения"]')
        units = {clean(e.getnext().text_content()).casefold() for e in unit_nodes if e.getnext() is not None}
        if units != {source['unit'].casefold()}:
            raise EmissConnectorError('Единица измерения паспорта не совпадает с подтверждённой.', category='unit_mismatch')
        try:
            meta = parse_indicator_metadata(page, str(indicator_id))
        except EmissConnectorError as exc:
            titles = [clean(e.text_content()) for e in tree.xpath('//span[contains(concat(" ", normalize-space(@class), " "), " sp_txt ")]')]
            no_grid = not re.search(r'filters\s*:\s*\{', page)
            if no_grid and any(title_key(t) == title_key(s) for t in titles for s in source['titles']):
                return {'indicator_id': str(indicator_id), 'indicator_title': source['title'], 'no_numeric_grid': True,
                        'unit': source['unit'], 'methodology': method, 'page_sha256': hashlib.sha256(page.encode()).hexdigest()}
            raise exc
        fields = {e.get('name'): e.get('value', '') for e in tree.xpath('//*[@id="downloadTokenHolder"]//input[@name]')}
        token_name = fields.get('struts.token.name')
        tokens = {k: v for k, v in fields.items() if k in {'struts.token.name', token_name} and v} if token_name else {}
        if tokens:
            self._download_tokens[str(indicator_id)] = tokens
            self._token_required.add(str(indicator_id))
        return meta

    def _export_once(self, meta, selected):
        sid = str(meta['indicator_id'])
        source = next(s for s in self.config['sources'] if s['indicator_id'] == sid)
        kind = source.get('export_format', 'sdmx')
        if kind not in {'sdmx', 'excel', 'grid'}:
            raise EmissConnectorError('Неизвестный подтверждённый формат источника.', category='export_contract_changed')
        form = [('id', sid)]
        if kind != 'grid':
            if sid in self._token_required and sid not in self._download_tokens:
                fresh = self.metadata(sid)
                if fresh != meta:
                    raise EmissConnectorError('Метаданные изменились перед выгрузкой.', category='metadata_contract_changed')
            form.extend(self._download_tokens.pop(sid, {}).items())
            form.append(('title', meta['indicator_title']))
        for field in meta['filters']:
            fid = str(field['field_id'])
            parameter = 'lineObjectIds' if fid == '0' and kind == 'grid' else 'filterObjectIds' if fid == '0' else field.get('object_parameter') or 'lineObjectIds'
            form.append((parameter, fid))
            form.extend(('selectedFilterIds', fid + '_' + str(value['id'])) for value in selected.get(fid, []))
        if kind == 'grid':
            previous = self.http.headers.get('X-Requested-With')
            self.http.headers['X-Requested-With'] = 'XMLHttpRequest'
            try:
                raw = self.request('POST', '/indicator/dataGrid.do?id=' + sid, form)
            finally:
                if previous is None:
                    self.http.headers.pop('X-Requested-With', None)
                else:
                    self.http.headers['X-Requested-With'] = previous
            observations, structure = parse_grid(raw, meta, selected)
        else:
            raw = self.request('POST', '/indicator/downloadData.do?format=' + kind, form)
            observations, structure = parse_excel(raw, meta, selected) if kind == 'excel' else parse_sdmx(raw)
        if not observations:
            raise EmissConnectorError('Пустая официальная выгрузка.', category='empty_export')
        return observations, structure, hashlib.sha256(raw).hexdigest(), raw


def normalized_live(items, meta, roles, selected, contract, aliases, checked_at, regions=None):
    from emiss_adapter.normalize import values_for_field
    from dataeconomy_data import category_dimensions
    import math
    rows=[]
    for item in items:
        if item.value_status=='invalid' or item.value is not None and not math.isfinite(item.value):
            raise EmissConnectorError('Источник содержит нечисловую ячейку.',category='invalid_numeric')
        dimensions={}
        for field in meta['filters']:
            fid=str(field['field_id'])
            value=values_for_field(item,fid,meta,selected)
            if value is None and fid==roles.get('year'):
                value=item.period
            if value is None:
                raise EmissConnectorError('Не удалось восстановить измерение '+field['title'],category='ambiguous_dimension')
            dimensions[field['title']]=value
        territory=values_for_field(item,roles.get('territory'),meta,selected)
        if not territory:raise EmissConnectorError('Не определена территория.',category='ambiguous_territory')
        year=values_for_field(item,roles.get('year'),meta,selected) or item.period
        label=values_for_field(item,roles.get('month'),meta,selected) if 'month' in roles else 'значение показателя за год'
        known=contract.get('period_kind_by_label',{}).get(str(label))
        frequency,start,end,basis=decode_period(year,label,known)
        if known and known not in {'unresolved',frequency}:raise EmissConnectorError('Изменился тип периода.',category='period_schema_changed')
        unit_values={str(value).strip().casefold() for key,value in dimensions.items() if 'единиц' in key.casefold()}
        if unit_values!={contract['unit'].strip().casefold()}:
            raise EmissConnectorError('Единица ячейки не совпадает с контрактом.',category='unit_mismatch')
        dimensions['Период']=label
        raw={'source_id':contract['indicator_id'],'unit':contract['unit'],'period_kind':known or frequency,
             'period_start':None if known=='unresolved' else start,'period_end':None if known=='unresolved' else end,
             'year':int(year),'territory_name':territory,'value_numeric':item.value,'value_raw':item.raw_value,
             'dimensions_json':json.dumps(dimensions,ensure_ascii=False),'attributes_json':json.dumps(item.attributes,ensure_ascii=False)}
        normalized=normalize_record(raw,contract,aliases,regions,checked_at[:10])
        if normalized['value'] is not None and normalized['period_end']>checked_at[:10]:
            raise EmissConnectorError('Число относится к незавершённому будущему периоду.',category='future_observation')
        rows.append(normalized)
    if len({r['id'] for r in rows})!=len(rows):raise EmissConnectorError('Повтор ключа наблюдения.',category='conflicting_duplicates')
    regional={r['code'] for r in rows if r['geo_level']=='regional' and r['value'] is not None}
    if len(regional)<contract.get('min_regional_count',0):raise EmissConnectorError('Охват регионов ниже контракта.',category='coverage_drop')
    observed_names={territory_key(r['name']) for r in rows}
    required_names={territory_key(n) for n in contract.get('known_territories',[])}
    if not required_names.issubset(observed_names):
        raise EmissConnectorError('В полной выгрузке исчезли ранее опубликованные территории, включая муниципальные. Последний проверенный набор сохранён.',category='geography_coverage_drop')
    return rows


TRANSPORT_ERRORS = {'network_error', 'http_error', 'temporary_http', 'access_challenge', 'source_redirect'}


def run(root=ROOT, only=None, client=None, timeout=None, retries=None, max_failures=None, rebuild=True):
    root = Path(root)
    config = load(root / 'scripts/dataeconomy_emiss_sources.json')
    if timeout is not None:
        config['timeout_seconds'] = timeout
    if retries is not None:
        config['retries'] = retries
    if max_failures is not None:
        config['failure_circuit_breaker'] = max_failures
    if config['timeout_seconds'] <= 0 or config['retries'] < 0 or config.get('failure_circuit_breaker', 3) < 1:
        raise ValueError('Timeout and failure threshold must be positive; retries must be nonnegative')
    if only and str(only) not in {s['indicator_id'] for s in config['sources']}:
        raise ValueError('Unknown confirmed Data Economy source ID')
    previous_status = load(root / DATA / 'refresh-status.json')
    previous = {str(s['source_id']): s for s in previous_status.get('sources', [])}
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    client = client or DataeconomyClient(config)
    aliases = region_aliases(root)
    regions = {str(r['id']): r for r in load(root / 'public/data/catalog.json')['regions']}
    statuses = []
    attempted = successful = published = updated = failed = deferred = consecutive = 0
    for source in config['sources']:
        sid = source['indicator_id']
        prior = previous.get(sid, {})
        if only and sid != str(only):
            statuses.append(prior or {'source_id': sid, 'state': 'not_checked', 'message': 'Не входил в выбранный запуск.'})
            continue
        entry = {**prior, 'source_id': sid, 'title': source['title']}
        if consecutive >= config.get('failure_circuit_breaker', 3):
            entry.update(state='deferred_after_source_outage', attempt_at=checked_at,
                         message='Запрос отложен после повторных ошибок доступа к ЕМИСС. Последний проверенный набор сохранён; этот источник в текущем запуске не проверялся.')
            deferred += 1
            statuses.append(entry)
            continue
        attempted += 1
        entry.update(checked_at=checked_at, attempt_at=checked_at)
        try:
            meta = client.metadata(sid)
            if meta.get('no_numeric_grid'):
                entry.update(state='metadata_only', metadata_checked_at=checked_at,
                             message='Паспорт и методика доступны; числовая таблица источником не опубликована. Последние проверенные числовые данные, если они были, сохранены.')
                successful += 1
                consecutive = 0
                statuses.append(entry)
                continue
            roles, selected = query_plan(meta, source, config['max_cells'])
            parsed, _, digest, raw = client.export(meta, selected)
            extension = {'sdmx': 'xml', 'excel': 'xls', 'grid': 'json'}[source.get('export_format', 'sdmx')]
            raw_files = [('all.' + extension, raw)]
            raw_hashes = [digest]
            try:
                incoming = normalized_live(parsed, meta, roles, selected, source, aliases, checked_at, regions)
            except EmissConnectorError as exc:
                if exc.category != 'ambiguous_period' or 'month' not in roles:
                    raise
                incoming = []
                for value in selected[roles['month']]:
                    single = copy.deepcopy(selected)
                    single[roles['month']] = [value]
                    parsed, _, digest, raw = client.export(meta, single)
                    raw_hashes.append(digest)
                    raw_files.append((f'period_{len(raw_files):02d}.' + extension, raw))
                    incoming.extend(normalized_live(parsed, meta, roles, single, source, aliases, checked_at, regions))
            if not incoming or not any(row['value'] is not None for row in incoming):
                raise EmissConnectorError('В выгрузке нет числовых наблюдений; последний проверенный набор не заменён.', category='empty_numeric_export')
            packet_path = root / DATA / 'series' / (sid + '.json')
            packet = load(packet_path)
            old_categories = {json.dumps(r['category'], ensure_ascii=False, sort_keys=True) for r in packet['observations']}
            new_categories = {json.dumps(r['category'], ensure_ascii=False, sort_keys=True) for r in incoming}
            if old_categories and not new_categories.issubset(old_categories):
                raise EmissConnectorError('Изменился состав дополнительного измерения; нужен самостоятельный контракт ряда.', category='dimension_contract_changed')
            merged, added, revisions = merge_observations(packet['observations'], incoming)
            merged = series_flags(merged, sid)
            next_packet = {**packet, 'published_at': checked_at, 'snapshot_id': 'live:' + hashlib.sha256(''.join(raw_hashes).encode()).hexdigest(),
                           'origin_kind': 'live_emiss', 'direct_emiss_verified':True, 'observations': merged}
            raw_path = root / DOWNLOADS / 'emiss_current' / (sid + '.zip')
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_tmp = raw_path.with_suffix('.zip.tmp')
            with zipfile.ZipFile(raw_tmp, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, body in raw_files:
                    archive.writestr(name, body)
                # Metadata excludes per-session form tokens and HTTP cookies.
                archive.writestr('metadata.json', json.dumps(meta, ensure_ascii=False, indent=2))
            raw_tmp.replace(raw_path)
            provenance_path = root / DATA / 'provenance' / (sid + '.json')
            provenance = load(provenance_path)
            provenance.update(acquired_at=checked_at, checked_at=checked_at, snapshot_id=next_packet['snapshot_id'],
                              origin_kind='live_emiss', observations=len(merged), numeric=sum(r['value'] is not None for r in merged),
                              response_sha256=raw_hashes, metadata=meta, requested_filters=selected,
                              new_rows=added, revisions=revisions, current_raw=raw_path.relative_to(root / 'public').as_posix(),
                              current_raw_sha256=sha256(raw_path))
            # All parsing and contract checks precede the first published change.
            atomic(packet_path, next_packet, compact=True)
            provenance['published_sha256'] = sha256(packet_path)
            atomic(provenance_path, provenance)
            changed = bool(added or revisions)
            entry.update(state='updated' if changed else 'unchanged', last_success=checked_at, published_at=checked_at,
                         raw_file=raw_path.relative_to(root / 'public').as_posix(), rows=len(merged),
                         new_rows=added, revisions=len(revisions),
                         message='Проверено; новые и пересмотренные значения опубликованы.' if changed else 'Проверено; числовых изменений нет.')
            successful += 1
            published += 1
            updated += changed
            consecutive = 0
        except Exception as exc:
            category = getattr(exc, 'category', 'validation_failed')
            entry.update(state=category, message=redact(exc), new_rows=0, revisions=0)
            failed += 1
            consecutive = consecutive + 1 if category in TRANSPORT_ERRORS else 0
        statuses.append(entry)
    client.close()
    dates = [r['published_at'] for r in statuses if r.get('published_at')]
    published_at = max(dates) if dates else previous_status.get('published_at')
    state = 'failed' if not successful else 'partial' if failed or deferred else 'updated' if updated else 'unchanged'
    report = {'schema_version': 1, 'project_id': 'data_economy', 'state': state,
              'checked_at': checked_at, 'published_at': published_at,
              'statistical_as_of': published_at[:10] if published_at else previous_status.get('statistical_as_of'),
              'last_success': checked_at if published else previous_status.get('last_success'),
              'attempted_sources': attempted, 'successful_sources': successful, 'published_sources': published,
              'updated_sources': updated, 'failed_sources': failed, 'deferred_sources': deferred,
              'message': f'Запрошено источников: {attempted}; подтверждено: {successful}; отложено: {deferred}. Неуспешные запросы не заменяют последние проверенные данные.',
              'sources': statuses, 'unmapped_indicators': config['unmapped_indicators']}
    atomic(root / DATA / 'refresh-status.json', report)
    atomic(root / 'monitoring/dataeconomy_last_refresh.json', report)
    if rebuild:
        build(root)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--source', help='Confirmed EMISS numeric ID; omit to check all 48 sources.')
    parser.add_argument('--timeout', type=float)
    parser.add_argument('--retries', type=int)
    parser.add_argument('--max-failures', type=int)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    result = run(args.root, args.source, timeout=args.timeout, retries=args.retries, max_failures=args.max_failures)
    print(result['message'])
    for source in result['sources']:
        if not args.source or source['source_id'] == args.source:
            print(source['source_id'], source['state'], source.get('message', ''))
    if args.strict and result['state'] in ('failed', 'partial'):
        raise SystemExit(2)
