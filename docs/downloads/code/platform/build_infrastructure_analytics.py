#!/usr/bin/env python3
"""Rebuild Infrastructure for Life statistics from self-contained source packets.

All charts derive from explicitly identified source cells. No statistical
history, geographic gap, causal effect or clustering is invented.
"""
from __future__ import annotations
import argparse
import collections
import json
from decimal import Decimal
from pathlib import Path
from download_manifest import download_records
from infrastructure_data import ROOT,PROJECT,DATA,DOWNLOADS,load,atomic,sha256,csv_write,quantile

def latest(rows,usable=True):
    a=[r for r in rows if r.get('analytical_value' if usable else 'value') is not None]
    return max(a,key=lambda r:(r['period_end'],r['frequency']=='annual')) if a else None
def default_category(sid):
    return {'Тип поселения':'Всего'} if str(sid)=='40466' else {'Вид валюты':'В рублях'} if str(sid)=='61608' else {}
def compact(row):
    if row is None:return None
    keep={'id','source_id','name','code','map_id','fd','geo_level','period','period_start','period_end','year','frequency','value','analytical_value','excluded','status','category','unit','geographic_comparison_eligible','geographic_exclusion_reason','quality_flags','source_period_label','period_basis','annual_comparison_eligible','period_semantics','national_scope','temporal_comparison_eligible'}
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
      geography_scope='regional_and_national' if regional else 'national_only',geography_note='Исходные территории сохранены. Областные строки 29 и 72 с неуточнённым охватом автономных округов помечены. Объединённые территориальные строки не разделяются между субъектами.',
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
    if sid in {'59262','59263','59993'} and year>=2023:
        rows=[r for r in rows if r.get('national_scope')=='rf_without_new_subjects_from_2023']
    if len(rows)>1:raise ValueError('Ambiguous national point: '+sid)
    return rows[0] if rows else None

def housing_analysis(packets,sources):
    by_id={s['id']:s for s in sources};composition=[];concentrations=[]
    frames=[(year,'annual',None) for year in range(2018,2026)]+[(year,'cumulative_ytd',f'{year}-09') for year in [2025,2026]]
    for year,freq,period in frames:
        values={sid:national_point(packets,sid,year,freq,period) for sid in ['59263','59262','59993']}
        if not all(values.values()):continue
        total,multi,individual=[values[s]['value'] for s in ['59263','59262','59993']]
        composition.append({'period':period or str(year),'year':year,'frequency':freq,'total':total,'multifamily':multi,'individual':individual,'unit':'млн м²','individual_share_percent':float(dec(individual)/dec(total)*100) if total else None,'rounding_residual':float(dec(total)-dec(multi)-dec(individual)),'observation_ids':{s:r['id'] for s,r in values.items()}})
    for year in range(2018,2026):
        total=national_point(packets,'59263',year)
        rows=canonical_regions(source_rows(packets,'59263',year,'annual',geo='regional',category={}),strict=True)
        rows=sorted((r for r in rows if r['analytical_value'] is not None),key=lambda r:r['value'],reverse=True)
        if total and rows:
            top5=sum(dec(r['value']) for r in rows[:5]);top10=sum(dec(r['value']) for r in rows[:10])
            concentrations.append({'year':year,'period':str(year),'n':len(rows),'national_value':total['value'],'national_observation_id':total['id'],'top5_value':float(top5),'top5_share_percent':float(top5/dec(total['value'])*100),'top10_value':float(top10),'top10_share_percent':float(top10/dec(total['value'])*100),'top5':[compact(r) for r in rows[:5]],'unit':'млн м²','interpretation':'Концентрация опубликованного ввода; без оценки потребности, цены и обеспеченности инфраструктурой.'})
    return composition,concentrations

def author_correlations(packets,sources):
    from scipy.stats import spearmanr
    specs=[('40466',2024,'annual',None),('62876',2025,'annual',None),('62794',2025,'annual',None),('62801',2025,'annual',None),('62887',2025,'monthly','2025-12'),('63457',2025,'annual',None)]
    by_id={s['id']:s for s in sources};lookups={};features=[]
    for sid,year,freq,period in specs:
        selected=canonical_regions(source_rows(packets,sid,year,freq,period,'regional',default_category(sid)))
        lookups[sid]={r['code']:r for r in selected if r['analytical_value'] is not None}
        features.append({'source_id':sid,'title':by_id[sid]['short_title'],'period':period or str(year),'frequency':freq,'unit':by_id[sid]['display_unit']})
    ids=[s[0] for s in specs];codes=sorted(set.intersection(*(set(lookups[s]) for s in ids)))
    def calculate(selected):
        matrix=spearmanr([[lookups[sid][code]['value'] for sid in ids] for code in selected]).statistic.tolist()
        pairs=[{'source_a':a,'source_b':b,'title_a':by_id[a]['short_title'],'title_b':by_id[b]['short_title'],'rho':matrix[i][j],'n':len(selected)} for i,a in enumerate(ids) for j,b in enumerate(ids) if j>i]
        return matrix,pairs
    matrix,pairs=calculate(codes);strict_codes=[c for c in codes if all(lookups[s][c]['geographic_comparison_eligible'] for s in ids)];strict_matrix,strict_pairs=calculate(strict_codes)
    regions=[{'code':code,'map_id':code,'name':lookups[ids[0]][code]['name'],'values':{s:lookups[s][code]['value'] for s in ids},'observation_ids':{s:lookups[s][code]['id'] for s in ids},'strict_scope_eligible':code in strict_codes} for code in codes]
    return {'computed':True,'n':len(codes),'features':features,'source_ids':ids,'matrix':matrix,'pairs':pairs,'regions':regions,'imputed_cells':0,'weighting':'unweighted_territories','period':'2024–2025','frequency':'explicit_mixed_structural_snapshot','role':'author_comparable_descriptive_snapshot','strict':{'n':len(strict_codes),'matrix':strict_matrix,'pairs':strict_pairs,'codes':strict_codes,'excluded_codes':[c for c in codes if c not in strict_codes]},'scope_note':'Основная матрица воспроизводит авторскую совокупность. В части источников областные строки 29 и 72 не уточняют охват автономных округов. Дополнительная строгая проверка исключает эти позиции. Обе матрицы рассчитаны без заполнения пропусков.','interpretation':'Жилищная площадь относится к2024, остальные признаки к2025, транспортный парк кдекабрю2025. Корреляция структурных условий не идентифицирует эффект проекта.','clustering_performed':False}

def canonical_unit(value):
    s=str(value or '').strip().casefold().replace('ё','е')
    return {'проценты':'процент','процентов':'процент','%':'процент','квадратных метров на человека':'квадратный метр','м² на человека':'квадратный метр','млн кв. м':'миллион квадратных метров общей площади','миллион квадратных метров':'миллион квадратных метров общей площади','млн м²':'миллион квадратных метров общей площади','трлн руб.':'триллион рублей','млн человек':'миллион человек','миллион человек':'миллион человек','чел.':'человек','тыс. человек':'тысяча человек','тысяча человек':'тысяча человек','ед.':'единица','единиц':'единица','единицы':'единица','шт.':'штука','штук':'штука','суток':'сутки','млн ед.':'миллион единиц','пара поездов':'пара (2 шт.)','процент годовых':'процент годовых'}.get(s,s)
def target_scale(source,target):
    a=canonical_unit(source['unit']);b=canonical_unit(target.get('unit'));sid=source['id']
    if a==b:return 1
    if sid in {'63457','63456'} and a=='человек' and b=='человек на 10 тыс. транспортных средств':return 1
    if sid=='59319' and a=='процент годовых' and b=='процент':return 1
    if sid=='63460' and a=='гектар' and b=='тыс. га':return 1000
    return None
def target_comparisons(sources,targets,packets):
    by_id={s['id']:s for s in sources};out=[];blocked=[]
    for target in targets:
        sid=str(target.get('source_id') or target.get('emiss_id') or '');s=by_id.get(sid)
        if not s:continue
        if not s.get('target_comparison_allowed') or target.get('mapping_status') in {'conditional','unmapped','unresolved'}:
            blocked.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'reason':'source_or_mapping_contract_disallows_comparison'});continue
        scale=target_scale(s,target)
        if scale is None:
            blocked.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'reason':'unit_unresolved','source_unit':s['unit'],'target_unit':target.get('unit')});continue
        for year,value in target.get('years',{}).items():
            if value is None:continue
            original_goal=value;value=float(dec(value)*dec(scale))
            annual=national_point(packets,sid,int(year))
            basis='independent_annual_source_row';reference_ids=[]
            if annual:
                fact=annual['value'];frequency='annual';period=str(year);reference_ids=[annual['id']];basis=annual['period_basis']
            elif sid=='61608':
                # Methodology explicitly defines Vn as sum over n months; n=12 is the year.
                rub=national_point(packets,sid,int(year),'cumulative_ytd',f'{year}-12',{'Вид валюты':'В рублях'})
                fx=national_point(packets,sid,int(year),'cumulative_ytd',f'{year}-12',{'Вид валюты':'В иностранной валюте'})
                if not rub or not fx:continue
                fact=float(dec(rub['value'])+dec(fx['value']));frequency='cumulative_ytd';period=f'{year}-12';reference_ids=[rub['id'],fx['id']];basis='explicit_12_month_sum_two_currencies'
            else:continue
            difference=delta(value,fact);favourable=difference if s['direction']=='higher' else -difference
            out.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'title':s['short_title'],'target_year':int(year),'target_value':value,'fact_value':fact,'fact_period':period,'fact_frequency':frequency,'difference':difference,'difference_unit':difference_unit(s),'unit':s['unit'],'display_unit':s['display_unit'],'ratio_percent':float(dec(fact)/dec(value)*100) if value else None,'direction':s['direction'],'favourable_difference':favourable,'on_favourable_side':favourable>=0,'comparison_kind':'annual_fact_vs_annual_plan' if frequency=='annual' else 'documented_full_year_accumulation_vs_annual_plan','annual_comparison_eligible':True,'formal_attainment_eligible':False,'annual_basis':basis,'reference_observation_id':reference_ids[0],'reference_observation_ids':reference_ids,'target_source':target,'interpretation':'Арифметическое сопоставление с выбранной датированной редакцией цели. Не подтверждает исполнение первоначального задания или причинный эффект.'})
    return out,blocked

def national_changes(sources):
    out=[];annual_december=[]
    for s in sources:
        if not s['temporal_comparison_allowed']:continue
        points=[r for r in s['national'] if r['analytical_value'] is not None and not (s['id'] in {'59262','59263','59993'} and r['year']>=2023 and r.get('national_scope')!='rf_without_new_subjects_from_2023')]
        lookup={(r['frequency'],r['period'],json.dumps(r['category'],sort_keys=True),r.get('national_scope')):r for r in points}
        for r in points:
            if r['frequency']=='dated_snapshot':continue
            prev_period=str(r['year']-1)+r['period'][4:];key=(r['frequency'],prev_period,json.dumps(r['category'],sort_keys=True),r.get('national_scope'));p=lookup.get(key)
            if p:
                d=delta(p['value'],r['value']);out.append({'source_id':s['id'],'title':s['short_title'],'from_period':p['period'],'to_period':r['period'],'prior_period':p['period'],'period':r['period'],'frequency':r['frequency'],'category':r['category'],'from_value':p['value'],'to_value':r['value'],'difference':d,'change':d,'relative_change_percent':ratio(p['value'],r['value']),'difference_unit':difference_unit(s),'unit':s['display_unit'],'reference_observation_ids':[p['id'],r['id']],'comparison_kind':'same_calendar_slice','interpretation':'Сравнение одинаковой частоты, календарного горизонта и категории. Причины изменения не установлены.'})
            if r['frequency']=='annual':
                for freq in ['monthly','cumulative_ytd']:
                    d=lookup.get((freq,str(r['year'])+'-12',json.dumps(r['category'],sort_keys=True),r.get('national_scope')))
                    if d:annual_december.append({'source_id':s['id'],'title':s['short_title'],'year':r['year'],'category':r['category'],'annual_value':r['value'],'december_value':d['value'],'december_frequency':freq,'difference':delta(d['value'],r['value']),'difference_unit':difference_unit(s),'annual_observation_id':r['id'],'december_observation_id':d['id'],'annual_basis':r['period_basis'],'interpretation':'Две исходные формы опубликованы отдельно. Расхождение не исправляется выбором удобного значения.'})
    return out,annual_december

def forecast_eligibility(s):
    count=len({r['year'] for r in s['annual'] if r['analytical_value'] is not None and r['category']==s['default_category']})
    return {'source_id':s['id'],'title':s['short_title'],'annual_observations':count,'distinct_annual_years':count,'eligible':False,'status':'methodology_break_unresolved' if not s['temporal_comparison_allowed'] else 'insufficient_independent_annual_history' if count<4 else 'model_not_validated','reason':'Условная траектория до цели не является вероятностным прогнозом. Для прогнозной модели необходимы отдельная временная проверка, согласование редакций и оценка ошибок.'}

def build(root=ROOT):
    root=Path(root);config=load(root/'scripts/infrastructure_emiss_sources.json');registry_packet=load(root/DATA/'indicators.json');refresh=load(root/DATA/'refresh-status.json');status={s['source_id']:s for s in refresh['sources']}
    packets={c['indicator_id']:load(root/DATA/'series'/f"{c['indicator_id']}.json") for c in config['sources']}
    sources=[make_source(c,packets[c['indicator_id']],status.get(c['indicator_id'],{}),root) for c in config['sources']];by_id={s['id']:s for s in sources};rows=[r for p in packets.values() for r in p['observations']]
    published_at=max((s['published_at'] for s in sources if s['published_at']),default=None)
    registry=[];region_count=len(load(root/'public/data/catalog.json')['regions'])
    for old in registry_packet['items']:
        linked=[by_id[s] for s in old['source_ids']];evidence=[r for s in old['source_ids'] for r in packets[s]['observations']];numeric=[r for r in evidence if r['value'] is not None];regions={r['code'] for r in numeric if r['geo_level']=='regional'}
        registry.append({**old,'source_release_counts':old.get('source_release_counts') or {k:old.get(k) for k in ['n_cells','n_numeric','n_usable','n_domain_violations']},'n_linked_sources':len(linked),'n_loaded_sources':sum(s['available'] for s in linked),'n_cells':len(evidence),'n_numeric':len(numeric),'n_usable':sum(r['analytical_value'] is not None for r in evidence),'n_regions':len(regions),'region_coverage_pct':100*len(regions)/region_count,'n_national':sum(r['geo_level']=='national' for r in numeric),'n_domain_violations':sum(r['excluded'] for r in numeric),'first_end':min((r['period_end'] for r in numeric),default=''),'last_end':max((r['period_end'] for r in evidence if r['analytical_value'] is not None),default=''),'status':'numeric_data' if numeric else 'linked_no_numeric','latest_national':[{**s['latest_national'],'source_title':s['title'],'source_url':s['source_url'],'territory_name':s['latest_national']['name'],'snapshot_id':s['snapshot_id'],'acquired_at':s['published_at'],'origin_kind':'live_emiss','analysis_status':'excluded' if s['latest_national']['excluded'] else 'usable'} for s in linked if s['latest_national']]})
    coverage={'indicators_total':len(registry),'registry_indicators':len(registry),'confirmed_sources':len(sources),'known_sources':len(sources),'numeric_sources':sum(s['available'] for s in sources),'available_sources':sum(s['available'] for s in sources),'indicators_with_numeric':sum(r['n_numeric']>0 for r in registry),'observations':len(rows),'numeric_observations':sum(r['value'] is not None for r in rows),'missing_observations':sum(r['value'] is None for r in rows),'usable_observations':sum(r['analytical_value'] is not None for r in rows),'excluded_numeric_observations':sum(r['value'] is not None and r['excluded'] for r in rows),'independent_annual_national_facts':sum(r['analytical_value'] is not None and r['geo_level']=='national' and r['frequency']=='annual' for r in rows),'annual_equivalent_references':0,'regional_sources':sum(bool(s['regional_latest']) for s in sources),'regions':len({r['code'] for r in rows if r['geo_level']=='regional'}),'other_territory_observations':sum(r['geo_level']=='other' for r in rows),'metadata_only_sources':sum(not s['available'] for s in sources),'unmapped_indicators':len(config.get('unmapped_indicators',[]))}
    target_path=root/DATA/'targets.json';target_packet=load(target_path) if target_path.exists() else [];targets=target_packet if isinstance(target_packet,list) else target_packet.get('items',[])
    comparisons,blocked=target_comparisons(sources,targets,packets);changes,annual_december=national_changes(sources);composition,concentrations=housing_analysis(packets,sources);correlations=author_correlations(packets,sources)
    distributions=[];availability=[];quality=[]
    for s in sources:
        exact=s['regional_latest'];matching=next((r for r in s['national'] if r['period_end']==s['regional_period_end'] and r['frequency']==s['regional_frequency'] and r['category']==s['regional_category'] and r['analytical_value'] is not None),None)
        if exact:distributions.append({'source_id':s['id'],'title':s['short_title'],'period_end':s['regional_period_end'],'frequency':s['regional_frequency'],'category':s['regional_category'],'unit':s['display_unit'],**summary([r for r in exact if r['geographic_comparison_eligible']]),'national_value':matching['analytical_value'] if matching else None,'national_value_origin':'published_national_not_regional_average','excluded_geography_count':sum(not r['geographic_comparison_eligible'] for r in exact)})
        groups=collections.defaultdict(list)
        for r in packets[s['id']]['observations']:groups[(r['period'],r['frequency'],json.dumps(r['category'],sort_keys=True))].append(r)
        for (period,freq,category),cells in sorted(groups.items()):availability.append({'source_id':s['id'],'period':period,'frequency':freq,'category':json.loads(category),'cells':len(cells),'numeric':sum(r['value'] is not None for r in cells),'missing':sum(r['value'] is None for r in cells),'usable':sum(r['analytical_value'] is not None for r in cells),'excluded_numeric':sum(r['value'] is not None and r['excluded'] for r in cells)})
        quality.extend({'source_id':s['id'],**f,'count':f['cells']} for f in s['quality_flags'])
    road_rows=canonical_regions(source_rows(packets,'62794',2025,'annual',geo='regional',category={}))
    road_numeric=[r for r in road_rows if r['analytical_value'] is not None]
    road_summary={'source_id':'62794','period':'2025','frequency':'annual','n':len(road_numeric),'below_50':sum(r['value']<50 for r in road_numeric),'regions_below_50':[compact(r) for r in road_numeric if r['value']<50],'strict_n':sum(r['geographic_comparison_eligible'] for r in road_numeric),'strict_below_50':sum(r['value']<50 and r['geographic_comparison_eligible'] for r in road_numeric),'scope_note':'Авторская совокупность источника и дополнительная проверка без неуточнённых областных строк показаны отдельно.'}
    download_names=[('source_registry','Реестр источников'),('target_comparisons','Годовые сопоставления с целями'),('national_changes','Сопоставимая динамика'),('annual_december_comparisons','Годовые и декабрьские записи'),('regional_summaries','Региональные распределения'),('correlations','Корреляции: авторский охват'),('correlations_strict','Корреляции: строгий охват'),('regional_profiles','Матрица шести характеристик'),('housing_composition','Структура жилищного строительства'),('housing_concentration','Концентрация жилищного строительства'),('quality_flags','Методологические оговорки'),('availability','Календарь доступности')]
    downloads=[{'label':label,'path':f'downloads/projects/{PROJECT}/statistics/{name}.csv'} for name,label in download_names]+[{'label':s['short_title']+' – полный ряд CSV.gz','path':s['downloads']['csv']} for s in sources]
    statistics={'schema_version':1,'project_id':PROJECT,'published_at':published_at,'statistical_as_of':published_at[:10] if published_at else None,'last_checked_at':refresh.get('checked_at'),'coverage':coverage,'registry':registry,'sources':sources,'target_comparisons':comparisons,'unmapped_indicators':config.get('unmapped_indicators',[]),'geography_note':'В каждой карте выбираются один источник, период, частота и категория. Две областные строки с неуточнённым охватом автономных округов имеют отдельную оговорку. Остальные территориальные совокупности не превращаются в субъекты.','history_loading':'Per-source source.downloads.observations; full source packet has observations[].','downloads':downloads}
    analytics={'schema_version':1,'project_id':PROJECT,'published_at':published_at,'coverage':coverage,'regional_summaries':distributions,'regional_distributions':distributions,'regional_history_deferred':True,'correlations':correlations,'profiles':correlations['regions'],'regional_profiles':correlations['regions'],'housing_composition':composition,'housing_concentration':concentrations,'roads_2025':road_summary,'national_changes':changes,'same_month_changes':[r for r in changes if r['frequency']=='monthly'],'annual_december_comparisons':annual_december,'availability':availability,'quality_flags':quality,'quality_flags_are_aggregated':True,'forecast_eligibility':[forecast_eligibility(s) for s in sources],'targets':targets,'target_comparisons':comparisons,'blocked_target_comparisons':blocked,'causal':{'identified':False,'reason':'Региональный срез и динамика наблюдаемого ряда не идентифицируют эффект проекта. Необходимы сопоставимые территории, момент вмешательства, доистория и контрфактический дизайн.'},'methodology':{'imputation':'none','year_end_policy':'explicit_source_rows_only','forecast':'not_validated','clustering':'not_performed','source_date_semantics':'date of verified EMISS acquisition, not time of platform build'},'reproduction':'python scripts/build_infrastructure_analytics.py'}
    atomic(root/DATA/'statistics.json',statistics,compact=True);atomic(root/DATA/'analytics.json',analytics,compact=True);atomic(root/DATA/'context.json',{'schema_version':1,'project_id':PROJECT,'kind':'project_regional_data','external_context':None,'note':'Используются собственные жилищные, транспортные и коммунальные ряды проекта.','profiles':correlations['regions']},compact=True)
    atomic(root/DATA/'indicators.json',{**registry_packet,'as_of':published_at[:10] if published_at else None,'origin_policy':'verified_emiss_source_packets; original_cells_preserved; explicit_period_and_geography_contracts','items':registry})
    foundation_path=root/DATA/'foundation.json'
    if foundation_path.exists():
        f=load(foundation_path);f.setdefault('source_release_registry',dict(f.get('registry',{})));f.setdefault('source_release_results',dict(f.get('results',{})))
        f.setdefault('registry',{}).update(n_registry=len(registry),n_with_numeric=coverage['indicators_with_numeric'],n_with_regional=coverage['regional_sources'],n_unique_cells=len(rows),n_numeric=coverage['numeric_observations'],n_usable=coverage['usable_observations'],n_with_national=sum(bool(s['national']) for s in sources),n_domain_violations=coverage['excluded_numeric_observations'],coverage_pct=100*coverage['indicators_with_numeric']/len(registry))
        f.setdefault('results',{}).update(n_numeric_indicators=coverage['indicators_with_numeric'],n_regional_indicators=coverage['regional_sources'],n_forecast_indicators=0,n_projected_series=0,n_diagnostic_forecast_series=0,n_annual_facts=coverage['independent_annual_national_facts'],n_annual_equivalent_references=0,n_documented_target_indicators=len(targets),forecast_status='no_validated_model',multivariate_status='six_variable_rank_correlations_no_typology')
        f['statistical_as_of']=published_at[:10] if published_at else None;atomic(foundation_path,f)
    methods_path=root/DATA/'methods.json'
    if methods_path.exists():
        methods=load(methods_path)
        overrides={'source_quality':('source_specific_contracts_verified','Исходные93631ячейки сохранены. Риски единиц, периодов, будущих дат и синхронных нулей явно маркированы.'),'observability':('computed_from_source_packets','Карточки каталога и независимые источники различаются. Числа, пропуски и исключения считаются отдельно.'),'time_dynamics':('computed_matching_frequency_category','Сравниваются одинаковые категории, частоты и календарные горизонты. Для индекса среды62872 временное сравнение заблокировано.'),'target_comparison':('documented_annual_comparisons','Годовые факты и явно обозначенное полное ипотечное накопление сравниваются с датированной редакцией цели. Промежуточный месяц не заменяет год.'),'forecasting':('model_not_validated','Условные траектории до цели доступны как сценарии. Вероятностная прогнозная модель не подтверждена.'),'geographical_join':('explicit_scope_mapping','Исходные названия сохранены. Явные строки без автономных округов отделены от агрегатов. Неуточнённые областные строки отмечены.'),'regional_maps':('matched_source_slices','Каждая карта относится к одному источнику, периоду, частоте и категории.'),'regional_descriptive':('unweighted_regions','Квантили type7 и невзвешенное среднее относятся к сопоставимым территориям. РФ взята из источника.'),'correlations':('author_82_strict_80_recomputed','Шесть характеристик: авторская выборка82 и строгая80, без импутации. Корреляция не устанавливает эффект.'),'pca':('not_claimed_in_author_analysis','В новой экспертизе используются ранговые корреляции шести признаков. PCA не добавляется как неподтверждённый результат.'),'kmeans':('not_claimed_in_author_analysis','Кластерная типология и интегральный рейтинг не установлены.'),'multivariate_stability':('explicit_geographic_sensitivity','Сопоставлены82и80территорий. Смысл и частоты каждого признака сохранены.'),'regional_similarity':('descriptive_profiles','Профили конкретных жилищных и транспортных условий не заменяются единым рейтингом.'),'relative_profiles':('descriptive_source_values','Региональные профили сохраняют исходные единицы и годы.'),'interactive_lab':('source_backed_reproducible_calculations','Изменения, распределения, корреляции и условные траектории вычисляются по проверенным источникам.')}
        overrides.update({
            'isolation_forest':('not_claimed_in_author_analysis','Модель поиска аномалий в текущей авторской экспертизе не заявлена. Экстремальное региональное значение само по себе не доказывает ошибку данных.'),
            'moran_global':('not_claimed_in_author_analysis','Пространственная автокорреляция для нового набора не рассчитывалась. Необходимы самостоятельный выбор матрицы пространственных весов, проверка охвата и перестановочный тест.'),
            'moran_local':('not_claimed_in_author_analysis','Локальные пространственные тесты и их множественные проверки не выполнены. Карта описывает значения, без заявления статистически подтверждённых пространственных групп.'),
            'cohort_projection':('not_implemented_without_population_inputs','Когортная проекция требует отдельных данных о населении и переходах. Объёмы строительства, число объектов и административные доли не используются как демографическая модель.'),
            'causal_designs':('design_proposed_effect_not_identified','Предложены способы последующей оценки дополнительного эффекта. Для идентификации нужны конкретные объекты и территории, сроки вмешательства, доистория и обоснованная контрольная траектория.'),
            'heterogeneous_causal_effects':('effect_not_identified','Различия региональных значений показаны описательно. Неоднородность причинного эффекта не оценена без идентифицированного общего дизайна и состава получателей.'),
            'policy_scenario_framework':('conditional_arithmetic_no_causal_effect','Траектории и расчёты пользовательских параметров условны. Они не дают вероятностный прогноз, установленную эффективность финансирования или оценку вклада проекта.'),
        })
        for m in methods['items']:
            if m['method_id'] in overrides:m['current_status'],m['current_limitations']=overrides[m['method_id']]
        methods['current_review_basis']='verified_infrastructure_source_contracts_and_author_report';atomic(methods_path,methods)
    d=root/DOWNLOADS
    csv_write(d/'source_registry.csv',[{k:s.get(k) for k in ['id','title','short_title','unit','display_unit','source_url','available','published_at','last_checked_at','observation_count','numeric_count','missing_count','usable_count','period_semantics','note']} for s in sources])
    csv_write(d/'target_comparisons.csv',comparisons,['source_id','indicator_code','title','target_year','target_value','fact_value','fact_period','fact_frequency','difference','difference_unit','ratio_percent','annual_basis','reference_observation_ids','target_source','interpretation'])
    for name,values in [('national_changes',changes),('annual_december_comparisons',annual_december),('regional_summaries',distributions),('correlations',correlations['pairs']),('correlations_strict',correlations['strict']['pairs']),('regional_profiles',correlations['regions']),('housing_composition',composition),('housing_concentration',concentrations),('quality_flags',quality),('availability',availability)]:csv_write(d/(name+'.csv'),values)
    fields=['id','source_id','name','code','geo_level','national_scope','period','frequency','source_frequency','period_start','period_end','source_period_label','period_basis','category','unit','value','analytical_value','raw_value','excluded','status','geographic_comparison_eligible','quality_codes']
    # Complete raw dimensions, source cell locators and original observation
    # hashes remain in the linked JSON and input ZIP. The flat analysis CSV
    # references exactly the same observation id without duplicating that JSON.
    for sid,p in packets.items():
        flat=[{k:r.get(k) for k in fields if k!='quality_codes'}|{'quality_codes':'|'.join(f['code'] for f in r['quality_flags'])} for r in p['observations']]
        csv_write(d/'series'/(sid+'.csv.gz'),flat,fields)
    atomic(root/DATA/'data-downloads.json',{'schema_version':1,'files':download_records(d, root/'public')})
    print(json.dumps(coverage));return statistics,analytics

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args();build(args.root)
