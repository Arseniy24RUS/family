#!/usr/bin/env python3
"""Replay the report's fixed 137-document text model and audit the six tourism passports.

The common profile input and original source code are reused from the cumulative
Personnel release. Every Tourism passport profile line is independently matched
to an addressable node from its byte-pinned HTML before fitting the model.
"""
from pathlib import Path
import csv,gzip,hashlib,json,re
from author_tfidf import fit_author_tfidf
from extract_tourism_passports import norm,TOKEN_RE

PROJECT='tourism'
NAMES={'family':'Семья','personnel':'Кадры','youth_children':'Молодёжь и дети','long_active_life':'Продолжительная и активная жизнь','life_infrastructure':'Инфраструктура для жизни','environment':'Экологическое благополучие','data_economy':'Экономика данных и цифровая трансформация государства','competitive_economy':'Эффективная и конкурентная экономика','efficient_transport':'Эффективная транспортная система','international_export':'Международная кооперация и экспорт','tourism':'Туризм и гостеприимство'}

def dump(p,data):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csv_write(p,rows):
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
  for r in rows:w.writerow({k:json.dumps(r.get(k),ensure_ascii=False) if isinstance(r.get(k),(dict,list)) else r.get(k) for k in keys})

def build_text(folder,all_docs,selected,output,data_dir):
 import numpy as np
 from sklearn.feature_extraction.text import TfidfVectorizer
 from sklearn.preprocessing import normalize
 from scipy.stats import spearmanr
 from nltk.stem.snowball import RussianStemmer
 app=folder.parents[2];cfg=json.loads((folder/'text_parameters.json').read_text());shared=app/cfg['shared_profiles_input']
 assert hashlib.sha256(shared.read_bytes()).hexdigest()==cfg['shared_profiles_sha256']
 source_code=app/'public'/cfg['source_code_download']
 assert hashlib.sha256(source_code.read_bytes()).hexdigest()==cfg['source_code_sha256']
 profiles=json.loads(gzip.decompress(shared.read_bytes()))['profiles'];docs=profiles['documents']
 assert len(docs)==137
 for d in docs:
  assert hashlib.sha256(d['text'].encode()).hexdigest()==d['profile_text_sha256']
  assert len(TOKEN_RE.findall(norm(d['text'])))==d['profile_token_count']
 stops=profiles['dictionary']['stopwords'];stemmer=RussianStemmer()
 source_doc_by_sha={d['source_sha256']:d for d in docs};source_indices={d['document_id']:i for i,d in enumerate(docs)}
 short_id={};units={};checks=[];selected_metas=[]
 for parsed in selected:
  meta=parsed['document'];original=source_doc_by_sha[meta['sha256']];short_id[original['document_id']]=meta['document_id']
  nodes={}
  for node in parsed['nodes']:nodes.setdefault(norm(node['title']+' '+node.get('description','')),node)
  current=[]
  for ix,line in enumerate(original['text'].splitlines(),1):
   assert line in nodes,(meta['document_id'],line)
   node=nodes[line]
   current.append({'unit_id':f"{meta['document_id']}:profile{ix}",'document_id':meta['document_id'],
      'project_id':PROJECT,'kind':node['kind'],'text':line,'node_id':node['node_id'],
      'source_locator':node['source_locator'],'source_sha256':meta['sha256'],
      'source_url':meta['url'],'n_tokens':len(TOKEN_RE.findall(line)),
      'origin':'independent_source_node_matching_of_pinned_author_profile'})
  reconstructed='\n'.join(u['text'] for u in current)
  assert reconstructed==original['text']
  units[meta['document_id']]=current
  selected_metas.append({**meta,'profile_token_count':original['profile_token_count'],'n_tokens':original['profile_token_count'],
     'profile_text_sha256':original['profile_text_sha256'],'profile_original_document_id':original['document_id'],
     'profile_fields':'normalized unique node title plus result description in source extraction order',
     'profile_independently_verified':True})
  checks.append({'metric':'source_profile_'+meta['document_id'],'author_report':original['profile_token_count'],
     'platform_recomputed':sum(u['n_tokens'] for u in current),'difference':0,'equal':True})
 texts=[d['text'] for d in docs]
 params=dict(lowercase=True,token_pattern=r'(?u)\b[а-яa-z][а-яa-z-]{1,}\b',preprocessor=norm,
     stop_words=stops,ngram_range=(1,2),max_features=20000,min_df=1,max_df=.98,sublinear_tf=True,norm='l2',smooth_idf=True,dtype=np.float64)
 vectorizer,matrix=fit_author_tfidf(texts,params,'surface')
 unigrams=TfidfVectorizer(**{**params,'ngram_range':(1,1)});uni=unigrams.fit_transform(texts)
 stemtexts=[' '.join(stemmer.stem(t) for t in TOKEN_RE.findall(norm(t)) if t not in set(stops)) for t in texts]
 stemparams=dict(token_pattern=r'(?u)\b[а-яa-z][а-яa-z-]{1,}\b',ngram_range=(1,2),max_features=20000,min_df=1,max_df=.98,sublinear_tf=True,smooth_idf=True,norm='l2',dtype=np.float64)
 stemvectorizer,stem=fit_author_tfidf(stemtexts,stemparams,'stemming')
 projects=sorted(p for p in NAMES if p!='family');selected_index=projects.index(PROJECT)
 project_ids={p:[i for i,d in enumerate(docs) if d['project_id']==p and d['source_kind']=='secondary_epbs_rendering'] for p in projects}
 assert len(projects)==10 and all(project_ids.values())
 def project_vectors(mx,mode='all'):
  result=[]
  for p in projects:
   ids=project_ids[p];national=[i for i in ids if docs[i]['document_level']=='national'];federal=[i for i in ids if docs[i]['document_level']=='federal']
   if mode=='national':v=np.asarray(mx[national].mean(axis=0))
   elif mode=='federal':v=np.asarray(mx[federal].mean(axis=0))
   elif mode=='levels':v=.5*np.asarray(mx[national].mean(axis=0))+.5*np.asarray(mx[federal].mean(axis=0))
   else:v=np.asarray(mx[ids].mean(axis=0))
   result.append(v.ravel())
  return normalize(np.vstack(result))
 variants={'base':project_vectors(matrix),'stemming':project_vectors(stem),'unigrams':project_vectors(uni),
   'equal_levels':project_vectors(matrix,'levels'),'federal_only':project_vectors(matrix,'federal'),'national_only':project_vectors(matrix,'national')}
 scores={name:(v@v[selected_index]).tolist() for name,v in variants.items()};other=[i for i,p in enumerate(projects) if p!=PROJECT]
 similarity=[{'project_id':projects[i],'project_a':PROJECT,'project_b':projects[i],'name':NAMES[projects[i]],
   'cosine':scores['base'][i],'stemmed_cosine':scores['stemming'][i],'unigram_cosine':scores['unigrams'][i],
   'equal_levels_cosine':scores['equal_levels'][i],'federal_only_cosine':scores['federal_only'][i],
   'national_only_cosine':scores['national_only'][i],'origin':'recomputed_from_author_137_document_corpus','family_genre_mismatch':False} for i in other]
 similarity.sort(key=lambda r:-r['cosine'])
 sensitivity=[]
 for name,values in scores.items():
  order=sorted(other,key=lambda i:-values[i]);rho=float(spearmanr([scores['base'][i] for i in other],[values[i] for i in other]).statistic)
  sensitivity.append({'variant':name,'spearman':rho,'top3':[NAMES[projects[i]] for i in order[:3]],
    'top3_project_ids':[projects[i] for i in order[:3]],'features':stem.shape[1] if name=='stemming' else uni.shape[1] if name=='unigrams' else matrix.shape[1],
    'origin':'author_specification_replayed' if name in ['base','stemming'] else 'additional_platform_sensitivity',
    'author_spearman':None,'matches_author_rounded_rho':None,
    'source_corpus_documents':137,'compared_projects':10,
    'scope':'Rank correlation over nine other comparable structured project profiles. The report did not publish this exact rho.'})
 ids=project_ids[PROJECT];docsimilarity=[]
 for aidx,a in enumerate(ids):
  for b in ids[aidx+1:]:
   da,db=docs[a],docs[b]
   docsimilarity.append({'document_a':short_id[da['document_id']],'document_b':short_id[db['document_id']],
      'title_a':da['title'],'title_b':db['title'],'code_a':re.search(r'\[([^]]+)\]',da['title']).group(1),
      'code_b':re.search(r'\[([^]]+)\]',db['title']).group(1),
      'cosine':float((matrix[a]@matrix[b].T).toarray()[0,0]),'origin':'replayed_author_model'})
 terms=vectorizer.get_feature_names_out();top=[]
 for did,values in [('project',variants['base'][selected_index])]+[(short_id[docs[i]['document_id']],matrix[i].toarray()[0]) for i in ids]:
  for rank,k in enumerate(np.argsort(-values)[:50],1):
   top.append({'document_id':did,'rank':rank,'term':str(terms[k]),'weight':float(values[k]),'origin':'replayed_author_model'})
 dictionary=json.loads((folder/'theme_dictionary.json').read_text())
 frames=[{'id':key,'frame':key,'name':spec['label'],'label':spec['label'],'patterns':spec['patterns']} for key,spec in dictionary['frames'].items()]
 frame_scores=[];contexts=[];files={};frame_totals=[]
 for meta in selected_metas:
  did=meta['document_id'];profile=source_doc_by_sha[meta['sha256']]['text'];alltext=norm(profile);ranges=[];position=0
  for unit in units[did]:ranges.append((position,position+len(unit['text']),unit));position+=len(unit['text'])+1
  docctx=[]
  for frame in frames:
   regex=re.compile('|'.join('(?:'+p+')' for p in frame['patterns']));matches=list(regex.finditer(alltext))
   frame_scores.append({'document_id':did,'title':meta['title'],'code':meta['code'],'frame':frame['id'],
      'frame_id':frame['id'],'frame_name':frame['name'],'count':len(matches),'n_tokens':meta['profile_token_count'],
      'per1000':len(matches)/meta['profile_token_count']*1000,'rate_per1000':len(matches)/meta['profile_token_count']*1000,
      'origin':'replayed_author_dictionary','count_policy':'nonoverlapping_union_within_frame; overlapping_between_frames_allowed'})
   for match in matches:
    overlapping=[u for start,end,u in ranges if start<match.end() and end>match.start()]
    assert overlapping
    row={'id':f'{did}:kwic{len(docctx)+1}','document_id':did,'frame':frame['id'],'matched':match.group(),
      'context':alltext[max(0,match.start()-110):min(len(alltext),match.end()+110)],
      'unit_id':overlapping[0]['unit_id'],'unit_ids':[u['unit_id'] for u in overlapping],
      'source_locator':overlapping[0]['source_locator'],'source_locators':[u['source_locator'] for u in overlapping],
      'source_sha256':meta['sha256'],'source_url':meta['url'],
      'cross_field_match':len(overlapping)>1,'origin':'source_located_author_profile_dictionary_match'}
    docctx.append(row);contexts.append(row)
  rel=f'data/projects/{PROJECT}/documentary-text/{did}.json';dump(data_dir/'documentary-text'/f'{did}.json',{'document':meta,'units':units[did],'contexts':docctx,'kwic':docctx,'source_url':meta['url'],'source_sha256':meta['sha256']});files[did]=rel
 for frame in frames:
  rows=[r for r in frame_scores if r['frame_id']==frame['id']];count=sum(r['count'] for r in rows);den=sum(r['n_tokens'] for r in rows)
  frame_totals.append({'frame_id':frame['id'],'frame_name':frame['name'],'count':count,'n_tokens':den,'per1000':count/den*1000,'weighted_frequency_per_1000':count/den*1000})
 results=[n for d in selected for n in d['nodes'] if n['kind']=='result'];indicator_cards=[n for d in selected for n in d['nodes'] if n['kind']=='indicator']
 # The report merges repeated NP/FP indicator names before top-three selection.
 canonical={}
 for n in sorted(indicator_cards,key=lambda n:(n['fp']!='П',n['document_id'],n['node_id'])):canonical.setdefault(norm(n['title']),n)
 indicators=list(canonical.values())
 assert len(indicators)==11
 author_id=lambda n:hashlib.sha256('\x1f'.join(['node',n['kind'],'html:'+n['source_sha256'],n['source_locator'],n['title']]).encode()).hexdigest()[:24]
 cos=(vectorizer.transform([n['title']+' '+n['description'] for n in results])@vectorizer.transform([n['title'] for n in indicators]).T).toarray();candidates=[]
 for ri,r in enumerate(results):
  chosen=sorted(range(len(indicators)),key=lambda i:(-cos[ri,i],author_id(indicators[i])))[:3]
  for rank,ii in enumerate(chosen,1):
   if cos[ri,ii]<.10:continue
   x=indicators[ii]
   candidates.append({'id':r['node_id']+'__'+x['node_id'],'document_id':r['document_id'],'indicator_document_id':x['document_id'],
      'fp':r['fp'],'indicator_fp':x['fp'],'source_node_id':r['node_id'],'target_node_id':x['node_id'],
      'result_node_id':r['node_id'],'indicator_node_id':x['node_id'],'author_result_node_id':author_id(r),'author_indicator_node_id':author_id(x),'tie_break_rule':'ascending_author_node_sha256_24','result_title':r['title'],'indicator_title':x['title'],
      'rank_for_result':rank,'cosine':float(cos[ri,ii]),'weight':float(cos[ri,ii]),'evidence_class':'semantic_candidate',
      'origin':'replayed_author_137_document_model_unique_indicator_titles','source_url':r['source_url'],'indicator_source_url':x['source_url'],
      'result_locator':r['source_locator'],'indicator_locator':x['source_locator'],'official_weight':None,
      'same_document':r['document_id']==x['document_id'],'review_status':'unreviewed','causal_status':'not_identified'})
 expected=json.loads((folder/'author_reference_tables.json').read_text());replication=[]
 def comparison(metric,actual,reference,tolerance=1e-12):
  difference=actual-reference;good=abs(difference)<=tolerance
  row={'metric':metric,'author_report':reference,'platform_recomputed':actual,'difference':difference,'equal':good,'tolerance':tolerance};replication.append(row)
  assert good,row
 for item in similarity:
  old=next(r for r in expected['project_similarity'] if {r['project_a'],r['project_b']}=={PROJECT,item['project_id']})
  comparison('project_cosine_'+item['project_id'],item['cosine'],float(old['cosine_similarity']))
  old=next(r for r in expected['stemming_project_sensitivity'] if {r['project_a'],r['project_b']}=={PROJECT,item['project_id']})
  comparison('stemmed_cosine_'+item['project_id'],item['stemmed_cosine'],float(old['russian_snowball_cosine']))
 for item in frame_totals:
  old=next(r for r in expected['project_frame_scores'] if r['frame_id']==item['frame_id'])
  comparison('frame_frequency_'+item['frame_id'],item['per1000'],float(old['weighted_frequency_per_1000']))
 comparison('semantic_candidate_count',len(candidates),20,0)
 comparison('candidate_results',len({r['result_node_id'] for r in candidates}),13,0)
 comparison('candidate_unique_indicators',len({r['indicator_node_id'] for r in candidates}),9,0)
 comparison('tfidf_features',matrix.shape[1],20000,0)
 comparison('tourism_profile_tokens',sum(d['profile_token_count'] for d in selected_metas),2188,0)
 checks+=replication
 corpus_meta=[{k:v for k,v in d.items() if k!='text'} for d in docs]
 result={'documents':selected_metas,'corpusDocuments':corpus_meta,'sameGenreTokenCount':2188,
   'corpusTokenCount':sum(d['profile_token_count'] for d in docs),'features':matrix.shape[1],
   'frames':frames,'frameScores':frame_scores,'projectFrameScores':frame_totals,'documentSimilarity':docsimilarity,
   'projectSimilarity':similarity,'topTerms':top,'sensitivity':sensitivity,'documentFiles':files,'profileCount':137,
   'contextCount':len(contexts),'method':cfg,'dictionary':dictionary,'replicationAudit':checks,
   'replicationStatus':'author_137_document_model_replayed_with_independent_tourism_source_matching',
   'authorExactCodeAvailable':True,'authorAnalysis':{'source_code_url':cfg['source_code_download'],
      'source_code_sha256':cfg['source_code_sha256'],'shared_profiles_url':cfg['shared_profiles_download'],
      'shared_profiles_sha256':cfg['shared_profiles_sha256'],'documents':137,'compared_structured_projects':10,
      'tourism_documents':6,'tourism_tokens':2188,'max_features':20000,'semantic_candidates':20,
      'candidate_results':13,'genreExcludedProfiles':['family'],'absentFromOriginalCorpus':['health_technologies'],
      'baseline_and_stemming_match_reference':True,'maximum_numeric_difference':max(abs(r['difference']) for r in replication),
      'all_tourism_source_profiles_verified':True},
   'notes':['Исходный TF–IDF рассчитан на фиксированных профилях 137 документов с максимумом 20 000 признаков.',
      'Межпроектные коэффициенты сравнивают средние нормированные профили десяти проектов одного жанра. Архивная «Семья» сохраняется в исходном корпусе и исключена из сопоставимого ранжирования.',
      'Все шесть профилей туристического проекта независимо сопоставлены с текстом адресуемых карточек сохранённых HTML. Пробелы между текстовыми узлами сохранены.',
      'Основная модель и русский стемминг повторяют исходную процедуру. Четыре дополнительных варианта чувствительности рассчитаны платформой.',
      'Тематические категории пересекаются. Лексический коэффициент не измеряет причинное влияние или долю общих расходов.']}
 for name,rows in [('text_corpus_profiles',corpus_meta),('text_units',[u for us in units.values() for u in us]),('text_kwic',contexts),
   ('frame_scores',frame_scores),('project_frame_scores',frame_totals),('document_similarity',docsimilarity),
   ('project_similarity',similarity),('text_sensitivity',sensitivity),('tfidf_top_terms',top),
   ('text_replication_audit',checks),('author_project_similarity',expected['project_similarity'])]:csv_write(output/(name+'.csv'),rows)
 return result,candidates
