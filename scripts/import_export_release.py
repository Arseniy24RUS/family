#!/usr/bin/env python3
"""Replay the complete pinned Export statistical snapshot without a network request."""
from pathlib import Path
import argparse, collections, csv, gzip, json, zipfile
from lxml import html
from export_data import *

def run(root=ROOT,from_inputs=True):
 root=Path(root);folder=root/'inputs/international_export/statistics'
 metadata={r['source_id']:r for r in load(folder/'sources.json')}
 rows=list(csv.DictReader(gzip.open(folder/'observations_snapshot.csv.gz','rt',encoding='utf-8-sig')))
 aliases=region_aliases(root);regions={str(r['id']):r for r in load(root/'public/data/catalog.json')['regions']}
 contracts=[];statuses=[];receipts=[]
 for sid in SOURCE_ORDER:
  selected=[r for r in rows if r['source_id']==sid];m=metadata[sid];original=folder/'originals'/sid
  savedmeta=load(original/'metadata.json');tree=html.fromstring((original/'metadata.html').read_bytes())
  method=tree.xpath('//*[@id="methodologyFull"]');method=' '.join(method[0].text_content().split()) if method else ''
  units={r['unit'] for r in selected};assert len(units)==1
  unit=next(iter(units));territory_fields=[f for f in savedmeta['filters'] if 'окато' in f.get('title','').casefold()]
  contract={'source_id':sid,'indicator_id':sid,'indicator_codes':[MAPPING[sid]],'title':m['source_title'],'titles':[m['source_title']],
   'source_url':m['source_url'],'unit':unit,'methodology':method,'metadata_sha256':sha256(original/'metadata.html'),
   'first_year':min(int(r['year']) for r in selected),'dimension_defaults':{},'field_overrides':{'territory':territory_fields[0]['field_id']} if len(territory_fields)==1 else {},
   'expected_period_types':['год','месяц','накопительно с января','квартал'],'known_territories':sorted({r['territory_name'] for r in selected}),
   'period_kind_by_label':{json.loads(r['dimensions_json'])['Период']:r['period_kind'] for r in selected},
   'min_regional_count':0,'export_format':FORMATS[sid],'semantic_note':NOTES[sid][2]}
  observations=sorted([normalize_record(r,contract,aliases,regions) for r in selected],key=lambda r:(r['period_end'],r['name'],r['id']))
  assert len({r['id'] for r in observations})==len(observations)
  packet={'schema_version':1,'project_id':'international_export','source_id':sid,'title':m['source_title'],'unit':unit,'source_url':m['source_url'],
   'published_at':m['current_snapshot_acquired_at'],'statistical_as_of':STATISTICAL_AS_OF,'snapshot_id':selected[0]['snapshot_id'],
   'origin_kind':'live_emiss','semantic_note':NOTES[sid][2],'observations':observations}
  output=root/DATA/'series'/f'{sid}.json';atomic(output,packet)
  bundle=root/DOWNLOADS/'emiss_inputs'/f'{sid}.zip';bundle.parent.mkdir(parents=True,exist_ok=True)
  evidence=[]
  with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
   z.writestr('observations.json',json.dumps(selected,ensure_ascii=False,indent=2))
   for p in sorted(original.rglob('*')):
    if not p.is_file():continue
    rel='source/'+p.relative_to(original).as_posix();z.write(p,rel);evidence.append({'path':rel,'bytes':p.stat().st_size,'sha256':sha256(p)})
   z.writestr('provenance.json',json.dumps({'source_id':sid,'source_url':m['source_url'],'snapshot_id':selected[0]['snapshot_id'],'acquired_at':m['current_snapshot_acquired_at'],'evidence_files':evidence},ensure_ascii=False,indent=2))
  receipt={'schema_version':1,'source_id':sid,'source_url':m['source_url'],'snapshot_id':selected[0]['snapshot_id'],'acquired_at':m['current_snapshot_acquired_at'],
   'statistical_as_of':STATISTICAL_AS_OF,'origin_kind':'live_emiss','observations':len(observations),'numeric':sum(r['value'] is not None for r in observations),
   'published_file':str((DATA/'series'/f'{sid}.json').relative_to('public')),'published_sha256':sha256(output),
   'input_bundle':str((DOWNLOADS/'emiss_inputs'/f'{sid}.zip').relative_to('public')),'input_sha256':sha256(bundle),'evidence_files':evidence,
   'period_policy':'Original source periods, frequencies and numerical cells are retained. Annual and December observations are separate. Monetary exports are calendar YTD in nominal USD. A new annual infrastructure programme resets independently of existing assets. The 2.0 standard series is not the 3.0 passport indicator. Missing is not zero.'}
  atomic(root/DATA/'provenance'/f'{sid}.json',receipt);receipts.append(receipt);contracts.append(contract)
  statuses.append({'source_id':sid,'title':m['source_title'],'state':'verified_source_snapshot','checked_at':m['current_snapshot_acquired_at'],'published_at':m['current_snapshot_acquired_at'],'last_success':m['current_snapshot_acquired_at'],'rows':len(observations),'message':'Сохранённый срез ЕМИСС. Новое сетевое обновление при сборке не выполнялось.'})
 latest=max(r['published_at'] for r in statuses)
 atomic(root/'scripts/export_emiss_sources.json',{'schema_version':1,'project_id':'international_export','base_url':'https://www.fedstat.ru','allowed_hosts':['www.fedstat.ru','fedstat.ru'],'max_cells':300000,'timeout_seconds':25,'retries':1,'min_interval_seconds':1,'min_download_interval_seconds':45,'export_retry_delay_seconds':15,'failure_circuit_breaker':3,'sources':contracts})
 atomic(root/DATA/'refresh-status.json',{'schema_version':1,'project_id':'international_export','state':'imported_verified_snapshot','checked_at':latest,'published_at':latest,'statistical_as_of':STATISTICAL_AS_OF,'last_success':latest,'attempted_sources':0,'successful_sources':0,'message':'Статистический срез от 15.10.2026. Дата сборки сайта не является датой обновления наблюдений.','sources':statuses})
 atomic(root/DATA/'import-validation.json',{'schema_version':1,'source_contracts':len(receipts),'numeric_sources':len(receipts),'observations':len(rows),'numeric':sum(r['numeric'] for r in receipts),'source_snapshot_sha256':sha256(folder/'observations_snapshot.csv.gz'),'sources':receipts,'replay_command':'python scripts/import_export_release.py --from-inputs'})
 if (folder/'metadata_sources.json').exists():atomic(root/DATA/'metadata-sources.json',load(folder/'metadata_sources.json'))
 print(json.dumps({'sources':len(receipts),'observations':len(rows),'numeric':sum(r['numeric'] for r in receipts)}));return receipts

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--from-inputs',action='store_true');a=p.parse_args();run(a.root)
