#!/usr/bin/env python3
"""Recalculate preserved Transport passports, arithmetic plans and documentary/text links."""
from pathlib import Path
from decimal import Decimal
import argparse,hashlib,json,re,zipfile
from extract_transport_passports import parse_passport,norm
from transport_data import ROOT,DATA,MAPPING,atomic,csv_write,sha256,load
from transport_text import build_text
PROJECT='efficient_transport';YEARS=list(range(2025,2031))
NAMES={'Т':'Эффективная транспортная система','Т1':'Высокоскоростные железнодорожные магистрали','Т2':'Развитие Большого Северного морского пути','Т3':'Развитие опорной сети железных дорог','Т4':'Развитие опорной сети морских портов','Т5':'Развитие внутренних водных путей','Т6':'Развитие опорной сети аэродромов','Т7':'Развитие пунктов пропуска через государственную границу','Т8':'Цифровая трансформация транспортной отрасли','Т9':'Развитие кадрового потенциала транспортной отрасли'}
FINANCE_NOTE='Арифметическая сумма опубликованных плановых строк. Согласованность сумм не подтверждает договорное обеспечение ресурсов и не исключает повторное отражение межбюджетных перечислений. Внебюджетная строка не равнозначна расходам частного сектора. Консолидированный ресурс и исполненные расходы отдельно не установлены.'
def title_key(value):
 return re.sub(r'[^а-яa-z0-9]+','',norm(re.sub(r'\s*\(Т\d+\)$','',value)))

def build(root=ROOT):
 root=Path(root);folder=root/'inputs/efficient_transport/documentary';out=root/'public/downloads/projects/efficient_transport/documentary';out.mkdir(parents=True,exist_ok=True);data=root/DATA
 manifest=load(folder/'source_manifest.json');archive=root/manifest['archive_path'];assert sha256(archive)==manifest['archive_sha256'];docs=[]
 with zipfile.ZipFile(archive) as z:
  for meta in manifest['documents']:
   if meta['project_id']!=PROJECT:continue
   raw=z.read(meta['archive_entry']);assert hashlib.sha256(raw).hexdigest()==meta['sha256'];p=root/'public'/meta['download_path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);d=parse_passport(raw,meta);d['document']['download_path']=meta['download_path'];docs.append(d)
 assert len(docs)==10
 atomic(folder/'parsed_transport_passports.json',docs)
 nodes=[n for d in docs for n in d['nodes']];results=[n for n in nodes if n['kind']=='result'];indicators=[n for n in nodes if n['kind']=='indicator'];tasks=[n for n in nodes if n['kind']=='task'];goals=[n for n in nodes if n['kind']=='goal']
 assert (len(results),len(indicators),len(tasks),len(goals))==(30,25,27,10)
 structural=[]
 for result in results:
  for indicator in indicators:
   if result.get('task_node_id') and result['task_node_id']==indicator.get('task_node_id'):
    structural.append({'id':result['node_id']+'__'+indicator['node_id'],'source_node_id':result['node_id'],'target_node_id':indicator['node_id'],'result_node_id':result['node_id'],'indicator_node_id':indicator['node_id'],'result_title':result['title'],'indicator_title':indicator['title'],'document_id':result['document_id'],'fp':result['fp'],'task_node_id':result['task_node_id'],'task_title':result.get('task_text'),'evidence_class':'shared_documented_task','source_url':result['source_url'],'source_sha256':result['source_sha256'],'result_locator':result['source_locator'],'indicator_locator':indicator['source_locator'],'task_locator':result.get('task_source_locator'),'official_weight':None,'causal_status':'not_identified'})
 claims=[n for d in docs for n in d['unresolved_weight_claims']];assert len(structural)==54 and len(claims)==42
 text,lexical=build_text(folder,manifest['documents'],docs,out,data)
 for row in structural+lexical:row['result_id']=row['result_node_id'];row['indicator_id']=row['indicator_node_id']
 for row in claims:row['result_id']=row['result_node_id'];row['indicator_title']='Адресат не установлен';row['claim_text']=str(row.get('value_raw',''))
 for row in text['documents']:row['token_count']=row['profile_token_count']
 for row in text['topTerms']:row['document']=row['document_id']
 assert len(lexical)==36
 cards=[{**t,'source_version':d['document']['publisher_version'],'publication_date':d['document']['publication_date'],'document_level':d['document']['document_level']} for d in docs for t in d['targets']]
 canonical={}
 for card in sorted(cards,key=lambda c:(c['document_level']!='national',c['document_id'],c['source_locator'])):canonical.setdefault(norm(card['title']),card)
 assert len(canonical)==22
 catalog=load(root/'inputs/efficient_transport/statistics/catalog_original.json')['items'];mapping={title_key(r['indicator_name']):(r['indicator_code'],r['source_ids'][0] if r['source_ids'] else None) for r in catalog};items=[]
 for card in canonical.values():
  key=title_key(card['title']);assert key in mapping,card['title'];code,sid=mapping[key]
  items.append({**card,'indicator_code':code,'code':code,'source_id':sid,'passport_unit':card['unit'],'unit':card['unit'],'years':{str(y):card['years'].get(str(y)) for y in YEARS},'mapping_status':'reviewed_definition_and_unit_match','mapping_note':'Цель выбранной редакции 16.10.2026. Дата обновления страницы не равна дате утверждения. Исторические обязательства 2025 года данной версией не восстанавливаются.','target_is_proxy':False,'basis':'passport_plan_selected_edition','additional_to_statistical_catalog':False,'direction':'lower_is_better' if sid=='62850' else 'higher_is_better_or_defined_state','annual_comparison_eligible':sid not in {'63268','63269'}})
 targets={'project_id':PROJECT,'documentary_snapshot':'2026-10-16','basis':'single_source_edition_per_card','items':items,'allCards':cards,'source_card_count':25,'unique_indicator_count':22,'statistical_catalog_count':24,'target_cells':len(items)*6,'numeric_targets':sum(v is not None for t in items for v in t['years'].values()),'missing_targets':sum(v is None for t in items for v in t['years'].values()),'version_policy':'Редакция опубликована 16.10.2026. Сопоставление с 2025 годом ретроспективное. Для Т1 горизонт заканчивается в 2028 году. Отсутствующие цели 2029–2030 и Азово-Черноморская цель 2025 года не заменены нулём.'}
 atomic(data/'targets.json',targets)
 records=[r for d in docs for r in d['finance_records']];document_rows=[r for r in records if r['scope']=='document'];np_rows=[r for r in document_rows if r['fp']=='Т' and r['year'] in YEARS]
 def amount(rows):return sum((Decimal(r['amount_decimal']) for r in rows if r['amount_decimal'] is not None),Decimal(0))
 total=amount(np_rows);assert total==Decimal('7622134021.13');projects=[]
 for d in sorted((d for d in docs if d['document']['code']!='Т'),key=lambda d:d['document']['code']):
  meta=d['document'];source=[r for r in document_rows if r['document_id']==meta['document_id']];selected=[r for r in source if r['year'] in YEARS];subtotal=amount(selected);years=[]
  for y in YEARS:
   cells=[r for r in selected if r['year']==y];v=amount(cells) if cells else None
   years.append({'year':y,'amountThousandRub':float(v) if v is not None else None,'amountBillionRub':float(v/Decimal(1000000)) if v is not None else None,'amountDecimal':str(v) if v is not None else None,'known_components':len(cells),'source_locators':[r['source_locator'] for r in cells],'status':'published_arithmetic_sum' if cells else 'outside_passport_horizon' if meta['code']=='Т1' and y>2028 else 'not_published','source_url':meta['url']})
  projects.append({'code':meta['code'],'fp':meta['code'],'name':NAMES[meta['code']],'document_id':meta['document_id'],'source_url':meta['url'],'source_sha256':meta['sha256'],'source_version':meta['publisher_version'],'totalThousandRub':float(subtotal),'totalBillionRub':float(subtotal/Decimal(1000000)),'totalDecimal':str(subtotal),'share':float(subtotal/total),'sharePct':float(subtotal/total*100),'years':years,'outsideHorizonThousandRub':float(amount([r for r in source if r['year']>2030])),'totalMeaning':'arithmetic_sum_of_published_rows_not_consolidated','missingYears':[r['year'] for r in years if r['amountThousandRub'] is None],'passportHorizon':[2025,2028 if meta['code']=='Т1' else 2030],'note':'Паспортный горизонт заканчивается в 2028 году. Отсутствующие строки 2029–2030 не являются нулевыми инвестициями во всю сферу высокоскоростного сообщения.' if meta['code']=='Т1' else 'Сумма опубликованных строк выбранной версии.'})
 assert sum(Decimal(p['totalDecimal']) for p in projects)==total
 yearly=[];reconciliation=[]
 for y in YEARS:
  cells=[r for r in np_rows if r['year']==y];v=amount(cells);fp_values=[next(k for k in p['years'] if k['year']==y)['amountThousandRub'] for p in projects];fp_decimal=amount([r for r in document_rows if r['fp']!='Т' and r['year']==y]);assert fp_decimal==v
  yearly.append({'year':y,'totalThousandRub':float(v),'totalBillionRub':float(v/Decimal(1000000)),'totalDecimal':str(v),'hhi':sum((x/float(v))**2 for x in fp_values if x is not None) if v else None,'hhi_status':'conditional_concentration_of_published_rows_excluding_outside_horizon_cells','source_components':[{'name':r['source'],'amountThousandRub':r['amount_thousand_rub'],'amountBillionRub':r['amount_thousand_rub']/1e6,'source_locator':r['source_locator']} for r in cells],'meaning':'arithmetic_sum_not_consolidated','source_url':'https://databudget.ru/projects/np/20','outsideHorizonProjects':['Т1'] if y>2028 else []})
  for r in cells:
   fp_value=amount([t for t in document_rows if t['fp']!='Т' and t['year']==y and t['source']==r['source']]);expected=Decimal(r['amount_decimal']);assert fp_value==expected
   reconciliation.append({'year':y,'source':r['source'],'nationalDecimal':str(expected),'federalProjectSumDecimal':str(fp_value),'differenceDecimal':str(fp_value-expected),'equal':True})
 source_totals=[]
 for name in sorted({r['source'] for r in np_rows}):
  rows=[r for r in np_rows if r['source']==name];v=amount(rows);source_totals.append({'name':name,'totalThousandRub':float(v),'totalBillionRub':float(v/Decimal(1000000)),'totalDecimal':str(v),'sharePct':float(v/total*100),'additive_after_transfer_elimination_only':True,'years':rows})
 finance={'unit':'тыс. руб.','periods':YEARS,'totalThousandRub':float(total),'totalBillionRub':float(total/Decimal(1000000)),'totalDecimal':str(total),'totalMeaning':'arithmetic_sum_of_published_rows_not_consolidated','consolidatedTotalThousandRub':None,'consolidationStatus':'unavailable_complete_comparable_transfer_elimination','projects':projects,'yearTotals':yearly,'hhi':[{'year':r['year'],'value':r['hhi'],'status':r['hhi_status']} for r in yearly],'totalHhi':sum(p['share']**2 for p in projects),'sourceRows':np_rows,'sourceTotals':source_totals,'resultRows':[r for r in records if r['scope']=='result'],'sourceReconciliation':reconciliation,'allSourcesReconciled':all(r['equal'] for r in reconciliation),'outsideHorizonThousandRub':sum(p['outsideHorizonThousandRub'] for p in projects),'caveat':FINANCE_NOTE,'shareMeaning':'Доли в арифметической сумме опубликованных плановых строк','hhiMeaning':'Концентрация раскрытого финансового плана. Не концентрация консолидированных расходов. Т1 после 2028 года исключён из множества действующих плановых строк.','twoRailProjectsSharePct':sum(p['sharePct'] for p in projects if p['code'] in ['Т1','Т3']),'lateYearsSharePct':sum(r['totalThousandRub'] for r in yearly if r['year']>=2027)/float(total)*100}
 counts={'results':30,'tasks':27,'indicatorCards':25,'uniqueIndicators':22,'goals':10,'structuralPairs':54,'structuralResults':len({r['result_node_id'] for r in structural}),'structuralIndicatorCards':len({r['indicator_node_id'] for r in structural}),'ambiguousClaims':42,'resolvedDirectLinks':0,'lexicalPairs':36,'lexicalResults':17,'lexicalIndicators':len({r['indicator_node_id'] for r in lexical}),'authorReportedLexicalIndicators':16,'resultsWithoutLexicalCandidate':13}
 network={'nodes':nodes,'structuralPairs':structural,'ambiguousClaims':claims,'lexicalPairs':lexical,'counts':counts,'summary':counts,'candidateThresholds':text['candidateThresholds'],'note':'Общая задача фиксирует документальную принадлежность. Неоднозначные утверждения и лексические кандидаты не устанавливают причинное влияние. Автор сообщает 16 уникальных показателей у 36 лексических пар. Детерминированное разрешение равных коэффициентов по идентификатору узла даёт 15, порядок карточек источника – 16. Число пар и охват 17 результатов сохраняются.','officialDirectWeightsUsed':False}
 sources=[{**d['document'],'download_url':d['document']['download_path'],'qualification':'Вторичное HTML-представление паспорта. Дата обновления сервиса не удостоверяет дату утверждения.'} for d in docs]
 pdf_manifest=folder/'pdf_sources.json'
 if pdf_manifest.exists():sources+=load(pdf_manifest)
 for name,rows in [('finance_project_years',[{'code':p['code'],'name':p['name'],**y} for p in projects for y in p['years']]),('finance_source_rows',np_rows),('finance_all_source_rows',records),('finance_year_totals',yearly),('finance_source_reconciliation',reconciliation),('network_nodes',nodes),('network_shared_tasks',structural),('network_ambiguous_claims',claims),('network_lexical_candidates',lexical),('network_thresholds',text['candidateThresholds']),('sources',sources)]:csv_write(out/(name+'.csv'),rows)
 csv_write(out/'targets.csv',[{**{k:v for k,v in t.items() if k not in ('years','raw_years','metadata')},'year':year,'target':value} for t in items for year,value in t['years'].items()])
 with zipfile.ZipFile(out/'documentary_sources.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted((out/'sources').glob('*')):z.write(p,p.name)
 result={'meta':{'schema_version':1,'project_id':PROJECT,'documentary_snapshot':'2026-10-16','prepared_at':'2026-10-29','sources':len(sources),'structured_passports':10,'corpus_documents':137,'comparable_text_projects':10,'source_kind':'secondary_epbs_rendering','input_archive_sha256':manifest['archive_sha256'],'full_export_url':'downloads/projects/efficient_transport/documentary/documentary_full.json'},'finance':finance,'network':network,'text':text,'targets':targets,'sources':sources,'downloads':{'full':'downloads/projects/efficient_transport/documentary/documentary_full.json','source_archive':'downloads/projects/efficient_transport/documentary/documentary_sources.zip','finance':'downloads/projects/efficient_transport/documentary/finance_project_years.csv','targets':'downloads/projects/efficient_transport/documentary/targets.csv','network':'downloads/projects/efficient_transport/documentary/network_shared_tasks.csv','lexical':'downloads/projects/efficient_transport/documentary/network_lexical_candidates.csv'}}
 atomic(out/'documentary_full.json',result);atomic(data/'documentary.json',result)
 atomic(root/'documentation/TRANSPORT_DOCUMENTARY_AUDIT.json',{'project_id':PROJECT,'sources':len(sources),'counts':counts,'text_numeric_checks':text['replicationAudit'],'finance_sum_decimal':str(total),'finance_is_consolidated':False,'finance_source_reconciliation':reconciliation,'target_cards':25,'target_unique':22,'target_numeric_cells':targets['numeric_targets'],'target_missing_cells':targets['missing_targets']})
 print(json.dumps({'sources':len(sources),'nodes':len(nodes),'structural_pairs':54,'ambiguous_claims':42,'lexical_pairs':36,'finance_arithmetic_thousand_rub':str(total),'target_unique':22}));return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args();build(a.root)
