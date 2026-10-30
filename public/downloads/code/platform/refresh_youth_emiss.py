#!/usr/bin/env python3
"""Server-side Youth EMISS refresh; validated current data survive source outages.

python scripts/refresh_youth_emiss.py [--source 62969] [--strict]

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
from emiss_adapter.normalize import convert
from emiss_adapter.errors import EmissConnectorError
from youth_data import ROOT, DATA, DOWNLOADS, load, atomic, sha256, region_aliases, territory_key, normalize_record, merge_observations
from build_youth_analytics import build


def clean(text):
    return ' '.join((text or '').split())


class YouthClient(Client):
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
        tokens = {k: v for k, v in fields.items() if k in {'struts.token.name', 'token'} and v}
        if tokens:
            self._download_tokens[str(indicator_id)] = tokens
            self._token_required.add(str(indicator_id))
        return meta


def normalized_live(items, meta, roles, selected, contract, aliases, checked_at):
    # Keep the explicitly listed non-subject territory, including its missing
    # cells, without drawing it as one of the 89 regional positions.
    adapter_aliases = {**aliases, territory_key('г. Байконур'): 'source:baikonur'}
    converted = convert(items, meta, roles, selected, contract, adapter_aliases, checked_at)
    rows = []
    for row in converted:
        kind = {'год': 'annual', 'месяц': 'monthly', 'накопительно с января': 'cumulative_ytd'}[row['type']]
        dimensions = {**row.get('dimensions', {}), 'Период': row['label']}
        raw = {'source_id': contract['indicator_id'], 'unit': contract['unit'], 'period_kind': kind,
               'period_start': row['start'], 'period_end': row['end'], 'year': row['year'],
               'territory_name': row['territory'], 'territory_code': row.get('r'),
               'territory_level': 'subject' if row.get('r') and not str(row['r']).startswith('source:') else 'national' if territory_key(row['territory']) == territory_key('Российская Федерация') else 'other_territory',
               'value_numeric': row['value'], 'value_raw': row['raw'],
               'dimensions_json': json.dumps(dimensions, ensure_ascii=False)}
        normalized = normalize_record(raw, contract, aliases)
        if normalized['value'] is not None and normalized['period_end'] > checked_at[:10]:
            raise EmissConnectorError('Числовое наблюдение относится к ещё не завершившемуся периоду; требуется проверка статуса.', category='future_observation')
        rows.append(normalized)
    return rows


TRANSPORT_ERRORS = {'network_error', 'http_error', 'temporary_http', 'access_challenge', 'source_redirect'}


def run(root=ROOT, only=None, client=None, timeout=None, retries=None, max_failures=None, rebuild=True):
    root = Path(root)
    config = load(root / 'scripts/youth_emiss_sources.json')
    if timeout is not None:
        config['timeout_seconds'] = timeout
    if retries is not None:
        config['retries'] = retries
    if max_failures is not None:
        config['failure_circuit_breaker'] = max_failures
    if config['timeout_seconds'] <= 0 or config['retries'] < 0 or config.get('failure_circuit_breaker', 3) < 1:
        raise ValueError('Timeout and failure threshold must be positive; retries must be nonnegative')
    if only and str(only) not in {s['indicator_id'] for s in config['sources']}:
        raise ValueError('Unknown confirmed Youth source ID')
    previous_status = load(root / DATA / 'refresh-status.json')
    previous = {str(s['source_id']): s for s in previous_status.get('sources', [])}
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    client = client or YouthClient(config)
    aliases = region_aliases(root)
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
            raw_files = [('all.xml', raw)]
            raw_hashes = [digest]
            try:
                incoming = normalized_live(parsed, meta, roles, selected, source, aliases, checked_at)
            except EmissConnectorError as exc:
                if exc.category != 'ambiguous_period' or 'month' not in roles:
                    raise
                incoming = []
                for value in selected[roles['month']]:
                    single = copy.deepcopy(selected)
                    single[roles['month']] = [value]
                    parsed, _, digest, raw = client.export(meta, single)
                    raw_hashes.append(digest)
                    raw_files.append((f'period_{len(raw_files):02d}.xml', raw))
                    incoming.extend(normalized_live(parsed, meta, roles, single, source, aliases, checked_at))
            if not incoming or not any(row['value'] is not None for row in incoming):
                raise EmissConnectorError('В выгрузке нет числовых наблюдений; последний проверенный набор не заменён.', category='empty_numeric_export')
            packet_path = root / DATA / 'series' / (sid + '.json')
            packet = load(packet_path)
            old_categories = {json.dumps(r['category'], ensure_ascii=False, sort_keys=True) for r in packet['observations']}
            new_categories = {json.dumps(r['category'], ensure_ascii=False, sort_keys=True) for r in incoming}
            if old_categories and not new_categories.issubset(old_categories):
                raise EmissConnectorError('Изменился состав дополнительного измерения; нужен самостоятельный контракт ряда.', category='dimension_contract_changed')
            merged, added, revisions = merge_observations(packet['observations'], incoming)
            next_packet = {**packet, 'published_at': checked_at, 'snapshot_id': 'live:' + hashlib.sha256(''.join(raw_hashes).encode()).hexdigest(),
                           'origin_kind': 'live_emiss', 'observations': merged}
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
            atomic(packet_path, next_packet)
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
    report = {'schema_version': 1, 'project_id': 'youth_children', 'state': state,
              'checked_at': checked_at, 'published_at': published_at,
              'statistical_as_of': published_at[:10] if published_at else previous_status.get('statistical_as_of'),
              'last_success': checked_at if published else previous_status.get('last_success'),
              'attempted_sources': attempted, 'successful_sources': successful, 'published_sources': published,
              'updated_sources': updated, 'failed_sources': failed, 'deferred_sources': deferred,
              'message': f'Запрошено источников: {attempted}; подтверждено: {successful}; отложено: {deferred}. Неуспешные запросы не заменяют последние проверенные данные.',
              'sources': statuses, 'unmapped_indicators': config['unmapped_indicators']}
    atomic(root / DATA / 'refresh-status.json', report)
    atomic(root / 'monitoring/youth_last_refresh.json', report)
    if rebuild:
        build(root)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--source', help='Confirmed EMISS numeric ID; omit to check all 29 sources.')
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
