#!/usr/bin/env python3
"""Reproduce Health Technologies plans, document structure and text diagnostics.

Inputs are byte-pinned public passport renderings and separately attributed source
transcriptions. No network request, regional imputation or causal model is run.
"""
from pathlib import Path
from decimal import Decimal
import argparse,collections,csv,gzip,hashlib,json,math,re,shutil,zipfile
from extract_healthtech_passports import parse_passport,decimal,norm,ws,TOKEN_RE

APP=Path(__file__).resolve().parents[1]
PROJECT='health_technologies'
REL=f'downloads/projects/{PROJECT}/documentary/'
YEARS=list(range(2025,2031))
NAMES={'family':'Семья','personnel':'Кадры','youth_children':'Молодёжь и дети','long_active_life':'Продолжительная и активная жизнь','health_technologies':'Новые технологии сбережения здоровья','life_infrastructure':'Инфраструктура для жизни','environment':'Экологическое благополучие','data_economy':'Экономика данных и цифровая трансформация государства','competitive_economy':'Эффективная и конкурентная экономика','efficient_transport':'Эффективная транспортная система','international_export':'Международная кооперация и экспорт','tourism':'Туризм и гостеприимство'}
def dump(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csv_write(p,rows,columns=None):
 p.parent.mkdir(parents=True,exist_ok=True)
 columns=columns or list(dict.fromkeys(k for row in rows for k in row))
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
  for row in rows:w.writerow({k:json.dumps(row.get(k),ensure_ascii=False) if isinstance(row.get(k),(dict,list)) else row.get(k) for k in columns})
def load(root):
 folder=root/'inputs/healthtech/documentary';manifest=json.loads((folder/'source_manifest.json').read_text());assert sha(folder/'passports.zip')==manifest['archive_sha256']
 docs=[]
 with zipfile.ZipFile(folder/'passports.zip') as z:
  for meta in manifest['documents']:
   raw=z.read(meta['archive_entry']);assert hashlib.sha256(raw).hexdigest()==meta['sha256']
   d=parse_passport(raw,meta);assert d['document']['profile_token_count']==meta['profile_token_count'];docs.append(d)
 return folder,manifest,docs

def build_targets(folder,docs,registry):
 mapping=json.loads((folder/'target_mapping.json').read_text());items=[];records=[];reg={x['indicator_code']:x for x in registry}
 for d in docs:
  for target in d['targets']:
   no=target['card_id'].rsplit('-',1)[-1];code=mapping['mapping'][f"{target['fp']}:{no}"];item=reg[code];unit={'Процент':'%','Единица':'ед.','Миллион рублей':'млн руб.'}.get(target['unit'],target['unit']);years={str(y):target['years'].get(str(y)) for y in YEARS}
   out={'indicator_code':code,'code':code,'source_id':item['source_ids'][0] if len(item['source_ids'])==1 else None,'title':target['title'],'registry_title':item['indicator_name'],'unit':unit,'passport_unit':target['unit'],'years':years,'source_document':target['document_id'],'source_locator':target['source_locator'],'source_url':target['source_url'],'source_sha256':target['source_sha256'],'source_version':d['document']['publisher_version'],'publication_date':d['document']['publication_date'],'source_card_id':target['card_id'],'local_code':target['local_code'],'base_value_raw':target['base_value_raw'],'base_date':target['base_date'],'mapping_status':'reviewed_same_level_definition','mapping_note':mapping.get('mapping_notes',{}).get(code),'unit_note':mapping.get('unit_notes',{}).get(code),'raw_years':target['raw_years'],'origin':'independently_extracted_passport_plan','federal_project_code':None if target['fp']=='С' else target['fp']}
   items.append(out)
   for year,raw in target['raw_years'].items():records.append({'indicator_code':code,'year':int(year),'value':target['years'][year],**raw,'unit':unit,'document_id':target['document_id'],'source_url':target['source_url'],'source_sha256':target['source_sha256'],'source_version':d['document']['publisher_version']})
 items.sort(key=lambda x:[p['indicator_code'] for p in registry].index(x['indicator_code']))
 assert len(items)==21 and len({x['indicator_code'] for x in items})==21
 numeric=sum(v is not None for x in items for v in x['years'].values())
 return {'project_id':PROJECT,'documentary_snapshot':'2026-10-16','basis':'single_source_edition_per_card','items':items,'target_cells':len(items)*6,'numeric_targets':numeric,'missing_targets':len(items)*6-numeric,'version_policy':'Preserve every published annual cell; missing values remain null. Source editions are not merged.','extracted_records_all_years':len(records),'strategicGoals':[]},records

def build_finance(folder,docs):
 allrows=[r for d in docs for r in d['finance_records']];bydoc={d['document']['document_id']:d for d in docs};docrows=[r for r in allrows if r['scope']=='document'];federal=[r for r in docrows if r['fp']!='С'];national=[r for r in docrows if r['fp']=='С']
 assert all(r['source']=='Федеральный бюджет, всего' for r in docrows)
 fpyears=[]
 for d in docs:
  code=d['document']['code']
  if code=='С':continue
  records={r['year']:r for r in federal if r['document_id']==d['document']['document_id']}
  for year in YEARS:
   r=records.get(year);fpyears.append({'fp':code,'code':code,'name':d['document']['title'].split('] ',1)[-1],'year':year,'amount_decimal':r['amount_decimal'] if r else None,'amount_thousand_rub':r['amount_thousand_rub'] if r else None,'amount_billion_rub':float(Decimal(r['amount_decimal'])/Decimal(1000000)) if r else None,'value':r['amount_thousand_rub'] if r else None,'unit':'тыс. руб.','kind':'passport_plan','scope':'published_federal_distribution','source_id':d['document']['document_id'],'source_locator':r['source_locator'] if r else None,'source_url':d['document']['url'],'source_sha256':d['document']['sha256'],'missing_reason':None if r else 'no_published_annual_amount_in_selected_edition'})
 total=sum((Decimal(r['amount_decimal']) for r in federal),Decimal(0));nationaltotal=sum((Decimal(r['amount_decimal']) for r in national),Decimal(0));assert total==nationaltotal==Decimal('16213442.40')
 shares=[]
 for code in sorted({r['fp'] for r in federal}):
  amount=sum((Decimal(r['amount_decimal']) for r in federal if r['fp']==code),Decimal(0));name=next(r['name'] for r in fpyears if r['fp']==code);shares.append({'fp':code,'code':code,'name':name,'amount_thousand_rub':float(amount),'amount_decimal':str(amount),'amount_billion_rub':float(amount/Decimal(1000000)),'share':float(amount/total),'sharePercent':float(100*amount/total),'origin':'recomputed_from_visible_document_plan_rows'})
 reconciliation=[]
 for year in YEARS:
  sr=[r for r in federal if r['year']==year];sv=sum((Decimal(r['amount_decimal']) for r in sr),Decimal(0));nr=next(r for r in national if r['year']==year);nv=Decimal(nr['amount_decimal']);assert sv==nv
  reconciliation.append({'year':year,'federal_thousand_rub':float(sv),'national_thousand_rub':float(nv),'difference_thousand_rub':float(nv-sv),'federal_decimal':str(sv),'national_decimal':str(nv),'difference_decimal':str(nv-sv),'published_federal_count':len(sr),'missing_federal_count':5-len(sr),'source_locator':nr['source_locator'],'source_url':nr['source_url'],'interpretation':'Sum of published annual cells only; missing federal amounts do not establish zero future funding.'})
 detail=[]
 for r in allrows:
  if r['scope']=='result':detail.append({**r,'amount_billion_rub':float(Decimal(r['amount_decimal'])/Decimal(1000000)) if r['amount_decimal'] is not None else None})
 result_sums=[]
 for rid in dict.fromkeys(r['result_id'] for r in detail):
  rr=[r for r in detail if r['result_id']==rid];amount=sum((Decimal(r['amount_decimal']) for r in rr),Decimal(0));result_sums.append({'result_id':rid,'fp':rr[0]['fp'],'title':rr[0]['result_title'],'amount_thousand_rub':float(amount),'amount_decimal':str(amount),'amount_billion_rub':float(amount/Decimal(1000000)),'source_document':rr[0]['document_id'],'source_url':rr[0]['source_url'],'source_locator':rr[0]['source_locator']})
 for code in sorted({r['fp'] for r in federal}):assert sum((Decimal(r['amount_decimal']) for r in detail if r['fp']==code),Decimal(0))==sum((Decimal(r['amount_decimal']) for r in federal if r['fp']==code),Decimal(0))
 budget=json.loads((folder/'budget_bill_author_transcription.json').read_text());brows=[];reserves=[]
 verification=json.loads((folder/'budget_source_verification.json').read_text())
 assert sha(folder/verification['filename'])==verification['sha256']
 from lxml import html
 tree=html.parse(str(folder/verification['filename']));source_table=tree.xpath(verification['source_locator'])[0]
 budget_rows=[]
 for row in source_table.xpath('.//tr'):
  cells=[ws(c.text_content()) for c in row.xpath('./td|./th')]
  if len(cells)==5 and all(decimal(c) is not None for c in cells[1:]):budget_rows.append({'cells':cells,'source_locator':tree.getpath(row)})
 names={
  'Общий объём':'Всего',
  'С1':'Федеральный проект "Управление медицинской наукой"',
  'С2':'Федеральный проект "Технологии разработки медицинских изделий, лекарственных средств и платформ нового поколения"',
  'С3':'Федеральный проект "Биомедицинские и когнитивные технологии будущего"',
  'С4':'Федеральный проект "Регенеративная биомедицина, технологии превентивной медицины, обеспечивающие активное и здоровое долголетие"',
  'С5':'Федеральный проект "Развитие производства наиболее востребованных лекарственных препаратов и медицинских изделий"',
  'Зарезервировано':'Зарезервированные бюджетные ассигнования на реализацию национального проекта'}
 budget_locators={}
 for row in budget['rows'][1:]:
  if row[0] not in names:continue
  source=next(r for r in budget_rows if r['cells'][0]==names[row[0]])
  assert [Decimal(decimal(c)) for c in row[1:]]==[Decimal(decimal(c)) for c in source['cells'][1:]]
  budget_locators[row[0]]=source['source_locator']
 budget.update(verification_status='independently_verified_legal_republication',verified_numeric_cells=28,source_html_sha256=verification['sha256'],source_html_download=REL+verification['filename'],source_table_locator=verification['source_locator'],verified_source_rows=budget_rows)
 for row in budget['rows'][1:]:
  for ix,year in enumerate(range(2026,2030),1):
   value=decimal(row[ix]);brows.append({'code':row[0],'name':row[0],'year':year,'value':float(value),'amount_decimal':value,'unit':'%' if row[0]=='Доля резерва, %' else 'млн руб.','kind':'budget_allocation' if year==2026 else 'budget_bill','status':budget['status_by_year'][str(year)],'source_id':'budget_2027_2029','source_locator':(budget_locators[row[0]]+f'/td[{ix+1}]') if row[0] in budget_locators else 'Расчёт доли резерва по таблице 4.1.15','source_url':budget['source_url'],'origin':budget['verification_status']})
 for year in range(2026,2030):
  totalrow=next(r for r in brows if r['year']==year and r['name']=='Общий объём');reserve=next(r for r in brows if r['year']==year and r['name']=='Зарезервировано');t=Decimal(totalrow['amount_decimal']);rv=Decimal(reserve['amount_decimal']);allocated=t-rv;fp=sum((Decimal(r['amount_decimal']) for r in brows if r['year']==year and re.fullmatch('С[1-5]',r['name'])),Decimal(0));passport=next((Decimal(r['amount_decimal'])/1000 for r in national if r['year']==year),None)
  reserves.append({'year':year,'total_million_rub':float(t),'reserve_million_rub':float(rv),'allocated_million_rub':float(allocated),'reserve_percent':float(rv/t*100),'federal_rows_million_rub':float(fp),'rounding_difference_million_rub':float(t-rv-fp),'passport_million_rub':float(passport) if passport is not None else None,'bill_minus_passport_million_rub':float(t-passport) if passport is not None else None,'residual_after_reserve_million_rub':float(t-passport-rv) if passport is not None else None,'status':totalrow['status'],'source_url':budget['source_url'],'source_locator':verification['source_locator'],'origin':budget['verification_status']})
 return {'unit':'тыс. руб.','periods':YEARS,'totalThousandRub':float(total),'nationalThousandRub':float(nationaltotal),'totalDecimal':str(total),'nationalDecimal':str(nationaltotal),'nationalMinusFederalThousandRub':0,'fpYears':fpyears,'yearTotals':reconciliation,'reconciliation':reconciliation,'federalShares':shares,'hhi':sum(x['share']**2 for x in shares),'resultYears':detail,'resultSums':result_sums,'reserveYears':reserves,'sources':docrows,'sourceRows':allrows,'frames':[{'id':'passport_plan','title':'Паспортное распределение на 2025–2030 годы','unit':'тыс. руб.','periods':YEARS,'rows':fpyears,'source_kind':'secondary_epbs_rendering','edition_date':'2026-10-16'},{'id':'budget_bill','title':'Роспись 2026 года и законопроект 2027–2029 годов','unit':'млн руб.','periods':list(range(2026,2030)),'rows':[r for r in brows if r['unit']=='млн руб.'],'source_kind':'legal_republication','verification_status':budget['verification_status']}],'budgetBill':budget,'notes':['Паспорт содержит опубликованное распределение, общая ресурсная потребность не установлена.','Отсутствующие годовые суммы 2029–2030 не заменяются нулями.','Роспись 2026 года, паспорт и внесённый законопроект представлены как разные документальные основания.','Суммы не характеризуют кассовое исполнение.']}

def build_text(folder,all_docs,selected,output,data_dir):
 import numpy as np
 from sklearn.feature_extraction.text import TfidfVectorizer
 from sklearn.preprocessing import normalize
 from scipy.stats import spearmanr
 from nltk.stem.snowball import RussianStemmer
 cfg=json.loads((folder/'text_parameters.json').read_text());stops=set(cfg['stop_words']);stemmer=RussianStemmer();corpus=['\n'.join(u['text'] for u in d['units']) for d in all_docs]
 def analyzer(stem=False,bigrams=True):
  def run(s):
   features=[]
   for line in s.splitlines():
    tokens=[t for t in TOKEN_RE.findall(norm(line)) if t not in stops]
    if stem:tokens=[stemmer.stem(t) if re.search('[а-я]',t) else t for t in tokens]
    features.extend(tokens)
    if bigrams:features.extend(a+' '+b for a,b in zip(tokens,tokens[1:]))
   return features
  return run
 def model(stem=False,bigrams=True):
  vectorizer=TfidfVectorizer(analyzer=analyzer(stem,bigrams),min_df=1,max_df=.98,sublinear_tf=True,smooth_idf=True,norm='l2',dtype=np.float64);matrix=vectorizer.fit_transform(corpus);return vectorizer,matrix
 vec,matrix=model();sv,sm=model(True);uv,um=model(False,False);projects=sorted(set(d['document']['project_id'] for d in all_docs));indices={p:[i for i,d in enumerate(all_docs) if d['document']['project_id']==p] for p in projects};project_index=projects.index(PROJECT)
 def profiles(mx,mode='all'):
  out=[]
  for p in projects:
   ids=indices[p];npids=[i for i in ids if all_docs[i]['document']['kind']=='np'];fpids=[i for i in ids if all_docs[i]['document']['kind']=='fp']
   if mode=='national':v=np.asarray(mx[npids].mean(axis=0))
   elif mode=='federal':v=np.asarray(mx[fpids].mean(axis=0))
   elif mode=='levels':v=(normalize(np.asarray(mx[npids].mean(axis=0)))+normalize(np.asarray(mx[fpids].mean(axis=0))))/2
   else:v=np.asarray(mx[ids].mean(axis=0))
   out.append(v.ravel())
  return normalize(np.vstack(out))
 variants={name:profiles(mx,mode) for name,mx,mode in [('base',matrix,'all'),('stemming',sm,'all'),('unigrams',um,'all'),('equal_levels',matrix,'levels'),('federal_only',matrix,'federal'),('national_only',matrix,'national')]}
 scores={k:(v@v[project_index]).tolist() for k,v in variants.items()};other=[i for i in range(len(projects)) if i!=project_index]
 similarity=[]
 for i in other:similarity.append({'project_id':projects[i],'project_a':PROJECT,'project_b':projects[i],'name':NAMES[projects[i]],'cosine':scores['base'][i],'stemmed_cosine':scores['stemming'][i],'unigram_cosine':scores['unigrams'][i],'equal_levels_cosine':scores['equal_levels'][i],'federal_only_cosine':scores['federal_only'][i],'national_only_cosine':scores['national_only'][i],'origin':'independently_recomputed_98_passport_corpus'})
 similarity.sort(key=lambda r:-r['cosine'])
 sensitivity=[]
 for k,ss in scores.items():
  order=sorted(other,key=lambda i:-ss[i]);sensitivity.append({'variant':k,'spearman':float(spearmanr([scores['base'][i] for i in other],[ss[i] for i in other]).statistic),'top3':[NAMES[projects[i]] for i in order[:3]],'features':sm.shape[1] if k=='stemming' else um.shape[1] if k=='unigrams' else matrix.shape[1],'origin':'independently_recomputed'})
 health_indices=indices[PROJECT];health_docsim=(matrix[health_indices]@matrix[health_indices].T).toarray();docsim=[]
 for i,a in enumerate(health_indices):
  for j,b in enumerate(health_indices):
   if j<=i:continue
   da,db=all_docs[a]['document'],all_docs[b]['document'];docsim.append({'document_a':da['document_id'],'document_b':db['document_id'],'title_a':da['title'],'title_b':db['title'],'code_a':da['code'],'code_b':db['code'],'cosine':float(health_docsim[i,j]),'origin':'independently_recomputed'})
 names=vec.get_feature_names_out();topterms=[]
 for code,values in [('project',variants['base'][project_index])]+[(all_docs[i]['document']['document_id'],matrix[i].toarray()[0]) for i in health_indices]:
  for rank,i in enumerate(np.argsort(-values)[:30],1):topterms.append({'document_id':code,'rank':rank,'term':str(names[i]),'weight':float(values[i]),'origin':'independently_recomputed'})
 dictionary=json.loads((folder/'theme_dictionary.json').read_text());frames=[{'id':k,'frame':k,'name':v['label'],'label':v['label'],'patterns':v['patterns']} for k,v in dictionary['frames'].items()];frame_scores=[];files={};contexts=[]
 for d in selected:
  doc=d['document'];docctx=[]
  for frame in frames:
   regex=re.compile('|'.join('(?:'+p+')' for p in frame['patterns']));count=0
   for unit in d['units']:
    matches=list(regex.finditer(norm(unit['text'])));count+=len(matches)
    for m in matches:
     row={'id':f'{doc["document_id"]}:kwic{len(docctx)+1}','document_id':doc['document_id'],'frame':frame['id'],'matched':m.group(),'context':unit['text'],'unit_id':unit['unit_id'],'source_locator':unit['source_locator'],'source_sha256':doc['sha256'],'source_url':doc['url'],'origin':'independent_dictionary_match'};docctx.append(row);contexts.append(row)
   frame_scores.append({'document_id':doc['document_id'],'title':doc['title'],'code':doc['code'],'frame':frame['id'],'frame_id':frame['id'],'frame_name':frame['name'],'count':count,'n_tokens':doc['profile_token_count'],'per1000':count/doc['profile_token_count']*1000,'rate_per1000':count/doc['profile_token_count']*1000,'origin':'independent_platform_dictionary'})
  rel=f'data/projects/{PROJECT}/documentary-text/{doc["document_id"]}.json';dump(data_dir/'documentary-text'/f'{doc["document_id"]}.json',{'document':doc,'units':d['units'],'contexts':docctx,'kwic':docctx,'source_url':doc['url'],'source_sha256':doc['sha256']});files[doc['document_id']]=rel
 candidates=[]
 for d in selected:
  results=[n for n in d['nodes'] if n['kind']=='result'];inds=[n for n in d['nodes'] if n['kind']=='indicator']
  if not results or not inds:continue
  rx=vec.transform([r['title']+'\n'+r['description'] for r in results]);ix=vec.transform([r['title'] for r in inds]);cos=(rx@ix.T).toarray()
  for i,r in enumerate(results):
   for j,x in enumerate(inds):candidates.append({'id':r['node_id']+'__'+x['node_id'],'document_id':d['document']['document_id'],'fp':d['document']['code'],'source_node_id':r['node_id'],'target_node_id':x['node_id'],'result_node_id':r['node_id'],'indicator_node_id':x['node_id'],'result_title':r['title'],'indicator_title':x['title'],'cosine':float(cos[i,j]),'weight':float(cos[i,j]),'evidence_class':'semantic_candidate','origin':'independently_recomputed','source_url':d['document']['url'],'result_locator':r['source_locator'],'indicator_locator':x['source_locator'],'official_weight':None})
 author=cfg['author_claims'];checks=[]
 for name,value in [('corpus_documents',len(all_docs)),('corpus_tokens',sum(d['document']['profile_token_count'] for d in all_docs)),('healthtech_tokens',sum(d['document']['profile_token_count'] for d in selected)),('features',matrix.shape[1]),('stemming_features',sm.shape[1]),('unigram_features',um.shape[1])]:checks.append({'metric':name,'author_report':author[name],'platform_recomputed':value,'difference':value-author[name],'equal':value==author[name]})
 result={'documents':[d['document'] for d in selected],'corpusDocuments':[d['document'] for d in all_docs],'sameGenreTokenCount':sum(d['document']['profile_token_count'] for d in selected),'corpusTokenCount':sum(d['document']['profile_token_count'] for d in all_docs),'features':matrix.shape[1],'frames':frames,'frameScores':frame_scores,'documentSimilarity':docsim,'projectSimilarity':similarity,'topTerms':topterms,'sensitivity':sensitivity,'documentFiles':files,'profileCount':len(all_docs),'contextCount':len(contexts),'method':cfg,'dictionary':dictionary,'replicationAudit':checks,'replicationStatus':'independent_reimplementation_with_published_parameters_and_explicit_comparison','authorExactCodeAvailable':False,'notes':['Содержательные поля и полные исходные публикации доступны для повторной проверки.','Авторский список стоп-слов и тематические словари не приложены в полном виде. Независимые параметры платформы опубликованы отдельно.','Несовпадающие авторские и воспроизведённые результаты не заменяют друг друга.','Лексическая близость не измеряет результативность, причинный эффект или долю общих расходов.']}
 csv_write(output/'text_corpus_profiles.csv',[d['document'] for d in all_docs]);csv_write(output/'text_units.csv',[u for d in all_docs for u in d['units']]);csv_write(output/'text_kwic.csv',contexts);csv_write(output/'frame_scores.csv',frame_scores);csv_write(output/'document_similarity.csv',docsim);csv_write(output/'project_similarity.csv',similarity);csv_write(output/'text_sensitivity.csv',sensitivity);csv_write(output/'tfidf_top_terms.csv',topterms);csv_write(output/'text_replication_audit.csv',checks)
 return result,candidates

def official_updates(folder,output):
 mf=folder/'official_updates'/'retrieval.json'
 if not mf.exists():return []
 from lxml import html
 meta=json.loads(mf.read_text());items=meta if isinstance(meta,list) else meta.get('items',meta.get('sources',[]));result=[]
 for item in items:
  name=item.get('file') or item.get('filename') or Path(item.get('local_path','')).name
  if not name:continue
  p=folder/'official_updates'/Path(name).name
  if not p.exists():continue
  tree=html.fromstring(p.read_bytes());title=tree.xpath('//*[contains(@class,"reader_article_headline")]');body=tree.xpath('//*[contains(@class,"reader_article_body")]');date=tree.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," reader_article_dateline__date " )]//text()')
  dest=output/'official_sources'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest)
  date_label=ws(' '.join(date));parts=date_label.split();months={'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12};date_iso=f'{int(parts[2]):04d}-{months[parts[1]]:02d}-{int(parts[0]):02d}';assert date_iso in ['2026-03-27','2026-05-18','2026-07-28']
  result.append({**item,'title':ws(title[0].text_content()) if title else None,'publication_date':date_iso,'publication_label':date_label,'text':ws(body[0].text_content()) if body else None,'sha256':sha(p),'download_path':REL+'official_sources/'+p.name,'source_kind':'official_government_publication','interpretation':'Published counts retain their period, object and stage; they are not substituted into EMISS series.'})
 return result

def build(root=APP,verify=False):
 folder,manifest,all_docs=load(root);selected=[d for d in all_docs if d['document']['project_id']==PROJECT];registry=json.loads((root/f'public/data/projects/{PROJECT}/indicators.json').read_text())['items'];data_dir=root/f'public/data/projects/{PROJECT}';output=root/'public'/REL;output.mkdir(parents=True,exist_ok=True)
 targets,targetrecords=build_targets(folder,selected,registry);finance=build_finance(folder,selected);text,candidates=build_text(folder,all_docs,selected,output,data_dir)
 nodes=[n for d in selected for n in d['nodes']];claims=[n for d in selected for n in d['unresolved_weight_claims']];assert len(claims)==69 and len(candidates)==83
 assert len({n['node_id'] for n in nodes})==len(nodes), 'Repeated source HTML IDs must not merge distinct cards'
 assert sum(n['kind']=='result' for n in nodes)==28
 assert len({r['id'] for r in candidates})==len(candidates)
 shared=[{k:v for k,v in r.items() if k not in ['cosine','weight','evidence_class','origin']}|{'evidence_class':'same_federal_project_candidate','origin':'administrative_cross_product_not_causal'} for r in candidates]
 network={'nodes':nodes,'unresolvedClaims':claims,'reviewedEdges':[],'directLinks':[],'edges':[],'sharedTaskPairs':shared,'semanticCandidates':candidates,'summary':{'results':sum(n['kind']=='result' for n in nodes),'indicators':sum(n['kind']=='indicator' for n in nodes),'unresolved_weight_claims':len(claims),'reviewed_direct_links':0,'shared_task_pairs':len(shared),'semantic_candidates':len(candidates)},'notes':['69 опубликованных записей влияния не позволяют однозначно определить адресуемый показатель.','83 пары являются всеми сочетаниями результатов и показателей внутри соответствующего ФП.','Косинус используется для выбора текстов для проверки, без присвоения причинной силы.']}
 updates=official_updates(folder,output)
 supplemental=[{'title':'Пояснительная записка к проекту бюджета2027–2029','source_url':finance['budgetBill']['source_url'],'sha256':finance['budgetBill']['source_html_sha256'],'download_path':finance['budgetBill']['source_html_download'],'source_kind':'legal_republication'}]+updates
 dump(output/'source_manifest.json',{**manifest,'supplemental_sources':supplemental})
 documentary={'meta':{'project_id':PROJECT,'documentary_snapshot':'2026-10-16','retrieved_at':'2026-10-29','sources':len(selected),'corpus_documents':98,'corpus_projects':12,'source_kind':'secondary_epbs_rendering','schema_version':1,'input_archive_sha256':manifest['archive_sha256']},'finance':finance,'network':network,'text':text,'targets':targets,'sources':[d['document'] for d in selected],'officialUpdates':updates,'downloads':{'sources':REL+'documentary_sources.zip','inputs':REL+'documentary_inputs.json.gz','sources_index':REL+'source_manifest.json','full_documentary':REL+'documentary_full.json','finance_years':REL+'finance_fp_years.csv','finance_sources':REL+'finance_source_rows.csv','finance_results':REL+'finance_result_years.csv','budget_reserves':REL+'finance_budget_reserves.csv','targets_all_editions':REL+'targets_all_years.csv','target_mapping':REL+'target_mapping.json','text_methods':REL+'text_methods.md','finance_methods':REL+'finance_methods.md','code':'downloads/code/platform/build_healthtech_documentary.py'}}
 for name,rows in [('finance_fp_years',finance['fpYears']),('finance_source_rows',finance['sourceRows']),('finance_reconciliation',finance['reconciliation']),('finance_result_years',finance['resultYears']),('finance_result_sums',finance['resultSums']),('finance_budget_reserves',finance['reserveYears']),('targets_all_years',targetrecords),('network_nodes',nodes),('network_unresolved_weights',claims),('network_shared_task',shared),('network_semantic_candidates',candidates)]:csv_write(output/(name+'.csv'),rows)
 for name in ['text_parameters.json','theme_dictionary.json','target_mapping.json','budget_bill_author_transcription.json','budget_source_verification.json','budget_2027_2029.html','text_methods.md','finance_methods.md']:
  shutil.copy2(folder/name,output/name)
 inp={'source_manifest':manifest,'profiles':[{'document':d['document'],'units':d['units']} for d in all_docs],'selected_passports':selected,'text_parameters':text['method'],'theme_dictionary':text['dictionary']};z=gzip.compress((json.dumps(inp,ensure_ascii=False,allow_nan=False)+'\n').encode(),mtime=0);(output/'documentary_inputs.json.gz').write_bytes(z)
 dump(data_dir/'targets.json',targets);dump(data_dir/'documentary.json',documentary);dump(output/'documentary_full.json',documentary)
 validation={'passed':True,'project_id':PROJECT,'corpus_documents':len(all_docs),'corpus_projects':12,'corpus_tokens':text['corpusTokenCount'],'healthtech_tokens':text['sameGenreTokenCount'],'source_passports':len(selected),'target_cells':targets['target_cells'],'numeric_targets':targets['numeric_targets'],'missing_targets':targets['missing_targets'],'finance_total_thousand_rub':finance['totalDecimal'],'finance_visible_federal_cells':sum(r['amount_decimal'] is not None for r in finance['fpYears']),'finance_missing_federal_cells':sum(r['amount_decimal'] is None for r in finance['fpYears']),'finance_difference_thousand_rub':0,'unique_nodes':len({n['node_id'] for n in nodes}),'result_cards':sum(n['kind']=='result' for n in nodes),'weight_claims':69,'verified_direct_edges':0,'candidate_pairs':83,'thematic_cells':len(text['frameScores']),'context_count':text['contextCount'],'features':text['features'],'replication_audit':text['replicationAudit'],'official_news_documents':len(updates)}
 dump(output/'documentary_validation.json',validation);print(json.dumps(validation,ensure_ascii=False,indent=2));return documentary
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=APP);p.add_argument('--verify',action='store_true');a=p.parse_args();build(a.root.resolve(),a.verify)
