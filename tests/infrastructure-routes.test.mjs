import test from 'node:test';
import assert from 'node:assert/strict';
import {projects,infrastructurePages,projectHref,getProject} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';

test('infrastructure completes its existing project slot with twenty-one routes',()=>{
 assert.equal(projects.length,12);assert.equal(infrastructurePages.length,21);assert.equal(projects[5].id,'life_infrastructure');
 for(const page of infrastructurePages){const route=parseRoute(projectHref('life_infrastructure',page.id,{source:'40466',frequency:'annual',year:'2024',mode:'archive',finSource:'regional'}));assert.equal(route.nationalProject,'life_infrastructure');assert.equal(route.page,page.id);assert.equal(route.mode,'latest');assert.equal(route.source,'40466');assert.equal(route.finSource,'regional');}
 assert.equal(getProject('life_infrastructure').color,'#45B97C');assert.equal(getProject('life_infrastructure').hasAuthors,false);assert.equal(parseRoute('#/projects/life_infrastructure/authors').page,'overview');assert.equal(projects.filter(p=>p.hasAuthors).length,1);
});
test('switching infrastructure pages preserves intent while discarding foreign source filters',()=>{
 for(const to of ['family','youth_children','personnel','long_active_life','health_technologies'])for(const page of ['targets','finance','map','population','texts','updates'])assert.equal(switchProject(parseRoute(projectHref('life_infrastructure',page,{source:'40466',year:'2024',fp:'И2'})),to),projectHref(to,page));
});
