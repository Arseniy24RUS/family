"""Monthly cohort-component engine with an explicit 100+ open age group.

Single-year baseline cells are disaggregated into twelve equally-sized birth-month
subcohorts (an assumption, not new observed information). Residents age by exactly
one month. Births, deaths, and net migration reconcile to the stock identity.
Inputs with missing cells or impossible emigration are rejected, not repaired.
"""
from __future__ import annotations
import math
from datetime import date

VERSION = 'cohort-monthly/1.1.1'
SEXES = ('male','female')
N_AGE = 101
END = '2030-12-31'


def normalized(values):
    if not isinstance(values,(list,tuple)) or any(not isinstance(x,(int,float)) or isinstance(x,bool) for x in values):
        raise ValueError('Профиль должен содержать только числа.')
    a = [float(x) for x in values]
    if not all(math.isfinite(x) and x >= 0 for x in a) or not math.isfinite(sum(a)) or sum(a) <= 0:
        raise ValueError('Возрастной профиль должен быть конечным, неотрицательным и ненулевым.')
    total=sum(a)
    return [x/total for x in a]


def fertility_profile(mean_age=28., sd=6.):
    return normalized([math.exp(-.5*((a+.5-mean_age)/sd)**2) if 15 <= a <= 49 else 0 for a in range(N_AGE)])


def migration_profile():
    # A declared smooth scenario profile; not an estimated Rogers-Castro model.
    return normalized([math.exp(-.5*((a-27)/9)**2)+.20*math.exp(-.5*((a-7)/5)**2)
                      +.08*math.exp(-.5*((a-62)/8)**2) for a in range(N_AGE)])


def life_e0(hazards):
    survival=1.; expectation=0.
    for m in hazards[:100]:
        expectation += survival * (-math.expm1(-m)/m if m else 1.)
        survival *= math.exp(-m)
    return expectation + survival / hazards[100] if hazards[100] > 0 else math.inf


def mortality_from_e0(e0, sex):
    """Calibrate a model life table; one e0 cannot identify observed age mortality."""
    if not isinstance(e0,(int,float)) or isinstance(e0,bool):raise ValueError('ОПЖ должна быть числом.')
    e0=float(e0)
    if sex not in SEXES or not math.isfinite(e0) or not 30 <= e0 <= 100:
        raise ValueError('ОПЖ для сценарной таблицы должна находиться в интервале 30–100 лет.')
    multiplier=1.25 if sex=='male' else .85
    template=[(.004 if sex=='male' else .0032) if a==0 else
        .00013 + multiplier*.000035*math.exp(.092*a) +
        ((.0003 if sex=='male' else .00008)*math.exp(-.5*((a-23)/7)**2)) for a in range(N_AGE)]
    lo,hi=.005,20.
    for _ in range(80):
        mid=(lo+hi)/2
        actual=life_e0([v*mid for v in template])
        if actual>e0:lo=mid
        else:hi=mid
    hazard=[v*(lo+hi)/2 for v in template]
    return {'qx':[-math.expm1(-m) for m in hazard],'e0':life_e0(hazard),'target_e0':e0,
        'kind':'model life table calibrated to e0, NOT observed age-specific mortality'}


def annual_value(values, year):
    if not values:
        raise ValueError('Пустая годовая траектория.')
    eligible=sorted(int(k) for k in values if int(k)<=year)
    if not eligible:
        raise ValueError(f'Нет значения компоненты на базовый год {year} или ранее.')
    v=values[str(eligible[-1])] if str(eligible[-1]) in values else values[eligible[-1]]
    v=float(v)
    if not math.isfinite(v):raise ValueError('Нечисловой компонент прогноза.')
    return v


def validate_input(data):
    if data.get('schema')!='semya.cohort-input/1':
        raise ValueError('Ожидается схема semya.cohort-input/1.')
    start=date.fromisoformat(data['base_date'])
    scenario=date.fromisoformat(data.get('scenario_start',data['base_date']))
    if scenario.day!=1 or scenario<start or scenario>=date(2031,1,1):raise ValueError('Сценарная дата должна быть первым числом месяца от базы до 2031 года.')
    if start.day!=1 or start.year < 2000 or start >= date(2031,1,1):
        raise ValueError('Базовая дата должна быть первым числом месяца до 2031 года, не ранее 2000 года.')
    for sex in SEXES:
        pop=data['population'][sex]
        if len(pop)!=N_AGE or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in pop) or not math.isfinite(sum(pop)) or sum(pop)<=0:
            raise ValueError(f'{sex}: нужны 101 наблюдение по возрастам 0–99 и 100+, без пропусков.')
        mort=data['mortality'][sex]
        if 'qx' in mort:
            q=mort['qx']
            if len(q)!=N_AGE or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=1 for v in q):
                raise ValueError('qx: ожидаются 101 вероятность от 0 до 1.')
        else:
            mortality_from_e0(annual_value(mort['annual_e0'],start.year),sex)
        mig=data['migration'][sex]
        annual_value(mig['annual_net'],start.year)
        w=normalized(mig['weights'])
        if len(w)!=N_AGE:raise ValueError('Миграционный профиль должен иметь 101 ячейку.')
    for sex in SEXES:
        for year,value in data['migration'][sex]['annual_net'].items():
            if not str(year).isdigit() or not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):raise ValueError('Некорректная годовая миграционная траектория')
        for year,value in data['mortality'][sex].get('annual_e0',{}).items():
            if not str(year).isdigit() or not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not 30<=value<=100:raise ValueError('Некорректная годовая траектория ОПЖ')
    f=data['fertility'];w=normalized(f['weights'])
    for year,value in f['annual_tfr'].items():
        if not str(year).isdigit() or not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:raise ValueError('Некорректная годовая траектория СКР')
    if len(w)!=N_AGE or any(x>0 for i,x in enumerate(w) if i<15 or i>49):
        raise ValueError('Возрастные веса рождаемости допустимы только в возрастах 15–49.')
    if annual_value(f['annual_tfr'],start.year)<0:raise ValueError('СКР не может быть отрицательным.')
    for key,value in f.get('monthly_tfr',{}).items():
        date.fromisoformat(key+'-01')
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:raise ValueError('Некорректная месячная траектория СКР.')
    raw_ratio=data.get('sex_ratio',105.6)
    if not isinstance(raw_ratio,(int,float)) or isinstance(raw_ratio,bool):raise ValueError('Соотношение полов должно быть числом.')
    ratio=float(raw_ratio)
    if not 90<=ratio<=120:raise ValueError('Соотношение полов при рождении вне диапазона 90–120.')
    return True


def aggregate_age(pop):
    return [sum(pop[a*12:a*12+12]) for a in range(100)]+[pop[1200]]


def simulate(data, options=None):
    validate_input(data)
    opt={'migration_scale':1.,'fertility_scale_end':1.,'e0_delta_end':0.} | (options or {})
    for k, bounds in {'migration_scale':(0,3),'fertility_scale_end':(.25,3),'e0_delta_end':(-15,15)}.items():
        v=opt[k]
        if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or not bounds[0]<=v<=bounds[1]:
            raise ValueError(f'Параметр {k} вне допустимого диапазона {bounds}.')
    start=date.fromisoformat(data['base_date']);start_n=start.year*12+start.month-1;end_n=2030*12+11
    scenario=date.fromisoformat(data.get('scenario_start',data['base_date']));scenario_n=scenario.year*12+scenario.month-1
    stocks={s:[v/12 for v in data['population'][s][:100] for _ in range(12)]+[float(data['population'][s][100])] for s in SEXES}
    fw=normalized(data['fertility']['weights']);mw={s:normalized(data['migration'][s]['weights']) for s in SEXES}
    share_m=data.get('sex_ratio',105.6)/(100+data.get('sex_ratio',105.6))
    monthly=[];max_balance=0.;cache={}
    for n in range(start_n,end_n+1):
        year,month=divmod(n,12);month+=1;key=f'{year:04d}-{month:02d}'
        progress=max(0,(n-scenario_n)/max(1,end_n-scenario_n))
        tfr=data['fertility'].get('monthly_tfr',{}).get(key)
        if tfr is None:tfr=annual_value(data['fertility']['annual_tfr'],year)
        tfr*=1+(opt['fertility_scale_end']-1)*progress
        before={s:sum(stocks[s]) for s in SEXES};start_f=aggregate_age(stocks['female'])
        next_stocks={};monthly_survival={};e0_used={}
        for s in SEXES:
            spec=data['mortality'][s]
            if 'qx' in spec:
                if opt['e0_delta_end']!=0:
                    raise ValueError('Сдвиг ОПЖ недоступен для заданных напрямую qx. Измените таблицу qx явно.')
                qx=spec['qx'];e0_used[s]=None
            else:
                e0=annual_value(spec['annual_e0'],year)+opt['e0_delta_end']*progress
                ck=(s,round(e0,9))
                if ck not in cache:cache[ck]=mortality_from_e0(e0,s)
                qx=cache[ck]['qx'];e0_used[s]=e0
            pm=[(1-v)**(1/12) for v in qx];monthly_survival[s]=pm
            survivors=[v*pm[min(i//12,100)] for i,v in enumerate(stocks[s])]
            next_stocks[s]=[0.]+survivors[:1199]+[survivors[1199]+survivors[1200]]
        end_f=aggregate_age(next_stocks['female'])
        exposure=[(a+b)/2 for a,b in zip(start_f,end_f)]
        births=sum(exposure[a]*fw[a]*tfr/12 for a in range(N_AGE))
        deaths={s:before[s]-sum(next_stocks[s]) for s in SEXES};net={}
        for s,sex_share in [('male',share_m),('female',1-share_m)]:
            born=births*sex_share;surviving=born*math.sqrt(monthly_survival[s][0])
            next_stocks[s][0]+=surviving;deaths[s]+=born-surviving
            net[s]=annual_value(data['migration'][s]['annual_net'],year)/12*(opt['migration_scale'] if n>=scenario_n else 1.)
            for a in range(100):
                added=net[s]*mw[s][a]/12
                for j in range(a*12,a*12+12):
                    next_stocks[s][j]+=added
                    if next_stocks[s][j]<-1e-8:
                        raise ValueError(f'{key}, {s}, возраст {a}: заданный отток превышает численность. Отрицательные ячейки не обрезаются.')
            next_stocks[s][1200]+=net[s]*mw[s][100]
            if next_stocks[s][1200]<-1e-8:raise ValueError('Отток превышает численность открытой группы 100+.')
        stocks=next_stocks
        age={s:aggregate_age(stocks[s]) for s in SEXES};total=sum(sum(x) for x in age.values())
        natural=births-sum(deaths.values());migration=sum(net.values())
        residual=total-sum(before.values())-natural-migration
        if not all(math.isfinite(v) for v in [total,births,natural,migration,residual,*deaths.values()]):
            raise ValueError('Переполнение вычислений: проверьте масштабы входных данных и коэффициентов.')
        max_balance=max(max_balance,abs(residual))
        if abs(residual)>max(1e-6,total*1e-10):raise ValueError('Нарушен демографический баланс.')
        nxt_y,nxt_m=divmod(n+1,12)
        monthly.append({'month':key,'stock_date':f'{nxt_y:04d}-{nxt_m+1:02d}-01',
            'population':total,'male':sum(age['male']),'female':sum(age['female']),
            'births':births,'deaths':sum(deaths.values()),'natural_change':natural,'net_migration':migration,
            'tfr':tfr,'e0_male':e0_used['male'],'e0_female':e0_used['female'],
            'children_0_14':sum(age['male'][:15])+sum(age['female'][:15]),
            'age_65_plus':sum(age['male'][65:])+sum(age['female'][65:]),
            'women_15_49':sum(age['female'][15:50]),'balance_residual':residual,
            'age':age})
    return {'schema':'semya.cohort-result/1','model_version':VERSION,'region_id':data.get('region_id'),
        'region_name':data.get('region_name'),'base_date':data['base_date'],'scenario_start':data.get('scenario_start',data['base_date']),'end_date':END,
        'baseline':data['population'],'options':opt,'months':monthly,'max_balance_residual':max_balance,
        'provenance':data.get('provenance',[]),'assumptions':data.get('assumptions',[]),
        'interpretation':'Условная сценарная передвижка, не официальный и не причинный прогноз. Месяц — вычислительный шаг, а не частота наблюдения всех компонент.'}
