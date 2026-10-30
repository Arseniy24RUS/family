import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {targetGap,targetScenario,regionSummary,indicatorBounds,unemploymentClass} from '../src/pages/personnel.js';

test('Personnel gaps retain the meaning and precision of verified annual values',()=>{
 const employment=targetGap(101.7,103.4,2025,2030);
 assert.ok(Math.abs(employment.gap-1.7)<1e-12);
 assert.ok(Math.abs(employment.annualChange-.34)<1e-12);
 const trained=targetGap(81.3,85,2025,2030);
 assert.ok(Math.abs(trained.annualChange-.74)<1e-12);
 const quota=targetGap(.1766,6,2025,2030);
 assert.ok(Math.abs(quota.annualChange-1.16468)<1e-12);
 // Exceeding a plan is retained as a negative signed gap, never discarded as an error.
 assert.ok(Math.abs(targetGap(112.89,100,2025,2030).gap+12.89)<1e-12);
 assert.equal(targetGap(0,100,2025,2030).annualRelativePercent,null);
});

test('Personnel ranges distinguish indexes and plan ratios from bounded shares',()=>{
 for(const id of ['62884','63038'])assert.deepEqual(indicatorBounds({id,unit:'процент'}),{minimum:0,maximum:null});
 for(const id of ['62907','63363','63238'])assert.deepEqual(indicatorBounds({id,unit:'процент'}),{minimum:0,maximum:100});
 assert.equal(targetScenario(112.89,0,2025,2030).at(-1).value,112.89);
 assert.equal(targetScenario(90,10,2025,2027).at(-1).value,110);
});

test('Scenario arithmetic rejects invalid horizons and overflow without inventing values',()=>{
 for(const args of [[NaN,100,2025,2030],[5,Infinity,2025,2030],[5,6,2025.5,2030],[5,6,2030,2030]])assert.equal(targetGap(...args),null);
 assert.deepEqual(targetScenario(1,1,2025,2024),[]);
 assert.deepEqual(targetScenario(1,1,2025,2100),[]);
 assert.deepEqual(targetScenario(1,1e308,2025,2030),[]);
 assert.equal(targetScenario(.1766,1.16468,2025,2030).length,6);
});

test('Context classes use documented half-open boundaries and preserve zero',()=>{
 for(const [v,cls] of [[0,0],[1.9,0],[2,1],[2.9,1],[3,2],[4.9,2],[5,3],[9.9,3],[10,4],[26.4,4]])assert.equal(unemploymentClass(v),cls);
 for(const v of [null,NaN,Infinity,-1])assert.equal(unemploymentClass(v),null);
});

test('The published 85-region context reproduces source quartiles and class counts',()=>{
 const context=JSON.parse(fs.readFileSync(new URL('../public/data/projects/personnel/context.json',import.meta.url),'utf8'));
 const summary=regionSummary(context.regions);
 assert.equal(summary.n,85);
 assert.equal(summary.minimum,1);
 assert.equal(summary.q1,1.9);
 assert.equal(summary.median,2.4);
 assert.equal(summary.q3,2.9);
 assert.equal(summary.maximum,26.4);
 assert.deepEqual(Array.from({length:5},(_,i)=>context.regions.filter(r=>unemploymentClass(r.value)===i).length),[22,42,10,9,2]);
 assert.equal(context.national_value,2.5);
 assert.notEqual(summary.median,context.national_value);
});

test('Missing or excluded regional values do not become zero',()=>{
 assert.deepEqual(regionSummary([{value:0,analytical_value:0},{value:8,analytical_value:8},{value:100,analytical_value:null,excluded:true},{value:null}]),{n:2,minimum:0,q1:2,median:4,q3:6,maximum:8});
 assert.deepEqual(regionSummary([{value:null}]),{n:0,minimum:null,q1:null,median:null,q3:null,maximum:null});
});
