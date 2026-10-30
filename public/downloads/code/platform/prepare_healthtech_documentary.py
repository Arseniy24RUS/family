#!/usr/bin/env python3
"""Prepare a pinned, compact 98-passport corpus from original public HTML bytes.

This one-time import is not required for regular offline platform builds.
"""
from pathlib import Path
import argparse,csv,hashlib,json,re,shutil,zipfile
from extract_healthtech_passports import parse_passport,ws
APP=Path(__file__).resolve().parents[1]
PROJECT='health_technologies'
BASE=f'downloads/projects/{PROJECT}/documentary/'
def dump(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def prepare(release,fetched,root=APP):
 destination=root/'inputs/healthtech/documentary';destination.mkdir(parents=True,exist_ok=True)
 output=root/'public'/BASE;output.mkdir(parents=True,exist_ok=True)
 records=list(csv.DictReader((release/'outputs/research/text/tables/documents.csv').open(encoding='utf-8-sig')))
 sources=[]
 for r in records:
  if r['source_kind']!='secondary_epbs_rendering':continue
  m=re.fullmatch(r'https://databudget.ru/projects/(np|fp)/(\d+)',r['source_url']);assert m,r['source_url']
  kind,num=m.groups();sources.append((release/r['local_file'],{'project_id':r['project_id'],'kind':kind,'id':int(num),'url':r['source_url'],'sha256':r['local_file_sha256'],'retrieved_at':r['snapshot_at'],'import_basis':'NationalProjects_Analytics_1.2.0','import_path':r['local_file']}))
 for r in json.loads((fetched/'manifest.json').read_text()):sources.append((fetched/r['filename'],{**r,'import_basis':'public_http_retrieval_2026-10-29'}))
 assert len(sources)==98 and len(set(r['url'] for p,r in sources))==98
 manifest=[];new=[]
 with zipfile.ZipFile(destination/'passports.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for path,meta in sorted(sources,key=lambda x:(x[1]['project_id'],x[1]['kind'],x[1]['id'])):
   raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==meta['sha256']
   parsed=parse_passport(raw,meta);name=f"{meta['project_id']}/{meta['kind']}_{meta['id']}.html"
   doc={**parsed['document'],'archive_entry':name,'bytes':len(raw)}
   z.writestr(name,raw);manifest.append(doc)
   if meta['project_id']==PROJECT:
    new.append(parsed)
    target=output/'sources'/Path(name).name;target.parent.mkdir(exist_ok=True);target.write_bytes(raw);doc['download_path']=BASE+'sources/'+target.name
  z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 meta={'schema_version':1,'project_id':PROJECT,'corpus_documents':len(manifest),'corpus_projects':len(set(r['project_id'] for r in manifest)),'corpus_tokens':sum(r['profile_token_count'] for r in manifest),'source_kind':'secondary_epbs_rendering','documents':manifest,'archive_sha256':hashlib.sha256((destination/'passports.zip').read_bytes()).hexdigest(),'archive_bytes':(destination/'passports.zip').stat().st_size,'author_report_expected':{'documents':98,'projects':12,'tokens':75539,'healthtech_tokens':2571},'retrieval_note':'86 byte-pinned DataBudget sources from the previous research release;12 newly retrieved DataBudget sources for Family and Health technologies. Publication dates and passport editions retained independently of retrieval dates.'}
 dump(destination/'source_manifest.json',meta);dump(output/'source_manifest.json',meta)
 shutil.copy2(destination/'passports.zip',output/'documentary_sources.zip')
 dump(destination/'parsed_healthtech_passports.json',new)
 print(json.dumps({k:meta[k] for k in ['corpus_documents','corpus_projects','corpus_tokens','archive_bytes','archive_sha256']},ensure_ascii=False,indent=2))
 print('project_tokens',sum(r['document']['profile_token_count'] for r in new))
 return meta
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--release',type=Path,required=True);p.add_argument('--fetched',type=Path,required=True);p.add_argument('--root',type=Path,default=APP);a=p.parse_args();prepare(a.release,a.fetched,a.root)
