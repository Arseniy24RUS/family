import test from 'node:test';
import assert from 'node:assert/strict';
import {targetGap,targetScenario,regionSummary} from '../src/pages/youth.js';

test('annual facts and targets produce exact interpretable required changes',()=>{
  const foreign=targetGap(414.647,500,2025,2030);
  assert.ok(Math.abs(foreign.gap-85.353)<1e-9);
  assert.ok(Math.abs(foreign.annualChange-17.0706)<1e-9);
  assert.equal(foreign.years,5);
  const qualifications=targetGap(5.6,30,2025,2030);
  assert.ok(Math.abs(qualifications.gap-24.4)<1e-9);
  assert.ok(Math.abs(qualifications.annualChange-4.88)<1e-9);
  const scenario=targetScenario(5.6,qualifications.annualChange,2025,2030);
  assert.equal(scenario.length,6);
  assert.deepEqual(scenario[0],{year:2025,value:5.6});
  assert.ok(Math.abs(scenario.at(-1).value-30)<1e-9);
  assert.ok(scenario.every(p=>!Object.hasOwn(p,'probability')));
});

test('scenario boundaries reject invalid years and preserve visibly invalid percentage results for qualification',()=>{
  for(const args of [[NaN,30,2025,2030],[5.6,Infinity,2025,2030],[5.6,30,2030,2030]])assert.equal(targetGap(...args),null);
  assert.deepEqual(targetScenario(10,1,2025.5,2030),[]);
  assert.deepEqual(targetScenario(10,1,2030,2025),[]);
  assert.deepEqual(targetScenario(10,1,2025,2200),[]);
  assert.equal(targetGap(0,30,2025,2030).annualRelativePercent,null);
  // The renderer warns about bounds. Arithmetic must not silently clip 110 to 100.
  assert.equal(targetScenario(90,10,2025,2027).at(-1).value,110);
});

test('regional summaries exclude flagged values and missing cells, without replacing them with zero',()=>{
  const result=regionSummary([{value:2,analytical_value:2},{value:8,analytical_value:8},{value:100,analytical_value:null,excluded:true},{value:null,analytical_value:null}]);
  assert.deepEqual(result,{n:2,minimum:2,q1:3.5,median:5,q3:6.5,maximum:8});
  assert.deepEqual(regionSummary([{value:null}]),{n:0,minimum:null,q1:null,median:null,q3:null,maximum:null});
});
