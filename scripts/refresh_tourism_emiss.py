#!/usr/bin/env python3
"""Refresh only six confirmed Tourism sources; validation failures preserve published rows.

Run explicitly or in GitHub Actions. The normal site build performs no network request.
python scripts/refresh_tourism_emiss.py --source 62900 --timeout 25 --retries 1
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, hashlib, json, zipfile
from tourism_data import *
from refresh_dataeconomy_emiss import DataeconomyClient
from dataeconomy_data import decode_period
from emiss_adapter.client import query_plan, redact
from emiss_adapter.normalize import values_for_field
from emiss_adapter.errors import EmissConnectorError

def normalized_live(items,meta,roles,selected,contract,aliases,checked_at,regions):
 rows=[]
 for item in items:
  if item.value_status=='invalid':raise EmissConnectorError('Нечисловая ячейка источника.',category='invalid_numeric')
  dimensions={}
  for field in meta['filters']:
   fid=str(field['field_id']);value=values_for_field(item,fid,meta,selected)
   if value is None and fid==roles.get('year'):value=item.period
   if value is None:raise EmissConnectorError('Не восстановлено измерение '+field['title'],category='ambiguous_dimension')
   dimensions[field['title']]=value
  territory=values_for_field(item,roles.get('territory'),meta,selected)
  if not territory:raise EmissConnectorError('Не определена территория.',category='ambiguous_territory')
  year=values_for_field(item,roles.get('year'),meta,selected) or item.period
  label=values_for_field(item,roles.get('month'),meta,selected) if 'month' in roles else 'значение показателя за год'
  known=contract.get('period_kind_by_label',{}).get(str(label));frequency,start,end,_=decode_period(year,label,known)
  units={str(value).strip().casefold() for key,value in dimensions.items() if 'единиц' in key.casefold()}
  if units!={contract['unit'].strip().casefold()}:raise EmissConnectorError('Единица измерения не совпала с контрактом.',category='unit_mismatch')
  dimensions['Период']=label
  raw={'source_id':contract['indicator_id'],'unit':contract['unit'],'period_kind':frequency,'period_start':start,'period_end':end,'year':int(year),'territory_name':territory,
   'value_numeric':item.value,'value_raw':item.raw_value,'value_status':item.value_status,'dimensions_json':json.dumps(dimensions,ensure_ascii=False),
   'attributes_json':json.dumps(item.attributes,ensure_ascii=False),'acquired_at':checked_at,'origin_kind':'live_emiss'}
  row=normalize_record(raw,contract,aliases,regions)
  if row['value'] is not None and row['period_end']>checked_at[:10]:raise EmissConnectorError('Число относится к незавершённому периоду.',category='future_observation')
  rows.append(row)
 if not rows or not any(r['value'] is not None for r in rows):raise EmissConnectorError('Выгрузка не содержит числовых наблюдений.',category='empty_numeric_export')
 if len({r['id'] for r in rows})!=len(rows):raise EmissConnectorError('Повтор ключа наблюдения.',category='conflicting_duplicates')
 if len({r['map_id'] for r in rows if r['geo_level']=='regional' and r['value'] is not None})<contract.get('min_regional_count',0):raise EmissConnectorError('Сократился подтверждённый охват регионов.',category='coverage_drop')
 if not {territory_key(n) for n in contract['known_territories']}.issubset({territory_key(r['name']) for r in rows}):raise EmissConnectorError('В полной выгрузке исчезла подтверждённая территория.',category='geography_coverage_drop')
 return rows

def run(root=ROOT,only=None,client=None,timeout=None,retries=None,max_failures=None,rebuild=True):
 root=Path(root);config=load(root/'scripts/tourism_emiss_sources.json')
 if timeout is not None:config['timeout_seconds']=timeout
 if retries is not None:config['retries']=retries
 if max_failures is not None:config['failure_circuit_breaker']=max_failures
 if config['timeout_seconds']<=0 or config['retries']<0 or config['failure_circuit_breaker']<1:raise ValueError('Invalid retry limits')
 if only and str(only) not in SOURCE_ORDER:raise ValueError('Unknown confirmed Tourism source ID')
 previous=load(root/DATA/'refresh-status.json');byid={r['source_id']:r for r in previous.get('sources',[])};checked=datetime.now(timezone.utc).isoformat(timespec='seconds')
 aliases=region_aliases(root);regions={str(r['id']):r for r in load(root/'public/data/catalog.json')['regions']};client=client or DataeconomyClient(config)
 statuses=[];attempted=success=failed=updated=deferred=consecutive=0
 try:
  for contract in config['sources']:
   sid=contract['indicator_id'];prior=byid.get(sid,{})
   if only and sid!=str(only):statuses.append(prior);continue
   if consecutive>=config['failure_circuit_breaker']:
    statuses.append({**prior,'source_id':sid,'state':'deferred_after_source_outage','attempt_at':checked,'message':'Источник не проверялся после повторных ошибок. Предыдущие данные сохранены.'});deferred+=1;continue
   attempted+=1;entry={**prior,'source_id':sid,'title':contract['title'],'checked_at':checked,'attempt_at':checked}
   try:
    meta=client.metadata(sid)
    if meta.get('no_numeric_grid'):raise EmissConnectorError('Числовая таблица отсутствует. Предыдущие данные сохранены.',category='no_numeric_grid')
    roles,selected=query_plan(meta,contract,config['max_cells']);parsed,_,digest,raw=client.export(meta,selected)
    incoming=normalized_live(parsed,meta,roles,selected,contract,aliases,checked,regions)
    path=root/DATA/'series'/f'{sid}.json';packet=load(path)
    old_categories={json.dumps(r['category'],ensure_ascii=False,sort_keys=True) for r in packet['observations']};new_categories={json.dumps(r['category'],ensure_ascii=False,sort_keys=True) for r in incoming}
    if not new_categories.issubset(old_categories):raise EmissConnectorError('Изменился состав категорий.',category='dimension_contract_changed')
    merged,added,revisions=merge_observations(packet['observations'],incoming);next_packet={**packet,'published_at':checked,'statistical_as_of':checked[:10],'snapshot_id':'live:'+digest,'observations':merged}
    current=root/DOWNLOADS/'emiss_current'/f'{sid}.zip';current.parent.mkdir(parents=True,exist_ok=True);temp=current.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
     z.writestr('data.xls',raw);z.writestr('metadata.json',json.dumps(meta,ensure_ascii=False,indent=2));z.writestr('selected.json',json.dumps(selected,ensure_ascii=False,indent=2))
    temp.replace(current)
    # Validation has finished before the single atomic replacement of the series.
    atomic(path,next_packet)
    provenance=load(root/DATA/'provenance'/f'{sid}.json');provenance.update(acquired_at=checked,snapshot_id='live:'+digest,published_sha256=sha256(path),response_sha256=digest,current_raw=current.relative_to(root/'public').as_posix(),current_raw_sha256=sha256(current),observations=len(merged),numeric=sum(r['value'] is not None for r in merged),new_rows=added,revisions=revisions)
    atomic(root/DATA/'provenance'/f'{sid}.json',provenance)
    changed=bool(added or revisions);entry.update(state='updated' if changed else 'unchanged',last_success=checked,published_at=checked,rows=len(merged),new_rows=added,revisions=len(revisions),message='Проверены единицы, методика, периоды и территории. Подтверждённые данные опубликованы.');success+=1;updated+=changed;consecutive=0
   except Exception as exc:
    category=getattr(exc,'category','validation_failed');entry.update(state=category,message=redact(exc),new_rows=0,revisions=0);failed+=1
    consecutive=consecutive+1 if category in {'network_error','http_error','temporary_http','access_challenge','source_redirect'} else 0
   statuses.append(entry)
 finally:client.close()
 dates=[r['published_at'] for r in statuses if r.get('published_at')];published=max(dates) if dates else previous.get('published_at')
 report={'schema_version':1,'project_id':'tourism','state':'failed' if not success else 'partial' if failed or deferred else 'updated' if updated else 'unchanged','checked_at':checked,'published_at':published,
  'statistical_as_of':published[:10] if published else previous.get('statistical_as_of'),'last_success':checked if success else previous.get('last_success'),'attempted_sources':attempted,'successful_sources':success,'published_sources':success,'updated_sources':updated,'failed_sources':failed,'deferred_sources':deferred,
  'message':f'Запрошено источников: {attempted}. Подтверждено: {success}. Ошибок: {failed}. Отложено: {deferred}. Неподтверждённые ответы не изменяют опубликованные наблюдения.','sources':statuses}
 atomic(root/DATA/'refresh-status.json',report)
 atomic(root/'monitoring/tourism_last_refresh.json',report)
 if rebuild:
  from build_tourism_analytics import build
  build(root)
 return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--source');p.add_argument('--timeout',type=float);p.add_argument('--retries',type=int);p.add_argument('--max-failures',type=int);p.add_argument('--strict',action='store_true');p.add_argument('--no-rebuild',action='store_true');a=p.parse_args();result=run(a.root,a.source,timeout=a.timeout,retries=a.retries,max_failures=a.max_failures,rebuild=not a.no_rebuild);print(json.dumps(result,ensure_ascii=False));raise SystemExit(1 if a.strict and result['state'] in ('failed','partial') else 0)
