#!/usr/bin/env python3
"""Prepare compact, pinned Personnel documentary inputs from the research release.

The normal site build reads the bundled input and does not need the full release.
This import preserves source byte hashes and all selected source editions.
"""
from pathlib import Path
import argparse,csv,gzip,hashlib,io,json,shutil,zipfile

APP=Path(__file__).resolve().parents[1]
PROJECT='personnel'
BASE='downloads/projects/personnel/documentary/'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def rows(p):
    with (gzip.open(p,'rt',encoding='utf-8-sig') if p.suffix=='.gz' else p.open(encoding='utf-8-sig')) as f:return list(csv.DictReader(f))

def prepare(release,materials,root=APP):
    out=root/'public'/BASE;out.mkdir(parents=True,exist_ok=True)
    text_dir=release/'outputs/research/text/tables';provenance=[]
    docs=[x for x in rows(text_dir/'documents.csv') if x['project_id']==PROJECT]
    ids={d['document_id'] for d in docs};assert len(docs)==11
    tables={}
    names=['documents','document_projects','frame_scores','project_frame_scores','tfidf_top_terms','document_similarity','project_similarity','stemming_project_sensitivity','nodes','edges','link_coverage','result_indicator_shared_task','semantic_candidates','network_node_metrics','network_summary','link_claims','indicator_registry_links','domain_evidence','lexical_frequencies','formal_text_features','concept_cooccurrence','kwic','units']
    for name in names:
        p=text_dir/(name+'.csv')
        if not p.exists():p=text_dir/(name+'.csv.gz')
        rr=rows(p)
        selected=[r for r in rr if r.get('project_id')==PROJECT or r.get('project_a')==PROJECT or r.get('project_b')==PROJECT or r.get('document_id') in ids]
        tables[name]=selected
        provenance.append({'path':p.relative_to(release).as_posix(),'sha256':sha(p),'size_bytes':p.stat().st_size,'selected_rows':len(selected)})
    for name in ['f_cashflows','f_documents','f_federal_shares','f_concentration','f_project_year','f_source_reconciliation']:
        p=release/'outputs/research/finance'/(name+'.csv');selected=[r for r in rows(p) if r.get('project_id')==PROJECT];tables[name]=selected
        provenance.append({'path':p.relative_to(release).as_posix(),'sha256':sha(p),'size_bytes':p.stat().st_size,'selected_rows':len(selected)})
    p=release/'outputs/tables/targets.csv';tables['targets']=[r for r in rows(p) if r.get('project_id')==PROJECT];provenance.append({'path':p.relative_to(release).as_posix(),'sha256':sha(p),'size_bytes':p.stat().st_size,'selected_rows':len(tables['targets'])})
    shared=root/'public/downloads/projects/youth_children/documentary/documentary_inputs.json.gz'
    with gzip.open(shared,'rt',encoding='utf-8') as f:global_profiles=json.load(f)['profiles']
    for d in global_profiles['documents']:assert hashlib.sha256(d['text'].encode()).hexdigest()==d['profile_text_sha256']
    checkpoints={x['path']:x for x in json.loads((materials/'CHECKSUMS.json').read_text())}
    manual=materials/'logic/manual_edges.csv';assert sha(manual)==checkpoints['logic/manual_edges.csv']['sha256']
    manual_rows=rows(manual);assert len(manual_rows)==10 and sum(int(x['documentary_weight_percent']) for x in manual_rows)==100
    source_docs=[]
    for d in docs:
        src=release/d['local_file'];assert sha(src)==d['local_file_sha256'],src
        target=out/'sources'/(d['source_sha256']+src.suffix);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        source_docs.append({**d,'archive_entry':'sources/'+target.name,'download_path':BASE+'sources/'+target.name,'sha256':sha(src),'size_bytes':src.stat().st_size})
    inp={'schema_version':1,'project_id':PROJECT,'source_release':'NationalProjects_Analytics_1.2.0','source_release_sha256':'4efffb01a65c67d6ed7a07dc4a16b4c6ed7d08226dd887a36721c6f9d72eca86','documentary_snapshot':'2026-10-19','tables':tables,'profiles':global_profiles,'source_provenance':provenance,'source_documents':source_docs,'manual_reviewed_links':manual_rows,'manual_review_provenance':{'source':'Kadry_Research_Materials_2026','path':'logic/manual_edges.csv','sha256':sha(manual),'source_pdf_sha256':'9613fa53bf6408a294622337dc27646e7805cc35276f2a84f020b60044f35522','pdf_pages':[155,156,157],'printed_pages':[1,2,3]},'profile_replication_basis':{'source':'Previously verified fixed 137-document research profiles','input_sha256':sha(shared)},'normalization':'Amounts retain decimal strings; manuscript content remains separate from documentary inputs.','limits':['Passport plans do not establish expenditure execution.','Documentary weights do not estimate causal effects.','Target editions are retained separately.']}
    data=gzip.compress((json.dumps(inp,ensure_ascii=False,allow_nan=False)+'\n').encode(),mtime=0)
    for p in [root/'inputs/personnel/documentary_inputs.json.gz',out/'documentary_inputs.json.gz']:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    dump(out/'source_manifest.json',{'project_id':PROJECT,'documents':source_docs,'input_provenance':provenance,'manual_review':inp['manual_review_provenance']})
    shutil.copy2(manual,out/'manual_direct_links.csv')
    shutil.copy2(release/'outputs/research/text/METHODS_RU.md',out/'text_methods.md')
    shutil.copy2(release/'outputs/research/finance/METHODS_RU.md',out/'finance_methods.md')
    code=out/'original_code';code.mkdir(exist_ok=True)
    for name in ['text_analysis.py','validate_text_analysis.py','finance_analysis.py','verify_finance.py','requirements-tested.txt']:
        shutil.copy2(release/'research'/name,code/name)
    with zipfile.ZipFile(out/'documentary_sources.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.write(out/'source_manifest.json','source_manifest.json');z.write(manual,'manual_direct_links.csv')
        for d in source_docs:z.write(root/'public'/d['download_path'],d['archive_entry'])
    print(json.dumps({'documents':len(source_docs),'input_gzip_bytes':len(data),'tables':{k:len(v) for k,v in tables.items()},'manual_direct_links':len(manual_rows)},ensure_ascii=False))
    return inp

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--release',type=Path,required=True);p.add_argument('--materials',type=Path,required=True);p.add_argument('--root',type=Path,default=APP);a=p.parse_args();prepare(a.release.resolve(),a.materials.resolve(),a.root.resolve())
