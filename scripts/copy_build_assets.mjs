/** Optional local build copies that conserve disk space without changing bytes. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export async function copyBuildAssets(source,destination,{filter=()=>true,link=false}={}){
  if(!filter(source))return;
  if(!link){
    await fs.mkdir(path.dirname(destination),{recursive:true});
    await fs.cp(source,destination,{recursive:true,filter});
    return;
  }
  if(path.resolve(source)===path.resolve(destination))throw Error('Build source and destination must differ.');
  const stat=await fs.lstat(source);
  if(stat.isSymbolicLink())throw Error('Hardlink publication requires regular source files: '+source);
  if(stat.isDirectory()){
    await fs.mkdir(destination,{recursive:true});
    for(const name of await fs.readdir(source))await copyBuildAssets(path.join(source,name),path.join(destination,name),{filter,link});
    return;
  }
  if(!stat.isFile())throw Error('Unsupported build asset: '+source);
  await fs.mkdir(path.dirname(destination),{recursive:true});
  const existing=await fs.lstat(destination).catch(error=>{if(error.code==='ENOENT')return null;throw error;});
  if(existing?.isSymbolicLink())throw Error('Build destination cannot be a symlink: '+destination);
  if(existing&&existing.dev===stat.dev&&existing.ino===stat.ino)return;
  const temporary=path.join(path.dirname(destination),'.'+path.basename(destination)+'.'+crypto.randomUUID()+'.tmp');
  try{await fs.link(source,temporary);await fs.rename(temporary,destination);}
  finally{await fs.rm(temporary,{force:true});}
}
