import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {coverageRatio,percentChange,buildPlanScenario,matchedPeriodChanges,seriesGroups,financeReportRows,loadHealthtechObservations} from '../src/pages/healthtech.js';

const statistics=JSON.parse(fs.readFileSync(new URL('../public/data/projects/health_technologies/statistics.json',import.meta.url),'utf8'));
const expertise=JSON.parse(fs.readFileSync(new URL('../public/data/projects/health_technologies/expertise.json',import.meta.url),'utf8'));
const source=id=>statistics.sources.find(s=>s.id===id);

test('patient coverage keeps the denominator and rejects impossible cohorts',()=>{
  assert.equal(coverageRatio(240,1000),24);
  assert.equal(coverageRatio(0,1000),0);
  for(const [a,b] of [[1001,1000],[-1,1000],[0,0],[1,0],[null,4],[2,''],['x',2],[2.5,100]])assert.equal(coverageRatio(a,b),null);
});

test('relative change is undefined at a zero or negative baseline',()=>{
  assert.equal(percentChange(100,125),25);
  assert.equal(percentChange(100,0),-100);
  assert.equal(percentChange(0,7),null);
  assert.equal(percentChange(-1,7),null);
});

test('conditional paths preserve the annual basis and the user goal without forecasting',()=>{
  const linear=buildPlanScenario(4.55,10,2025,2030,'linear','percentage');
  assert.equal(linear.rows.length,6);
  assert.equal(linear.rows[0].value,4.55);
  assert.equal(linear.rows.at(-1).value,10);
  assert.ok(Math.abs(linear.annualChange-1.09)<1e-12);
  const compound=buildPlanScenario(10,20,2025,2027,'compound','percentage');
  assert.ok(Math.abs(compound.rows[1].value-Math.sqrt(200))<1e-12);
  assert.equal(compound.rows.at(-1).value,20);
  for(const args of [[4.55,101,2025,2030,'linear','percentage'],[0,10,2025,2030,'compound'],[3,4,2026,2025],[3,4,2025,2100],[3,4,2025.5,2030],[null,4,2025,2030]])assert.equal(buildPlanScenario(...args),null);
});

test('the only independent annual fact does not acquire monthly placeholder zeroes',()=>{
  const s=source('62986'),groups=seriesGroups(s,s.national);
  assert.equal(groups.length,1);
  const numbers=groups.flatMap(g=>g.points).filter(p=>p.y!==null);
  assert.deepEqual(numbers.map(p=>p.y),[4.55]);
  assert.equal(groups[0].frequency,'annual');
  assert.ok(s.national.some(p=>p.value===0&&p.analytical_value===null));
});

test('year-to-date commercial revenue is split at the year boundary',()=>{
  const s=source('63132'),groups=seriesGroups(s,s.national);
  assert.equal(groups.length,2);
  for(const group of groups){const years=new Set(group.points.map(p=>new Date(p.x).getUTCFullYear()));assert.equal(years.size,1);}
  const pairs=matchedPeriodChanges(s.national);
  assert.ok(pairs.length>0);
  for(const p of pairs){assert.equal(p.period.slice(5),p.previous_period.slice(5));assert.equal(Number(p.period.slice(0,4)),Number(p.previous_period.slice(0,4))+1);}
});

test('missing June in patient coverage breaks the line',()=>{
  const s=source('62988'),groups=seriesGroups(s,s.national),g=groups.find(g=>g.points.some(p=>new Date(p.x).getUTCFullYear()===2026&&new Date(p.x).getUTCMonth()===4));
  assert.ok(g);
  assert.ok(g.points.some(p=>new Date(p.x).getUTCFullYear()===2026&&new Date(p.x).getUTCMonth()===5&&p.y===null));
});

test('finance source tables retain null passport cells and explicit budget zeros',()=>{
  const passport=financeReportRows(expertise,'passport_plan'),budget=financeReportRows(expertise,'budget_bill');
  assert.equal(passport.find(r=>r.code==='С2'&&r.year===2029).value,null);
  assert.equal(budget.find(r=>r.code==='С4'&&r.year===2029).value,0);
  assert.equal(budget.find(r=>r.code==='Доля резерва, %'&&r.year===2029).value,98);
  assert.equal(budget.find(r=>r.code==='Зарезервировано'&&r.year===2029).value,5613.6);
  assert.equal(passport.find(r=>r.code==='Итого'&&r.year===2025).unit,'млрд руб.');
  assert.equal(budget.find(r=>r.code==='Общий объём'&&r.year===2026).unit,'млн руб.');
});

test('source loading validates identity and can retry a failed request',async()=>{
  let calls=0;
  const selected={id:'unit-test-healthtech-source',downloads:{observations:'./data/test-healthtech-retry.json'}};
  const fetcher=async()=>{calls++;return calls===1?{ok:false,status:503}:{ok:true,json:async()=>({project_id:'health_technologies',source_id:selected.id,observations:[{value:0}]})};};
  await assert.rejects(loadHealthtechObservations(selected,fetcher),/503/);
  assert.deepEqual(await loadHealthtechObservations(selected,fetcher),[{value:0}]);
  assert.equal(calls,2);
  await assert.rejects(loadHealthtechObservations({id:'wrong-source',downloads:{observations:'./data/test-healthtech-wrong-source.json'}},async()=>({ok:true,json:async()=>({source_id:'foreign',observations:[]})})),/Неверный источник/);
  await assert.rejects(loadHealthtechObservations({id:'wrong-project',downloads:{observations:'./data/test-healthtech-wrong-project.json'}},async()=>({ok:true,json:async()=>({project_id:'family',source_id:'wrong-project',observations:[]})})),/Неверный проект/);
});
