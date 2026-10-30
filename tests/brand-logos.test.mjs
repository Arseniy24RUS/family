import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {projects} from '../src/platform/projects.js';

const read=file=>fs.readFileSync(new URL(file,import.meta.url));
const sha=value=>createHash('sha256').update(value).digest('hex');

test('all twelve official logos preserve the verified page-47 paths and have no runtime dependencies',()=>{
  const manifest=JSON.parse(read('../public/assets/brand/manifest.json'));
  assert.deepEqual(manifest,JSON.parse(read('../documentation/BRAND_LOGOS_PROVENANCE.json')));
  assert.equal(manifest.source.physical_page,47);
  assert.equal(manifest.source.printed_page,47);
  assert.equal(manifest.source.sha256,'eb480ed2200e61c56cdec8f98299b6594a7a0766bf6ae88c8bd864a5552e3485');
  assert.equal(manifest.logos.length,projects.length);
  for(const project of projects){
    const record=manifest.logos.find(logo=>logo.id===project.id);
    assert.ok(record,project.id);
    const bytes=read('../public/assets/brand/'+record.file),svg=bytes.toString();
    assert.equal(sha(bytes),record.sha256,project.id);
    assert.equal(bytes.length,record.bytes);
    assert.equal(record.project_color,project.color);
    assert.ok(svg.toLowerCase().includes(`fill="${record.brand_color.toLowerCase()}"`));
    assert.ok(!/<(?:image|text|rect|script|foreignObject)\b|(?:xlink:)?href=/i.test(svg));
    const paths=[...svg.matchAll(/<path\s+([^>]+)\/?\>/g)].map(match=>Object.fromEntries([...match[1].matchAll(/([\w:-]+)="([^"]*)"/g)].map(attr=>[attr[1],attr[2]]).sort(([a],[b])=>a.localeCompare(b))));
    assert.equal(paths.length,record.path_count);
    assert.equal(sha(JSON.stringify(paths)),record.source_path_attributes_sha256,project.id+' source geometry');
    const viewbox=svg.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
    const [x0,y0,x1,y1]=record.source_bbox_points;
    assert.ok(Math.abs(viewbox[0]-(x0-2))<1e-6);
    assert.ok(Math.abs(viewbox[1]-(y0-2))<1e-6);
    assert.ok(Math.abs(viewbox[2]-(x1-x0+4))<1e-6);
    assert.ok(Math.abs(viewbox[3]-(y1-y0+4))<1e-6);
  }
});
