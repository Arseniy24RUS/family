import test from 'node:test';
import assert from 'node:assert/strict';
import {
  nneTotal,growthFromBase,supportRatio,paidShipmentShare,cohortShare,
  additionalExportRatio,differenceInDifferences,requiredAnnualChange,
  targetSeries,observationBasis,selectPublicationBasis,nationalChartSeries,
  validateExportSeries,loadExportObservations
} from '../src/pages/international_export.js';
import {projects,internationalExportPages,completeProjectPages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';

test('Export completes the twelfth module while keeping authors only in Family',()=>{
  assert.equal(projects.length,12);assert.equal(internationalExportPages.length,21);
  assert.equal(completeProjectPages.international_export,internationalExportPages);
  assert.equal(getProject('international_export').color,'#2B3847');
  assert.deepEqual(projects.filter(p=>p.hasAuthors).map(p=>p.id),['family']);
  for(const page of internationalExportPages){
    const state=parseRoute(projectHref('international_export',page.id,{source:'62713',series_basis:'annual',context:'services'}));
    assert.equal(state.nationalProject,'international_export');assert.equal(state.page,page.id);assert.equal(state.series_basis,'annual');
  }
  assert.equal(parseRoute('#/projects/international_export/authors').page,'overview');
  const state=parseRoute(projectHref('international_export','targets',{source:'62713',series_basis:'annual'}));
  assert.equal(switchProject(state,'efficient_transport'),projectHref('efficient_transport','targets'));
});

test('The NNE identity and fixed-2023-base growth use the report units and denominator',()=>{
  assert.ok(Math.abs(nneTotal(122.09,41.56)-163.65)<1e-12);
  assert.ok(Math.abs(growthFromBase(163.65)-10.2020202020202)<1e-10);
  assert.equal(growthFromBase(148.5),0);
  assert.equal(growthFromBase(0),-100);
  assert.equal(nneTotal(null,41.56),null);assert.equal(nneTotal(-1,41.56),null);
});

test('Export-to-subsidy ratio is a monetary multiple, not a percentage or causal estimate',()=>{
  assert.equal(supportRatio(100,10),10);assert.equal(supportRatio(0,10),0);
  assert.equal(supportRatio(100,0),null);assert.equal(supportRatio(100,null),null);
});

test('Payments are capped per shipment before aggregation, preventing cross-shipment overpayment',()=>{
  assert.equal(paidShipmentShare([{due:100,paid:200},{due:100,paid:0}]),50);
  assert.equal(paidShipmentShare([{due:100,paid:100},{due:100,paid:50},{due:0,paid:0}]),75);
  assert.equal(paidShipmentShare([{due:0,paid:10}]),null);
  assert.equal(paidShipmentShare([{due:100,paid:null}]),null);
  assert.equal(paidShipmentShare([{due:100,paid:-1}]),null);
});

test('Cohort shares retain the complete starting denominator and reject impossible counts',()=>{
  assert.equal(cohortShare(30,80),37.5);assert.equal(cohortShare(0,80),0);
  assert.equal(cohortShare(81,80),null);assert.equal(cohortShare(0,0),null);
  assert.equal(cohortShare(null,80),null);assert.equal(cohortShare(-1,80),null);
  assert.equal(cohortShare(1.5,80),null);assert.equal(cohortShare(30,80.5),null);
});

test('Additional export requires an explicit counterfactual and preserves negative effects',()=>{
  assert.equal(additionalExportRatio(120,100,10),2);
  assert.equal(additionalExportRatio(80,100,10),-2);
  assert.equal(additionalExportRatio(120,null,10),null);
  assert.equal(additionalExportRatio(120,100,0),null);
  assert.equal(additionalExportRatio(120,-1,10),null);
  assert.equal(differenceInDifferences(10,15,8,10),3);
  assert.equal(differenceInDifferences(10,15,null,10),null);
});

test('The conditional annual rate uses five transitions from 2025 to 2030',()=>{
  assert.ok(Math.abs(requiredAnnualChange(163.65,248.10,5)-8.68)<.01);
  assert.ok(Math.abs(requiredAnnualChange(122.09,192.90,5)-9.58)<.01);
  assert.ok(Math.abs(requiredAnnualChange(41.56,55.20,5)-5.84)<.01);
  assert.equal(requiredAnnualChange(0,248.10,5),null);
  assert.equal(requiredAnnualChange(163.65,248.10,0),null);
  assert.equal(requiredAnnualChange(163.65,248.10,Infinity),null);
});

test('Annual and December observations with the same date remain separate publication series',()=>{
  const annual={year:2025,period:'2025',period_end:'2025-12-31',frequency:'annual',source_frequency:'annual',value:10.2};
  const monthly={year:2025,period:'2025-12',period_end:'2025-12-31',frequency:'monthly',source_frequency:'monthly',value:.5};
  const rows=[monthly,annual];
  assert.equal(selectPublicationBasis(rows,''),'annual');
  assert.equal(selectPublicationBasis(rows,'monthly'),'monthly');
  assert.equal(observationBasis(annual),'annual');assert.equal(observationBasis(monthly),'monthly');
  assert.throws(()=>nationalChartSeries(rows,{title:'Прирост ННЭ'}),/Нельзя соединять/);
  assert.deepEqual(nationalChartSeries(rows.filter(r=>observationBasis(r)==='annual'),{title:'Прирост ННЭ'})[0].points.map(r=>r.y),[10.2]);
});

test('Calendar accumulation splits at January and missing plan values remain null',()=>{
  const rows=[{year:2025,period_end:'2025-12-31',frequency:'cumulative_ytd',source_frequency:'monthly',value:163.65},{year:2026,period_end:'2026-01-31',frequency:'cumulative_ytd',source_frequency:'monthly',value:12}];
  const series=nationalChartSeries(rows,{title:'ННЭ'});assert.equal(series.length,2);
  assert.deepEqual(series.map(s=>s.points.map(p=>p.y)),[[163.65],[12]]);
  assert.deepEqual(targetSeries({years:{2025:null,2026:10,2030:20}}),[{year:2025,value:null},{year:2026,value:10},{year:2030,value:20}]);
});

test('Source loading rejects foreign project packets and permits a corrected retry',async()=>{
  const packet={project_id:'international_export',source_id:'62715',observations:[{source_id:'62715',period_end:'2025-12-31',value:163.65}]};
  assert.equal(validateExportSeries(packet,'62715').length,1);
  assert.throws(()=>validateExportSeries({...packet,project_id:'efficient_transport'},'62715'),/не соответствует/);
  assert.throws(()=>validateExportSeries({...packet,observations:{}},'62715'),/не соответствует/);
  assert.throws(()=>validateExportSeries({...packet,observations:[{...packet.observations[0],value:'163.65'}]},'62715'),/не прошли/);
  const original=globalThis.fetch;let calls=0;
  globalThis.fetch=async()=>new Response(JSON.stringify(++calls===1?{...packet,source_id:'62713'}:packet),{status:200});
  try{
    await assert.rejects(loadExportObservations({source_id:'62715'}),/не соответствует/);
    assert.equal((await loadExportObservations({source_id:'62715'}))[0].value,163.65);
    assert.equal((await loadExportObservations({source_id:'62715'}))[0].value,163.65);assert.equal(calls,2);
  }finally{globalThis.fetch=original;}
});
