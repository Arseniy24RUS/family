#!/usr/bin/env python3
"""Parse public DataBudget passport bytes with exact DOM locators.

The documents are secondary renderings of public budget-system passports.
No source level, edition, missing value or undocumented relationship is inferred.
"""
from pathlib import Path
from decimal import Decimal,InvalidOperation
import argparse,collections,hashlib,json,re
from lxml import html

TOKEN_RE=re.compile(r'[а-яёa-z]{2,}(?:-[а-яёa-z]{2,})?',re.I)
def ws(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def norm(s):return ws(s).lower().replace('ё','е')
def text(el):return ws(el.text_content()) if el is not None else ''
def classes(el,name):return el.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," '+name+' ")]')
def first_class(el,name):
 v=classes(el,name);return text(v[0]) if v else ''
def nearest_card(el):return next((a for a in el.iterancestors() if a.tag=='details'),None)
def decimal(s):
 s=ws(s).replace(' ','').replace(',','.').replace('\u2060','')
 if not s or s in ['—','–','-']:return None
 try:return str(Decimal(s))
 except InvalidOperation:return None
def fields(card):
 out={}
 for dt in card.xpath('.//dt'):
  if nearest_card(dt) is card:out[text(dt)]=text(dt.getnext())
 return out
def parse_passport(raw,meta):
 tree=html.fromstring(raw);root=tree.getroottree()
 document_title=text(tree.xpath('//h1')[0]);code=re.search(r'\[([^]]+)\]',document_title).group(1)
 doc_id=meta.get('document_id') or f"{meta['kind']}_{meta['id']}"
 units=[];seen=set();nodes=[];claims=[];finance=[];targets=[]
 def unit(kind,value,el,node=None):
  value=ws(value);key=norm(value)
  if not value or key in seen:return
  seen.add(key);units.append({'unit_id':f'{doc_id}:u{len(units)+1}','document_id':doc_id,'project_id':meta['project_id'],'kind':kind,'text':value,'n_tokens':len(TOKEN_RE.findall(norm(value))),'source_locator':root.getpath(el),'node_id':node,'source_sha256':meta['sha256']})
 def stable_node_id(card,kind='result'):
  # Public HTML repeats several result IDs within the same passport.
  # The complete source XPath distinguishes real cards without deduplication.
  suffix=hashlib.sha256(root.getpath(card).encode()).hexdigest()[:16]
  return f'{doc_id}:{card.get("id") or kind}:{suffix}'
 def node(kind,title,description,card,metadata=None):
  nid=stable_node_id(card,kind);nodes.append({'node_id':nid,'id':nid,'document_id':doc_id,'project_id':meta['project_id'],'fp':code,'kind':kind,'title':title,'description':description,'source_locator':root.getpath(card),'source_xpath':root.getpath(card),'source_card_id':card.get('id'),'source_sha256':meta['sha256'],'source_url':meta['url'],'metadata':metadata or {}});return nodes[-1]
 for dt in tree.xpath('//dt'):
  if text(dt)=='Цель проекта' and nearest_card(dt) is None:
   unit('goal',text(dt.getnext()),dt.getnext())
 for card in tree.xpath('//*[starts-with(@id,"passport-task-")]'):
  title=first_class(card,'db-result-fold-title')
  if not title:title=text(card.find('summary'))
  nd=node('task',title,'',card,fields(card));unit('task',title,card,nd['node_id'])
 for dt in tree.xpath('//dt'):
  if text(dt)=='Задача':unit('task',text(dt.getnext()),dt.getnext())
 for kind,prefix in [('result','passport-result-'),('indicator','passport-purpose-')]:
  for card in tree.xpath(f'//*[starts-with(@id,"{prefix}")]'):
   f=fields(card);title=first_class(card,'db-result-fold-title');description=f.get('Характеристика результата','') if kind=='result' else ''
   nd=node(kind,title,description,card,f)
   unit(kind+'_title',title,card,nd['node_id'])
   if description:
    description_el=next(dt.getnext() for dt in card.xpath('.//dt') if text(dt)=='Характеристика результата' and nearest_card(dt) is card)
    unit('result_description',description,description_el,nd['node_id'])
   task_class='db-result-task' if kind=='result' else 'db-purpose-task'
   task=classes(card,task_class)
   nd['task_text']=text(task[0]) if task else ''
   if task:
    refs=task[0].xpath('.//a/@href');nd['task_href']=refs[0] if refs else None
   if kind=='indicator':
    years={};raw_years={}
    for cell in classes(card,'db-purpose-year-cell'):
     year=first_class(cell,'db-purpose-year');rawval=first_class(cell,'db-purpose-year-val');val=decimal(rawval)
     if re.fullmatch(r'20\d{2}',year):years[year]=float(val) if val is not None else None;raw_years[year]={'value_decimal':val,'value_raw':rawval,'source_locator':root.getpath(cell)}
    targets.append({'document_id':doc_id,'fp':code,'card_id':card.get('id'),'source_locator':root.getpath(card),'source_url':meta['url'],'source_sha256':meta['sha256'],'title':title,'unit':f.get('Единица измерения'),'local_code':f.get('Код показателя'),'years':years,'raw_years':raw_years,'base_value_raw':f.get('Базовое значение'),'base_date':f.get('Дата базового значения'),'metadata':f})
   else:
    for dt in card.xpath('.//dt'):
     if text(dt)=='Влияние результата на показатель':
      value=text(dt.getnext());parent=dt.getparent().getparent()
      labels={text(d):text(d.getnext()) for d in parent.xpath('.//dt')}
      claims.append({'id':f'{doc_id}:weight{len(claims)+1}','document_id':doc_id,'fp':code,'result_node_id':nd['node_id'],'result_title':title,'value_raw':value,'value':float(decimal(value)) if decimal(value) is not None else None,'published_fields':labels,'indicator_node_id':None,'resolution':'unresolved_target_indicator','source_locator':root.getpath(dt),'source_sha256':meta['sha256'],'source_url':meta['url']})
 for row in classes(tree,'db-finsupport-row'):
  source=first_class(row,'db-finsupport-source')
  anc=next((a for a in row.iterancestors() if (a.get('id') or '').startswith('passport-result-')),None)
  level='result' if anc is not None else 'document'
  if anc is None and not any(a.get('id')=='passport-finsupports' for a in row.iterancestors()):continue
  for cell in classes(row,'db-passport-year-chip'):
   year=first_class(cell,'db-passport-year-label');rawval=first_class(cell,'db-passport-year-value');val=decimal(rawval)
   if not re.fullmatch(r'20\d{2}',year):continue
   finance.append({'document_id':doc_id,'fp':code,'scope':level,'result_id':stable_node_id(anc) if anc is not None else None,'source_result_card_id':anc.get('id') if anc is not None else None,'source_result_locator':root.getpath(anc) if anc is not None else None,'result_title':first_class(anc,'db-result-fold-title') if anc is not None else None,'source':source,'year':int(year),'amount_decimal':val,'amount_thousand_rub':float(val) if val is not None else None,'value_raw':rawval,'unit':'тыс. руб.','source_locator':root.getpath(cell),'source_sha256':meta['sha256'],'source_url':meta['url']})
 version=first_class(tree,'db-exp-version')
 full=text(tree)
 if not version:
  m=re.search(r'Версия\s+(\d+\.\d+)',full);version=m.group(1) if m else None
 pub=re.search(r'(\d{2}\.\d{2}\.20\d{2})\s+в\s+(\d{2}:\d{2})',full)
 publication=pub.group(1) if pub else None
 tokens=sum(u['n_tokens'] for u in units)
 return {'document':{**meta,'id':doc_id,'document_id':doc_id,'code':code,'title':document_title,'publisher_version':version,'publication_date':publication,'source_kind':'secondary_epbs_rendering','genre':'html_passport','document_level':'national' if meta['kind']=='np' else 'federal','profile_token_count':tokens,'n_tokens':tokens,'source_url':meta['url'],'source_sha256':meta['sha256'],'profile_text_sha256':hashlib.sha256('\n'.join(u['text'] for u in units).encode()).hexdigest()},'units':units,'nodes':nodes,'unresolved_weight_claims':claims,'targets':targets,'finance_records':finance}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('file',type=Path);p.add_argument('--project',default='health_technologies');p.add_argument('--kind',choices=['np','fp'],required=True);p.add_argument('--id',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();raw=a.file.read_bytes();result=parse_passport(raw,{'project_id':a.project,'kind':a.kind,'id':a.id,'url':f'https://databudget.ru/projects/{a.kind}/{a.id}','sha256':hashlib.sha256(raw).hexdigest()});a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['document'])
if __name__=='__main__':main()
