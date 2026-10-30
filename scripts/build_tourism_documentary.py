#!/usr/bin/env python3
"""Recalculate Tourism passport plans, structural links and fixed-corpus text results."""
from pathlib import Path
from decimal import Decimal
import argparse, collections, hashlib, json, shutil, zipfile
from extract_tourism_passports import parse_passport, norm
from tourism_data import ROOT, DATA, MAPPING, atomic, csv_write, sha256, load
from tourism_text import build_text

PROJECT='tourism';YEARS=list(range(2025,2031))
NAMES={'П':'Туризм и гостеприимство','П1':'Создание номерного фонда, инфраструктуры и новых точек притяжения','П2':'Пять морей и озеро Байкал','П3':'Туристическая привлекательность страны','П4':'Кадры для туризма','П5':'Производство отечественной продукции для туристской индустрии'}
TITLE_MAP={
 'Количество туристических поездок по территории Российской Федерации':('2.14.П.2','62900'),
 'Доля туристской отрасли в валовом внутреннем продукте':('2.14.П.3','62903'),
 'Объем экспорта туристских услуг':('2.14.П.1','62902'),
 'Количество номеров в классифицированных средствах размещения':('2.14.П1.1','62159'),
 'Число поездок в новые современные круглогодичные гостиничные комплексы':('2.14.П2.1',None),
 'Численность иностранных граждан, размещенных в коллективных средствах размещения':('2.14.П3.1','63347'),
 'Индекс удовлетворенности граждан в сфере туризма и гостеприимства':('2.14.П3.2',None),
 'Число посещений Национального туристического портала':('2.14.П3.3',None),
 'Доля прошедших обучение по программам переподготовки и повышения квалификации по направлению "деятельность гостиниц и предприятий общественного питания" в численности занятых в отрасли туризма':('2.14.П4.1',None),
 'Число специалистов, прошедших переподготовку и повышение квалификации по виду экономической деятельности "деятельность гостиниц и предприятий общественного питания" в центрах подготовки кадров для туристской индустрии':('П04611-П4',None),
 'Обеспеченность туристской индустрии отечественной промышленной продукцией':('2.14.П5.1','62780')}
UNITS={'Миллион штук':'млн поездок','Миллион человек':'млн человек','Тысяча номеров':'тыс. номеров','Процент':'%','Миллиард долларов':'млрд долл. США','Человек':'чел.','Миллион единиц':'млн единиц'}
FINANCE_NOTE='Сумма опубликованных финансовых строк включает федеральные и региональные записи, между которыми возможен повторный учёт трансфертов. Она не является консолидированным ресурсом, кассовым расходом или оценкой эффекта. Полная сопоставимая сумма исключаемых трансфертов текущей редакции не раскрыта.'

def build(root=ROOT):
 root=Path(root);folder=root/'inputs/tourism/documentary';out=root/'public/downloads/projects/tourism/documentary';out.mkdir(parents=True,exist_ok=True);data=root/DATA
 manifest=load(folder/'source_manifest.json');archive=root/manifest['archive_path'];assert sha256(archive)==manifest['archive_sha256']
 docs=[]
 with zipfile.ZipFile(archive) as z:
  for meta in manifest['documents']:
   if meta['project_id']!=PROJECT:continue
   raw=z.read(meta['archive_entry']);assert hashlib.sha256(raw).hexdigest()==meta['sha256']
   p=root/'public'/meta['download_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
   docs.append(parse_passport(raw,meta))
 assert len(docs)==6
 atomic(folder/'parsed_tourism_passports.json',docs)
 nodes=[n for d in docs for n in d['nodes']];results=[n for n in nodes if n['kind']=='result'];indicators=[n for n in nodes if n['kind']=='indicator'];tasks=[n for n in nodes if n['kind']=='task'];goals=[n for n in nodes if n['kind']=='goal']
 assert (len(results),len(indicators),len(tasks),len(goals))==(31,14,20,6)
 structural=[]
 for result in results:
  for indicator in indicators:
   if result.get('task_node_id') and result['task_node_id']==indicator.get('task_node_id'):
    structural.append({'id':result['node_id']+'__'+indicator['node_id'],'source_node_id':result['node_id'],'target_node_id':indicator['node_id'],
     'result_node_id':result['node_id'],'indicator_node_id':indicator['node_id'],'result_title':result['title'],'indicator_title':indicator['title'],
     'document_id':result['document_id'],'fp':result['fp'],'task_node_id':result['task_node_id'],'task_title':result.get('task_text'),
     'evidence_class':'shared_documented_task','source_url':result['source_url'],'source_sha256':result['source_sha256'],
     'result_locator':result['source_locator'],'indicator_locator':indicator['source_locator'],'task_locator':result.get('task_source_locator'),
     'official_weight':None,'causal_status':'not_identified'})
 claims=[n for d in docs for n in d['unresolved_weight_claims']]
 assert len(structural)==49 and len(claims)==73
 text,lexical=build_text(folder,manifest['documents'],docs,out,data)
 for row in structural+lexical:
  row['result_id']=row['result_node_id'];row['indicator_id']=row['indicator_node_id']
 for row in claims:
  row['result_id']=row['result_node_id'];row['indicator_title']='Адресат не установлен';row['claim_text']=str(row.get('value_raw',''))
 for row in text['documents']:row['token_count']=row['profile_token_count']
 for row in text['topTerms']:row['document']=row['document_id']
 assert len(lexical)==20
 cards=[{**t,'source_version':d['document']['publisher_version'],'publication_date':d['document']['publication_date'],'document_level':d['document']['document_level']} for d in docs for t in d['targets']]
 canonical={}
 for card in sorted(cards,key=lambda c:(c['document_level']!='national',c['document_id'],c['source_locator'])):canonical.setdefault(norm(card['title']),card)
 assert len(canonical)==11
 mapping={norm(k):v for k,v in TITLE_MAP.items()};items=[]
 for card in canonical.values():
  assert norm(card['title']) in mapping,card['title']
  code,sid=mapping[norm(card['title'])]
  items.append({**card,'indicator_code':code,'code':code,'source_id':sid,'passport_unit':card['unit'],'unit':UNITS.get(card['unit'],card['unit']),
   'years':{str(y):card['years'].get(str(y)) for y in YEARS},'mapping_status':'reviewed_definition_and_unit_match' if sid else 'no_verified_numeric_source',
   'mapping_note':'Физическая публикация 63347 сопоставлена с собственным показателем иностранных размещений. Связь каталога с экспортным прокси сохранена отдельно.' if sid=='63347' else 'Паспортная цель выбранной редакции. Срок публикации не является датой утверждения.',
   'target_is_proxy':False,'basis':'passport_plan_selected_edition','additional_to_statistical_catalog':code=='П04611-П4'})
 targets={'project_id':PROJECT,'documentary_snapshot':'2026-10-16','basis':'single_source_edition_per_card','items':items,'allCards':cards,
  'source_card_count':14,'unique_indicator_count':11,'statistical_catalog_count':10,'target_cells':len(items)*6,
  'numeric_targets':sum(v is not None for item in items for v in item['years'].values()),'missing_targets':sum(v is None for item in items for v in item['years'].values()),
  'version_policy':'Редакция опубликована 16.10.2026. Сопоставление с 2025 годом ретроспективное, исходные обязательства начала 2025 года этим не восстанавливаются.'}
 atomic(data/'targets.json',targets)
 finance_records=[r for d in docs for r in d['finance_records']]
 document_rows=[r for r in finance_records if r['scope']=='document'];np_rows=[r for r in document_rows if r['fp']=='П' and r['year'] in YEARS]
 def amount(rows):return sum((Decimal(r['amount_decimal']) for r in rows if r['amount_decimal'] is not None),Decimal(0))
 total=amount(np_rows);assert total==Decimal('1787964010.59')
 projects=[]
 for d in sorted((d for d in docs if d['document']['code']!='П'),key=lambda d:d['document']['code']):
  meta=d['document'];source=[r for r in document_rows if r['document_id']==meta['document_id']];selected=[r for r in source if r['year'] in YEARS];subtotal=amount(selected)
  years=[]
  for y in YEARS:
   cells=[r for r in selected if r['year']==y];v=amount(cells) if cells else None
   years.append({'year':y,'amountThousandRub':float(v) if v is not None else None,'amountBillionRub':float(v/Decimal(1000000)) if v is not None else None,'amountDecimal':str(v) if v is not None else None,'known_components':len(cells),'source_locators':[r['source_locator'] for r in cells],'status':'published_arithmetic_sum' if cells else 'not_published','source_url':meta['url']})
  beyond=amount([r for r in source if r['year']>2030])
  projects.append({'code':meta['code'],'fp':meta['code'],'name':NAMES[meta['code']],'document_id':meta['document_id'],'source_url':meta['url'],'source_sha256':meta['sha256'],'source_version':meta['publisher_version'],
   'totalThousandRub':float(subtotal),'totalBillionRub':float(subtotal/Decimal(1000000)),'totalDecimal':str(subtotal),'share':float(subtotal/total),'sharePct':float(subtotal/total*100),
   'years':years,'outsideHorizonThousandRub':float(beyond),'totalMeaning':'arithmetic_sum_of_published_rows_not_consolidated','missingYears':[y['year'] for y in years if y['amountThousandRub'] is None],
   'note':'Отдельная строка 2025 года не опубликована. Ноль не подставлен. Сумма раскрытых строк 2026–2030 совпадает с заголовочным итогом.' if meta['code']=='П5' else 'Суммы после 2030 года исключены из сопоставимого горизонта.'})
 assert sum(Decimal(p['totalDecimal']) for p in projects)==total
 year_totals=[]
 for y in YEARS:
  cells=[r for r in np_rows if r['year']==y];v=amount(cells);fp_values=[next(k for k in p['years'] if k['year']==y)['amountThousandRub'] for p in projects]
  year_totals.append({'year':y,'totalThousandRub':float(v),'totalBillionRub':float(v/Decimal(1000000)),'totalDecimal':str(v),
   'hhi':sum((x/float(v))**2 for x in fp_values) if all(x is not None for x in fp_values) and v else None,
   'hhi_status':'conditional_structure_of_arithmetic_sum' if all(x is not None for x in fp_values) else 'not_calculated_missing_p5_2025',
   'source_components':[{'name':r['source'],'amountThousandRub':r['amount_thousand_rub'],'amountBillionRub':r['amount_thousand_rub']/1e6,'source_locator':r['source_locator']} for r in cells],
   'meaning':'arithmetic_sum_not_consolidated','source_url':'https://databudget.ru/projects/np/26'})
 source_totals=[]
 for name in sorted({r['source'] for r in np_rows}):
  selected=[r for r in np_rows if r['source']==name];v=amount(selected)
  source_totals.append({'name':name,'totalThousandRub':float(v),'totalBillionRub':float(v/Decimal(1000000)),'totalDecimal':str(v),'additive_after_transfer_elimination_only':True,'years':selected})
 finance={'unit':'тыс. руб.','periods':YEARS,'totalThousandRub':float(total),'totalBillionRub':float(total/Decimal(1000000)),'totalDecimal':str(total),
  'totalMeaning':'arithmetic_sum_of_published_rows_not_consolidated','consolidatedTotalThousandRub':None,'consolidationStatus':'unavailable_complete_comparable_transfer_elimination',
  'projects':projects,'yearTotals':year_totals,'hhi':[{'year':r['year'],'value':r['hhi'],'status':r['hhi_status']} for r in year_totals],'sourceRows':np_rows,'sourceTotals':source_totals,'resultRows':[r for r in finance_records if r['scope']=='result'],
  'outsideHorizonThousandRub':sum(p['outsideHorizonThousandRub'] for p in projects),'caveat':FINANCE_NOTE,
  'shareMeaning':'Условные доли в арифметической сумме опубликованных строк','hhiMeaning':'Условная концентрация раскрытой арифметической суммы, не концентрация чистых бюджетных расходов'}
 counts={'results':31,'tasks':20,'indicatorCards':14,'uniqueIndicators':11,'goals':6,'structuralPairs':49,'structuralResults':31,'structuralIndicatorCards':11,'ambiguousClaims':73,'resolvedDirectLinks':0,'lexicalPairs':20,'lexicalResults':13,'lexicalIndicators':9,'resultsWithoutLexicalCandidate':18}
 network={'nodes':nodes,'structuralPairs':structural,'ambiguousClaims':claims,'lexicalPairs':lexical,'counts':counts,'summary':counts,
  'note':'Общая задача фиксирует документальную принадлежность. Неоднозначные записи прямого влияния и лексические кандидаты не получают причинной интерпретации.','officialDirectWeightsUsed':False}
 sources=[{**d['document'],'download_url':d['document']['download_path'],'qualification':'Вторичное HTML-представление паспорта. Дата обновления сервиса не удостоверяет дату утверждения.'} for d in docs]
 pdf_manifest=folder/'pdf_sources.json'
 if pdf_manifest.exists():sources+=load(pdf_manifest)
 csv_write(out/'finance_project_years.csv',[{'code':p['code'],'name':p['name'],**y} for p in projects for y in p['years']])
 csv_write(out/'finance_source_rows.csv',np_rows);csv_write(out/'finance_all_source_rows.csv',finance_records);csv_write(out/'finance_year_totals.csv',year_totals)
 csv_write(out/'network_nodes.csv',nodes);csv_write(out/'network_shared_tasks.csv',structural);csv_write(out/'network_ambiguous_claims.csv',claims);csv_write(out/'network_lexical_candidates.csv',lexical)
 csv_write(out/'targets.csv',[{**{k:v for k,v in t.items() if k not in ('years','raw_years','metadata')},'year':year,'target':value} for t in items for year,value in t['years'].items()])
 csv_write(out/'sources.csv',sources)
 with zipfile.ZipFile(out/'documentary_sources.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted((out/'sources').glob('*')):z.write(p,p.name)
 result={'meta':{'schema_version':1,'project_id':PROJECT,'documentary_snapshot':'2026-10-16','prepared_at':'2026-10-29','sources':len(sources),'structured_passports':6,'corpus_documents':137,'comparable_text_projects':10,'source_kind':'secondary_epbs_rendering','input_archive_sha256':manifest['archive_sha256'],'full_export_url':'downloads/projects/tourism/documentary/documentary_full.json'},
  'finance':finance,'network':network,'text':text,'targets':targets,'sources':sources,'downloads':{'full':'downloads/projects/tourism/documentary/documentary_full.json','source_archive':'downloads/projects/tourism/documentary/documentary_sources.zip','finance':'downloads/projects/tourism/documentary/finance_project_years.csv','targets':'downloads/projects/tourism/documentary/targets.csv','network':'downloads/projects/tourism/documentary/network_shared_tasks.csv','lexical':'downloads/projects/tourism/documentary/network_lexical_candidates.csv'}}
 atomic(out/'documentary_full.json',result);atomic(data/'documentary.json',result)
 atomic(root/'documentation/TOURISM_DOCUMENTARY_AUDIT.json',{'project_id':PROJECT,'sources':len(sources),'counts':counts,'text_numeric_checks':text['replicationAudit'],'finance_sum_decimal':str(total),'finance_is_consolidated':False,'target_cards':14,'target_unique':11,'target_numeric_cells':targets['numeric_targets'],'target_missing_cells':targets['missing_targets']})
 print(json.dumps({'sources':len(sources),'nodes':len(nodes),'structural_pairs':49,'ambiguous_claims':73,'lexical_pairs':20,'finance_arithmetic_thousand_rub':str(total),'target_unique':11}));return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args();build(a.root)
