import path from 'node:path';
import {spawn} from 'node:child_process';

const root=path.resolve(import.meta.dirname,'..');
const python=process.env.PYTHON || (process.platform==='win32'?'python':'python3');
const child=spawn(python,[path.join(root,'scripts/preview_platform.py'),'--no-open',...process.argv.slice(2)],{
  cwd:root,
  stdio:'inherit',
});
const handlers=new Map();
for(const signal of ['SIGINT','SIGTERM']){
  const forward=()=>{if(child.exitCode===null && child.signalCode===null)child.kill(signal);};
  handlers.set(signal,forward);
  process.on(signal,forward);
}
child.once('error',error=>{
  console.error(`Не удалось запустить ${python}: ${error.message}`);
  process.exitCode=1;
});
child.once('close',(code,signal)=>{
  for(const [name,handler] of handlers)process.removeListener(name,handler);
  if(signal){
    try{process.kill(process.pid,signal);}catch{process.exitCode=1;}
  }else{
    process.exitCode=Number.isInteger(code) && code>=0 ? code : 1;
  }
});
