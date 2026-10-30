#!/usr/bin/env python3
"""Package a validated cumulative release. Fallback parts are opt-in.

Run after build and validation. Requires Python 3.11+ and the Info-ZIP zip CLI.
Do not modify source files while this process is running.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import date
from restore_package_copies import restore, SCHEMA as COPY_SCHEMA

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','node_modules','__pycache__','.pytest_cache','.cache','qa','deliverables'}
ALLOWED_HIDDEN={'.github','.gitignore','.gitattributes','.nojekyll'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def source_files():
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink():continue
        if any(part in EXCLUDED for part in rel.parts):continue
        if any(part.startswith('.') and part not in ALLOWED_HIDDEN for part in rel.parts):continue
        if path.suffix in {'.pyc','.pyo','.tmp'} or path.name in {'RELEASE_MANIFEST.json','PACKAGE_COPIES.json'}:continue
        yield path

def published_source(relative):
    if relative == 'docs/index.html':return 'index.html'
    if relative.startswith('docs/src/'):return relative[len('docs/'):]
    if relative.startswith('docs/'):return 'public/'+relative[len('docs/'):]
    return None

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--part-mib',type=int,default=0,help='Optional ordinary backup ZIP size; 0 creates only the full ZIP.')
    parser.add_argument('--compression-level',type=int,choices=range(1,10),default=6,
                        help='Standard ZIP deflate compression, 1–9. Use 9 for a compact single cumulative archive.')
    parser.add_argument('--deduplicate-docs',action='store_true',
                        help='Store each identical source/docs payload once. The local launcher restores docs copies without network access.')
    parser.add_argument('--date',default=date.today().isoformat(),help='Release date in YYYY-MM-DD format.')
    args=parser.parse_args()
    output=args.output.resolve()
    if output.is_relative_to(ROOT):parser.error('Output must be outside the project checkout.')
    if not shutil.which('zip'):parser.error('Install Info-ZIP zip for release packaging.')
    if args.part_mib and args.part_mib<10:parser.error('--part-mib must be 0 or at least 10.')
    try:date.fromisoformat(args.date)
    except ValueError:parser.error('--date must be YYYY-MM-DD.')
    version=json.loads((ROOT/'package.json').read_text())['version']
    name='NationalProjects_Platform_'+version
    output.mkdir(parents=True,exist_ok=True)
    target=output/(name+'_FULL.zip')
    if target.exists():parser.error('Full output already exists; choose a new output directory.')
    restore(ROOT)
    paths=list(source_files())
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip() if (ROOT/'.git').exists() else '50ad21c1ad1c94e3cf07857363333df120558617'
    prior=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text()) if (ROOT/'RELEASE_MANIFEST.json').exists() else {}
    deleted=subprocess.check_output(['git','diff','--name-only','--diff-filter=D'],cwd=ROOT,text=True).splitlines() if (ROOT/'.git').exists() else []
    removed=sorted(set(prior.get('removed_paths',[]))|set(deleted))
    notes=['Cumulative source and prebuilt docs.','Extract the full ZIP, then use START_HERE.html or start_local.bat.']
    if args.part_mib:notes.append('All fallback ZIP files must be extracted into the same parent directory.')
    records=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in paths]
    by_path={entry['path']:entry for entry in records}
    copies={}
    if args.deduplicate_docs:
        for entry in records:
            source=published_source(entry['path'])
            if source in by_path and (entry['bytes'],entry['sha256']) == (by_path[source]['bytes'],by_path[source]['sha256']):
                copies[entry['path']]={**entry,'source':source}
        copy_manifest={'schema':COPY_SCHEMA,'release_version':version,'copies':list(copies.values()),
                       'instructions':'Run start_local.bat / start_local.sh or python scripts/restore_package_copies.py. npm run build recreates docs from the complete sources as usual. Existing files are never overwritten.'}
        copy_path=ROOT/'PACKAGE_COPIES.json'
        copy_path.write_text(json.dumps(copy_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        paths.append(copy_path)
        records.append({'path':copy_path.name,'bytes':copy_path.stat().st_size,'sha256':digest(copy_path)})
        notes.append('Byte-identical docs copies are represented by PACKAGE_COPIES.json; all source bytes are physically present. Local preview restores missing copies automatically. Build the complete docs/ before committing to GitHub Pages.')
    base_release=prior.get('base_release') if prior.get('version')==version else prior.get('version')
    manifest={'schema':'national-projects.release/1','version':version,'base_release':base_release,'source_commit':commit,'created_date':args.date,'files':records,'removed_paths':removed,'notes':notes,
              'packaging':{'mode':'deduplicated-docs' if copies else 'full','copies_manifest':'PACKAGE_COPIES.json' if copies else None,'deduplicated_copies':len(copies)}}
    (ROOT/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    paths.append(ROOT/'RELEASE_MANIFEST.json')
    packed_paths=[p for p in paths if p.relative_to(ROOT).as_posix() not in copies]
    with tempfile.TemporaryDirectory(prefix='nationalprojects-package-',dir=output.parent) as stage:
        (Path(stage)/name).symlink_to(ROOT,target_is_directory=True)
        relative=[name+'/'+p.relative_to(ROOT).as_posix() for p in packed_paths]
        subprocess.run(['zip','-q','-'+str(args.compression_level),str(target),'-@'],cwd=stage,input='\n'.join(relative)+'\n',text=True,check=True)
    # Reopen after Info-ZIP exits. Validate every source byte before making backups.
    with zipfile.ZipFile(target) as archive:
        corrupt=archive.testzip()
        if corrupt:raise RuntimeError('ZIP CRC failed: '+corrupt)
        assert set(archive.namelist())==set(relative)
        verified={}
        for item in manifest['files']:
            retained=copies.get(item['path'],{}).get('source',item['path'])
            if retained not in verified:verified[retained]=hashlib.sha256(archive.read(name+'/'+retained)).hexdigest()
            actual=verified[retained]
            if actual!=item['sha256']:raise RuntimeError('Packaged file changed: '+item['path'])
        groups=[];group=[];size=0;limit=args.part_mib*1024*1024
        for entry in (archive.infolist() if args.part_mib else []):
            if group and size+entry.compress_size>limit:groups.append(group);group=[];size=0
            group.append(entry);size+=entry.compress_size
        if group:groups.append(group)
        backups=[]
        for i,entries in enumerate(groups,1):
            part=output/(name+f'_BACKUP_{i}_of_{len(groups)}.zip')
            if part.exists():raise FileExistsError(part)
            with zipfile.ZipFile(part,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=args.compression_level) as out:
                for entry in entries:out.writestr(entry.filename,archive.read(entry.filename))
            with zipfile.ZipFile(part) as check:
                if check.testzip():raise RuntimeError('Backup CRC failed: '+str(part))
            backups.append({'name':part.name,'bytes':part.stat().st_size,'sha256':digest(part),'files':len(entries)})
    results={'version':version,'full':{'name':target.name,'bytes':target.stat().st_size,'sha256':digest(target),'files':len(packed_paths)},'backups':backups,'logical_files':len(paths),'deduplicated_copies':len(copies),'uncompressed_bytes':sum(p.stat().st_size for p in paths),'physical_payload_bytes':sum(p.stat().st_size for p in packed_paths),'validation':'CRC and every logical file SHA256 passed; duplicate copies resolve to physically retained bytes'}
    (output/'DOWNLOAD_MANIFEST.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    lines=[item['sha256']+'  '+item['name'] for item in [results['full'],*backups]]
    (output/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n')
    print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
