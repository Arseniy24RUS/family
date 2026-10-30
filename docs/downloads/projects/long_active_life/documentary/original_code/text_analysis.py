#!/usr/bin/env python3
"""Source-resolved text and document-structure research, National Projects 1.2.0.
No downloads, API calls, hidden language models, or changes to the input databases.
"""
from __future__ import annotations
import argparse, collections, csv, gzip, hashlib, itertools, json, math, re, sqlite3, sys
from pathlib import Path
import numpy as np
import pandas as pd
from lxml import html
from scipy.cluster.hierarchy import linkage, dendrogram
from scipy.spatial.distance import squareform
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

FAMILY_SHA='50ad21c1ad1c94e3cf07857363333df120558617'
VERSION='1.2.0'
PROJECT_MAP={'health':'long_active_life','infrastructure':'life_infrastructure','ecology':'environment','export':'international_export','transport':'efficient_transport'}
PROJECT_NAMES={'family':'Семья','personnel':'Кадры','youth_children':'Молодёжь и дети','long_active_life':'Продолжительная и активная жизнь','life_infrastructure':'Инфраструктура для жизни','environment':'Экологическое благополучие','data_economy':'Экономика данных и цифровая трансформация государства','competitive_economy':'Эффективная и конкурентная экономика','efficient_transport':'Эффективная транспортная система','international_export':'Международная кооперация и экспорт','tourism':'Туризм и гостеприимство'}
STOPWORDS=set('и в во на с со по к ко у о об от до из за для при а но или либо что чтобы как так также это этот эта эти того том тех его ее их мы вы они он она оно будет будут были быть есть не ни же ли бы всего всего все всех каждого который которая которые которых через между над под после перед включая соответствии рамках осуществление осуществления реализация реализации российский российская российской российские российскую российским российскими российская федерация федерации федеральный федерального федеральной федеральные федеральных национальный национального национальной национальные национальных проект проекта проектов проектом программа программы программ году года годы лет год тыс руб рублей процент процентов единица единиц штука штук млн миллиард тысяч сведения информации информация'.split())
TOKEN_RE=re.compile(r'[а-яёa-z]{2,}(?:-[а-яёa-z]{2,})?',re.I)
# Word-start constraints prevent the legacy substring errors эко -> экономика and прав -> управление.
FRAMES={
 'demography_family':('Демография и семья',[r'\bрождаем[а-я]*',r'\bдеторожд[а-я]*',r'\bмногодет[а-я]*',r'\bсемь[а-я]*',r'\bсемейн[а-я]*',r'\bдемограф[а-я]*']),
 'reproductive_health':('Репродуктивное здоровье',[r'\bрепродуктив[а-я]*',r'\bберемен[а-я]*',r'\bперинатал[а-я]*',r'\bмладенчес[а-я]*',r'\bэко\b',r'\bженск[а-я]*\s+консультац[а-я]*']),
 'clinical_health':('Медицинская помощь',[r'\bмедицин[а-я]*',r'\bздравоохран[а-я]*',r'\bлечен[а-я]*',r'\bзаболеван[а-я]*',r'\bбольниц[а-я]*',r'\bполиклиник[а-я]*']),
 'healthy_life_care':('Здоровый образ жизни и уход',[r'\bздоров[а-я]*',r'\bдолголет[а-я]*',r'\bпожил[а-я]*',r'\bдолговременн[а-я]*\s+уход[а-я]*',r'\bстарш[а-я]*\s+поколен[а-я]*',r'\bфизическ[а-я]*\s+культур[а-я]*']),
 'education_youth':('Образование и молодёжь',[r'\bобразован[а-я]*',r'\bобразовательн[а-я]*',r'\bшкол[а-я]*',r'\bучител[а-я]*',r'\bмолодеж[а-я]*',r'\bстудент[а-я]*',r'\bвуз[а-я]*']),
 'employment_skills':('Занятость и квалификация',[r'\bзанятост[а-я]*',r'\bтрудоустрой[а-я]*',r'\bбезработ[а-я]*',r'\bкадр[а-я]*',r'\bквалификац[а-я]*',r'\bработодател[а-я]*',r'\bпрофесс[а-я]*']),
 'income_support':('Доходы и социальная поддержка',[r'\bбедност[а-я]*',r'\bдоход[а-я]*',r'\bпособи[а-я]*',r'\bвыплат[а-я]*',r'\bсоциальн[а-я]*\s+поддержк[а-я]*',r'\bматеринск[а-я]*\s+капитал[а-я]*']),
 'housing_urban':('Жильё и городская среда',[r'\bжилищ[а-я]*',r'\bжил[а-я]*\s+(?:дом[а-я]*|площад[а-я]*)',r'\bипотек[а-я]*',r'\bблагоустрой[а-я]*',r'\bкоммунальн[а-я]*',r'\bгородск[а-я]*\s+сред[а-я]*']),
 'transport_logistics':('Транспорт и логистика',[r'\bтранспорт[а-я]*',r'\bдорог[а-я]*',r'\bжелезнодорож[а-я]*',r'\bавиа[а-я]*',r'\bпорт[а-я]*',r'\bперевоз[а-я]*',r'\bлогист[а-я]*']),
 'environment_climate':('Окружающая среда и климат',[r'\bэколог[а-я]*',r'\bклимат[а-я]*',r'\bотход[а-я]*',r'\bзагрязн[а-я]*',r'\bвыброс[а-я]*',r'\bбиоразнообраз[а-я]*',r'\bприрод[а-я]*']),
 'tourism':('Туризм и гостеприимство',[r'\bтуриз[а-я]*',r'\bтурист[а-я]*',r'\bгостиниц[а-я]*',r'\bгостеприим[а-я]*',r'\bпутешеств[а-я]*']),
 'digital_data':('Цифровая среда и данные',[r'\bцифров[а-я]*',r'\bданн[а-я]*',r'\bинформационн[а-я]*\s+(?:систем[а-я]*|технолог[а-я]*|безопасност[а-я]*)',r'\bинтернет[а-я]*',r'\bпрограммно[а-я]*\s+обеспечен[а-я]*',r'\bискусственн[а-я]*\s+интеллект[а-я]*']),
 'enterprise_industry':('Предпринимательство и производство',[r'\bпредприним[а-я]*',r'\bпромышлен[а-я]*',r'\bпроизводств[а-я]*',r'\bпроизводительност[а-я]*',r'\bинвестиц[а-я]*',r'\bбизнес[а-я]*']),
 'export_trade':('Экспорт и международная торговля',[r'\bэкспорт[а-я]*',r'\bимпорт[а-я]*',r'\bвнешнеторгов[а-я]*',r'\bмеждународн[а-я]*\s+кооперац[а-я]*',r'\bнесырьев[а-я]*']),
 'culture_values':('Культура и ценности',[r'\bкультур[а-я]*',r'\bценност[а-я]*',r'\bискусств[а-я]*',r'\bтрадиц[а-я]*',r'\bтворчеств[а-я]*',r'\bнаследи[а-я]*']),
 'science_innovation':('Наука и инновации',[r'\bнаучн[а-я]*',r'\bисследован[а-я]*',r'\bинновац[а-я]*',r'\bразработк[а-я]*',r'\bтехнологическ[а-я]*']),
 'access_rights':('Доступность и права',[r'\bправ(?:о|а|у|ом|е|ами|ах)?\b',r'\bдоступност[а-я]*',r'\bдоступн[а-я]*',r'\bинвалид[а-я]*',r'\bравн[а-я]*\s+возможност[а-я]*']),
 'governance_evidence':('Управление и оценка',[r'\bмониторинг[а-я]*',r'\bуправлен[а-я]*',r'\bкоординац[а-я]*',r'\bоценк[а-я]*',r'\bстатист[а-я]*',r'\bэффективност[а-я]*']),
}
COMPILED={k:re.compile('|'.join('(?:'+p+')' for p in pats)) for k,(_,pats) in FRAMES.items()}

def j(x):return json.dumps(x,ensure_ascii=False,sort_keys=True)
def ident(*xs):return hashlib.sha256('\x1f'.join(map(str,xs)).encode()).hexdigest()[:24]
def ws(x):return re.sub(r'\s+',' ',str(x or '')).strip()
def norm(x):return ws(x).lower().replace('ё','е')
def tokens(x):return TOKEN_RE.findall(norm(x))
def filehash(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def textof(el):return ws(el.text_content()) if el is not None else ''
def cls(el,name):return name in (el.get('class') or '').split()
def class_nodes(el,name):return el.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," '+name+' ")]')
def nearest_details(el):return next((a for a in el.iterancestors() if a.tag=='details'),None)
def records(path):
 with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def read_only(p):
 c=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c

def clean_pdf_pages(pages):
 # Only short repeated lines are removed, never substantive long sentences.
 counts=collections.Counter()
 for _,text in pages:
  counts.update(set(ws(line) for line in text.splitlines() if 1<len(ws(line))<150))
 threshold=max(3,math.ceil(len(pages)*.40))
 repeated={line for line,n in counts.items() if n>=threshold and (re.search('паспорт|система гарант|национальн|федеральн|страниц|[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}',line.lower()) or len(line)<55)}
 result=[]
 for page,text in pages:
  kept=[line for line in text.splitlines() if ws(line) not in repeated and not re.fullmatch(r'[\s\d.,:;№/()\-–—%]+',line)]
  cleaned=re.sub(r'(?<=[а-яА-Я])-\s*\n\s*(?=[а-яА-Я])','', '\n'.join(kept))
  result.append((page,ws(cleaned)))
 return result,sorted(repeated)

def extract(package):
 c=read_only(package/'corpus/data/catalog.sqlite3')
 docs=[];units=[];nodes=[];evidence=[];edges=[];claims=[];indicator_task_claims=[];doclinks=[];bodytexts={};removed=[]
 node_by_key={}; unit_ids=set(); docnodes=collections.defaultdict(list)
 def addnode(doc,kind,title,description='',field=None,xpath='',card_id='',extra=None):
  nid=ident('node',kind,doc['document_id'],(extra or {}).get('canonical_key') or xpath or (field['path'] if field else ''),title)
  if nid in node_by_key:return node_by_key[nid]
  r={'node_id':nid,'project_id':doc['project_id'],'kind':kind,'title':ws(title),'description':ws(description),'document_id':doc['document_id'],'source_sha256':doc['source_sha256'],'source_xpath':xpath,'source_card_id':card_id,'source_field_path':field['path'] if field else '', 'source_field_index':field['field_index'] if field else None,'source_url':doc['source_url'],'local_file':doc['local_file'],'source_version':doc['source_version'],'document_level':doc['document_level'],'indicator_code_local':'','unit':'','has_explicit_deadline':0,'has_explicit_unit':0,'has_explicit_responsible':0,'has_numeric_target':0,'record_status':'documentary_extraction'}
  if extra:r.update(extra)
  nodes.append(r);node_by_key[nid]=r;docnodes[doc['document_id']].append(r)
  evidence.append({'evidence_id':ident(nid,xpath,r['source_field_index']),'node_id':nid,**{k:r[k] for k in ['document_id','source_sha256','source_xpath','source_field_path','source_field_index','source_url','local_file','source_version']},'evidence_text':ws(title)+' '+ws(description)})
  return r
 def addunit(doc,kind,text,locator,field_index=None,page=None,parent='',include=1):
  text=ws(text)
  if not text:return
  uid=ident(doc['document_id'],kind,locator)
  if uid in unit_ids:return
  unit_ids.add(uid)
  units.append({'unit_id':uid,'document_id':doc['document_id'],'project_id':doc['project_id'],'unit_kind':kind,'text':text,'n_tokens':len(tokens(text)),'source_locator':locator,'page_number':page,'source_field_index':field_index,'parent_node_id':parent,'include_document_profile':include,'text_hash':ident(norm(text)),'source_sha256':doc['source_sha256'],'source_url':doc['source_url'],'local_file':doc['local_file'],'source_version':doc['source_version']})
 def addedge(a,b,kind,relation,doc,xpath,text,score=None):
  edges.append({'edge_id':ident(a,b,kind,relation,doc['document_id'],xpath),'project_id':doc['project_id'],'source_node_id':a,'target_node_id':b,'evidence_class':kind,'relation':relation,'weight':1.0 if score is None else score,'weight_meaning':'binary_documentary_relation' if score is None else 'lexical_cosine','document_id':doc['document_id'],'source_sha256':doc['source_sha256'],'source_xpath':xpath,'source_url':doc['source_url'],'local_file':doc['local_file'],'source_version':doc['source_version'],'evidence_text':ws(text)})
 web=[dict(r) for r in c.execute('select * from web_documents order by case document_level when "national" then 0 else 1 end,project,url')]
 docurl={}
 for w in web:
  d={'document_id':'html:'+w['sha256'],'project_id':PROJECT_MAP.get(w['project'],w['project']),'source_sha256':w['sha256'],'source_kind':w['source_type'],'document_level':w['document_level'],'title':w['title'] or w['url'],'source_url':w['url'],'local_file':'corpus/data/'+w['html_path'],'source_version':' | '.join(filter(None,[w['publisher_version_label'],w['publisher_updated_label'],w['period_label'],w['retrieved_at']])),'genre':'html_passport' if w['source_type']=='secondary_epbs_rendering' else 'legal_republication','input_token_count':len(tokens(w['text'])),'profile_status':'included','source_period':w['period_label'],'publisher_version':w['publisher_version_label'],'snapshot_at':w['retrieved_at']}
  docs.append(d);docurl[w['url']]=d;doclinks.append({'document_id':d['document_id'],'project_id':d['project_id'],'association':'catalogue_project'})
  if w['source_type']!='secondary_epbs_rendering':
   cleaned=ws(w['text']);bodytexts[d['document_id']]=cleaned;addunit(d,'html_unstructured',cleaned,'full_text');continue
  tree=html.parse(str(package/d['local_file']));fields=[dict(r) for r in c.execute('select * from web_fields where sha256=? order by field_index',(w['sha256'],))]
  result_by_ctx={};goal=None;indicator_by_title=collections.defaultdict(list);tasks_by_id={}
  schedule_by_context=collections.defaultdict(list)
  for measure in c.execute('select context_json,period_raw,value_decimal,value_role from web_measurements where sha256=? and series_kind in ("indicator_year","result_date")',(w['sha256'],)):
   schedule_by_context[j(json.loads(measure['context_json']))].append(dict(measure))
  # A task title may exist only in the DOM summary, not as a web_fields label.
  for taskcard in tree.xpath('//*[starts-with(@id,"passport-task-")]'):
   title_nodes=class_nodes(taskcard,'db-result-fold-title');title=textof(title_nodes[0]) if title_nodes else textof(taskcard.find('summary'))
   if not title:continue
   taskid=taskcard.get('id');taskxp=tree.getpath(taskcard)
   tn=addnode(d,'task',title,xpath=taskxp,card_id=taskid,extra={'task_code':taskid.removeprefix('passport-task-'),'record_status':'documentary_dom_task_card'})
   tasks_by_id[taskid]=tn;addunit(d,'task',title,taskxp,parent=tn['node_id'])
  fields_ordered=sorted(fields,key=lambda f:(0 if f['label']=='Задача' else 1,f['field_index']))
  for f in fields_ordered:
   label=f['label'];ctx=json.loads(f['context_json'])
   if label not in ['Цель проекта','Задача','Код показателя','Характеристика результата']:continue
   matches=tree.xpath('/html'+f['path'])
   if not matches:raise ValueError('Unresolved stored field XPath: '+f['path'])
   el=matches[0];card=nearest_details(el);xp=tree.getpath(card) if card is not None else tree.getpath(el)
   if label=='Цель проекта':
    node=addnode(d,'goal',f['value_raw'],field=f,xpath=tree.getpath(el));goal=node
   elif label=='Задача':
    node=addnode(d,'task',f['value_raw'],field=f,xpath=xp,card_id=card.get('id') or '' if card is not None else '')
    code_fields=[e for e in card.xpath('.//dt') if textof(e)=='Код задачи'] if card is not None else []
    code=textof(code_fields[0].getnext()) if code_fields else ''
    node['task_code']=code
    if node['source_card_id']:tasks_by_id[node['source_card_id']]=node
   else:
    title_nodes=class_nodes(card,'db-result-fold-title');title=textof(title_nodes[0]) if title_nodes else textof(card.find('summary'))
    meta={}
    for dt in card.xpath('.//dt'):
     anc=nearest_details(dt)
     if anc is card:meta[textof(dt)]=textof(dt.getnext())
    kind='indicator' if label=='Код показателя' else 'result'
    node=addnode(d,kind,title,description=f['value_raw'] if kind=='result' else '',field=f,xpath=xp,card_id=card.get('id') or '',extra={'indicator_code_local':f['value_raw'] if kind=='indicator' else '', 'unit':meta.get('Единица измерения',''),'has_explicit_unit':int(bool(meta.get('Единица измерения'))),'has_explicit_deadline':int(bool(re.search(r'20\d{2}',meta.get('Срок реализации','')))),'has_explicit_responsible':int(bool(meta.get('Ответственный исполнитель') or meta.get('Ответственный за показатель') or meta.get('Организация ответственного исполнителя'))),'has_numeric_target':int(bool(meta.get('Итоговое значение результата') and re.search(r'\d',meta['Итоговое значение результата']))),'metadata_json':j(meta)})
    schedule=schedule_by_context.get(j(ctx),[])
    node['has_explicit_schedule_period']=int(any(re.search(r'20\d{2}',m['period_raw']) for m in schedule))
    node['has_numeric_schedule_value']=int(any(m['value_decimal'] is not None for m in schedule))
    node['has_explicit_planned_numeric_value']=int(any(m['value_decimal'] is not None and m['value_role']=='plan' for m in schedule))
    node['schedule_rows']=len(schedule)
    node['has_numeric_target']=int(bool(node['has_numeric_target'] or node['has_explicit_planned_numeric_value']))
    if kind=='result':
     result_by_ctx[ctx[2]]=node
     taskparts=class_nodes(card,'db-result-task')
     if taskparts:
      p=taskparts[0];tasktext=re.sub(r'^Задача:\s*','',textof(p));mt=re.match(r'^([^–—-]+)\s*[–—-]\s*(.+)$',tasktext)
      taskname=mt.group(2) if mt else tasktext;code=mt.group(1).strip() if mt else ''
      anchors=p.xpath('.//a[starts-with(@href,"#")]/@href');href=anchors[0] if anchors else ''
      tasknode=tasks_by_id.get(href[1:]) if href else None
      resolution='same_document_exact_anchor' if tasknode is not None else 'unresolved_anchor_literal_reference'
      if tasknode is None:
       tasknode=addnode(d,'task_reference',taskname,xpath=tree.getpath(p),extra={'task_code':code,'canonical_key':'taskref:'+code+':'+norm(taskname),'reference_href':href,'record_status':'unresolved_anchor_task_reference'})
      addedge(node['node_id'],tasknode['node_id'],'explicit_documentary','result_declares_task',d,tree.getpath(p),textof(p))
      edges[-1]['reference_href']=href;edges[-1]['target_resolution']=resolution
    else:
     indicator_by_title[norm(title)].append(node)
     for p in class_nodes(card,'db-purpose-task'):
      taskname=textof(p)
      canonical=list({tn['node_id']:tn for tn in tasks_by_id.values() if norm(tn['title'])==norm(taskname)}.values())
      matches=canonical if canonical else [tn for tn in docnodes[d['document_id']] if tn['kind']=='task' and norm(tn['title'])==norm(taskname)]
      resolution='unique_exact_same_document_task_name' if len(matches)==1 else ('ambiguous_same_document_task_name' if len(matches)>1 else 'unresolved_task_name')
      claim={'claim_id':ident(d['document_id'],tree.getpath(p)),'project_id':d['project_id'],'indicator_node_id':node['node_id'],'target_label_raw':taskname,'target_node_id':matches[0]['node_id'] if len(matches)==1 else '', 'resolution':resolution,'source_sha256':d['source_sha256'],'document_id':d['document_id'],'source_xpath':tree.getpath(p),'source_url':d['source_url'],'local_file':d['local_file'],'source_version':d['source_version']}
      indicator_task_claims.append(claim)
      if len(matches)==1:
       addedge(node['node_id'],matches[0]['node_id'],'explicit_documentary','indicator_declares_task',d,tree.getpath(p),taskname)
       edges[-1]['target_resolution']=resolution

   addunit(d,node['kind'],node['title']+' '+node['description'],xp,f['field_index'],parent=node['node_id'])
  for node in docnodes[d['document_id']]:
   if goal and node['node_id']!=goal['node_id'] and node['kind'] in ('indicator','result','task'):
    addedge(goal['node_id'],node['node_id'],'structural_inference','same_passport_membership',d,node['source_xpath'],d['title'])
  # Control points are actions, kept separate from result/output cards and annual targets.
  for f in fields:
   ctx=json.loads(f['context_json'])
   if f['label']=='Характеристика' and len(ctx)>3 and any(str(x).startswith('Контрольные точки') for x in ctx):
    parent=result_by_ctx.get(ctx[2]);addunit(d,'milestone',f['value_raw'],f['path'],f['field_index'],parent=parent['node_id'] if parent else '',include=0)
   if f['label']=='Влияние результата на показатель':
    parent=result_by_ctx.get(ctx[2]) if len(ctx)>2 else None
    target=ctx[-1] if ctx else ''
    match=indicator_by_title.get(norm(target),[])
    claim={'claim_id':ident(d['document_id'],f['field_index']),'project_id':d['project_id'],'source_node_id':parent['node_id'] if parent else '', 'target_label_raw':target,'reported_weight_raw':f['value_raw'],'resolution':'exact_unique_indicator_title' if len(match)==1 else ('ambiguous_indicator_title' if len(match)>1 else 'unresolved_target'),'target_node_id':match[0]['node_id'] if len(match)==1 else '', 'source_sha256':d['source_sha256'],'document_id':d['document_id'],'source_xpath':'/html'+f['path'],'source_field_index':f['field_index'],'source_url':d['source_url'],'local_file':d['local_file'],'source_version':d['source_version'],'context_json':f['context_json']}
    claims.append(claim)
    if parent and len(match)==1:addedge(parent['node_id'],match[0]['node_id'],'explicit_documentary','source_claim_exact_indicator_title',d,claim['source_xpath'],target)
  # Repeated control points and organisational metadata do not dominate the main document vector.
  profile=list(dict.fromkeys(norm(u['text']) for u in units if u['document_id']==d['document_id'] and u['include_document_profile']))
  bodytexts[d['document_id']]='\n'.join(profile)
  if not bodytexts[d['document_id']]:d['profile_status']='no_structured_business_text'
 # Parent-national / child-federal links are source membership, not a causal edge.
 for l in c.execute('select * from web_project_links'):
  a=next((x for x in docs if x['source_sha256']==l['parent_sha256']),None);b=docurl.get(l['child_url'])
  if a and b:
   doclinks.append({'document_id':b['document_id'],'project_id':a['project_id'],'association':'explicit_national_federal_link'})
   ag=[n for n in docnodes[a['document_id']] if n['kind']=='goal'];bg=[n for n in docnodes[b['document_id']] if n['kind']=='goal']
   if ag and bg:addedge(ag[0]['node_id'],bg[0]['node_id'],'explicit_documentary','national_contains_federal_passport',a,'web_project_links',l['link_text'])
 # PDF content is a separate genre and edition, never concatenated into the HTML denominator.
 for o in c.execute('select * from objects order by sha256'):
  refs=[dict(x) for x in c.execute('select s.project,s.project_name,sd.*,s.expected_kind from source_documents sd join sources s on s.id=sd.source_id where sd.sha256=? order by sd.source_id',(o['sha256'],))]
  if not refs:continue
  r=refs[0];project=PROJECT_MAP.get(r['project'],r['project']);kind=r['verified_kind'] or r['expected_kind']
  d={'document_id':'pdf:'+o['sha256'],'project_id':project,'source_sha256':o['sha256'],'source_kind':'pdf_archive','document_level':'federal' if 'federal' in kind else ('national' if 'national' in kind else 'other'),'title':r['project_name']+' | '+kind+' | '+o['sha256'][:8],'source_url':r['final_url'],'local_file':'corpus/data/'+o['path'],'source_version':'sha256:'+o['sha256']+' | retrieved:'+r['retrieved_at'],'genre':kind,'input_token_count':0,'profile_status':'included_separate_pdf_genre','source_period':'','publisher_version':'','snapshot_at':r['retrieved_at']}
  pages=[(x['page_number'],x['text']) for x in c.execute('select * from page_text where sha256=? order by page_number',(o['sha256'],))]
  cleaned,headers=clean_pdf_pages(pages);d['input_token_count']=sum(len(tokens(t)) for _,t in pages);d['page_count']=len(pages)
  docs.append(d);bodytexts[d['document_id']]='\n'.join(text for _,text in cleaned)
  for rr in refs:doclinks.append({'document_id':d['document_id'],'project_id':PROJECT_MAP.get(rr['project'],rr['project']),'association':'source_document_registry'})
  for line in headers:removed.append({'document_id':d['document_id'],'removed_line':line,'rule':'repeated_short_header_or_footer'})
  for page,text in cleaned:addunit(d,'pdf_page',text,'page:'+str(page),page=page)
 # Family original text and page extracts are pinned reference evidence, not newly OCRed PDFs.
 ref=package/'research/text_support/family_reference';familypages=records(ref/'nlp_page_texts_extracted.csv')
 for old in records(ref/'nlp_document_texts_extracted.csv'):
  did='family:'+old['document_id'];pages=[(int(x['page']),x['text']) for x in familypages if x['document_id']==old['document_id']]
  cleaned,headers=clean_pdf_pages(pages)
  d={'document_id':did,'project_id':'family','source_sha256':hashlib.sha256(old['text'].encode()).hexdigest(),'source_kind':'family_archived_extraction','document_level':'national' if 'project' in old['document_id'] else 'strategy','title':old['file_name'],'source_url':f'https://github.com/Arseniy24RUS/family/blob/{FAMILY_SHA}/public/downloads/data/nlp_document_texts_extracted.csv','local_file':'research/text_support/family_reference/nlp_document_texts_extracted.csv','source_version':'Git commit '+FAMILY_SHA,'genre':'family_presentation' if 'presentation' in old['document_id'] else ('family_passport' if 'passport' in old['document_id'] else 'family_strategy'),'input_token_count':len(tokens(old['text'])),'profile_status':'reference_genre_only','source_period':'','publisher_version':'','snapshot_at':'','page_count':len(pages)}
  docs.append(d);bodytexts[did]='\n'.join(text for _,text in cleaned);doclinks.append({'document_id':did,'project_id':'family','association':'pinned_family_reference'})
  for page,text in cleaned:addunit(d,'family_reference_page',text,'page:'+str(page),page=page)
  for line in headers:removed.append({'document_id':did,'removed_line':line,'rule':'repeated_short_header_or_footer'})
 file_hash_cache={}
 for d in docs:
  d['hash_kind']='extracted_document_text_utf8' if d['source_kind']=='family_archived_extraction' else 'source_file_bytes'
  if d['local_file'] not in file_hash_cache:file_hash_cache[d['local_file']]=filehash(package/d['local_file'])
  d['local_file_sha256']=file_hash_cache[d['local_file']]
  d['profile_token_count']=len(tokens(bodytexts[d['document_id']]));d['profile_text_sha256']=hashlib.sha256(bodytexts[d['document_id']].encode()).hexdigest()
 doc_by_id={d['document_id']:d for d in docs}
 for u in units:
  u['hash_kind']=doc_by_id[u['document_id']]['hash_kind']
  u['local_file_sha256']=doc_by_id[u['document_id']]['local_file_sha256']
 c.close()
 # Attach the reviewed 1.1 mapping by exact SHA + source card ID, without semantic remapping.
 registry=[];lookup=collections.defaultdict(list)
 for n in nodes:
  if n['kind']=='indicator':lookup[(n['source_sha256'],n['source_card_id'])].append(n)
 for m in json.loads((package/'inputs/target_update/mappings.json').read_text()):
  for n in lookup.get((m['source_sha256'],m['source_locator']),[]):
   registry.append({'node_id':n['node_id'],'project_id':n['project_id'],'mapping_id':m['mapping_id'],'target_series_id':m['target_series_id'],'statistical_indicator_code':m['indicator_code'],'mapping_status':m['mapping_status'],'match_method':'exact_source_sha_and_card_id','formal_attainment_eligible':0})
 return {'documents':docs,'units':units,'nodes':nodes,'node_evidence':evidence,'edges':edges,'link_claims':claims,'indicator_task_claims':indicator_task_claims,'document_projects':list({(x['document_id'],x['project_id'],x['association']):x for x in doclinks}.values()),'removed_boilerplate':removed,'indicator_registry_links':registry},bodytexts

def lexical(tables,texts,out):
 docs=tables['documents'];units=tables['units'];valid=[d for d in docs if len(tokens(texts[d['document_id']]))>=10]
 vectorizer=TfidfVectorizer(lowercase=True,token_pattern=r'(?u)\b[а-яa-z][а-яa-z-]{1,}\b',preprocessor=norm,stop_words=sorted(STOPWORDS),ngram_range=(1,2),max_features=20000,min_df=1,max_df=.98,sublinear_tf=True,norm='l2',smooth_idf=True)
 x=vectorizer.fit_transform([texts[d['document_id']] for d in valid]);terms=vectorizer.get_feature_names_out();cos=cosine_similarity(x)
 top=[];freq=[];scores=[];kwic=[];cooc=collections.Counter();coocden=collections.Counter();frame_units=collections.defaultdict(list)
 for i,d in enumerate(valid):
  row=x.getrow(i);ids=row.indices[np.argsort(-row.data)[:50]]
  for rank,k in enumerate(ids,1):top.append({'document_id':d['document_id'],'project_id':d['project_id'],'rank':rank,'term':terms[k],'tfidf':float(x[i,k]),'source_url':d['source_url'],'source_version':d['source_version']})
  ct=collections.Counter(t for t in tokens(texts[d['document_id']]) if t not in STOPWORDS)
  for term,n in ct.most_common(100):freq.append({'document_id':d['document_id'],'project_id':d['project_id'],'term':term,'count':n,'per_1000_tokens':n/d['profile_token_count']*1000})
  for fid,rx in COMPILED.items():
   n=len(list(rx.finditer(norm(texts[d['document_id']]))));scores.append({'document_id':d['document_id'],'project_id':d['project_id'],'genre':d['genre'],'frame_id':fid,'frame_name':FRAMES[fid][0],'count':n,'n_tokens':d['profile_token_count'],'per_1000_tokens':n/d['profile_token_count']*1000,'dictionary_version':'cross_project_v1','count_policy':'nonoverlapping_union_within_frame; overlapping_between_frames_allowed'})
 # KWIC and co-occurrence use source units, not an invented common page for HTML.
 for u in units:
  if u['unit_kind']=='milestone':continue
  s=norm(u['text']);found=[];coocden[(u['project_id'],u['unit_kind'])]+=1
  for fid,rx in COMPILED.items():
   matches=list(rx.finditer(s))
   if matches:
    found.append(fid);frame_units[(u['document_id'],fid)].append(u['unit_id'])
    # Up to three examples per source unit/frame, with explicit retained/excluded counts in method.
    for m in matches[:3]:kwic.append({'unit_id':u['unit_id'],'document_id':u['document_id'],'project_id':u['project_id'],'frame_id':fid,'matched_text':m.group(),'start_offset_normalized':m.start(),'end_offset_normalized':m.end(),'context':s[max(0,m.start()-100):min(len(s),m.end()+100)],'source_locator':u['source_locator'],'page_number':u['page_number'],'source_field_index':u['source_field_index'],'source_url':u['source_url'],'local_file':u['local_file'],'source_version':u['source_version']})
  for a,b in itertools.combinations(sorted(found),2):cooc[(u['project_id'],u['unit_kind'],a,b)]+=1
 pairs=[]
 for i,d in enumerate(valid):
  for k in range(i+1,len(valid)):
   e=valid[k];pairs.append({'document_a':d['document_id'],'document_b':e['document_id'],'project_a':d['project_id'],'project_b':e['project_id'],'genre_a':d['genre'],'genre_b':e['genre'],'cosine_similarity':float(cos[i,k]),'same_genre':int(d['genre']==e['genre']),'same_project':int(d['project_id']==e['project_id'])})
 tables.update({'tfidf_top_terms':top,'lexical_frequencies':freq,'frame_scores':scores,'kwic':kwic,'concept_cooccurrence':[{'project_id':p,'unit_kind':uk,'frame_a':a,'frame_b':b,'cooccurring_units':n,'eligible_units':coocden[(p,uk)],'share_units':n/coocden[(p,uk)]} for (p,uk,a,b),n in sorted(cooc.items())],'document_similarity':pairs,'vocabulary':[{'term':t,'idf':float(vectorizer.idf_[i])} for i,t in enumerate(terms)]})
 # Source-balanced project profiles: structured HTML only for ten new projects. Family retains a separate genre.
 project_vectors=[];project_order=[];project_scores=[]
 for p in sorted(PROJECT_NAMES):
  ids=[i for i,d in enumerate(valid) if d['project_id']==p and (d['source_kind']=='secondary_epbs_rendering' or (p=='family' and d['genre']=='family_passport'))]
  if not ids:continue
  v=np.asarray(x[ids].mean(axis=0)).ravel();v/=np.linalg.norm(v) or 1
  project_vectors.append(v);project_order.append(p)
  pdids={valid[i]['document_id'] for i in ids}
  for fid in FRAMES:
   rr=[r for r in scores if r['document_id'] in pdids and r['frame_id']==fid]
   project_scores.append({'project_id':p,'frame_id':fid,'documents':len(rr),'mean_document_frequency_per_1000':sum(r['per_1000_tokens'] for r in rr)/len(rr),'weighted_frequency_per_1000':sum(r['count'] for r in rr)/sum(r['n_tokens'] for r in rr)*1000,'scope':'one_family_passport_reference' if p=='family' else 'deduplicated_structured_html_passports','comparable_genre_with_other_projects':int(p!='family')})
 pcos=cosine_similarity(project_vectors);tables['project_similarity']=[{'project_a':a,'project_b':b,'cosine_similarity':float(pcos[i,k]),'family_genre_mismatch':int('family' in (a,b))} for i,a in enumerate(project_order) for k,b in enumerate(project_order) if i<k];tables['project_frame_scores']=project_scores
 dist=np.clip(1-pcos,0,2);np.fill_diagonal(dist,0);z=linkage(squareform(dist,checks=True),method='average')
 tables['project_dendrogram']=[{'step':i,'left_cluster':int(r[0]),'right_cluster':int(r[1]),'distance':float(r[2]),'n_leaves':int(r[3]),'leaf_order_json':j(project_order)} for i,r in enumerate(z)]
 # Reproduce the legacy four-document TF-IDF as a separate reference calculation.
 return vectorizer,x,valid,cos,project_order,pcos,z

def stemming_sensitivity(tables,texts,valid,primary_cos,project_order,primary_project_cos):
 try:
  import nltk
  from nltk.stem.snowball import SnowballStemmer
 except ImportError:
  tables['stemming_sensitivity_summary']=[{'status':'not_run_missing_dependency','required_package':'nltk==3.9.2','meaning':'primary_analysis_still_available'}]
  return
 from scipy.stats import spearmanr
 stemmer=SnowballStemmer('russian',ignore_stopwords=False)
 from functools import lru_cache
 stem=lru_cache(maxsize=200000)(stemmer.stem)
 normalized=[' '.join(stem(t) for t in tokens(texts[d['document_id']]) if t not in STOPWORDS) for d in valid]
 model=TfidfVectorizer(token_pattern=r'(?u)\b[а-яa-z][а-яa-z-]{1,}\b',ngram_range=(1,2),max_features=20000,min_df=1,max_df=.98,sublinear_tf=True,smooth_idf=True,norm='l2')
 mat=model.fit_transform(normalized);sim=cosine_similarity(mat);rows=[];a=[];b=[]
 for i,d in enumerate(valid):
  for k in range(i+1,len(valid)):
   e=valid[k];v=float(sim[i,k]);u=float(primary_cos[i,k]);a.append(u);b.append(v)
   rows.append({'document_a':d['document_id'],'document_b':e['document_id'],'project_a':d['project_id'],'project_b':e['project_id'],'primary_surface_cosine':u,'russian_snowball_cosine':v,'difference_stem_minus_surface':v-u,'same_genre':int(d['genre']==e['genre']),'same_project':int(d['project_id']==e['project_id'])})
 pv=[]
 for p in project_order:
  ids=[i for i,d in enumerate(valid) if d['project_id']==p and (d['source_kind']=='secondary_epbs_rendering' or (p=='family' and d['genre']=='family_passport'))]
  v=np.asarray(mat[ids].mean(axis=0)).ravel();v/=np.linalg.norm(v) or 1;pv.append(v)
 psim=cosine_similarity(pv);pr=[];pa=[];pb=[];qa=[];qb=[];neighbors=[]
 for i,p in enumerate(project_order):
  ptop=sorted([k for k in range(len(project_order)) if k!=i],key=lambda k:-primary_project_cos[i,k])[:3]
  stop=sorted([k for k in range(len(project_order)) if k!=i],key=lambda k:-psim[i,k])[:3]
  neighbors.append({'project_id':p,'primary_top3_json':j([project_order[k] for k in ptop]),'stemmed_top3_json':j([project_order[k] for k in stop]),'intersection_top3':len(set(ptop)&set(stop)),'jaccard_top3':len(set(ptop)&set(stop))/len(set(ptop)|set(stop))})
  for k in range(i+1,len(project_order)):
   q=project_order[k];u=float(primary_project_cos[i,k]);v=float(psim[i,k]);pa.append(u);pb.append(v)
   if 'family' not in (p,q):qa.append(u);qb.append(v)
   pr.append({'project_a':p,'project_b':q,'primary_surface_cosine':u,'russian_snowball_cosine':v,'difference_stem_minus_surface':v-u,'family_genre_mismatch':int('family' in (p,q))})
 tables['stemming_document_sensitivity']=rows;tables['stemming_project_sensitivity']=pr;tables['stemming_neighbor_sensitivity']=neighbors
 tables['stemming_sensitivity_summary']=[{'status':'completed','algorithm':'NLTK SnowballStemmer Russian','nltk_version':nltk.__version__,'external_corpus_downloads':0,'lemmatization_performed':0,'stemmed_tfidf_features':len(model.vocabulary_),'document_pairs':len(rows),'document_pair_rank_spearman':float(spearmanr(a,b).statistic),'project_pair_rank_spearman_all11':float(spearmanr(pa,pb).statistic),'project_pair_rank_spearman_html10':float(spearmanr(qa,qb).statistic),'mean_abs_document_cosine_change':float(np.mean(np.abs(np.array(b)-a))),'max_abs_document_cosine_change':float(np.max(np.abs(np.array(b)-a))),'meaning':'descriptive_sensitivity; correlated_pairs_no_pvalue_claim; stemming_not_lemmatization'}]


def semantics(tables,vectorizer):
 nodes=tables['nodes'];byid={n['node_id']:n for n in nodes};candidates=[];coverage=[];formal=[];domains=[]
 inds=[n for n in nodes if n['kind']=='indicator'];results=[n for n in nodes if n['kind']=='result']
 iv=vectorizer.transform([n['title'] for n in inds]);rv=vectorizer.transform([n['title']+' '+n['description'] for n in results]);sim=cosine_similarity(rv,iv)
 registry=collections.defaultdict(set)
 for r in tables['indicator_registry_links']:
  if r['mapping_status']=='approved':registry[r['node_id']].add(r['statistical_indicator_code'])
 for i,r in enumerate(results):
  eligible=[k for k,n in enumerate(inds) if n['project_id']==r['project_id']]
  chosen=sorted(eligible,key=lambda k:(-sim[i,k],inds[k]['node_id']))[:3]
  for rank,k in enumerate(chosen,1):
   if sim[i,k]<.10:continue
   n=inds[k];candidates.append({'candidate_id':ident(r['node_id'],n['node_id']),'project_id':r['project_id'],'result_node_id':r['node_id'],'indicator_node_id':n['node_id'],'rank_for_result':rank,'cosine_similarity':float(sim[i,k]),'evidence_class':'semantic_candidate','same_document':int(r['document_id']==n['document_id']),'review_status':'unreviewed','result_title':r['title'],'indicator_title':n['title'],'result_source_url':r['source_url'],'indicator_source_url':n['source_url'],'result_source_xpath':r['source_xpath'],'indicator_source_xpath':n['source_xpath'],'source_versions_json':j([r['source_version'],n['source_version']]),'statistical_codes_json':j(sorted(registry[n['node_id']]))})
 task_results=collections.defaultdict(list);task_indicators=collections.defaultdict(list)
 for e in tables['edges']:
  if e['relation']=='result_declares_task':task_results[e['target_node_id']].append(e)
  if e['relation']=='indicator_declares_task':task_indicators[e['target_node_id']].append(e)
 shared=[]
 for task in sorted(set(task_results)&set(task_indicators)):
  for result_edge in task_results[task]:
   for ie in task_indicators[task]:
    r=byid[result_edge['source_node_id']];n=byid[ie['source_node_id']]
    shared.append({'link_id':ident(r['node_id'],n['node_id'],task),'project_id':r['project_id'],'result_node_id':r['node_id'],'indicator_node_id':n['node_id'],'shared_task_node_id':task,'evidence_class':'structural_inference','relation':'result_indicator_shared_task','result_task_edge_id':result_edge['edge_id'],'indicator_task_edge_id':ie['edge_id'],'result_title':r['title'],'indicator_title':n['title'],'task_title':byid[task]['title'],'document_id':r['document_id'],'source_sha256':r['source_sha256'],'result_task_xpath':result_edge['source_xpath'],'indicator_task_xpath':ie['source_xpath'],'source_url':r['source_url'],'local_file':r['local_file'],'source_version':r['source_version'],'statistical_codes_json':j(sorted(registry[n['node_id']])),'direct_effect_claimed':0})
 tables['result_indicator_shared_task']=shared
 for p in sorted(PROJECT_NAMES):
  pn=[n for n in nodes if n['project_id']==p];pr=[n for n in pn if n['kind']=='result'];pi=[n for n in pn if n['kind']=='indicator'];pc=[a for a in candidates if a['project_id']==p]
  explicit=[e for e in tables['edges'] if e['project_id']==p and e['relation']=='source_claim_exact_indicator_title'];claimed=[c for c in tables['link_claims'] if c['project_id']==p]
  coverage.append({'project_id':p,'result_cards':len(pr),'indicator_cards':len(pi),'explicit_resolved_result_indicator_edges':len(explicit),'source_reported_link_claims':len(claimed),'unresolved_source_link_claims':sum(c['resolution']=='unresolved_target' for c in claimed),'shared_task_result_indicator_links':sum(e['project_id']==p for e in shared),'results_linked_through_documented_task':len({e['result_node_id'] for e in shared if e['project_id']==p}),'indicators_linked_through_documented_task':len({e['indicator_node_id'] for e in shared if e['project_id']==p}),'results_with_candidate_ge_0_10':len({c['result_node_id'] for c in pc}),'results_without_candidate_ge_0_10':len(pr)-len({c['result_node_id'] for c in pc}),'indicators_with_approved_statistical_mapping':sum(bool(registry[n['node_id']]) for n in pi),'status':'family_manual_reference_separate' if p=='family' else 'documentary_extraction_and_unreviewed_candidates','expert_link_completion':0})
  for fid,rx in COMPILED.items():
   hit=collections.defaultdict(list)
   for n in pn:
    if rx.search(norm(n['title']+' '+n['description'])):hit[n['kind']].append(n)
   matched_codes=set(itertools.chain.from_iterable(registry[n['node_id']] for n in hit['indicator']))
   domains.append({'project_id':p,'domain_id':fid,'domain_name':FRAMES[fid][0],'goal_nodes':len(hit['goal']),'task_nodes':len(hit['task'])+len(hit['task_reference']),'result_nodes':len(hit['result']),'indicator_nodes':len(hit['indicator']),'approved_statistical_codes':len(matched_codes),'statistical_codes_json':j(sorted(matched_codes)),'evidence_node_ids_json':j([n['node_id'] for rr in hit.values() for n in rr]),'interpretation':'dictionary_marker_presence_only; zero_is_not_proof_of_absence','expert_domain_coverage_status':'not_assigned'})
 for n in nodes:
  if n['kind'] in ('goal','task','result','indicator'):
   formal.append({'node_id':n['node_id'],'project_id':n['project_id'],'kind':n['kind'],'has_numeral_in_text':int(bool(re.search(r'\d',n['title']+' '+n['description']))),'has_explicit_unit':n['has_explicit_unit'],'has_explicit_deadline':n['has_explicit_deadline'],'has_explicit_responsible':n['has_explicit_responsible'],'has_numeric_target':n['has_numeric_target'],'has_explicit_schedule_period':n.get('has_explicit_schedule_period',0),'has_numeric_schedule_value':n.get('has_numeric_schedule_value',0),'has_explicit_planned_numeric_value':n.get('has_explicit_planned_numeric_value',0),'has_time_expression_in_text':int(bool(re.search(r'20\d{2}',n['title']+' '+n['description']))),'smart_rating':None,'interpretation':'text_and_card_features_only; achievable_relevant_not_inferred'})
 tables.update({'semantic_candidates':candidates,'link_coverage':coverage,'formal_text_features':formal,'domain_evidence':domains})
 # Unweighted topology for documented result-task relations, separate from semantic candidate networks.
 metrics=[];summaries=[]
 for p in sorted(PROJECT_NAMES):
  for layer in ['documentary_result_task','structural_shared_task_result_indicator','semantic_result_indicator']:
   es=[(e['source_node_id'],e['target_node_id'],1.0) for e in tables['edges'] if e['project_id']==p and e['relation']=='result_declares_task'] if layer.startswith('documentary') else [(e['result_node_id'],e['indicator_node_id'],e['cosine_similarity']) for e in candidates if e['project_id']==p]
   if layer=='structural_shared_task_result_indicator':es=[(e['result_node_id'],e['indicator_node_id'],1.0) for e in shared if e['project_id']==p]
   keep=[n['node_id'] for n in nodes if n['project_id']==p and n['kind'] in (('result','task','task_reference') if layer.startswith('documentary') else ('result','indicator'))]
   adj={n:{} for n in keep}
   for a,b,w in es:adj.setdefault(a,{})[b]=w;adj.setdefault(b,{})[a]=w
   bet=brandes(adj)
   left=sum(byid[n]['kind']=='result' for n in adj);right=len(adj)-left;edge_count=sum(len(v) for v in adj.values())//2
   for n,nei in adj.items():metrics.append({'project_id':p,'layer':layer,'node_id':n,'node_kind':byid[n]['kind'],'degree':len(nei),'weighted_degree':sum(nei.values()),'unweighted_betweenness':bet[n],'degree_denominator_opposite_partition':right if byid[n]['kind']=='result' else left,'isolate':int(not nei),'weight_meaning':'binary_documentary_relation' if layer.startswith('documentary') else ('binary_shared_documentary_task' if layer.startswith('structural') else 'lexical_cosine_only'),'causal_effect_estimated':0})
   summaries.append({'project_id':p,'layer':layer,'left_result_nodes':left,'right_nodes':right,'edges':edge_count,'bipartite_density':edge_count/(left*right) if left*right else None,'isolates':sum(not v for v in adj.values()),'causal_effect_estimated':0})
 tables['network_node_metrics']=metrics;tables['network_summary']=summaries

def brandes(adj):
 # Brandes exact unweighted undirected betweenness, normalized by pairs excluding node.
 cb={v:0.0 for v in adj};n=len(adj)
 for s in adj:
  stack=[];pred={v:[] for v in adj};sigma=dict.fromkeys(adj,0.0);sigma[s]=1.0;dist=dict.fromkeys(adj,-1);dist[s]=0;q=collections.deque([s])
  while q:
   v=q.popleft();stack.append(v)
   for w in adj[v]:
    if dist[w]<0:q.append(w);dist[w]=dist[v]+1
    if dist[w]==dist[v]+1:sigma[w]+=sigma[v];pred[w].append(v)
  delta=dict.fromkeys(adj,0.0)
  while stack:
   w=stack.pop()
   for v in pred[w]:delta[v]+=sigma[v]/sigma[w]*(1+delta[w])
   if w!=s:cb[w]+=delta[w]
 scale=1/((n-1)*(n-2)) if n>2 else 0.0
 return {v:val*scale for v,val in cb.items()}

def family_reference_layer(package,tables):
 ref=package/'research/text_support/family_reference'
 rows=records(ref/'activities_indicators_matrix_long.csv');manual_nodes={};manual_edges=[];adj={}
 url=f'https://github.com/Arseniy24RUS/family/blob/{FAMILY_SHA}/public/downloads/data/activities_indicators_matrix_long.csv'
 for rowno,r in enumerate(rows,2):
  a='A::'+r['activity_id'];b='I::'+r['indicator_code'];w=2.0 if r['relationship_type']=='direct' else 1.0
  manual_nodes[a]={'node_id':a,'project_id':'family','node_kind':'manual_activity','title':r['activity'],'federal_project':r['federal_project'],'declared_scale':r['declared_scale'],'source_url':url,'local_file':'research/text_support/family_reference/activities_indicators_matrix_long.csv','source_version':'Git commit '+FAMILY_SHA}
  manual_nodes[b]={'node_id':b,'project_id':'family','node_kind':'manual_indicator','title':r['indicator_code'],'federal_project':'','declared_scale':'','source_url':url,'local_file':'research/text_support/family_reference/activities_indicators_matrix_long.csv','source_version':'Git commit '+FAMILY_SHA}
  manual_edges.append({'edge_id':ident('family',a,b),'project_id':'family','source_node_id':a,'target_node_id':b,'relationship_type':r['relationship_type'],'weight':w,'weight_meaning':'original_author_direct_2_indirect_1','evidence_class':'archived_author_manual_annotation','source_row':rowno,'source_url':url,'local_file':'research/text_support/family_reference/activities_indicators_matrix_long.csv','source_version':'Git commit '+FAMILY_SHA,'new_review_performed':0})
  adj.setdefault(a,{})[b]=w;adj.setdefault(b,{})[a]=w
 bet=brandes(adj);metrics=[];checks=[]
 expected={r['node_id']:r for r in records(ref/'activity_indicator_network_node_metrics.csv')}
 for n,nei in adj.items():
  row={'node_id':n,'project_id':'family','degree':len(nei),'weighted_degree':sum(nei.values()),'unweighted_betweenness':bet[n]}
  metrics.append(row);e=expected.get(n)
  checks.append({'check':'family_manual_network_node_replication','node_id':n,'passed':bool(e is not None and int(e['degree'])==row['degree'] and abs(float(e['weighted_degree'])-row['weighted_degree'])<1e-12 and abs(float(e['betweenness'])-row['unweighted_betweenness'])<1e-12)})
 left=sum(n.startswith('A::') for n in adj);right=len(adj)-left;m=sum(len(v) for v in adj.values())//2
 summary={'project_id':'family','manual_activity_nodes':left,'manual_indicator_nodes':right,'edges':m,'bipartite_density':m/(left*right),'legacy_general_graph_density':2*m/(len(adj)*(len(adj)-1)),'source_version':'Git commit '+FAMILY_SHA,'new_review_performed':0}
 oldsummary={r['metric']:float(r['value']) for r in records(ref/'activity_indicator_network_summary.csv')}
 checks.append({'check':'family_manual_network_summary_replication','passed':left==oldsummary['n_activity_nodes'] and right==oldsummary['n_indicator_nodes'] and m==oldsummary['n_edges'] and abs(summary['legacy_general_graph_density']-oldsummary['density'])<1e-12})
 narratives=[]
 for i,r in enumerate(records(ref/'nlp_narrative_blocks_dictionary.csv'),2):
  narratives.append({'reference_row':i,'project_id':'family',**r,'status':'archived_reference_only_not_pooled_with_new_dictionary','source_url':f'https://github.com/Arseniy24RUS/family/blob/{FAMILY_SHA}/public/downloads/data/nlp_narrative_blocks_dictionary.csv'})
 tables.update({'family_manual_nodes':list(manual_nodes.values()),'family_manual_edges':manual_edges,'family_manual_network_metrics':metrics,'family_manual_network_summary':[summary],'family_narrative_reference':narratives})
 for r in tables['link_coverage']:
  r['family_reference_activities']=left if r['project_id']=='family' else None
  r['family_reference_indicators']=right if r['project_id']=='family' else None
  r['family_reference_manual_edges']=m if r['project_id']=='family' else None
 return checks


def legacy_validation(package):
 ref=package/'research/text_support/family_reference';docs=records(ref/'nlp_document_texts_extracted.csv');frames=json.loads((ref/'frames_original.json').read_text());expected={r['document_id']:r for r in records(ref/'nlp_frame_scores_by_document.csv')};checks=[]
 for d in docs:
  txt=d['text'].lower();nt=max(1,len(txt.split()));e=expected[d['document_id']]
  checks.append({'check':'family_legacy_token_count','document_id':d['document_id'],'passed':nt==int(e['n_tokens']),'computed':nt,'expected':int(e['n_tokens'])})
  for frame,pats in frames.items():
   cnt=sum(txt.count(p.lower()) for p in pats);exp=int(e[frame+'_count']);checks.append({'check':'family_legacy_frame_'+frame,'document_id':d['document_id'],'passed':cnt==exp,'computed':cnt,'expected':exp})
 x=TfidfVectorizer(max_features=4000,ngram_range=(1,2)).fit_transform([d['text'] for d in docs]);sim=cosine_similarity(x);old=records(ref/'nlp_document_similarity_tfidf.csv')
 for i,row in enumerate(old):
  for k,d in enumerate(docs):
   exp=float(row[d['file_name']]);val=float(sim[i,k]);checks.append({'check':'family_legacy_tfidf','document_id':docs[i]['document_id'],'other_document_id':d['document_id'],'passed':abs(exp-val)<1e-10,'computed':val,'expected':exp})
 return checks

def export_tables(tables,out):
 db=out/'research_text.sqlite'
 if db.exists():db.unlink()
 c=sqlite3.connect(db);rowcounts={};data=out/'tables';data.mkdir(exist_ok=True)
 for name,rows in tables.items():
  df=pd.DataFrame(rows)
  if not len(df):df=pd.DataFrame(columns=['status'])
  df.to_sql('t_'+name,c,index=False,if_exists='replace');rowcounts['t_'+name]=len(rows)
  large=name in ('units','kwic','node_evidence')
  path=data/(name+'.csv'+('.gz' if large else ''))
  df.to_csv(path,index=False,encoding='utf-8-sig',compression='gzip' if large else None)
 c.execute('create index idx_t_units_doc on t_units(document_id)');c.execute('create index idx_t_nodes_project_kind on t_nodes(project_id,kind)');c.execute('create index idx_t_evidence_node on t_node_evidence(node_id)');c.commit()
 quick=c.execute('pragma quick_check').fetchall();c.close()
 return rowcounts,quick

def make_figures(out,order,pcos,z,tables):
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plt.rcParams.update({'font.family':'DejaVu Serif','font.size':10,'svg.fonttype':'none'})
 figs=out/'figures';figs.mkdir(exist_ok=True)
 labels=[PROJECT_NAMES[p] for p in order]
 # Family is clearly marked as a different document genre.
 labels=[s+' *' if p=='family' else s for p,s in zip(order,labels)]
 def save(fig,name):
  fig.savefig(figs/(name+'.svg'),bbox_inches='tight');fig.savefig(figs/(name+'.png'),dpi=140,bbox_inches='tight');plt.close(fig)
 fig,ax=plt.subplots(figsize=(12,10));im=ax.imshow(pcos,vmin=0,vmax=1,cmap='Blues');ax.set_xticks(range(len(order)),labels,rotation=55,ha='right');ax.set_yticks(range(len(order)),labels)
 for i in range(len(order)):
  for k in range(len(order)):ax.text(k,i,f'{pcos[i,k]:.2f}',ha='center',va='center',fontsize=8,color='white' if pcos[i,k]>.65 else 'black')
 fig.colorbar(im,ax=ax,label='Косинус TF-IDF');fig.text(.01,.01,'* Семья: архивный паспорт PDF. Остальные проекты: структурные тексты HTML. Межжанровое сопоставление ограничено.',fontsize=9);fig.tight_layout(rect=(0,.04,1,1));save(fig,'project_text_similarity')
 fig,ax=plt.subplots(figsize=(11,7));dendrogram(z,labels=labels,orientation='right',ax=ax);ax.set_xlabel('Расстояние 1 – косинус, average linkage');fig.tight_layout();save(fig,'project_text_dendrogram')
 cov=[r for r in tables['link_coverage'] if r['project_id']!='family'];fig,ax=plt.subplots(figsize=(11,7));y=np.arange(len(cov));ax.barh(y-.18,[r['result_cards'] for r in cov],height=.32,label='Карточки результатов');ax.barh(y+.18,[r['indicator_cards'] for r in cov],height=.32,label='Карточки показателей');ax.set_yticks(y,[PROJECT_NAMES[r['project_id']] for r in cov]);ax.set_xlabel('Число извлечённых карточек');ax.legend();fig.tight_layout();save(fig,'documentary_nodes')

METHODS_RU='''# Текстовые и структурные исследования 1.2.0

## Единицы анализа и источники

Исходная текстовая SQLite читается без изменения. HTML, PDF и архивные извлечения «Семьи» учитываются как отдельные документы, жанры и редакции. Совпадение источника в нескольких регистрах хранится в таблице document_projects. Повторные источники одного SHA не создают повторные документы. Сохранены исходные URL, локальные пути, SHA-256, тип хэша hash_kind, отдельный local_file_sha256, версии и точные XPath/номера полей либо страницы.

Для HTML в основной профиль включены уникальные формулировки целей, задач, результатов и показателей. Организационные реквизиты, повторяющиеся таблицы бюджетов и служебные подписи исключены. Контрольные точки извлечены отдельно как milestone, но не включены в основной словарный знаменатель. Для PDF удалены только короткие повторяющиеся колонтитулы и строки числовых табличных ячеек. Реестр удалённых строк сохранён. Строки с извлечённым текстом не заменяют проверки PDF и не являются OCR.

## Лексика, словари и контекст

Нормализация включает нижний регистр, замену ё на е, нормализацию пробелов и удаление строк переноса слов через дефис в PDF. Лемматизация не заявляется. Отдельная проверка чувствительности использует русский SnowballStemmer из NLTK 3.9.2 без загрузки корпусов. Первичная поверхностная токенизация и стемминг не смешиваются: сохранены обе матрицы, изменение коэффициентов, ранговая корреляция и состав ближайших соседей. Стемминг не равен лемматизации. Корреляции между ранжированиями являются описательными, p-значения для зависимых пар не используются. Токены задаются открытым регулярным выражением, стоп-слова сохранены в коде. Новый словарь содержит 18 межпроектных тематик и использует границы слов. Старые 9 фреймов «Семьи» воспроизводятся отдельно точным исходным способом: сумма txt.count для подстрок, знаменатель len(text.split()). Подстроки эко и прав в старом коде могут попадать в слова экономика и управление, поэтому такой словарь не переносится как универсальный.

Частота темы равна числу неперекрывающихся совпадений объединённого выражения внутри одной темы на 1000 текстовых токенов. Между темами пересечения возможны, частоты не складываются до 100%. Ноль совпадений означает только отсутствие словарного маркера. KWIC хранит до 3 контекстов на единицу/тему и координаты в нормализованном тексте. Все исходные единицы доступны для расширенного поиска.

Совместная встречаемость считается отдельно по страницам PDF и по структурным единицам HTML. Знаменатель – число доступных непустых единиц соответствующего типа. Повторное упоминание на одной странице не увеличивает число совместно встречающихся страниц. Совместное присутствие не является причинной или синтаксической связью.

## TF-IDF и тематическое сходство

Основной расчёт использует униграммы и биграммы, максимум 20000 признаков, min_df=1, max_df=0.98, sublinear_tf=True, smooth_idf=True, L2-нормировку. Никакая модель языка и внешний API не используются. Косинус вычисляется по всему фиксированному корпусу, таблица сохраняет жанры каждого документа. Не следует интерпретировать коэффициент как процент общего смысла. Средний межпроектный профиль – средний L2-вектор HTML-паспортов проекта с последующей нормировкой. Для «Семьи» использован один архивный паспорт, поэтому сопоставление с HTML помечено как межжанровое. Дендограмма строится average linkage по расстоянию 1–cosine.

Старая ручная сеть мероприятий и показателей Семьи сохранена отдельными таблицами family_manual_*. Степени, взвешенные степени и посреднические центральности пересчитаны по исходным direct/indirect-связям и проверены против архива. Старая 10-блочная нарративная таблица сохранена отдельно от новой 18-тематической группировки.

Для точной контрольной репликации старого 4-документного расчёта отдельно используются TfidfVectorizer(max_features=4000, ngram_range=(1, 2)) и исходные тексты без новой очистки. Число слов, все 36 фреймовых счётчиков и все 16 элементов матрицы сравниваются с архивными CSV.

## Структура документов и связи

Различаются goal, task, result, indicator и milestone. Карточка результата остаётся documentary_result: её извлечение само по себе не доказывает достижение общественного эффекта. Тип indicator также не объявляется автоматически outcome либо impact. Формальные признаки явного поля срока, единицы, ответственного, временного выражения в тексте, периодов числового графика и плановых чисел вынесены отдельно. has_explicit_deadline обозначает именно наличие поля «Срок реализации», тогда как годы таблицы учитываются в has_explicit_schedule_period. Числовые расписания без явной роли plan не переименовываются в план. Общий SMART-балл не рассчитывается.

Рёбра explicit_documentary требуют буквального основания: строка задачи внутри карточки результата с точным HTML-якорем на задачу в том же документе, явная ссылка национального паспорта на федеральный, либо уникальное точное совпадение адресата в источниковой секции влияния с названием карточки показателя. Строка db-purpose-task связывает показатель с единственной задачей с точно совпадающим названием в том же документе. Совпадение общего узла задачи в двух явных рёбрах result→task и indicator→task формирует отдельную таблицу result_indicator_shared_task с классом structural_inference. Такая двухшаговая документальная цепочка не равна прямому влиянию результата на показатель. Обе исходные строки, XPath и edge_id сохранены. Членство цели и результата в одном паспорте также записывается как structural_inference. Факт соседства в документе не кодирует причинное действие. При неразрешённом якоре сохраняется один task_reference на сочетание документ/код/название. Результат не связывается со всеми одноимёнными задачами других паспортов. Статус target_resolution позволяет отличить разрешённый якорь от буквальной ссылки без найденной карточки.

Секция «Влияние результата на показатели» во многих HTML повторяет название самого результата без идентификатора целевого показателя. Каждая такая запись сохранена в link_claims. Неразрешённый адресат остаётся unresolved_target. Числовой вес из этой секции не становится величиной эффекта.

Кандидаты result–indicator получены отдельно по косинусу TF-IDF среди показателей того же нацпроекта: не более 3 кандидатов на результат с порогом 0.10. Все имеют unreviewed и semantic_candidate. Порог задаёт объём ручной проверки, не вероятность правильности. Новая матрица не объявляется равнозначной исходной ручной разметке Семьи direct/indirect.

## Сеть и сферы

Документальная сеть result–task, сеть result–indicator через общую документальную задачу и лексическая сеть result–indicator считаются отдельно. Сохранены степень, сумма весов и точная невзвешенная нормированная посредническая центральность Brandes. Плотность использует двудольный знаменатель N_results*N_other. Косинус является весом близости, в кратчайшие пути он не подставляется как расстояние. Изолят означает отсутствие ребра в данном слое, но не доказанную бесполезность мероприятия.

Матрица сфер содержит число документальных узлов с маркерами, доказательные node_id и привязанные статистические коды из проверенных связей 1.1. Связь с реестром переносится только по точным source SHA и card ID. Семантический результат не создаёт нового утверждённого статистического соответствия. Содержательное заключение о достаточности сферы и причинной состоятельности цепочки остаётся предметом последующей экспертизы.

## Повторение

Запуск из корня комплекта: python research/text_analysis.py. Параметры --package-root и --output задают корень и отдельную выходную папку. Скрипт требует numpy, pandas, scipy, scikit-learn, lxml и matplotlib, затем работает без сети. Таблицы находятся в research_text.sqlite и CSV, крупные CSV сжаты gzip. Для воспроизведения чувствительности дополнительно нужен nltk==3.9.2. Если он не установлен, основной анализ работает, а таблица чувствительности явно получает not_run_missing_dependency. Исходные SQLite не изменяются.
'''

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--package-root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--output',type=Path,default=Path('outputs/research/text'));ap.add_argument('--skip-figures',action='store_true');args=ap.parse_args();package=args.package_root.resolve();out=args.output if args.output.is_absolute() else package/args.output;out.mkdir(parents=True,exist_ok=True)
 source=package/'corpus/data/catalog.sqlite3';before=filehash(source)
 print('Extracting document and structure units',flush=True);tables,texts=extract(package)
 print('Documents',len(tables['documents']),'units',len(tables['units']),'nodes',len(tables['nodes']),flush=True)
 print('Lexical and TF-IDF research',flush=True);vectorizer,x,valid,cos,order,pcos,z=lexical(tables,texts,out)
 print('Russian stemming sensitivity',flush=True);stemming_sensitivity(tables,texts,valid,cos,order,pcos)
 print('Document structure, semantic candidates, exact graph metrics',flush=True);semantics(tables,vectorizer)
 checks=legacy_validation(package)+family_reference_layer(package,tables)
 nodeids={n['node_id'] for n in tables['nodes']}
 checks += [{'check':'all_edges_resolve_nodes','passed':all(e['source_node_id'] in nodeids and e['target_node_id'] in nodeids for e in tables['edges'])},{'check':'one_documentary_task_target_per_result','passed':all(n<=1 for n in collections.Counter(e['source_node_id'] for e in tables['edges'] if e['relation']=='result_declares_task').values())},{'check':'documentary_task_targets_stay_within_document','passed':all(next(n for n in tables['nodes'] if n['node_id']==e['target_node_id'])['document_id']==e['document_id'] for e in tables['edges'] if e['relation']=='result_declares_task')},{'check':'unique_document_ids','passed':len({d['document_id'] for d in tables['documents']})==len(tables['documents'])},{'check':'unique_nodes','passed':len(nodeids)==len(tables['nodes'])},{'check':'tfidf_symmetric','passed':bool(np.allclose(cos,cos.T,atol=1e-12))},{'check':'tfidf_diagonal_one','passed':bool(np.allclose(np.diag(cos),1,atol=1e-12))},{'check':'tfidf_bounds','passed':bool(cos.min()>=-1e-12 and cos.max()<=1+1e-12)},{'check':'all_evidence_files_exist','passed':all((package/d['local_file']).exists() for d in tables['documents'])},{'check':'input_database_sha_preserved','passed':filehash(source)==before},{'check':'new_dictionary_avoids_eco_economy','passed':not bool(COMPILED['reproductive_health'].search('экономика'))},{'check':'new_dictionary_avoids_prav_management','passed':not bool(COMPILED['access_rights'].search('управление'))}]
 # Three-node path: middle normalized betweenness1, endpoints0, an independent known control.
 b=brandes({'a':{'b':1},'b':{'a':1,'c':1},'c':{'b':1}});checks.append({'check':'brandes_three_node_path','passed':b=={'a':0.0,'b':1.0,'c':0.0}})
 tables['validation_checks']=checks
 print('Exporting',flush=True);counts,quick=export_tables(tables,out)
 if not args.skip_figures:make_figures(out,order,pcos,z,tables)
 methods_text=re.sub(r'(?<=[А-Яа-я])(?=\d)|(?<=\d)(?=[А-Яа-я])',' ',METHODS_RU)
 (out/'METHODS_RU.md').write_text(methods_text,encoding='utf-8')
 (out/'dictionary.json').write_text(j({'version':'cross_project_v1','frames':{k:{'name':v[0],'patterns':v[1]} for k,v in FRAMES.items()},'token_regex':TOKEN_RE.pattern,'stopwords':sorted(STOPWORDS)}),encoding='utf-8')
 summary={'version':VERSION,'family_reference_commit':FAMILY_SHA,'source_database_sha256':before,'documents':len(tables['documents']),'new_projects':10,'family_reference_documents':4,'nodes':len(tables['nodes']),'node_types':dict(collections.Counter(n['kind'] for n in tables['nodes'])),'unit_types':dict(collections.Counter(u['unit_kind'] for u in tables['units'])),'link_claim_resolution':dict(collections.Counter(r['resolution'] for r in tables['link_claims'])),'indicator_task_resolution':dict(collections.Counter(r['resolution'] for r in tables['indicator_task_claims'])),'shared_task_links':len(tables.get('result_indicator_shared_task',[])),'semantic_candidates':len(tables['semantic_candidates']),'candidate_results':len({r['result_node_id'] for r in tables['semantic_candidates']}),'dictionary_frames':len(FRAMES),'tfidf_documents':len(valid),'tfidf_features':len(vectorizer.vocabulary_),'stemming_sensitivity':tables.get('stemming_sensitivity_summary',[]),'family_manual_network':tables.get('family_manual_network_summary',[]),'tables':counts,'checks_passed':sum(bool(r['passed']) for r in checks),'checks_total':len(checks),'sqlite_quick_check':quick,'all_checks_passed':all(r['passed'] for r in checks),'source_preserved':filehash(source)==before,'substantive_manual_review_completed':False,'formal_causal_effects_estimated':False}
 (out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)
 if not summary['all_checks_passed']:raise SystemExit('Validation failure; inspect validation_checks')
if __name__=='__main__':main()
