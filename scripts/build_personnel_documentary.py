#!/usr/bin/env python3
"""Build Personnel finance, target, network and text data from pinned inputs.

Default execution is offline and uses the standard library. --verify-text
recalculates the fixed global TF-IDF model and Russian Snowball sensitivity.
"""
from pathlib import Path
from decimal import Decimal
import argparse,collections,csv,gzip,hashlib,json,re
from build_youth_documentary import numrows,verify_text

PROJECT='personnel';REL='downloads/projects/personnel/documentary/'
def dump(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csv_rows(p,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def build_targets(inp,registry):
    allrows=inp['tables']['targets'];selected=[r for r in allrows if r['source_url'].startswith('https://databudget.ru/') and r['mapping_status'] in {'approved','conditional'} and r['target_period_kind']=='annual']
    assert len(selected)==65,len(selected)
    sources={d['source_sha256']:d for d in inp['source_documents']};items=[]
    for indicator in registry['items']:
        code=indicator['indicator_code'];rr=sorted([r for r in selected if r['indicator_code']==code],key=lambda r:int(r['target_year']))
        assert rr,code
        r=rr[0];years={str(y):None for y in range(2025,2031)};years.update({x['target_year']:float(x['target_value']) for x in rr})
        statuses={y:('documented_target' if v is not None else 'not_published') for y,v in years.items()}
        if code=='2.14.Л1.1':statuses['2030']='ambiguous_zero_target_requires_interpretation'
        variants=[]
        for url,version in sorted({(x['source_url'],x['source_version']) for x in allrows if x['indicator_code']==code}):
            vv=[x for x in allrows if x['indicator_code']==code and x['source_url']==url and x['source_version']==version]
            first=vv[0];d=sources.get(first['source_sha256'],{})
            variants.append({'source_url':url,'source_version':version,'source_sha256':first['source_sha256'],'source_file':d.get('download_path'),'years':{x['target_year']:float(x['target_value']) for x in vv},'selected':url==r['source_url'] and version==r['source_version'],'document_level':first['document_level']})
        sids=indicator.get('source_ids',[])
        item={'code':code,'indicator_code':code,'emiss_id':int(sids[0]) if sids else None,'name':r['indicator_name'],'unit':'%' if r['unit'].lower()=='процент' else r['unit'],'direction':r['direction'],'years':years,'yearStatus':statuses,
              'baseline':{'year':int(r['baseline_year']) if r['baseline_year'].isdigit() else None,'value':float(r['baseline_value']) if r['baseline_value'] else None,'status':'source_value_with_year' if r['baseline_year'] else 'source_value_without_confirmed_year'},
              'source_url':r['source_url'],'source_sha256':r['source_sha256'],'source_locator':r['source_locator'],'source_version':r['source_version'],'source_file':sources[r['source_sha256']]['download_path'],'publisher_updated_label':r['publisher_updated_label'],'measure_type':r['measure_type'],'gap_unit':r['gap_unit'],'records':rr,'versions':variants,'mapping_status':r['mapping_status'],'formal_comparison_eligible':r['mapping_status']=='approved' and code!='2.14.Л1.1',
              'edition_note':'Выбранная электронная редакция от 16.10.2026. Сопоставление не является проверкой первоначально утверждённого обязательства 2025 года.'}
        if code=='2.14.Л1.1':item['clarification']='Ноль 2030 присутствует в полном паспорте и электронной публикации. Смысл требует уточнения, нулевая длительность трудоустройства из него не следует.'
        if r['mapping_status']=='conditional':item['clarification']='Паспортные цели МРОТ сохранены. Соответствие недоступному статистическому источнику имеет условный статус; сравнение с фактом не рассчитывается.'
        items.append(item)
    assert len(items)==11 and sum(v is not None for x in items for v in x['years'].values())==65
    return {'project_id':PROJECT,'documentary_snapshot':inp['documentary_snapshot'],'basis':'selected_electronic_passport_editions_2026_10_16','items':items,'target_cells':66,'numeric_targets':65,'missing_targets':1,'version_policy':'Preserve every extracted edition separately; never average alternative targets.','clarifications':[{'indicator_code':'2.14.Л1.1','year':2030,'value':0,'status':'ambiguous_zero_target_requires_interpretation','note':'Не использовать автоматически в оценке достижения или сценарии до разъяснения.'}]}

def build_finance(inp):
    raw=[r for r in inp['tables']['f_cashflows'] if r['row_type']=='document_header' and r['source_name']=='all_sources_declared']
    period={str(y) for y in range(2025,2031)};fed=[r for r in raw if r['document_level']=='federal' and r['year'] in period];nat=[r for r in raw if r['document_level']=='national' and r['year'] in period]
    assert len(fed)==24 and len(nat)==6,(len(fed),len(nat))
    projects=[]
    for title in sorted({r['document_title'] for r in fed}):
        rr=sorted([r for r in fed if r['document_title']==title],key=lambda r:int(r['year']));r=rr[0];code=re.search(r'\[(Л\d+)\]',title).group(1);total=sum(Decimal(x['amount_thousand_rub']) for x in rr)
        full=[x for x in raw if x['document_title']==title and x['document_level']=='federal'];later=sum(Decimal(x['amount_thousand_rub']) for x in full if str(x['year']) in {str(y) for y in range(2031,2037)})
        projects.append({'id':'l'+code[1:],'code':code,'name':title.split('] ',1)[1],'title':title,'totalThousandRub':str(total),'totalBillionRub':float(total/Decimal(10**6)),'years':[{'year':int(x['year']),'amountThousandRub':x['amount_thousand_rub'],'amountBillionRub':float(Decimal(x['amount_thousand_rub'])/Decimal(10**6)),'record_id':x['record_id'],'source_xpath':x['source_xpath']} for x in rr],'laterThousandRub':str(later),'laterBillionRub':float(later/Decimal(10**6)),'fullHorizonThousandRub':str(total+later),'fullHorizonBillionRub':float((total+later)/Decimal(10**6)),'source_url':r['source_url'],'source_sha256':r['source_sha256'],'edition':r['edition_label'],'publisher_updated_label':r['publisher_updated_label'],'retrieved_at':r['retrieved_at']})
    total=sum(Decimal(p['totalThousandRub']) for p in projects);national=sum(Decimal(r['amount_thousand_rub']) for r in nat);later=sum(Decimal(p['laterThousandRub']) for p in projects)
    for p in projects:p.update(share=float(Decimal(p['totalThousandRub'])/total*100),sharePercent=float(Decimal(p['totalThousandRub'])/total*100),shareFraction=float(Decimal(p['totalThousandRub'])/total))
    reconciliation=[]
    for y in range(2025,2031):
        n=sum(Decimal(r['amount_thousand_rub']) for r in nat if r['year']==str(y));f=sum(Decimal(r['amount_thousand_rub']) for r in fed if r['year']==str(y))
        reconciliation.append({'year':y,'nationalThousandRub':str(n),'federalThousandRub':str(f),'differenceThousandRub':str(f-n),'nationalBillionRub':float(n/Decimal(10**6)),'federalBillionRub':float(f/Decimal(10**6)),'differenceBillionRub':float((f-n)/Decimal(10**6))})
    hhi=sum((Decimal(p['totalThousandRub'])/total)**2 for p in projects)
    assert total==Decimal('178800951.31') and national==Decimal('177331609.71') and total-national==Decimal('1469341.60')
    assert later==Decimal('119393668.30') and all(Decimal(r['differenceThousandRub'])==0 for r in reconciliation[1:])
    horizons=[]
    for p in projects:
        rr=sorted([r for r in raw if r['document_level']=='federal' and r['document_title']==p['title']],key=lambda r:int(r['year']))
        p['fullYears']=[{'year':int(r['year']),'amountThousandRub':r['amount_thousand_rub'],'amountBillionRub':float(Decimal(r['amount_thousand_rub'])/Decimal(10**6))} for r in rr]
        horizons.append({'code':p['code'],'name':p['name'],'commonStart':2025,'commonEnd':2030,'commonThousandRub':p['totalThousandRub'],'commonBillionRub':p['totalBillionRub'],'fullStart':min(int(r['year']) for r in rr),'fullEnd':max(int(r['year']) for r in rr),'fullThousandRub':p['fullHorizonThousandRub'],'fullBillionRub':p['fullHorizonBillionRub'],'laterStart':2031,'laterEnd':2036,'laterThousandRub':p['laterThousandRub'],'laterBillionRub':p['laterBillionRub']})
    assert sum(len(p['fullYears']) for p in projects)==48
    return {'projects':projects,'reconciliation':reconciliation,'horizonSummaries':horizons,'totalThousandRub':str(total),'totalBillionRub':float(total/Decimal(10**6)),'nationalThousandRub':str(national),'nationalBillionRub':float(national/Decimal(10**6)),'differenceThousandRub':str(total-national),'differenceBillionRub':float((total-national)/Decimal(10**6)),'laterThousandRub':str(later),'laterBillionRub':float(later/Decimal(10**6)),'fullHorizonThousandRub':str(total+later),'hhi':float(hhi),'hhiDecimal':str(hhi),'effectiveEqualProjects':float(1/hhi),'top2SharePercent':sum(p['sharePercent'] for p in projects if p['code'] in ['Л1','Л3']),'unit':'тыс. руб.','basis':'Номинальные плановые назначения по всем источникам, 2025–2030','notExecution':True,'differentEditions':True,'cashflows':inp['tables']['f_cashflows'],'sourceReconciliation':inp['tables']['f_source_reconciliation'],'limitations':['Паспортный план не является кассовым исполнением.','Вложенные межбюджетные перечисления не суммируются повторно.','Суммы 2031–2036 показаны отдельно от сравнимого горизонта.','Расхождение редакций не устанавливает недофинансирование или нарушение.']}

def reviewed_links(inp):
    rr=inp['manual_reviewed_links'];src=next(d for d in inp['source_documents'] if d['source_sha256']==inp['manual_review_provenance']['source_pdf_sha256'])
    target='reviewed_Л1_i1';nodes=[{'id':target,'kind':'indicator','code':'Л1','title':rr[0]['indicator'],'sourceIds':['report','fn_091','fn_092']}];edges=[]
    for r in rr:
        rid='reviewed_Л1_r'+str(r['result_number']);nodes.append({'id':rid,'kind':'result','title':r['result_short'],'code':'Л1','result_number':str(r['result_number']),'sourceIds':['report','fn_091','fn_092']})
        edges.append({'id':rid+'_i1','source_node_id':rid,'target_node_id':target,'evidence_class':'reviewed_direct_passport_link','relation':'direct_passport_assignment','code':'Л1','weight':1,'documentary_weight_percent':int(r['documentary_weight_percent']),'weight_meaning':'passport_declared_distribution_not_estimated_causal_effect','sourceIds':['report','fn_091','fn_092'],'figureId':'figure_11','pdf_page':int(r['pdf_page']),'printed_page':int(r['printed_page']),'source_url':src['source_url'],'source_file':src['download_path'],'source_sha256':src['source_sha256'],'edition_note':'Полная редакция с помесячным планом 2025 года. Сохранение привязки в редакции 2026 года требует отдельной сверки.','causal_effect':False})
    assert len(edges)==10 and sum(x['documentary_weight_percent'] for x in edges)==100
    return {'nodes':nodes,'edges':edges,'scope':'Десять рассмотренных результатов Л1, один показатель','source':'Полный паспорт «Управление рынком труда», PDF, с. 155–157, дополнительные материалы, с. 1–3.','causal_effect':False}

def build_text(inp):
    t=inp['tables'];docs=numrows(t['documents']);fed={d['document_id'] for d in docs if d['genre']=='html_passport' and d['document_level']=='federal'};primary=next(d['document_id'] for d in docs if d['genre']=='html_passport' and d['document_level']=='national')
    pairs=[r for r in t['document_similarity'] if r['document_a'] in fed and r['document_b'] in fed];assert len(fed)==4 and len(pairs)==6
    frames=[{'id':k,'name':v['name'],'patterns':v['patterns']} for k,v in inp['profiles']['dictionary']['frames'].items()]
    return {'documents':docs,'federalDocumentIds':sorted(fed),'primaryDocumentId':primary,'frames':frames,'frameScores':numrows(t['frame_scores']),'projectFrameScores':numrows(t['project_frame_scores']),'topTerms':numrows(t['tfidf_top_terms']),'documentSimilarity':numrows(pairs),'projectSimilarity':numrows(t['project_similarity']),'stemmingSensitivity':numrows(t['stemming_project_sensitivity']),'kwic':numrows(t['kwic']),'units':numrows(t['units']),'lexicalFrequencies':numrows(t['lexical_frequencies']),'domainEvidence':numrows(t['domain_evidence']),'conceptCooccurrence':numrows(t['concept_cooccurrence']),'parameters':inp['profiles']['parameters'],'corpusDocuments':len(inp['profiles']['documents']),'dictionaryVersion':inp['profiles']['dictionary']['version'],'limitations':['Категории словаря пересекаются и не складываются до 100%.','Внутрипроектная матрица сравнивает четыре федеральных HTML-паспорта одного жанра.','Нулевая доходная категория Л1 связана с отсутствием маркеров МРОТ и зарплаты в словаре, несмотря на наличие мер.','Профиль «Семьи» отличается по жанру.','Стемминг не является лемматизацией.','Сходство лексики не измеряет причинную связь или качество управления.']}

def build(root=Path(__file__).resolve().parents[1],verify=False):
    root=Path(root);download=root/'public'/REL
    with gzip.open(root/'inputs/personnel/documentary_inputs.json.gz','rt',encoding='utf-8') as f:inp=json.load(f)
    for source in inp['source_documents']:
        path=(root/'public'/source['download_path']).resolve()
        assert path.is_relative_to((root/'public').resolve()),source['download_path']
        assert path.stat().st_size==source['size_bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==source['source_sha256'],source['download_path']
    assert hashlib.sha256((download/'manual_direct_links.csv').read_bytes()).hexdigest()==inp['manual_review_provenance']['sha256']
    registry=json.loads((root/'public/data/projects/personnel/indicators.json').read_text());targets=build_targets(inp,registry);finance=build_finance(inp);text=build_text(inp);t=inp['tables']
    network={'nodes':numrows(t['nodes']),'edges':numrows(t['edges']),'sharedTaskLinks':numrows(t['result_indicator_shared_task']),'semanticCandidates':numrows(t['semantic_candidates']),'coverage':numrows(t['link_coverage'])[0],'metrics':numrows(t['network_node_metrics']),'summary':numrows(t['network_summary']),'unresolvedClaims':numrows(t['link_claims']),'indicatorRegistryLinks':numrows(t['indicator_registry_links']),'directReviewed':reviewed_links(inp),'limitations':['Документальная карточка не устанавливает исполнение результата.','Связь через общую задачу имеет класс structural_inference.','Лексические кандидаты остаются непроверенными.','Прямая паспортная проверка охватывает 10 результатов Л1, а не все 32 результата.']}
    assert len(network['nodes'])==63 and len(network['edges'])==105 and len(network['sharedTaskLinks'])==67
    meta={'project_id':PROJECT,'source_release':inp['source_release'],'documentary_snapshot':inp['documentary_snapshot'],'source_documents':len(inp['source_documents']),'source_document_bytes_verified':True,'source_provenance':inp['source_provenance'],'source_kind':'documentary_plans_and_profiles','notExecution':True,'notCausal':True}
    doc={'meta':meta,'finance':finance,'network':network,'text':text,'targets':targets,'sources':inp['source_documents'],'downloads':{'sources':REL+'documentary_sources.zip','inputs':REL+'documentary_inputs.json.gz','sources_index':REL+'source_manifest.json','text_methods':REL+'text_methods.md','finance_methods':REL+'finance_methods.md','full_documentary':REL+'documentary_full.json','direct_links':REL+'manual_direct_links.csv','code':'downloads/code/platform/build_personnel_documentary.py'}}
    validation={'passed':True,'finance_total_thousand_rub':finance['totalThousandRub'],'national_total_thousand_rub':finance['nationalThousandRub'],'reconciliation_gap_thousand_rub':finance['differenceThousandRub'],'finance_project_year_cells':24,'later_years_thousand_rub':finance['laterThousandRub'],'hhi':finance['hhi'],'target_cells':66,'numeric_targets':65,'federal_thematic_cells':sum(r['document_id'] in text['federalDocumentIds'] for r in text['frameScores']),'same_genre_cosine_pairs':len(text['documentSimilarity']),'direct_reviewed_edges':10,'direct_reviewed_results':10,'node_types':dict(collections.Counter(n['kind'] for n in network['nodes'])),'source_documents':11}
    if verify:
        replication=verify_text(inp,doc);dump(download/'text_replication_validation.json',replication);validation['text_replication']=replication
    # Keep complete research exports downloadable; only the selected document is loaded by the interface.
    dump(download/'documentary_full.json',doc)
    text['documentFiles']=[]
    for source in text['documents']:
        did=source['document_id'];units=[r for r in text['units'] if r['document_id']==did];kwic=[r for r in text['kwic'] if r['document_id']==did]
        name=hashlib.sha256(did.encode()).hexdigest()[:20]+'.json';path='data/projects/personnel/text/'+name
        dump(root/'public'/path,{'document_id':did,'units':units,'kwic':kwic})
        text['documentFiles'].append({'document_id':did,'path':path,'units':len(units),'kwic':len(kwic)})
    text['unitCount']=len(text['units']);text['kwicCount']=len(text['kwic']);text['units']=[];text['kwic']=[];text['lazyText']=True
    # Raw cashflows and dense candidate tables are retained in the complete export.
    finance['cashflowCount']=len(finance['cashflows']);finance['cashflows']=[]
    dump(root/'public/data/projects/personnel/documentary.json',doc);dump(root/'public/data/projects/personnel/targets.json',targets)
    csv_rows(download/'finance_projects.csv',[{k:v for k,v in p.items() if k not in {'years','fullYears'}} for p in finance['projects']]);csv_rows(download/'finance_reconciliation.csv',finance['reconciliation']);csv_rows(download/'finance_cashflows.csv',t['f_cashflows']);csv_rows(download/'finance_fp_years.csv',[{'code':p['code'],'name':p['name'],**r} for p in finance['projects'] for r in p['fullYears']]);csv_rows(download/'finance_horizons.csv',finance['horizonSummaries']);csv_rows(download/'targets_all_editions.csv',t['targets']);csv_rows(download/'targets_selected.csv',[r for i in targets['items'] for r in i['records']]);csv_rows(download/'network_shared_task.csv',t['result_indicator_shared_task']);csv_rows(download/'network_semantic_candidates.csv',t['semantic_candidates']);csv_rows(download/'document_similarity.csv',doc['text']['documentSimilarity']);csv_rows(download/'stemming_sensitivity.csv',t['stemming_project_sensitivity']);csv_rows(download/'frame_scores.csv',t['frame_scores'])
    validation.update(runtime_json_bytes=(root/'public/data/projects/personnel/documentary.json').stat().st_size,lazy_document_files=len(text['documentFiles']),all_text_units=text['unitCount'],all_kwic_contexts=text['kwicCount'])
    assert validation['runtime_json_bytes']<2_000_000
    dump(download/'documentary_validation.json',validation);print(json.dumps(validation,ensure_ascii=False,indent=2));return doc

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--verify-text',action='store_true');a=p.parse_args();build(a.root,a.verify_text)
