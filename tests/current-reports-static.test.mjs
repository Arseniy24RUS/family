import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {projects,completeProjectPages} from '../src/platform/projects.js';
import {sections} from '../src/content/sections.js';
import {loadCurrentReports,validateCurrentReports,renderCurrentReportCard,renderReportDownloadLinks,ORIGINAL_REPORT_LABEL} from '../scripts/current_reports.mjs';

const root=path.resolve(import.meta.dirname,'..');
const publicRoot=path.join(root,'public');
const manifest=await loadCurrentReports(root);
const htmlLinks=html=>[...html.matchAll(/(?:href|src)="([^"]+)"/g)].map(match=>match[1]);
function resolveLocal(link,route){
  const url=new URL(link,'https://example.test/family/'+route);
  if(url.origin!=='https://example.test')return null;
  assert.ok(url.pathname.startsWith('/family/'),'deployment prefix retained: '+link);
  return path.join(publicRoot,decodeURIComponent(url.pathname.slice('/family/'.length)));
}

test('current-report links resolve for every project at root and nested article depths',async()=>{
  assert.equal(manifest.reports.length,12);
  for(const report of manifest.reports){
    for(const [prefix,route] of [['../','research/index.html'],['../../../',`research/projects/${report.project_id}/index.html`]]){
      const html=renderCurrentReportCard(manifest,report.project_id,prefix);
      assert.match(html,/Актуальная редакция экспертизы/);
      assert.ok(html.includes(report.edition_label));
      assert.ok(html.includes(report.pdf.pages+' стр.'));
      for(const link of htmlLinks(html))await fs.access(resolveLocal(link,route));
    }
    const pdf=await fs.readFile(path.join(publicRoot,report.pdf.url));
    assert.equal(pdf.subarray(0,5).toString(),'%PDF-');
    assert.equal(pdf.length,report.pdf.bytes);
    assert.equal(createHash('sha256').update(pdf).digest('hex'),report.pdf.sha256);
    await fs.access(path.join(publicRoot,report.docx.url));
  }
});

test('current-report schema rejects mismatched identity, missing project and unsafe download paths',()=>{
  const bads=[
    data=>data.reports.pop(),
    data=>data.reports[1].project_id=data.reports[0].project_id,
    data=>data.reports[0].pdf.url='https://elsewhere.test/file.pdf',
    data=>data.reports[0].pdf.url='downloads/projects/family/current/../old.pdf',
    data=>data.reports[0].docx.url='downloads/projects/tourism/current/report.docx',
    data=>data.reports[0].pdf.pages=0,
    data=>data.reports[0].edition_date='2025-01-01',
  ];
  for(const mutate of bads){const data=structuredClone(manifest);mutate(data);assert.throws(()=>validateCurrentReports(data));}
  assert.throws(()=>renderReportDownloadLinks(manifest.reports[0],'/'),/prefix/);
  const copy=structuredClone(manifest);copy.reports[0].edition_label='<script>alert(1)</script>';
  const html=renderCurrentReportCard(copy,'family','../');
  assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('&lt;script&gt;'));
});

test('all generated study articles expose current PDF and distinguish their original calculation report',async()=>{
  const pages=[{route:'research/index.html',id:'family'},...sections.map(section=>({route:`research/${section.id}.html`,id:'family'})),{route:'research/projects/family/index.html',id:'family'}];
  for(const [id,specs] of Object.entries(completeProjectPages))for(const spec of specs)pages.push({route:`research/projects/${id}/${spec.id==='overview'?'index':spec.id}.html`,id});
  assert.equal(pages.length,245);
  for(const {route,id} of pages){
    const html=await fs.readFile(path.join(publicRoot,route),'utf8');
    assert.equal((html.match(/data-current-report=/g)||[]).length,1,route);
    assert.ok(html.includes(`data-current-report="${id}"`),route);
    const report=manifest.reports.find(item=>item.project_id===id);
    assert.ok(html.includes(report.pdf.url),route);
    assert.ok(html.includes(report.docx.url),route);
    for(const link of htmlLinks(html).filter(value=>/current-reports\.css|reports\.html|\/current\//.test(value)))await fs.access(resolveLocal(link,route));
    for(const anchor of html.matchAll(/<a\b[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)){
      if(/(?:\/report\/[^/]+\.docx|expertise_2026-05-14\.docx)(?:[?#]|$)/.test(anchor[1]))assert.ok(anchor[2].includes(ORIGINAL_REPORT_LABEL),route+' original report label');
    }
  }
});

test('catalogue has twelve documents, local assets and stable project navigation under /family/',async()=>{
  const route='research/reports.html',html=await fs.readFile(path.join(publicRoot,route),'utf8');
  assert.equal((html.match(/class="report-document"/g)||[]).length,12);
  for(const project of projects){
    const report=manifest.reports.find(item=>item.project_id===project.id);
    assert.ok(html.includes(`id="${project.id}"`));
    assert.ok(html.includes(report.pdf.url));
    assert.ok(html.includes(report.docx.url));
  }
  for(const link of htmlLinks(html)){
    const file=resolveLocal(link,route);
    if(file)await fs.access(file);
  }
  assert.ok(!html.includes('fonts.googleapis.com'));
});
