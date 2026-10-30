import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {copyBuildAssets} from '../scripts/copy_build_assets.mjs';

test('portable and disk-saving publication preserve identical allowed bytes',async()=>{
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),'np-asset-copy-'));
  try{
    const source=path.join(temp,'source');await fs.mkdir(source);
    await fs.writeFile(path.join(source,'data.json'),'[0,null,123.45000000000000001,"Транспорт"]\n');
    await fs.writeFile(path.join(source,'.temporary'),'not published');
    const filter=p=>!path.basename(p).startsWith('.');
    for(const link of [false,true]){
      const output=path.join(temp,link?'links':'copies');
      await copyBuildAssets(source,output,{filter,link});
      assert.deepEqual(await fs.readdir(output),['data.json']);
      assert.deepEqual(await fs.readFile(path.join(output,'data.json')),await fs.readFile(path.join(source,'data.json')));
      const a=await fs.stat(path.join(source,'data.json')),b=await fs.stat(path.join(output,'data.json'));
      assert.equal(a.ino===b.ino,link);
    }
    await fs.writeFile(path.join(temp,'new-source.json'),'[42]');
    await copyBuildAssets(path.join(temp,'new-source.json'),path.join(temp,'links/data.json'),{link:true});
    assert.equal(await fs.readFile(path.join(source,'data.json'),'utf8'),'[0,null,123.45000000000000001,"Транспорт"]\n');
    assert.equal(await fs.readFile(path.join(temp,'links/data.json'),'utf8'),'[42]');
  }finally{await fs.rm(temp,{recursive:true,force:true});}
});

test('disk-saving copy refuses source identity',async()=>{
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),'np-asset-guard-'));
  try{
    const source=path.join(temp,'source.json');await fs.writeFile(source,'{}');
    await assert.rejects(copyBuildAssets(source,source,{link:true}),/must differ/);
    assert.equal(await fs.readFile(source,'utf8'),'{}');
  }finally{await fs.rm(temp,{recursive:true,force:true});}
});

test('disk-saving copy refuses destination symlinks',async(t)=>{
  const temp=await fs.mkdtemp(path.join(os.tmpdir(),'np-asset-symlink-guard-'));
  try{
    const source=path.join(temp,'source.json');await fs.writeFile(source,'{}');
    const output=path.join(temp,'output.json');
    try{await fs.symlink(source,output);}catch(error){
      if(process.platform==='win32'&&error.code==='EPERM'){
        t.skip('Windows does not permit symlink creation in this environment');
        return;
      }
      throw error;
    }
    await assert.rejects(copyBuildAssets(source,output,{link:true}),/symlink/);
    assert.equal(await fs.readFile(source,'utf8'),'{}');
  }finally{await fs.rm(temp,{recursive:true,force:true});}
});
