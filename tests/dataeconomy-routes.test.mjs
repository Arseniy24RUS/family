import test from 'node:test';
import assert from 'node:assert/strict';
import {projects,dataeconomyPages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';

test('data economy completes its existing registry slot with21 current pages and official palette',()=>{
 assert.equal(projects.length,12);assert.equal(dataeconomyPages.length,21);assert.equal(new Set(dataeconomyPages.map(p=>p.id)).size,21);
 for(const page of dataeconomyPages){const r=parseRoute(projectHref('data_economy',page.id,{source:'62766',frequency:'monthly',year:'2026',mode:'archive',finSource:'extra_budget',geography:'regional'}));assert.equal(r.nationalProject,'data_economy');assert.equal(r.page,page.id);assert.equal(r.mode,'latest');assert.equal(r.source,'62766');assert.equal(r.finSource,'extra_budget');assert.equal(r.geography,'regional');}
 assert.equal(getProject('data_economy').color,'#4224FD');assert.equal(getProject('data_economy').hasAuthors,false);assert.equal(parseRoute('#/projects/data_economy/authors').page,'overview');assert.equal(projects.filter(p=>p.hasAuthors).length,1);
});
test('switching a completed project keeps page intent and clears digital source assumptions',()=>{
 for(const to of ['family','youth_children','personnel','long_active_life','health_technologies','life_infrastructure','environment','competitive_economy'])for(const page of ['targets','finance','map','population','texts','updates'])assert.equal(switchProject(parseRoute(projectHref('data_economy',page,{source:'62766',year:'2026',fp:'Ц4',annualServices:'10000'})),to),projectHref(to,page));
});
test('digital calculator inputs and explicit zeros survive route roundtrip',()=>{
 const params={tool:'cascade',eligible:'1000',accessible:'0',started:'0',completed:'0',fp:'Ц4'};
 const state=parseRoute(projectHref('data_economy','lab',params));for(const[k,v]of Object.entries(params))assert.equal(state[k],v);
});
