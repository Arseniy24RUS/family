import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {buildSeo} from './build-seo.mjs';
import {buildProjects} from './build_projects.mjs';
import {buildYouthPages} from './build_youth.mjs';
import {buildPersonnelPages} from './build_personnel.mjs';
import {buildLonglifePages} from './build_longlife.mjs';
import {buildHealthtechPages,buildHealthtechFoundation} from './build_healthtech.mjs';
import {buildInfrastructurePages,buildInfrastructureFoundation} from './build_infrastructure.mjs';
import {buildEnvironmentPages,buildEnvironmentFoundation} from './build_environment.mjs';
import {buildCompetitivePages,buildCompetitiveFoundation} from './build_competitive.mjs';
import {buildDataeconomyPages,buildDataeconomyFoundation} from './build_dataeconomy.mjs';
import {buildTourismPages,buildTourismFoundation} from './build_tourism.mjs';
import {buildTransportPages,buildTransportFoundation} from './build_transport.mjs';
import {buildExportPages,buildExportFoundation} from './build_export.mjs';
import {copyBuildAssets} from './copy_build_assets.mjs';
import {buildReportsCatalogue} from './build_reports_catalogue.mjs';
import {buildRuntimeMetadata} from './build_runtime_metadata.mjs';
const root=path.resolve(import.meta.dirname,'..');
const python=process.env.PYTHON || (process.platform==='win32'?'python':'python3');
// Verify the whole author-edited edition before publishing any current report.
// Conversion is a release preparation step; ordinary builds use verified PDFs.
execFileSync(python,['-X','utf8',path.join(root,'scripts/build_current_reports.py')],{cwd:root,stdio:'inherit'});
// Recompute documentary and statistical views from their own versioned inputs.
// This stage is offline; fetching EMISS is a separate, validated refresh action.
for(const script of ['build_youth_documentary.py','build_youth_analytics.py','build_personnel_documentary.py','build_personnel_analytics.py','build_longlife_documentary.py','build_longlife_analytics.py','build_healthtech_documentary.py','build_healthtech_analytics.py','build_infrastructure_documentary.py','build_infrastructure_analytics.py','build_environment_documentary.py','build_environment_analytics.py','build_competitive_expertise.py','build_competitive_documentary.py','build_competitive_analytics.py','build_dataeconomy_expertise.py','build_dataeconomy_documentary.py','build_dataeconomy_analytics.py','build_tourism_expertise.py','build_tourism_documentary.py','build_tourism_analytics.py','build_transport_expertise.py','build_transport_documentary.py','build_transport_analytics.py','build_export_expertise.py','build_export_regional_context.py','build_export_documentary.py','build_export_analytics.py'])execFileSync(python,['-X','utf8',path.join(root,'scripts',script)],{cwd:root,stdio:'inherit'});
await buildSeo();
await buildHealthtechFoundation(root);
await buildInfrastructureFoundation(root);
await buildEnvironmentFoundation(root);
await buildCompetitiveFoundation(root);
await buildDataeconomyFoundation(root);
await buildTourismFoundation(root);
await buildTransportFoundation(root);
await buildExportFoundation(root);
await buildProjects();
await buildYouthPages();
await buildPersonnelPages();
await buildLonglifePages();
await buildHealthtechPages();
await buildInfrastructurePages();
await buildEnvironmentPages();
await buildCompetitivePages();
await buildDataeconomyPages();
await buildTourismPages();
await buildTransportPages();
await buildExportPages();
await buildReportsCatalogue(root);
execFileSync(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),['-X','utf8',path.join(root,'scripts/build_projection_downloads.py')],{cwd:root,stdio:'inherit'});
execFileSync(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),['-X','utf8',path.join(root,'scripts/build_current_analytics.py')],{cwd:root,stdio:'inherit'});
await buildRuntimeMetadata(root);
const allowedHidden=new Set(['.github','.gitignore','.gitattributes','.nojekyll']);
const publishable=p=>!p.endsWith('.tmp')&&path.relative(root,p).split(path.sep).every(part=>part!=='__pycache__'&&(!part.startsWith('.')||allowedHidden.has(part)));
// The default remains independent portable copies. Explicit local QA may use
// hardlinks when workspace capacity is limited; all edited outputs are replaced.
const linkOutput=process.argv.includes('--link-output');
const copy=(a,b)=>copyBuildAssets(a,b,{filter:publishable,link:linkOutput});
async function walk(dir){const all=[];for(const e of await fs.readdir(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(!publishable(p))continue;if(e.isDirectory())all.push(...await walk(p));else all.push(p);}return all;}
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
await copy(path.join(root,'requirements-youth-research.txt'),path.join(root,'public/downloads/code/platform/requirements-youth-research.txt'));
for(const p of await walk(path.join(root,'documentation'))){await copy(p,path.join(root,'public/downloads/documentation',path.basename(p)));}
for(const name of ['README.md','NOTICE.md','CHANGELOG.md']) await copy(path.join(root,name),path.join(root,'public/downloads/documentation',name));
const downloadRoot=path.join(root,'public/downloads'),files=[];
for(const p of await walk(downloadRoot)){const rel=path.relative(downloadRoot,p).replaceAll('\\','/');if(rel==='index.json')continue;const bytes=await fs.readFile(p);let category=rel.startsWith('code/original/')?'original_code':rel.startsWith('code/platform/')?'platform_code':rel.startsWith('code/frontend/')?'frontend_code':rel.startsWith('documents/')||rel.endsWith('.docx')||rel.endsWith('.pdf')?'document':rel.startsWith('documentation/')?'platform_code':rel.startsWith('metadata/')?'metadata':rel.endsWith('.geojson')?'geometry':rel.includes('colab')?'notebook':rel.endsWith('.zip')?'raw':'data';files.push({path:rel,title:path.basename(p),category,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')});if(bytes.length>95*1024*1024)throw Error('File too large for GitHub: '+rel);}
files.sort((a,b)=>a.path.localeCompare(b.path));await fs.writeFile(path.join(downloadRoot,'index.json'),JSON.stringify({schema:'semya.files/1',files},null,2));
const docs=path.join(root,'docs');await fs.rm(docs,{recursive:true,force:true});await copy(path.join(root,'public'),docs);await copy(path.join(root,'src'),path.join(docs,'src'));await copy(path.join(root,'index.html'),path.join(docs,'index.html'));await fs.writeFile(path.join(docs,'.nojekyll'),'');
const catalog=JSON.parse(await fs.readFile(path.join(docs,'data/current/catalog.json'),'utf8'));for(const source of catalog.datasets){await fs.access(path.join(docs,'data/baseline',source.id+'.json'));}for(const f of files)await fs.access(path.join(docs,'downloads',f.path));
console.log(`Built docs/: ${files.length} downloadable files, ${catalog.n_observations} observations, ${catalog.datasets.length} statistical sources.`);
