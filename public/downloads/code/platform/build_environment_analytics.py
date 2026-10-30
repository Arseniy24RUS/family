#!/usr/bin/env python3
"""Rebuild Environmental Wellbeing statistics from independently identified cells.

python scripts/build_environment_analytics.py

Annual facts, source months, YTD ratios and programme totals retain distinct
period contracts. All derived arrays carry observation IDs. No imputation,
forecast, clustering or causal effect is introduced.
"""
from __future__ import annotations
import argparse
import collections
import json
from decimal import Decimal
from pathlib import Path
from download_manifest import download_records
from environment_data import ROOT,PROJECT,DATA,DOWNLOADS,load,atomic,sha256,csv_write,quantile

def latest(rows,usable=True):
    a=[r for r in rows if r.get('analytical_value' if usable else 'value') is not None]
    return max(a,key=lambda r:(r['period_end'],r['frequency']=='annual')) if a else None
def default_category(sid):
    return {}
def compact(row):
    if row is None:return None
    keep={'id','source_id','name','code','map_id','fd','geo_level','period','period_start','period_end','year','frequency','value','analytical_value','excluded','status','category','unit','geographic_comparison_eligible','geographic_exclusion_reason','quality_flags','source_period_label','period_basis','annual_comparison_eligible','period_semantics','national_scope','temporal_comparison_eligible','source_status','source_frequency','source_period_start','source_period_end'}
    return {k:v for k,v in row.items() if k in keep}
def slice_key(row):return row['period_end'],row['frequency'],json.dumps(row['category'],ensure_ascii=False,sort_keys=True)
def canonical_regions(rows,strict=False):
    """Prefer explicit excluding-AO rows when a source publishes both scopes."""
    groups=collections.defaultdict(list)
    for row in rows:
        if row['geo_level']=='regional':groups[row['code']].append(row)
    out=[]
    for code,group in sorted(groups.items()):
        if any(r.get('geographic_exclusion_reason')=='conflicting_explicit_territorial_scopes' for r in group):continue
        eligible=[r for r in group if r['geographic_comparison_eligible']]
        choice=eligible or ([] if strict else group)
        if len(choice)>1:
            signatures={(r['value'],r['period_end'],r['frequency'],json.dumps(r['category'],sort_keys=True)) for r in choice}
            if len(signatures)>1:raise ValueError('Conflicting territorial scopes: '+code)
        if choice:out.append(choice[0])
    return out
def summary(rows):
    values=[r['analytical_value'] for r in rows if r['analytical_value'] is not None]
    return {'n':len(values),'minimum':min(values) if values else None,'p10':quantile(values,.1),'q1':quantile(values,.25),'median':quantile(values,.5),'q3':quantile(values,.75),'p90':quantile(values,.9),'maximum':max(values) if values else None,'mean':sum(values)/len(values) if values else None,'weighting':'unweighted_territories','quartile_method':'Hyndman_Fan_type_7'}
def make_source(config,packet,status,root):
    sid=config['indicator_id'];rows=packet['observations'];national=[r for r in rows if r['geo_level']=='national'];regional=[r for r in rows if r['geo_level']=='regional'];category=default_category(sid)
    slices=collections.defaultdict(list)
    for r in regional:slices[slice_key(r)].append(r)
    candidates=[k for k,p in slices.items() if p[0]['category']==category and any(r['analytical_value'] is not None for r in p)]
    key=max(candidates,key=lambda k:(k[0],k[1]=='annual')) if candidates else None
    regional_latest=canonical_regions(slices.get(key,[]))
    source={k:v for k,v in config.items() if k not in {'field_overrides','dimension_defaults','titles','known_territories','first_year','min_regional_count','expected_period_types','export_format'}}
    flags=collections.Counter((f['code'],f['message'],f['severity'],f['exclude_from_analysis']) for r in rows for f in r['quality_flags'])
    current=[r for r in national if r['category']==category]
    source.update(id=sid,available=any(r['value'] is not None for r in rows),published_at=packet['published_at'],published_at_semantics=packet.get('published_at_semantics'),last_success=status.get('last_success') or packet['published_at'],last_checked_at=status.get('checked_at'),refresh_state=status.get('state'),snapshot_id=packet.get('snapshot_id'),origin_kind=packet['origin_kind'],direct_emiss_verified=packet.get('direct_emiss_verified',True),
      observation_count=len(rows),numeric_count=sum(r['value'] is not None for r in rows),missing_count=sum(r['value'] is None for r in rows),usable_count=sum(r['analytical_value'] is not None for r in rows),excluded_numeric_count=sum(r['value'] is not None and r['excluded'] for r in rows),
      national=[compact(r) for r in national],annual=[compact(r) for r in national if r['frequency']=='annual'],annual_equivalents=[],
      latest_national=compact(latest(current) or latest(current,False)),latest_published=compact(latest(current,False)),latest_analytically_usable=compact(latest(current)),
      default_category=category,categories=[json.loads(x) for x in sorted({json.dumps(r['category'],ensure_ascii=False,sort_keys=True) for r in rows})],
      regional_latest=[compact(r) for r in regional_latest],regional_history=[],regional_history_deferred=True,other_territories=[],other_territory_count=sum(r['geo_level']=='other' for r in rows),
      regional_periods=sorted({r['period_end'] for r in regional}),regional_period_end=key[0] if key else None,regional_frequency=key[1] if key else None,regional_category=category,
      regional_slices=[{'period':p[0]['period'],'period_end':k[0],'frequency':k[1],'category':p[0]['category'],'count':len(p),'numeric_count':sum(r['value'] is not None for r in p),'usable_count':sum(r['analytical_value'] is not None for r in p),'canonical_region_count':len(canonical_regions(p))} for k,p in sorted(slices.items())],
      project_territory_count=len({r['name'] for r in rows if r['geo_level']=='project_territory'}), project_territory_observations=sum(r['geo_level']=='project_territory' for r in rows), geography_scope='national_regional_project_territories' if any(r['geo_level']=='project_territory' for r in rows) else 'regional_and_national' if regional else 'national_only',geography_note='Исходные территории сохранены. Муниципальные территории проекта, субъекты, федеральные округа и РФ учитываются раздельно. Числовые значения муниципальной территории не переносятся на субъект.',
      quality_flags=[{'code':c,'message':m,'severity':s,'exclude_from_analysis':e,'cells':n} for (c,m,s,e),n in sorted(flags.items())],
      downloads={'observations':f'data/projects/{PROJECT}/series/{sid}.json','provenance':f'data/projects/{PROJECT}/provenance/{sid}.json','source_input':f'downloads/projects/{PROJECT}/statistics/emiss_inputs/{sid}.zip','csv':f'downloads/projects/{PROJECT}/statistics/series/{sid}.csv.gz'})
    raw=status.get('raw_file')
    if raw:
        expected=f'downloads/projects/{PROJECT}/statistics/emiss_current/{sid}.zip';provenance=load(root/DATA/'provenance'/f'{sid}.json')
        if raw!=expected or provenance.get('current_raw')!=raw or sha256(root/'public'/raw)!=provenance.get('current_raw_sha256'):raise ValueError('Current response provenance mismatch')
        source['downloads']['current_raw']=raw
    return source
def difference_unit(source):return 'п.п.' if source['unit']=='процент' else source['display_unit']
def dec(value):return Decimal(str(value))
def delta(a,b):return float(dec(b)-dec(a))
def ratio(a,b):return float((dec(b)/dec(a)-1)*100) if a else None
def source_rows(packets,sid,year=None,frequency=None,period=None,geo=None,category=None):
    return [r for r in packets[sid]['observations'] if (year is None or r['year']==year) and (frequency is None or r['frequency']==frequency) and (period is None or r['period']==period) and (geo is None or r['geo_level']==geo) and (category is None or r['category']==category)]
def national_point(packets,sid,year,frequency='annual',period=None,category=None):
    rows=source_rows(packets,sid,year,frequency,period,'national',default_category(sid) if category is None else category)
    rows=[r for r in rows if r['analytical_value'] is not None]
    if len(rows)>1:raise ValueError('Ambiguous national point: '+sid)
    return rows[0] if rows else None


def author_correlations(packets,sources):
    from scipy.stats import spearmanr
    ids=['62792','62793']; by_id={s['id']:s for s in sources}; lookups={}
    features=[]
    for sid in ids:
        rows=canonical_regions(source_rows(packets,sid,2025,'annual',geo='regional',category={}))
        lookups[sid]={r['code']:r for r in rows if r['analytical_value'] is not None}
        features.append({'source_id':sid,'title':by_id[sid]['short_title'],'unit':'%','period':'2025','frequency':'annual'})
    codes=sorted(set.intersection(*(set(lookups[s]) for s in ids)))
    def calculate(selected):
        rho=float(spearmanr([lookups[ids[0]][c]['value'] for c in selected],[lookups[ids[1]][c]['value'] for c in selected]).statistic)
        return [[1.0,rho],[rho,1.0]],[{'source_a':ids[0],'source_b':ids[1],'title_a':by_id[ids[0]]['short_title'],'title_b':by_id[ids[1]]['short_title'],'rho':rho,'n':len(selected)}]
    matrix,pairs=calculate(codes)
    suspect=[c for c in codes if c=='79' and all(lookups[s][c]['value']==0 for s in ids)]
    selected=[c for c in codes if c not in suspect]; other_matrix,other_pairs=calculate(selected)
    sensitivity={'n':len(selected),'matrix':other_matrix,'pairs':other_pairs,'codes':selected,'excluded_codes':suspect,
                 'reason':'Отдельная проверка чувствительности без исходной пары 0/0 Еврейской автономной области. Основная совокупность сохраняет эту пару.'}
    regions=[{'code':c,'map_id':c,'name':lookups[ids[0]][c]['name'],'values':{s:lookups[s][c]['value'] for s in ids},'observation_ids':{s:lookups[s][c]['id'] for s in ids},'strict_scope_eligible':c in selected} for c in codes]
    return {'computed':True,'n':len(codes),'features':features,'source_ids':ids,'matrix':matrix,'pairs':pairs,'regions':regions,
            'strict':sensitivity,'sensitivity':sensitivity,'period':'2025','frequency':'annual','imputed_cells':0,
            'weighting':'unweighted_territories','role':'author_comparable_descriptive_snapshot',
            'scope_note':'85 опубликованных субъектов в основной совокупности; проверка без пары 0/0 Еврейской автономной области охватывает 84 субъекта. Исключение не относится к географическому объединению автономных округов.',
            'interpretation':'Ранговая связь двух долей ТКО. Обработка и захоронение могут относиться к одним отходам; связь не устанавливает эффект инфраструктуры или проекта.','clustering_performed':False}

def waste_profiles(packets,correlations):
    rows=correlations['regions']; treatment=[r['values']['62792'] for r in rows]; landfill=[r['values']['62793'] for r in rows]
    t=national_point(packets,'62792',2025); l=national_point(packets,'62793',2025)
    return {'period':'2025','frequency':'annual','n':len(rows),'rows':rows,
            'national':{'treatment':t['value'],'landfill':l['value'],'sum_percent':float(dec(t['value'])+dec(l['value'])),'reference_ids':[t['id'],l['id']]},
            'treatment_summary':summary([{'analytical_value':v} for v in treatment]),'landfill_summary':summary([{'analytical_value':v} for v in landfill]),
            'treatment_below_25':sum(v<25 for v in treatment),'treatment_zero':sum(v==0 for v in treatment),'treatment_at_100':sum(v==100 for v in treatment),
            'landfill_at_least_90':sum(v>=90 for v in landfill),'landfill_at_100':sum(v==100 for v in landfill),
            'both_at_least_80':sum(r['values']['62792']>=80 and r['values']['62793']>=80 for r in rows),
            'high_both_rows':[r for r in rows if r['values']['62792']>=80 and r['values']['62793']>=80],
            'interpretation':'Две доли не являются дополнениями до 100%. Для баланса потоков нужны образованная масса, передача на обработку, полезные фракции, остатки и межтерриториальное движение.'}

def air_groups(packets,sources):
    by_id={s['id']:s for s in sources}; out=[]
    for sid,baseline,n in [('62862',2017,12),('62863',2020,29)]:
        source=by_id[sid]; rows=packets[sid]['observations']
        def block(year,frequency,period=None):
            city=source_rows(packets,sid,year,frequency,period,'project_territory',{})
            valid=[r for r in city if r['analytical_value'] is not None]
            national=national_point(packets,sid,year,frequency,period)
            mean=float(sum((dec(r['value']) for r in valid),Decimal(0))/len(valid)) if valid else None
            return {'year':year,'frequency':frequency,'period':period or str(year),'n':len(valid),'expected_n':n,'complete':len(valid)==n,
                    'rows':[compact(r) for r in sorted(city,key=lambda x:x['name'])],
                    'national_value':national['value'] if national else None,'unweighted_mean':mean,
                    'difference_from_published':float(dec(mean)-dec(national['value'])) if mean is not None and national else None,
                    'mean_reduction_percent':float(100-dec(mean)) if mean is not None else None,
                    'reference_ids':[r['id'] for r in valid]+([national['id']] if national else []),
                    'minimum':min((r['value'] for r in valid),default=None),'maximum':max((r['value'] for r in valid),default=None)}
        last=latest([r for r in rows if r['geo_level']=='national'])
        out.append({'source_id':sid,'title':source['short_title'],'unit':'%','baseline_year':baseline,'expected_territories':n,
                    'geography_level':'project_territory','annual':block(2025,'annual'),
                    'latest':block(last['year'],last['frequency'],last['period']) if last else None,
                    'weighting':'unweighted_project_territories','interpretation':'Индексы имеют собственный базовый год. Невзвешенное среднее не заменяет отношение суммарной массы выбросов или населённостно-взвешенную экспозицию.'})
    return out

def forest_summary(packets):
    rows=canonical_regions(source_rows(packets,'62781',2025,'annual',geo='regional',category={}))
    numeric=[r for r in rows if r['analytical_value'] is not None]
    national=national_point(packets,'62781',2025)
    area=national_point(packets,'62782',2025)
    newest=latest(source_rows(packets,'62782',geo='national',category={}))
    return {'source_id':'62781','period':'2025','frequency':'annual',**summary(numeric),'national_value':national['value'],
            'above_100':sum(r['value']>100 for r in numeric),'rows':[compact(r) for r in numeric],
            'reference_id':national['id'],'denominator_year':2023,'numerator_year':2025,'bounded_share':False,
            'program_increment':{'source_id':'62782','cumulative_since':'2025-01-01','from_period':area['period'],'to_period':newest['period'],
               'from_frequency':area['frequency'],'to_frequency':newest['frequency'],'from_value':area['value'],'to_value':newest['value'],
               'difference':delta(area['value'],newest['value']),'unit':'тыс. га','reference_ids':[area['id'],newest['id']],
               'interpretation':'Прибавка опубликованного накопленного уровня к уточнённому годовому результату 2025. Весь накопленный объём не приписывается 2026 году.'},
            'interpretation':'Отношение сумм площадей по РФ отличается от среднего региональных отношений. Высокое значение при малом знаменателе не подтверждает экологическую эквивалентность восстановленного леса.'}

def canonical_unit(value):
    s=str(value or '').strip().casefold().replace('ё','е')
    return {'%':'процент','процентов':'процент','проценты':'процент','миллион человек':'миллион человек','млн человек':'миллион человек','млн чел.':'миллион человек','тыс. человек':'тысяча человек','тыс. чел.':'тысяча человек','единица':'штука','единицы':'штука','единиц':'штука','шт.':'штука','ед.':'штука','тыс. га':'тысяча гектаров','млн куб. м':'миллион кубических метров','млн м3':'миллион кубических метров','млн м³':'миллион кубических метров'}.get(s,s)

def target_comparisons(sources,targets,packets):
    by_id={s['id']:s for s in sources};out=[];blocked=[]
    for target in targets:
        sid=str(target.get('source_id') or target.get('emiss_id') or '');s=by_id.get(sid)
        if not s:continue
        if not s['target_comparison_allowed'] or target.get('mapping_status') in {'conditional','unmapped','unresolved'} or target.get('discontinued'):
            blocked.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'reason':'discontinued_indicator' if s['source_status']=='discontinued' else 'source_or_mapping_contract_disallows_comparison'});continue
        if canonical_unit(s['unit'])!=canonical_unit(target.get('unit')):
            blocked.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'reason':'unit_unresolved','source_unit':s['unit'],'target_unit':target.get('unit')});continue
        for year,goal in target.get('years',{}).items():
            if goal is None:continue
            annual=national_point(packets,sid,int(year))
            if not annual or not annual['annual_comparison_eligible']:continue
            difference=delta(goal,annual['value']);favourable=difference if s['direction']=='higher' else -difference
            out.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'title':s['short_title'],'target_year':int(year),'target_value':goal,
                'fact_value':annual['value'],'fact_period':str(year),'fact_frequency':'annual','difference':difference,
                'difference_unit':difference_unit(s),'unit':s['unit'],'display_unit':s['display_unit'],
                'ratio_percent':float(dec(annual['value'])/dec(goal)*100) if goal else None,
                'direction':s['direction'],'favourable_difference':favourable,'on_favourable_side':favourable>=0,
                'comparison_kind':'annual_fact_vs_annual_plan','annual_comparison_eligible':True,'formal_attainment_eligible':False,
                'annual_basis':annual['period_basis'],'reference_observation_id':annual['id'],'reference_observation_ids':[annual['id']],
                'target_source':target,'interpretation':'Арифметическое сопоставление самостоятельного годового факта с датированной редакцией цели. Декабрьский мониторинг не подменяет год; причинный эффект и формальное исполнение не установлены.'})
    return out,blocked

def national_changes(sources):
    changes=[];annual_december=[]
    for s in sources:
        points=[r for r in s['national'] if r['analytical_value'] is not None]
        lookup={(r['frequency'],r['period'],json.dumps(r['category'],sort_keys=True)):r for r in points}
        for r in points:
            if r['frequency']=='annual':
                for freq in ['monthly','cumulative_ytd']:
                    december=lookup.get((freq,str(r['year'])+'-12',json.dumps(r['category'],sort_keys=True)))
                    if december:annual_december.append({'source_id':s['id'],'title':s['short_title'],'year':r['year'],'annual_value':r['value'],'december_value':december['value'],'difference':delta(december['value'],r['value']),'unit':s['display_unit'],'december_frequency':freq,'reference_observation_ids':[december['id'],r['id']],'interpretation':'Самостоятельная годовая запись и декабрьский оперативный срез. Разность может отражать уточнение отчётности; причины не идентифицированы.'})
            if not s['temporal_comparison_allowed']:continue
            prior=lookup.get((r['frequency'],str(r['year']-1)+r['period'][4:],json.dumps(r['category'],sort_keys=True)))
            if not prior:continue
            kind='same_calendar_slice' if s['annual_reset'] else 'same_calendar_program_snapshot' if s['cumulative'] else 'same_calendar_monitoring_snapshot'
            changes.append({'source_id':s['id'],'title':s['short_title'],'from_period':prior['period'],'to_period':r['period'],'prior_period':prior['period'],'period':r['period'],
                'frequency':r['frequency'],'category':r['category'],'from_value':prior['value'],'to_value':r['value'],'difference':delta(prior['value'],r['value']),'change':delta(prior['value'],r['value']),
                'relative_change_percent':ratio(prior['value'],r['value']),'difference_unit':difference_unit(s),'unit':s['display_unit'],
                'comparison_kind':kind,'reference_observation_ids':[prior['id'],r['id']],
                'interpretation':'Сопоставление одинаковой частоты, календарного горизонта и категории. Для программного накопления разность уровней не является отдельным годовым потоком. Причины изменения не установлены.'})
    return changes,annual_december

def forecast_eligibility(source):
    count=len({r['year'] for r in source['annual'] if r['analytical_value'] is not None})
    return {'source_id':source['id'],'title':source['short_title'],'annual_observations':count,'distinct_annual_years':count,'eligible':False,
            'status':'discontinued_indicator' if source['source_status']=='discontinued' else 'methodology_alignment_required' if not source['temporal_comparison_allowed'] else 'insufficient_independent_annual_history',
            'reason':'Вероятностная прогнозная модель не проверялась. Короткие ряды и накопленные месяцы не дают независимой годовой истории; условная траектория не является прогнозом.'}

def build(root=ROOT):
    root=Path(root);config=load(root/'scripts/environment_emiss_sources.json');registry_packet=load(root/DATA/'indicators.json');refresh=load(root/DATA/'refresh-status.json')
    status={s['source_id']:s for s in refresh['sources']}
    packets={c['indicator_id']:load(root/DATA/'series'/f"{c['indicator_id']}.json") for c in config['sources']}
    sources=[make_source(c,packets[c['indicator_id']],status.get(c['indicator_id'],{}),root) for c in config['sources']]
    by_id={s['id']:s for s in sources};rows=[r for p in packets.values() for r in p['observations']]
    published_at=max(s['published_at'] for s in sources if s['published_at']);region_total=len(load(root/'public/data/catalog.json')['regions'])
    registry=[]
    for old in registry_packet['items']:
        linked=[by_id[s] for s in old['source_ids']];evidence=[r for s in old['source_ids'] for r in packets[s]['observations']]
        numeric=[r for r in evidence if r['value'] is not None];regions={r['code'] for r in numeric if r['geo_level']=='regional'}
        registry.append({**old,'source_release_counts':old.get('source_release_counts') or {k:old.get(k) for k in ['n_cells','n_numeric','n_usable','n_domain_violations']},
          'n_linked_sources':len(linked),'n_loaded_sources':sum(s['available'] for s in linked),'n_cells':len(evidence),'n_numeric':len(numeric),
          'n_usable':sum(r['analytical_value'] is not None for r in evidence),'n_regions':len(regions),'region_coverage_pct':100*len(regions)/region_total,
          'n_national':sum(r['geo_level']=='national' for r in numeric),'n_domain_violations':sum(r['excluded'] for r in numeric),
          'first_end':min((r['period_end'] for r in numeric),default=''),'last_end':max((r['period_end'] for r in evidence if r['analytical_value'] is not None),default=''),
          'status':'discontinued' if all(s['source_status']=='discontinued' for s in linked) else 'numeric_data' if numeric else 'linked_no_numeric',
          'latest_national':[{**s['latest_national'],'source_title':s['title'],'source_url':s['source_url'],'territory_name':s['latest_national']['name'],'snapshot_id':s['snapshot_id'],'acquired_at':s['published_at'],'origin_kind':'live_emiss','analysis_status':'excluded' if s['latest_national']['excluded'] else 'usable'} for s in linked if s['latest_national']]})
    coverage={'indicators_total':len(registry),'registry_indicators':len(registry),'confirmed_sources':len(sources),'known_sources':len(sources),
        'numeric_sources':sum(s['available'] for s in sources),'available_sources':sum(s['available'] for s in sources),'indicators_with_numeric':sum(r['n_numeric']>0 for r in registry),
        'observations':len(rows),'numeric_observations':sum(r['value'] is not None for r in rows),'missing_observations':sum(r['value'] is None for r in rows),
        'usable_observations':sum(r['analytical_value'] is not None for r in rows),'excluded_numeric_observations':sum(r['value'] is not None and r['excluded'] for r in rows),
        'independent_annual_national_facts':sum(r['analytical_value'] is not None and r['geo_level']=='national' and r['frequency']=='annual' for r in rows),
        'annual_equivalent_references':0,'regional_sources':sum(bool(s['regional_latest']) for s in sources),
        'regions':len({r['code'] for r in rows if r['geo_level']=='regional'}),'other_territory_observations':sum(r['geo_level']=='other' for r in rows),
        'project_territory_observations':sum(r['geo_level']=='project_territory' for r in rows),'project_territories':len({r['name'] for r in rows if r['geo_level']=='project_territory'}),
        'metadata_only_sources':sum(not s['available'] for s in sources),'unmapped_indicators':len(config.get('unmapped_indicators',[])),
        'discontinued_sources':sum(s['source_status']=='discontinued' for s in sources)}
    target_path=root/DATA/'targets.json';target_packet=load(target_path) if target_path.exists() else []
    targets=target_packet if isinstance(target_packet,list) else target_packet.get('items',[])
    comparisons,blocked=target_comparisons(sources,targets,packets);changes,annual_december=national_changes(sources)
    correlations=author_correlations(packets,sources);waste=waste_profiles(packets,correlations);air=air_groups(packets,sources);forest=forest_summary(packets)
    distributions=[];availability=[];quality=[]
    for s in sources:
        exact=s['regional_latest'];matching=next((r for r in s['national'] if r['period_end']==s['regional_period_end'] and r['frequency']==s['regional_frequency'] and r['category']==s['regional_category'] and r['analytical_value'] is not None),None)
        if exact:distributions.append({'source_id':s['id'],'title':s['short_title'],'period_end':s['regional_period_end'],'frequency':s['regional_frequency'],'category':s['regional_category'],'unit':s['display_unit'],**summary([r for r in exact if r['geographic_comparison_eligible']]),'national_value':matching['analytical_value'] if matching else None,'national_value_origin':'published_national_not_regional_average','excluded_geography_count':sum(not r['geographic_comparison_eligible'] for r in exact)})
        groups=collections.defaultdict(list)
        for r in packets[s['id']]['observations']:groups[(r['period'],r['frequency'],json.dumps(r['category'],sort_keys=True))].append(r)
        for (period,freq,category),cells in sorted(groups.items()):availability.append({'source_id':s['id'],'period':period,'frequency':freq,'category':json.loads(category),'cells':len(cells),'numeric':sum(r['value'] is not None for r in cells),'missing':sum(r['value'] is None for r in cells),'usable':sum(r['analytical_value'] is not None for r in cells),'excluded_numeric':sum(r['value'] is not None and r['excluded'] for r in cells)})
        quality.extend({'source_id':s['id'],**f,'count':f['cells']} for f in s['quality_flags'])
    download_names=[('source_registry','Реестр источников'),('target_comparisons','Годовые сопоставления с целями'),('national_changes','Сопоставимая динамика'),('annual_december_comparisons','Годовые и декабрьские записи'),('regional_summaries','Региональные распределения'),('correlations','ТКО: корреляция 85 субъектов'),('correlations_strict','ТКО: чувствительность без ЕАО'),('regional_profiles','ТКО: региональные пары'),('air_territories','Воздух: 12 городов и 29 территорий'),('forest_regions','Отношение площадей лесовосстановления'),('quality_flags','Методологические оговорки'),('availability','Календарь доступности')]
    downloads=[{'label':label,'path':f'downloads/projects/{PROJECT}/statistics/{name}.csv'} for name,label in download_names]+[{'label':s['short_title']+' – полный ряд CSV.gz','path':s['downloads']['csv']} for s in sources]
    statistics={'schema_version':1,'project_id':PROJECT,'published_at':published_at,'statistical_as_of':published_at[:10],'last_checked_at':refresh.get('checked_at'),
        'coverage':coverage,'registry':registry,'sources':sources,'target_comparisons':comparisons,'unmapped_indicators':config.get('unmapped_indicators',[]),
        'geography_note':'Один источник, период, частота и категория задают один территориальный срез. Субъекты и муниципальные территории проекта не смешиваются.',
        'history_loading':'Per-source source.downloads.observations; full source packet has observations[].','downloads':downloads}
    analytics={'schema_version':1,'project_id':PROJECT,'published_at':published_at,'coverage':coverage,
        'regional_summaries':distributions,'regional_distributions':distributions,'regional_history_deferred':True,
        'correlations':correlations,'profiles':correlations['regions'],'regional_profiles':correlations['regions'],
        'waste_profiles':waste,'air_groups':air,'forest_2025':forest,'national_changes':changes,'changes':changes,
        'same_month_changes':[r for r in changes if r['frequency'] in {'monthly','cumulative_ytd'}],
        'annual_december_comparisons':annual_december,'availability':availability,'quality_flags':quality,'quality_flags_are_aggregated':True,
        'forecast_eligibility':[forecast_eligibility(s) for s in sources],'targets':targets,'target_comparisons':comparisons,'blocked_target_comparisons':blocked,
        'causal':{'identified':False,'reason':'Региональный срез, городские индексы и короткая динамика не идентифицируют эффект проекта. Требуются конкретное вмешательство, сопоставимая история и обоснованная контрольная траектория.'},
        'methodology':{'imputation':'none','year_end_policy':'independent_annual_source_rows_only','forecast':'not_validated','clustering':'not_performed','pca':'not_performed','source_date_semantics':'verified EMISS acquisition, distinct from platform build and network attempt'},
        'reproduction':'python scripts/build_environment_analytics.py'}
    atomic(root/DATA/'statistics.json',statistics,compact=True);atomic(root/DATA/'analytics.json',analytics,compact=True)
    atomic(root/DATA/'indicators.json',{**registry_packet,'as_of':published_at[:10],'origin_policy':'verified_emiss_source_packets; all_original_cells_preserved; explicit_period_and_geography_contracts','items':registry})
    atomic(root/DATA/'context.json',{'schema_version':1,'project_id':PROJECT,'kind':'project_regional_data','external_context':None,'note':'Исходные региональные доли ТКО и отдельные городские индексы воздуха. Общий рейтинг и причинный эффект не рассчитываются.','profiles':correlations['regions']},compact=True)
    d=root/DOWNLOADS
    csv_write(d/'source_registry.csv',[{k:s.get(k) for k in ['id','title','short_title','unit','display_unit','source_url','source_status','available','published_at','last_checked_at','observation_count','numeric_count','missing_count','usable_count','period_semantics','note']} for s in sources])
    csv_write(d/'target_comparisons.csv',comparisons,['source_id','indicator_code','title','target_year','target_value','fact_value','fact_period','fact_frequency','difference','difference_unit','ratio_percent','annual_basis','reference_observation_ids','target_source','interpretation'])
    air_flat=[{'source_id':group['source_id'],'baseline_year':group['baseline_year'],'slice':kind,**row} for group in air for kind in ['annual','latest'] if group[kind] for row in group[kind]['rows']]
    for name,values in [('national_changes',changes),('annual_december_comparisons',annual_december),('regional_summaries',distributions),('correlations',correlations['pairs']),('correlations_strict',correlations['strict']['pairs']),('regional_profiles',correlations['regions']),('air_territories',air_flat),('forest_regions',forest['rows']),('quality_flags',quality),('availability',availability)]:csv_write(d/(name+'.csv'),values)
    fields=['id','source_id','name','code','geo_level','national_scope','period','frequency','source_frequency','period_start','period_end','source_period_start','source_period_end','source_period_label','period_basis','category','unit','value','analytical_value','raw_value','excluded','status','source_status','geographic_comparison_eligible','quality_codes']
    for sid,p in packets.items():
        flat=[{k:r.get(k) for k in fields if k!='quality_codes'}|{'quality_codes':'|'.join(f['code'] for f in r['quality_flags'])} for r in p['observations']]
        csv_write(d/'series'/(sid+'.csv.gz'),flat,fields)
    atomic(root/DATA/'data-downloads.json',{'schema_version':1,'files':download_records(d, root/'public')})
    print(json.dumps(coverage));return statistics,analytics

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args();build(args.root)
