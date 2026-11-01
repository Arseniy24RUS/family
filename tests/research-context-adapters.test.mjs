import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {prepareResearchContext} from '../src/platform/research-context-data.js';
import {ALL_RESEARCH_REGIONS,contextParams,periodContextParams,updateContextFromLocalControl,researchNavigationContext} from '../src/core/research-context.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';
import {projectHref} from '../src/platform/projects.js';

const read = path => JSON.parse(fs.readFileSync(new URL('../public/'+path,import.meta.url),'utf8'));
const catalog = read('data/regions.json');
const familyCatalog = read('data/current/catalog.json');
const manifest = read('data/latest/manifest.json');
const tourism = read('data/projects/tourism/research.json');
const health = {statistics:read('data/projects/long_active_life/statistics.json')};
const personnel = {analytics:read('data/projects/personnel/analytics.json')};
const loadSeries = async id => {
  const packet = read(manifest.sources.find(source=>source.source_id === id).published_file);
  return {...packet,rows:packet.rows.map(row=>Object.fromEntries(packet.columns.map((key,index)=>[key,row[index]])))};
};
async function prepare(projectId,state = {},page = 'map') {
  return prepareResearchContext({projectId,page,state:{nationalProject:projectId,page,...state},
    catalog:projectId === 'family' ? familyCatalog : catalog,familyData:{manifest},
    research:({tourism,long_active_life:health,personnel})[projectId],loadSeries,
    loadHealthObservations:async source=>read(source.downloads.observations).observations});
}
const tourismState = {region:'77',regions:'77,23,24',period:'2026-09-30'};

test('the real tourism request is unavailable in other default indicators without selecting their latest rows',async()=>{
  const source = await prepare('tourism',tourismState);
  assert.equal(source.regionValue,10.193);
  assert.deepEqual(contextParams(source.state),{ctx_region:'77',ctx_start:'2026-01-01',ctx_end:'2026-09-30',ctx_kind:'cumulative_ytd',ctx_frequency:'monthly'});
  for (const project of ['family','long_active_life','personnel']) {
    const switched = parseRoute(switchProject(source.state,project));
    assert.equal(switched.source,undefined);assert.equal(switched.period,undefined);
    const target = await prepare(project,switched);
    assert.equal(target.status,'unavailable',project);assert.equal(target.blocked,true,project);
    assert.equal(target.selected,null,project);assert.equal(target.regionValue,null,project);
    assert.deepEqual(contextParams(target.state),contextParams(source.state),project);
  }
});

test('the retained cumulative window applies to actual Health rows when an appropriate indicator is explicitly selected',async()=>{
  const source = await prepare('tourism',tourismState);
  const state = parseRoute(switchProject(source.state,'long_active_life'));
  const target = await prepare('long_active_life',{...state,source:'62930'});
  assert.equal(target.status,'available');assert.equal(target.blocked,false);
  assert.equal(target.state.period,'monthly|2026-09-30|');
  assert.equal(target.regionValue,15.6);assert.equal(target.state.r,'77');
  assert.deepEqual(contextParams(target.state),contextParams(source.state));
});

test('explicit available-period choices apply real Family, Health and Personnel values',async()=>{
  const source = await prepare('tourism',tourismState);
  const examples = [
    ['family','месяц|2026-09-30',1.39,'monthly','2026-09-01'],
    ['family','год|2025-12-31',1.434,'annual','2025-01-01'],
    ['long_active_life','monthly|2026-07-31|',56.66,'stock_at_period_end','2026-07-31'],
    ['personnel','annual|2024-12-31',1,'annual','2024-01-01']
  ];
  for (const [project,nativeKey,value,kind,start] of examples) {
    const missing = await prepare(project,parseRoute(switchProject(source.state,project)));
    const period = missing.periods.find(period=>period.nativeKey === nativeKey);
    assert.ok(period,project+' '+nativeKey);
    const selected = await prepare(project,{...missing.state,...periodContextParams(period),period:nativeKey});
    assert.equal(selected.blocked,false,project);assert.equal(selected.regionValue,value,project);
    assert.equal(selected.state.period,nativeKey,project);assert.equal(selected.state.ctx_kind,kind,project);
    assert.equal(selected.state.ctx_start,start,project);assert.equal(selected.state.ctx_region,'77',project);
  }
});

test('Family annual December and monthly December remain distinct even when their published numbers coincide',async()=>{
  const annual = await prepare('family',{period:'год|2025-12-31',r:'77'});
  const monthly = await prepare('family',{period:'месяц|2025-12-31',r:'77'});
  assert.equal(annual.regionValue,monthly.regionValue);
  assert.equal(annual.state.ctx_kind,'annual');assert.equal(monthly.state.ctx_kind,'monthly');
  const destination = await prepare('tourism',parseRoute(switchProject(annual.state,'tourism')));
  assert.equal(destination.blocked,true);assert.equal(destination.state.ctx_kind,'annual');
});

test('missing regional measurements are explicit even when the requested time window exists',async()=>{
  const source = await prepare('tourism',tourismState);
  const target = await prepare('long_active_life',{...contextParams(source.state),source:'63006'});
  assert.equal(target.status,'available');assert.equal(target.blocked,false);
  assert.equal(target.regionAvailable,false);assert.equal(target.regionValue,null);
});

test('multiperiod and unsupported views preserve the request without claiming time filtering',async()=>{
  const source = await prepare('tourism',tourismState);
  const state = contextParams(source.state);
  const family = await prepare('family',state,'regions');
  assert.equal(family.status,'outside');assert.equal(family.applied,false);assert.equal(family.state.r,'77');
  assert.match(family.scope,/многомерные/);assert.deepEqual(contextParams(family.state),state);
  const unsupported = await prepare('youth_children',state);
  assert.equal(unsupported.applied,false);assert.equal(unsupported.supported,false);
  assert.equal(unsupported.status,'outside');assert.deepEqual(contextParams(unsupported.state),state);
});

test('tourism comparison order stays stable and removing its final chip clears the shared territory',async()=>{
  const selected = await prepare('tourism',{...tourismState,region:'24'});
  assert.equal(selected.state.regions,'77,23,24');assert.equal(selected.state.ctx_region,'24');
  const full = await prepare('tourism',{...tourismState,regions:'77,23,24,78,50',ctx_region:'22'});
  assert.equal(full.state.regions,'77,23,24,78,22');assert.equal(full.comparisonAdjusted,true);
  const only = await prepare('tourism',{period:'2026-09-30',region:'77',regions:'77'});
  const removed = updateContextFromLocalControl(only.state,{region:'',regions:'none',period:'2026-09-30'},only.periods);
  assert.equal(removed.ctx_region,ALL_RESEARCH_REGIONS);
  const restored = await prepare('tourism',parseRoute(projectHref('tourism','map',removed)));
  assert.equal(restored.region,'');assert.equal(restored.state.regions,'none');
});

test('same-project links honor explicit territory and period; other sources resolve their own native period',async()=>{
  const model = await prepare('family',{r:'77',period:'год|2025-12-31'});
  const destination = {nationalProject:'family',page:'map',r:'23',period:'месяц|2026-09-30'};
  const shared = researchNavigationContext(model.state,destination,{periods:model.periods,sourceId:'data_21'});
  assert.equal(shared.ctx_region,'23');assert.equal(shared.ctx_end,'2026-09-30');assert.equal(shared.ctx_kind,'monthly');
  const foreign = researchNavigationContext(model.state,{...destination,source:'data_22'},{periods:model.periods,sourceId:'data_21'});
  assert.equal(foreign.ctx_region,'23');assert.equal(foreign.ctx_kind,null);
  assert.equal(parseRoute(projectHref('family','map',{...foreign,...destination,source:'data_22'})).ctx_kind,undefined);
});

test('clearing the final tourism region survives sidebar navigation and a round trip through another project',async()=>{
  const initial = await prepare('tourism',{period:'2026-09-30',region:'77',regions:'77'});
  const clearedState = updateContextFromLocalControl(initial.state,{region:'',regions:'none',period:'2026-09-30'},initial.periods);
  const cleared = await prepare('tourism',parseRoute(projectHref('tourism','map',clearedState)));
  const sidebar = parseRoute(projectHref('tourism','regions',{},cleared.state));
  const regional = await prepare('tourism',sidebar,'regions');
  assert.equal(regional.region,'');
  assert.equal(regional.state.regions,'none');
  const family = await prepare('family',parseRoute(switchProject(regional.state,'family')),'regions');
  const returned = await prepare('tourism',parseRoute(switchProject(family.state,'tourism')),'regions');
  assert.equal(returned.region,'');
  assert.equal(returned.state.regions,'none');
  assert.equal(returned.state.ctx_region,'all');
  assert.equal(returned.state.ctx_end,'2026-09-30');
});

test('an explicit All regions request from Family never restores the initial Moscow selection in Tourism',async()=>{
  const initial = await prepare('family',{period:'месяц|2026-09-30',r:'77'});
  const cleared = updateContextFromLocalControl(initial.state,{ctx_region:ALL_RESEARCH_REGIONS,r:null},initial.periods);
  const regional = await prepare('family',parseRoute(projectHref('family','regions',{},cleared)),'regions');
  const tourism = await prepare('tourism',parseRoute(switchProject(regional.state,'tourism')),'regions');
  assert.equal(tourism.region,'');assert.equal(tourism.state.regions,'none');
  assert.equal(tourism.state.ctx_region,ALL_RESEARCH_REGIONS);
  assert.equal(tourism.unknownRegion,false);assert.equal(tourism.blocked,true);
  const back = await prepare('family',parseRoute(switchProject(tourism.state,'family')),'regions');
  const map = await prepare('family',parseRoute(projectHref('family','map',{},back.state)));
  assert.equal(map.region,'');assert.equal(map.state.r,null);
  assert.equal(map.state.ctx_region,ALL_RESEARCH_REGIONS);assert.equal(map.state.ctx_end,'2026-09-30');
  assert.equal(map.blocked,false);
});

test('a fresh Tourism visit still has its initial comparison, while an explicit empty request does not',async()=>{
  const fresh = await prepare('tourism');
  assert.equal(fresh.region,'77');assert.equal(fresh.state.regions,'77,23');
  const empty = await prepare('tourism',{ctx_region:ALL_RESEARCH_REGIONS});
  assert.equal(empty.region,'');assert.equal(empty.state.regions,'none');
  assert.equal(empty.request.present,true);assert.equal(empty.request.invalidRegion,false);
});

test('source-control resets cannot silently clear the common territory or time',async()=>{
  const selected = await prepare('long_active_life',{r:'77',period:'monthly|2026-07-31|'});
  const next = updateContextFromLocalControl(selected.state,{source:'62930',period:null,r:null,region:null},selected.periods);
  assert.equal(next.ctx_region,'77');assert.equal(next.ctx_kind,'stock_at_period_end');
  const changed = await prepare('long_active_life',next);
  assert.equal(changed.blocked,true);assert.equal(changed.region,'77');
});
