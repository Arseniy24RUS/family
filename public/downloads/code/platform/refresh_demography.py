#!/usr/bin/env python3
"""Fetch observed age-sex inputs, refresh monthly demographic projections, retain valid snapshots.
Usage: python scripts/refresh_demography.py --fetch
Offline/custom inputs: place semya.cohort-input/1 JSON files in inputs/cohort/.
Missing external inputs are reported in the published manifest, never fabricated.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, sys, shutil
from pathlib import Path
from datetime import datetime,timezone
from demography.cohort import simulate, validate_input, VERSION
from demography.repository_inputs import fetch_repository, build_inputs, FILES
from build_indicator_forecasts import write,load,run as indicators_run
ROOT=Path(__file__).resolve().parents[1]

def run(root=ROOT,fetch=False,strict=False):
    now=datetime.now(timezone.utc).isoformat(timespec='seconds');cache=root/'inputs/upstream';cache.mkdir(parents=True,exist_ok=True)
    source=load(cache/'manifest.json') if (cache/'manifest.json').exists() else {'state':'not_fetched','message':'Внешняя возрастная база ещё не получена.'}
    if fetch:
        source=fetch_repository(cache);write(cache/'manifest.json',source)
    prior_path=root/'public/data/projections/population/manifest.json';prior=load(prior_path) if prior_path.exists() else {};old={r['region_id']:r for r in prior.get('regions',[])}
    cat=load(root/'public/data/catalog.json');names={'RU':'Российская Федерация',**{r['id']:r['name'] for r in cat['regions']}}
    inputs={};issues={}
    if all((cache/f).exists() for f in FILES):
        try:
            objects,missing=build_inputs(root,cache);inputs={x['region_id']:x for x in objects};issues={x['region_id']:x['message'] for x in missing}
            # Public immutable source copies make the successful calculation independently downloadable.
            for filename in FILES:
                dest=root/'public/downloads/demography/upstream'/filename;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(cache/filename,dest)
            write(root/'public/downloads/demography/upstream/manifest.json',source)
        except Exception as exc:
            issues={rid:'Ошибка контракта внешних данных: '+str(exc) for rid in names}
    else:issues={rid:'Не загружены наблюдаемые возрастные базы и компоненты из авторского репозитория.' for rid in names}
    local_errors=[]
    for p in sorted((root/'inputs/cohort').glob('*.json')) if (root/'inputs/cohort').exists() else []:
        target=p.stem
        try:
            obj=load(p);rid=obj['region_id'];target=rid
            if rid not in names:raise ValueError('Регион отсутствует в справочнике платформы')
            validate_input(obj);inputs[rid]=obj;issues.pop(rid,None)
        except Exception as exc:
            inputs.pop(target,None);issues[target]='Не принят локальный вход: '+str(exc);local_errors.append({'file':p.name,'message':str(exc)})
    entries=[]
    for rid,name in names.items():
        entry={**old.get(rid,{}),'region_id':rid,'region_name':name,'checked_at':now}
        try:
            if rid not in inputs:raise ValueError(issues.get(rid,'Исходные данные недоступны'))
            obj=inputs[rid]
            # Adopt the next month after the last observed monthly fertility coefficient as scenario origin.
            ip=root/f'public/data/projections/indicators/data_21/{rid}.json'
            if ip.exists():
                d=load(ip);n=int(d['source_as_of'][:4])*12+int(d['source_as_of'][5:7]);y,m=divmod(n,12)
                obj.setdefault('scenario_start',max(obj['base_date'],f'{y:04d}-{m+1:02d}-01'))
            payload=json.dumps({'input':obj,'engine':VERSION},sort_keys=True,ensure_ascii=False,allow_nan=False).encode();digest=hashlib.sha256(payload).hexdigest()
            basepath=f'data/projections/population/{rid}';input_file=basepath+'/input.json'
            # Recompute from scratch; this is a short horizon and inexpensive. Previous outputs stay intact until both scenarios pass.
            results={'with_migration':simulate(obj),'no_migration':simulate(obj,{'migration_scale':0})}
            calculated=entry.get('calculated_at') if entry.get('input_sha256')==digest else now
            for label,result in results.items():result.update(calculated_at=calculated,input_sha256=digest,scenario=label)
            write(root/'public'/input_file,obj)
            paths={}
            for label,result in results.items():
                fn=basepath+'/'+label+'.json';write(root/'public'/fn,result);paths[label]=fn
            entry.update(state='ready',input_file=input_file,result_files=paths,input_sha256=digest,calculated_at=calculated,base_date=obj['base_date'],scenario_start=obj.get('scenario_start',obj['base_date']),population_base=sum(sum(a) for a in obj['population'].values()),population_end=results['with_migration']['months'][-1]['population'],months=len(results['with_migration']['months']),max_balance_residual=max(r['max_balance_residual'] for r in results.values()),message='Рассчитано на проверенных входах; происхождение компонент раскрыто в JSON.')
        except Exception as exc:
            valid_old=set(entry.get('result_files',{}))=={'with_migration','no_migration'} and entry.get('input_file') and (root/'public'/entry['input_file']).exists() and all((root/'public'/p).exists() for p in entry.get('result_files',{}).values())
            entry.update(state='retained' if valid_old else 'unavailable',message=str(exc))
        entries.append(entry)
    ready=sum(e['state']=='ready' for e in entries);retained=sum(e['state']=='retained' for e in entries)
    manifest={'schema':'semya.population-index/1','engine_version':VERSION,'checked_at':now,'last_success':now if ready else prior.get('last_success'),'state':'ready' if ready==len(entries) else 'partial' if ready+retained else 'awaiting_inputs','end_date':'2030-12-31','ready':ready,'retained':retained,'unavailable':len(entries)-ready-retained,'source':source,'local_input_errors':local_errors,'regions':entries,'interpretation':'Месячный вычислительный шаг. Новые фактические наблюдения поступают с периодичностью каждого источника. Отсутствующая возрастная структура не восстанавливается искусственно.'}
    write(prior_path,manifest);print(f'Передвижка: {ready} рассчитано, {retained} сохранено, {len(entries)-ready-retained} без достаточных входов.');return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--fetch',action='store_true');p.add_argument('--strict',action='store_true');p.add_argument('--indicators',action='store_true');a=p.parse_args()
    if a.indicators:indicators_run(a.root)
    m=run(a.root,a.fetch,a.strict)
    if a.strict and m['ready']<86:sys.exit(2)
