import test from 'node:test';
import assert from 'node:assert/strict';
import {annualScenarioAnchors,housingDecomposition,accessibilityByThreshold,lifeCycleCost,buildPlanScenario,matchedPeriodChanges,seriesGroups,regionalSlice,sliceKey,pairedRegions,financeTotals,loadInfrastructureObservations} from '../src/pages/infrastructure.js';

const close=(a,b,tol=1e-10)=>assert.ok(Math.abs(a-b)<tol,`${a} ≠ ${b}`);
test('housing ratio decomposition preserves the exact total and makes denominator contraction visible',()=>{
 const r=housingDecomposition(100,4,110,3.5);close(r.before,25);close(r.after,110/3.5);close(r.stock_contribution+r.population_contribution,r.difference);
 const onlyDenominator=housingDecomposition(100,4,100,2);assert.equal(onlyDenominator.stock_contribution,0);assert.equal(onlyDenominator.population_contribution,25);
 for(const args of [[null,4,100,3],[100,0,100,3],[100,4,-1,3],[100,4,100,0]])assert.equal(housingDecomposition(...args),null);
});
test('accessibility uses residents as weights and includes the stated time threshold',()=>{
 const result=accessibilityByThreshold('Территория; жителей; время\nА;100;10\nБ;900;30\nВ;50;31',30);assert.equal(result.total,1050);assert.equal(result.covered,1000);close(result.percentage,100000/1050);assert.equal(result.rows[1].within_threshold,true);
 for(const args of [['А;0;10',30],['А;1.5;10',30],['А;10;',30],['А;10;5',null],['А;10;-1',30],['А;10;5\nБ;10;нет',30]])assert.equal(accessibilityByThreshold(...args),null);
});
test('life-cycle costs discount capital, operation, repairs and residual value in their own years',()=>{
 const r=lifeCycleCost(100,10,2,10,20,'1;5\n1;5\n2;10');close(r.present_value,100+20/1.1+(10+10-20)/1.21);assert.equal(r.rows[1].repair,10);assert.equal(r.rows[0].operating,0);assert.equal(r.rows[2].residual,20);
 const zero=lifeCycleCost(0,0,1,0,0);assert.equal(zero.present_value,0);
 for(const args of [[100,10,0,5,0],[100,-1,2,5,0],[100,10,2,101,0],[100,10,2,5,0,'3;10'],[100,10,2,5,null],[100,10,2,5,0,'1;unknown']])assert.equal(lifeCycleCost(...args),null);
});
test('conditional paths keep their base and target without predicting probability',()=>{
 const linear=buildPlanScenario(28.8,33,2024,2030);assert.equal(linear.rows.length,7);assert.equal(linear.rows[0].value,28.8);assert.equal(linear.rows.at(-1).value,33);close(linear.annualChange,.7);
 const compound=buildPlanScenario(10,40,2025,2027,'compound');close(compound.rows[1].value,20);
 for(const args of [[90,101,2025,2030,'linear','percentage'],[0,5,2025,2030,'compound'],[3,4,2025,2025],[3,4,2025.5,2030],[3,4,2025,2060]])assert.equal(buildPlanScenario(...args),null);
});
test('monthly cumulative series break across years and never bridge an absent month',()=>{
 const rows=[['2025-11-30',2],['2025-12-31',3],['2026-01-31',1],['2026-03-31',2]].map(([date,value])=>({period:date.slice(0,7),period_end:date,frequency:'monthly',value,analytical_value:value}));const groups=seriesGroups({annual_reset:true},rows);assert.equal(groups.length,2);assert.ok(groups[1].points.some(p=>p.y===null));
 for(const group of groups)assert.equal(new Set(group.points.map(p=>new Date(p.x).getUTCFullYear())).size,1);
});
test('methodology break 62872 does not join observations from successive periods',()=>{
 const rows=[{period:'2024',period_end:'2024-12-31',frequency:'annual',value:1},{period:'2025',period_end:'2025-12-31',frequency:'annual',value:2}];const groups=seriesGroups({id:'62872'},rows);assert.equal(groups.length,1);assert.equal(groups[0].points.filter(p=>p.y!==null).length,2);assert.ok(groups[0].points.some(p=>p.y===null));
});
test('same-period changes never mix categories or duplicate source rows',()=>{
 const points=[{period:'2025-06',period_end:'2025-06-30',frequency:'monthly',category:'Всего',value:10},{period:'2026-06',period_end:'2026-06-30',frequency:'monthly',category:'Всего',value:12},{period:'2025-06',period_end:'2025-06-30',frequency:'monthly',category:'Город',value:90}];assert.equal(matchedPeriodChanges(points).length,1);close(matchedPeriodChanges(points)[0].relative_change,20);assert.equal(matchedPeriodChanges([...points,{...points[0]}]).length,0);
});
test('regional ambiguity remains missing and paired slices require equal periods',()=>{
 const point=(id,value,date='2025-12-31',extra={})=>({map_id:id,geo_level:'regional',period:date.slice(0,4),period_end:date,frequency:'annual',value,...extra});
 const rows=[point('29',30,'2025-12-31',{geographic_comparison_eligible:false}),point('29',null,'2025-12-31',{geographic_comparison_eligible:true}),point('77',20)];
 const key=sliceKey(rows[0]),slice=regionalSlice(rows,key,{comparable:true});assert.equal(slice.find(r=>r.map_id==='29').value,null);assert.equal(pairedRegions(rows,[point('77',40,'2024-12-31')],key,sliceKey(point('77',40,'2024-12-31'))).length,0);
});
test('financial aggregation keeps missing cells distinct from explicit zero',()=>{
 assert.deepEqual(financeTotals([{year:2025,value:null},{year:2026,value:0}]),{sum:0,missing:1,count:2});assert.deepEqual(financeTotals([{year:2025,value:null}]),{sum:null,missing:1,count:1});assert.equal(financeTotals([{year:2025,value:5},{year:2026,value:10}],2025).sum,5);
});
test('lazy source loader verifies identity and retries after a failed network response',async()=>{
 let calls=0;const source={id:'infrastructure-test',downloads:{observations:'./data/infrastructure-test.json'}},fetcher=async()=>++calls===1?{ok:false,status:503}:{ok:true,json:async()=>({project_id:'life_infrastructure',source_id:source.id,observations:[{value:0}]})};
 await assert.rejects(loadInfrastructureObservations(source,fetcher),/503/);assert.deepEqual(await loadInfrastructureObservations(source,fetcher),[{value:0}]);assert.equal(calls,2);
 await assert.rejects(loadInfrastructureObservations({id:'foreign',downloads:{observations:'./data/infrastructure-test-foreign.json'}},async()=>({ok:true,json:async()=>({project_id:'family',source_id:'foreign',observations:[]})})),/Неверный проект/);
});


test('construction series keep the changed national geography in separate lines',()=>{
 const rows=[{period:'2022',period_end:'2022-12-31',frequency:'annual',name:'Российская Федерация',value:102.713},{period:'2023',period_end:'2023-12-31',frequency:'annual',name:'Российская Федерация без учета новых субъектов (с 01.01.2023)',national_scope:'rf_without_new_subjects_from_2023',value:110.438}];
 const groups=seriesGroups({id:'59263'},rows);assert.equal(groups.length,2);assert.ok(groups.every(g=>g.points.length===1));assert.equal(matchedPeriodChanges(rows).length,0);
});


test('February comparisons keep the same month across a leap-year boundary',()=>{
 const rows=[{period:'2024-02',period_start:'2024-02-01',period_end:'2024-02-29',frequency:'monthly',value:10},{period:'2025-02',period_start:'2025-02-01',period_end:'2025-02-28',frequency:'monthly',value:11}];const result=matchedPeriodChanges(rows);assert.equal(result.length,1);close(result[0].relative_change,10);
});


test('scenario anchors prefer the explicitly published national scope and reject unresolved conflicts',()=>{
 const old={year:2023,frequency:'annual',period:'2023',name:'Российская Федерация',value:110.438,annual_comparison_eligible:true},scoped={...old,name:'РФ без новых субъектов',national_scope:'rf_without_new_subjects_from_2023'};
 const anchors=annualScenarioAnchors({annual:[old,scoped]});assert.equal(anchors.length,1);assert.equal(anchors[0].national_scope,scoped.national_scope);
 assert.equal(annualScenarioAnchors({annual:[{...old,value:100},{...old,value:101}]}).length,0);
});


test('duplicated 2023 all-Russia publication cannot bridge the scope break',()=>{
 const rows=[{year:2022,period:'2022',period_end:'2022-12-31',frequency:'annual',name:'Российская Федерация',national_scope:'rf_source_definition',value:102.713},{year:2023,period:'2023',period_end:'2023-12-31',frequency:'annual',name:'Российская Федерация',national_scope:'rf_source_definition',value:110.438},{year:2023,period:'2023',period_end:'2023-12-31',frequency:'annual',name:'Российская Федерация без учета новых субъектов',national_scope:'rf_without_new_subjects_from_2023',value:110.438}];
 assert.equal(matchedPeriodChanges(rows).length,0);const groups=seriesGroups({id:'59263'},rows);assert.equal(groups.length,3);assert.ok(groups.every(g=>g.points.length===1));
});
