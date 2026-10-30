import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {parseRoute,switchProject} from '../src/platform/routes.js';
import {longlifePages,projectHref,getProject} from '../src/platform/projects.js';
import {validateLonglifeContent} from '../scripts/build_longlife.mjs';
import {renderReportBlocks} from '../scripts/build_research_pages.mjs';

test('Longlife supports every research route and preserves source and regional filters',()=>{
  assert.equal(longlifePages.length,21);
  for(const page of longlifePages){
    const route=parseRoute(projectHref('long_active_life',page.id,{source:'62954',period:'2026-09',r:'77',q:'наблюдение',mode:'baseline'}));
    assert.deepEqual([route.nationalProject,route.page,route.mode,route.source,route.r,route.q],['long_active_life',page.id,'latest','62954','77','наблюдение']);
  }
  assert.equal(parseRoute('#/projects/long_active_life/authors').page,'overview');
  assert.equal(getProject('long_active_life').color,'#D9124A');
  assert.equal(getProject('long_active_life').hasAuthors,false);
});

test('all four complete projects share page intent without sharing foreign source filters',()=>{
  const ids=['family','youth_children','personnel','long_active_life'];
  for(const from of ids)for(const to of ids){
    for(const page of ['map','targets','finance','texts','projections','population','updates']){
      const state=parseRoute(projectHref(from,page,{source:'62954',r:'77',q:'здоровье'}));
      assert.equal(switchProject(state,to),projectHref(to,page));
    }
  }
  assert.equal(switchProject(parseRoute('#/projects/long_active_life/structure'),'personnel'),'#/projects/personnel/structure');
  assert.equal(switchProject(parseRoute('#/projects/long_active_life/structure'),'family'),'#/overview');
  assert.equal(switchProject(parseRoute('#/projects/long_active_life/map?source=62954'),'tourism'),'#/projects/tourism/map');
  assert.equal(switchProject(parseRoute('#/projects/long_active_life/map?source=62954'),'efficient_transport'),'#/projects/efficient_transport/map');
  assert.equal(switchProject(parseRoute('#/projects/long_active_life/map?source=62954'),'international_export'),'#/projects/international_export/map');
});

test('Longlife preserves the supplied report tables, figures, formulas and source identity',()=>{
  const report=JSON.parse(fs.readFileSync(new URL('../public/data/projects/long_active_life/expertise.json',import.meta.url),'utf8'));
  const checked=validateLonglifeContent(report);
  assert.deepEqual([checked.routes,checked.sources,checked.figures],[21,138,18]);
  const blocks=Object.values(report.pages).flatMap(page=>page.blocks);
  assert.equal(blocks.filter(block=>block.type==='table').length,14);
  assert.equal(blocks.filter(block=>block.type==='figure_ref').length,18);
  assert.equal(blocks.filter(block=>block.type==='formula'&&Number.isInteger(block.sourceBlock)).length,8);
  assert.equal(report.meta.source_docx_sha256,'5685d539722553bd90da5f3db190e663e5640129bc4bd8443258e9907d5de72b');
  for(const page of Object.values(report.pages))assert.doesNotThrow(()=>renderReportBlocks(page,report));
  const invalid=structuredClone(report);
  invalid.meta.source_clarifications=[{route:'methods',text:'Уточнение',source_url:'javascript:alert(1)'}];
  assert.throws(()=>validateLonglifeContent(invalid),/Unsafe research clarification URL/);
});
