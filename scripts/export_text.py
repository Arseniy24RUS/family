#!/usr/bin/env python3
"""Independent, fully specified 65-profile interpretation of the Export report.

The report publishes its corpus and TF–IDF formula, but not the exact stopword
list or token regular expression. Author numbers remain separate observations;
this script never tunes coefficients to their rounded reference values.
"""
from pathlib import Path
import hashlib,json,re
from export_data import atomic,csv_write
from extract_export_passports import norm

PROJECT='international_export'
AUTHOR_THRESHOLDS={0.05:26,0.1:15,0.15:8,0.2:6}

def build_text(folder,all_docs,selected,output,data_dir):
 import numpy as np
 from sklearn.feature_extraction.text import TfidfVectorizer
 folder=Path(folder);cfg=json.loads((folder/'text_parameters.json').read_text());dictionary=json.loads((folder/'theme_dictionary.json').read_text())
 documents=sorted([d for d in selected if d['document']['code']!='М'],key=lambda d:d['document']['code'])
 results=[];indicators=[];profiles=[]
 for d in documents:
  for kind,dest,letter in [('result',results,'R'),('indicator',indicators,'I')]:
   for i,node in enumerate([n for n in d['nodes'] if n['kind']==kind],1):
    row={**node,'id':node['node_id'],'code':f"{node['fp']}-{letter}{i:02d}",'text':node['title']+(' '+node.get('description','') if kind=='result' else '')}
    row['text_sha256']=hashlib.sha256(row['text'].encode()).hexdigest();dest.append(row)
 profiles=results+indicators;assert (len(results),len(indicators),len(profiles))==(47,18,65)
 params=dict(preprocessor=lambda x:x.lower().replace('ё','е'),token_pattern=cfg['token_pattern'],stop_words=cfg['stopwords'],ngram_range=tuple(cfg['ngram_range']),sublinear_tf=True,smooth_idf=True,norm='l2',dtype=np.float64)
 vectorizer=TfidfVectorizer(**params);matrix=vectorizer.fit_transform([p['text'] for p in profiles]);scores=(matrix[:47]@matrix[47:].T).toarray();names=vectorizer.get_feature_names_out()
 best=[]
 for i,r in enumerate(results):
  choices=[j for j,t in enumerate(indicators) if t['fp']==r['fp']]
  j=min(choices,key=lambda j:(-scores[i,j],indicators[j]['code']));t=indicators[j];value=float(scores[i,j])
  best.append({'id':r['node_id']+'__'+t['node_id'],'result_id':r['node_id'],'indicator_id':t['node_id'],'result_node_id':r['node_id'],'indicator_node_id':t['node_id'],'result_title':r['title'],'indicator_title':t['title'],'result_code':r['code'],'indicator_code':t['code'],'source_node_id':r['node_id'],'target_node_id':t['node_id'],'document_id':r['document_id'],'fp':r['fp'],'cosine':value,'score':value,'evidence_class':'lexical_best_within_same_federal_project','source_url':r['source_url'],'source_sha256':r['source_sha256'],'result_locator':r['source_locator'],'indicator_locator':t['source_locator'],'causal_status':'not_identified','official_weight':None,'selected_at_main_threshold':value>=0.1})
 thresholds=[]
 for threshold,author in AUTHOR_THRESHOLDS.items():
  n=sum(r['cosine']>=threshold for r in best);thresholds.append({'threshold':threshold,'pairs':n,'results_with_candidate':n,'results_without_candidate':47-n,'top_k':1,'scope':'same_federal_project','author_reported_results':author,'matches_author':n==author,'origin':'independent_fully_specified_65_profile_model'})
 # Four aggregated profiles are fitted independently, as described in report B360.
 docprofiles=[{**d['document'],'text':'\n'.join(p['text'] for p in profiles if p['document_id']==d['document']['document_id'])} for d in documents]
 dv=TfidfVectorizer(**params);dm=dv.fit_transform([d['text'] for d in docprofiles]);ds=(dm@dm.T).toarray();dn=dv.get_feature_names_out();similarity=[];top=[];files={};allcontexts=[];frame_scores=[];metas=[]
 for i,d in enumerate(docprofiles):
  did=d['document_id'];meta={k:v for k,v in d.items() if k!='text'};meta['profile_token_count']=len(re.findall(cfg['token_pattern'],norm(d['text'])));meta['token_count']=meta['profile_token_count'];meta['profile_text_sha256']=hashlib.sha256(d['text'].encode()).hexdigest();metas.append(meta)
  for j,t in enumerate(docprofiles):similarity.append({'source_document_id':did,'target_document_id':t['document_id'],'left':d['code'],'right':t['code'],'source_title':d['title'],'target_title':t['title'],'cosine':float(ds[i,j]),'score':float(ds[i,j]),'same_document':i==j})
  weights=dm.getrow(i).toarray().ravel();terms=[{'document_id':did,'document':did,'term':str(dn[j]),'weight':float(weights[j]),'tfidf':float(weights[j]),'rank':rank+1} for rank,j in enumerate(sorted(range(len(dn)),key=lambda j:(-weights[j],dn[j]))[:30]) if weights[j]>0];top+=terms;contexts=[];rlist=[r for r in results if r['document_id']==did]
  for frame in dictionary['frames']:
   rx=re.compile('|'.join('(?:'+p+')' for p in frame['patterns']));hitrows=[]
   for r in rlist:
    text=norm(r['text']);matches=list(rx.finditer(text))
    if matches:hitrows.append(r['id'])
    for match in matches[:5]:
     contexts.append({'id':f'{did}:kwic{len(contexts)+1}','document_id':did,'result_id':r['id'],'result_code':r['code'],'frame':frame['id'],'matched':match.group(),'before':text[max(0,match.start()-85):match.start()],'after':text[match.end():match.end()+85],'context':text[max(0,match.start()-85):match.end()+85],'source_url':r['source_url'],'source_sha256':r['source_sha256'],'source_locator':r['source_locator'],'text':r['text'],'origin':'independent_published_dictionary'})
   frame_scores.append({'document_id':did,'code':d['code'],'title':d['title'],'frame':frame['id'],'frame_id':frame['id'],'frame_name':frame['label'],'count':len(hitrows),'result_count':len(rlist),'denominator':len(rlist),'value':len(hitrows)/len(rlist)*100,'percent':len(hitrows)/len(rlist)*100,'sharePct':len(hitrows)/len(rlist)*100,'result_ids':hitrows,'unit':'процент результатов ФП','overlapping_categories':True})
  allcontexts+=contexts;dest=data_dir/'text_documents'/f'{did}.json';atomic(dest,{'document':meta,'profile':d['text'],'terms':terms,'topTerms':terms,'contexts':contexts,'units':[p for p in profiles if p['document_id']==did]});files[did]=f'data/projects/{PROJECT}/text_documents/{did}.json'
 note='В докладе задан корпус из 65 текстов и формула TF–IDF, но не опубликованы точный список стоп-слов, регулярное выражение токенизации и словарь тематических признаков. Платформа публикует собственную полную спецификацию и независимый расчёт. Авторские коэффициенты и пороги сохранены отдельно. Совпадение некоторых пороговых чисел не означает воспроизведение всех коэффициентов.'
 discrepancy='При порогах 0,05 / 0,10 / 0,15 / 0,20 автор сообщает 26 / 15 / 8 / 6 результатов. Независимая спецификация платформы даёт '+ ' / '.join(str(r['pairs']) for r in thresholds)+'. Различия не исправлялись подгонкой весов; исходный доклад сохранён.'
 checks=[{'metric':'threshold_'+str(r['threshold']),'computed':r['pairs'],'author_reported':r['author_reported_results'],'difference':r['pairs']-r['author_reported_results'],'equal':r['matches_author']} for r in thresholds]
 coefficient_checks=[]
 for rc,ic,author in [('М1-R04','М1-I02',.429),('М3-R05','М3-I02',.371),('М3-R23','М3-I09',.328),('М4-R04','М4-I02',.216),('М2-R05','М2-I01',0.0)]:
  i=next(i for i,r in enumerate(results) if r['code']==rc);j=next(j for j,r in enumerate(indicators) if r['code']==ic);computed=float(scores[i,j]);coefficient_checks.append({'result_code':rc,'indicator_code':ic,'result_title':results[i]['title'],'indicator_title':indicators[j]['title'],'author_reported_cosine':author,'computed_cosine':computed,'difference':computed-author,'matches_author_rounded_3dp':round(computed,3)==author,'source_url':'downloads/projects/international_export/report/expertise_export_2026.html#b376'})
 result={'documents':metas,'corpusDocuments':[{k:v for k,v in p.items() if k!='text'} for p in profiles],'profiles':profiles,'profileCount':65,'resultProfiles':47,'indicatorProfiles':18,'sameGenreTokenCount':sum(m['token_count'] for m in metas),'corpusTokenCount':sum(len(re.findall(cfg['token_pattern'],norm(p['text']))) for p in profiles),'features':int(matrix.shape[1]),'frames':dictionary['frames'],'frameScores':frame_scores,'projectFrameScores':[],'documentSimilarity':similarity,'projectSimilarity':[],'candidateThresholds':thresholds,'bestCandidates':best,'resultIndicatorMatrix':{'rows':[{k:r[k] for k in ['id','code','fp','title','document_id']} for r in results],'columns':[{k:r[k] for k in ['id','code','fp','title','document_id']} for r in indicators],'values':scores.tolist(),'selection_scope':'Best match within the same federal project; full matrix includes cross-project pairs.','unit':'cosine_similarity'},'topTerms':top,'terms':top,'documentFiles':files,'contextCount':len(allcontexts),'method':cfg,'dictionary':dictionary,'replicationAudit':checks,'replicationStatus':'independent_model_author_preprocessing_not_fully_specified','authorExactCodeAvailable':False,'authorAnalysis':{'documents':65,'result_profiles':47,'indicator_profiles':18,'threshold_results':{str(k):v for k,v in AUTHOR_THRESHOLDS.items()},'document_similarity_range':[.038,.144],'industrial_agriculture_similarity':.144,'industrial_system_similarity':.143,'selected_example_scores':[.429,.371,.328,.216,0.0],'source_url':'downloads/projects/international_export/report/expertise_export_2026.html#b348'},'notes':[note,discrepancy,'Для каждого результата выбирается ровно один наиболее близкий показатель собственного ФП. Нулевая близость не доказывает отсутствия экономической связи, положительная не устанавливает причинного влияния.','Векторы четырёх ФП рассчитываются повторно на четырёх агрегированных профилях. Их коэффициенты нельзя сравнивать по шкале с коэффициентами матрицы 47×18.','Тематические значения — доли результатов собственного ФП, а не частоты на тысячу слов. Темы пересекаются, поэтому сумма долей не обязана равняться 100%.']}
 for name,rows in [('text_profiles',profiles),('text_kwic',allcontexts),('frame_scores',frame_scores),('document_similarity',similarity),('tfidf_top_terms',top),('network_best_candidates',best),('text_replication_audit',checks)]:csv_write(output/(name+'.csv'),rows)
 result['authorCoefficientComparison']=coefficient_checks;csv_write(output/'author_coefficient_comparison.csv',coefficient_checks)
 csv_write(output/'result_indicator_matrix.csv',[{'result_code':r['code'],'indicator_code':t['code'],'result_id':r['id'],'indicator_id':t['id'],'result_fp':r['fp'],'indicator_fp':t['fp'],'cosine':float(scores[i,j]),'eligible_own_fp':r['fp']==t['fp']} for i,r in enumerate(results) for j,t in enumerate(indicators)])
 atomic(output/'text_method.json',cfg);atomic(output/'theme_dictionary.json',dictionary)
 return result,[r for r in best if r['cosine']>=0.1]
