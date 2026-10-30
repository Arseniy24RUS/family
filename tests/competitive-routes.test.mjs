import test from 'node:test';
import assert from 'node:assert/strict';
import {projects,competitivePages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';

test('competitive economy completes its existing registry slot with 21 current-only pages',()=>{
 assert.equal(projects.length,12);assert.equal(competitivePages.length,21);assert.equal(new Set(competitivePages.map(p=>p.id)).size,21);
 for(const page of competitivePages){const r=parseRoute(projectHref('competitive_economy',page.id,{source:'62979',frequency:'annual',year:'2025',mode:'archive',finSource:'extra_budget',geography:'regional'}));assert.equal(r.nationalProject,'competitive_economy');assert.equal(r.page,page.id);assert.equal(r.mode,'latest');assert.equal(r.source,'62979');assert.equal(r.finSource,'extra_budget');assert.equal(r.geography,'regional');}
 assert.equal(getProject('competitive_economy').color,'#D86464');assert.equal(getProject('competitive_economy').hasAuthors,false);assert.equal(parseRoute('#/projects/competitive_economy/authors').page,'overview');assert.equal(projects.filter(p=>p.hasAuthors).length,1);
});
test('switching completed studies preserves page and removes economics source parameters',()=>{
 for(const to of ['family','youth_children','personnel','long_active_life','health_technologies','life_infrastructure','environment'])for(const page of ['targets','finance','map','population','texts','updates'])assert.equal(switchProject(parseRoute(projectHref('competitive_economy',page,{source:'62979',year:'2025',fp:'Э1',priceIndex:'108'})),to),projectHref(to,page));
});
test('economic assumptions, zeros and signed values survive route round trip',()=>{
 const params={tool:'did',treatedBefore:'-5',treatedAfter:'0',comparisonBefore:'2.5',comparisonAfter:'3',priceIndex:'108',fp:'Э3'};
 const state=parseRoute(projectHref('competitive_economy','lab',params));for(const [k,v]of Object.entries(params))assert.equal(state[k],v);
});
