/** Validate published efficient_transport sources, author material, quality masks and local links. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {efficientTransportPages,getProject} from '../src/platform/projects.js';
import {validateTransportContent} from './build_transport.mjs';

const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const sourceId=source=>String(source.source_id??source.id);
const reportHash='fcbf95e7aba2d8c647a1852e8b1241b8af0a542a5056504fe6132b013591e079';
const close=(a,b,label)=>assert.ok(Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=1e-9*Math.max(1,Math.abs(b)),label);

const ZIP_CHECK=String.raw`
import sys, json, zipfile, hashlib, math
with open(sys.argv[1],encoding='utf-8') as input_file:
    payload=json.load(input_file)
checked=0
for bundle in payload:
    with zipfile.ZipFile(bundle['path']) as archive:
        assert archive.testzip() is None, 'Source ZIP CRC failure'
        for evidence in bundle['evidence_files']:
            data=archive.read(evidence['path'])
            assert len(data)==evidence['bytes'], 'Source evidence size differs: '+evidence['path']
            assert hashlib.sha256(data).hexdigest()==evidence['sha256'], 'Source evidence hash differs: '+evidence['path']
        original=json.loads(archive.read('observations.json'))
        source_index={str(row['observation_key']):row for row in original}
        assert len(source_index)==len(original), 'Duplicate original observation keys'
        with open(bundle['published'],encoding='utf-8') as file:
            published=json.load(file)['observations']
        if not bundle.get('has_current_response'):
            assert len(published)==len(original), 'Source observations were lost or synthesized'
        for row in published:
            source=source_index.get(row['source_observation_key'])
            if not source or row['snapshot_id']!=source['snapshot_id']:
                assert bundle.get('has_current_response'), 'Unidentified observation without retained current response'
                assert str(row['snapshot_id']).startswith('live:') and len(row['snapshot_id'])==69, 'Invalid current response identity'
                checked+=1
                continue
            value=source.get('value_numeric')
            expected=None if value is None or str(value).strip()=='' else float(value)
            assert row['value']==expected, 'Original numeric source cell was changed'
            assert str(row['raw'])==str(source.get('value_raw','')), 'Original source text was changed'
            assert row['unit']==source['unit'], 'Original source unit was changed'
            assert row['source_period_start']==source['period_start'], 'Original period start was changed'
            assert row['source_period_end']==source['period_end'], 'Original period end was changed'
            assert row['snapshot_id']==source['snapshot_id'], 'Original snapshot identity was changed'
            checked+=1
print(json.dumps({'source_bundles':len(payload),'original_observations_checked':checked}))
`;

export async function validateTransport(root=path.resolve(import.meta.dirname,'..')){
  const docs=path.join(root,'docs'),prefix='data/projects/efficient_transport/';
  const bytes=relative=>fs.readFile(path.join(docs,relative));
  const read=async relative=>JSON.parse(await bytes(relative));
  const [statistics,analytics,documentary,expertise,foundation,methods]=await Promise.all(
    ['statistics','analytics','documentary','expertise','foundation','methods'].map(name=>read(prefix+name+'.json'))
  );
  assert.equal(statistics.project_id,'efficient_transport');
  assert.equal(analytics.project_id,'efficient_transport');
  assert.equal(documentary.meta.project_id,'efficient_transport');
  assert.equal(foundation.author_expertise_status,'published');
  const reportCheck=validateTransportContent(expertise);
  assert.equal(getProject('efficient_transport').color,'#DCAA44');
  assert.equal(getProject('efficient_transport').hasAuthors,false);
  assert.equal(expertise.meta.source_docx_sha256,reportHash);
  assert.equal(hash(await bytes(expertise.meta.report_url)),reportHash,'Included original DOCX checksum.');
  assert.equal(expertise.tables.length,16);
  assert.equal(expertise.figures.length,9);
  assert.equal(expertise.meta.footnotes,171);
  assert.equal(expertise.meta.formulas,7);
  assert.equal(expertise.meta.inline_formula_nodes,13);
  assert.equal(expertise.meta.bibliography_entries,73);
  const coverage=await read(expertise.meta.coverage_url);
  assert.equal(coverage.summary.substantive_blocks,382);
  assert.equal(coverage.summary.assigned_blocks,382);
  assert.deepEqual(coverage.summary.unmapped_substantive_blocks,[]);
  assert.deepEqual(coverage.summary.duplicate_assignments,[]);
  for(const figure of expertise.figures)assert.equal(hash(await bytes(figure.url)),figure.original_sha256,'Preserved author illustration: '+figure.id);
  for(const table of expertise.tables)await bytes(table.csv_url);

  const localLinks=new Set();
  function collect(value,key=''){
    if(Array.isArray(value)){for(const item of value)collect(item,key);return;}
    if(value&&typeof value==='object'){for(const [field,item] of Object.entries(value))collect(item,field);return;}
    // Corpus local_file records a member of the original research archive, not a web link.
    if(key==='local_file')return;
    if(typeof value==='string'&&/^(?:\.\/)?(?:data|downloads|assets|research|src)\/[\w\u0400-\u04ff]/u.test(value)&&!/[\r\n]/.test(value))localLinks.add(value.replace(/^\.\//,''));
  }
  for(const data of [statistics,analytics,documentary,expertise,foundation])collect(data);
  const htmlFiles=[];
  for(const page of efficientTransportPages){
    const relative='research/projects/efficient_transport/'+(page.id==='overview'?'index':page.id)+'.html';
    const html=(await bytes(relative)).toString('utf8');
    assert.ok(html.includes('--brand:#DCAA44;'),'Transport static theme: '+page.id);
    assert.ok(html.includes('--study-table-head:#fff;'),'White efficient_transport table heads: '+page.id);
    assert.ok(html.includes('#/projects/efficient_transport/'+page.id),'Transport interactive route: '+page.id);
    assert.ok(!/href=["'][^"']*#\/(?:projects\/efficient_transport\/)?authors/.test(html),'Authors stay with Family.');
    htmlFiles.push([relative,html]);
  }
  htmlFiles.push([expertise.meta.html_url,(await bytes(expertise.meta.html_url)).toString('utf8')]);
  for(const [relative,html] of htmlFiles){
    for(const match of html.matchAll(/\b(?:href|src)\s*=\s*(["'])(.*?)\1/gis)){
      const raw=match[2].replaceAll('&amp;','&');
      if(!raw||/^(?:mailto:|data:|tel:|javascript:)/i.test(raw))continue;
      const resolved=new URL(raw,'https://efficient_transport.local/family/'+relative);
      if(resolved.origin!=='https://efficient_transport.local')continue;
      assert.ok(resolved.pathname.startsWith('/family/'),'Local link must remain under the Pages project path: '+raw);
      let target=decodeURIComponent(resolved.pathname.slice('/family/'.length));
      if(!target||target.endsWith('/'))target+='index.html';
      localLinks.add(target);
      if(resolved.pathname==='/family/'+relative&&resolved.hash.startsWith('#source-')){
        assert.ok(html.includes('id="'+resolved.hash.slice(1)+'"'),'Missing static source anchor: '+resolved.hash);
      }
    }
  }

  assert.equal(new Set(statistics.sources.map(sourceId)).size,statistics.sources.length);
  assert.equal(statistics.registry.length,statistics.coverage.registry_indicators);
  assert.deepEqual(analytics.coverage,statistics.coverage);
  const observations=new Map(),bundles=[];
  let cells=0,numeric=0,usable=0,excluded=0,numericSources=0;
  for(const source of statistics.sources){
    const id=sourceId(source),relative=prefix+'series/'+id+'.json';
    const raw=await bytes(relative),packet=JSON.parse(raw),provenance=await read(prefix+'provenance/'+id+'.json');
    assert.equal(packet.project_id,'efficient_transport');
    assert.equal(String(packet.source_id),id);
    assert.equal(packet.unit,source.unit);
    assert.equal(hash(raw),provenance.published_sha256,'Published series checksum: '+id);
    assert.equal(hash(await bytes(provenance.input_bundle)),provenance.input_sha256,'Original source bundle checksum: '+id);
    assert.equal(packet.snapshot_id,provenance.snapshot_id);
    assert.equal(packet.observations.length,provenance.observations);
    if(source.observation_count!==undefined||source.observations_count!==undefined)assert.equal(packet.observations.length,source.observation_count??source.observations_count);
    let sourceNumeric=0,sourceUsable=0,sourceExcluded=0;
    for(const row of packet.observations){
      assert.equal(String(row.source_id),id);
      assert.ok(row.id&&!observations.has(row.id),'Source observations have unique identities.');
      assert.ok(row.source_observation_key&&typeof row.raw==='string','Original source cells are identifiable.');
      assert.ok(row.snapshot_id===provenance.snapshot_id||provenance.current_raw,'An earlier retained observation requires current response provenance.');
      assert.match(row.source_period_start,/^\d{4}-\d{2}-\d{2}$/);
      assert.match(row.source_period_end,/^\d{4}-\d{2}-\d{2}$/);
      assert.ok(row.value===null||Number.isFinite(row.value),'Finite source number or explicit missing value.');
      assert.ok(Array.isArray(row.quality_flags));
      assert.equal(row.analytical_value,row.excluded?null:row.value,'Excluded values remain in the raw source and are absent from analytics.');
      if(row.excluded)assert.ok(row.quality_flags.some(flag=>flag.exclude_from_analysis===true),'Every exclusion has a stated quality reason.');
      if(row.geo_level==='regional')assert.match(String(row.map_id||row.code),/^\d{2}$/);
      if(row.frequency==='cumulative_ytd'){
        assert.equal(row.period_start,row.year+'-01-01');
        assert.ok(row.source_frequency&&row.period_semantics,'Cumulative interpretation retains the source periodicity.');
      }
      if(row.value!==null){numeric++;sourceNumeric++;}
      if(row.analytical_value!==null){usable++;sourceUsable++;}
      if(row.value!==null&&row.excluded){excluded++;sourceExcluded++;}
      observations.set(row.id,row);
    }
    cells+=packet.observations.length;
    if(sourceNumeric)numericSources++;
    assert.equal(provenance.numeric,sourceNumeric);
    if(source.numeric_count!==undefined)assert.equal(source.numeric_count,sourceNumeric);
    if(source.usable_count!==undefined)assert.equal(source.usable_count,sourceUsable);
    if(source.excluded_numeric_count!==undefined)assert.equal(source.excluded_numeric_count,sourceExcluded);
    assert.ok(packet.observations.every(row=>row.geo_level==='national'&&row.map_id===null),'Transport sources must retain their national-only scope.');
    assert.equal(source.last_available_period,packet.observations.filter(row=>row.analytical_value!==null).map(row=>row.period_end).sort().at(-1));
    if(provenance.current_raw)assert.equal(hash(await bytes(provenance.current_raw)),provenance.current_raw_sha256,'Current response checksum: '+id);
    for(const row of [...(source.national||[]),...(source.regional_latest||[])]){
      const original=observations.get(row.id);
      assert.ok(original,'Summary observation belongs to its source packet.');
      assert.equal(row.value,original.value);
      assert.equal(row.analytical_value,original.analytical_value);
      assert.equal(row.period_end,original.period_end);
      assert.equal(row.frequency,original.frequency);
    }
    bundles.push({path:path.join(docs,provenance.input_bundle),published:path.join(docs,relative),evidence_files:provenance.evidence_files,has_current_response:!!provenance.current_raw});
    collect(provenance);
  }
  for(const [key,value] of Object.entries({observations:cells,numeric_observations:numeric,usable_observations:usable,numeric_sources:numericSources}))assert.equal(statistics.coverage[key],value,'Coverage agrees with source packets: '+key);
  if(statistics.coverage.excluded_numeric_observations!==undefined)assert.equal(statistics.coverage.excluded_numeric_observations,excluded);
  if(statistics.coverage.review_exclusions!==undefined)assert.ok(statistics.coverage.review_exclusions<=excluded);
  const python=process.env.PYTHON||(process.platform==='win32'?'python':'python3');
  const checkDirectory=await fs.mkdtemp(path.join(os.tmpdir(),'efficient_transport-source-check-'));
  let originalCheck;
  try{
    const payloadPath=path.join(checkDirectory,'bundles.json');
    await fs.writeFile(payloadPath,JSON.stringify(bundles));
    originalCheck=JSON.parse(execFileSync(python,['-c',ZIP_CHECK,payloadPath],{encoding:'utf8',stdio:['ignore','pipe','pipe'],maxBuffer:1024*1024,timeout:60000}));
  }finally{
    await fs.rm(checkDirectory,{recursive:true,force:true});
  }
  assert.equal(originalCheck.original_observations_checked,cells);

  assert.equal(statistics.sources.length,22);
  assert.equal(statistics.coverage.registry_indicators,24);
  assert.equal(statistics.coverage.regional_sources,0);
  assert.equal(statistics.coverage.regions,0);
  const bySource=id=>[...observations.values()].filter(row=>String(row.source_id)===id);
  for(const id of ['63268','63269']){
    assert.ok(bySource(id).every(row=>row.source_frequency==='annual'||row.annual_equivalent_eligible===false),'Staff monthly data refer to the preceding reporting year.');
    assert.ok(!(analytics.target_comparisons||[]).some(row=>String(row.source_id)===id),'Staff monthly publications cannot certify current-year attainment.');
  }
  const targets=await read(prefix+'targets.json');
  assert.equal(targets.items.length,22);
  assert.equal(targets.allCards.length,25);
  assert.equal(targets.items.find(row=>row.source_id==='62822').years['2025'],null,'Missing port target remains missing.');
  assert.equal(targets.items.find(row=>row.source_id==='62823').years['2025'],0,'Published zero port increment remains zero.');
  for(const target of targets.items.filter(row=>row.fp==='Т1')){
    assert.equal(target.years['2029'],null);
    assert.equal(target.years['2030'],null);
  }
  assert.ok(bySource('62823').some(row=>row.value===0&&!row.excluded),'A valid zero capacity increment remains available.');
  for(const comparison of analytics.target_comparisons||[]){
    if(comparison.target===0)assert.equal(comparison.difference_pct,null,'Zero target has no finite relative attainment ratio.');
  }
  const decimalCents=value=>{
    assert.match(String(value),/^-?\d+(?:\.\d{1,2})?$/);
    const negative=String(value).startsWith('-');
    const [whole,fraction='']=String(value).replace(/^-/,'').split('.');
    return(negative?-1n:1n)*(BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0')));
  };
  const finance=documentary.finance;
  assert.equal(finance.projects.length,9);
  assert.equal(finance.consolidatedTotalThousandRub,null);
  assert.equal(decimalCents(finance.totalDecimal),finance.projects.reduce((sum,row)=>sum+decimalCents(row.totalDecimal),0n),'Federal project plan totals reconcile exactly.');
  assert.equal(decimalCents(finance.totalDecimal),finance.yearTotals.reduce((sum,row)=>sum+decimalCents(row.totalDecimal),0n),'Annual plan totals reconcile exactly.');
  assert.equal(decimalCents(finance.totalDecimal),finance.sourceTotals.reduce((sum,row)=>sum+decimalCents(row.totalDecimal),0n),'Financing sources reconcile exactly.');
  for(const row of finance.sourceReconciliation){
    assert.equal(decimalCents(row.nationalDecimal),decimalCents(row.federalProjectSumDecimal));
    assert.equal(decimalCents(row.differenceDecimal),0n);
  }
  assert.equal(finance.sourceReconciliation.length,18);
  const network=documentary.network,nodeIds=new Set(network.nodes.map(row=>row.id));
  assert.equal(network.nodes.length,92);
  assert.equal(network.structuralPairs.length,54);
  assert.equal(network.ambiguousClaims.length,42);
  assert.equal(network.lexicalPairs.length,36);
  for(const row of [...network.structuralPairs,...network.lexicalPairs]){
    assert.ok(nodeIds.has(row.result_node_id)&&nodeIds.has(row.indicator_node_id),'Every resolved network endpoint exists.');
    assert.equal(row.official_weight,null);
    assert.equal(row.causal_status,'not_identified');
  }
  for(const row of network.ambiguousClaims)assert.equal(row.indicator_node_id,null);
  assert.equal(network.counts.lexicalIndicators,15);
  assert.equal(network.counts.authorReportedLexicalIndicators,16);
  assert.ok(documentary.text.tieSensitivity.some(row=>row.unique_indicators===15));
  assert.ok(documentary.text.tieSensitivity.some(row=>row.unique_indicators===16));
  assert.equal(documentary.text.corpusDocuments.length,137);
  assert.equal(documentary.text.documents.length,10);
  for(const source of documentary.sources){
    if(source.download_url&&source.sha256)assert.equal(hash(await bytes(source.download_url)),source.sha256,'Retained documentary source: '+source.id);
  }

  for(const comparison of analytics.target_comparisons||[]){
    const fact=comparison.fact_value??comparison.value,target=comparison.target_value??comparison.target;
    const referenceId=comparison.reference_observation_id||comparison.fact_observation_id||comparison.observation_id;
    if(referenceId){
      const row=observations.get(referenceId);
      assert.ok(row,'Target reference observation exists.');
      assert.equal(row.geo_level,'national');
      assert.equal(row.analytical_value,fact);
      assert.equal(String(row.source_id),String(comparison.source_id));
    }else{
      const matching=[...observations.values()].filter(row=>String(row.source_id)===String(comparison.source_id)&&row.geo_level==='national'&&row.period===comparison.period&&row.unit===comparison.unit&&row.analytical_value===fact);
      assert.ok(matching.length>0,'Target reference uses a same-period source observation of the same unit.');
    }
    if(Number.isFinite(comparison.difference))close(comparison.difference,fact-target,'Target comparison arithmetic.');
    assert.notEqual(comparison.formal_attainment_eligible,true,'Retrospective passport comparisons do not certify original plan attainment.');
  }
  assert.notEqual(analytics.multivariate?.status,'computed','Federal observations do not support a regional multivariate model.');
  assert.equal(foundation.panel.pca_performed,false);
  assert.equal(foundation.panel.clustering_performed,false);
  assert.equal(foundation.panel.spatial_autocorrelation_performed,false);
  assert.equal(foundation.results.n_forecast_indicators,0);
  assert.equal(foundation.results.n_projected_series,0);
  assert.equal(foundation.research.causal_effect_status,'not_identified_in_existing_sources');
  assert.equal(foundation.research.financing_status,'published_plan_reconciled_without_consolidation_claim');
  assert.equal(foundation.research.strict_financing_hhi,null);
  assert.ok(foundation.legacy_release_metadata,'Historical research metadata remain available separately.');
  assert.ok(methods.items.every(item=>item.current_status&&item.current_status_label&&item.current_limitations));
  assert.equal(methods.items.length,39);

  for(const candidate of localLinks){
    const clean=candidate.split(/[?#]/,1)[0];
    const resolved=path.resolve(docs,clean);
    assert.ok(resolved===docs||resolved.startsWith(docs+path.sep),'Published link cannot escape the site: '+candidate);
    await fs.access(resolved);
  }
  const result={sources:statistics.sources.length,cells,numeric,usable,excluded,routes:reportCheck.routes,
    source_blocks:coverage.summary.assigned_blocks,tables:expertise.tables.length,figures:expertise.figures.length,
    footnotes:expertise.meta.footnotes,formulas:expertise.meta.formulas,inline_formula_nodes:expertise.meta.inline_formula_nodes,local_links_checked:localLinks.size,
    source_bundles_checked:originalCheck.source_bundles};
  console.log('Validated Transport: '+JSON.stringify(result));
  return result;
}
