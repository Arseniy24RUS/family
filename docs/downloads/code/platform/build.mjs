import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..');
execFileSync(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),['-X','utf8',path.join(root,'scripts/build_projection_downloads.py')],{cwd:root,stdio:'inherit'});
const copy=async(a,b)=>{await fs.mkdir(path.dirname(b),{recursive:true});await fs.cp(a,b,{recursive:true});};
async function walk(dir){const all=[];for(const e of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())all.push(...await walk(p));else all.push(p);}return all;}
// Bundle the tiny local worker without a third-party build tool or runtime import.
const statsSource=(await fs.readFile(path.join(root,'src/core/stats.js'),'utf8')).replace(/^export /gm,'');
const workerSource=(await fs.readFile(path.join(root,'src/core/worker.js'),'utf8')).replace(/^import .*;\n/m,'');
await fs.mkdir(path.join(root,'public/workers'),{recursive:true});
await fs.writeFile(path.join(root,'public/workers/lab-worker.js'),'/* Generated from src/core/stats.js and worker.js. */\n'+statsSource+'\n'+workerSource);
const cohortSource=(await fs.readFile(path.join(root,'src/core/cohort.js'),'utf8')).replace(/^export /gm,'');
await fs.writeFile(path.join(root,'public/workers/cohort-worker.js'),'/* Generated from src/core/cohort.js */\n'+cohortSource+'\nself.onmessage = e => { try { self.postMessage({result:simulateCohort(e.data.input,e.data.options)}); } catch(error) { self.postMessage({error:error.message}); } };\n');
// Publish implementation and provenance with the interface. No external library or CDN is required.
for(const p of await walk(path.join(root,'scripts'))){if(!/\.(py|mjs|json|txt)$/.test(p)||p.includes('__pycache__'))continue;await copy(p,path.join(root,'public/downloads/code/platform',path.relative(path.join(root,'scripts'),p)));}
for(const p of await walk(path.join(root,'src'))){await copy(p,path.join(root,'public/downloads/code/frontend',path.relative(path.join(root,'src'),p)));}
for(const p of await walk(path.join(root,'documentation'))){await copy(p,path.join(root,'public/downloads/documentation',path.basename(p)));}
for(const name of ['README.md','NOTICE.md','CHANGELOG.md']) await copy(path.join(root,name),path.join(root,'public/downloads/documentation',name));
const downloadRoot=path.join(root,'public/downloads'),files=[];
for(const p of await walk(downloadRoot)){const rel=path.relative(downloadRoot,p).replaceAll('\\','/');if(rel==='index.json')continue;const bytes=await fs.readFile(p);let category=rel.startsWith('code/original/')?'original_code':rel.startsWith('code/platform/')?'platform_code':rel.startsWith('code/frontend/')?'frontend_code':rel.startsWith('documents/')||rel.endsWith('.docx')?'document':rel.startsWith('documentation/')?'platform_code':rel.startsWith('metadata/')?'metadata':rel.endsWith('.geojson')?'geometry':rel.includes('colab')?'notebook':rel.endsWith('.zip')?'raw':'data';files.push({path:rel,title:path.basename(p),category,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')});if(bytes.length>95*1024*1024)throw Error('File too large for GitHub: '+rel);}
files.sort((a,b)=>a.path.localeCompare(b.path));await fs.writeFile(path.join(downloadRoot,'index.json'),JSON.stringify({schema:'semya.files/1',files},null,2));
const docs=path.join(root,'docs');await fs.rm(docs,{recursive:true,force:true});await copy(path.join(root,'public'),docs);await copy(path.join(root,'src'),path.join(docs,'src'));await copy(path.join(root,'index.html'),path.join(docs,'index.html'));await fs.writeFile(path.join(docs,'.nojekyll'),'');
const catalog=JSON.parse(await fs.readFile(path.join(docs,'data/catalog.json'),'utf8'));for(const source of catalog.datasets){await fs.access(path.join(docs,'data/baseline',source.id+'.json'));}for(const f of files)await fs.access(path.join(docs,'downloads',f.path));
console.log(`Built docs/: ${files.length} downloadable files, ${catalog.n_observations} observations, ${catalog.datasets.length} statistical sources.`);
