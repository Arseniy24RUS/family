import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {annualScenarioAnchors,scenarioGoal,wasteBalance,emissionIndex,environmentalExposure,buildPlanScenario,matchedPeriodChanges,seriesGroups,observationSlices,regionalSlice,sliceKey,pairedRegions,regionSummary,financeTotals,loadEnvironmentObservations} from '../src/pages/environment.js';

const close=(a,b,tolerance=1e-9)=>assert.ok(Math.abs(a-b)<tolerance,`${a} ≠ ${b}`);
const stat=JSON.parse(readFileSync(new URL('../public/data/projects/environment/statistics.json',import.meta.url)));
const source=id=>stat.sources.find(s=>String(s.id)===String(id));
const points=id=>JSON.parse(readFileSync(new URL('../public/'+source(id).downloads.observations.replace(/^\.\//,''),import.meta.url))).observations;
const annual=(value,extra={})=>({year:2025,period:'2025',period_end:'2025-12-31',frequency:'annual',geo_level:'national',value,annual_comparison_eligible:true,...extra});

test('waste balance excludes processing as an intermediate stage and preserves both shares',()=>{
 const input={received:100,treated:80,secondary_used:25,landfilled:65,other_output:5,stock_start:0,stock_end:5},r=wasteBalance(input);
 assert.equal(r.residual,0);assert.equal(r.balanced,true);assert.equal(r.outgoing,100);assert.equal(r.stock_change,5);assert.equal(r.treatment_share+r.landfill_share,145);assert.equal(r.utilization_share,25);
 assert.equal(wasteBalance({...input,treated:20}).residual,0);
});
test('waste balance includes stock release and never clamps repeated processing',()=>{
 const r=wasteBalance({received:100,treated:120,secondary_used:40,landfilled:70,other_output:0,stock_start:20,stock_end:10});
 assert.equal(r.residual,0);assert.equal(r.stock_change,-10);assert.equal(r.treatment_share,120);assert.deepEqual(r.stages_exceed_input,['treated']);
});
test('waste balance reports inconsistency and rejects missing or negative input',()=>{
 const good={received:100,treated:80,secondary_used:30,landfilled:60,other_output:0,stock_start:0,stock_end:0};
 assert.equal(wasteBalance(good).residual,10);assert.equal(wasteBalance(good).balanced,false);
 for(const patch of [{received:0},{received:null},{stock_start:''},{landfilled:-1},{treated:Infinity},{other_output:'unknown'}])assert.equal(wasteBalance({...good,...patch}),null);
});
test('residual emission index and reduction have opposite readings and are not bounded shares',()=>{
 assert.deepEqual(emissionIndex(100,80),{baseline:100,current:80,residual_index:80,reduction_percent:20,absolute_change:-20});
 const growing=emissionIndex(50,60);assert.equal(growing.residual_index,120);assert.equal(growing.reduction_percent,-20);assert.equal(emissionIndex(100,0).reduction_percent,100);
 close(emissionIndex(5000,4000).residual_index,emissionIndex(5,4).residual_index);
 for(const args of [[0,10],[null,10],[100,-1],[100,''],[-1,10],[100,Infinity]])assert.equal(emissionIndex(...args),null);
});
test('population-weighted exposure differs from equal-cell and area averages',()=>{
 const r=environmentalExposure('Ячейка; население; концентрация; площадь\nА;1000;5;9\nБ;3000;15;1');
 close(r.weighted_mean,12.5);close(r.unweighted_mean,10);close(r.area_weighted_mean,6);assert.equal(r.population_coverage,100);assert.equal(r.area_coverage,100);assert.equal(r.population_complete,true);
});
test('missing concentration is retained and reduces population coverage without zero imputation',()=>{
 const r=environmentalExposure('А;1000;5;9\nБ;3000;;1');
 assert.equal(r.rows[1].concentration,null);assert.equal(r.rows[1].population_included,false);assert.equal(r.weighted_mean,5);assert.equal(r.population_coverage,25);assert.equal(r.area_coverage,90);assert.equal(r.concentration_complete,false);
});
test('unknown population remains an explicit limitation and zero weights do not invent a mean',()=>{
 const partial=environmentalExposure('А;1000;5\nБ;;15');assert.equal(partial.population_complete,false);assert.equal(partial.weighted_mean,5);assert.equal(partial.unweighted_mean,10);
 const zero=environmentalExposure('А;0;5\nБ;0;15');assert.equal(zero.weighted_mean,null);assert.equal(zero.population_coverage,null);assert.equal(zero.unweighted_mean,10);
 const missing=environmentalExposure('А;1000;');assert.equal(missing.weighted_mean,null);assert.equal(missing.observed_cells,0);assert.equal(missing.population_coverage,0);
});
test('exposure parsing supports Russian decimals and rejects invalid boundaries',()=>{
 close(environmentalExposure('А\t100\t2,5\nБ\t100\t3,5').weighted_mean,3);
 for(const input of ['', 'А;100;-1','А;-100;1','А;100;1;-4','А;100;2\nА;200;4','А;100;unknown','А;100','А;100;2;4;5'])assert.equal(environmentalExposure(input),null);
});
test('conditional paths preserve their endpoints without a probability forecast',()=>{
 const linear=buildPlanScenario(56.6,100,2025,2030,'linear','percentage');assert.equal(linear.rows.length,6);assert.equal(linear.rows[0].value,56.6);assert.equal(linear.rows.at(-1).value,100);close(linear.annualChange,8.68);
 const compound=buildPlanScenario(100,25,2025,2027,'compound');close(compound.rows[1].value,50);
 assert.equal(buildPlanScenario(149.64,200,2025,2030,'linear').rows.at(-1).value,200);
 for(const args of [[90,101,2025,2030,'linear','percentage'],[0,5,2025,2030,'compound'],[3,4,2025,2025],[3,4,2025.5,2030],[3,4,2025,2060]])assert.equal(buildPlanScenario(...args),null);
});
test('annual anchors reject stopped indicators, unresolved methodologies and monthly substitutions',()=>{
 for(const id of ['62779','62787','62804','62871'])assert.equal(annualScenarioAnchors(source(id)).length,0,id);
 assert.equal(annualScenarioAnchors(source('62781')).length,1);close(annualScenarioAnchors(source('62781'))[0].value,149.64);
 assert.equal(annualScenarioAnchors({annual:[{...annual(10),frequency:'cumulative_ytd'}]}).length,0);
 assert.equal(annualScenarioAnchors({annual:[annual(10),annual(11)]}).length,0);
 assert.equal(annualScenarioAnchors({annual:[annual(10),annual(10)]}).length,1);
});
test('YTD sources split calendar cycles and do not bridge missing months',()=>{
 const rows=[['2025-11-30',2],['2025-12-31',3],['2026-01-31',1],['2026-03-31',2]].map(([date,value])=>({period:date.slice(0,7),period_end:date,frequency:'cumulative_ytd',value}));
 const groups=seriesGroups({annual_reset:true,period_semantics:'cumulative_ytd'},rows);assert.equal(groups.length,2);assert.ok(groups[1].points.some(p=>p.y===null));
 for(const g of groups)assert.equal(new Set(g.points.map(p=>new Date(p.x).getUTCFullYear())).size,1);
});
test('program accumulation crosses January without an invented annual reset',()=>{
 const rows=[{period:'2025-12',period_end:'2025-12-31',frequency:'cumulative_ytd',period_semantics:'cumulative_since_2025',value:100},{period:'2026-01',period_end:'2026-01-31',frequency:'cumulative_ytd',period_semantics:'cumulative_since_2025',value:101}];
 const groups=seriesGroups({annual_reset:false,cumulative_since:2025,period_semantics:'cumulative_since_2025'},rows);assert.equal(groups.length,1);assert.equal(groups[0].points.length,2);assert.match(groups[0].name,/с 2025 года/);
});
test('methodological breaks and discontinued series never join observations',()=>{
 for(const id of ['62787','62804','62779']){
  const groups=seriesGroups(source(id),source(id).national);assert.ok(groups.length);for(const g of groups)for(let i=1;i<g.points.length;i++)assert.ok(g.points[i-1].y===null||g.points[i].y===null,id);
 }
});
test('same-window changes separate categories, reject duplicates and avoid zero denominators',()=>{
 const points=[{name:'РФ',period:'2025-08',period_end:'2025-08-31',period_start:'2025-01-01',frequency:'cumulative_ytd',category:'Все',value:16.2},{name:'РФ',period:'2026-08',period_end:'2026-08-31',period_start:'2026-01-01',frequency:'cumulative_ytd',category:'Все',value:14.7296},{name:'РФ',period:'2025-08',period_end:'2025-08-31',frequency:'monthly',category:'Все',value:1}];
 const r=matchedPeriodChanges(points);assert.equal(r.length,1);close(r[0].relative_change,(14.7296/16.2-1)*100);
 assert.equal(matchedPeriodChanges([...points,{...points[0]}]).length,0);
 assert.equal(matchedPeriodChanges([{...points[0],value:0},points[1]])[0].relative_change,null);
});
test('real protected-area visits compare January–August to January–August, not a full year',()=>{
 const r=matchedPeriodChanges(source('62777').national).find(r=>r.period==='2026-08');assert.ok(r);close(r.previous,16.2);close(r.current,14.7296);close(r.relative_change,-9.07654320987654);
});
test('row-level methodological and lifecycle restrictions block derived changes',()=>{
 for(const extra of [{temporal_comparison_eligible:false},{source_status:'discontinued'}])assert.equal(matchedPeriodChanges([annual(10,{year:2024,period:'2024',period_end:'2024-12-31',...extra}),annual(11,{...extra})]).length,0);
});
test('February comparisons align month and temporal window across leap years',()=>{
 const r=matchedPeriodChanges([{period:'2024-02',period_start:'2024-02-01',period_end:'2024-02-29',frequency:'monthly',value:10},{period:'2025-02',period_start:'2025-02-01',period_end:'2025-02-28',frequency:'monthly',value:11}]);assert.equal(r.length,1);close(r[0].relative_change,10);
});
test('territorial slices do not turn project participants into regional observations',()=>{
 const city={map_id:null,code:null,name:'Братск',geo_level:'project_territory',period:'2025',period_end:'2025-12-31',frequency:'annual',value:80},region={...city,map_id:'38',name:'Иркутская область',geo_level:'regional',value:81};
 assert.equal(observationSlices([city,region])[0].numeric_count,1);assert.equal(regionalSlice([city,region],sliceKey(city)).length,1);
});
test('regional ambiguity remains missing and paired data require identical frequency and date',()=>{
 const point=(id,value,date='2025-12-31',extra={})=>({map_id:id,geo_level:'regional',period:date.slice(0,4),period_end:date,frequency:'annual',value,...extra});
 const rows=[point('29',30,'2025-12-31',{geographic_comparison_eligible:false}),point('29',null,'2025-12-31',{geographic_comparison_eligible:true}),point('77',20)];
 const key=sliceKey(rows[0]);assert.equal(regionalSlice(rows,key,{comparable:true}).find(r=>r.map_id==='29').value,null);
 for(const extra of [{period_end:'2024-12-31'},{frequency:'cumulative_ytd'}]){const b=point('77',40,'2025-12-31',extra);assert.equal(pairedRegions(rows,[b],key,sliceKey(b)).length,0);}
});
test('real annual TKO joins have 85 pairs and preserve the EAO zero pair',()=>{
 const a=points('62792'),b=points('62793'),key=sliceKey(a.find(r=>r.geo_level==='regional'&&r.frequency==='annual'));
 const r=pairedRegions(a,b,key,key);assert.equal(r.length,85);assert.deepEqual(r.filter(r=>r.id==='79').map(r=>[r.x,r.y]),[[0,0]]);
});
test('regional quantiles keep zeros and forest values above 100',()=>{
 const s=regionSummary([0,100,150,4000,null].map(value=>({value})));assert.equal(s.n,4);close(s.q1,75);close(s.median,125);close(s.q3,1112.5);assert.equal(s.maximum,4000);
});
test('financial aggregation retains missing cells distinctly from an observed zero',()=>{
 assert.deepEqual(financeTotals([{year:2025,value:null},{year:2026,value:0}]),{sum:0,missing:1,count:2});assert.deepEqual(financeTotals([{year:2025,value:null}]),{sum:null,missing:1,count:1});assert.equal(financeTotals([{year:2025,value:5},{year:2026,value:10}],2025).sum,5);
});
test('lazy loader verifies project/source identity and retries only after a failed request',async()=>{
 let calls=0;const source={id:'environment-test',downloads:{observations:'./data/environment-test.json'}},fetcher=async()=>++calls===1?{ok:false,status:503}:{ok:true,json:async()=>({project_id:'environment',source_id:source.id,observations:[{value:0}]})};
 await assert.rejects(loadEnvironmentObservations(source,fetcher),/503/);assert.deepEqual(await loadEnvironmentObservations(source,fetcher),[{value:0}]);await loadEnvironmentObservations(source,fetcher);assert.equal(calls,2);
 await assert.rejects(loadEnvironmentObservations({id:'foreign',downloads:{observations:'./data/environment-foreign.json'}},async()=>({ok:true,json:async()=>({project_id:'family',source_id:'foreign',observations:[]})})),/Неверный проект/);
 await assert.rejects(loadEnvironmentObservations({id:'wrong',downloads:{observations:'./data/environment-wrong.json'}},async()=>({ok:true,json:async()=>({project_id:'environment',source_id:'other',observations:[]})})),/Неверный источник/);
});


test('published zero targets remain visible without automatically becoming a desired decline',()=>{
 const documentary=JSON.parse(readFileSync(new URL('../public/data/projects/environment/documentary.json',import.meta.url))),t=documentary.targets.items.find(t=>String(t.source_id)==='62861'),s=source('62861'),fact=annualScenarioAnchors(s)[0].value;
 assert.equal(s.source_status,'active');assert.equal(t.years['2030'],0);
 const choice=scenarioGoal(s,fact,t.years['2030']);assert.equal(choice.rawTarget,0);assert.equal(choice.requiresInterpretation,true);assert.equal(choice.defaultGoal,null);assert.equal(choice.goal,null);
 assert.equal(scenarioGoal(s,fact,t.years['2027']).goal,100);assert.equal(scenarioGoal(s,fact,t.years['2030'],'90').goal,90);
 assert.equal(t.years['2030'],0);assert.equal(buildPlanScenario(fact,choice.goal,2025,2030),null);
});
