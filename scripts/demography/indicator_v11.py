"""Explicit monthly log-scale diagnostic ensemble (new implementation, not the 2026 report model).
No annual/cumulative rows, interpolation of gaps, seasonal inference from one year,
policy coefficients, cross-region averaging or hidden fallback observations.
"""
from __future__ import annotations
import calendar, hashlib, json, math, statistics
from datetime import date
VERSION = 'monthly-log-ensemble/1.1.1'
MODELS = ('last', 'local_damped', 'holt_damped')
NAMES = {'last':'Последнее значение', 'local_damped':'Локальный затухающий тренд', 'holt_damped':'Затухающий тренд Холта'}
PARAMETERS = {'local_window':12,'phi':0.96,'alpha':0.5,'beta':0.1,'minimum_training':6,'validation_horizons':[1,3]}

def month_id(value):
    d=date.fromisoformat(str(value)[:10]); return d.year*12+d.month-1

def end_month(n):
    y,m=divmod(n,12); m+=1; return f'{y:04d}-{m:02d}-{calendar.monthrange(y,m)[1]:02d}'

def mean(a): return sum(a)/len(a)

def path(y,horizon,method):
    phi=PARAMETERS['phi']; n=len(y)
    if method=='last': return [y[-1]]*horizon
    if method=='local_damped':
        a=y[-min(PARAMETERS['local_window'],n):]; center=(len(a)-1)/2
        slope=sum((i-center)*(v-mean(a)) for i,v in enumerate(a))/sum((i-center)**2 for i in range(len(a))) if len(a)>1 else 0
        level=y[-1]
    elif method=='holt_damped':
        level=y[0]; slope=(y[min(2,n-1)]-y[0])/min(2,n-1) if n>1 else 0
        alpha,beta=PARAMETERS['alpha'],PARAMETERS['beta']
        for v in y[1:]:
            previous=level; level=alpha*v+(1-alpha)*(level+phi*slope)
            slope=beta*(level-previous)+(1-beta)*phi*slope
    else: raise ValueError('Unknown model')
    return [level+slope*phi*(1-phi**k)/(1-phi) for k in range(1,horizon+1)]

def forecast(observations, end='2030-12-31'):
    obs=sorted(observations,key=lambda x:x['date'])
    if len(obs)<6: raise ValueError('Для прогнозирования нужны хотя бы 6 последовательных месячных наблюдений.')
    ids=[month_id(o['date']) for o in obs]
    if len(set(ids))!=len(ids): raise ValueError('Дубли месячных наблюдений.')
    # A new gap cannot silently be interpolated or compressed into one step.
    if any(b-a!=1 for a,b in zip(ids,ids[1:])): raise ValueError('Разрыв месячной сетки: заполнение или сжатие времени запрещено.')
    if any(not isinstance(o['value'],(int,float)) or isinstance(o['value'],bool) or not math.isfinite(o['value']) or o['value']<=0 for o in obs):
        raise ValueError('Нужны положительные конечные значения СКР без пропусков.')
    H=max(0,month_id(end)-ids[-1]);y=[math.log(o['value']) for o in obs]
    backtests=[];errors={m:[] for m in MODELS}
    for origin in range(6,len(y)):
        for horizon in PARAMETERS['validation_horizons']:
            target=origin+horizon-1
            if target>=len(y):continue
            for m in MODELS:
                pred=path(y[:origin],horizon,m)[-1];err=pred-y[target]
                errors[m].append(err)
                backtests.append({'model':m,'train_end':obs[origin-1]['date'],'target':obs[target]['date'],'horizon':horizon,'observed':obs[target]['value'],'predicted':math.exp(pred),'log_error':err})
    mse={m:mean([e*e for e in errors[m]]) if errors[m] else None for m in MODELS}
    # A small floor prevents a single accidentally perfect short validation from monopolising weights.
    floor=max(1e-8,mean([v for v in mse.values() if v is not None])*0.05) if backtests else 1e-8
    raw={m:1/(mse[m]+floor) if mse[m] is not None else 1 for m in MODELS};total=sum(raw.values());weights={m:raw[m]/total for m in MODELS}
    paths={m:path(y,H,m) for m in MODELS}
    # Conditional, deliberately labelled uncalibrated bands. No causal/policy probability is inferred.
    one_step=[b['log_error'] for b in backtests if b['horizon']==1]
    sigma=math.sqrt(mean([e*e for e in one_step])) if one_step else statistics.pstdev([b-a for a,b in zip(y,y[1:])])
    result=[]
    for i in range(H):
        mu=sum(weights[m]*paths[m][i] for m in MODELS)
        spread=sum(weights[m]*(paths[m][i]-mu)**2 for m in MODELS)
        se=math.sqrt((i+1)*sigma*sigma+spread)
        if max(abs(mu),abs(mu+1.96*se),abs(mu-1.96*se))>25: raise ValueError('Модель вышла за численно устойчивый диапазон; результат не публикуется.')
        row={'date':end_month(ids[-1]+i+1),'value':math.exp(mu),'lo80':math.exp(mu-1.2815515655*se),'hi80':math.exp(mu+1.2815515655*se),'lo95':math.exp(mu-1.9599639845*se),'hi95':math.exp(mu+1.9599639845*se),'model_min':min(math.exp(paths[m][i]) for m in MODELS),'model_max':max(math.exp(paths[m][i]) for m in MODELS)}
        row['members']={m:math.exp(paths[m][i]) for m in MODELS};result.append(row)
    fingerprint=hashlib.sha256(json.dumps({'obs':obs,'end':end,'version':VERSION,'parameters':PARAMETERS},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    models=[]
    for m in MODELS:
        b=[b for b in backtests if b['model']==m]
        models.append({'id':m,'name':NAMES[m],'weight':weights[m],'n_tests':len(b),'log_rmse':math.sqrt(mse[m]) if mse[m] is not None else None,'mae':mean([abs(bi['predicted']-bi['observed']) for bi in b]) if b else None})
    return {'schema':'semya.indicator-projection/1','model_version':VERSION,'input_sha256':fingerprint,'source_as_of':obs[-1]['date'],'end_date':end,'n_observations':len(obs),'observations':obs,'forecast':result,'models':models,'backtest':backtests,'parameters':PARAMETERS,'intervals':{'type':'conditional_log_normal','innovation_log_rmse':sigma,'calibrated':False},'caveats':['Новая модель платформы; не заменяет сохранённый прогноз исходной экспертизы.','Помесячно опубликованный СКР является годовым по размерности коэффициентом, а не числом детей за отдельный месяц.','Годовые и накопительные строки не включены в месячное обучение.','Короткая история и зависимость соседних оценок ограничивают надёжность экстраполяции. Сезонность не оценивается.','Условные 80/95%-полосы построены из ошибок краткосрочной проверки с увеличением дисперсии по горизонту. Фактическое покрытие не валидировано; структурные шоки не учтены.','Национальная серия рассчитана независимо. Региональные коэффициенты не усредняются в показатель России.']}
