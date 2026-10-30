#!/usr/bin/env python3
"""Prepare Economic passports from the shared, checksum-pinned source archive.

Normal builds use the included inputs and need no external release or network.
Optional --release only reimports the reviewed mapping/reference tables from
NationalProjects_Analytics_1.2.0, preserving exact source identities.
"""
from pathlib import Path
import argparse,csv,hashlib,json,zipfile
from extract_competitive_passports import parse_passport

APP=Path(__file__).resolve().parents[1]
PROJECT='competitive_economy'
REL=f'downloads/projects/{PROJECT}/documentary/'

def dump(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def prepare(root=APP,release=None):
 folder=root/'inputs/competitive/documentary';output=root/'public'/REL
 original=json.loads((root/'inputs/healthtech/documentary/source_manifest.json').read_text())
 archive=root/'inputs/healthtech/documentary/passports.zip'
 assert hashlib.sha256(archive.read_bytes()).hexdigest()==original['archive_sha256']
 selected=[];manifest=[]
 with zipfile.ZipFile(archive) as z:
  for item in original['documents']:
   meta=dict(item)
   if meta['project_id']==PROJECT:
    raw=z.read(meta['archive_entry']);assert hashlib.sha256(raw).hexdigest()==meta['sha256']
    dst=output/'sources'/f"{meta['document_id']}.html";dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
    meta['download_path']=REL+'sources/'+dst.name;selected.append(parse_passport(raw,meta))
   manifest.append(meta)
 assert len(selected)==8
 result={**original,'project_id':PROJECT,'archive_path':'inputs/healthtech/documentary/passports.zip',
   'shared_archive_download':'downloads/projects/health_technologies/documentary/documentary_sources.zip',
   'documents':manifest,'selected_documents':8,'selected_tokens':sum(d['document']['profile_token_count'] for d in selected),
   'source_archive_scope':'shared_98_document_archive_containing_all_8_economic_passports',
   'text_model_scope':'separate_pinned_137_document_profiles_reused_from_personnel',
   'retrieval_note':'Original individual retrieval times from 19 October 2026 are retained. Preparation is not a new retrieval.',
   'text_extraction_note':'Economic result descriptions join original HTML text nodes with spaces. This retains lexical boundaries between paragraphs and list items.'}
 dump(folder/'source_manifest.json',result);dump(output/'source_manifest.json',result);dump(folder/'parsed_competitive_passports.json',selected)
 if release:
  rows=list(csv.DictReader((release/f'outputs/projects/{PROJECT}/targets.csv').open(encoding='utf-8-sig')));mapping={}
  for item in rows:
   if not item['source_url'].startswith('https://databudget.ru/'):continue
   key=item['source_url']+'#'+item['source_locator']
   if key in mapping:assert mapping[key]['indicator_code']==item['indicator_code']
   mapping[key]={'indicator_code':item['indicator_code'],'source_sha256':item['source_sha256'],
     'title':item['target_indicator_name'],'unit':item['unit'],'mapping_status':item['mapping_status'],
     'mapping_id':item['mapping_id'],'target_is_proxy':item['target_is_proxy']=='1',
     'origin':'reviewed_mapping_from_NationalProjects_Analytics_1.2.0'}
  assert len(mapping)==51
  unmapped={t['source_url']+'#'+t['card_id']:{'title':t['title'],'unit':t['unit'],'source_sha256':t['source_sha256'],
      'reason':'В исходном реестре 49 кодов соответствие не установлено. Карточка сохраняется без принудительного сопоставления.'}
      for d in selected for t in d['targets'] if t['source_url']+'#'+t['card_id'] not in mapping}
  assert len(unmapped)==3
  dump(folder/'target_mapping.json',{'project_id':PROJECT,'mapping':mapping,'unmapped_cards':unmapped,
      'selection_policy':'Национальная карточка предпочтительна при наличии совпадающего определения. Все 54 исходные карточки и годы сохранены отдельно. Публикация октября 2026 года не удостоверяет задание, утверждённое до начала 2025 года.',
      'source_overrides':{}})
  expected={}
  for name in ['project_similarity','stemming_project_sensitivity','project_frame_scores','document_similarity','tfidf_top_terms','semantic_candidates','network_summary']:
   rr=list(csv.DictReader((release/f'outputs/research/text/tables/{name}.csv').open(encoding='utf-8-sig')))
   original_ids={'html:'+d['document']['sha256'] for d in selected}
   expected[name]=[r for r in rr if r.get('project_id')==PROJECT or r.get('project_a')==PROJECT or r.get('project_b')==PROJECT or r.get('document_id') in original_ids or r.get('document_a') in original_ids and r.get('document_b') in original_ids]
  dump(folder/'author_reference_tables.json',expected)
 cfg=json.loads((folder/'text_parameters.json').read_text())
 assert hashlib.sha256((root/cfg['shared_profiles_input']).read_bytes()).hexdigest()==cfg['shared_profiles_sha256']
 print(json.dumps({'source_passports':8,'source_tokens':result['selected_tokens'],'corpus_archive_documents':len(manifest),'text_model_documents':137},ensure_ascii=False))
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=APP);p.add_argument('--release',type=Path);a=p.parse_args();prepare(a.root.resolve(),a.release)
