/** Validate Personnel source identity, periods, analytical views and report coverage. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {personnelPages} from '../src/platform/projects.js';
import {validatePersonnelContent} from './build_personnel.mjs';

const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const amount=value=>{
  assert.match(String(value),/^-?\d+(\.\d{1,2})?$/,'Exact financial amounts retain hundredths of a thousand rubles.');
  const [integer,fraction='']=String(value).split('.');
  return BigInt(integer)*100n+BigInt(fraction.padEnd(2,'0'))*(integer.startsWith('-')?-1n:1n);
};

export async function validatePersonnel(root=path.resolve(import.meta.dirname,'..')){
  const docs=path.join(root,'docs'),prefix='data/projects/personnel/';
  const bytes=async rel=>{
    assert.ok(!rel.split('/').includes('..')&&!path.isAbsolute(rel),'Safe published path: '+rel);
    return fs.readFile(path.join(docs,rel));
  };
  const read=async rel=>JSON.parse(await bytes(rel));
  const [stats,analytics,report,documentary,context]=await Promise.all(['statistics','analytics','expertise','documentary','context'].map(name=>read(prefix+name+'.json')));
  const config=JSON.parse(await fs.readFile(path.join(root,'scripts/personnel_emiss_sources.json'),'utf8'));
  const checked=validatePersonnelContent(report);
  assert.equal(stats.project_id,'personnel');
  assert.equal(analytics.project_id,'personnel');
  assert.deepEqual(new Set(stats.sources.map(s=>s.id)),new Set(config.sources.map(s=>s.indicator_id)));
  const allRows=new Map();
  let cells=0,numbers=0,excluded=0,equivalents=0,annual=0;
  for(const source of stats.sources){
    const raw=await bytes(prefix+'series/'+source.id+'.json');
    const packet=JSON.parse(raw),provenance=await read(prefix+'provenance/'+source.id+'.json');
    assert.equal(packet.project_id,'personnel');
    assert.equal(packet.source_id,source.id);assert.equal(packet.unit,source.unit);
    assert.equal(provenance.published_sha256,hash(raw));
    assert.equal(packet.observations.length,source.observation_count);
    assert.equal(provenance.input_sha256,hash(await bytes(provenance.input_bundle)));
    const ids=new Set();
    for(const row of packet.observations){
      assert.equal(row.source_id,source.id);
      assert.ok(!ids.has(row.id),'Unique Personnel observation: '+row.id);ids.add(row.id);
      assert.ok(row.value===null||Number.isFinite(row.value));
      assert.equal(row.analytical_value,row.excluded?null:row.value);
      assert.match(row.period_end,/^\d{4}-\d{2}-\d{2}$/);
      assert.equal(row.geo_level,'national','Regional context is never an EMISS project observation.');
      assert.notEqual(row.frequency,'annual_equivalent','An annual equivalent is a reference, not a new observation.');
      allRows.set(source.id+':'+row.id,row);
      cells++;if(row.value!==null)numbers++;if(row.excluded&&row.value!==null)excluded++;
      if(row.frequency==='annual'&&!row.excluded&&row.value!==null)annual++;
    }
    for(const equivalent of source.annual_equivalents||[]){
      const original=packet.observations.find(r=>r.id===equivalent.reference_observation_id);
      assert.ok(original,'Annual equivalent references a real source observation.');
      assert.equal(equivalent.independent_observation,false);
      assert.equal(equivalent.frequency,'annual_equivalent');
      assert.equal(equivalent.original_period,original.period);
      assert.equal(equivalent.original_frequency,original.frequency);
      assert.equal(equivalent.value,original.value);
      assert.ok(equivalent.annual_basis&&equivalent.methodology_order&&equivalent.methodology_url);
      assert.ok(source.annual_equivalence_rule);
      assert.ok(original.period.endsWith(source.annual_equivalence_rule.suffix));
      assert.ok(source.annual_equivalence_rule.frequencies.includes(original.frequency));
      equivalents++;
    }
    if(source.downloads.current_raw){
      assert.equal(source.downloads.current_raw,provenance.current_raw);
      assert.equal(hash(await bytes(source.downloads.current_raw)),provenance.current_raw_sha256);
    }
  }
  assert.equal(cells,analytics.coverage.observations);
  assert.equal(numbers,analytics.coverage.numeric_observations);
  assert.equal(excluded,analytics.coverage.excluded_numeric_observations);
  assert.equal(annual,analytics.coverage.independent_annual_national_facts);
  assert.equal(equivalents,analytics.coverage.annual_equivalent_references);
  for(const comparison of analytics.target_comparisons){
    const original=allRows.get(comparison.source_id+':'+comparison.reference_observation_id);
    assert.ok(original,'Comparison references an original observation.');
    assert.equal(original.value,comparison.fact_value);
    assert.ok(Math.abs(comparison.difference-(comparison.fact_value-comparison.target_value))<1e-8);
    assert.ok(comparison.difference_unit);
    assert.equal(comparison.annual_comparison_eligible,['annual','annual_equivalent'].includes(comparison.fact_frequency));
    if(comparison.fact_frequency==='annual')assert.equal(original.frequency,'annual');
    if(comparison.fact_frequency==='annual_equivalent'){
      const source=stats.sources.find(s=>s.id===comparison.source_id);
      assert.ok(source.annual_equivalents.some(r=>r.reference_observation_id===original.id&&r.year===comparison.target_year));
      assert.ok(comparison.annual_basis&&comparison.methodology_url);
    }
    assert.equal(comparison.formal_attainment_eligible,false,'Selected later passport editions are not proof of original-year official fulfilment.');
    assert.equal(comparison.difference_unit,comparison.source_id==='62884'?'пункты индекса':'п.п.');
  }
  assert.equal(context.role,'pre_project_context');assert.equal(context.year,2024);
  assert.equal(context.national_value_origin,'published_national_not_regional_average');
  assert.equal(context.source_hash_kind,'preserved_table_excerpt_not_pdf');
  assert.equal(context.regions.length,85);
  assert.equal(new Set(context.regions.map(r=>r.code)).size,85);
  const geometry=await read('data/map.json'),mapIds=new Set(geometry.features.map(r=>r.id));
  for(const region of context.regions){assert.ok(mapIds.has(region.map_id));assert.ok(Number.isFinite(region.value));assert.equal(region.role,'pre_project_context');}
  for(const source of context.source_provenance.files){assert.equal(hash(await bytes(source.path)),source.sha256);}
  assert.deepEqual(analytics.context,context);
  const finance=documentary.finance;
  const total=finance.projects.reduce((sum,p)=>sum+amount(p.totalThousandRub),0n);
  assert.equal(total,amount(finance.totalThousandRub));
  assert.equal(total-amount(finance.nationalThousandRub),amount(finance.differenceThousandRub));
  for(const project of finance.projects){
    assert.equal(project.years.reduce((sum,y)=>sum+amount(y.amountThousandRub),0n),amount(project.totalThousandRub));
    assert.equal(project.fullYears.reduce((sum,y)=>sum+amount(y.amountThousandRub),0n),amount(project.fullHorizonThousandRub));
    assert.equal(amount(project.totalThousandRub)+amount(project.laterThousandRub),amount(project.fullHorizonThousandRub));
  }
  const targets=documentary.targets;
  let targetCells=0,targetNumbers=0;
  for(const target of targets.items)for(const value of Object.values(target.years)){
    targetCells++;assert.ok(value===null||Number.isFinite(value));if(value!==null)targetNumbers++;
  }
  assert.equal(targets.target_cells,targetCells);assert.equal(targets.numeric_targets,targetNumbers);
  assert.equal(targets.missing_targets,targetCells-targetNumbers);
  for(const source of documentary.sources)assert.equal(hash(await bytes(source.download_path)),source.sha256);
  assert.equal(hash(await bytes(report.meta.report_url)),report.meta.source_docx_sha256);
  const coverage=await read('downloads/projects/personnel/report/coverage_manifest.json');
  assert.equal(coverage.summary.assigned_blocks,coverage.summary.substantive_blocks);
  assert.deepEqual(coverage.summary.unmapped_substantive_blocks,[]);
  assert.deepEqual(coverage.summary.duplicate_assignments,[]);
  assert.ok((await bytes(prefix+'documentary.json')).length<2*1024*1024,'Full text contexts load on demand.');
  for(const item of documentary.text.documentFiles)await bytes(item.path.replace(/^\.\//,''));
  for(const page of personnelPages)await bytes('research/projects/personnel/'+(page.id==='overview'?'index.html':page.id+'.html'));
  console.log(`Validated Personnel: ${stats.sources.length} sources, ${cells} original cells, ${equivalents} annual references, ${context.regions.length} context regions, ${checked.routes} report pages.`);
  return {sources:stats.sources.length,cells,numbers,excluded,annual,equivalents,context_regions:context.regions.length,routes:checked.routes};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await validatePersonnel();
