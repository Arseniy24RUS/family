/** Validate packaged data, local downloads, and basic relative-path deployment. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {youthPages} from '../src/platform/projects.js';
import {validateYouthContent} from './build_youth.mjs';
import {validatePersonnel} from './validate_personnel.mjs';
import {validateLonglife} from './validate_longlife.mjs';
import {validateHealthtech} from './validate_healthtech.mjs';
import {validateInfrastructure} from './validate_infrastructure.mjs';
import {validateEnvironment} from './validate_environment.mjs';
import {validateCompetitive} from './validate_competitive.mjs';
import {validateDataeconomy} from './validate_dataeconomy.mjs';
import {validateTourism} from './validate_tourism.mjs';
import {validateTransport} from './validate_transport.mjs';
import {validateExport} from './validate_export.mjs';
import {validateCurrentReports} from './current_reports.mjs';
import {projects} from '../src/platform/projects.js';
import {projectRuntimes} from '../src/platform/runtime.js';
const root=path.resolve(import.meta.dirname,'..'),docs=path.join(root,'docs');
execFileSync(process.env.PYTHON || (process.platform==='win32'?'python':'python3'),
 ['-X','utf8',path.join(root,'scripts/restore_package_copies.py')],{cwd:root,stdio:'inherit'});
const read=async p=>JSON.parse(await fs.readFile(path.join(docs,p),'utf8'));
const cat=await read('data/catalog.json'),files=await read('downloads/index.json'),manifest=await read('data/latest/manifest.json');
for(const f of files.files){assert.ok(!f.path.includes('..'));const bytes=await fs.readFile(path.join(docs,'downloads',f.path));assert.equal(bytes.length,f.bytes);assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),f.sha256);}
for(const source of cat.datasets){const packet=await read('data/baseline/'+source.id+'.json');assert.equal(packet.source_id,source.id);}
for(const source of manifest.sources||[]){if(source.published_file){assert.match(source.published_file,/^data\/latest\/[a-zA-Z0-9_.\/-]+$/);await fs.access(path.join(docs,source.published_file));}}
await fs.access(path.join(docs,'workers/lab-worker.js'));await fs.access(path.join(docs,'.nojekyll'));
console.log(`Validated ${files.files.length} download hashes, ${cat.datasets.length} baseline sources, and ${manifest.sources?.filter(s=>s.published_file).length||0} published updates.`);

// Current author documents and shared runtime are one contract across all studies.
const reports=validateCurrentReports(await read('data/current-reports.json'));
for(const report of reports.reports){
 for(const kind of ['pdf','docx']){
  const item=report[kind],bytes=await fs.readFile(path.join(docs,item.url));
  assert.equal(bytes.length,item.bytes);
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),item.sha256);
  if(kind==='pdf')assert.equal(bytes.subarray(0,5).toString(),'%PDF-');
 }
 await fs.access(path.join(docs,'assets/brand',report.project_id+'.svg'));
}
assert.deepEqual((await read('data/regions.json')).regions,(await read('data/current/catalog.json')).regions);
assert.deepEqual(Object.keys(projectRuntimes).sort(),projects.filter(p=>p.id!=='family').map(p=>p.id).sort());
for(const descriptor of Object.values(projectRuntimes)){
 await fs.access(path.resolve(docs,'src/platform',descriptor.module));
 await fs.access(path.join(docs,descriptor.stylesheet));
}
await fs.access(path.join(docs,'research/reports.html'));
await fs.access(path.join(docs,'src/core/data-transport-entry.js'));
console.log(`Validated ${reports.reports.length} current PDF/DOCX pairs, official project marks and shared runtime registry.`);

// Computed modules must be complete, finite and source-labelled; no empty UI stubs.
const ip=await read('data/projections/indicators/manifest.json'),maps=await read('data/projections/indicators/maps.json');
let n=0;
for(const e of ip.series){
 if(!e.file)continue;const p=await read(e.file);assert.equal(p.region_id,e.region_id);assert.equal(p.indicator_id,e.indicator_id);if(e.state==='ready')assert.equal(p.model_version,ip.model_version);assert.ok(p.observations.length>=6);assert.equal(p.end_date,'2030-12-31');
 for(const v of p.forecast){assert.ok(Number.isFinite(v.value)&&v.value>0);assert.ok(v.lo95<=v.lo80&&v.lo80<=v.value&&v.value<=v.hi80&&v.hi80<=v.hi95);assert.equal(maps.values[e.indicator_id][v.date.slice(0,7)][e.region_id],v.value);}n++;
}
const cp=await read('data/projections/population/manifest.json');
assert.equal(cp.regions.length,cat.regions.length+1);
for(const e of cp.regions){if(!['ready','retained'].includes(e.state))continue;assert.ok(e.input_file);await fs.access(path.join(docs,e.input_file));for(const f of Object.values(e.result_files)){const r=await read(f);assert.equal(r.region_id,e.region_id);assert.equal(r.end_date,'2030-12-31');assert.ok(r.months.length>0);for(const m of r.months){assert.ok(Math.abs(m.balance_residual)<=Math.max(1e-6,m.population*1e-10));assert.equal(m.age.male.length,101);assert.equal(m.age.female.length,101);}}}
const demo=await read('data/projections/demo_input.json');assert.equal(demo.region_id,'demo');assert.ok(!cp.regions.some(r=>r.region_id==='demo'));
const authors=await read('data/authors.json');assert.deepEqual(authors.authors.map(a=>a.surname),['Ростовская','Ситковский','Синельников','Архангельский']);
for(const name of ['ran','fnisc','isd'])await fs.access(path.join(docs,`assets/institutions/${name}.png`));
await fs.access(path.join(docs,'workers/cohort-worker.js'));
console.log(`Validated ${n} monthly forecasts, ${cp.ready} cohort projections and institutional identity.`);

const current=await read('data/current/research.json'),currentCat=await read('data/current/catalog.json');
let currentRows=0;
for(const s of current.current_metadata.sources){
 const bytes=await fs.readFile(path.join(docs,s.source));
 assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),s.sha256,'Current analysis input hash: '+s.id);
 const packet=JSON.parse(bytes);currentRows+=packet.rows.length;
 const rows=packet.rows.map(r=>Object.fromEntries(packet.columns.map((k,i)=>[k,r[i]])));
 for(const input of current.current_inputs){
  if(!current.current_metadata.features.includes(s.id))continue;
  assert.ok(rows.some(r=>r.r===input.id&&r.type+'|'+r.end===s.period&&!r.flag&&r.value===input[s.id]),'Current regional input: '+s.id+'/'+input.id);
 }
}
assert.equal(currentRows,currentCat.n_observations);
assert.equal(current.current_inputs.length,current.region_clusters.length);
assert.equal(current.current_inputs.length,current.region_similarity_network_communities.length);
for(const r of current.spatial_local_moran_long){assert.ok(r.q_value>=r.p_value-1e-12&&r.q_value<=1);assert.ok(r.cluster_type==='NS'||r.q_value<=.05);}
console.log(`Validated current analytics: ${currentRows} observations, ${current.region_clusters.length} complete regional profiles.`);

// A successful refresh must remain coherent across raw series, provenance,
// frontend aggregates, reports and locally downloadable source responses.
const youthPrefix='data/projects/youth_children/';
const youthStats=await read(youthPrefix+'statistics.json'),youthAnalytics=await read(youthPrefix+'analytics.json');
const youthReport=await read(youthPrefix+'expertise.json'),youthDocumentary=await read(youthPrefix+'documentary.json');
const sourceConfig=JSON.parse(await fs.readFile(path.join(root,'scripts/youth_emiss_sources.json'),'utf8'));
assert.equal(youthStats.project_id,'youth_children');
assert.equal(youthAnalytics.project_id,'youth_children');
assert.deepEqual(new Set(youthStats.sources.map(s=>s.id)),new Set(sourceConfig.sources.map(s=>s.indicator_id)));
const checkedReport=validateYouthContent(youthReport);
let youthCells=0,youthNumbers=0,youthExcluded=0;
for(const s of youthStats.sources){
 const packetBytes=await fs.readFile(path.join(docs,youthPrefix+'series/'+s.id+'.json'));
 const packet=JSON.parse(packetBytes),provenance=await read(youthPrefix+'provenance/'+s.id+'.json');
 assert.equal(packet.source_id,s.id);assert.equal(packet.unit,s.unit);
 assert.equal(provenance.published_sha256,crypto.createHash('sha256').update(packetBytes).digest('hex'));
 assert.equal(packet.observations.length,s.observation_count);
 const rowIds=new Set();
 for(const row of packet.observations){
  assert.equal(row.source_id,s.id);assert.ok(!rowIds.has(row.id),'Duplicate Youth observation: '+row.id);rowIds.add(row.id);
  assert.ok(row.value===null||Number.isFinite(row.value));
  assert.ok(row.analytical_value===null||Number.isFinite(row.analytical_value));
  assert.equal(row.analytical_value,row.excluded?null:row.value);
  assert.match(row.period_end,/^\d{4}-\d{2}-\d{2}$/);
  youthCells++;if(row.value!==null)youthNumbers++;if(row.excluded&&row.value!==null)youthExcluded++;
 }
 const input=await fs.readFile(path.join(docs,provenance.input_bundle));
 assert.equal(crypto.createHash('sha256').update(input).digest('hex'),provenance.input_sha256);
 if(s.downloads.current_raw){
  assert.equal(s.downloads.current_raw,provenance.current_raw);
  const raw=await fs.readFile(path.join(docs,s.downloads.current_raw));
  assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),provenance.current_raw_sha256);
 }
}
assert.equal(youthCells,youthAnalytics.coverage.observations);
assert.equal(youthNumbers,youthAnalytics.coverage.numeric_observations);
assert.equal(youthExcluded,youthAnalytics.coverage.excluded_numeric_observations);
for(const comparison of youthAnalytics.target_comparisons){
 assert.equal(comparison.formal_attainment_eligible,comparison.fact_frequency==='annual');
 assert.ok(comparison.difference_unit,'Difference unit must be explicit.');
 assert.ok(Math.abs(comparison.difference-(comparison.fact_value-comparison.target_value))<1e-7);
}
for(const p of youthPages)await fs.access(path.join(docs,'research/projects/youth_children',p.id==='overview'?'index.html':p.id+'.html'));
const reportBytes=await fs.readFile(path.join(docs,youthReport.meta.report_url));
assert.equal(crypto.createHash('sha256').update(reportBytes).digest('hex'),youthReport.meta.source_docx_sha256);
assert.ok((await fs.stat(path.join(docs,youthPrefix+'documentary.json'))).size<2*1024*1024,'Text corpus must load lazily.');
for(const document of youthDocumentary.text.documentFiles)await fs.access(path.join(docs,document.path.replace(/^\.\//,'')));
console.log(`Validated Youth: ${youthStats.sources.length} sources, ${youthCells} cells, ${youthNumbers} numeric values, ${checkedReport.routes} pages and source-linked report.`);
await validatePersonnel(root);
await validateLonglife(root);
await validateHealthtech(root);
await validateInfrastructure(root);
await validateEnvironment(root);
await validateCompetitive(root);
await validateDataeconomy(root);
await validateTourism(root);
await validateTransport(root);
await validateExport(root);
