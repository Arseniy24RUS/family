/** Validate Export source identity, analytical scope, complete report and published links. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {internationalExportPages,getProject} from '../src/platform/projects.js';
import {validateExportContent} from './build_export.mjs';

const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const sourceId=source=>String(source.source_id??source.id);
const reportHash='2af8cbdc122dfbaa1c8896def0d2584b9b128ac019d9f00f7752495ea17b1f63';
const close=(a,b,label)=>assert.ok(Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=1e-9*Math.max(1,Math.abs(b)),label);
const decimalCents=value=>{
  assert.match(String(value),/^-?\d+(?:\.\d{1,2})?$/);
  const negative=String(value).startsWith('-');
  const [whole,fraction='']=String(value).replace(/^-/,'').split('.');
  return(negative?-1n:1n)*(BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0')));
};

// Initial snapshot cells are immutable. New live cells must be independently
// reconstructible from the retained response which their SHA identity names.
const SOURCE_CHECK=String.raw`
import sys,json,zipfile,hashlib
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
payload=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
sys.path.insert(0,payload['scripts'])
from export_data import normalize_record
original_count=published_count=live_count=response_count=0
for bundle in payload['bundles']:
    contract=bundle['contract']
    with zipfile.ZipFile(bundle['path']) as archive:
        assert archive.testzip() is None, 'Original source ZIP CRC failure'
        for item in bundle['evidence_files']:
            raw=archive.read(item['path'])
            assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256'], 'Original evidence hash or size differs'
        original=json.loads(archive.read('observations.json'))
    source_index={str(r['observation_key']):r for r in original}
    assert len(source_index)==len(original), 'Duplicate original source observation key'
    original_normalized={normalize_record(r,contract)['id']:normalize_record(r,contract) for r in original}
    assert len(original_normalized)==len(original), 'Original frequencies collapsed into one observation'
    original_count+=len(original)
    published=json.loads(Path(bundle['published']).read_text(encoding='utf-8'))['observations']
    assert set(original_normalized).issubset({r['id'] for r in published}), 'An original observation identity was lost'
    live_by_digest={}
    for response in bundle['responses']:
        from refresh_export_emiss import normalized_live
        from emiss_adapter.client import query_plan
        from emiss_adapter.sdmx import parse_sdmx
        from dataeconomy_formats import parse_excel,parse_grid
        location=Path(response['absolute_path']);blob=location.read_bytes()
        assert hashlib.sha256(blob).hexdigest()==response['archive_sha256'], 'Retained response ZIP hash differs'
        with zipfile.ZipFile(location) as archive:
            assert archive.testzip() is None, 'Current response ZIP CRC failure'
            fmt=contract['export_format'];name={'sdmx':'data.xml','excel':'data.xls','grid':'data.json'}[fmt]
            raw=archive.read(name);digest=hashlib.sha256(raw).hexdigest()
            assert digest==response['response_sha256'], 'Live response bytes differ from the observation snapshot identity'
            meta=json.loads(archive.read('metadata.json'));selected=json.loads(archive.read('selected.json'))
        roles,_=query_plan(meta,contract,300000)
        parsed,_=parse_sdmx(raw) if fmt=='sdmx' else (parse_grid if fmt=='grid' else parse_excel)(raw,meta,selected)
        normalized=normalized_live(parsed,meta,roles,selected,contract,{},response['acquired_at'],{})
        live_by_digest[digest]={r['id']:r for r in normalized};response_count+=1
    for row in published:
        source=source_index.get(row['source_observation_key'])
        if source and row['snapshot_id']==source['snapshot_id']:
            expected=original_normalized[row['id']]
            assert row['raw']==str(source.get('value_raw','')), 'Original cell text changed'
        else:
            assert row['snapshot_id'].startswith('live:') and len(row['snapshot_id'])==69, 'Unidentified current observation'
            digest=row['snapshot_id'][5:]
            assert row['source_observation_key']==row['snapshot_id']+':'+row['id'], 'Live source observation identity differs'
            assert digest in live_by_digest, 'Retained live observation lost its own raw response'
            assert row['id'] in live_by_digest[digest], 'Live observation not present in its identified response'
            expected=live_by_digest[digest][row['id']];live_count+=1
        for field in ['id','value','unit','source_frequency','source_period_start','source_period_end','period_start','period_end','frequency','name','category']:
            assert row[field]==expected[field], 'Published cell differs from its actual source: '+field
        published_count+=1
cbr_count=0
for source in payload['cbr_sources']:
    with zipfile.ZipFile(source['absolute_path']) as archive:
        assert archive.testzip() is None, 'CBR workbook CRC failure'
        sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    cells={c.attrib['r']:c.find('m:v',ns).text for c in sheet.findall('.//m:c',ns) if c.find('m:v',ns) is not None}
    for row in source['rows']:
        assert cells[row['source_cell']]==row['raw_value'], 'CBR original XML cell text differs'
        assert Decimal(cells[row['source_cell']]).quantize(Decimal('0.01'))==Decimal(str(row['value'])), 'CBR value differs at the published two-decimal precision'
        cbr_count+=1
print(json.dumps({'source_bundles':len(payload['bundles']),'original_snapshot_cells':original_count,'published_cells_checked':published_count,'live_rows_checked':live_count,'retained_responses_checked':response_count,'cbr_cells_checked':cbr_count}))
`;

export async function validateExport(root=path.resolve(import.meta.dirname,'..')){
  const docs=path.join(root,'docs'),prefix='data/projects/international_export/';
  const bytes=relative=>fs.readFile(path.join(docs,relative));
  const read=async relative=>JSON.parse(await bytes(relative));
  const [statistics,analytics,documentary,expertise,foundation,methods,targets,regional]=await Promise.all(
    ['statistics','analytics','documentary','expertise','foundation','methods','targets','regional-context'].map(name=>read(prefix+name+'.json'))
  );
  const config=JSON.parse(await fs.readFile(path.join(root,'scripts/export_emiss_sources.json'),'utf8'));
  const contracts=new Map(config.sources.map(c=>[String(c.indicator_id),c]));
  assert.equal(statistics.project_id,'international_export');assert.equal(analytics.project_id,'international_export');
  assert.equal(documentary.meta.project_id,'international_export');assert.equal(foundation.author_expertise_status,'published');
  assert.equal(getProject('international_export').color,'#2B3847');assert.equal(getProject('international_export').hasAuthors,false);
  assert.equal(foundation.release_date,'2026-10-30');assert.equal(foundation.author_edition_date,'2026-10-29');
  const reportCheck=validateExportContent(expertise);
  assert.equal(expertise.meta.source_docx_sha256,reportHash);assert.equal(hash(await bytes(expertise.meta.report_url)),reportHash);
  assert.equal(expertise.tables.length,16);assert.equal(expertise.figures.length,15);assert.equal(expertise.meta.footnotes,115);
  assert.equal(expertise.meta.formulas,11);assert.equal(expertise.meta.total_math_nodes,11);
  const coverage=await read(expertise.meta.coverage_url);
  assert.equal(coverage.summary.source_body_blocks,448);assert.equal(coverage.summary.substantive_blocks,384);assert.equal(coverage.summary.assigned_blocks,384);
  assert.deepEqual(coverage.summary.unmapped_substantive_blocks,[]);assert.deepEqual(coverage.summary.duplicate_assignments,[]);
  for(const figure of expertise.figures)assert.equal(hash(await bytes(figure.url)),figure.original_sha256,'Original figure: '+figure.id);
  for(const table of expertise.tables)await bytes(table.csv_url);

  const localLinks=new Set();
  function collect(value,key=''){
    if(Array.isArray(value)){for(const item of value)collect(item,key);return;}
    if(value&&typeof value==='object'){for(const [field,item] of Object.entries(value))collect(item,field);return;}
    if(typeof value==='string'&&/^(?:\.\/)?(?:data|downloads|assets|research|src)\/[\w\u0400-\u04ff]/u.test(value)&&!/[\r\n]/.test(value))localLinks.add(value.replace(/^\.\//,''));
  }
  for(const value of [statistics,analytics,documentary,expertise,foundation,regional])collect(value);
  const htmlFiles=[];
  for(const page of internationalExportPages){
    const relative='research/projects/international_export/'+(page.id==='overview'?'index':page.id)+'.html';
    const html=(await bytes(relative)).toString('utf8');
    assert.ok(html.includes('--brand:#2B3847;'),'Export static theme: '+page.id);
    assert.ok(html.includes('--study-table-head:#fff;'),'Export white table headings: '+page.id);
    assert.ok(html.includes('#/projects/international_export/'+page.id),'Export interactive route: '+page.id);
    assert.ok(!/href=["'][^"']*#\/(?:projects\/international_export\/)?authors/.test(html),'Authors stay with Family.');
    htmlFiles.push([relative,html]);
  }
  htmlFiles.push([expertise.meta.html_url,(await bytes(expertise.meta.html_url)).toString('utf8')]);
  for(const [relative,html] of htmlFiles){
    for(const match of html.matchAll(/\b(?:href|src)\s*=\s*(["'])(.*?)\1/gis)){
      const raw=match[2].replaceAll('&amp;','&');if(!raw||/^(?:mailto:|data:|tel:|javascript:)/i.test(raw))continue;
      const resolved=new URL(raw,'https://international-export.local/family/'+relative);
      if(resolved.origin!=='https://international-export.local')continue;
      assert.ok(resolved.pathname.startsWith('/family/'),'Local link remains inside Pages project path: '+raw);
      let target=decodeURIComponent(resolved.pathname.slice('/family/'.length));if(!target||target.endsWith('/'))target+='index.html';localLinks.add(target);
      if(resolved.pathname==='/family/'+relative&&resolved.hash.startsWith('#source-'))assert.ok(html.includes('id="'+resolved.hash.slice(1)+'"'),'Missing source anchor: '+resolved.hash);
    }
  }

  assert.equal(statistics.sources.length,18);assert.equal(contracts.size,18);assert.equal(new Set(statistics.sources.map(sourceId)).size,18);
  assert.equal(statistics.registry.length,21);assert.equal(statistics.coverage.known_sources,20);assert.equal(statistics.coverage.metadata_only_sources,2);
  assert.deepEqual(analytics.coverage,statistics.coverage);assert.equal(statistics.coverage.regional_sources,0);assert.equal(statistics.coverage.regions,0);
  const observations=new Map(),bundles=[];let cells=0,numeric=0,usable=0,excluded=0,annual=0,hasCurrent=false;
  for(const source of statistics.sources){
    const id=sourceId(source),relative=prefix+'series/'+id+'.json',raw=await bytes(relative),packet=JSON.parse(raw),provenance=await read(prefix+'provenance/'+id+'.json');
    assert.equal(packet.project_id,'international_export');assert.equal(String(packet.source_id),id);assert.equal(packet.unit,source.unit);
    assert.equal(hash(raw),provenance.published_sha256,'Published series checksum: '+id);assert.equal(hash(await bytes(provenance.input_bundle)),provenance.input_sha256,'Original bundle checksum: '+id);
    assert.equal(packet.snapshot_id,provenance.snapshot_id);assert.equal(packet.observations.length,provenance.observations);assert.equal(source.observations_count,packet.observations.length);
    let sn=0,su=0;const identities=new Set();
    for(const row of packet.observations){
      assert.equal(String(row.source_id),id);assert.ok(row.id&&!observations.has(row.id));assert.ok(row.source_observation_key&&typeof row.raw==='string');
      assert.match(row.source_period_start,/^\d{4}-\d{2}-\d{2}$/);assert.match(row.source_period_end,/^\d{4}-\d{2}-\d{2}$/);assert.ok(row.source_period_start<=row.source_period_end);
      assert.ok(row.value===null||Number.isFinite(row.value));assert.equal(row.geo_level,'national');assert.equal(row.map_id,null);
      assert.ok(Array.isArray(row.quality_flags));assert.equal(row.analytical_value,row.excluded?null:row.value);
      if(row.excluded)assert.ok(row.quality_flags.some(flag=>flag.exclude_from_analysis===true));
      const identity=JSON.stringify([id,row.name,row.source_frequency,row.source_period_start,row.source_period_end,row.category]);assert.ok(!identities.has(identity),'Source frequency is a distinct observation dimension.');identities.add(identity);
      if(row.frequency==='cumulative_ytd'){assert.equal(row.period_start,row.year+'-01-01');assert.notEqual(row.source_frequency,'annual');}
      if(row.source_frequency==='annual')assert.equal(row.period,String(row.year));
      if(row.value!==null){numeric++;sn++;}if(row.analytical_value!==null){usable++;su++;}if(row.value!==null&&row.excluded)excluded++;
      if(row.source_frequency==='annual'&&!row.excluded)annual++;observations.set(row.id,row);
    }
    cells+=packet.observations.length;assert.equal(provenance.numeric,sn);assert.equal(source.numeric_count,sn);assert.equal(source.usable_count,su);
    assert.equal(source.last_available_period,packet.observations.filter(row=>row.analytical_value!==null).map(row=>row.period_end).sort().at(-1));
    for(const row of source.national){const original=observations.get(row.id);assert.ok(original);for(const key of ['value','analytical_value','frequency','source_frequency','period_end'])assert.equal(row[key],original[key]);}
    const history=[...(provenance.retained_responses||[])];
    if(provenance.current_raw){
      hasCurrent=true;assert.equal(hash(await bytes(provenance.current_raw)),provenance.current_raw_sha256);
      if(!history.some(r=>r.path===provenance.current_raw))history.push({path:provenance.current_raw,archive_sha256:provenance.current_raw_sha256,response_sha256:provenance.response_sha256,acquired_at:provenance.acquired_at});
    }
    for(const response of history){assert.equal(hash(await bytes(response.path)),response.archive_sha256);assert.match(response.response_sha256,/^[a-f0-9]{64}$/);}
    bundles.push({path:path.join(docs,provenance.input_bundle),published:path.join(docs,relative),evidence_files:provenance.evidence_files,contract:contracts.get(id),responses:history.map(r=>({...r,absolute_path:path.join(docs,r.path)}))});collect(provenance);
  }
  for(const [key,value] of Object.entries({observations:cells,numeric_observations:numeric,usable_observations:usable,excluded_numeric_observations:excluded,independent_annual_national_facts:annual,numeric_sources:18}))assert.equal(statistics.coverage[key],value,'Coverage: '+key);
  if(!hasCurrent){assert.equal(cells,181);assert.equal(annual,4);assert.equal(analytics.target_comparisons.length,11);}
  for(const source of statistics.metadata_sources){assert.equal(source.numeric_observations,0);assert.equal(hash(await bytes(source.download_url)),source.input_sha256);}

  assert.equal(targets.items.length,21);assert.equal(targets.allCards.length,25);assert.equal(targets.numeric_targets,122);assert.equal(targets.missing_targets,4);
  const missingTarget=targets.items.find(t=>t.indicator_code==='2.14.М3.7');assert.deepEqual(missingTarget.years,{'2025':null,'2026':null,'2027':null,'2028':4,'2029':4,'2030':null});
  const standard=targets.items.find(t=>String(t.source_id)==='62731');assert.equal(standard.annual_comparison_eligible,false);assert.equal(standard.mapping_status,'historical_standard_version_mismatch');
  assert.ok(!analytics.target_comparisons.some(c=>String(c.source_id)==='62731'));
  for(const comparison of analytics.target_comparisons){
    const row=observations.get(comparison.reference_observation_id);assert.ok(row);assert.equal(row.analytical_value,comparison.value);assert.equal(String(row.source_id),String(comparison.source_id));assert.equal(row.unit,comparison.unit);
    assert.ok(row.source_frequency==='annual'||row.annual_equivalent_eligible);assert.equal(row.year,comparison.year);close(comparison.difference,comparison.value-comparison.target,'Target arithmetic');
    if(comparison.target===0)assert.equal(comparison.difference_pct,null);assert.notEqual(comparison.formal_attainment_eligible,true);assert.equal(comparison.causal_status,'not_identified');
    const annualRows=[...observations.values()].filter(r=>r.source_id===row.source_id&&r.year===row.year&&r.annual_comparison_eligible&&r.analytical_value!==null);
    if(annualRows.length)assert.equal(row.source_frequency,'annual','An explicit annual record takes precedence over December only for annual comparison.');
  }

  const finance=documentary.finance;assert.equal(finance.projects.length,4);assert.equal(finance.consolidatedTotalThousandRub,null);
  assert.equal(decimalCents(finance.totalDecimal),72331164510n);assert.equal(decimalCents(finance.adjustedTotalDecimal),72197328880n);
  assert.equal(decimalCents(finance.totalDecimal)-decimalCents(finance.adjustedTotalDecimal),decimalCents(finance.knownDuplicateTransferThousandRub));
  assert.equal(decimalCents(finance.knownDuplicateTransferThousandRub),133835630n);assert.equal(finance.ownRegionalContribution2025ThousandRub,33282.2);assert.equal(finance.outsideHorizonThousandRub,3921704.4);
  for(const group of [finance.projects,finance.yearTotals,finance.sourceTotals])assert.equal(group.reduce((n,r)=>n+decimalCents(r.totalDecimal),0n),decimalCents(finance.totalDecimal));
  for(const row of finance.sourceReconciliation){assert.equal(decimalCents(row.nationalDecimal),decimalCents(row.federalProjectSumDecimal));assert.equal(decimalCents(row.differenceDecimal),0n);}
  assert.equal(finance.sourceReconciliation.length,9);const tr=finance.transferReconciliation;assert.equal(decimalCents(tr.federalTotalDecimal)-decimalCents(tr.explicitResultFederalDecimal),decimalCents(tr.differenceDecimal));
  assert.equal(finance.budgetProposal.baseline_year,2026);assert.equal(finance.budgetProposal.baseline_as_of,'2026-09-01');assert.equal(finance.cashExecution.amountThousandRub,null);
  const network=documentary.network,nodeIds=new Set(network.nodes.map(n=>n.id));assert.equal(network.nodes.length,89);assert.equal(network.structuralPairs.length,284);assert.equal(network.ambiguousClaims.length,101);assert.equal(network.lexicalPairs.length,15);assert.equal(network.lexicalCandidates.length,47);assert.equal(network.counts.resolvedDirectLinks,0);
  for(const row of [...network.structuralPairs,...network.lexicalPairs]){assert.ok(nodeIds.has(row.result_node_id)&&nodeIds.has(row.indicator_node_id));assert.equal(row.official_weight,null);assert.equal(row.causal_status,'not_identified');}
  for(const row of network.ambiguousClaims)assert.equal(row.indicator_node_id,null);
  assert.equal(documentary.sources.length,8);assert.equal(documentary.meta.structured_passports,5);
  for(const source of documentary.sources)if(source.download_url&&source.sha256)assert.equal(hash(await bytes(source.download_url)),source.sha256);
  const text=documentary.text;assert.equal(text.profileCount,65);assert.equal(text.corpusDocuments.length,65);assert.equal(text.documents.length,4);assert.equal(text.authorExactCodeAvailable,false);
  assert.deepEqual(text.candidateThresholds.map(r=>r.pairs),[28,15,8,6]);assert.deepEqual(text.candidateThresholds.map(r=>r.author_reported_results),[26,15,8,6]);assert.equal(text.candidateThresholds[0].matches_author,false);
  for(const profile of text.profiles)assert.equal(hash(Buffer.from(profile.text)),profile.text_sha256);
  const matrix=text.resultIndicatorMatrix;assert.equal(matrix.rows.length,47);assert.equal(matrix.columns.length,18);assert.equal(matrix.values.length,47);
  for(const row of matrix.values){assert.equal(row.length,18);assert.ok(row.every(n=>Number.isFinite(n)&&n>=0&&n<=1+1e-12));}
  assert.equal(text.documentSimilarity.length,16);assert.equal(text.frameScores.length,24);
  for(const row of text.frameScores)close(row.percent,100*row.count/row.denominator,'Theme denominator is result profiles of the same FP.');

  assert.deepEqual(analytics.regional_context,regional);const services=regional.services;assert.equal(services.rows.length,170);assert.deepEqual(services.years,[2024,2025]);assert.deepEqual([...services.missing_map_ids].sort(),['90','93','94','95']);
  const cbrSources=[];
  for(const source of services.sources){
    assert.equal(hash(await bytes(source.local_file)),source.sha256,'CBR source checksum');const rows=services.rows.filter(r=>r.year===source.year);assert.equal(rows.length,85);assert.equal(new Set(rows.map(r=>r.map_id)).size,85);
    assert.ok(rows.every(r=>Number.isFinite(r.value)&&r.value>=0&&!services.missing_map_ids.includes(r.map_id)));
    const total=rows.reduce((n,r)=>n+r.value,0),national=services.national.find(r=>r.year===source.year),unallocated=services.unallocated.find(r=>r.year===source.year),concentration=services.concentration.find(r=>r.year===source.year),rec=services.reconciliation.find(r=>r.year===source.year);
    close(concentration.allocated_million_usd,total,'CBR regional sum');close(concentration.hhi_allocated,rows.reduce((n,r)=>n+(r.value/total)**2,0),'CBR HHI');
    close(concentration.top10_share_national_pct,rows.map(r=>r.value).sort((a,b)=>b-a).slice(0,10).reduce((a,b)=>a+b,0)/national.value*100,'CBR top 10 national share');
    assert.equal(rows.reduce((n,r)=>n+decimalCents(r.value),0n)+decimalCents(unallocated.value)-decimalCents(national.value),decimalCents(rec.residual));assert.ok(Math.abs(rec.residual)<=rec.tolerance);
    cbrSources.push({absolute_path:path.join(docs,source.local_file),rows:[...rows,national,unallocated]});
  }
  assert.equal(services.growth_summary.increased,63);assert.equal(services.growth_summary.decreased,22);assert.equal(services.growth_summary.comparable_regions,85);
  const python=process.env.PYTHON||(process.platform==='win32'?'python':'python3'),checkDirectory=await fs.mkdtemp(path.join(os.tmpdir(),'international-export-source-check-'));let sourceCheck;
  try{
    const payloadPath=path.join(checkDirectory,'sources.json');await fs.writeFile(payloadPath,JSON.stringify({scripts:import.meta.dirname,bundles,cbr_sources:cbrSources}));
    sourceCheck=JSON.parse(execFileSync(python,['-c',SOURCE_CHECK,payloadPath],{encoding:'utf8',stdio:['ignore','pipe','pipe'],maxBuffer:1024*1024,timeout:60000}));
  }finally{await fs.rm(checkDirectory,{recursive:true,force:true});}
  assert.equal(sourceCheck.original_snapshot_cells,181);assert.equal(sourceCheck.published_cells_checked,cells);assert.equal(sourceCheck.source_bundles,18);assert.equal(sourceCheck.cbr_cells_checked,174);

  assert.notEqual(analytics.multivariate?.status,'computed');assert.equal(analytics.forecasts.length,0);assert.ok(analytics.forecast_eligibility.every(r=>r.eligible===false));
  assert.equal(foundation.panel.pca_performed,false);assert.equal(foundation.panel.clustering_performed,false);assert.equal(foundation.panel.spatial_autocorrelation_performed,false);assert.equal(foundation.results.n_forecast_indicators,0);assert.equal(foundation.results.n_projected_series,0);
  assert.equal(foundation.research.causal_effect_status,'not_identified_in_existing_sources');assert.equal(foundation.research.financing_status,'known_duplicate_removed_full_consolidation_unresolved');assert.equal(foundation.research.strict_financing_hhi,null);assert.ok(foundation.legacy_release_metadata);
  assert.equal(methods.items.length,39);assert.ok(methods.items.every(r=>r.current_status&&r.current_status_label&&r.current_limitations));assert.equal(foundation.method_summary.total,39);
  assert.equal(foundation.registry.n_unique_cells,cells);assert.equal(foundation.registry.n_numeric,numeric);assert.equal(foundation.registry.n_with_numeric,statistics.coverage.semantically_available_indicators);
  for(const candidate of localLinks){const clean=candidate.split(/[?#]/,1)[0],resolved=path.resolve(docs,clean);assert.ok(resolved===docs||resolved.startsWith(docs+path.sep),'Local link cannot escape publication: '+candidate);await fs.access(resolved);}
  const result={sources:18,cells,numeric,usable,excluded,independent_annual:annual,routes:reportCheck.routes,source_blocks:384,source_body_blocks:448,tables:16,figures:15,footnotes:115,formulas:11,local_links_checked:localLinks.size,...sourceCheck,context_regions:85,context_cells:170};console.log('Validated Export: '+JSON.stringify(result));return result;
}
