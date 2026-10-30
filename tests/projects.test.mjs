import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {projects,projectHref} from '../src/platform/projects.js';
import {parseRoute,switchProject} from '../src/platform/routes.js';
import {buildPublications,safeSourceUrl,validateExpertise} from '../scripts/build_projects.mjs';

const expectedProjects=['family','long_active_life','youth_children','tourism','personnel','life_infrastructure','efficient_transport','environment','international_export','data_economy','competitive_economy','health_technologies'];
const legacyFamilyPages=['overview','framework','logic','audit','targets','map','regions','finance','network','texts','domains','causal','proposals','lab','explorer','library','updates','projections','population','authors'];

test('all twelve national projects are selectable; authors belong only to Family',()=>{
  assert.deepEqual(projects.map(project=>project.id),expectedProjects);
  assert.equal(new Set(projects.map(project=>project.id)).size,12);
  assert.deepEqual(projects.filter(project=>project.hasAuthors).map(project=>project.id),['family']);
  for(const project of projects){
    assert.ok(project.name.trim()&&project.short.trim());
    assert.match(project.color,/^#[0-9a-f]{6}$/i);
    assert.equal(parseRoute(projectHref(project.id)).nationalProject,project.id);
  }
});

test('all twenty existing Family deep links retain their destinations and federal-project query',()=>{
  for(const page of legacyFamilyPages){
    const state=parseRoute('#/'+page+'?project=family_support&source=data_21&r=77');
    assert.equal(state.nationalProject,'family',page);
    assert.equal(state.page,page,page);
    assert.equal(state.project,'family_support',page);
    assert.equal(state.source,'data_21',page);
    assert.equal(state.r,'77',page);
  }
});

test('path identity is authoritative and saved baseline links use the current statistical layer',()=>{
  const state=parseRoute('#/map?project=family_support&nationalProject=tourism&page=authors&mode=baseline');
  assert.deepEqual([state.nationalProject,state.page,state.mode,state.project],['family','map','latest','family_support']);
  const newProject=parseRoute('#/projects/personnel/explorer?mode=baseline&nationalProject=family');
  assert.deepEqual([newProject.nationalProject,newProject.page,newProject.mode],['personnel','explorer','latest']);
  const linked=projectHref('family','map',{mode:'baseline',page:'authors',nationalProject:'tourism',project:'family_support',source:'data_21'});
  assert.ok(linked.startsWith('#/map?'));
  const query=new URLSearchParams(linked.split('?')[1]);
  assert.equal(query.get('project'),'family_support');
  assert.equal(query.get('source'),'data_21');
  for(const key of ['mode','page','nationalProject'])assert.equal(query.has(key),false);
});

test('unknown project and unavailable author routes resolve to usable overviews',()=>{
  assert.deepEqual(parseRoute(''),{nationalProject:'family',page:'overview',mode:'latest'});
  const unknown=parseRoute('#/projects/nonexistent/not-a-page');
  assert.deepEqual([unknown.nationalProject,unknown.page],['family','overview']);
  for(const id of expectedProjects.slice(1)){
    const state=parseRoute('#/projects/'+id+'/authors');
    assert.deepEqual([state.nationalProject,state.page],[id,'overview']);
  }
  assert.equal(parseRoute('#/authors').page,'authors');
});

test('switching national projects preserves shared page intent and clears incompatible filters',()=>{
  const explorer=parseRoute('#/explorer?project=family_support&source=data_21&indicator=old-code&r=77&compare=78&q=Москва&mode=baseline');
  assert.equal(switchProject(explorer,'tourism'),'#/projects/tourism/explorer');
  assert.equal(switchProject(parseRoute('#/map?source=data_21&r=77'),'tourism'),'#/projects/tourism/map');
  assert.equal(switchProject(parseRoute('#/map?source=data_21&r=77'),'efficient_transport'),'#/projects/efficient_transport/map');
  assert.equal(switchProject(parseRoute('#/map?source=data_21&r=77'),'international_export'),'#/projects/international_export/map');
  assert.equal(switchProject(parseRoute('#/projects/tourism/methods?q=forecast'),'personnel'),'#/projects/personnel/methods');
  assert.equal(switchProject(parseRoute('#/projects/tourism/methods'),'family'),'#/overview');
  assert.equal(switchProject(parseRoute('#/projects/tourism/library?tab=documents'),'family'),'#/library');
});

function pageFixture(overrides={}){
  return {project_id:'long_active_life',id:'framework',status:'reviewed',title:'Методологическая рамка',summary:'Тестовый проверяемый контракт страницы.',updated_at:'2026-10-28',sources:[{title:'ЕМИСС',url:'https://www.fedstat.ru/',locator:'Реестр показателей'}],blocks:[{type:'heading',text:'Вопрос'},{type:'paragraph',text:'Текст для проверки схемы.'},{type:'list',items:['Условие','Ограничение']},{type:'note',text:'Границы интерпретации.'},{type:'table',columns:[{key:'metric',label:'Показатель'},{key:'value',label:'Значение'}],rows:[{metric:'Тестовая строка',value:null}]}],...overrides};
}

test('source references allow public and local evidence but reject executable and credential-bearing URLs',()=>{
  for(const url of ['https://www.fedstat.ru/indicator/62834','http://example.org/report.pdf','downloads/evidence.csv','../data/source.json','#evidence'])assert.equal(safeSourceUrl(url),true,url);
  for(const url of ['javascript:alert(1)','data:text/html,test','file:///tmp/report','//example.org/report','https://user:password@example.org/','https://example.org\n','https:\\example.org',''])assert.equal(safeSourceUrl(url),false,url);
});

test('reviewed page schema requires provenance and supported semantic content',()=>{
  const valid=pageFixture();
  assert.equal(validateExpertise(valid,'long_active_life','framework'),valid);
  const invalid=[
    pageFixture({project_id:'tourism'}),pageFixture({id:'authors'}),pageFixture({status:'draft'}),
    pageFixture({updated_at:'2026-02-30'}),pageFixture({sources:[]}),
    pageFixture({sources:[{title:'Источник',url:'javascript:alert(1)'}]}),
    pageFixture({blocks:[]}),pageFixture({blocks:[{type:'html',text:'<script>ignored</script>'}]}),
    pageFixture({blocks:[{type:'heading',text:'Заголовок',level:1}]}),
    pageFixture({blocks:[{type:'table',columns:[{key:'a',label:'A'},{key:'a',label:'Again'}],rows:[{a:1}]}]}),
    pageFixture({blocks:[{type:'table',columns:[{key:'value',label:'Value'}],rows:[{value:{nested:true}}]}]}),
  ];
  for(const document of invalid)assert.throws(()=>validateExpertise(document,'long_active_life','framework'));
});

test('publication pipeline excludes drafts and removes a page returned to draft',async()=>{
  const siteRoot=await fs.mkdtemp(path.join(os.tmpdir(),'np-publications-'));
  const input=path.join(siteRoot,'content/projects/long_active_life');
  const output=path.join(siteRoot,'public/data/projects');
  try{
    await fs.mkdir(input,{recursive:true});
    const reviewed=pageFixture();
    await fs.writeFile(path.join(input,'framework.json'),JSON.stringify(reviewed));
    // A draft is deliberately incomplete: editorial work must not prevent a
    // build or appear in the public registry before explicit review.
    await fs.writeFile(path.join(input,'logic.json'),JSON.stringify({status:'draft'}));
    assert.equal(await buildPublications(siteRoot),1);
    const registry=JSON.parse(await fs.readFile(path.join(output,'publications.json'),'utf8'));
    assert.equal(Object.keys(registry.projects).length,12);
    assert.deepEqual(registry.projects.long_active_life,[{id:'framework',title:reviewed.title}]);
    assert.deepEqual(JSON.parse(await fs.readFile(path.join(output,'published/long_active_life/framework.json'),'utf8')),reviewed);
    await assert.rejects(fs.access(path.join(output,'published/long_active_life/logic.json')),{code:'ENOENT'});
    await fs.writeFile(path.join(input,'framework.json'),JSON.stringify({...reviewed,status:'draft'}));
    assert.equal(await buildPublications(siteRoot),0);
    const removed=JSON.parse(await fs.readFile(path.join(output,'publications.json'),'utf8'));
    assert.deepEqual(removed.projects.long_active_life,[]);
    await assert.rejects(fs.access(path.join(output,'published/long_active_life/framework.json')),{code:'ENOENT'});
  }finally{await fs.rm(siteRoot,{recursive:true,force:true});}
});

test('an invalid reviewed page stops the batch before replacing existing publications',async()=>{
  const siteRoot=await fs.mkdtemp(path.join(os.tmpdir(),'np-publication-atomic-'));
  const input=path.join(siteRoot,'content/projects/long_active_life');
  const output=path.join(siteRoot,'public/data/projects');
  try{
    await fs.mkdir(input,{recursive:true});
    await fs.writeFile(path.join(input,'framework.json'),JSON.stringify(pageFixture()));
    await buildPublications(siteRoot);
    const before=await fs.readFile(path.join(output,'publications.json'),'utf8');
    const published=await fs.readFile(path.join(output,'published/long_active_life/framework.json'),'utf8');
    await fs.writeFile(path.join(input,'logic.json'),JSON.stringify(pageFixture({id:'logic',sources:[]})));
    await assert.rejects(buildPublications(siteRoot),/At least one source/);
    assert.equal(await fs.readFile(path.join(output,'publications.json'),'utf8'),before);
    assert.equal(await fs.readFile(path.join(output,'published/long_active_life/framework.json'),'utf8'),published);
    await assert.rejects(fs.access(path.join(output,'published/long_active_life/logic.json')),{code:'ENOENT'});
  }finally{await fs.rm(siteRoot,{recursive:true,force:true});}
});
