#!/usr/bin/env python3
"""Monthly server-side refresh. Safe defaults: no guesses, no silent stale replacement.
python scripts/refresh_emiss.py [--source data_21] [--strict]
Requires httpx, json5, lxml. EMISS_PROXY_URL is optional and is never published.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,os,sys,tempfile,zipfile,io
from pathlib import Path
from datetime import datetime,timezone
from dataclasses import asdict
from emiss_adapter.client import Client,resolve_indicator,query_plan,redact
from emiss_adapter.normalize import convert,merge,unpack,territory_key,COLS
from emiss_adapter.errors import EmissConnectorError
ROOT=Path(__file__).resolve().parents[1]

def atomic(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(content,encoding='utf-8');temp.replace(path)

def run(root=ROOT,only=None,client=None):
    config=json.loads((root/'scripts/emiss_sources.json').read_text())
    catalog=json.loads((root/'public/data/catalog.json').read_text())
    latest=root/'public/data/latest';latest.mkdir(exist_ok=True,parents=True)
    old=json.loads((latest/'manifest.json').read_text()) if (latest/'manifest.json').exists() else {}
    now=datetime.now(timezone.utc).isoformat(timespec='seconds');client=client or Client(config)
    previous={s['source_id']:s for s in old.get('sources',[])};results=[];items=None;catalog_error=None;success=0;updated=0
    # Exact name matching; unresolved names remain in the per-source report.
    try:items=client.catalog()
    except Exception as exc:catalog_error=redact(exc)
    if items:atomic(latest/'catalog_discovery.json',{'checked_at':now,'items':[asdict(i) for i in items]})
    for source in config['sources']:
        sid=source['source_id'];prior=previous.get(sid,{})
        if only and sid!=only:
            results.append(prior or {'source_id':sid,'state':'not_checked','message':'Не входил в выбранный запуск'});continue
        entry={**prior,'source_id':sid,'checked_at':now};raw_hashes=[];raw_files=[]
        try:
            remote_id=source.get('indicator_id') or prior.get('indicator_id')
            if not remote_id:
                if items is None:raise EmissConnectorError('Каталог недоступен: '+str(catalog_error),category='catalog_unavailable')
                remote_id=resolve_indicator(items,source['titles']).indicator_id
            entry['indicator_id']=str(remote_id)
            meta=client.metadata(remote_id);roles,selected=query_plan(meta,source,config['max_cells'])
            aliases={territory_key(r['name']):r['id'] for r in catalog['regions']}
            base=json.loads((root/'public/data/baseline'/f'{sid}.json').read_text())
            base_rows=unpack(base)
            for r in base_rows:
                if r.get('r'):aliases[territory_key(r['territory'])]=r['r']
            # All methods validate complete source before publication.
            parsed,structure,digest,raw=client.export(meta,selected);raw_hashes.append(digest);raw_files.append(('full.xml',raw))
            try:incoming=convert(parsed,meta,roles,selected,source,aliases,now)
            except EmissConnectorError as exc:
                if exc.category!='ambiguous_period' or 'month' not in roles:raise
                # Some exports omit period labels. Request one explicit period at a time.
                incoming=[];period_field=roles['month']
                for value in selected[period_field]:
                    single=copy.deepcopy(selected);single[period_field]=[value]
                    part,_,digest,part_raw=client.export(meta,single);raw_hashes.append(digest);raw_files.append((f'period_{len(raw_files):03d}.xml',part_raw))
                    incoming.extend(convert(part,meta,roles,single,source,aliases,now))
            prev_file=prior.get('published_file')
            packet=json.loads((root/'public'/prev_file).read_text()) if prev_file and (root/'public'/prev_file).exists() else base
            merged,n_new,revisions=merge(unpack(packet),incoming)
            target=f'data/latest/{sid}.json';payload={'schema':'semya.series/1','source_id':sid,'columns':COLS,'rows':[[r.get(k) for k in COLS] for r in merged],'basis':'validated_emiss_merged_with_history','snapshot':now,'emiss_id':str(remote_id),'source_url':config['base_url']+'/indicator/'+str(remote_id),'unit':source['unit']}
            raw_path = latest/f'{sid}_raw_sdmx.zip'
            raw_tmp = raw_path.with_suffix('.zip.tmp')
            with zipfile.ZipFile(raw_tmp,'w',zipfile.ZIP_DEFLATED) as z:
                for name, body in raw_files: z.writestr(name,body)
            raw_tmp.replace(raw_path)
            atomic(root/'public'/target,payload)
            atomic(latest/f'{sid}_provenance.json',{'checked_at':now,'indicator_id':str(remote_id),'source_url':payload['source_url'],'metadata':meta,'roles':roles,'requested_filters':selected,'response_sha256':raw_hashes,'source_observations_received':len(incoming),'new_rows':n_new,'revisions':revisions,'note':'Previously observed numbers are retained when a new export contains missing values. No arbitrary category or sequential-month imputation.'})
            entry.update(raw_file=f'data/latest/{sid}_raw_sdmx.zip',provenance_file=f'data/latest/{sid}_provenance.json',state='updated' if n_new or revisions else 'unchanged',published_file=target,fetched_at=now,last_success=now,new_rows=n_new,revisions=len(revisions),rows=len(merged),message='Проверено; новые данные объединены с сохранённой историей.' if n_new or revisions else 'Проверено; числовых изменений нет.')
            success+=1;updated+=bool(n_new or revisions)
        except Exception as exc:
            entry.update(state=getattr(exc,'category','failed'),message=redact(exc),new_rows=0,revisions=0)
            # Keep prior published_file, fetched_at, last_success, and last good observations.
        results.append(entry)
    discoveries=[]
    for candidate in config.get('discovery_only',[]):
        try:
            match=resolve_indicator(items or [],[candidate['title']]);discoveries.append({**candidate,'indicator_id':match.indicator_id,'state':'needs_contract_review','message':'Источник найден; перед публикацией требуется подтверждение измерений и единиц.'})
        except Exception as exc:discoveries.append({**candidate,'state':'not_resolved','message':redact(exc)})
    atomic(latest/'unobserved_discovery.json',{'checked_at':now,'indicators':discoveries})
    n_attempted=1 if only else len(config['sources'])
    status='failed' if not success else 'partial' if success<n_attempted else 'success' if updated else 'unchanged'
    manifest={'schema':'semya.update/1','state':status,'checked_at':now,'last_success':now if success else old.get('last_success'),'snapshot':'2026-05-14','message':f'Проверено источников: {success} из {n_attempted}. Обновлённые файлы: {updated}. Неуспешные запросы не заменяют сохранённые данные.','sources':results}
    atomic(latest/'manifest.json',manifest)
    logs=root/'monitoring';logs.mkdir(exist_ok=True)
    atomic(logs/'last_refresh.json',manifest)
    client.close();return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',help='Only one configured source_id');p.add_argument('--strict',action='store_true');args=p.parse_args()
    if args.source and args.source not in {f'data_{i}' for i in range(20,36)}:p.error('Unknown source')
    status=run(only=args.source);print(status['message'])
    for source in status['sources']:print(source['source_id'],source['state'],source.get('message',''))
    if args.strict and status['state'] in {'partial','failed'}:sys.exit(2)
