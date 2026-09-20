#!/usr/bin/env python3
"""Recompute monthly TFR/TFR3+ for Russia and every region with valid observations.
The archive stays immutable. Manifest records failures without erasing last good outputs.
"""
from __future__ import annotations
import argparse, copy, json, re, sys
from pathlib import Path
from datetime import datetime, timezone
from demography.indicator import forecast, VERSION
ROOT=Path(__file__).resolve().parents[1]

def load(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8');tmp.replace(p)

def observations_for(rows,region):
    rr=[r for r in rows if r['type']=='месяц' and ((str(r.get('r'))==region) if region!='RU' else bool(re.match(r'^Российская Федерация',r['territory'])))]
    groups={}
    for r in rr: groups.setdefault(r['end'],[]).append(r)
    obs=[]
    for d,g in sorted(groups.items()):
        parts=[r for r in g if re.search(r'кроме|без.*автоном',r['territory'],re.I)]
        pool=parts or g
        values={r['value'] for r in pool if isinstance(r.get('value'),(int,float))}
        if len(values)>1: raise ValueError('Противоречивые значения для одной территории и месяца: '+d)
        obs.append({'date':d,'value':next(iter(values)) if values else None,'territory':pool[0]['territory']})
    # Live exports include empty cells for periods not yet released. Do not
    # mistake those trailing placeholders for gaps inside observed history.
    while obs and obs[-1]['value'] is None:obs.pop()
    if any(r['value'] is None for r in obs):raise ValueError('Пропуск внутри месячного ряда.')
    return obs

def run(root=ROOT):
    cat=load(root/'public/data/catalog.json');latest=load(root/'public/data/latest/manifest.json');prior_path=root/'public/data/projections/indicators/manifest.json'
    prior=load(prior_path) if prior_path.exists() else {};old={(e['indicator_id'],e['region_id']):e for e in prior.get('series',[])}
    now=datetime.now(timezone.utc).isoformat(timespec='seconds');out=[]
    names={'RU':'Российская Федерация',**{r['id']:r['name'] for r in cat['regions']}}
    for sid in ['data_21','data_22']:
        info=next((x for x in latest.get('sources',[]) if x['source_id']==sid),{})
        rel=info.get('published_file') or f'data/baseline/{sid}.json';packet=load(root/'public'/rel)
        rows=[dict(zip(packet['columns'],x)) for x in packet['rows']]
        for rid,name in names.items():
            entry={'indicator_id':sid,'region_id':rid,'region_name':name,'checked_at':now}
            try:
                obs=observations_for(rows,rid);model=forecast(obs)
                prev=old.get((sid,rid),{});fp=f'data/projections/indicators/{sid}/{rid}.json';existing=root/'public'/fp
                if prev.get('input_sha256')==model['input_sha256'] and existing.exists():
                    calculated=load(existing).get('calculated_at',now)
                else: calculated=now
                model.update(region_id=rid,region_name=name,indicator_id=sid,label='СКР' if sid=='data_21' else 'СКР третьих и последующих детей',source=rel,source_snapshot=packet.get('snapshot'),calculated_at=calculated,upstream_state=info.get('state','archive'))
                write(root/'public'/fp,model)
                entry.update(state='ready',file=fp,n_observations=len(obs),source_as_of=model['source_as_of'],source=rel,input_sha256=model['input_sha256'],calculated_at=calculated,value_end=model['forecast'][-1]['value'] if model['forecast'] else obs[-1]['value'],lo95_end=model['forecast'][-1]['lo95'] if model['forecast'] else None,hi95_end=model['forecast'][-1]['hi95'] if model['forecast'] else None)
            except Exception as exc:
                prev=old.get((sid,rid),{});valid=prev.get('file') and (root/'public'/prev['file']).is_file();entry={**(prev if valid else {}),**entry,'state':'retained' if valid else 'unavailable','message':str(exc)}
            out.append(entry)
    manifest={'schema':'semya.indicator-index/1','model_version':VERSION,'checked_at':now,'end_date':'2030-12-31','ready':sum(x['state']=='ready' for x in out),'series':out}
    maps={}
    for e in out:
        if not e.get('file'):continue
        model=load(root/'public'/e['file'])
        for row in model['observations']+model['forecast']:
            maps.setdefault(e['indicator_id'],{}).setdefault(row['date'][:7],{})[e['region_id']]=row['value']
    write(root/'public/data/projections/indicators/maps.json',{'schema':'semya.projection-maps/1','values':maps})
    write(prior_path,manifest);print('Прогнозы показателей:',manifest['ready'],'из',len(out));return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);args=p.parse_args();run(args.root)
