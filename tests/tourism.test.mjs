import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {projects,tourismPages,completeProjectPages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject,familyPages} from '../src/platform/routes.js';
import {validateTourismContent,buildTourismFoundation} from '../scripts/build_tourism.mjs';

const ROOT=path.resolve(import.meta.dirname,'..');
const read=async relative=>JSON.parse(await fs.readFile(path.join(ROOT,relative),'utf8'));
const expectedReportHash='bc1950af5a03bdfa2609317a581f06af4fe5ef3f714176e3f8947e926401aac5';
const prefix='public/data/projects/tourism/';

test('tourism preserves its existing project identity, all routes and the family-only author section',()=>{
  assert.equal(projects.length,12);
  assert.equal(tourismPages.length,21);
  assert.equal(new Set(tourismPages.map(page=>page.id)).size,21);
  assert.equal(completeProjectPages.tourism,tourismPages);
  assert.equal(getProject('tourism').color,'#208076');
  assert.equal(getProject('tourism').hasAuthors,false);
  assert.deepEqual(projects.filter(project=>project.hasAuthors).map(project=>project.id),['family']);
  for(const page of tourismPages){
    const state=parseRoute(projectHref('tourism',page.id,{source:'62902',year:'2025',frequency:'annual',mode:'archive'}));
    assert.equal(state.nationalProject,'tourism');
    assert.equal(state.page,page.id);
    assert.equal(state.source,'62902');
    assert.equal(state.mode,'latest');
  }
  assert.equal(parseRoute('#/projects/tourism/authors').page,'overview');
  for(const page of familyPages)assert.equal(parseRoute('#/'+page).page,page);
});

test('project switching keeps the page while removing source and scenario assumptions from tourism',()=>{
  for(const target of ['family','youth_children','personnel','long_active_life','health_technologies','life_infrastructure','environment','competitive_economy','data_economy']){
    for(const page of ['targets','finance','map','population','texts','updates']){
      const state=parseRoute(projectHref('tourism',page,{source:'62902',year:'2025',fp:'П3',occupancy:'0'}));
      assert.equal(switchProject(state,target),projectHref(target,page));
    }
  }
  const state=parseRoute(projectHref('tourism','lab',{occupancy:'0',capacity:'0'}));
  assert.equal(state.occupancy,'0');
  assert.equal(state.capacity,'0');
});

test('the original report, its illustrations and all numbered research material are retained',async()=>{
  const expertise=await read(prefix+'expertise.json');
  const validated=validateTourismContent(expertise);
  assert.equal(validated.routes,21);
  assert.equal(validated.sources,131);
  assert.equal(validated.figures,12);
  assert.equal(expertise.meta.source_docx_sha256,expectedReportHash);
  const report=await fs.readFile(path.join(ROOT,'public',expertise.meta.report_url));
  assert.equal(crypto.createHash('sha256').update(report).digest('hex'),expectedReportHash);
  assert.equal(expertise.tables.length,16);
  assert.equal(expertise.meta.footnotes,130);
  assert.equal(expertise.meta.formulas,7);
  const tableIds=Object.values(expertise.pages).flatMap(page=>page.blocks.filter(block=>block.type==='table').map(block=>block.id));
  assert.equal(new Set(tableIds).size,16);
  assert.deepEqual(new Set(tableIds),new Set(expertise.tables.map(table=>table.id)));
  for(const figure of expertise.figures){
    const bytes=await fs.readFile(path.join(ROOT,'public',figure.url));
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),figure.original_sha256);
  }
  const coverage=await read('public/'+expertise.meta.coverage_url);
  assert.equal(coverage.summary.substantive_blocks,373);
  assert.equal(coverage.summary.assigned_blocks,373);
  assert.deepEqual(coverage.summary.unmapped_substantive_blocks,[]);
  assert.deepEqual(coverage.summary.duplicate_assignments,[]);
  for(const key of ['report_url','markdown_url','html_url','extract_url','coverage_url'])await fs.access(path.join(ROOT,'public',expertise.meta[key]));
});

test('tourism validation rejects an unresolved table-cell citation',async()=>{
  const expertise=await read(prefix+'expertise.json');
  const table=Object.values(expertise.pages).flatMap(page=>page.blocks).find(block=>block.type==='table');
  table.cellSourceIds=[[['missing_source']]];
  assert.throws(()=>validateTourismContent(expertise),/unknown source/);
});

test('current research metadata cannot inherit unverified forecast or multivariate claims',async()=>{
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),'tourism-metadata-'));
  try{
    const target=path.join(temp,'public/data/projects/tourism');
    await fs.mkdir(target,{recursive:true});
    for(const name of ['foundation','expertise','methods','statistics','analytics','documentary']){
      await fs.copyFile(path.join(ROOT,prefix,name+'.json'),path.join(target,name+'.json'));
    }
    await fs.copyFile(path.join(ROOT,'package.json'),path.join(temp,'package.json'));
    const existing=JSON.parse(await fs.readFile(path.join(target,'foundation.json'),'utf8'));
    const statistics=JSON.parse(await fs.readFile(path.join(target,'statistics.json'),'utf8'));
    const coverage=statistics.coverage;
    const result=await buildTourismFoundation(temp);
    assert.equal(result.author_expertise_status,'published');
    assert.equal(result.results.n_forecast_indicators,0);
    assert.equal(result.results.n_projected_series,0);
    assert.equal(result.panel.pca_performed,false);
    assert.equal(result.panel.clustering_performed,false);
    assert.equal(result.panel.spatial_autocorrelation_performed,false);
    assert.equal(result.research.causal_effect_status,'not_identified_in_existing_sources');
    assert.equal(result.research.strict_financing_hhi,null);
    assert.equal(result.research.financing_status,'arithmetic_row_sum_without_consolidated_resource_claim');
    assert.equal(result.registry.n_registry,coverage.registry_indicators);
    assert.equal(result.registry.original_catalog_numeric_indicators,coverage.catalog_indicators_with_numeric??coverage.indicators_with_numeric);
    assert.equal(result.registry.n_with_numeric,coverage.semantically_available_indicators??coverage.indicators_with_numeric);
    assert.equal(result.registry.n_numeric_sources,coverage.numeric_sources);
    assert.equal(result.registry.n_unique_cells,coverage.observations);
    assert.equal(result.registry.n_usable,coverage.usable_observations);
    assert.ok(result.registry.n_usable<=result.registry.n_numeric);
    assert.equal(result.method_summary.total,39);
    assert.ok(result.sections.every(section=>section.publication_status==='published'));
    if(existing.legacy_release_metadata)assert.deepEqual(result.legacy_release_metadata,existing.legacy_release_metadata);
    else assert.deepEqual(result.legacy_release_metadata.original,existing);
    const methods=JSON.parse(await fs.readFile(path.join(target,'methods.json'),'utf8'));
    assert.ok(methods.items.every(item=>item.current_status&&item.current_status_label&&item.current_limitations));
    for(const id of ['pca','kmeans','isolation_forest'])assert.match(methods.items.find(item=>item.method_id===id).current_status,/^not_applicable/);
  }finally{
    await fs.rm(temp,{recursive:true,force:true});
  }
});
