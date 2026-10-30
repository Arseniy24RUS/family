import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {parseRoute,switchProject} from '../src/platform/routes.js';
import {youthPages,projectHref,getProject} from '../src/platform/projects.js';
import {validateYouthContent,renderReportBlocks} from '../scripts/build_youth.mjs';

const report=JSON.parse(fs.readFileSync(new URL('../public/data/projects/youth_children/expertise.json',import.meta.url),'utf8'));

test('Youth deep links retain their filters, discard legacy archive mode and never expose authors',()=>{
  assert.equal(youthPages.length,21);
  for(const page of youthPages){
    const route=parseRoute(projectHref('youth_children',page.id,{source:'62969',period:'2026-07',r:'77',q:'Москва',mode:'baseline'}));
    assert.deepEqual([route.nationalProject,route.page,route.mode,route.source,route.r,route.q],['youth_children',page.id,'latest','62969','77','Москва']);
  }
  assert.equal(parseRoute('#/projects/youth_children/authors').page,'overview');
  assert.equal(getProject('youth_children').color,'#8265CB');
  assert.equal(getProject('youth_children').hasAuthors,false);
});

test('switching between complete projects preserves page intent and clears incompatible source filters',()=>{
  for(const page of ['map','regions','finance','projections','population','updates']){
    const youth=switchProject(parseRoute('#/'+page+'?source=data_21&r=77'),'youth_children');
    assert.equal(youth,'#/projects/youth_children/'+page);
    assert.equal(switchProject(parseRoute(youth+'?source=62969&r=22'),'family'),'#/'+page);
  }
  assert.equal(switchProject(parseRoute('#/projects/youth_children/map?source=62969'),'tourism'),'#/projects/tourism/map');
  assert.equal(switchProject(parseRoute('#/projects/youth_children/map?source=62969'),'efficient_transport'),'#/projects/efficient_transport/map');
  assert.equal(switchProject(parseRoute('#/projects/youth_children/map?source=62969'),'international_export'),'#/projects/international_export/map');
  assert.equal(switchProject(parseRoute('#/projects/youth_children/methods?q=text'),'personnel'),'#/projects/personnel/methods');
});

test('every Youth report page has valid evidence and the complete referenced figure set',()=>{
  const checked=validateYouthContent(report);
  assert.deepEqual([checked.routes,checked.sources,checked.figures],[21,84,17]);
  const blocks=Object.values(report.pages).flatMap(p=>p.blocks);
  assert.equal(blocks.filter(b=>b.type==='table').length,12);
  assert.equal(blocks.filter(b=>b.type==='figure_ref').length,17);
  assert.equal(blocks.filter(b=>b.type==='formula'&&Number.isInteger(b.sourceBlock)).length,4);
  assert.ok(report.meta.source_pages>=90);
  for(const page of Object.values(report.pages))assert.doesNotThrow(()=>renderReportBlocks(page,report));
});

test('static research rejects unsafe references and escapes report prose without executing markup',()=>{
  const invalid=structuredClone(report);invalid.sources[0].url='javascript:alert(1)';
  assert.throws(()=>validateYouthContent(invalid),/Unsafe/);
  const rendered=renderReportBlocks({blocks:[{type:'paragraph',text:'<script>alert(1)</script> & источник'}]},report);
  assert.ok(rendered.includes('&lt;script&gt;'));
  assert.ok(!rendered.includes('<script>'));
});
