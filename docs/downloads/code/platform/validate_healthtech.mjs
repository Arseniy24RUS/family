/** Validate the published health-technology evidence, arithmetic and routes. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {healthtechPages,getProject} from '../src/platform/projects.js';
import {validateHealthtechContent} from './build_healthtech.mjs';

const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const close=(actual,expected,label)=>assert.ok(Math.abs(actual-expected)<=1e-9*Math.max(1,Math.abs(expected)),label);
const monetaryUnits=value=>{
  assert.match(value,/^-?\d+(?:\.\d{1,2})?$/,'Financial amounts retain exact hundredths.');
  const negative=value.startsWith('-'),[integer,fraction='']=value.replace('-','').split('.');
  return (BigInt(integer)*100n+BigInt(fraction.padEnd(2,'0')))*(negative?-1n:1n);
};

export async function validateHealthtech(root){
  const docs=path.join(root,'docs'),prefix='data/projects/health_technologies/';
  const bytes=relative=>fs.readFile(path.join(docs,relative.replace(/^\.\//,'')));
  const read=async relative=>JSON.parse(await bytes(relative));
  const [statistics,analytics,report,documentary,status,methods]=await Promise.all(
    ['statistics','analytics','expertise','documentary','refresh-status','methods'].map(name=>read(prefix+name+'.json')));
  const config=JSON.parse(await fs.readFile(path.join(root,'scripts/healthtech_emiss_sources.json'),'utf8'));
  for(const packet of [statistics,analytics,status,methods])assert.equal(packet.project_id,'health_technologies');
  assert.equal(documentary.meta.project_id,'health_technologies');
  assert.equal(getProject('health_technologies').color,'#0A8BBF');
  assert.equal(getProject('health_technologies').hasAuthors,false);
  const checkedReport=validateHealthtechContent(report);
  assert.equal(hash(await bytes(report.meta.report_url)),report.meta.source_docx_sha256,'Original DOCX bytes.');
  const coverage=await read(report.meta.coverage_url);
  assert.equal(coverage.summary.substantive_blocks,coverage.summary.assigned_blocks);
  assert.deepEqual(coverage.summary.unmapped_substantive_blocks,[]);
  assert.deepEqual(coverage.summary.duplicate_assignments,[]);
  assert.equal(coverage.summary.tables,report.tables.length);
  assert.equal(coverage.summary.figures,report.figures.length);
  for(const figure of report.figures)await fs.access(path.join(docs,figure.url));
  const reportSources=new Set(report.sources.map(source=>source.id));
  for(const source of report.sources.filter(source=>source.kind==='source_note')){
    assert.ok(source.source_blocks?.length,'Every footnote has an original body or table reference: '+source.id);
    assert.ok(Object.values(report.pages).some(page=>page.blocks.some(block=>(block.sourceIds||[]).includes(source.id))),
      'Every footnote is reachable from a published report block: '+source.id);
  }
  for(const table of report.tables){
    for(const id of [...(table.headerSourceIds||[]).flat(),...(table.cellSourceIds||[]).flat(2)]){
      assert.ok(reportSources.has(id)&&table.sourceIds.includes(id),'Cell citation remains attached to its table.');
    }
  }

  assert.deepEqual(new Set(statistics.sources.map(s=>s.id)),new Set(config.sources.map(s=>s.indicator_id)));
  assert.equal(statistics.registry.length,statistics.summary.registry_indicators);
  assert.equal(new Set(statistics.registry.map(r=>r.indicator_code)).size,statistics.registry.length);
  assert.deepEqual(analytics.coverage,statistics.summary,'Runtime and analytics describe the same snapshot.');
  assert.equal(statistics.meta.geography_scope,'national_only');
  const observations=new Map(),sources=new Map(statistics.sources.map(s=>[s.id,s]));
  let cells=0,numeric=0,usable=0,excluded=0,annual=0,available=0;
  for(const source of statistics.sources){
    const raw=await bytes(prefix+'series/'+source.id+'.json'),packet=JSON.parse(raw);
    const provenance=await read(prefix+'provenance/'+source.id+'.json');
    assert.equal(packet.project_id,'health_technologies');
    assert.equal(packet.source_id,source.id);
    assert.equal(packet.unit,source.unit);
    assert.equal(hash(raw),provenance.published_sha256,'Published source SHA: '+source.id);
    assert.equal(packet.observations.length,source.observation_count);
    assert.deepEqual(packet.observations,source.national,'Summary retains every raw national cell.');
    assert.equal(source.regional_latest.length,0);
    assert.equal(source.annual_equivalents.length,0,'Monthly records do not create annual equivalents.');
    const ids=new Set(),periods=new Set();
    let sourceNumeric=0,sourceUsable=0,sourceExcluded=0;
    for(const row of packet.observations){
      assert.equal(row.source_id,source.id);
      assert.equal(row.geo_level,'national');
      assert.equal(row.code,'643');
      assert.equal(row.map_id,null);
      assert.equal(row.geographic_comparison_eligible,false);
      assert.ok(!ids.has(row.id));ids.add(row.id);
      const periodKey=row.frequency+'|'+row.period;
      assert.ok(!periods.has(periodKey));periods.add(periodKey);
      assert.ok(!observations.has(row.id));observations.set(row.id,row);
      assert.ok(row.source_observation_key&&typeof row.raw_value==='string');
      assert.match(row.period_start,/^\d{4}-\d{2}-\d{2}$/);
      assert.match(row.period_end,/^\d{4}-\d{2}-\d{2}$/);
      assert.ok(row.value===null||Number.isFinite(row.value));
      assert.equal(row.analytical_value,row.excluded?null:row.value);
      assert.ok(Array.isArray(row.quality_flags));
      if(row.value!==null){numeric++;sourceNumeric++;}
      if(row.analytical_value!==null){usable++;sourceUsable++;}
      if(row.value!==null&&row.excluded){excluded++;sourceExcluded++;}
      if(row.annual_comparison_eligible){assert.equal(row.frequency,'annual');assert.notEqual(row.analytical_value,null);}
      if(row.frequency==='annual'&&row.analytical_value!==null)annual++;
      if(row.origin_kind==='secondary_emiss_republication')assert.ok(row.source_locator);
    }
    cells+=packet.observations.length;
    assert.equal(sourceNumeric,source.numeric_count);
    assert.equal(sourceUsable,source.usable_count);
    assert.equal(sourceExcluded,source.excluded_numeric_count);
    assert.equal(packet.observations.length-sourceNumeric,source.missing_count);
    if(sourceNumeric)available++;
    if(source.origin_kind==='secondary_emiss_republication'){
      assert.equal(source.direct_emiss_verified,false);
      assert.equal(source.published_at,provenance.metadata?.published_at||null);
    }
    if(source.downloads.source_input)await bytes(source.downloads.source_input);
    if(provenance.current_raw){assert.equal(hash(await bytes(provenance.current_raw)),provenance.current_raw_sha256);}
    for(const row of [source.latest_national,source.latest_published,source.latest_analytically_usable].filter(Boolean)){
      assert.ok(observations.has(row.id));
    }
  }
  const totals={observations:cells,numeric_observations:numeric,usable_observations:usable,
    excluded_numeric_observations:excluded,missing_observations:cells-numeric,annual_facts:annual,available_sources:available};
  for(const [key,value] of Object.entries(totals))assert.equal(statistics.summary[key],value,key);
  for(const sid of ['63059','62985'])assert.equal(sources.get(sid).target_comparison_allowed,false);
  for(const comparison of analytics.target_comparisons){
    const fact=observations.get(comparison.reference_observation_id);
    assert.ok(fact);
    assert.equal(fact.frequency,'annual');
    assert.equal(fact.analytical_value,comparison.fact_value);
    assert.equal(fact.year,comparison.target_year);
    assert.equal(sources.get(comparison.source_id).target_comparison_allowed,true);
    assert.equal(comparison.formal_attainment_eligible,false);
    close(comparison.difference,comparison.fact_value-comparison.target_value,'Difference arithmetic.');
    if(comparison.target_value)close(comparison.ratio_percent,100*comparison.fact_value/comparison.target_value,'Target ratio.');
  }
  for(const group of ['matched_period_changes','within_year_changes'])for(const change of analytics[group]){
    const [before,after]=change.reference_observation_ids.map(id=>observations.get(id));
    assert.ok(before&&after);assert.equal(before.source_id,after.source_id);
    assert.equal(before.analytical_value,change.from_value);assert.equal(after.analytical_value,change.to_value);
    assert.equal(before.frequency,after.frequency);
    close(change.difference,change.to_value-change.from_value,'Source-linked change.');
  }

  const targets=documentary.targets;
  assert.deepEqual(new Set(targets.items.map(t=>t.indicator_code)),new Set(statistics.registry.map(r=>r.indicator_code)));
  let targetCells=0,targetNumbers=0;
  for(const target of targets.items){
    assert.ok(target.source_sha256&&target.source_locator&&target.source_document);
    assert.deepEqual(Object.keys(target.years),['2025','2026','2027','2028','2029','2030']);
    for(const value of Object.values(target.years)){assert.ok(value===null||Number.isFinite(value));targetCells++;if(value!==null)targetNumbers++;}
  }
  assert.equal(targetCells,targets.target_cells);assert.equal(targetNumbers,targets.numeric_targets);
  assert.equal(targetCells-targetNumbers,targets.missing_targets);

  const finance=documentary.finance;
  assert.equal(finance.unit,'тыс. руб.');
  let federalTotal=0n,nationalTotal=0n;
  for(const year of finance.yearTotals){
    const rows=finance.fpYears.filter(r=>r.year===year.year),visible=rows.filter(r=>r.amount_decimal!==null);
    const total=visible.reduce((sum,row)=>sum+monetaryUnits(row.amount_decimal),0n);
    assert.equal(total,monetaryUnits(year.federal_decimal));
    assert.equal(visible.length,year.published_federal_count);
    assert.equal(rows.length-visible.length,year.missing_federal_count);
    const national=monetaryUnits(year.national_decimal);
    assert.equal(national-total,monetaryUnits(year.difference_decimal),'National minus federal plans.');
    federalTotal+=total;nationalTotal+=national;
    for(const missing of rows.filter(r=>r.amount_decimal===null))assert.equal(missing.amount_thousand_rub,null);
  }
  assert.equal(federalTotal,monetaryUnits(finance.totalDecimal));
  assert.equal(nationalTotal,monetaryUnits(finance.nationalDecimal));
  close(finance.hhi,finance.federalShares.reduce((sum,row)=>sum+row.share**2,0),'Financial concentration.');
  assert.ok(finance.notes.length);
  const documentIds=new Set(documentary.sources.map(s=>s.document_id));
  for(const source of documentary.sources){
    assert.equal(hash(await bytes(source.download_path)),source.source_sha256||source.sha256);
    assert.equal(source.source_kind,'secondary_epbs_rendering');
    assert.match(source.title,/^\[С\d?\]\s\S/,'Document title belongs to the national or federal passport.');
  }
  for(const row of finance.sourceRows){assert.ok(documentIds.has(row.document_id));assert.ok(row.source_sha256&&row.source_locator);}

  const network=documentary.network,nodeIds=new Set(network.nodes.map(n=>n.id||n.node_id));
  assert.equal(nodeIds.size,network.nodes.length);
  const nodesById=new Map(network.nodes.map(n=>[n.id||n.node_id,n]));
  assert.equal(new Set(network.sharedTaskPairs.map(pair=>pair.id)).size,network.sharedTaskPairs.length);
  for(const row of finance.resultYears){
    const node=nodesById.get(row.result_id);
    assert.ok(node&&node.kind==='result');
    assert.equal(node.source_locator,row.source_result_locator);
    assert.equal(node.source_card_id,row.source_result_card_id);
    assert.equal(node.document_id,row.document_id);
    assert.ok(row.source_locator.startsWith(node.source_locator+'/'),'Financial value belongs to this result card.');
  }
  for(const result of finance.resultSums){
    const rows=finance.resultYears.filter(row=>row.result_id===result.result_id);
    assert.ok(rows.length&&nodesById.has(result.result_id));
    assert.equal(rows.reduce((sum,row)=>sum+monetaryUnits(row.amount_decimal),0n),monetaryUnits(result.amount_decimal));
  }
  assert.equal(network.unresolvedClaims.length,network.summary.unresolved_weight_claims);
  for(const claim of network.unresolvedClaims){assert.equal(claim.indicator_node_id,null);assert.ok(claim.source_locator);}
  for(const candidate of network.sharedTaskPairs){
    assert.ok(nodeIds.has(candidate.source_node_id)&&nodeIds.has(candidate.target_node_id));
    assert.equal(candidate.evidence_class,'same_federal_project_candidate');assert.equal(candidate.official_weight,null);
  }
  for(const candidate of network.semanticCandidates){assert.ok(Number.isFinite(candidate.cosine)&&candidate.cosine>=0&&candidate.cosine<=1+1e-12);}
  for(const publication of documentary.officialUpdates){
    assert.equal(publication.source_kind,'official_government_publication');
    assert.match(publication.publication_date,/^\d{4}-\d{2}-\d{2}$/);
    assert.equal(hash(await bytes(publication.download_path)),publication.sha256);
  }
  for(const file of Object.values(documentary.text.documentFiles))await bytes(file);
  assert.equal(documentary.text.profileCount,documentary.meta.corpus_documents);
  assert.equal(documentary.text.authorExactCodeAvailable,false);
  assert.match(documentary.text.replicationStatus,/independent/);
  for(const item of documentary.text.replicationAudit){
    close(item.difference,item.platform_recomputed-item.author_report,'Disclosed replication difference.');
    assert.equal(item.equal,item.author_report===item.platform_recomputed);
  }
  for(const page of healthtechPages){
    const html=await fs.readFile(path.join(docs,'research/projects/health_technologies',page.id==='overview'?'index.html':page.id+'.html'),'utf8');
    assert.ok(html.includes('--brand:#0A8BBF'));assert.ok(html.includes('health_technologies'));
  }
  assert.ok((await fs.stat(path.join(docs,prefix+'documentary.json'))).size<2*1024*1024,'Full corpus loads separately.');
  console.log(`Validated Health Technologies: ${statistics.registry.length} cards, ${available} numerical publications, ${cells} source cells, ${checkedReport.routes} pages, exact plan reconciliation.`);
  return {routes:checkedReport.routes,sourceCells:cells,numeric,usable,targetCells};
}
