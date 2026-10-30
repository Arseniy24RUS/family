#!/usr/bin/env python3
"""Build Youth documentary, finance and target datasets from pinned source inputs.

Default builds use only the Python standard library and never access the network.
--verify-text independently recalculates TF-IDF/cosines from all 137 fixed text
profiles; numpy and scikit-learn are then required, nltk for stemming replication.
Raw sources, source hashes, locators and original research scripts remain bundled.
"""
from __future__ import annotations
from pathlib import Path
from decimal import Decimal
import argparse, collections, csv, gzip, hashlib, json, math, os, re, tempfile

PROJECT='youth_children'
REL='downloads/projects/youth_children/documentary/'
OFFICIAL='https://minobrnauki.gov.ru/upload/2026/06/N_Molodezh_i_deti_.pdf'
EMISS=[62932,62931,62935,62936,62934,62969,62968,62895,62898]
NUMERIC={'rank','tfidf','count','n_tokens','per_1000_tokens','mean_document_frequency_per_1000','weighted_frequency_per_1000','cosine_similarity','primary_surface_cosine','russian_snowball_cosine','difference_stem_minus_surface','weight','same_genre','same_project','family_genre_mismatch','input_token_count','profile_token_count','page_count','documents','source_field_index','page_number','start_offset_normalized','end_offset_normalized','include_document_profile','has_explicit_deadline','has_explicit_unit','has_explicit_responsible','has_numeric_target','has_explicit_schedule_period','has_numeric_schedule_value','has_explicit_planned_numeric_value','schedule_rows','degree','weighted_degree','betweenness','cooccurring_units','eligible_units','share_units','result_cards','indicator_cards','explicit_resolved_result_indicator_edges','source_reported_link_claims','unresolved_source_link_claims','shared_task_result_indicator_links','results_linked_through_documented_task','indicators_linked_through_documented_task','results_with_candidate_ge_0_10','results_without_candidate_ge_0_10','indicators_with_approved_statistical_mapping','expert_link_completion','formal_attainment_eligible','direct_effect_claimed'}

def norm(text):return re.sub(r'\s+',' ',str(text or '')).strip().lower().replace('ё','е')
def numrows(rows):
    return [{k:(float(v) if v not in ('',None) and k in NUMERIC else v) for k,v in r.items()} for r in rows]
def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def rows_csv(path,rows):
    if not rows:return
    path=Path(path);fields=list(rows[0]);temporary=None
    try:
        # A reader must see either the preceding complete file or the next one.
        # The temporary stays in the same directory for an atomic replacement.
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8-sig',newline='',
                                         dir=path.parent,prefix='.'+path.name+'-',suffix='.tmp',delete=False) as f:
            temporary=Path(f.name)
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        with temporary.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f)
            if next(reader,None)!=fields:raise ValueError('CSV header did not survive writing: '+path.name)
            written_rows=sum(1 for _ in reader)
        if written_rows!=len(rows):
            raise ValueError(f'CSV row count mismatch for {path.name}: {written_rows} != {len(rows)}')
        os.replace(temporary,path)
        temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)

def build_targets(inp):
    rr=[r for r in inp['tables']['targets'] if r['source_url']==OFFICIAL and r['document_level']=='national' and r['mapping_status']=='approved' and r['target_period_kind']=='annual']
    assert len(rr)==54, f'Expected 9×6 selected official targets, found {len(rr)}'
    items=[]
    for n,eid in enumerate(EMISS,1):
        code=f'2.14.Ю.{n}';ss=sorted([r for r in rr if r['indicator_code']==code],key=lambda r:int(r['target_year']))
        assert len(ss)==6 and [int(r['target_year']) for r in ss]==list(range(2025,2031)),code
        r=ss[0];base={'year':int(r['baseline_year']),'value':float(r['baseline_value'])}
        items.append({'code':code,'indicator_code':code,'emiss_id':eid,'name':r['indicator_name'],'unit':r['unit'],'direction':r['direction'],
                      'baseline':base,'years':{r['target_year']:float(r['target_value']) for r in ss},
                      'source_url':r['source_url'],'source_sha256':r['source_sha256'],'source_locator':r['source_locator'],'source_version':r['source_version'],
                      'source_file':REL+'national_passport_minobrnauki.pdf','measure_type':r['measure_type'],'gap_unit':r['gap_unit'],'records':ss})
    assert next(x for x in items if x['emiss_id']==62935)['years']['2030']==70
    qual=next(x for x in items if x['emiss_id']==62898)
    assert qual['years']['2028']==14.9 and qual['years']['2029']==21.1
    return {'project_id':PROJECT,'source':OFFICIAL,'documentary_snapshot':inp['documentary_snapshot'],'basis':'selected_official_national_passport','items':items,
            'clarifications':[{'emiss_id':62898,'years':{'2028':14.9,'2029':21.1},'source_page':5,'note':'В прозе авторского отчёта приведены 15 и 21; расчёты используют точные значения выбранного первичного источника.'}]}

def build_finance(inp):
    rr=[r for r in inp['tables']['f_cashflows'] if r['row_type']=='document_header' and r['source_name']=='all_sources_declared' and r['year'] in {str(y) for y in range(2025,2031)}]
    fed=[r for r in rr if r['document_level']=='federal'];nat=[r for r in rr if r['document_level']=='national']
    assert len(fed)==54 and len(nat)==6,(len(fed),len(nat))
    projects=[]
    for title in sorted({r['document_title'] for r in fed}):
        ss=sorted([r for r in fed if r['document_title']==title],key=lambda r:int(r['year']))
        code=re.search(r'\[(Ю\d+)\]',title).group(1);total=sum(Decimal(r['amount_thousand_rub']) for r in ss)
        projects.append({'code':code,'id':'y'+code[1:],'name':title.split('] ',1)[1],'title':title,'totalThousandRub':str(total),'totalBillionRub':float(total/Decimal(10**6)),
                         'years':[{'year':int(r['year']),'amountThousandRub':r['amount_thousand_rub'],'amountBillionRub':float(Decimal(r['amount_thousand_rub'])/Decimal(10**6)),'record_id':r['record_id'],'source_xpath':r['source_xpath']} for r in ss],
                         'source_url':ss[0]['source_url'],'source_sha256':ss[0]['source_sha256'],'edition':ss[0]['edition_label'],'publisher_updated_label':ss[0]['publisher_updated_label'],'retrieved_at':ss[0]['retrieved_at']})
    projects.sort(key=lambda r:int(r['code'][1:]));total=sum(Decimal(p['totalThousandRub']) for p in projects)
    for p in projects:
        share=Decimal(p['totalThousandRub'])/total;p.update(share=float(share*100),sharePercent=float(share*100),shareFraction=float(share))
    national=sum(Decimal(r['amount_thousand_rub']) for r in nat)
    reconciliation=[]
    for year in range(2025,2031):
        n=sum(Decimal(r['amount_thousand_rub']) for r in nat if r['year']==str(year));f=sum(Decimal(r['amount_thousand_rub']) for r in fed if r['year']==str(year))
        reconciliation.append({'year':year,'nationalThousandRub':str(n),'federalThousandRub':str(f),'differenceThousandRub':str(f-n),'nationalBillionRub':float(n/Decimal(10**6)),'federalBillionRub':float(f/Decimal(10**6)),'differenceBillionRub':float((f-n)/Decimal(10**6))})
    hhi=sum((Decimal(p['totalThousandRub'])/total)**2 for p in projects)
    assert total==Decimal('6181320505.53') and national==Decimal('6177944262.03')
    return {'projects':projects,'reconciliation':reconciliation,'totalThousandRub':str(total),'totalBillionRub':float(total/Decimal(10**6)),
            'nationalThousandRub':str(national),'differenceThousandRub':str(total-national),'hhi':float(hhi),'hhiDecimal':str(hhi),
            'top2SharePercent':sum(p['sharePercent'] for p in projects if p['code'] in ['Ю6','Ю4']),
            'unit':'тыс. руб.','basis':'Плановые номинальные суммы по всем источникам, 2025–2030','notExecution':True,'differentEditions':True,
            'cashflows':inp['tables']['f_cashflows'],'sourceReconciliation':inp['tables']['f_source_reconciliation'],
            'limitations':['Паспортный план не является кассовым исполнением.','Редакции федеральных паспортов имеют разные даты.','Вложенные межбюджетные перечисления не прибавляются повторно.','HHI описывает концентрацию, не эффективность или оптимальность расходов.']}

def reviewed_links():
    registry={
     'Ю1':['Доля молодых людей, вовлечённых в мероприятия профессионального развития','Охват молодёжи мероприятиями инфраструктуры молодёжной политики'],
     'Ю4':['Доля выбравших ЕГЭ по естественно-научным предметам, профильной математике и информатике','Доля детей 5–18 лет, охваченных дополнительным образованием','Доля детей и молодёжи 7–35 лет с выявленными выдающимися способностями','Доля капитально отремонтированных школьных зданий','Доля субъектов с высоким индексом качества общего образования'],
     'Ю9':['Доля занятых выпускников «Профессионалитета»','Доля колледжей, реализующих программы «Профессионалитета»','Доля обучающихся 6–11 классов, охваченных единой моделью профориентации','Доля обучающихся СПО, прошедших демонстрационный экзамен профильного уровня','Охват студентов программами подготовки для ключевых отраслей экономики']}
    results={
     'Ю1':[('1.1','Образовательные заезды «Таврида»',[0,1]),('1.2','Конкурс «Большая перемена»',[0,1]),('1.3','Проектные активности Движения Первых, грантовая поддержка',[0,1]),('1.23','Бесплатное профобучение участников студенческих отрядов',[0,1]),('1.24','План разработки закона о профилактике агрессии и травли',[0]),('1.30','Программа «Регион для молодых»',[0,1])],
     'Ю4':[('1.1','Всероссийская и международные олимпиады',list(range(5))),('1.4','Капитальный ремонт и оборудование школьных зданий',list(range(5)))],
     'Ю9':[('1.10','Аттестация обучающихся СПО: демонстрационный экзамен',list(range(5))),('1.24','Создание кластеров среднего профессионального образования',list(range(5)))]}
    notes={'Ю1':('fn_063','figure_12'),'Ю4':('fn_064','figure_13'),'Ю9':('fn_064','figure_13')}
    nodes=[];edges=[]
    for code,inds in registry.items():
        for j,label in enumerate(inds):nodes.append({'id':f'reviewed_{code}_i{j+1}','kind':'indicator','title':label,'code':code,'sourceIds':['report',notes[code][0]]})
        for result_no,label,targets in results[code]:
            nid=f'reviewed_{code}_r{result_no}';nodes.append({'id':nid,'kind':'result','title':label,'code':code,'result_number':result_no,'sourceIds':['report',notes[code][0]]})
            for j in targets:edges.append({'id':f'{nid}_i{j+1}','source_node_id':nid,'target_node_id':f'reviewed_{code}_i{j+1}','evidence_class':'reviewed_direct_passport_link','relation':'direct_passport_assignment','code':code,'weight':1,'sourceIds':['report',notes[code][0]],'figureId':notes[code][1],'edition_note':'Паспортная редакция с планом 2025 года; сохранение связи в редакции 2026 требует самостоятельной проверки.','causal_effect':False})
    assert len(edges)==31 and sum(n['kind']=='result' for n in nodes)==10
    return {'nodes':nodes,'edges':edges,'scope':'10 рассмотренных результатов из трёх федеральных проектов','source':'Текст и рисунки 12–13 авторской экспертизы; прямые связи проверены по полным паспортам.','causal_effect':False}

def build_text(inp):
    t=inp['tables'];docs=numrows(t['documents']);federal={d['document_id'] for d in docs if d['genre']=='html_passport' and d['document_level']=='federal'}
    primary=next(d['document_id'] for d in docs if d['genre']=='html_passport' and d['document_level']=='national')
    docsim=[r for r in t['document_similarity'] if r['document_a'] in federal and r['document_b'] in federal]
    assert len(federal)==9 and len(docsim)==36
    frames=[{'id':key,'name':v['name'],'patterns':v['patterns']} for key,v in inp['profiles']['dictionary']['frames'].items()]
    return {'documents':docs,'federalDocumentIds':sorted(federal),'primaryDocumentId':primary,'frames':frames,
            'frameScores':numrows(t['frame_scores']),'projectFrameScores':numrows(t['project_frame_scores']),
            'topTerms':numrows(t['tfidf_top_terms']),'documentSimilarity':numrows(docsim),'projectSimilarity':numrows(t['project_similarity']),
            'stemmingSensitivity':numrows(t['stemming_project_sensitivity']),'kwic':numrows(t['kwic']),'units':numrows(t['units']),
            'lexicalFrequencies':numrows(t['lexical_frequencies']),'domainEvidence':numrows(t['domain_evidence']),
            'conceptCooccurrence':numrows(t['concept_cooccurrence']),'parameters':inp['profiles']['parameters'],'corpusDocuments':len(inp['profiles']['documents']),
            'dictionaryVersion':inp['profiles']['dictionary']['version'],
            'limitations':['Частоты 18 тематик пересекаются и не складываются до 100%.','Внутрипроектная матрица использует девять федеральных HTML-паспортов одного жанра.','Профиль «Семьи» имеет другой жанр и выделяется в межпроектном сравнении.','Стемминг не является лемматизацией.','Косинус характеризует словоупотребление, не качество и не причинное влияние.']}

def verify_text(inp,doc):
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    profiles=inp['profiles'];dictionary=profiles['dictionary'];token_re=re.compile(dictionary['token_regex'],re.I)
    valid=[d for d in profiles['documents'] if len(token_re.findall(norm(d['text'])))>=10]
    assert len(valid)==137
    for d in valid:assert hashlib.sha256(d['text'].encode()).hexdigest()==d['profile_text_sha256']
    p=profiles['parameters'];model=TfidfVectorizer(lowercase=True,token_pattern=p['token_pattern'],preprocessor=norm,stop_words=sorted(dictionary['stopwords']),ngram_range=tuple(p['ngram_range']),max_features=p['max_features'],min_df=p['min_df'],max_df=p['max_df'],sublinear_tf=p['sublinear_tf'],smooth_idf=p['smooth_idf'],norm=p['norm'])
    mat=model.fit_transform([d['text'] for d in valid]);cos=cosine_similarity(mat);idx={d['document_id']:i for i,d in enumerate(valid)}
    errors=[]
    for r in doc['text']['documentSimilarity']:errors.append(abs(cos[idx[r['document_a']],idx[r['document_b']]]-r['cosine_similarity']))
    vectors={}
    for project in sorted({d['project_id'] for d in valid}):
        ids=[i for i,d in enumerate(valid) if d['project_id']==project and (d['source_kind']=='secondary_epbs_rendering' or (project=='family' and d['genre']=='family_passport'))]
        if ids:
            v=np.asarray(mat[ids].mean(axis=0)).ravel();vectors[project]=v/(np.linalg.norm(v) or 1)
    for r in doc['text']['projectSimilarity']:errors.append(abs(float(np.dot(vectors[r['project_a']],vectors[r['project_b']]))-r['cosine_similarity']))
    terms=model.vocabulary_
    for r in doc['text']['topTerms']:errors.append(abs(float(mat[idx[r['document_id']],terms[r['term']]])-r['tfidf']))
    frame_errors=[];bydoc={d['document_id']:d for d in valid}
    for r in doc['text']['frameScores']:
        d=bydoc[r['document_id']];rx=re.compile('|'.join('(?:'+p+')' for p in dictionary['frames'][r['frame_id']]['patterns']))
        count=len(list(rx.finditer(norm(d['text']))));assert count==int(r['count'])
        value=count/len(token_re.findall(norm(d['text'])))*1000;frame_errors.append(abs(value-r['per_1000_tokens']))
    maxerr=max(errors,default=0);assert maxerr<1e-10,(maxerr,'TF-IDF mismatch')
    assert max(frame_errors,default=0)<1e-10
    result={'profile_hashes_checked':len(valid),'tfidf_features':len(model.vocabulary_),'numeric_comparisons':len(errors),'tfidf_max_abs_error':float(maxerr),'frame_cells_checked':len(frame_errors),'frame_max_abs_error':max(frame_errors,default=0),'passed':True}
    try:
        from nltk.stem.snowball import SnowballStemmer
    except ImportError:
        result['stemming']='not_run_missing_nltk';return result
    from functools import lru_cache
    stem=SnowballStemmer('russian',ignore_stopwords=False);stop=set(dictionary['stopwords'])
    stem_token=lru_cache(maxsize=200000)(stem.stem)
    texts=[' '.join(stem_token(t) for t in token_re.findall(norm(d['text'])) if t not in stop) for d in valid]
    sm=TfidfVectorizer(token_pattern=p['token_pattern'],ngram_range=(1,2),max_features=p['max_features'],min_df=1,max_df=.98,sublinear_tf=True,smooth_idf=True,norm='l2').fit_transform(texts)
    sv={}
    for project in vectors:
        ids=[i for i,d in enumerate(valid) if d['project_id']==project and (d['source_kind']=='secondary_epbs_rendering' or (project=='family' and d['genre']=='family_passport'))]
        v=np.asarray(sm[ids].mean(axis=0)).ravel();sv[project]=v/(np.linalg.norm(v) or 1)
    se=[abs(float(np.dot(sv[r['project_a']],sv[r['project_b']]))-r['russian_snowball_cosine']) for r in doc['text']['stemmingSensitivity']]
    assert max(se)<1e-10;result.update(stemming='recomputed',stemming_max_abs_error=max(se),stemming_comparisons=len(se));return result

def build(root=Path(__file__).resolve().parents[1],verify=False):
    root=Path(root);download=root/'public'/REL
    with gzip.open(download/'documentary_inputs.json.gz','rt',encoding='utf-8') as f:inp=json.load(f)
    targets=build_targets(inp);finance=build_finance(inp);text=build_text(inp);t=inp['tables']
    network={'nodes':numrows(t['nodes']),'edges':numrows(t['edges']),'sharedTaskLinks':numrows(t['result_indicator_shared_task']),'semanticCandidates':numrows(t['semantic_candidates']),'coverage':numrows(t['link_coverage'])[0],
             'metrics':numrows(t['network_node_metrics']),'summary':numrows(t['network_summary']),'unresolvedClaims':numrows(t['link_claims']),'indicatorRegistryLinks':numrows(t['indicator_registry_links']),'directReviewed':reviewed_links(),
             'limitations':['Документальные карточки результатов не удостоверяют их исполнение.','Связь через общую задачу имеет класс structural_inference.','Лексические кандидаты имеют статус unreviewed.','Прямые связи рассмотрены для10результатов, а не для всех199.']}
    network['limitations']=[s.replace('для10','для 10').replace('всех199','всех 199') for s in network['limitations']]
    ids={n['node_id'] for n in network['nodes']};assert all(e['source_node_id'] in ids and e['target_node_id'] in ids for e in network['edges'])
    sources=[dict(d,download_archive=REL+'documentary_sources.zip') for d in inp['source_documents']]
    doc={'meta':{'project_id':PROJECT,'source_release':inp['source_release'],'snapshot':inp['documentary_snapshot'],'source_input_sha256':hashlib.sha256((download/'documentary_inputs.json.gz').read_bytes()).hexdigest(),'interpretation':'Source-resolved documentary analysis, not causal effects'},
         'finance':finance,'targets':targets['items'],'text':text,'network':network,'sources':sources,'provenance':inp['source_provenance'],
         'downloads':{'sources':REL+'documentary_sources.zip','inputs':REL+'documentary_inputs.json.gz','national_passport':REL+'national_passport_minobrnauki.pdf','sources_index':REL+'source_index.json','text_methods':REL+'TEXT_METHODS_RU.md','finance_methods':REL+'FINANCE_METHODS_RU.md','code':'downloads/code/platform/build_youth_documentary.py'}}
    out=root/'public/data/projects/youth_children'
    # Complete data remain downloadable; app startup fetches a compact index.
    dump(download/'documentary_full.json',doc)
    document_files=[]
    for i,d in enumerate(text['documents'],1):
        did=d['document_id'];payload={'document':d,'units':[r for r in text['units'] if r['document_id']==did],
                                   'kwic':[r for r in text['kwic'] if r['document_id']==did]}
        name=f'document_{i:02d}.json';dump(out/'text'/name,payload)
        document_files.append({'document_id':did,'path':f'data/projects/{PROJECT}/text/{name}','units':len(payload['units']),'kwic':len(payload['kwic'])})
    def keep(rows,keys):return [{k:r[k] for k in keys if k in r} for r in rows]
    compact_text={k:v for k,v in text.items() if k not in {'kwic','units','lexicalFrequencies','conceptCooccurrence'}}
    compact_text['topTerms']=keep(text['topTerms'],['document_id','rank','term','tfidf'])
    compact_text['frameScores']=keep(text['frameScores'],['document_id','frame_id','count','n_tokens','per_1000_tokens'])
    compact_text['documentFiles']=document_files
    compact_network={k:v for k,v in network.items() if k not in {'nodes','edges','sharedTaskLinks','semanticCandidates','unresolvedClaims','metrics'}}
    compact_network['nodes']=keep(network['nodes'],['node_id','kind','title','description','document_id','source_card_id','source_url','document_level','indicator_code_local','unit'])
    compact_network['edges']=keep(network['edges'],['edge_id','source_node_id','target_node_id','evidence_class','relation','weight','document_id','source_url','target_resolution'])
    compact_network['sharedTaskLinks']=keep(network['sharedTaskLinks'],['link_id','result_node_id','indicator_node_id','shared_task_node_id','evidence_class','relation','document_id','source_url','statistical_codes_json','direct_effect_claimed'])
    compact_network['semanticCandidates']=keep(network['semanticCandidates'],['candidate_id','result_node_id','indicator_node_id','similarity','cosine_similarity','score','rank','review_status','evidence_class','source_url'])
    compact_network['unresolvedClaimCount']=len(network['unresolvedClaims'])
    compact_network['metrics']=keep(network['metrics'],['node_id','layer','degree','weighted_degree','betweenness','betweenness_normalized'])
    compact={**doc,'finance':{k:v for k,v in finance.items() if k not in {'cashflows','sourceReconciliation'}},'targets':[{k:v for k,v in r.items() if k!='records'} for r in targets['items']],
             'text':compact_text,'network':compact_network,'sources':keep(sources,['document_id','title','source_url','source_version','source_kind','source_sha256','snapshot_at','archive_entry','download_archive'])}
    compact['downloads']['full_documentary']=REL+'documentary_full.json'
    # Compact JSON is intentionally minified; substantive data are retained.
    (out/'documentary.json').write_text(json.dumps(compact,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
    dump(out/'targets.json',targets)
    for name,rows in t.items():rows_csv(download/(name+'.csv'),rows)
    checks={'passed':True,'finance_total_thousand_rub':finance['totalThousandRub'],'national_total_thousand_rub':finance['nationalThousandRub'],'reconciliation_gap_thousand_rub':finance['differenceThousandRub'],'finance_project_year_cells':sum(len(p['years']) for p in finance['projects']),'hhi':finance['hhi'],'targets':len(targets['items'])*6,
            'federal_thematic_cells':sum(r['document_id'] in text['federalDocumentIds'] for r in text['frameScores']),'same_genre_cosine_pairs':len(text['documentSimilarity']),'direct_reviewed_edges':len(network['directReviewed']['edges']),'direct_reviewed_results':sum(n['kind']=='result' for n in network['directReviewed']['nodes']),'node_types':dict(collections.Counter(n['kind'] for n in network['nodes'])),'source_documents':len(sources)}
    checks.update(runtime_json_bytes=(out/'documentary.json').stat().st_size,lazy_document_files=len(document_files),all_text_units=len(text['units']),all_kwic_contexts=len(text['kwic']))
    if verify:
        checks['text_replication']=verify_text(inp,doc)
        dump(download/'text_replication_validation.json',checks['text_replication'])
    dump(download/'documentary_validation.json',checks)
    return checks

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--verify-text',action='store_true');args=ap.parse_args()
    print(json.dumps(build(args.root,args.verify_text),ensure_ascii=False,indent=2))
