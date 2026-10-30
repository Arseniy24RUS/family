#!/usr/bin/env python3
"""Refresh confirmed Health Technologies sources through the EMISS export form.

The export adapter is shared with the platform. Project-specific units,
methodology, country scope and periods are validated before publication. A
failed or empty response retains the verified republished source packets.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import html

from emiss_adapter.client import query_plan, redact
from emiss_adapter.errors import EmissConnectorError
from refresh_longlife_emiss import LonglifeClient
from healthtech_data import ROOT, PROJECT, DATA, DOWNLOADS, load, atomic, sha256, clean, observation, merge_observations
from build_healthtech_analytics import build


class HealthtechClient(LonglifeClient):
    """Use the existing token-aware official XLS adapter with the new contracts."""

    def request(self, method, path, form=None):
        body = super().request(method,path,form)
        if method=='GET' and re.fullmatch(r'/indicator/\d+',path):
            self._healthtech_source_dates = getattr(self,'_healthtech_source_dates',{})
            tree = html.fromstring(body)
            dates = set()
            for node in tree.xpath('//*[normalize-space(text())="Последнее обновление данных" or normalize-space(text())="Дата последнего обновления данных"]'):
                sibling = node.getnext()
                if sibling is not None:
                    match = re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b',sibling.text_content())
                    if match:dates.add(datetime.strptime(match[1],'%d.%m.%Y').date().isoformat())
            if len(dates)>1:
                raise EmissConnectorError('Неоднозначная дата обновления источника.',category='metadata_contract_changed')
            self._healthtech_source_dates[path.rsplit('/',1)[-1]] = next(iter(dates),None)
        return body

    def metadata(self, indicator_id):
        result = super().metadata(indicator_id)
        result['source_updated_at'] = getattr(self,'_healthtech_source_dates',{}).get(str(indicator_id))
        return result


def live_rows(items, config, checked_at):
    output = []
    sid = config['indicator_id']
    def label(dimensions, names):
        matches = [(key,value) for key,value in dimensions.items() if clean(key).casefold() in names]
        if len(matches)!=1:
            raise EmissConnectorError('Неоднозначное измерение источника: '+', '.join(names),category='dimension_contract_changed')
        return matches[0][1]
    for item in items:
        dimensions = item.dimensions
        allowed = {'год','период','месяц','окато','окато (российская федерация, федеральные округа, субъекты российской федерации)','единица измерения','единицы измерения','показатель'}
        if any(clean(key).casefold() not in allowed for key in dimensions):
            raise EmissConnectorError('Появилось неподтверждённое дополнительное измерение.',category='dimension_contract_changed')
        territory = label(dimensions,{'окато','окато (российская федерация, федеральные округа, субъекты российской федерации)'})
        if re.sub(r'^\d+\s+','',clean(territory)).casefold() != 'российская федерация':
            raise EmissConnectorError('Обнаружено новое территориальное измерение. Нужна самостоятельная проверка состава.',category='geographic_contract_changed')
        unit = label(dimensions,{'единица измерения','единицы измерения'})
        unit = re.sub(r'^\d+\s+','',clean(unit))
        if unit != config['unit']:
            raise EmissConnectorError('Единица наблюдения отличается от сохранённой.',category='unit_mismatch')
        raw = {'territory_label':'643 Российская Федерация','unit_label':unit,
               'year':label(dimensions,{'год'}),'period_label':label(dimensions,{'период','месяц'}),
               'value_raw':item.raw_value if item.raw_value is not None else '',
               'source_locator':item.attributes.get('source_cell'),'origin_kind':'live_emiss'}
        try:
            row = observation(sid,raw,config)
        except ValueError as exc:
            raise EmissConnectorError(str(exc),category='observation_contract_changed') from exc
        if row['value'] != item.value:
            raise EmissConnectorError('Число не совпадает с исходным представлением ячейки.',category='numeric_contract_changed')
        if row['value'] is not None and row['period_end'] > checked_at[:10]:
            raise EmissConnectorError('Числовая ячейка относится к незавершённому будущему периоду.',category='future_observation')
        row.update(source_dimensions=dimensions,source_dimension_codes=item.dimension_codes,
                   original_territory_label=territory,original_unit_label=label(dimensions,{'единица измерения','единицы измерения'}))
        output.append(row)
    if len({(r['period'],r['frequency']) for r in output}) != len(output):
        raise EmissConnectorError('Повторные ячейки национального ряда.',category='duplicate_observation')
    return output


def validate_coverage(old, incoming):
    if not incoming or not any(row['value'] is not None for row in incoming):
        raise EmissConnectorError('В ответе нет числовых наблюдений; набор не заменён.',category='empty_numeric_export')
    old_keys = {(r['period'],r['frequency']) for r in old if r['value'] is not None}
    new_keys = {(r['period'],r['frequency']) for r in incoming}
    if not old_keys <= new_keys:
        raise EmissConnectorError('Выгрузка утратила ранее опубликованные периоды. Требуется проверка полноты перед слиянием.',category='coverage_contract_changed')
    old_annual = {r['year'] for r in old if r['frequency']=='annual' and r['value'] is not None}
    new_annual = {r['year'] for r in incoming if r['frequency']=='annual' and r['value'] is not None}
    if not old_annual <= new_annual:
        raise EmissConnectorError('Самостоятельный годовой факт исчез из выгрузки.',category='annual_fact_disappeared')


def run(root=ROOT, only=None, client=None, timeout=None, retries=None, max_failures=None, rebuild=True):
    root = Path(root)
    config = load(root/'scripts/healthtech_emiss_sources.json')
    if timeout is not None:config['timeout_seconds']=timeout
    if retries is not None:config['retries']=retries
    if max_failures is not None:config['failure_circuit_breaker']=max_failures
    if config['timeout_seconds']<=0 or config['retries']<0 or config['failure_circuit_breaker']<1:
        raise ValueError('Invalid refresh limits')
    if only and str(only) not in {s['indicator_id'] for s in config['sources']}:
        raise ValueError('Unknown confirmed Health Technologies source ID')
    previous_status = load(root/DATA/'refresh-status.json')
    previous = {s['source_id']:s for s in previous_status['sources']}
    checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    owned_client = client is None
    client = client or HealthtechClient(config)
    statuses = []
    attempted=successful=published=updated=failed=deferred=consecutive=0
    try:
        for source in config['sources']:
            sid = source['indicator_id']
            prior = previous.get(sid,{})
            if only and sid != str(only):
                statuses.append(prior)
                continue
            entry = {**prior,'source_id':sid,'title':source['title']}
            if consecutive >= config['failure_circuit_breaker']:
                entry.update(state='deferred_after_source_outage',attempt_at=checked_at,
                             message='Запрос отложен после повторных ошибок доступа. Этот источник в текущем запуске не проверялся; сохранённые значения не изменены.')
                deferred+=1
                statuses.append(entry)
                continue
            attempted+=1
            entry.update(checked_at=checked_at,attempt_at=checked_at)
            try:
                meta = client.metadata(sid)
                if source['contract_status']!='verified_republished_workbook':
                    entry.update(state='metadata_requires_contract_review',metadata_checked_at=checked_at,
                                 message='Карточка доступна. Для нового числового ряда требуется подтвердить единицы, методику и состав периода; неподтверждённые значения не опубликованы.')
                    successful+=1
                    consecutive=0
                    statuses.append(entry)
                    continue
                if meta.get('no_numeric_grid'):
                    entry.update(state='metadata_only',metadata_checked_at=checked_at,
                                 message='Карточка доступна, распознаваемая числовая таблица отсутствует. Сохранённый набор оставлен без изменения.')
                    successful+=1
                    consecutive=0
                    statuses.append(entry)
                    continue
                roles,selected = query_plan(meta,source,config['max_cells'])
                parsed,structure,digest,raw = client.export(meta,selected)
                incoming = live_rows(parsed,source,checked_at)
                packet_path = root/DATA/'series'/(sid+'.json')
                packet = load(packet_path)
                validate_coverage(packet['observations'],incoming)
                merged,added,revisions = merge_observations(packet['observations'],incoming)
                raw_path = root/DOWNLOADS/'emiss_current'/(sid+'.zip')
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('data.xls',raw)
                    archive.writestr('metadata.json',json.dumps(meta,ensure_ascii=False,indent=2))
                    archive.writestr('request_filters.json',json.dumps(selected,ensure_ascii=False,indent=2))
                source_updated_at = meta.get('source_updated_at')
                next_packet = {**packet,'origin_kind':'live_emiss','direct_emiss_verified':True,'acquired_at':checked_at,
                               'verified_at':checked_at,'published_at':source_updated_at,
                               'published_at_semantics':'source_update_date' if source_updated_at else 'source_update_date_unavailable',
                               'snapshot_id':'live:'+digest,'source_input':raw_path.relative_to(root/'public').as_posix(),'observations':merged}
                provenance_path = root/DATA/'provenance'/(sid+'.json')
                provenance = load(provenance_path)
                provenance.update(origin_kind='live_emiss',direct_emiss_verified=True,acquired_at=checked_at,checked_at=checked_at,
                                  original_replication_published_at=provenance.get('original_replication_published_at',provenance.get('published_at')),
                                  published_at=source_updated_at,verified_at=checked_at,published_at_semantics=next_packet['published_at_semantics'],
                                  response_sha256=digest,current_raw=next_packet['source_input'],metadata=meta,
                                  requested_filters=selected,new_rows=added,revisions=revisions)
                # No published mutations precede successful parsing and validation.
                atomic(raw_path,buffer.getvalue())
                atomic(packet_path,next_packet)
                provenance.update(current_raw_sha256=sha256(raw_path),published_sha256=sha256(packet_path))
                atomic(provenance_path,provenance)
                changed = bool(added or revisions)
                entry.update(state='updated' if changed else 'unchanged',last_success=checked_at,published_at=source_updated_at,
                             direct_emiss_verified=True,origin_kind='live_emiss',rows=len(merged),new_rows=added,revisions=len(revisions),
                             raw_file=next_packet['source_input'],message='Прямая выгрузка проверена; изменения опубликованы.' if changed else 'Прямая выгрузка проверена; числовых изменений нет.')
                successful+=1
                published+=1
                updated+=changed
                consecutive=0
            except (EmissConnectorError, ValueError, OSError) as exc:
                failed+=1
                category = getattr(exc,'category','validation_error')
                if category in {'network_error','http_error','temporary_http','access_challenge','source_redirect'}:
                    consecutive+=1
                entry.update(state='failed',error_category=category,
                             message=redact(str(exc))+' Последний проверенный набор сохранён с прежней датой и происхождением.')
            statuses.append(entry)
    finally:
        if owned_client:client.close()
    state = 'failed' if failed and not successful else 'partial' if failed or deferred else 'success'
    published_at = max([s.get('published_at') for s in statuses if s.get('published_at')],default=None)
    result = {'schema_version':1,'project_id':PROJECT,'state':state,'checked_at':checked_at,'published_at':published_at,
              'attempted':attempted,'successful':successful,'published':published,'updated':updated,'failed':failed,'deferred':deferred,
              'direct_emiss_verified':bool(published) and all(s.get('direct_emiss_verified') for s in statuses if s.get('published_at')),
              'message':f'Прямая проверка ЕМИСС: запросов {attempted}, успешных проверок {successful}, опубликованных наборов {published}, ошибок {failed}, отложено {deferred}. Недоступность запроса не изменяет сохранённые значения.',
              'sources':statuses}
    atomic(root/DATA/'refresh-status.json',result)
    atomic(root/'monitoring/healthtech_last_refresh.json',result)
    if rebuild:build(root)
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--source',help='Confirmed EMISS source ID; omit for all twenty linked sources.')
    parser.add_argument('--timeout',type=float)
    parser.add_argument('--retries',type=int)
    parser.add_argument('--max-failures',type=int)
    parser.add_argument('--strict',action='store_true')
    args = parser.parse_args()
    result = run(args.root,args.source,timeout=args.timeout,retries=args.retries,max_failures=args.max_failures)
    print(result['message'])
    for row in result['sources']:
        if not args.source or row['source_id']==args.source:print(row['source_id'],row['state'],row.get('message',''))
    if args.strict and result['state'] in {'failed','partial'}:raise SystemExit(2)
