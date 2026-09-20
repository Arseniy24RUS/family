#!/usr/bin/env python3
"""Reproduce a downloaded individual forecast or cohort package using Python 3.11+."""
import argparse,json,math
from pathlib import Path
from demography.indicator import forecast, VERSION
from demography.indicator_v11 import forecast as legacy_forecast, VERSION as LEGACY_VERSION
from demography.cohort import simulate

def same(a,b,path='root'):
    if isinstance(a,(int,float)) and not isinstance(a,bool):
        if not isinstance(b,(int,float)) or not math.isclose(a,b,rel_tol=2e-10,abs_tol=2e-6):raise ValueError(f'Несовпадение {path}: {a} ≠ {b}')
    elif isinstance(a,list):
        if len(a)!=len(b):raise ValueError('Несовпадение длины '+path)
        for i,(x,y) in enumerate(zip(a,b)):same(x,y,path+f'[{i}]')
    elif isinstance(a,dict):
        for k,v in a.items():
            if k not in b:raise ValueError('Нет поля '+path+'.'+k)
            same(v,b[k],path+'.'+k)
    elif a!=b:raise ValueError('Несовпадение '+path)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('kind',choices=['indicator','cohort']);p.add_argument('file',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
    saved=json.loads(args.file.read_text(encoding='utf-8-sig'))
    if args.kind=='indicator':
        version=saved.get('model_version')
        if version == VERSION: runner=forecast
        elif version == LEGACY_VERSION: runner=legacy_forecast
        else: raise ValueError('Неподдерживаемая версия модели: '+str(version))
        fresh=runner(saved['observations'],saved['end_date'])
        if saved.get('model_version')!=fresh['model_version']:raise ValueError('Версия модели изменилась; используйте код из того же релиза, что и JSON.')
        for key in ['forecast','models','backtest','input_sha256','ensemble_backtest','parameters','validation','curvature']:
            if key in fresh: same(fresh[key],saved[key],key)
        print('Совпали траектории, параметры весов, проверки и хеш входа.')
    else:
        data=saved.get('input',saved);fresh=simulate(data,saved.get('options',{}));old=saved.get('result')
        if old:
            if old.get('model_version')!=fresh['model_version']:raise ValueError('Версия алгоритма изменилась; нужен код соответствующего релиза.')
            same(fresh['months'],old['months'],'months');same(fresh['max_balance_residual'],old['max_balance_residual'],'balance')
            print('Проверены все месяцы, возрастные ячейки и демографический баланс.')
        else:print('Входной файл рассчитан; эталонный результат не приложен.')
    if args.output:args.output.write_text(json.dumps(fresh,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
