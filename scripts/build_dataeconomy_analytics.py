#!/usr/bin/env python3
"""Rebuild Data Economy statistics from independently identified cells.

python scripts/build_dataeconomy_analytics.py

Annual facts, source months, YTD ratios and programme totals retain distinct
period contracts. Original source series and regional maps are not imputed.
A separate source-linked profile matrix explicitly records its missing cells,
median imputations, PCA and descriptive clustering with sensitivity checks.
Neither a forecast nor a causal effect is inferred.
"""
from __future__ import annotations
import argparse
import collections
import json
from decimal import Decimal
from pathlib import Path
from download_manifest import download_records
from dataeconomy_data import ROOT,PROJECT,DATA,DOWNLOADS,load,atomic,sha256,csv_write,quantile,annual_equivalents

def latest(rows,usable=True):
    a=[r for r in rows if r.get('analytical_value' if usable else 'value') is not None]
    return max(a,key=lambda r:(r['period_end'],r['frequency']=='annual')) if a else None
def default_category(sid):
    return {}
def compact(row):
    if row is None:return None
    keep={'id','source_id','name','code','map_id','fd','geo_level','period','period_start','period_end','year','frequency','value','analytical_value','excluded','status','category','unit','geographic_comparison_eligible','geographic_exclusion_reason','quality_flags','source_period_label','period_basis','annual_comparison_eligible','period_semantics','national_scope','temporal_comparison_eligible','source_status','source_frequency','source_period_start','source_period_end','annual_equivalent_eligible','annual_equivalent_basis','measurement_regime'}
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
      national=[compact(r) for r in national],annual=[compact(r) for r in national if r['frequency']=='annual'],annual_equivalents=annual_equivalents(sid,national),
      latest_national=compact(latest(current,False)),latest_published=compact(latest(current,False)),latest_analytically_usable=compact(latest(current)),
      default_category=category,categories=[json.loads(x) for x in sorted({json.dumps(r['category'],ensure_ascii=False,sort_keys=True) for r in rows})],
      regional_latest=[compact(r) for r in regional_latest],regional_history=[],regional_history_deferred=True,other_territories=[],other_territory_names=sorted({r['name'] for r in rows if r['geo_level']=='other'}),other_territory_count=sum(r['geo_level']=='other' for r in rows),
      regional_periods=sorted({r['period_end'] for r in regional}),regional_period_end=key[0] if key else None,regional_frequency=key[1] if key else None,regional_category=category,
      regional_slices=[{'period':p[0]['period'],'period_end':k[0],'frequency':k[1],'category':p[0]['category'],'count':len(p),'numeric_count':sum(r['value'] is not None for r in p),'usable_count':sum(r['analytical_value'] is not None for r in p),'canonical_region_count':len(canonical_regions(p))} for k,p in sorted(slices.items())],
      project_territory_count=len({r['name'] for r in rows if r['geo_level']=='project_territory'}), project_territory_observations=sum(r['geo_level']=='project_territory' for r in rows), geography_scope='national_regional_project_territories' if any(r['geo_level']=='project_territory' for r in rows) else 'regional_and_national' if regional else 'national_only',geography_note='Исходные территории сохранены. Субъекты, федеральные округа и РФ учитываются раздельно. Национальное значение не заменяется средним регионов.',
      quality_flags=[{'code':c,'message':m,'severity':s,'exclude_from_analysis':e,'cells':n} for (c,m,s,e),n in sorted(flags.items())],
      downloads={'observations':f'data/projects/{PROJECT}/series/{sid}.json','provenance':f'data/projects/{PROJECT}/provenance/{sid}.json','source_input':f'downloads/projects/{PROJECT}/statistics/emiss_inputs/{sid}.zip','csv':f'downloads/projects/{PROJECT}/statistics/series/{sid}.csv.gz'})
    if sid in {'63143','63144','63145'}:source['geography_note']+=' Национальная строка явно исключает новые субъекты с 01.01.2023; этот охват сохраняется отдельно.'
    raw=status.get('raw_file')
    if raw:
        expected=f'downloads/projects/{PROJECT}/statistics/emiss_current/{sid}.zip';provenance=load(root/DATA/'provenance'/f'{sid}.json')
        if raw!=expected or provenance.get('current_raw')!=raw or sha256(root/'public'/raw)!=provenance.get('current_raw_sha256'):raise ValueError('Current response provenance mismatch')
        source['downloads']['current_raw']=raw
    return source
def difference_unit(source):return 'п. индекса' if source['id'] in {'62751','62857','62811'} else 'п.п.' if source['unit']=='процент' else source['display_unit']
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


def canonical_unit(value):
    s=str(value or '').strip().casefold().replace('ё','е')
    return {'%':'процент','процентов':'процент','проценты':'процент','чел.':'человек','чел':'человек','ед.':'единица','единица':'единица','единицы':'единица','штука':'единица','миллион рублей':'миллион рублей','млн руб.':'миллион рублей','трлн руб.':'триллион рублей','миллион человек':'миллион человек','млн человек':'миллион человек','млн чел.':'миллион человек','тыс. человек':'тысяча человек','тыс. чел.':'тысяча человек','единиц':'единица','шт.':'единица','млрд руб.':'миллиард рублей','млрд. руб.':'миллиард рублей','километр':'километр (тысяча метров)','километр; тысяча метров':'километр (тысяча метров)','км':'километр (тысяча метров)','тыс. га':'тысяча гектаров','млн куб. м':'миллион кубических метров','млн м3':'миллион кубических метров','млн м³':'миллион кубических метров'}.get(s,s)

def target_comparisons(sources,targets,packets):
    by_id={s['id']:s for s in sources};out=[];blocked=[]
    for target in targets:
        sid=str(target.get('source_id') or '');s=by_id.get(sid)
        if not s:continue
        if not s['target_comparison_allowed'] or target.get('mapping_status') in {'conditional','unmapped','unresolved'} or target.get('discontinued'):
            blocked.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'reason':'source_or_mapping_contract_disallows_comparison'});continue
        if canonical_unit(s['unit'])!=canonical_unit(target.get('unit')):
            blocked.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'reason':'unit_unresolved','source_unit':s['unit'],'target_unit':target.get('unit')});continue
        for year,goal in target.get('years',{}).items():
            if goal is None:continue
            eligible=[r for r in packets[sid]['observations'] if r['geo_level']=='national' and r['year']==int(year) and r['period_end']==str(year)+'-12-31' and r['category']==default_category(sid) and r['analytical_value'] is not None]
            if len(eligible)>1:raise ValueError('Ambiguous December target reference: '+sid)
            if not eligible:continue
            point=eligible[0];difference=delta(goal,point['value']);favourable=difference if s['direction']=='higher' else -difference
            annual_rule=point.get('annual_equivalent_eligible',False)
            kind='reviewed_december_annual_equivalent' if annual_rule else 'year_end_cumulative_reference' if point['frequency']=='cumulative_ytd' else 'december_publication_vs_dated_annual_plan'
            out.append({'source_id':sid,'indicator_code':target.get('indicator_code'),'title':s['short_title'],'target_year':int(year),'target_value':goal,
                'fact_value':point['value'],'fact_period':point['period'],'fact_frequency':point['frequency'],'difference':difference,'difference_unit':difference_unit(s),
                'unit':s['unit'],'display_unit':s['display_unit'],'ratio_percent':float(dec(point['value'])/dec(goal)*100) if goal else None,
                'direction':s['direction'],'favourable_difference':favourable,'on_favourable_side':favourable>=0,
                'comparison_kind':kind,'annual_comparison_eligible':point['frequency']=='annual','annual_equivalent_eligible':annual_rule,
                'formal_attainment_eligible':False,'primary_method_rule_verified':False,
                'annual_basis':point.get('annual_equivalent_basis') if annual_rule else 'documented_ytd_coverage' if point['frequency']=='cumulative_ytd' else 'monthly_december_not_independent_annual',
                'reference_observation_id':point['id'],'reference_observation_ids':[point['id']],'national_scope':point['national_scope'],
                'external_consistency':s.get('external_consistency'),'target_source':target,
                'interpretation':'Арифметическое сопоставление декабрьской публикации с датированной редакцией цели. Частота и правило накопления сохранены. Самостоятельный годовой факт и официальное исполнение не установлены. '+('Годовое правило разобрано в авторской экспертизе; полного первичного текста в проверенном наборе нет.' if annual_rule else '')})
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
            if not s['temporal_comparison_allowed'] or not r.get('temporal_comparison_eligible',True):continue
            prior=lookup.get((r['frequency'],str(r['year']-1)+r['period'][4:],json.dumps(r['category'],sort_keys=True)))
            if not prior or not prior.get('temporal_comparison_eligible',True):continue
            if prior.get('measurement_regime')!=r.get('measurement_regime'):continue
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

def digital_analysis(packets,sources,comparisons):
    by_id={s['id']:s for s in sources};profiles=[]
    for sid in ['62766','62815','62767','62760','62763','62752','62757']:
        source=by_id[sid];end=source['regional_period_end'];frequency=source['regional_frequency']
        rows=canonical_regions([r for r in packets[sid]['observations'] if r['geo_level']=='regional' and r['period_end']==end and r['frequency']==frequency and r['category']=={}],strict=True)
        rows=[r for r in rows if r['analytical_value'] is not None]
        national=next((r for r in packets[sid]['observations'] if r['geo_level']=='national' and r['period_end']==end and r['frequency']==frequency and r['category']=={}),None)
        profiles.append({'id':'regional_'+sid,'source_id':sid,'title':source['short_title'],'year':int(end[:4]),'period':end[:7],'frequency':frequency,'unit':source['display_unit'],**summary(rows),'rows':[compact(r) for r in rows],
          'national_value':national['value'] if national else None,'national_observation_id':national['id'] if national else None,'national_reference_comparable':False,
          'below_50':sum(r['value']<50 for r in rows),'at_least_70':sum(r['value']>=70 for r in rows),'at_least_95':sum(r['value']>=95 for r in rows),'at_100':sum(r['value']==100 for r in rows),
          'zero_count':sum(r['value']==0 for r in rows),'map_territories':89,'missing_map_territories':89-len(rows),'reference_observation_ids':[r['id'] for r in rows],
          'interpretation':'Невзвешенное распределение одного показателя и месяца публикации. Национальный расчёт не заменяется средним регионов и не наносится как сопоставимая опорная линия без согласования компонент.'})
    thematic=[
      ('internet','Инфраструктура доступа',['62803','62805'],'Техническая возможность, фактическое подключение, качество связи и стоимость доступа имеют разные измерения.'),
      ('platforms','Цифровые платформы социальной сферы',['62856','62752','62753','62757','62756','62755','62754'],'Составной индекс, институциональный охват, оборудование и фактическое использование разделены. Возрастная граница 12–60 лет не включает старшие группы.'),
      ('ai','Искусственный интеллект и рынок данных',['62811','62904','62866','62864','62867','62868','62869','62870'],'Исследования, кадры, затраты, мощность и готовность не образуют единого доказательства эффекта внедрения ИИ.'),
      ('government','Цифровое государственное управление',['62764','62765','62766','62767','62758','62759','62760','62763','62761'],'Вид услуги, обращение, пользователь и завершённый процесс имеют разные знаменатели. Порог высокой оценки не является долей довольных граждан.'),
      ('software','Отечественные ИТ-решения',['62814','62816','62857','62817','62815','62818','62813'],'Годовые сведения, составные показатели ПО и скользящие денежные объёмы нельзя складывать по месяцам или объединять в среднюю долю импортозамещения.'),
      ('research','Прикладные исследования и разработки',['62888','62889','62830','63475'],'Накопленные инвестиции, число кубитов, протяжённость сетей и этап готовности прототипа различаются. Нулевой опубликованный уровень требует проверки статуса.'),
      ('cybersecurity','Инфраструктура кибербезопасности',['62751','62808','62807','62806','62809','62810'],'Предотвращённые попытки, фактический ущерб, охват защиты и длительность блокировки оцениваются отдельно. Антифрод-индекс допускает значения выше 100.'),
      ('personnel','Кадры для цифровой трансформации',['62883','62880'],'Сертификат, годовой выпуск, накопленное число обученных и профильная занятость не взаимозаменяемы.'),
      ('statistics','Государственная статистика',['63143','63144','63145'],'Машиночитаемые показатели, качество паспортов и объём отчётных элементов имеют самостоятельные знаменатели. Методика качества изменена с 2026 года.'),
    ]
    blocks=[]
    for key,title,ids,note in thematic:
        blocks.append({'id':key,'title':title,'source_ids':ids,'numeric_sources':sum(by_id[s]['available'] for s in ids),'sources':[{'source_id':sid,'title':by_id[sid]['short_title'],'unit':by_id[sid]['display_unit'],'available':by_id[sid]['available'],'latest_published':by_id[sid]['latest_published'],'latest_analytically_usable':by_id[sid]['latest_analytically_usable'],'note':by_id[sid]['note']} for sid in ids],'interpretation':note})
    diagnostics=[{'source_id':s['id'],'title':s['short_title'],'period_semantics':s['period_semantics'],'independent_annual_facts':len(s['annual']),'reviewed_annual_equivalents':len(s['annual_equivalents']),
      'original_zero_count':sum(r['value']==0 for r in packets[s['id']]['observations']),'excluded_numeric_count':s['excluded_numeric_count'],'scenario_allowed':s['scenario_allowed'],'target_comparison_allowed':s['target_comparison_allowed'],'note':s['note']} for s in sources]
    selection=[r for r in comparisons if r['target_year']==2025]
    description={'year':2025,'comparisons':len(selection),'above':sum(r['difference']>0 for r in selection),'equal':sum(r['difference']==0 for r in selection),'below':sum(r['difference']<0 for r in selection),'formal_attainment_comparisons':sum(r['formal_attainment_eligible'] for r in selection),'reference_observation_ids':[r['reference_observation_id'] for r in selection],'interpretation':'Условные декабрьские сопоставления выбранной редакции, без общего процента выполнения проекта.'}
    return {'regional_profiles':profiles,'blocks':blocks,'diagnostics':diagnostics,'december_target_summary':description,'annual_target_summary':{'comparisons':0,'formal_attainment_comparisons':0,'interpretation':'Самостоятельные годовые записи в источниках отсутствуют.'},'composite_ranking_computed':False,'source_series_imputed_cells':0,'profile_matrix_imputation_is_separate':True,'author_snapshot_role':'Содержательная экспертиза и текущие статистические публикации сохраняют собственные даты.'}

def build(root=ROOT):
    root=Path(root);config=load(root/'scripts/dataeconomy_emiss_sources.json');registry_packet=load(root/DATA/'indicators.json');refresh=load(root/DATA/'refresh-status.json')
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
          'n_national':sum(r['geo_level']=='national' for r in numeric),'n_domain_violations':sum(any(f['code'] in {'below_domain','above_domain','outside_binary_status'} for f in r['quality_flags']) for r in numeric),'n_review_exclusions':sum(r['excluded'] for r in numeric),
          'first_end':min((r['period_end'] for r in numeric),default=''),'last_end':max((r['period_end'] for r in evidence if r['analytical_value'] is not None),default=''),
          'status':'numeric_data' if numeric else 'linked_no_numeric' if linked else 'unmapped',
          'latest_national':[{**s['latest_national'],'source_title':s['title'],'source_url':s['source_url'],'territory_name':s['latest_national']['name'],'snapshot_id':s['snapshot_id'],'acquired_at':s['published_at'],'origin_kind':'live_emiss','analysis_status':'excluded' if s['latest_national']['excluded'] else 'usable'} for s in linked if s['latest_national']]})
    coverage={'indicators_total':len(registry),'registry_indicators':len(registry),'confirmed_sources':len(sources),'known_sources':len(sources),
        'numeric_sources':sum(s['available'] for s in sources),'available_sources':sum(s['available'] for s in sources),'indicators_with_numeric':sum(r['n_numeric']>0 for r in registry),
        'observations':len(rows),'numeric_observations':sum(r['value'] is not None for r in rows),'missing_observations':sum(r['value'] is None for r in rows),
        'usable_observations':sum(r['analytical_value'] is not None for r in rows),'excluded_numeric_observations':sum(r['value'] is not None and r['excluded'] for r in rows),
        'domain_violations':sum(r['value'] is not None and any(f['code'] in {'below_domain','above_domain','outside_binary_status'} for f in r['quality_flags']) for r in rows),
        'review_exclusions':sum(r['value'] is not None and any(f['code']=='technology_zero_requires_review' for f in r['quality_flags']) for r in rows),
        'independent_annual_national_facts':sum(r['analytical_value'] is not None and r['geo_level']=='national' and r['frequency']=='annual' for r in rows),
        'annual_equivalent_references':sum(len(s['annual_equivalents']) for s in sources),'regional_sources':sum(bool(s['regional_latest']) for s in sources),
        'regions':len({r['code'] for r in rows if r['geo_level']=='regional'}),'other_territory_observations':sum(r['geo_level']=='other' for r in rows),
        'project_territory_observations':sum(r['geo_level']=='project_territory' for r in rows),'project_territories':len({r['name'] for r in rows if r['geo_level']=='project_territory'}),
        'metadata_only_sources':sum(not s['available'] for s in sources),'unmapped_indicators':len(config.get('unmapped_indicators',[])),
        'discontinued_sources':sum(s['source_status']=='discontinued' for s in sources)}
    target_path=root/DATA/'targets.json';target_packet=load(target_path) if target_path.exists() else []
    targets=target_packet if isinstance(target_packet,list) else target_packet.get('items',[])
    comparisons,blocked=target_comparisons(sources,targets,packets);changes,annual_december=national_changes(sources)
    digital=digital_analysis(packets,sources,comparisons)
    from dataeconomy_multivariate import build_multivariate
    multivariate=build_multivariate(root,packets,sources)
    multivariate_computed=multivariate.get('status')=='computed'
    admissible_partition=multivariate_computed and multivariate['summary']['baseline_k']>=2
    correlations={'computed':False,'n':0,'features':[],'pairs':[],'regions':[],'matrix':[],'reason':'Показатели имеют разные содержательные периоды и знаменатели. Проверка многомерного описания вынесена в отдельный блок с исходной матрицей и проверками устойчивости.','clustering_performed':multivariate_computed,'admissible_partition_available':admissible_partition}
    profiles=[{**row,'profile_id':block['id']} for block in digital['regional_profiles'] for row in block['rows']]
    distributions=[];availability=[];quality=[]
    for s in sources:
        exact=s['regional_latest'];matching=next((r for r in s['national'] if r['period_end']==s['regional_period_end'] and r['frequency']==s['regional_frequency'] and r['category']==s['regional_category'] and r['analytical_value'] is not None),None)
        if exact:distributions.append({'source_id':s['id'],'title':s['short_title'],'period_end':s['regional_period_end'],'frequency':s['regional_frequency'],'category':s['regional_category'],'unit':s['display_unit'],**summary([r for r in exact if r['geographic_comparison_eligible']]),'national_value':matching['analytical_value'] if matching else None,'national_value_origin':'published_national_not_regional_average','national_reference_comparable':False,'excluded_geography_count':sum(not r['geographic_comparison_eligible'] for r in exact)})
        groups=collections.defaultdict(list)
        for r in packets[s['id']]['observations']:groups[(r['period'],r['frequency'],json.dumps(r['category'],sort_keys=True))].append(r)
        for (period,freq,category),cells in sorted(groups.items()):availability.append({'source_id':s['id'],'period':period,'frequency':freq,'category':json.loads(category),'cells':len(cells),'numeric':sum(r['value'] is not None for r in cells),'missing':sum(r['value'] is None for r in cells),'usable':sum(r['analytical_value'] is not None for r in cells),'excluded_numeric':sum(r['value'] is not None and r['excluded'] for r in cells)})
        quality.extend({'source_id':s['id'],**f,'count':f['cells']} for f in s['quality_flags'])
    download_names=[('source_registry','Реестр источников'),('target_comparisons','Условные декабрьские сопоставления с целями'),('national_changes','Сопоставимая динамика'),('annual_december_comparisons','Годовые и декабрьские записи'),('regional_summaries','Региональные распределения'),('digital_profiles','Семь региональных распределений'),('digital_diagnostics','Определения и ограничения цифровых показателей'),('quality_flags','Замечания к исходным значениям'),('availability','Календарь доступности')]
    downloads=[{'label':label,'path':f'downloads/projects/{PROJECT}/statistics/{name}.csv'} for name,label in download_names]+[{'label':s['short_title']+' – полный ряд CSV.gz','path':s['downloads']['csv']} for s in sources]
    downloads.append({'label':'Многомерные расчёты и проверки устойчивости' if multivariate_computed else 'Статус доступности многомерных расчётов','path':f'downloads/projects/{PROJECT}/statistics/multivariate.json'})
    if multivariate_computed:downloads += [{'label':'Исходная матрица с маской заполнений','path':f'downloads/projects/{PROJECT}/statistics/multivariate_inputs.csv'},{'label':'Проверка авторских многомерных расчётов','path':f'downloads/projects/{PROJECT}/statistics/multivariate_replication.csv'}]
    statistics={'schema_version':1,'project_id':PROJECT,'published_at':published_at,'statistical_as_of':published_at[:10],'last_checked_at':refresh.get('checked_at'),
        'coverage':coverage,'registry':registry,'sources':sources,'target_comparisons':comparisons,'unmapped_indicators':config.get('unmapped_indicators',[]),
        'geography_note':'Один источник, период, частота и категория задают один территориальный срез. Субъекты, национальные агрегаты и другие территориальные уровни не смешиваются.',
        'history_loading':'Per-source source.downloads.observations; full source packet has observations[].','downloads':downloads}
    analytics={'schema_version':1,'project_id':PROJECT,'published_at':published_at,'coverage':coverage,
        'regional_summaries':distributions,'regional_distributions':distributions,'regional_history_deferred':True,
        'correlations':correlations,'profiles':profiles,'regional_profiles':profiles,'digital':digital,'digital_profiles':digital['regional_profiles'],'analysis_blocks':digital['blocks'],'multivariate':multivariate,'national_changes':changes,'changes':changes,
        'same_month_changes':[r for r in changes if r['frequency'] in {'monthly','cumulative_ytd'}],
        'annual_december_comparisons':annual_december,'availability':availability,'quality_flags':quality,'quality_flags_are_aggregated':True,
        'forecast_eligibility':[forecast_eligibility(s) for s in sources],'targets':targets,'target_comparisons':comparisons,'blocked_target_comparisons':blocked,
        'causal':{'identified':False,'reason':'Региональные различия и административные цифровые показатели не идентифицируют эффект проекта. Требуются конкретное вмешательство, сопоставимая история и обоснованная контрольная траектория.'},
        'methodology':{'imputation':'none_in_source_series;explicit_mask_only_in_profile_matrix','year_end_policy':'reviewed_december_equivalence_separate_from_independent_annual','forecast':'not_validated','clustering':('computed_with_seed_feature_and_time_sensitivity' if admissible_partition else 'no_admissible_partition_with_sensitivity_computed') if multivariate_computed else 'not_computed:'+multivariate['status'],'pca':'computed_descriptive_not_ranking' if multivariate_computed else 'not_computed:'+multivariate['status'],'source_date_semantics':'verified EMISS acquisition, distinct from platform build and network attempt'},
        'reproduction':'python scripts/build_dataeconomy_analytics.py'}
    atomic(root/DATA/'statistics.json',statistics,compact=True);atomic(root/DATA/'analytics.json',analytics,compact=True)
    atomic(root/DATA/'indicators.json',{**registry_packet,'as_of':published_at[:10],'origin_policy':'verified_emiss_source_packets; all_original_cells_preserved; explicit_period_and_geography_contracts','items':registry})
    atomic(root/DATA/'context.json',{'schema_version':1,'project_id':PROJECT,'kind':'project_regional_data','external_context':None,'note':'Семь отдельных распределений административных цифровых показателей. Матрица PCA и проверки групп не являются рейтингом цифрового благополучия населения.','profiles':profiles},compact=True)
    d=root/DOWNLOADS
    csv_write(d/'source_registry.csv',[{k:s.get(k) for k in ['id','title','short_title','unit','display_unit','source_url','source_status','available','published_at','last_checked_at','observation_count','numeric_count','missing_count','usable_count','period_semantics','note']} for s in sources])
    csv_write(d/'target_comparisons.csv',comparisons,['source_id','indicator_code','title','target_year','target_value','fact_value','fact_period','fact_frequency','difference','difference_unit','ratio_percent','annual_basis','reference_observation_ids','target_source','interpretation'])
    for name,values in [('national_changes',changes),('annual_december_comparisons',annual_december),('regional_summaries',distributions),('digital_profiles',profiles),('digital_diagnostics',digital['diagnostics']),('quality_flags',quality),('availability',availability)]:csv_write(d/(name+'.csv'),values)
    fields=['id','source_id','name','code','geo_level','national_scope','period','frequency','source_frequency','period_start','period_end','source_period_start','source_period_end','source_period_label','period_basis','category','unit','value','analytical_value','raw_value','excluded','status','source_status','geographic_comparison_eligible','quality_codes']
    for sid,p in packets.items():
        flat=[{k:r.get(k) for k in fields if k!='quality_codes'}|{'quality_codes':'|'.join(f['code'] for f in r['quality_flags'])} for r in p['observations']]
        csv_write(d/'series'/(sid+'.csv.gz'),flat,fields)
    atomic(root/DATA/'data-downloads.json',{'schema_version':1,'files':download_records(d, root/'public')})
    print(json.dumps(coverage));return statistics,analytics

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args();build(args.root)
