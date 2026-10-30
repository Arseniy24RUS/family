import test from 'node:test';
import assert from 'node:assert/strict';
import {targetGap,targetScenario,regionSummary,indicatorBounds,lowerIsFavourable,differenceUnit,
  sliceKey,observationSlices,regionalSlice,pairedRegions,samePeriodChanges,
  loadSourceObservations} from '../src/pages/longlife.js';

const observation=(code,value,extra={})=>({code,map_id:code,name:'Регион '+code,
  geo_level:'regional',frequency:'monthly',period:'2026-07',period_end:'2026-07-31',
  value,analytical_value:value,category:{},geographic_comparison_eligible:true,...extra});

test('target arithmetic preserves signs and zero without inventing a relative growth rate',()=>{
  assert.deepEqual(targetGap(10,8,2025,2030),{years:5,gap:-2,annualChange:-.4,
    annualRelativePercent:100*((8/10)**.2-1)});
  assert.equal(targetGap(0,20,2025,2030).annualChange,4);
  assert.equal(targetGap(0,20,2025,2030).annualRelativePercent,null);
  assert.equal(targetGap(20,20,2030,2030),null);
  assert.equal(targetGap(null,20,2025,2030),null);
  assert.deepEqual(targetScenario(10,-.4,2025,2030).at(-1),{year:2030,value:8});
  assert.deepEqual(targetScenario(0,Number.MAX_VALUE,2025,2030),[]);
});

test('health indicators use explicit domains and favourable directions',()=>{
  assert.deepEqual(indicatorBounds({domain:'proportion_0_100'}),{minimum:0,maximum:100});
  assert.deepEqual(indicatorBounds({domain:'nonnegative_ratio'}),{minimum:0,maximum:null});
  assert.deepEqual(indicatorBounds({domain:'growth_rate'}),{minimum:-100,maximum:null});
  assert.deepEqual(indicatorBounds({domain:'rate_per_10000'}),{minimum:0,maximum:null});
  assert.deepEqual(indicatorBounds({unit:'процент'}),{minimum:null,maximum:null});
  assert.deepEqual(indicatorBounds({lower_bound:-100,upper_bound:null}),{minimum:-100,maximum:null});
  assert.equal(lowerIsFavourable({direction:'lower'}),true);
  assert.equal(lowerIsFavourable({direction:'higher'},{direction:'decrease'}),true);
  assert.equal(lowerIsFavourable({direction:'higher'}),false);
  assert.equal(differenceUnit({id:'63006',domain:'nonnegative_ratio',unit:'процент'}),'пункты индекса');
  assert.equal(differenceUnit({id:'62926',domain:'nonnegative_ratio',unit:'процент'}),'п.п.');
});

test('regional summaries retain legitimate zeros and do not count missing/excluded values',()=>{
  const rows=[observation('01',0),observation('02',10),observation('03',20),
    observation('04',40),observation('05',null),observation('06',102,{analytical_value:null,excluded:true})];
  assert.deepEqual(regionSummary(rows),{n:4,minimum:0,q1:7.5,median:15,q3:25,maximum:40});
  assert.deepEqual(regionSummary([]),{n:0,minimum:null,q1:null,median:null,q3:null,maximum:null});
});

test('annual and December observations never merge into one slice',()=>{
  const rows=[observation('01',10,{period:'2025',period_end:'2025-12-31',frequency:'annual'}),
    observation('01',12,{period:'2025-12',period_end:'2025-12-31'}),
    observation('02',0,{period:'2025-12',period_end:'2025-12-31'})];
  const slices=observationSlices(rows);
  assert.equal(slices.length,2);
  assert.equal(regionalSlice(rows,sliceKey(rows[0])).length,1);
  assert.deepEqual(regionalSlice(rows,sliceKey(rows[1])).map(r=>r.analytical_value),[12,0]);
});

test('regional scope removes ambiguous parent aggregates only when requested',()=>{
  const rows=[observation('01',10),observation('29',20,{geographic_comparison_eligible:false}),observation('83',30)];
  assert.equal(regionalSlice(rows,sliceKey(rows[0])).length,3);
  assert.deepEqual(regionalSlice(rows,sliceKey(rows[0]),{comparable:true}).map(r=>r.code),['01','83']);
});

test('a confirmed exclusive territory survives a missing ambiguous parent with the same map code',()=>{
  // ЕМИСС 62930, September 2026: the source retains both original rows.
  const parent=observation('29',null,{name:'Архангельская область',excluded:true,
    status:'missing',geographic_comparison_eligible:false,source_id:'62930',
    period:'2026-09',period_end:'2026-09-30'});
  const exclusive=observation('29',49,{name:'Архангельская область (кроме Ненецкого автономного округа)',
    excluded:false,source_id:'62930',period:'2026-09',period_end:'2026-09-30'});
  for(const rows of [[parent,exclusive],[exclusive,parent]]){
    for(const comparable of [false,true]){
      const selected=regionalSlice(rows,sliceKey(parent),{comparable});
      assert.equal(selected.length,1);
      assert.equal(selected[0].analytical_value,49);
      assert.equal(selected[0].geographic_comparison_eligible,true);
      assert.equal(selected[0].name,exclusive.name);
    }
    assert.equal(rows.length,2);assert.equal(parent.analytical_value,null);
  }
});

test('geographic eligibility takes precedence without filling a missing exclusive observation from its parent',()=>{
  const parent=observation('29',60,{geographic_comparison_eligible:false});
  const exclusive=observation('29',49);
  assert.equal(regionalSlice([parent,exclusive],sliceKey(parent))[0].analytical_value,49);
  const missing={...exclusive,value:null,analytical_value:null,excluded:true,status:'missing'};
  const selected=regionalSlice([parent,missing],sliceKey(parent))[0];
  assert.equal(selected.analytical_value,null);
  assert.equal(selected.geographic_comparison_eligible,true);
});

test('conflicting duplicate regional values are not silently selected or averaged',()=>{
  const rows=[observation('01',10),observation('01',20),observation('01',10),observation('02',0),observation('02',0)];
  const selected=regionalSlice(rows,sliceKey(rows[0]));
  assert.equal(selected.length,2);
  assert.equal(selected[0].analytical_value,null);
  assert.equal(selected[0].excluded,true);
  assert.equal(selected[1].analytical_value,0);
});

test('paired analyses join complete comparable regions in the same date and frequency',()=>{
  const a=[observation('01',0),observation('02',10),observation('29',20,{geographic_comparison_eligible:false}),observation('03',null)];
  const b=[observation('01',5),observation('02',20),observation('29',30),observation('03',40)];
  const pairs=pairedRegions(a,b,sliceKey(a[0]),sliceKey(b[0]));
  assert.deepEqual(pairs.map(r=>[r.id,r.x,r.y]),[['01',0,5],['02',10,20]]);
  const otherDate=b.map(r=>({...r,period_end:'2026-08-31'}));
  assert.deepEqual(pairedRegions(a,otherDate,sliceKey(a[0]),sliceKey(otherDate[0])),[]);
  const otherFrequency=b.map(r=>({...r,frequency:'annual'}));
  assert.deepEqual(pairedRegions(a,otherFrequency,sliceKey(a[0]),sliceKey(otherFrequency[0])),[]);
});

test('same-period changes respect annual/monthly separation and leap month ends',()=>{
  const rows=[observation('RU',0,{period:'2024-02',period_end:'2024-02-29',geo_level:'national'}),
    observation('RU',4,{period:'2025-02',period_end:'2025-02-28',geo_level:'national'}),
    observation('RU',9,{period:'2024',period_end:'2024-12-31',frequency:'annual',geo_level:'national'}),
    observation('RU',15,{period:'2025-12',period_end:'2025-12-31',geo_level:'national'})];
  const differences=samePeriodChanges(rows);
  assert.equal(differences.length,1);
  assert.equal(differences[0].change,4);
  assert.equal(differences[0].prior_period,'2024-02');
});

test('lazy loading shares successful concurrent requests',async()=>{
  const source={id:'test-once',downloads:{observations:'qa/test-once.json'}};
  let requests=0;
  const fetcher=async()=>{requests++;return{ok:true,json:async()=>({source_id:source.id,observations:[{value:0}]})};};
  const [a,b]=await Promise.all([loadSourceObservations(source,fetcher),loadSourceObservations(source,fetcher)]);
  assert.equal(requests,1);
  assert.equal(a,b);
  assert.equal(a[0].value,0);
});

test('a failed lazy request is evicted and a retry retrieves the source',async()=>{
  const source={id:'test-retry',downloads:{observations:'qa/test-retry.json'}};
  let requests=0;
  const fetcher=async()=>++requests===1?{ok:false,status:503}:{ok:true,json:async()=>({source_id:source.id,observations:[{value:12}]})};
  await assert.rejects(loadSourceObservations(source,fetcher),/HTTP 503/);
  const rows=await loadSourceObservations(source,fetcher);
  assert.equal(requests,2);
  assert.equal(rows[0].value,12);
});

test('lazy loading validates source identity and shape before caching',async()=>{
  const source={id:'test-identity',downloads:{observations:'qa/test-identity.json'}};
  await assert.rejects(loadSourceObservations(source,async()=>({ok:true,json:async()=>({source_id:'wrong',observations:[]})})),/Идентификатор/);
  await assert.rejects(loadSourceObservations(source,async()=>({ok:true,json:async()=>({source_id:source.id,observations:null})})),/таблица наблюдений/);
  const rows=await loadSourceObservations(source,async()=>({ok:true,json:async()=>({source_id:source.id,observations:[]})}));
  assert.deepEqual(rows,[]);
});
