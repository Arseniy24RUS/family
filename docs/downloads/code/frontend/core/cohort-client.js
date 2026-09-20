/** Fetch a local, generated worker bundle and run it off the UI thread.
 * The Blob transport also supports sandboxed embeds without assuming the page origin.
 */
let sourcePromise;
async function source(){
 if(!sourcePromise)sourcePromise=fetch(new URL('../../workers/cohort-worker.js',import.meta.url)).then(async r=>{if(!r.ok)throw Error('Не найден вычислительный модуль: HTTP '+r.status);return r.text();}).catch(e=>{sourcePromise=null;throw e;});
 return sourcePromise;
}
export async function calculateCohort(input,options={}) {
 const code=await source();
 return new Promise((resolve,reject)=>{
  const url=URL.createObjectURL(new Blob([code],{type:'text/javascript'}));let worker;
  try{worker=new Worker(url);}catch(e){URL.revokeObjectURL(url);reject(e);return;}
  const clean=()=>{clearTimeout(timer);worker.terminate();URL.revokeObjectURL(url);};
  const timer=setTimeout(()=>{clean();reject(Error('Расчёт превысил 90 секунд. Проверьте исходные данные.'));},90000);
  worker.onmessage=e=>{clean();e.data.error?reject(Error(e.data.error)):resolve(e.data.result);};
  worker.onerror=e=>{clean();reject(Error(e.message||'Не удалось запустить вычислительный модуль.'));};
  worker.postMessage({input,options});
 });
}
