import test from 'node:test';
import assert from 'node:assert/strict';
import {projects,environmentPages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';

test('environment completes its existing slot with 21 routes and official colour',()=>{
 assert.equal(projects.length,12);assert.equal(environmentPages.length,21);assert.equal(new Set(environmentPages.map(p=>p.id)).size,21);
 for(const page of environmentPages){const route=parseRoute(projectHref('environment',page.id,{source:'62792',frequency:'annual',year:'2025',mode:'archive',finSource:'regional',geography:'project_territory'}));assert.equal(route.nationalProject,'environment');assert.equal(route.page,page.id);assert.equal(route.mode,'latest');assert.equal(route.source,'62792');assert.equal(route.finSource,'regional');assert.equal(route.geography,'project_territory');}
 assert.equal(getProject('environment').color,'#87C879');assert.equal(getProject('environment').hasAuthors,false);assert.equal(parseRoute('#/projects/environment/authors').page,'overview');assert.equal(projects.filter(p=>p.hasAuthors).length,1);
});
test('switching projects preserves a valid page and discards unrelated source parameters',()=>{
 for(const to of ['family','youth_children','personnel','long_active_life','health_technologies','life_infrastructure'])for(const page of ['targets','finance','map','population','texts','updates'])assert.equal(switchProject(parseRoute(projectHref('environment',page,{source:'62792',year:'2025',fp:'Ч2',airSource:'62863'})),to),projectHref(to,page));
});
test('laboratory multiline input and air source state round-trip without loss',()=>{
 const exposureRows='А;1000;5;9\nБ;3000;;1',params={tool:'exposure',exposureRows,airSource:'62863',airPeriod:'latest'};
 const state=parseRoute(projectHref('environment','lab',params));for(const [key,value] of Object.entries(params))assert.equal(state[key],value);
});
