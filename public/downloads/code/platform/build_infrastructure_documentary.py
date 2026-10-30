#!/usr/bin/env python3
"""Reproduce Infrastructure for Life plans, document structure and text diagnostics.

Inputs are byte-pinned public passport renderings and separately attributed source
transcriptions. No network request, regional imputation or causal model is run.
"""
from pathlib import Path
from decimal import Decimal
import argparse,collections,csv,gzip,hashlib,json,math,re,shutil,zipfile
from extract_infrastructure_passports import parse_passport,decimal,norm,ws,TOKEN_RE

APP=Path(__file__).resolve().parents[1]
PROJECT='life_infrastructure'
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
   elif mode=='levels':v=(np.asarray(mx[npids].mean(axis=0))+np.asarray(mx[fpids].mean(axis=0)))/2
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
 for name,value in [('corpus_documents',len(all_docs)),('corpus_tokens',sum(d['document']['profile_token_count'] for d in all_docs)),('infrastructure_tokens',sum(d['document']['profile_token_count'] for d in selected)),('features',matrix.shape[1]),('stemming_features',sm.shape[1]),('unigram_features',um.shape[1])]:checks.append({'metric':name,'author_report':author[name],'platform_recomputed':value,'difference':value-author[name],'equal':value==author[name]})
 result={'documents':[d['document'] for d in selected],'corpusDocuments':[d['document'] for d in all_docs],'sameGenreTokenCount':sum(d['document']['profile_token_count'] for d in selected),'corpusTokenCount':sum(d['document']['profile_token_count'] for d in all_docs),'features':matrix.shape[1],'frames':frames,'frameScores':frame_scores,'documentSimilarity':docsim,'projectSimilarity':similarity,'topTerms':topterms,'sensitivity':sensitivity,'documentFiles':files,'profileCount':len(all_docs),'contextCount':len(contexts),'method':cfg,'dictionary':dictionary,'replicationAudit':checks,'replicationStatus':'independent_reimplementation_with_published_parameters_and_explicit_comparison','authorExactCodeAvailable':False,'notes':['Содержательные поля и полные исходные публикации доступны для повторной проверки.','Авторский список стоп-слов и тематические словари не приложены в полном виде. Независимые параметры платформы опубликованы отдельно.','Несовпадающие авторские и воспроизведённые результаты не заменяют друг друга.','Лексическая близость не измеряет результативность, причинный эффект или долю общих расходов.']}
 csv_write(output/'text_corpus_profiles.csv',[d['document'] for d in all_docs]);csv_write(output/'text_units.csv',[u for d in selected for u in d['units']]);csv_write(output/'text_kwic.csv',contexts);csv_write(output/'frame_scores.csv',frame_scores);csv_write(output/'document_similarity.csv',docsim);csv_write(output/'project_similarity.csv',similarity);csv_write(output/'text_sensitivity.csv',sensitivity);csv_write(output/'tfidf_top_terms.csv',topterms);csv_write(output/'text_replication_audit.csv',checks)
 return result,candidates


def load(root):
    folder = root/'inputs/infrastructure/documentary'
    manifest = json.loads((folder/'source_manifest.json').read_text())
    archive = root/manifest['archive_path']
    assert sha(archive) == manifest['archive_sha256']
    docs = []
    with zipfile.ZipFile(archive) as z:
        for meta in manifest['documents']:
            raw = z.read(meta['archive_entry'])
            assert hashlib.sha256(raw).hexdigest() == meta['sha256']
            parsed = parse_passport(raw, meta)
            assert parsed['document']['profile_token_count'] == meta['profile_token_count']
            docs.append(parsed)
    assert len(docs) == 98
    return folder, manifest, docs


UNIT_LABELS = {'Процент':'%', 'Единица':'ед.', 'Штука':'шт.',
    'Миллион квадратных метров общей площади':'млн м²', 'Квадратных метров на человека':'м² на человека',
    'Триллион рублей':'трлн руб.', 'Миллион человек':'млн человек', 'Тысяча человек':'тыс. человек',
    'Миллион единиц':'млн ед.', 'Тысяча гектаров':'тыс. га', 'Сутки':'сутки', 'Пара (2 шт.)':'пара поездов'}


def build_targets(folder, docs, registry):
    mapping = json.loads((folder/'target_mapping.json').read_text())
    reg = {x['indicator_code']:x for x in registry}
    cards, records = [], []
    for doc in docs:
        for t in doc['targets']:
            key = t['source_url']+'#'+t['card_id']
            match = mapping['mapping'].get(key)
            if match is None:
                assert key in mapping['unmapped_cards']
                match={'indicator_code':None,'source_sha256':t['source_sha256'],'title':t['title'],'mapping_id':None,'target_is_proxy':False}
            assert match['source_sha256'] == t['source_sha256']
            assert norm(match['title']) == norm(t['title'])
            code = match['indicator_code']
            ids = reg[code]['source_ids'] if code in reg else []
            source_id = mapping.get('source_overrides',{}).get(code) or (ids[0] if len(ids)==1 else None)
            unit = UNIT_LABELS.get(t['unit'], t['unit'])
            if code in ['2.14.И.10','2.14.И.10.1']:
                unit = 'человек на 10 тыс. транспортных средств'
            out = {'indicator_code':code, 'code':code, 'source_id':source_id,
                'title':t['title'], 'registry_title':reg[code]['indicator_name'] if code in reg else None, 'unit':unit,
                'passport_unit':t['unit'], 'years':{str(y):t['years'].get(str(y)) for y in YEARS},
                'source_document':t['document_id'], 'document_level':doc['document']['document_level'],
                'source_locator':t['source_locator'], 'source_url':t['source_url'], 'source_sha256':t['source_sha256'],
                'source_version':doc['document']['publisher_version'], 'publication_date':doc['document']['publication_date'],
                'source_card_id':t['card_id'], 'local_code':t['local_code'], 'base_value_raw':t['base_value_raw'],
                'base_date':t['base_date'], 'mapping_status':'reviewed_same_level_definition' if code else 'outside_inherited_registry',
                'mapping_id':match['mapping_id'], 'target_is_proxy':bool(match['target_is_proxy'] or 'прокси' in norm(t['title'])),
                'raw_years':t['raw_years'], 'origin':'independently_extracted_passport_plan',
                'federal_project_code':None if doc['document']['kind']=='np' else t['fp']}
            if code=='2.14.И.4':
                out['mapping_note']='Цель относится только к общему вводу жилья 59263. Источники 59262 и 59993 не заменяют общий объём.'
            if code in ['2.14.И.10','2.14.И.10.1']:
                out['unit_note']='Единица карточки «Человек» раскрыта вместе с указанным в названии знаменателем 10 тыс. транспортных средств.'
            cards.append(out)
            for year, raw in t['raw_years'].items():
                records.append({'indicator_code':code, 'source_id':source_id, 'document_id':t['document_id'],
                    'card_id':t['card_id'], 'year':int(year), 'value':t['years'][year], **raw, 'unit':unit,
                    'source_url':t['source_url'], 'source_sha256':t['source_sha256'],
                    'source_version':doc['document']['publisher_version'], 'title':t['title']})
    assert len(cards)==51 and len({t['indicator_code'] for t in cards if t['indicator_code']})==32
    items=[]
    for item in registry:
        code=item['indicator_code']; alternatives=[c for c in cards if c['indicator_code']==code]
        chosen=sorted(alternatives,key=lambda x:(x['document_level']!='national',x['source_document']))[0]
        comparisons=[]
        for a in alternatives:
            if a is chosen:continue
            comparisons.append({'source_document':a['source_document'],'source_card_id':a['source_card_id'],
                'source_url':a['source_url'],'source_locator':a['source_locator'],'source_sha256':a['source_sha256'],
                'different_years':[str(y) for y in YEARS if a['years'][str(y)]!=chosen['years'][str(y)]]})
        items.append({**chosen,'alternative_cards':comparisons,'selection_reason':'national_level_preferred_when_available'})
    numeric=sum(v is not None for x in items for v in x['years'].values())
    return {'project_id':PROJECT,'documentary_snapshot':'2026-10-16','basis':'single_source_edition_per_card',
        'items':items,'allCards':cards,'target_cells':len(items)*6,'numeric_targets':numeric,
        'missing_targets':len(items)*6-numeric,'version_policy':mapping['selection_policy'],
        'extracted_records_all_years':len(records),'source_card_count':len(cards),'strategicGoals':[]}, records


SOURCES = {
    'Федеральный бюджет, всего':('federal','Федеральный бюджет'),
    'Консолидированные бюджеты субъектов Российской Федерации, всего':('regional','Бюджеты регионов, консолидированные'),
    'Внебюджетные источники, всего':('extra_budget','Внебюджетные источники')}


def decimal_sum(rows):
    return sum((Decimal(r['amount_decimal']) for r in rows if r['amount_decimal'] is not None), Decimal(0))


def amounts(value):
    return {'amount_decimal':str(value) if value is not None else None,
        'amount_thousand_rub':float(value) if value is not None else None,
        'amountThousandRub':float(value) if value is not None else None,
        'amount_billion_rub':float(value/1000000) if value is not None else None,
        'value':float(value) if value is not None else None}


def build_budget(root, folder):
    from lxml import html
    spec = json.loads((folder/'budget_source.json').read_text())
    source = root/spec['source_input_path']; assert sha(source)==spec['source_html_sha256']
    tree = html.fromstring(source.read_bytes()); rt=tree.getroottree()
    tables=[t for t in tree.xpath('//table') if 'Развитие инфраструктуры в населенных пунктах' in ws(t.text_content()) and '1 413 125,1' in ws(t.text_content())]
    assert len(tables)==1
    table=tables[0]; allrows=[]; totals=[]; projects=[]; active_code=None
    names={'Развитие инфраструктуры в населенных пунктах':'И1','Жилье':'И2','Модернизация коммунальной инфраструктуры':'И3','Формирование комфортной городской среды':'И4','Безопасность дорожного движения':'И5','Развитие общественного транспорта':'И6','Развитие федеральной сети':'И7','Региональная и местная дорожная сеть':'И8','Общесистемные меры развития дорожного хозяйства':'И9','Новый ритм строительства':'ИА','Развитие железнодорожного центрального транспортного узла':'ИВ'}
    for row in table.xpath('.//tr'):
        cells=row.xpath('./th|./td')
        if len(cells)!=5:continue
        label=ws(cells[0].text_content())
        if re.fullmatch(r'\d+', label):
            continue  # Numbered table header is not a budget direction.
        numbers=[decimal(ws(c.text_content())) for c in cells[1:]]
        if any(v is None for v in numbers):continue
        if label=='Всего':kind='national_total'; code='И'; name='Всего'
        elif label.startswith('Федеральный проект '):
            name=label.split('"',2)[1];code=names[name];active_code=code;kind='federal_project'
        else:kind='direction';code=active_code;name=label
        for year,val,cell in zip(range(2026,2030),numbers,cells[1:]):
            r={'year':year,'fp':code,'code':code,'name':name,'label':label,'level':kind,
                'source_code':'federal','source_name':'Федеральный бюджет','source':'Федеральный бюджет',
                'amount_decimal':val,'amount_million_rub':float(val),'amount_billion_rub':float(Decimal(val)/1000),
                'amount_thousand_rub':float(Decimal(val)*1000),'amountThousandRub':float(Decimal(val)*1000),
                'value':float(val),'unit':'млн руб.','kind':'budget_allocation' if year==2026 else 'budget_bill','status':spec['periods'][str(year)],
                'source_locator':rt.getpath(cell),'source_url':spec['source_url'],'source_sha256':spec['source_html_sha256'],
                'origin':spec['verification_status']}
            allrows.append(r)
            if kind=='national_total':totals.append(r)
            elif kind=='federal_project':projects.append(r)
    assert len(totals)==4 and len(projects)==44
    assert [r['amount_decimal'] for r in totals]==['1304889.3','1413125.1','1759332.5','1439537.7']
    roadshares=[]
    for total in totals:
        year=total['year']; roads=[r for r in projects if r['year']==year and r['code'] in ['И7','И8']]
        amount=decimal_sum(roads);denom=Decimal(total['amount_decimal'])
        roadshares.append({'year':year,'road_million_rub':float(amount),'total_million_rub':float(denom),
            'share_percent':float(amount/denom*100),'denominator':'published_national_budget_table_total',
            'source_url':spec['source_url'],'source_locator':rt.getpath(table)})
    return {**spec,'source_locator':rt.getpath(table),'rows':allrows,'projectRows':projects,
        'totals':totals,'roadShares':roadshares,'published_numeric_cells':len(allrows),
        'note':'2026 – роспись на 01.09.2026. 2027–2029 – внесённый законопроект. Отсутствующая строка «Ипотека» не заменяется нулём и не означает отсутствия государственной ипотечной поддержки.'}


def build_finance(root, folder, docs):
    labels={**SOURCES, 'из них: бюджетам субъектов Российской Федерации':('federal_transfer_component','Из федерального бюджета бюджетам субъектов'), 'в том числе: средства Фонда национального благосостояния':('fnb_component','В том числе средства ФНБ')}
    allrows=[{**r,'source_code':labels[r['source']][0],'source_name':labels[r['source']][1], 'is_subcomponent':r['source'] not in SOURCES, 'included_in_additive_total':r['source'] in SOURCES} for d in docs for r in d['finance_records']]
    docrows=[r for r in allrows if r['scope']=='document']
    national=[r for r in docrows if r['fp']=='И' and r['year'] in YEARS]
    federal=[r for r in docrows if r['fp']!='И' and r['year'] in YEARS]
    nat_total=decimal_sum(national);fp_total=decimal_sum(federal)
    assert nat_total==Decimal('15094430617.02')
    assert fp_total-nat_total==Decimal('4371150.69')
    fpyears=[];fpsource=[];projects=[]
    for d in docs:
        meta=d['document'];code=meta['code']
        if code=='И':continue
        name=meta['title'].split('] ',1)[-1];rows=[r for r in federal if r['document_id']==meta['document_id']]
        years=[]
        for year in YEARS:
            yr=[r for r in rows if r['year']==year];value=decimal_sum(yr) if yr else None
            base={'fp':code,'code':code,'name':name,'year':year,'unit':'тыс. руб.','kind':'passport_plan',
                'scope':'published_all_sources_federal_project_plan','source_id':meta['document_id'],
                'source_url':meta['url'],'source_sha256':meta['sha256'],'source_version':meta['publisher_version']}
            out={**base,**amounts(value),'source_code':'all','source_name':'Все опубликованные источники',
                'source_locator':None,'source_locators':[r['source_locator'] for r in yr],
                'missing_reason':None if yr else 'no_published_annual_amount_in_selected_edition',
                'component_count':len(yr),'origin':'sum_of_visible_source_rows_without_zero_imputation'}
            fpyears.append(out);years.append(out)
            for source, (source_code, source_name) in SOURCES.items():
                cells=[r for r in yr if r['source']==source];assert len(cells)<=1
                value=decimal_sum(cells) if cells else None
                fpsource.append({**base,**amounts(value),'source':source,'source_code':source_code,'source_name':source_name,
                    'source_locator':cells[0]['source_locator'] if cells else None,
                    'value_raw':cells[0]['value_raw'] if cells else None,
                    'missing_reason':None if cells else 'no_published_source_year_cell',
                    'origin':'independently_extracted_document_plan'})
        visible_total=decimal_sum(rows) if rows else None
        projects.append({'code':code,'fp':code,'name':name,'totalThousandRub':float(visible_total) if visible_total is not None else None,
            'totalDecimal':str(visible_total) if visible_total is not None else None,'years':years,
            'source_url':meta['url'],'source_sha256':meta['sha256'],'scope':'published_all_sources_2025_2030'})
    reconciliation=[]
    for year in YEARS:
        n=decimal_sum([r for r in national if r['year']==year]);f=decimal_sum([r for r in federal if r['year']==year]);diff=f-n
        reconciliation.append({'year':year,'nationalThousandRub':float(n),'federalThousandRub':float(f),'differenceThousandRub':float(diff),
            'national_thousand_rub':float(n),'federal_thousand_rub':float(f),'difference_thousand_rub':float(diff),
            'national_decimal':str(n),'federal_decimal':str(f),'difference_decimal':str(diff),
            'definition':'Сумма опубликованных строк ФП минус сумма опубликованных строк НП за тот же год и все источники.',
            'national_locators':[r['source_locator'] for r in national if r['year']==year],
            'federal_locators':[r['source_locator'] for r in federal if r['year']==year]})
    sources=[]
    for source,(code,label) in SOURCES.items():
        rs=[r for r in national if r['source']==source];amount=decimal_sum(rs)
        sources.append({'source_code':code,'source_name':label,'source':source,'amountThousandRub':float(amount),
            'amount_thousand_rub':float(amount),'amount_decimal':str(amount),'sharePercent':float(amount/nat_total*100),
            'years':rs,'origin':'national_passport_published_plan'})
    shares=[]
    for p in projects:
        value=Decimal(p['totalDecimal']) if p['totalDecimal'] is not None else None
        shares.append({'fp':p['code'],'code':p['code'],'name':p['name'],**amounts(value),
            'share':float(value/fp_total) if value is not None else None,
            'sharePercent':float(value/fp_total*100) if value is not None else None,
            'denominator':'sum_visible_federal_project_amounts_2025_2030'})
    horizons=[]
    for d in docs:
        for first,last in [(2025,2030),(2031,2036)]:
            rs=[r for r in docrows if r['document_id']==d['document']['document_id'] and first<=r['year']<=last]
            horizons.append({'code':d['document']['code'],'name':d['document']['title'],'horizon':f'{first}–{last}',
                'first_year':first,'last_year':last,**amounts(decimal_sum(rs) if rs else None),
                'published_cells':len(rs),'source_url':d['document']['url'],
                'included_in_national_reconciliation':first==2025})
    details=[r for r in allrows if r['scope']=='result'];result_sums=[]
    for rid in sorted({r['result_id'] for r in details}):
        rs=[r for r in details if r['result_id']==rid and r['year'] in YEARS and r['included_in_additive_total']]
        if not rs:continue
        result_sums.append({'result_id':rid,'fp':rs[0]['fp'],'result_title':rs[0]['result_title'],**amounts(decimal_sum(rs)),
            'unit':'тыс. руб.','scope':'result_sources_2025_2030','source_url':rs[0]['source_url'],
            'source_locator':rs[0]['source_result_locator'],'source_sha256':rs[0]['source_sha256']})
    budget=build_budget(root,folder)
    return {'unit':'тыс. руб.','periods':YEARS,'totalThousandRub':float(nat_total),'nationalThousandRub':float(nat_total),
        'federalThousandRub':float(fp_total),'totalDecimal':str(nat_total),'nationalDecimal':str(nat_total),
        'federalDecimal':str(fp_total),'nationalMinusFederalThousandRub':float(nat_total-fp_total),
        'federalMinusNationalThousandRub':float(fp_total-nat_total),'projects':projects,'fpYears':fpyears,
        'sourceYears':fpsource,'nationalSourceYears':national,'sourceSummaries':sources,'horizonSummaries':horizons,
        'yearTotals':reconciliation,'reconciliation':reconciliation,'federalShares':shares,
        'hhi':sum(x['share']**2 for x in shares if x['share'] is not None),
        'resultYears':details,'resultSums':result_sums,'sources':docrows,'sourceRows':allrows,
        'frames':[{'id':'passport_plan','title':'Паспортный план всех источников на 2025–2030 годы',
            'unit':'тыс. руб.','periods':YEARS,'rows':fpsource,'totalRows':fpyears,'source_kind':'secondary_epbs_rendering',
            'edition_date':'2026-10-16','grain':'federal_project_source_year'},
            {'id':'budget_bill','title':'Федеральная роспись 2026 года и бюджетные предложения 2027–2029 годов',
            'unit':'млн руб.','periods':list(range(2026,2030)),'rows':budget['projectRows'],'totalRows':budget['totals'],
            'source_kind':'legal_republication','verification_status':budget['verification_status'],'grain':'federal_project_year'}],
        'budgetBill':budget,'notes':['Финансирование НП за 2025–2030 годы представлено по всем опубликованным источникам и текущим ценам.',
            'Сумма опубликованных ФП за тот же горизонт превышает НП на 4 371 150,69 тыс. руб. Разница требует сверки редакций и не устанавливает финансового нарушения.',
            'Данные 2031–2036 годов по жилью и городской среде сохранены отдельно и исключены из сопоставления 2025–2030.',
            'Отсутствующие источник и год сохраняются как пропуск. Отсутствие самостоятельной финансовой строки «Ипотеки» не означает отсутствия ипотечных субсидий в других программах.',
            'Паспорт, роспись и бюджетные предложения не измеряют кассовое исполнение и общественный эффект.']}


def build_network(selected, candidates):
    nodes=[n for d in selected for n in d['nodes']]
    byid={n['node_id']:n for n in nodes}
    assert len(byid)==len(nodes)
    claims=[c for d in selected for c in d['unresolved_weight_claims']]
    same_project=[];shared=[]
    for r in candidates:
        pair={k:v for k,v in r.items() if k not in ['cosine','weight','evidence_class','origin']}
        pair.update(evidence_class='same_federal_project_candidate',origin='administrative_same_project_pair_not_causal')
        same_project.append(pair)
        a,b=byid[r['result_node_id']],byid[r['indicator_node_id']]
        if a.get('task_node_id') and a['task_node_id']==b.get('task_node_id'):
            task=byid[a['task_node_id']]
            shared.append({**pair,'task_node_id':task['node_id'],'task_title':task['title'],
                'task_locator':task['source_locator'],'result_membership_basis':a['task_assignment_basis'],
                'indicator_membership_basis':b['task_assignment_basis'],'evidence_class':'same_document_task_membership',
                'origin':'explicit_link_and_unique_exact_title_resolution_not_causal'})
    assert sum(n['kind']=='result' for n in nodes)==85
    assert sum(n['kind']=='indicator' for n in nodes)==51
    assert len(nodes)==191 and sum(n['kind']=='task' for n in nodes)==42 and sum(n['kind']=='goal' for n in nodes)==13
    assert len(claims)==160 and len(candidates)==300 and len(shared)==266
    assert len({r['id'] for r in candidates})==300
    return {'nodes':nodes,'unresolvedClaims':claims,'reviewedEdges':[],'directLinks':[],'edges':[],
        'sharedTaskPairs':shared,'sameProjectPairs':same_project,'semanticCandidates':candidates,
        'summary':{'results':85,'indicators':51,'tasks':sum(n['kind']=='task' for n in nodes), 'goals':sum(n['kind']=='goal' for n in nodes), 'standalone_tasks':sum(n.get('record_scope')=='standalone_task_card' for n in nodes), 'repeated_structure_tasks':sum(n.get('record_scope')=='national_structure_federal_task_restatement' for n in nodes),
            'unresolved_weight_claims':160,'reviewed_direct_links':0,'shared_task_pairs':266,
            'same_project_pairs':300,'semantic_candidates':300},
        'notes':['Сохранены 42 записи задач: 26 самостоятельных карточек и 16 повторных представлений федеральных задач в национальном паспорте. Последние не создают дополнительных связей. Отдельно сохранены 13 целей документов.', '160 опубликованных записей влияния не идентифицируют показатель назначения. Их численные значения не присваиваются рёбрам.',
            '266 пар соединены через одну адресуемую задачу внутри исходного документа. Общая задача характеризует документальную принадлежность.',
            '300 пар составляют все сочетания результатов и показателей в одном ФП. Лексический косинус рассчитывается для каждой пары и служит отбору формулировок для проверки.',
            'Причинные связи и веса общественного эффекта из общей задачи и сходства слов не выводятся.']}


def build(root=APP, verify=False):
    folder,manifest,all_docs=load(root)
    selected=[d for d in all_docs if d['document']['project_id']==PROJECT]
    data_dir=root/f'public/data/projects/{PROJECT}';output=root/'public'/REL
    registry=json.loads((data_dir/'indicators.json').read_text())['items']
    output.mkdir(parents=True,exist_ok=True)
    targets,targetrecords=build_targets(folder,selected,registry)
    finance=build_finance(root,folder,selected)
    text,candidates=build_text(folder,all_docs,selected,output,data_dir)
    network=build_network(selected,candidates)
    documentary={'meta':{'project_id':PROJECT,'documentary_snapshot':'2026-10-16','prepared_at':'2026-10-29',
        'sources':13,'corpus_documents':98,'corpus_projects':12,'source_kind':'secondary_epbs_rendering','schema_version':1,
        'input_archive_sha256':manifest['archive_sha256'],'retrieval_policy':'Individual original retrieval dates are preserved; preparation is not a new retrieval.'},
        'finance':finance,'network':network,'text':text,'targets':targets,'sources':[d['document'] for d in selected],
        'officialUpdates':[],'downloads':{'sources':manifest['shared_archive_download'],'inputs':REL+'documentary_inputs.json.gz',
        'sources_index':REL+'source_manifest.json','full_documentary':REL+'documentary_full.json',
        'finance_years':REL+'finance_fp_years.csv','finance_sources':REL+'finance_source_rows.csv',
        'finance_results':REL+'finance_result_years.csv','finance_reconciliation':REL+'finance_reconciliation.csv',
        'budget_bill':REL+'budget_bill_rows.csv','targets_all_editions':REL+'targets_all_years.csv',
        'target_mapping':REL+'target_mapping.json','text_methods':REL+'text_methods.md',
        'finance_methods':REL+'finance_methods.md','code':'downloads/code/platform/build_infrastructure_documentary.py'}}
    for name,rows in [('finance_fp_years',finance['fpYears']),('finance_source_rows',finance['sourceRows']),
        ('finance_fp_source_years',finance['sourceYears']),('finance_national_source_years',finance['nationalSourceYears']),
        ('finance_reconciliation',finance['reconciliation']),('finance_horizons',finance['horizonSummaries']),
        ('finance_result_years',finance['resultYears']),('finance_result_sums',finance['resultSums']),
        ('budget_bill_rows',finance['budgetBill']['rows']),('budget_road_shares',finance['budgetBill']['roadShares']),
        ('targets_all_years',targetrecords),('network_nodes',network['nodes']),('network_unresolved_weights',network['unresolvedClaims']),
        ('network_shared_task',network['sharedTaskPairs']),('network_same_project',network['sameProjectPairs']),
        ('network_semantic_candidates',network['semanticCandidates'])]:
        csv_write(output/(name+'.csv'),rows)
    for name in ['text_parameters.json','theme_dictionary.json','target_mapping.json','budget_source.json','text_methods.md','finance_methods.md']:
        shutil.copy2(folder/name,output/name)
    inp={'source_manifest':manifest,'selected_passports':selected,'text_parameters':text['method'],'theme_dictionary':text['dictionary'],
        'shared_corpus_archive':manifest['shared_archive_download'],'shared_corpus_sha256':manifest['archive_sha256']}
    (output/'documentary_inputs.json.gz').write_bytes(gzip.compress((json.dumps(inp,ensure_ascii=False,allow_nan=False)+'\n').encode(),mtime=0))
    dump(data_dir/'targets.json',targets)
    dump(output/'documentary_full.json',documentary)
    runtime=json.loads(json.dumps(documentary,ensure_ascii=False))
    for field in ['sourceRows','resultYears']:
        runtime['finance'].pop(field)
    runtime['finance']['budgetBill'].pop('rows')
    runtime['targets'].pop('allCards')
    runtime['meta']['runtime_omissions']={'finance.sourceRows':'finance_source_rows.csv','finance.resultYears':'finance_result_years.csv','finance.budgetBill.rows':'budget_bill_rows.csv','targets.allCards':'documentary_full.json'}
    runtime['meta']['full_export_url']=REL+'documentary_full.json'
    dump(data_dir/'documentary.json',runtime)
    dump(output/'source_manifest.json',{**manifest,'supplemental_sources':[finance['budgetBill']|{'rows':None,'projectRows':None,'totals':None}]})
    validation={'passed':True,'project_id':PROJECT,'corpus_documents':98,'corpus_projects':12,'corpus_tokens':text['corpusTokenCount'],
        'infrastructure_tokens':text['sameGenreTokenCount'],'source_passports':13,'target_cards':targets['source_card_count'],
        'target_cells':targets['target_cells'],'numeric_targets':targets['numeric_targets'],'missing_targets':targets['missing_targets'],
        'finance_national_total_thousand_rub':finance['nationalDecimal'],'finance_federal_total_thousand_rub':finance['federalDecimal'],
        'finance_federal_minus_national_thousand_rub':finance['federalMinusNationalThousandRub'],
        'budget_source_cells':finance['budgetBill']['published_numeric_cells'],
        'unique_nodes':len(network['nodes']),**network['summary'],'thematic_cells':len(text['frameScores']),
        'context_count':text['contextCount'],'features':text['features'],'replication_audit':text['replicationAudit']}
    dump(output/'documentary_validation.json',validation)
    print(json.dumps(validation,ensure_ascii=False,indent=2))
    return documentary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=APP)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    build(args.root.resolve(),args.verify)
