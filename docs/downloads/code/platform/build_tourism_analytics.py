#!/usr/bin/env python3
"""Build descriptive Tourism data with explicit period, unit and source semantics."""
from pathlib import Path
import argparse, collections, math, statistics
from download_manifest import download_records
from tourism_data import *

def quantile(values,p):
 values=sorted(values);x=(len(values)-1)*p;lo=int(math.floor(x));hi=int(math.ceil(x));return values[lo]+(values[hi]-values[lo])*(x-lo)

def build(root=ROOT):
 root=Path(root);data=root/DATA;downloads=root/DOWNLOADS;downloads.mkdir(parents=True,exist_ok=True)
 packets=[load(data/'series'/f'{sid}.json') for sid in SOURCE_ORDER];allrows=[r for p in packets for r in p['observations']]
 targets=load(data/'targets.json') if (data/'targets.json').exists() else {'items':[]}
 original=load(root/'inputs/tourism/statistics/catalog_original.json');registry=[];sources=[]
 for packet in packets:
  sid=packet['source_id'];rows=packet['observations'];national=sorted([r for r in rows if r['geo_level']=='national'],key=lambda r:r['period_end']);regional=[r for r in rows if r['geo_level']=='regional']
  end=max((r['period_end'] for r in regional),default=None);latest=[r for r in regional if r['period_end']==end]
  csv_write(downloads/f'observations_{sid}.csv',rows)
  sources.append({'source_id':sid,'indicator_code':MAPPING[sid],'title':packet['title'],'short_title':NOTES[sid][0],'unit':packet['unit'],
   'source_url':packet['source_url'],'published_at':packet['published_at'],'statistical_as_of':packet['statistical_as_of'],
   'observations_count':len(rows),'numeric_count':sum(r['value'] is not None for r in rows),'usable_count':sum(r['analytical_value'] is not None for r in rows),
   'national':national,'regional_latest':latest,'regional_count':len(latest),'n_regions':len(latest),'n_national':len(national),
   'period_semantics':NOTES[sid][1],'semantic_note':NOTES[sid][2],'note':NOTES[sid][2],'quality_note':NOTES[sid][2],
   'first_period':min((r['period_end'] for r in rows),default=None),'last_period':max((r['period_end'] for r in rows),default=None),
   'frequencies':sorted({r['frequency'] for r in rows}),'status':'verified_source_snapshot','history_url':f'data/projects/tourism/series/{sid}.json',
   'downloads':{'observations':f'downloads/projects/tourism/statistics/observations_{sid}.csv','source':f'downloads/projects/tourism/statistics/emiss_inputs/{sid}.zip','provenance':f'data/projects/tourism/provenance/{sid}.json'}})
 for entry in original['items']:
  code=entry['indicator_code'];linked=[s for s in sources if s['indicator_code']==code];selected=[r for p in packets if MAPPING[p['source_id']]==code for r in p['observations']]
  revised={**entry,'catalog_source_ids':entry.get('source_ids',[]),'catalog_status_original':entry.get('catalog_status'),
   'source_ids':[s['source_id'] for s in linked],'n_linked_sources':len(linked),'n_loaded_sources':len(linked),'n_cells':len(selected),'n_numeric':sum(r['value'] is not None for r in selected),
   'n_usable':sum(r['analytical_value'] is not None for r in selected),'n_regions':len({r['map_id'] for r in selected if r['geo_level']=='regional'}),'n_national':sum(r['geo_level']=='national' for r in selected),
   'n_domain_violations':sum(any(f['code']=='domain_violation' for f in r['quality_flags']) for r in selected),
   'first_end':min((r['period_end'] for r in selected),default=None),'last_end':max((r['period_end'] for r in selected),default=None),
   'latest_national':[s['national'][-1] for s in linked if s['national']],'status':'numeric_data' if selected else 'no_verified_numeric_source',
   'mapping_status':'reviewed_definition_match' if code=='2.14.П3.1' else 'reviewed_source_semantics' if code=='2.14.П.1' else 'preserved_catalog_mapping'}
  if code in ('2.14.П.1','2.14.П3.1'):
   revised['mapping_note']='Таблица 63347 измеряет иностранных размещённых граждан, млн человек. Денежный экспорт показан только по 62902, млрд долларов США. Исходная каталоговая связь 63347 с экспортным прокси сохранена в catalog_source_ids.'
  registry.append(revised)
 assert len(registry)==10
 coverage={'indicators_total':10,'registry_indicators':10,'catalog_indicators_with_numeric':5,'indicators_with_numeric':sum(bool(r['source_ids']) for r in registry),'semantically_available_indicators':sum(bool(r['source_ids']) for r in registry),
  'confirmed_sources':len(sources),'known_sources':len(sources),'numeric_sources':len(sources),'available_sources':len(sources),
  'observations':len(allrows),'numeric_observations':sum(r['value'] is not None for r in allrows),'missing_observations':sum(r['value'] is None for r in allrows),
  'usable_observations':sum(r['analytical_value'] is not None for r in allrows),'excluded_numeric_observations':sum(r['value'] is not None and r['excluded'] for r in allrows),
  'domain_violations':sum(any(f['code']=='domain_violation' for f in r['quality_flags']) for r in allrows),'review_exclusions':sum(r['value'] is not None and r['excluded'] and not any(f['code']=='domain_violation' for f in r['quality_flags']) for r in allrows),
  'regional_sources':sum(bool(s['regional_count']) for s in sources),'regions':len({r['map_id'] for r in allrows if r['geo_level']=='regional'}),
  'independent_annual_national_facts':sum(r['geo_level']=='national' and r['source_frequency']=='annual' and not r['excluded'] for r in allrows),
  'annual_equivalent_references':sum(r['geo_level']=='national' and r['period']=='2025-12' and not r['excluded'] for r in allrows),
  'unmapped_indicators':sum(not r['source_ids'] for r in registry),'metadata_only_sources':0,'other_territory_observations':sum(r['geo_level']=='other' for r in allrows),
  'coverage_note':'Пять кодов имели прямые числовые связи исходного каталога. После содержательной сверки 63347 доступен шестой показатель – иностранные размещения. Число первичных наблюдений не изменено.'}
 dates=[s['published_at'] for s in sources];published=max(dates);refresh=load(data/'refresh-status.json')
 comparisons=[]
 qualification={'62900':'Годовая оценка поездок в декабрьской публикации. Ретроспективное сравнение с редакцией плана 16.10.2026.',
  '62159':'Декабрьский запас зарегистрированных номеров. Превышение ориентира не определяет строительный ввод.',
  '62903':'Сохранённая декабрьская оценка 3,0%. Первая годовая оценка может быть равна плану. Отдельное позднейшее сообщение 3,1% приведено в авторском отчёте и не подменяет ячейку выгрузки.',
  '62902':'Условное арифметическое сравнение. Стадия уточнения денежной декабрьской оценки не установлена.',
  '63347':'Условное арифметическое сравнение физических размещений. Стадия уточнения не установлена, величина не является долларовым экспортом.',
  '62780':'Опубликованная доля совпадает с целью. Числитель и знаменатель не сверены.'}
 for item in targets['items']:
  sid=item.get('source_id')
  if not sid:continue
  source=next(s for s in sources if s['source_id']==sid);rows=[r for r in source['national'] if r['period']=='2025-12' and not r['excluded']]
  target=item['years'].get('2025')
  if not rows or target is None:continue
  row=rows[-1];difference=row['analytical_value']-target
  comparisons.append({'indicator_code':item['indicator_code'],'source_id':sid,'title':item['title'],'year':2025,'period':row['period'],
   'value':row['value'],'target':target,'unit':source['unit'],'difference':difference,'difference_pct':difference/target*100 if target else None,
   'difference_unit':'п.п.' if source['unit']=='процент' else source['unit'],'status_label':'Условное арифметическое сопоставление' if sid in ('62902','63347','62903','62780') else 'Ретроспективное описательное сопоставление','comparison_kind':'retrospective_december_reference','status':'conditional_arithmetic_comparison' if sid in ('62902','63347','62903','62780') else 'retrospective_descriptive_comparison',
   'formal_completion_status':None,'causal_status':'not_identified','note':qualification[sid],'source_url':source['source_url'],
   'target_source_url':item['source_url'],'target_source_sha256':item['source_sha256'],'target_source_version':item['source_version'],'target_source_locator':item['source_locator']})
 stats={'schema_version':1,'project_id':'tourism','published_at':published,'statistical_as_of':max(p.get('statistical_as_of',STATISTICAL_AS_OF) for p in packets),'last_checked_at':refresh.get('checked_at'),
  'coverage':coverage,'registry':registry,'sources':sources,'target_comparisons':comparisons,'unmapped_indicators':[r for r in registry if not r['source_ids']],
  'geography_note':'Региональная панель содержит 85 территорий только для поездок. Пропущенные территории не заменены нулями. Сумма показателей не является долей путешествующих жителей.',
  'history_loading':'Каждый полный ряд загружается отдельно из series/{source_id}.json.',
  'downloads':{'observations':'downloads/projects/tourism/statistics/observations.csv','registry':'downloads/projects/tourism/statistics/registry.csv','comparisons':'downloads/projects/tourism/statistics/target_comparisons.csv','original_snapshot':'downloads/projects/tourism/statistics/observations_snapshot.csv.gz'}}
 regional=[r for r in allrows if r['geo_level']=='regional' and not r['excluded']];periods=sorted({r['period_end'] for r in regional});summaries=[];reconciliation=[]
 for end in periods:
  rows=[r for r in regional if r['period_end']==end];v=[r['value'] for r in rows];national=next((r for r in allrows if r['source_id']=='62900' and r['geo_level']=='national' and r['period_end']==end),None);total=sum(v)
  summaries.append({'source_id':'62900','title':'Туристические поездки','period_end':end,'period':end[:7],'frequency':'cumulative_ytd','unit':'миллион штук','n':len(v),
   'minimum':min(v),'q1':quantile(v,.25),'median':statistics.median(v),'q3':quantile(v,.75),'maximum':max(v),'mean':statistics.mean(v),'sum':total,
   'national_value':national['value'] if national else None,'weighting':'unweighted_territories','quartile_method':'Hyndman_Fan_type_7','interpretation':'Распределение накопленных поездок по принимающим территориям. Не оценка доступности поездок для жителей.'})
  reconciliation.append({'period_end':end,'regions':len(rows),'regional_sum':total,'national_value':national['value'] if national else None,'difference':total-national['value'] if national else None,'tolerance':1e-6,'equal':abs(total-national['value'])<1e-6 if national else False})
 annual=[r for r in regional if r['period']=='2025-12'];latest=[r for r in regional if r['period_end']==max(periods)]
 annual_total=sum(r['value'] for r in annual)
 annual_ranked=[{**r,'rank':i+1,'share_pct':r['value']/annual_total*100} for i,r in enumerate(sorted(annual,key=lambda r:-r['value']))]
 districts=[]
 for fd in sorted({r.get('fd') for r in annual if r.get('fd')}):
  selected=[r for r in annual if r.get('fd')==fd];total=sum(r['value'] for r in selected);districts.append({'name':fd,'year':2025,'period':'2025-12','value':total,'unit':'млн поездок','regions':len(selected),'share_pct':total/annual_total*100,'weighting':'sum_of_published_regions'})
 changes=[]
 for source in sources:
  series=source['national'];last=next((r for r in reversed(series) if not r['excluded']),None)
  prior=next((r for r in series if last and r['period_end'][5:]==last['period_end'][5:] and r['year']==last['year']-1 and not r['excluded']),None)
  if last and prior:
   changes.append({'source_id':source['source_id'],'title':source['title'],'period':last['period'],'prior_period':prior['period'],'value':last['value'],'prior_value':prior['value'],'unit':source['unit'],'difference':last['value']-prior['value'],'difference_pct':(last['value']/prior['value']-1)*100 if prior['value'] else None,'status':'descriptive_same_month_reference','causal_status':'not_identified','methodology_comparability':'requires_edition_review','note':source['semantic_note']})
 forecast=[{'source_id':s['source_id'],'title':s['title'],'eligible':False,'status':'not_estimated','reason':'Показатели имеют накопление, повторные оценки, изменение охвата или административный характер. Независимый сопоставимый годовой ряд и проверка прогноза вне обучающей выборки отсутствуют.'} for s in sources]
 multivariate={'status':'not_applicable','reason':'Сопоставимая региональная панель содержит один признак: туристические поездки. PCA, кластеризация, корреляционная матрица и Isolation Forest не рассчитываются на искусственно дополненных данных.','features':1,'regions':85,'imputation':False,'pca':None,'clusters':None,'isolation_forest':None}
 analytics={'schema_version':1,'project_id':'tourism','published_at':published,'coverage':coverage,'regional_summaries':summaries,'regional_distributions':summaries,
  'regional_profiles':annual_ranked,'regional_latest':latest,'regional_periods':periods,'regional_reconciliation':reconciliation,'district_summaries':districts,
  'regional_concentration_2025':{'period':'2025-12','regions':len(annual),'total':annual_total,'unit':'млн поездок','top5_share_pct':sum(r['share_pct'] for r in annual_ranked[:5]),'top10_share_pct':sum(r['share_pct'] for r in annual_ranked[:10]),'hhi':sum((r['value']/annual_total)**2 for r in annual),'scope':'distribution_of_published_trips_not_population_access'},
  'national_changes':changes,'same_month_changes':changes,'changes':changes,'forecast_eligibility':forecast,'forecasts':[],
  'targets':targets['items'],'target_comparisons':comparisons,'multivariate':multivariate,'correlations':[],
  'spatial':{'status':'not_recomputed','reason':'Картограмма и территориальные распределения рассчитаны. Исторический Moran I из исследовательского архива не объявляется новым результатом без проверки весов и сопоставимости периода.'},
  'causal':{'status':'not_identified','reason':'Описательные ряды и документальные связи не идентифицируют самостоятельный эффект мер.'},
  'quality_flags':[{'source_id':s['source_id'],'note':s['semantic_note'],'excluded_numeric':s['numeric_count']-s['usable_count']} for s in sources],
  'methodology':{'missing_policy':'Исходные пропуски и нули сохранены. Нули с неустановленным статусом не используются в аналитике и не заменяются выдуманными значениями.','period_policy':'Накопленные оценки не суммируются по месяцам. Декабрьские ссылки отделены от независимых годовых наблюдений.','target_policy':targets.get('version_policy'),'geography_policy':'Собственная опубликованная национальная величина сохраняется отдельно от суммы регионов.'},
  'reproduction':{'commands':['python scripts/import_tourism_release.py --from-inputs','python scripts/build_tourism_documentary.py','python scripts/build_tourism_analytics.py'],'network_required':False}}
 atomic(data/'statistics.json',stats);atomic(data/'analytics.json',analytics)
 atomic(data/'indicators.json',{'schema_version':1,'project_id':'tourism','as_of':STATISTICAL_AS_OF,'origin_policy':'Pinned current-source snapshot with reviewed semantic mapping; original catalog linkage retained per item.','items':registry})
 atomic(data/'context.json',{'schema_version':1,'project_id':'tourism','kind':'single_project_regional_indicator','profiles':annual_ranked,'note':multivariate['reason']})
 csv_write(downloads/'observations.csv',allrows);csv_write(downloads/'registry.csv',registry);csv_write(downloads/'target_comparisons.csv',comparisons);csv_write(downloads/'regional_2025.csv',annual_ranked);csv_write(downloads/'regional_latest.csv',latest);csv_write(downloads/'regional_reconciliation.csv',reconciliation);csv_write(downloads/'districts_2025.csv',districts);csv_write(downloads/'national_changes.csv',changes)
 (downloads/'observations_snapshot.csv.gz').write_bytes((root/'inputs/tourism/statistics/observations_snapshot.csv.gz').read_bytes())
 atomic(root/'documentation/TOURISM_STATISTICAL_AUDIT.json',{'coverage':coverage,'regional_reconciliation':reconciliation,'annual_comparisons':comparisons,'independent_forecasts':False,'pca_performed':False,'clustering_performed':False})
 files=download_records(root/'public/downloads/projects/tourism', root/'public')
 atomic(data/'data-downloads.json',{'schema_version':1,'files':files})
 print(json.dumps({'coverage':coverage,'target_comparisons':len(comparisons),'regional_periods':len(periods),'reconciled_periods':sum(r['equal'] for r in reconciliation)},ensure_ascii=False));return analytics

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args();build(a.root)
