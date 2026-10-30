import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {
  generalizedCost,bottleneckCapacity,accessiblePopulationShare,
  capacityIndex,digitalIndex,investmentIndex,requiredAnnualChange,
  targetSeries,nationalChartSeries,targetsForDomain,validateTransportSeries,loadTransportObservations
} from '../src/pages/efficient_transport.js';
import {projects,efficientTransportPages,completeProjectPages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';

test('Transport routes preserve project identity, data filters and family-only author scope',()=>{
  assert.equal(projects.length,12);
  assert.equal(efficientTransportPages.length,21);
  assert.equal(completeProjectPages.efficient_transport,efficientTransportPages);
  assert.equal(getProject('efficient_transport').color,'#DCAA44');
  assert.deepEqual(projects.filter(p=>p.hasAuthors).map(p=>p.id),['family']);
  for(const page of efficientTransportPages){
    const state=parseRoute(projectHref('efficient_transport',page.id,{source:'62820',geography:'ports',basin_measure:'change'}));
    assert.equal(state.nationalProject,'efficient_transport');
    assert.equal(state.page,page.id);
    assert.equal(state.source,'62820');
    assert.equal(state.basin_measure,'change');
  }
  assert.equal(parseRoute('#/projects/efficient_transport/authors').page,'overview');
  const state=parseRoute(projectHref('efficient_transport','lab',{calculator:'digital_index'}));
  assert.equal(switchProject(state,'tourism'),projectHref('tourism','lab'));
});

test('Generalized costs preserve monetary and time components with explicit missing-data guards',()=>{
  assert.equal(generalizedCost(2000,3,500,250),3750);
  assert.equal(generalizedCost(0,0,0,0),0);
  assert.equal(generalizedCost(100,null,100,0),null);
  assert.equal(generalizedCost(100,2,-1,0),null);
  assert.equal(generalizedCost(100,Infinity,10,0),null);
});

test('Sequential chain capacity follows the restrictive link and does not sum capacities',()=>{
  assert.equal(bottleneckCapacity([100,60,120]),60);
  assert.equal(bottleneckCapacity([100,0,120]),0);
  assert.equal(bottleneckCapacity([100,null,120]),null);
  assert.equal(bottleneckCapacity([100,-1,120]),null);
  assert.equal(bottleneckCapacity([]),null);
});

test('Accessibility weights territories by population and includes the threshold boundary',()=>{
  const areas=[{population:100,time:20},{population:300,time:45},{population:600,time:70}];
  assert.equal(accessiblePopulationShare(areas,45),40);
  assert.equal(accessiblePopulationShare(areas,19),0);
  assert.equal(accessiblePopulationShare(areas,70),100);
  assert.equal(accessiblePopulationShare([{population:0,time:1}],10),null);
  assert.equal(accessiblePopulationShare([{population:100,time:null}],10),null);
  assert.equal(accessiblePopulationShare(areas,-1),null);
});

test('Capacity and digital indices retain their source denominators and scales',()=>{
  assert.equal(capacityIndex(1,1),100);
  assert.ok(Math.abs(capacityIndex(1.5,1.25)-143)<1e-10);
  assert.equal(capacityIndex(1,null),null);
  assert.equal(digitalIndex(1e9),20);
  assert.equal(digitalIndex(6e9),120,'The fixed forecast denominator is not a current share bounded at 100%.');
  assert.equal(digitalIndex(null),null);
  assert.equal(digitalIndex(-1),null);
});

test('Investment index preserves its base offset and financing-share guard',()=>{
  assert.equal(investmentIndex(.66,50,100),150);
  assert.equal(investmentIndex(.66,0,100),100);
  assert.equal(investmentIndex(-.66,50,100),50,'A decline in calculated transport work may reduce the index.');
  assert.equal(investmentIndex(.66,100,50),null);
  assert.equal(investmentIndex(.66,0,0),null);
  assert.equal(investmentIndex(null,50,100),null);
});

test('Passport trajectories preserve missing plan cells and their finite horizon',()=>{
  assert.deepEqual(targetSeries({years:{2024:10,2025:null,2026:12,2027:14,2028:20,2029:null,2030:null,2031:30}}),[
    {year:2025,value:null},{year:2026,value:12},{year:2027,value:14},{year:2028,value:20},{year:2029,value:null},{year:2030,value:null}
  ]);
  assert.ok(Math.abs(requiredAnnualChange(100,121,2)-10)<1e-10);
  assert.equal(requiredAnnualChange(0,121,2),null);
  assert.equal(requiredAnnualChange(100,121,0),null);
  assert.equal(requiredAnnualChange(100,121,Infinity),null);
});

test('Annual cumulative flows split at January while project-cumulative capacity retains its sequence',()=>{
  const rows=[
    {year:2025,period_end:'2025-11-30',value:33,frequency:'cumulative_ytd'},
    {year:2025,period_end:'2025-12-31',value:37,frequency:'cumulative_ytd'},
    {year:2026,period_end:'2026-01-31',value:3,frequency:'cumulative_ytd'},
    {year:2026,period_end:'2026-02-28',value:null,frequency:'cumulative_ytd'}
  ];
  const flow=nationalChartSeries(rows,{source_id:'62820',title:'СМП'});
  assert.equal(flow.length,2);
  assert.deepEqual(flow.map(x=>x.points.map(p=>p.y)),[[33,37],[3,null]]);
  const stock=nationalChartSeries(rows.map(r=>({...r,frequency:'monthly_stock',period_semantics:'project_cumulative_capacity'})),{title:'Мощность'});
  assert.equal(stock.length,1);
  assert.equal(stock[0].points.length,4);
});


test('Lazy statistical packets reject foreign projects, source IDs and malformed rows',()=>{
  const valid={project_id:'efficient_transport',source_id:'62820',observations:[{source_id:'62820',period_end:'2025-12-31',value:37.02}]};
  assert.equal(validateTransportSeries(valid,'62820').length,1);
  assert.throws(()=>validateTransportSeries({...valid,project_id:'tourism'},'62820'),/не соответствует/);
  assert.throws(()=>validateTransportSeries({...valid,source_id:'62851'},'62820'),/не соответствует/);
  assert.throws(()=>validateTransportSeries({...valid,observations:{}},'62820'),/не соответствует/);
  assert.throws(()=>validateTransportSeries({...valid,observations:[{...valid.observations[0],value:'37.02'}]},'62820'),/не прошли/);
});

test('A rejected lazy packet is evicted so a corrected source can be retried',async()=>{
  const original=globalThis.fetch;let calls=0;
  const packet={project_id:'efficient_transport',source_id:'62820',observations:[{source_id:'62820',period_end:'2025-12-31',value:37.02}]};
  globalThis.fetch=async()=>new Response(JSON.stringify(++calls===1?{...packet,project_id:'tourism'}:packet),{status:200});
  try{
    await assert.rejects(loadTransportObservations({source_id:'62820'}),/не соответствует/);
    assert.equal((await loadTransportObservations({source_id:'62820'}))[0].value,37.02);
    assert.equal((await loadTransportObservations({source_id:'62820'}))[0].value,37.02);
    assert.equal(calls,2);
  }finally{globalThis.fetch=original;}
});


test('Federal direction links retain indicators repeated at the national level',async()=>{
  const documentary=JSON.parse(await fs.readFile(new URL('../public/data/projects/efficient_transport/documentary.json',import.meta.url),'utf8'));
  for(const [domain,source] of [['Т2','62820'],['Т6','62832'],['Т8','62851']]){
    assert.ok(targetsForDomain(documentary.targets,domain).some(item=>item.source_id===source),domain+' keeps its shared national indicator');
  }
  assert.equal(targetsForDomain(documentary.targets,'Т2').length,1);
  assert.equal(targetsForDomain(documentary.targets,'Т6').length,3);
  assert.equal(targetsForDomain(documentary.targets,'Т8').length,2);
});
