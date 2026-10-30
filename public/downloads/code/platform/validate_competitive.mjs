/** Validate the published Competitive study and its source-linked arithmetic. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {competitivePages,getProject} from '../src/platform/projects.js';
import {median,quantile} from '../src/core/stats.js';
import {validateCompetitiveContent} from './build_competitive.mjs';

const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const close=(actual,expected,label)=>assert.ok(Number.isFinite(actual)&&Number.isFinite(expected)&&Math.abs(actual-expected)<=1e-8*Math.max(1,Math.abs(expected)),label);
const cents=value=>{
  assert.match(value,/^-?\d+(?:\.\d{1,2})?$/,'Financial source amounts retain exact hundredths.');
  const negative=value.startsWith('-'),[integer,fraction='']=value.replace('-','').split('.');
  return (BigInt(integer)*100n+BigInt(fraction.padEnd(2,'0')))*(negative?-1n:1n);
};

export async function validateCompetitive(root){
  const docs=path.join(root,'docs'),prefix='data/projects/competitive_economy/';
  const bytes=relative=>fs.readFile(path.join(docs,relative.replace(/^\.\//,'')));
  const read=async relative=>JSON.parse(await bytes(relative));
  const [statistics,analytics,report,runtime,status,methods]=await Promise.all(
    ['statistics','analytics','expertise','documentary','refresh-status','methods'].map(name=>read(prefix+name+'.json')));
  const documentary=await read(runtime.downloads.full_documentary);
  const config=JSON.parse(await fs.readFile(path.join(root,'scripts/competitive_emiss_sources.json'),'utf8'));
  for(const packet of [statistics,analytics,status,methods])assert.equal(packet.project_id,'competitive_economy');
  for(const packet of [runtime,documentary])assert.equal(packet.meta.project_id,'competitive_economy');
  assert.equal(getProject('competitive_economy').color,'#D86464');
  assert.equal(getProject('competitive_economy').hasAuthors,false);
  assert.equal(methods.items.length,39);
  for(const method of methods.items){
    assert.ok(method.current_status&&method.current_status_label&&method.current_limitations,
      'Every inherited method has an explicit current evidence status: '+method.method_id);
  }

  const reportCheck=validateCompetitiveContent(report);
  assert.equal(sha(await bytes(report.meta.report_url)),report.meta.source_docx_sha256,'Original report bytes.');
  const coverage=await read(report.meta.coverage_url);
  assert.equal(coverage.summary.substantive_blocks,coverage.summary.assigned_blocks);
  assert.deepEqual(coverage.summary.unmapped_substantive_blocks,[]);
  assert.deepEqual(coverage.summary.duplicate_assignments,[]);
  assert.equal(coverage.summary.tables,report.tables.length);
  assert.equal(coverage.summary.figures,report.figures.length);
  const sourceIds=new Set(report.sources.map(source=>source.id));
  for(const source of report.sources.filter(source=>source.kind==='source_note')){
    assert.ok(source.source_blocks?.length,'Every footnote retains its original body/table reference: '+source.id);
    assert.ok(Object.values(report.pages).some(page=>page.blocks.some(block=>(block.sourceIds||[]).includes(source.id))),source.id);
  }
  for(const table of report.tables)for(const id of [...(table.headerSourceIds||[]).flat(),...(table.cellSourceIds||[]).flat(2)]){
    assert.ok(sourceIds.has(id)&&table.sourceIds.includes(id),'Cell citation belongs to its original table.');
  }
  for(const figure of report.figures)await bytes(figure.url);
  for(const page of competitivePages){
    const html=(await bytes('research/projects/competitive_economy/'+(page.id==='overview'?'index':page.id)+'.html')).toString();
    assert.ok(html.includes('--brand:#D86464;'));
    assert.ok(html.includes('#/projects/competitive_economy/'+page.id));
  }

  assert.deepEqual(new Set(statistics.sources.map(source=>source.id)),new Set(config.sources.map(source=>String(source.indicator_id))));
  assert.deepEqual(statistics.coverage,analytics.coverage);
  assert.equal(statistics.registry.length,statistics.coverage.registry_indicators);
  const observations=new Map(),sourceMap=new Map(statistics.sources.map(source=>[source.id,source]));
  let cells=0,numeric=0,usable=0,excluded=0,annual=0;
  for(const source of statistics.sources){
    const raw=await bytes(prefix+'series/'+source.id+'.json'),packet=JSON.parse(raw);
    const provenance=await read(prefix+'provenance/'+source.id+'.json');
    assert.equal(packet.project_id,'competitive_economy');
    assert.equal(packet.source_id,source.id);assert.equal(packet.unit,source.unit);
    assert.equal(sha(raw),provenance.published_sha256,'Published source SHA: '+source.id);
    assert.equal(sha(await bytes(provenance.input_bundle)),provenance.input_sha256,'Included source bundle: '+source.id);
    assert.equal(packet.observations.length,source.observation_count);
    let sourceNumeric=0,sourceUsable=0,sourceExcluded=0;
    for(const row of packet.observations){
      assert.equal(row.source_id,source.id);
      assert.ok(!observations.has(row.id),'Unique source observation: '+row.id);
      assert.ok(row.source_observation_key&&typeof row.raw_value==='string');
      assert.match(row.period_start,/^\d{4}-\d{2}-\d{2}$/);
      assert.match(row.period_end,/^\d{4}-\d{2}-\d{2}$/);
      assert.ok(row.value===null||Number.isFinite(row.value));
      assert.equal(row.analytical_value,row.excluded?null:row.value);
      assert.ok(Array.isArray(row.quality_flags));
      if(row.value!==null){numeric++;sourceNumeric++;}
      if(row.analytical_value!==null){usable++;sourceUsable++;}
      if(row.value!==null&&row.excluded){excluded++;sourceExcluded++;}
      if(row.geo_level==='national'&&row.frequency==='annual'&&row.analytical_value!==null)annual++;
      if(row.geo_level==='regional')assert.match(row.map_id||row.code,/^\d{2}$/);
      if(row.annual_comparison_eligible)assert.equal(row.frequency,'annual');
      // Keep only fields required by cross-file checks; raw dimensions remain in each source file.
      const {id,source_id,geo_level,map_id,code,period,period_end,frequency,year,category,value,analytical_value,geographic_comparison_eligible}=row;
      observations.set(id,{id,source_id,geo_level,map_id,code,period,period_end,frequency,year,category,value,analytical_value,geographic_comparison_eligible});
    }
    cells+=packet.observations.length;
    assert.equal(sourceNumeric,source.numeric_count);assert.equal(sourceUsable,source.usable_count);
    assert.equal(sourceExcluded,source.excluded_numeric_count);
    assert.equal(packet.observations.length-sourceNumeric,source.missing_count);
    for(const row of [...source.national,...source.regional_latest]){
      const original=observations.get(row.id);assert.ok(original);
      assert.equal(row.value,original.value);assert.equal(row.analytical_value,original.analytical_value);
      assert.equal(row.period,original.period);assert.equal(row.frequency,original.frequency);
    }
    if(provenance.current_raw)assert.equal(sha(await bytes(provenance.current_raw)),provenance.current_raw_sha256);
  }
  for(const [key,count] of Object.entries({observations:cells,numeric_observations:numeric,missing_observations:cells-numeric,
    usable_observations:usable,excluded_numeric_observations:excluded,independent_annual_national_facts:annual}))assert.equal(statistics.coverage[key],count,key);
  for(const comparison of analytics.target_comparisons){
    const row=observations.get(comparison.reference_observation_id);assert.ok(row);
    const ids=comparison.reference_observation_ids||[comparison.reference_observation_id];
    assert.equal(new Set(ids).size,ids.length);
    assert.ok(ids.includes(comparison.reference_observation_id));
    const references=ids.map(id=>observations.get(id));
    for(const reference of references){
      assert.ok(reference);
      assert.equal(reference.geo_level,'national');assert.equal(reference.source_id,row.source_id);
      assert.equal(reference.period,row.period);assert.equal(reference.frequency,row.frequency);
      assert.ok(Number.isFinite(reference.analytical_value));
    }
    close(references.reduce((sum,reference)=>sum+reference.analytical_value,0),comparison.fact_value,
      'A comparison preserves every explicitly referenced observation, without changing its period or denominator.');
    assert.equal(row.period,comparison.fact_period);assert.equal(row.frequency,comparison.fact_frequency);
    assert.ok(sourceMap.get(row.source_id).target_comparison_allowed);
    close(comparison.difference,comparison.fact_value-comparison.target_value,'Target difference.');
    if(comparison.target_value)close(comparison.ratio_percent,100*comparison.fact_value/comparison.target_value,'Target ratio.');
    assert.equal(comparison.formal_attainment_eligible,false,'Late published plan comparison is not certification of original plan attainment.');
  }
  assert.equal(analytics.correlations.computed,false,'Separate economic distributions do not constitute a joint correlation model.');
  assert.equal(analytics.economics.composite_ranking_computed,false);
  assert.equal(analytics.economics.imputed_cells,0);
  for(const profile of analytics.economics.regional_profiles){
    assert.equal(profile.rows.length,profile.n);
    assert.equal(new Set(profile.rows.map(row=>row.map_id||row.code)).size,profile.n);
    const values=[];
    for(const row of profile.rows){
      const original=observations.get(row.id);assert.ok(original);
      assert.equal(original.source_id,profile.source_id);
      assert.equal(original.geo_level,'regional');
      assert.equal(original.period,profile.period);assert.equal(original.frequency,profile.frequency);
      assert.equal(original.analytical_value,row.analytical_value);
      assert.ok(Number.isFinite(row.analytical_value));values.push(row.analytical_value);
    }
    if(values.length){
      close(profile.median,median(values),'Independent median: '+profile.id);
      close(profile.q1,quantile(values,.25),'Independent first quartile: '+profile.id);
      close(profile.q3,quantile(values,.75),'Independent third quartile: '+profile.id);
      close(profile.mean,values.reduce((sum,value)=>sum+value,0)/values.length,'Independent unweighted mean: '+profile.id);
    }
  }
  for(const source of statistics.sources){
    if(source.proxy_only)assert.ok(!analytics.target_comparisons.some(row=>row.source_id===source.id),
      'A tax proxy must not be substituted for enterprise income.');
    if(source.scenario_allowed===false){
      assert.ok(source.period_note||source.note,'A disabled scenario retains its source-specific reason.');
    }
  }

  const foundation=await read(prefix+'foundation.json');
  assert.ok(foundation.legacy_release_metadata?.original,'Earlier metadata is preserved explicitly.');
  assert.equal(foundation.author_expertise_status,'published');
  assert.equal(foundation.registry.n_unique_cells,cells);
  assert.equal(foundation.registry.n_domain_violations,statistics.coverage.domain_violations);
  assert.equal(foundation.registry.n_review_exclusions,statistics.coverage.review_exclusions);
  assert.equal(foundation.panel.clustering_performed,false);
  assert.equal(foundation.panel.pca_performed,false);
  assert.equal(foundation.results.n_projected_series,0);
  assert.equal(foundation.results.forecast_status,'model_not_validated');

  const finance=documentary.finance;
  assert.equal(finance.unit,'тыс. руб.');
  let national=0n,federal=0n;
  for(const year of finance.yearTotals){
    const fp=finance.fpYears.filter(row=>row.year===year.year&&row.amount_decimal!==null);
    const np=finance.nationalSourceYears.filter(row=>row.year===year.year&&row.amount_decimal!==null);
    const f=fp.reduce((sum,row)=>sum+cents(row.amount_decimal),0n),n=np.reduce((sum,row)=>sum+cents(row.amount_decimal),0n);
    assert.equal(f,cents(year.federal_decimal));assert.equal(n,cents(year.national_decimal));
    assert.equal(f-n,cents(year.difference_decimal),'FP minus NP, one year and the same funding scope.');
    national+=n;federal+=f;
  }
  assert.equal(national,cents(finance.nationalDecimal));assert.equal(federal,cents(finance.federalDecimal));
  assert.equal(national,cents(finance.totalDecimal));
  for(const row of finance.sourceYears.filter(row=>row.amount_decimal===null))assert.equal(row.amount_thousand_rub,null);
  close(finance.hhi,finance.federalShares.reduce((sum,row)=>sum+row.share**2,0),'FP financing concentration.');
  const budget=finance.budgetBill;
  assert.equal(sha(await bytes(budget.source_html_download)),budget.source_html_sha256);
  assert.equal(budget.unit,'млн руб.');
  assert.equal(budget.rows.length,budget.published_numeric_cells);
  for(const row of budget.rows){
    assert.ok(row.source_locator&&row.source_sha256);
    assert.ok(!/^\d+$/.test(row.name),'Column number is not a budget expenditure row.');
  }

  const nodeMap=new Map(documentary.network.nodes.map(row=>[row.id||row.node_id,row]));
  assert.equal(nodeMap.size,documentary.network.nodes.length);
  for(const edge of documentary.network.reviewedEdges)assert.ok(edge.evidence_class&&edge.source_locator,
    'A reviewed link must retain the review basis and source address.');
  for(const pair of documentary.network.sharedTaskPairs){
    const result=nodeMap.get(pair.result_node_id),indicator=nodeMap.get(pair.indicator_node_id),task=nodeMap.get(pair.task_node_id);
    assert.equal(result?.kind,'result');assert.equal(indicator?.kind,'indicator');assert.equal(task?.kind,'task');
    assert.equal(result.document_id,pair.document_id);assert.equal(indicator.document_id,pair.document_id);assert.equal(task.document_id,pair.document_id);
    assert.notEqual(task.scope,'national_structure_federal_task_restatement');
    assert.equal(pair.official_weight??null,null);
    assert.equal(pair.causal_status,'not_identified');
    assert.equal(pair.evidence_class,'same_document_task_membership');
  }
  for(const claim of documentary.network.unresolvedClaims)assert.equal(claim.indicator_node_id,null);
  for(const row of finance.resultYears){
    const result=nodeMap.get(row.result_id);assert.equal(result?.kind,'result');
    assert.equal(result.document_id,row.document_id);assert.equal(result.source_locator,row.source_result_locator);
    assert.ok(row.source_locator.startsWith(row.source_result_locator+'/'));
    if(row.is_subcomponent)assert.equal(row.included_in_additive_total,false);
  }
  for(const source of documentary.sources){
    assert.equal(sha(await bytes(source.download_path)),source.source_sha256||source.sha256);
    assert.equal(source.source_kind,'secondary_epbs_rendering');
  }
  assert.deepEqual(runtime.network.summary,documentary.network.summary);
  assert.equal(runtime.targets.items.length,statistics.registry.length);
  let targetCells=0,targetNumbers=0;
  for(const target of documentary.targets.items){
    assert.ok(target.source_sha256&&target.source_locator&&target.source_document);
    assert.deepEqual(Object.keys(target.years),['2025','2026','2027','2028','2029','2030']);
    for(const value of Object.values(target.years)){assert.ok(value===null||Number.isFinite(value));targetCells++;if(value!==null)targetNumbers++;}
  }
  assert.equal(documentary.targets.target_cells,targetCells);assert.equal(documentary.targets.numeric_targets,targetNumbers);
  assert.equal(documentary.targets.missing_targets,targetCells-targetNumbers);
  assert.equal(typeof documentary.text.authorExactCodeAvailable,'boolean');
  assert.ok(documentary.text.sensitivity.length>=2,'Textual sensitivity must retain the actual alternative specifications.');
  const author=documentary.text.authorAnalysis;
  assert.equal(author.documents,documentary.meta.corpus_documents);
  assert.equal(author.economic_documents,documentary.sources.length);
  assert.equal(sha(await bytes(author.source_code_url)),author.source_code_sha256,'Included author analysis code.');
  assert.equal(sha(await bytes(author.shared_profiles_url)),author.shared_profiles_sha256,'Pinned shared text corpus.');
  if(documentary.text.authorExactCodeAvailable){
    assert.equal(author.baseline_and_stemming_match_reference,true);
    assert.equal(author.all_economic_source_profiles_verified,true);
    for(const item of documentary.text.replicationAudit)assert.equal(item.equal,true,'Exact reference replay: '+item.metric);
  }
  for(const file of Object.values(documentary.text.documentFiles))await bytes(file);
  for(const item of documentary.text.replicationAudit)assert.equal(item.difference,item.platform_recomputed-item.author_report);
  for(const url of Object.values(runtime.downloads))await bytes(url);
  assert.equal(status.project_id,'competitive_economy');
  assert.ok(status.checked_at&&status.published_at);
  console.log(`Validated Competitive: ${statistics.sources.length} sources, ${cells} cells, ${numeric} numeric values, ${reportCheck.routes} pages, ${nodeMap.size} documentary nodes and source-linked financial arithmetic.`);
  return {sources:statistics.sources.length,cells,numeric,routes:reportCheck.routes,nodes:nodeMap.size};
}
