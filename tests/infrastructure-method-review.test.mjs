import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {applyInfrastructureMethodReview,buildInfrastructureFoundation} from '../scripts/build_infrastructure.mjs';

const root=path.resolve(import.meta.dirname,'..');
const review=JSON.parse(await fs.readFile(path.join(root,'scripts/infrastructure_method_review.json'),'utf8'));
const relative='public/data/projects/life_infrastructure';
const published=JSON.parse(await fs.readFile(path.join(root,relative,'methods.json'),'utf8'));

test('the versioned review exactly preserves all published editorial fields',()=>{
  const methods=structuredClone(published);
  applyInfrastructureMethodReview(methods,review);
  assert.deepEqual(methods,published);
});

test('a new editorial revision applies without replacing numeric or historical fields',()=>{
  const methods=structuredClone(published),edited=structuredClone(review);
  edited.items[0].current_limitations='Новая редакторская оговорка с указанием основания.';
  methods.items[0].numeric_indicators=41;
  const before=structuredClone(methods);
  applyInfrastructureMethodReview(methods,edited);
  assert.equal(methods.items[0].current_limitations,edited.items[0].current_limitations);
  before.items[0].current_limitations=edited.items[0].current_limitations;
  assert.deepEqual(methods,before);
});

test('incomplete or duplicate reviews fail before changing any catalogue field',()=>{
  for(const change of [
    value=>value.items.pop(),
    value=>value.items.push(value.items[0]),
    value=>{value.items[0].current_limitations=' ';},
    value=>{value.items[0].numeric_indicators=123;},
    value=>{value.project_id='tourism';}
  ]){
    const methods=structuredClone(published),broken=structuredClone(review);
    change(broken);
    assert.throws(()=>applyInfrastructureMethodReview(methods,broken),/Infrastructure method/);
    assert.deepEqual(methods,published);
  }
  const missing=structuredClone(published);missing.items.pop();
  assert.throws(()=>applyInfrastructureMethodReview(missing,review),/absent from the catalogue/);
});

test('publication reads a changed editorial source on every build',async()=>{
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),'np-method-review-'));
  try{
    await fs.mkdir(path.join(temp,relative),{recursive:true});
    await fs.mkdir(path.join(temp,'scripts'));
    for(const file of ['foundation.json','expertise.json','methods.json'])
      await fs.copyFile(path.join(root,relative,file),path.join(temp,relative,file));
    await fs.copyFile(path.join(root,'package.json'),path.join(temp,'package.json'));
    const edited=structuredClone(review);
    for(const revision of ['Редакция А: ограничение проверено.','Редакция Б: основание уточнено.']){
      edited.items[0].current_limitations=revision;
      await fs.writeFile(path.join(temp,'scripts/infrastructure_method_review.json'),JSON.stringify(edited));
      await buildInfrastructureFoundation(temp);
      const output=JSON.parse(await fs.readFile(path.join(temp,relative,'methods.json'),'utf8'));
      assert.equal(output.items[0].current_limitations,revision);
      assert.equal(output.items[0].numeric_indicators,published.items[0].numeric_indicators);
      const bytes=await fs.readFile(path.join(temp,relative,'methods.json'));
      await buildInfrastructureFoundation(temp);
      assert.deepEqual(await fs.readFile(path.join(temp,relative,'methods.json')),bytes);
    }
  }finally{await fs.rm(temp,{recursive:true,force:true});}
});
