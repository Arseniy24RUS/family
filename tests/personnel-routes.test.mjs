import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {parseRoute,switchProject} from '../src/platform/routes.js';
import {personnelPages,projectHref,getProject} from '../src/platform/projects.js';
import {validatePersonnelContent} from '../scripts/build_personnel.mjs';
import {renderReportBlocks,validateResearchContent} from '../scripts/build_research_pages.mjs';

const report=JSON.parse(fs.readFileSync(new URL('../public/data/projects/personnel/expertise.json',import.meta.url),'utf8'));

test('Personnel deep links retain source filters and have no archive or authors route',()=>{
  assert.equal(personnelPages.length,21);
  for(const page of personnelPages){
    const route=parseRoute(projectHref('personnel',page.id,{source:'62907',period:'2025',r:'77',q:'обучение',mode:'baseline'}));
    assert.deepEqual([route.nationalProject,route.page,route.mode,route.source,route.r,route.q],['personnel',page.id,'latest','62907','77','обучение']);
  }
  assert.equal(parseRoute('#/projects/personnel/authors').page,'overview');
  assert.equal(getProject('personnel').color,'#CF4520');
  assert.equal(getProject('personnel').hasAuthors,false);
});

test('page intent survives switching all three completed projects while their filters are cleared',()=>{
  for(const from of ['family','youth_children','personnel'])for(const to of ['family','youth_children','personnel']){
    for(const page of ['map','targets','finance','texts','projections','population','updates']){
      const state=parseRoute(projectHref(from,page,{source:'62907',q:'Кадры',r:'77'}));
      assert.equal(switchProject(state,to),projectHref(to,page));
    }
  }
  assert.equal(switchProject(parseRoute('#/projects/personnel/structure'),'youth_children'),'#/projects/youth_children/structure');
  assert.equal(switchProject(parseRoute('#/projects/personnel/structure'),'family'),'#/overview');
  assert.equal(switchProject(parseRoute('#/projects/personnel/map?source=62907'),'tourism'),'#/projects/tourism/map');
  assert.equal(switchProject(parseRoute('#/projects/personnel/map?source=62907'),'efficient_transport'),'#/projects/efficient_transport/map');
  assert.equal(switchProject(parseRoute('#/projects/personnel/map?source=62907'),'international_export'),'#/projects/international_export/map');
});

test('Personnel report retains all source figures, tables, equations and notes',()=>{
  const checked=validatePersonnelContent(report);
  assert.deepEqual([checked.routes,checked.sources,checked.figures],[21,113,14]);
  const blocks=Object.values(report.pages).flatMap(p=>p.blocks);
  assert.equal(blocks.filter(b=>b.type==='table').length,13);
  assert.equal(blocks.filter(b=>b.type==='figure_ref').length,14);
  assert.equal(blocks.filter(b=>b.type==='formula'&&Number.isInteger(b.sourceBlock)).length,6);
  assert.equal(report.meta.source_docx_sha256,'d459f1011cf3525100bc800e2d71f473bf49ec7c5cf34f85a552c428c762299b');
  for(const page of Object.values(report.pages))assert.doesNotThrow(()=>renderReportBlocks(page,report));
});

test('shared static renderer rejects foreign project identity and unsafe source URLs',()=>{
  assert.throws(()=>validateResearchContent(report,'youth_children',personnelPages),/identity/);
  const invalid=structuredClone(report);invalid.sources[0].url='javascript:alert(1)';
  assert.throws(()=>validatePersonnelContent(invalid),/Unsafe/);
  const rendered=renderReportBlocks({blocks:[{type:'paragraph',text:'<img src=x onerror=alert(1)> & проверка'}]},report);
  assert.ok(rendered.includes('&lt;img'));
  assert.ok(!rendered.includes('<img'));
});
