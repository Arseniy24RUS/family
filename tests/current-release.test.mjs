import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {inflateRawSync} from 'node:zlib';
import {series} from '../src/core/data.js';

const root=path.resolve(import.meta.dirname,'..');
const read=p=>JSON.parse(fs.readFileSync(path.join(root,'public',p),'utf8'));
const manifest=read('data/latest/manifest.json');
const unpack=p=>p.rows.map(row=>Object.fromEntries(p.columns.map((c,i)=>[c,row[i]])));
const configured=JSON.parse(fs.readFileSync(path.join(root,'scripts/emiss_sources.json'),'utf8')).sources;
const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');

// These import bundles deliberately put input.json first, with explicit lengths
// and ordinary DEFLATE. Read only that member without a third-party ZIP package.
function bundledInput(relative){
  const bytes=fs.readFileSync(path.join(root,'public',relative));
  assert.equal(bytes.readUInt32LE(0),0x04034b50);
  assert.equal(bytes.readUInt16LE(6)&8,0);
  const method=bytes.readUInt16LE(8),size=bytes.readUInt32LE(18),nameLength=bytes.readUInt16LE(26),extraLength=bytes.readUInt16LE(28);
  assert.equal(bytes.toString('utf8',30,30+nameLength),'input.json');
  const start=30+nameLength+extraLength,compressed=bytes.subarray(start,start+size);
  assert.ok(method===0||method===8);
  return {bytes,payload:JSON.parse((method===8?inflateRawSync(compressed):compressed).toString('utf8'))};
}

test('preserved release inputs retain their fixed snapshot and observation count',()=>{
  const receipt=read('data/latest/import_validation.json');
  assert.equal(receipt.statistical_snapshot,'2026-10-15');
  assert.equal(receipt.n_sources,16);assert.equal(receipt.sources.length,16);
  let rows=0;
  for(const source of receipt.sources){
    const {bytes,payload}=bundledInput(source.input_bundle);
    assert.equal(digest(bytes),source.input_sha256);
    assert.equal(payload.statistical_snapshot,'2026-10-15');
    assert.equal(payload.snapshot.origin_kind,'live_emiss');
    assert.equal(payload.config.source_id,source.source_id);
    assert.equal(payload.config.indicator_id,source.indicator_id);
    assert.equal(payload.config.indicator_code,source.indicator_code);
    assert.equal(payload.config.unit,source.unit);
    assert.equal(payload.observations.length,source.observations);
    for(const row of payload.observations){assert.equal(row.source_id,source.indicator_id);assert.equal(row.unit,source.unit);}
    rows+=payload.observations.length;
  }
  assert.equal(rows,25627);assert.equal(rows,receipt.n_observations);
});

test('current published data preserve source contracts after imports and future refreshes',()=>{
  assert.equal(manifest.sources.length,configured.length);
  for(const config of configured){
    const item=manifest.sources.find(s=>s.source_id===config.source_id);
    assert.ok(item?.published_file);
    const p=read(item.published_file),provenance=read(item.provenance_file);
    assert.equal(p.source_id,config.source_id);
    assert.equal(p.emiss_id,config.indicator_id);assert.equal(p.unit,config.unit);
    assert.equal(provenance.indicator_id,config.indicator_id);
    assert.equal(provenance.source_url,p.source_url);
    assert.match(p.snapshot,/^\d{4}-\d{2}-\d{2}/);assert.equal(item.rows,p.rows.length);
    if(provenance.schema==='semya.release-provenance/1'){
      assert.equal(provenance.indicator_code,config.indicator_code);
      assert.equal(provenance.origin_kind,'live_emiss');
      assert.equal(provenance.published_sha256,digest(fs.readFileSync(path.join(root,'public',item.published_file))));
    }else{
      // The monthly refresh has its own transport provenance schema. Future
      // dates and observation counts must not be frozen to the initial release.
      assert.ok(Array.isArray(provenance.response_sha256)&&provenance.response_sha256.length>0);
      assert.ok(provenance.response_sha256.every(value=>/^[0-9a-f]{64}$/.test(value)));
      assert.ok(Number.isInteger(provenance.source_observations_received)&&provenance.source_observations_received>0);
      assert.match(provenance.checked_at,/^\d{4}-\d{2}-\d{2}T/);
    }
    for(const row of unpack(p))assert.ok(row.value===null||Number.isFinite(row.value));
  }
});

test('annual poverty and cumulative cultural visits keep distinct temporal semantics',()=>{
  const receipt=read('data/latest/import_validation.json');
  const poverty=bundledInput(receipt.sources.find(s=>s.source_id==='data_20').input_bundle).payload.observations;
  assert.ok(poverty.some(r=>r.period_kind==='annual'));
  assert.ok(poverty.some(r=>/квартал/.test(JSON.parse(r.dimensions_json)['Период'])));
  const culture=bundledInput(receipt.sources.find(s=>s.source_id==='data_35').input_bundle).payload.observations;
  assert.ok(culture.every(r=>r.period_kind==='cumulative_ytd'&&r.period_start.endsWith('-01-01')));
  for(const sid of ['data_20','data_35']){
    const source=manifest.sources.find(s=>s.source_id===sid),rows=unpack(read(source.published_file));
    for(const row of rows){
      if(row.type==='год')assert.ok(row.start.endsWith('-01-01')&&row.end.endsWith('-12-31'));
      if(row.type==='накопительно с января')assert.ok(row.start.endsWith('-01-01'));
      if(row.type==='квартал')assert.ok(['-03-31','-06-30','-09-30','-12-31'].some(end=>row.end.endsWith(end)));
    }
    if(read(source.provenance_file).schema==='semya.release-provenance/1'){
      if(sid==='data_20')assert.ok(rows.some(r=>r.type==='год')&&rows.some(r=>r.type==='квартал'));
      else assert.ok(rows.every(r=>r.type==='накопительно с января'));
    }
  }
});

test('legacy baseline requests load current data and invalid publication identities fail',async()=>{
  const previous=globalThis.fetch,paths=[];
  globalThis.fetch=async p=>{paths.push(p);return {ok:true,json:async()=>read(p.replace(/^\.\//,''))};};
  try{
    const p=await series('data_21','baseline',manifest);
    const published=read(manifest.sources.find(s=>s.source_id==='data_21').published_file);
    assert.equal(p.usingLatest,true);assert.equal(p.snapshot,published.snapshot);
    assert.ok(paths.every(p=>!p.includes('baseline')));
    await assert.rejects(()=>series('absent_source','latest',manifest),/не опубликованы актуальные данные/);
    await assert.rejects(()=>series('data_20','latest',{sources:[{source_id:'data_20',published_file:'data/latest/data_21.json'}]}),/другому источнику/);
  }finally{globalThis.fetch=previous;}
});
