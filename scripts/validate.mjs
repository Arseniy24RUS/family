/** Validate packaged data, local downloads, and basic relative-path deployment. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..'),docs=path.join(root,'docs');
const read=async p=>JSON.parse(await fs.readFile(path.join(docs,p),'utf8'));
const cat=await read('data/catalog.json'),files=await read('downloads/index.json'),manifest=await read('data/latest/manifest.json');
for(const f of files.files){assert.ok(!f.path.includes('..'));const bytes=await fs.readFile(path.join(docs,'downloads',f.path));assert.equal(bytes.length,f.bytes);assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),f.sha256);}
for(const source of cat.datasets){const packet=await read('data/baseline/'+source.id+'.json');assert.equal(packet.source_id,source.id);}
for(const source of manifest.sources||[]){if(source.published_file){assert.match(source.published_file,/^data\/latest\/[a-zA-Z0-9_.\/-]+$/);await fs.access(path.join(docs,source.published_file));}}
await fs.access(path.join(docs,'workers/lab-worker.js'));await fs.access(path.join(docs,'.nojekyll'));
console.log(`Validated ${files.files.length} download hashes, ${cat.datasets.length} baseline sources, and ${manifest.sources?.filter(s=>s.published_file).length||0} published updates.`);

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
