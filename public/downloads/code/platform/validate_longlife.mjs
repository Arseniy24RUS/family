/** Independent consistency checks for published Longlife data and research pages. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {longlifePages} from '../src/platform/projects.js';
import {validateLonglifeContent} from './build_longlife.mjs';

const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const close=(actual,expected,label)=>assert.ok(Math.abs(actual-expected)<=1e-8*Math.max(1,Math.abs(expected)),label||`${actual} != ${expected}`);
const amount=value=>{
  assert.match(String(value),/^-?\d+(\.\d{1,2})?$/,'Financial source amounts retain exact hundredths of thousand rubles.');
  const [integer,fraction='']=String(value).split('.');
  return BigInt(integer)*100n+BigInt(fraction.padEnd(2,'0'))*(integer.startsWith('-')?-1n:1n);
};
const quantile=(values,p)=>{
  const x=[...values].sort((a,b)=>a-b),position=(x.length-1)*p,lower=Math.floor(position);
  return x[lower]+(x[Math.min(lower+1,x.length-1)]-x[lower])*(position-lower);
};

export async function validateLonglife(root=path.resolve(import.meta.dirname,'..')){
  const docs=path.join(root,'docs'),prefix='data/projects/long_active_life/';
  const bytes=async relative=>{
    assert.ok(!path.isAbsolute(relative)&&!relative.split('/').includes('..'),'Safe published path: '+relative);
    return fs.readFile(path.join(docs,relative.replace(/^\.\//,'')));
  };
  const read=async relative=>JSON.parse(await bytes(relative));
  const [statistics,analytics,report,documentary,geometry]=await Promise.all([
    ...['statistics','analytics','expertise','documentary'].map(name=>read(prefix+name+'.json')),read('data/map.json')
  ]);
  const config=JSON.parse(await fs.readFile(path.join(root,'scripts/longlife_emiss_sources.json'),'utf8'));
  const checked=validateLonglifeContent(report),mapIds=new Set(geometry.features.map(feature=>feature.id));
  assert.equal(statistics.project_id,'long_active_life');assert.equal(analytics.project_id,'long_active_life');
  assert.deepEqual(new Set(statistics.sources.map(source=>source.id)),new Set(config.sources.map(source=>source.indicator_id)));
  const allRows=new Map(),packets=new Map();
  let cells=0,numeric=0,excluded=0,nationalAnnual=0,regionalSources=0;
  for(const source of statistics.sources){
    const packetBytes=await bytes(prefix+'series/'+source.id+'.json');
    const packet=JSON.parse(packetBytes),provenance=await read(prefix+'provenance/'+source.id+'.json');
    packets.set(source.id,packet);
    assert.equal(packet.project_id,'long_active_life');assert.equal(packet.source_id,source.id);assert.equal(packet.unit,source.unit);
    assert.equal(provenance.published_sha256,hash(packetBytes));
    assert.equal(provenance.input_sha256,hash(await bytes(provenance.input_bundle)));
    assert.equal(packet.observations.length,source.observation_count);
    const ids=new Set();let sourceNumeric=0,sourceExcluded=0;
    for(const row of packet.observations){
      assert.equal(row.source_id,source.id);assert.ok(!ids.has(row.id),'Unique Longlife cell: '+row.id);ids.add(row.id);
      assert.ok(row.value===null||Number.isFinite(row.value));
      assert.equal(row.analytical_value,row.excluded?null:row.value);
      assert.match(row.period_end,/^\d{4}-\d{2}-\d{2}$/);assert.ok(row.source_observation_key);
      assert.notEqual(row.frequency,'annual_equivalent','A source record is not an inferred annual equivalent.');
      assert.ok(!Object.keys(row.category||{}).some(key=>/ОКАТО/i.test(key)),'Geography is not an analytical category.');
      if(row.geo_level==='regional'&&row.geographic_comparison_eligible)assert.ok(mapIds.has(row.map_id),'Regional join: '+row.map_id);
      allRows.set(source.id+':'+row.id,row);cells++;
      if(row.value!==null){numeric++;sourceNumeric++;if(row.excluded){excluded++;sourceExcluded++;}}
      if(row.geo_level==='national'&&row.frequency==='annual'&&row.analytical_value!==null)nationalAnnual++;
    }
    assert.equal(sourceNumeric,source.numeric_count);assert.equal(sourceExcluded,source.excluded_numeric_count);
    assert.equal(source.observation_count-sourceNumeric,source.missing_count);
    for(const summary of [...(source.national||[]),...(source.annual||[]),...(source.regional_latest||[]),...(source.latest_national?[source.latest_national]:[])]){
      const original=allRows.get(source.id+':'+summary.id);
      assert.ok(original,'Summary points to a source cell.');assert.equal(summary.value,original.value);
      assert.equal(summary.period_end,original.period_end);assert.equal(summary.frequency,original.frequency);
    }
    assert.deepEqual(source.regional_history,[],'Detailed histories load by source.');
    assert.equal(source.regional_history_deferred,true);
    if(source.regional_latest?.length)regionalSources++;
    if(source.downloads.current_raw){
      assert.equal(source.downloads.current_raw,provenance.current_raw);
      assert.equal(hash(await bytes(provenance.current_raw)),provenance.current_raw_sha256);
    }
  }
  const coverage=analytics.coverage;
  assert.equal(cells,coverage.observations);assert.equal(numeric,coverage.numeric_observations);
  assert.equal(cells-numeric,coverage.missing_observations);assert.equal(excluded,coverage.excluded_numeric_observations);
  assert.equal(numeric-excluded,coverage.usable_observations);assert.equal(nationalAnnual,coverage.independent_annual_national_facts);
  assert.equal(regionalSources,coverage.regional_sources);
  assert.equal(coverage.known_sources,statistics.sources.length);
  assert.equal(coverage.indicators_total,coverage.indicators_with_numeric+coverage.unmapped_indicators);
  for(const comparison of analytics.target_comparisons){
    const row=allRows.get(comparison.source_id+':'+comparison.reference_observation_id);
    assert.ok(row,'Target comparison refers to an original observation.');
    assert.equal(row.geo_level,'national');assert.equal(row.value,comparison.fact_value);assert.equal(row.frequency,comparison.fact_frequency);
    close(comparison.difference,comparison.fact_value-comparison.target_value,'Target difference arithmetic.');
    assert.equal(comparison.annual_comparison_eligible,row.frequency==='annual');
    assert.equal(comparison.formal_attainment_eligible,false);
    assert.ok(comparison.difference_unit);assert.ok(comparison.target_source.source_file);
    await bytes(comparison.target_source.source_file);
  }
  for(const comparison of analytics.annual_december_comparisons){
    const annual=allRows.get(comparison.source_id+':'+comparison.annual_observation_id);
    const december=allRows.get(comparison.source_id+':'+comparison.december_observation_id);
    assert.ok(annual&&december);assert.equal(annual.frequency,'annual');assert.equal(december.frequency,'monthly');
    assert.equal(annual.value,comparison.annual_value);assert.equal(december.value,comparison.december_value);
    close(comparison.difference,annual.value-december.value);
  }
  const staffing=analytics.author_staffing;
  if(staffing.computed){
    assert.equal(staffing.regions.length,staffing.n);assert.equal(new Set(staffing.regions.map(row=>row.code)).size,staffing.n);
    const counts={both_below:0,doctors_below_only:0,nurses_below_only:0,both_at_or_above:0};
    for(const row of staffing.regions){
      const doctor=allRows.get('62971:'+row.doctor_observation_id),nurse=allRows.get('62970:'+row.nurse_observation_id);
      assert.ok(doctor&&nurse);assert.equal(doctor.value,row.doctors);assert.equal(nurse.value,row.nurses);
      assert.equal(doctor.period,row.period);assert.equal(nurse.period,row.period);assert.ok(mapIds.has(row.map_id));
      const belowDoctor=row.doctors<staffing.national.doctors,belowNurse=row.nurses<staffing.national.nurses;
      const group=belowDoctor?(belowNurse?'both_below':'doctors_below_only'):(belowNurse?'nurses_below_only':'both_at_or_above');
      assert.equal(row.group,group);counts[group]++;
    }
    assert.deepEqual(counts,staffing.group_counts);
    for(const kind of ['doctors','nurses']){
      const values=staffing.regions.map(row=>row[kind]),summary=staffing.summary[kind];
      for(const [key,p] of [['q1',.25],['median',.5],['q3',.75]])close(summary[key],quantile(values,p));
    }
  }
  const diagnostic=analytics.multivariate;
  if(diagnostic.computed){
    assert.equal(diagnostic.scores.length,diagnostic.n_regions);assert.equal(diagnostic.features.length,diagnostic.n_features);
    assert.equal(diagnostic.imputed_count,diagnostic.missing_cells.length);
    assert.equal(diagnostic.imputation_policy,'feature_median_diagnostic_copy_only');
    close(diagnostic.explained_variance_ratio.reduce((a,b)=>a+b,0),1);
    for(const [id,snapshot] of Object.entries(diagnostic.source_snapshots))assert.equal(snapshot,packets.get(id).snapshot_id);
    const observed=statistics.downloads.find(file=>file.path.includes('multivariate_observed_'));
    const imputed=statistics.downloads.find(file=>file.path.includes('multivariate_diagnostic_imputed_'));
    assert.equal(hash(await bytes(observed.path)),diagnostic.observed_matrix_sha256);
    assert.equal(hash(await bytes(imputed.path)),diagnostic.diagnostic_matrix_sha256);
    assert.equal(diagnostic.kmeans.cluster_sizes.reduce((a,b)=>a+b,0),diagnostic.n_regions);
    if(diagnostic.seed_stability_provenance){
      assert.equal(diagnostic.seed_stability_provenance.author_seed_list_available,false);
      assert.deepEqual(diagnostic.seed_stability_provenance.seeds,diagnostic.kmeans.seed_stability.map(row=>row.seed));
      assert.ok(report.meta.source_clarifications?.some(item=>item.route==='methods'));
    }
  }
  const finance=documentary.finance,total=finance.projects.reduce((sum,project)=>sum+amount(project.totalThousandRub),0n);
  assert.equal(total,amount(finance.totalThousandRub));
  assert.equal(total-amount(finance.nationalThousandRub),amount(finance.differenceThousandRub));
  assert.equal(amount(finance.nationalThousandRub)-total,amount(finance.nationalMinusFederalThousandRub));
  for(const project of finance.projects){
    assert.equal(project.years.reduce((sum,year)=>sum+amount(year.amountThousandRub),0n),amount(project.totalThousandRub));
    assert.equal(project.fullYears.reduce((sum,year)=>sum+amount(year.amountThousandRub),0n),amount(project.fullHorizonThousandRub));
  }
  let targetCells=0,targetNumbers=0;
  for(const target of documentary.targets.items)for(const value of Object.values(target.years)){
    targetCells++;assert.ok(value===null||Number.isFinite(value));if(value!==null)targetNumbers++;
  }
  assert.equal(targetCells,documentary.targets.target_cells);assert.equal(targetNumbers,documentary.targets.numeric_targets);
  assert.equal(targetCells-targetNumbers,documentary.targets.missing_targets);
  for(const source of documentary.sources)assert.equal(hash(await bytes(source.download_path)),source.sha256);
  const direct=documentary.network.directReviewed,nodeIds=new Set(direct.nodes.map(node=>node.id)),weightSums=new Map();
  assert.equal(direct.edges.length,direct.edgeCount);assert.equal(direct.causal_effect,false);
  for(const edge of direct.edges){
    assert.ok(nodeIds.has(edge.source_node_id)&&nodeIds.has(edge.target_node_id));assert.equal(edge.causal_effect,false);
    assert.ok(Number.isFinite(edge.documentary_weight_percent)&&edge.documentary_weight_percent>=0);
    weightSums.set(edge.target_node_id,(weightSums.get(edge.target_node_id)||0)+edge.documentary_weight_percent);
  }
  for(const sum of weightSums.values())close(sum,100,'Each passport indicator has a complete documented weight distribution.');
  const demographic=documentary.demographicContext;
  assert.equal(demographic.role,'pre_project_context');assert.equal(demographic.year,2023);
  for(const row of demographic.ageSex)close(row.female-row.male,row.gap);
  assert.equal(demographic.downloaded_original_pdf,false);
  for(const file of Object.values(demographic.downloads))await bytes(file);
  assert.equal(hash(await bytes(report.meta.report_url)),report.meta.source_docx_sha256);
  const reportCoverage=await read('downloads/projects/long_active_life/report/coverage_manifest.json');
  assert.equal(reportCoverage.summary.assigned_blocks,reportCoverage.summary.substantive_blocks);
  assert.deepEqual(reportCoverage.summary.unmapped_substantive_blocks,[]);assert.deepEqual(reportCoverage.summary.duplicate_assignments,[]);
  assert.ok((await bytes(prefix+'statistics.json')).length<3*1024*1024,'Overview does not preload complete regional histories.');
  assert.deepEqual(documentary.text.units,[]);assert.deepEqual(documentary.text.kwic,[]);
  for(const item of documentary.text.documentFiles)await bytes(item.path);
  for(const page of longlifePages){
    const html=String(await bytes('research/projects/long_active_life/'+(page.id==='overview'?'index.html':page.id+'.html')));
    assert.ok(html.includes('--brand:#D9124A'));
    if(page.id==='methods'&&report.meta.source_clarifications?.length)assert.ok(html.includes('source-clarification'));
  }
  console.log(`Validated Longlife: ${statistics.sources.length} sources, ${cells} original cells, ${numeric} numeric values, ${regionalSources} regional sources, ${checked.routes} report pages.`);
  return {sources:statistics.sources.length,cells,numeric,excluded,nationalAnnual,regionalSources,routes:checked.routes};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await validateLonglife();
