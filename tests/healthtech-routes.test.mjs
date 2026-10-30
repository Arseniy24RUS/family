import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {projects,healthtechPages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';

test('Health technologies extends the existing eleven projects with all twenty-one routes',()=>{
  assert.equal(projects.length,12);
  assert.equal(healthtechPages.length,21);
  for(const page of healthtechPages){const route=parseRoute(projectHref('health_technologies',page.id,{source:'62986',frequency:'annual',year:'2025',frame:'budget_bill',mode:'archive'}));assert.deepEqual([route.nationalProject,route.page,route.mode,route.source,route.frequency,route.year,route.frame],['health_technologies',page.id,'latest','62986','annual','2025','budget_bill']);}
  assert.equal(parseRoute('#/projects/health_technologies/authors').page,'overview');
  assert.equal(getProject('health_technologies').hasAuthors,false);
  assert.equal(projects.filter(p=>p.hasAuthors).length,1);
});

test('switching between completed studies retains page intent and clears foreign filters',()=>{
  for(const from of ['family','youth_children','personnel','long_active_life','health_technologies'])for(const to of ['family','youth_children','personnel','long_active_life','health_technologies'])for(const page of ['targets','finance','map','population','texts','updates'])assert.equal(switchProject(parseRoute(projectHref(from,page,{source:'62986',year:'2025',fp:'С1'})),to),projectHref(to,page));
});

test('page-47 logo has verified provenance while the established project palette and prior asset remain intact',()=>{
  const read=p=>fs.readFileSync(new URL(p,import.meta.url)),m=JSON.parse(read('../public/assets/brand/manifest.json')),record=m.logos.find(r=>r.id==='health_technologies'),previous=JSON.parse(read('../documentation/BRAND_LOGOS_PREVIOUS_ASSETS.json')).logos.find(r=>r.id==='health_technologies'),src=read('../public/downloads/projects/health_technologies/brand/official_logo_original.svg'),rendered=read('../public/assets/brand/health_technologies.svg'),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
  assert.equal(record.brand_color,'#008BBF');
  assert.equal(getProject('health_technologies').color,'#0A8BBF');
  assert.equal(record.project_color,getProject('health_technologies').color);
  assert.equal(sha(src),previous.source_sha256);
  assert.equal(sha(rendered),record.sha256);
  assert.equal(record.source_sha256,m.source.sha256);
  assert.equal(record.source_page,47);
  assert.equal(record.geometry_unchanged,true);
  const paths=[...rendered.toString().matchAll(/<path\s+([^>]+)\/?\>/g)].map(match=>Object.fromEntries([...match[1].matchAll(/([\w:-]+)="([^"]*)"/g)].map(attr=>[attr[1],attr[2]]).sort(([a],[b])=>a.localeCompare(b))));
  assert.equal(paths.length,record.path_count);
  assert.equal(sha(JSON.stringify(paths)),record.source_path_attributes_sha256);
});
