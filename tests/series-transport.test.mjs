import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {gzipSync} from 'node:zlib';
import {createSeriesTransport,installSeriesTransport} from '../src/core/series-transport.js';
const original=Buffer.from('{"value":12345678901234567890.123400,"raw":"0,00","name":"Туризм","quality":["excluded"]}\n');
const packed=gzipSync(original),hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const record={path:'data/projects/tourism/series/62900.json',compressed_path:'data/projects/tourism/series/62900.json.gz',bytes:original.length,sha256:hash(original),compressed_bytes:packed.length,compressed_sha256:hash(packed)};
const manifest={schema:'national-projects.series-transport/1',files:[record]};
const baseURL='https://example.test/family/';
function transport(fetcher,extras={}){return createSeriesTransport({manifest,baseURL,fetcher,...extras});}

test('exact bytes including numeric lexemes survive gzip under a GitHub Pages prefix',async()=>{
 const called=[];const t=transport(async(url,options)=>{called.push([url,options]);return new Response(packed,{headers:{'content-type':'application/gzip','content-length':String(packed.length)}});});
 const r=await t.fetch('./'+record.path);assert.deepEqual(Buffer.from(await r.arrayBuffer()),original);assert.equal(called[0][0],baseURL+record.compressed_path);assert.match(r.headers.get('content-type'),/application\/json/);assert.equal(r.headers.get('content-length'),null);
});
test('explicit compressed URL, query and Request signals retain their meaning',async()=>{
 const controller=new AbortController();let seen;
 const t=transport(async(req,init)=>{seen={req,init};return new Response(packed);});
 const request=new Request(baseURL+record.path+'?version=2',{signal:controller.signal,headers:{'X-Check':'test'}});
 assert.deepEqual(Buffer.from(await(await t.fetch(request)).arrayBuffer()),original);assert.ok(seen.req instanceof Request);assert.equal(seen.req.url,baseURL+record.compressed_path+'?version=2');assert.equal(seen.req.headers.get('X-Check'),'test');controller.abort();assert.equal(seen.req.signal.aborted,true);
 assert.deepEqual(Buffer.from(await(await t.fetch(baseURL+record.compressed_path)).arrayBuffer()),original);
});
test('unlisted URLs, another origin and non-GET methods are never rewritten',async()=>{
 const calls=[];const t=transport(async(...args)=>{calls.push(args);return new Response('{}');});
 for(const [url,init]of [['./data/authors.json',undefined],['https://other.test/family/'+record.path,undefined],[baseURL+record.path,{method:'HEAD'}],['https://example.test/other/'+record.path,undefined]]){await t.fetch(url,init);assert.equal(calls.at(-1)[0],url);assert.equal(calls.at(-1)[1],init);}
});
test('network and gzip corruption remain visible failures',async()=>{
 const missing=transport(async()=>new Response('',{status:404}));assert.equal((await missing.fetch(record.path)).status,404);
 const corrupt=transport(async()=>new Response(packed.subarray(0,packed.length-5)));await assert.rejects(async()=>{await(await corrupt.fetch(record.path)).arrayBuffer();});
 const unavailable=transport(async()=>{throw Error('offline');});await assert.rejects(unavailable.fetch(record.path),/offline/);
});
test('malformed, external and duplicate manifest paths are rejected',()=>{
 for(const change of [{path:'../escape.json'},{compressed_path:'https://other.test/x'},{sha256:'bad'},{bytes:-1}])assert.throws(()=>createSeriesTransport({baseURL,manifest:{...manifest,files:[{...record,...change}]}}));
 assert.throws(()=>createSeriesTransport({baseURL,manifest:{...manifest,files:[record,record]}}));
});
test('v2 restores large runtime JSON and still forbids arbitrary document paths',async()=>{
 const large={...record,path:'data/projects/tourism/analytics.json',compressed_path:'data/projects/tourism/analytics.json.gz'};
 const v2={schema:'national-projects.series-transport/2',files:[large]};
 const t=createSeriesTransport({baseURL,manifest:v2,fetcher:async url=>{assert.equal(url,baseURL+large.compressed_path);return new Response(packed);}});
 assert.deepEqual(Buffer.from(await(await t.fetch(large.path)).arrayBuffer()),original);
 assert.throws(()=>createSeriesTransport({baseURL,manifest:{...v2,schema:manifest.schema}}));
 for(const path of ['downloads/original.json','data/../private.json','data/.cache/cache.json','data/series-transport.json','data/%2e%2e/private.json']){
  assert.throws(()=>createSeriesTransport({baseURL,manifest:{...v2,files:[{...large,path,compressed_path:path+'.gz'}]}}));
 }
});
test('complete local docs do not enable or alter transport',async()=>{const before=globalThis.fetch;assert.deepEqual(await installSeriesTransport(),{enabled:false});assert.equal(globalThis.fetch,before);});
test('a browser without gzip support receives a clear failure instead of wrong data',async()=>{const t=transport(async()=>new Response(packed),{decompress:null});await assert.rejects(t.fetch(record.path),/браузер/);});
test('the publication meta enables transport before application data loads',async()=>{
 const previousFetch=globalThis.fetch,previousDocument=globalThis.document,handlers=[];
 try{
  globalThis.document={baseURI:baseURL+'index.html',querySelector:()=>({content:'data/series-transport.json'}),addEventListener:(name,fn)=>handlers.push([name,fn])};
  globalThis.fetch=async url=>String(url).endsWith('series-transport.json')?new Response(JSON.stringify(manifest)):new Response(packed);
  assert.deepEqual(await installSeriesTransport(),{enabled:true,records:1});
  assert.deepEqual(Buffer.from(await(await globalThis.fetch(baseURL+record.path)).arrayBuffer()),original);
  assert.equal(handlers[0][0],'click');
 }finally{globalThis.fetch=previousFetch;if(previousDocument===undefined)delete globalThis.document;else globalThis.document=previousDocument;}
});

test('an early static-article download waits for the manifest and returns original bytes',async()=>{
 const isolated=await import('../src/core/series-transport.js?early-article-click');
 const previous={fetch:globalThis.fetch,document:globalThis.document,create:URL.createObjectURL,revoke:URL.revokeObjectURL,timer:globalThis.setTimeout};
 const handlers=[];let deliverManifest,blob,downloaded='',prevented=false,manifestRequests=0;
 try{
  const pendingManifest=new Promise(resolve=>{deliverManifest=resolve;});
  globalThis.document={baseURI:baseURL+'research/projects/tourism/map.html',querySelector:()=>({content:'../../../data/series-transport.json'}),
   addEventListener:(name,fn)=>handlers.push([name,fn]),createElement:()=>({click(){downloaded=this.download;}})};
  URL.createObjectURL=value=>{blob=value;return 'blob:test';};URL.revokeObjectURL=()=>{};globalThis.setTimeout=()=>0;
  globalThis.fetch=async url=>{if(String(url).endsWith('series-transport.json')){manifestRequests++;return pendingManifest;}return new Response(packed);};
  const installation=isolated.installSeriesTransport();
  assert.equal(handlers.length,1,'download guard exists before the asynchronous manifest response');
  const anchor={href:baseURL+record.path};
  const click=handlers[0][1]({target:{closest:()=>anchor},button:0,preventDefault(){prevented=true;}});
  assert.equal(prevented,true);assert.equal(blob,undefined);
  deliverManifest(new Response(JSON.stringify(manifest)));
  await Promise.all([installation,click]);
  assert.equal(manifestRequests,1);assert.equal(downloaded,'62900.json');
  assert.deepEqual(Buffer.from(await blob.arrayBuffer()),original);
 }finally{
  globalThis.fetch=previous.fetch;URL.createObjectURL=previous.create;URL.revokeObjectURL=previous.revoke;globalThis.setTimeout=previous.timer;
  if(previous.document===undefined)delete globalThis.document;else globalThis.document=previous.document;
 }
});

test('manifest failure permits a later retry without duplicate click handlers',async()=>{
 const isolated=await import('../src/core/series-transport.js?manifest-retry');
 const previousFetch=globalThis.fetch,previousDocument=globalThis.document,handlers=[];let calls=0;
 try{
  globalThis.document={baseURI:baseURL+'index.html',querySelector:()=>({content:'data/series-transport.json'}),addEventListener:(name,fn)=>handlers.push([name,fn])};
  globalThis.fetch=async url=>{if(String(url).endsWith('series-transport.json')){calls++;return calls===1?new Response('',{status:503}):new Response(JSON.stringify(manifest));}return new Response(packed);};
  await assert.rejects(isolated.installSeriesTransport(),/503/);
  assert.deepEqual(await isolated.installSeriesTransport(),{enabled:true,records:1});
  assert.equal(calls,2);assert.equal(handlers.length,1);
  assert.deepEqual(Buffer.from(await(await globalThis.fetch(baseURL+record.path)).arrayBuffer()),original);
 }finally{globalThis.fetch=previousFetch;if(previousDocument===undefined)delete globalThis.document;else globalThis.document=previousDocument;}
});
