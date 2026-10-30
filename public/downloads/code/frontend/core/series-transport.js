/** Lossless transport for the compact GitHub Pages artifact only.
 * The full docs/ and public/ retain their original JSON. This adapter is enabled
 * only by the publication builder's meta tag and only for listed local JSON.
 */
const PATH=/^data\/projects\/[a-z0-9_]+\/series\/[a-zA-Z0-9_-]+\.json$/;
const RUNTIME_PATH=/^data\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_-]+\.json$/;
const SHA=/^[a-f0-9]{64}$/;

export function createSeriesTransport({manifest,baseURL,fetcher=globalThis.fetch.bind(globalThis),decompress=globalThis.DecompressionStream}){
 const version=manifest?.schema;
 if(!['national-projects.series-transport/1','national-projects.series-transport/2'].includes(version)||!Array.isArray(manifest.files))throw Error('Неизвестный формат публикационного набора.');
 const allowedPath=version.endsWith('/2')?RUNTIME_PATH:PATH;
 const base=new URL(baseURL),lookup=new Map();
 for(const record of manifest.files){
  if(!allowedPath.test(record.path)||record.path==='data/series-transport.json'||record.compressed_path!==record.path+'.gz'||!SHA.test(record.sha256)||!SHA.test(record.compressed_sha256)||!Number.isSafeInteger(record.bytes)||record.bytes<1||!Number.isSafeInteger(record.compressed_bytes)||record.compressed_bytes<1)throw Error('Некорректный адрес набора данных.');
  for(const relative of [record.path,record.compressed_path]){
   const url=new URL(relative,base);if(url.origin!==base.origin||!url.pathname.startsWith(base.pathname)||lookup.has(url.origin+url.pathname))throw Error('Повторяющийся или внешний адрес набора данных.');
   lookup.set(url.origin+url.pathname,record);
  }
 }
 function recordFor(input){
  const raw=typeof input==='string'||input instanceof URL?String(input):input?.url;
  if(!raw)return null;
  let url;try{url=new URL(raw,base);}catch{return null;}
  return lookup.get(url.origin+url.pathname)||null;
 }
 async function fetchSeries(input,init){
  const method=String(init?.method||(typeof input==='object'&&input?.method)||'GET').toUpperCase(),record=recordFor(input);
  if(!record||method!=='GET')return fetcher(input,init);
  if(typeof decompress!=='function')throw Error('Для открытия данных требуется браузер с поддержкой распаковки gzip. Обновите браузер или откройте полный локальный комплект.');
  const requested=new URL(typeof input==='string'||input instanceof URL?String(input):input.url,base),target=new URL(record.compressed_path,base);target.search=requested.search;
  const request=typeof Request!=='undefined'&&input instanceof Request?new Request(target,input):target.href;
  const response=await fetcher(request,init);
  if(!response.ok)return response;
  if(!response.body)throw Error('Статистический источник вернул пустой ответ.');
  const headers=new Headers(response.headers);headers.delete('content-encoding');headers.delete('content-length');headers.set('content-type','application/json; charset=utf-8');
  // DecompressionStream validates gzip integrity and preserves the JSON bytes.
  return new Response(response.body.pipeThrough(new decompress('gzip')),{status:response.status,statusText:response.statusText,headers});
 }
 return {fetch:fetchSeries,recordFor,records:manifest.files.length};
}

let installed=null,installing=null,activeTransport=null,boundDocument=null;
export async function installSeriesTransport(){
 if(installed)return installed;
 if(installing)return installing;
 const meta=globalThis.document?.querySelector('meta[name="series-transport"]');
 if(!meta)return {enabled:false};
 const manifestURL=new URL(meta.content||meta.getAttribute('content'),document.baseURI),baseURL=new URL('../',manifestURL);
 bindDownloads(baseURL);
 installing=installTransport(meta).then(result=>{installed=result;return result;}).finally(()=>{installing=null;});
 return installing;
}
async function installTransport(meta){
 const nativeFetch=globalThis.fetch.bind(globalThis),manifestURL=new URL(meta.content||meta.getAttribute('content'),document.baseURI),baseURL=new URL('../',manifestURL);
 const response=await nativeFetch(manifestURL.href,{cache:'no-cache'});if(!response.ok)throw Error('Не удалось открыть состав данных (HTTP '+response.status+').');
 const transport=createSeriesTransport({manifest:await response.json(),baseURL:baseURL.href,fetcher:nativeFetch});
 globalThis.fetch=transport.fetch;
 activeTransport=transport;
 return {enabled:true,records:transport.records};
}

/** Bind before the manifest request so an early article click cannot open a
 * forwarding envelope. A failed installation is retried by the next click.
 */
function bindDownloads(baseURL){
 if(boundDocument===document)return;
 boundDocument=document;
 document.addEventListener('click',async event=>{
  if(event.defaultPrevented||event.button>0)return;
  const anchor=event.target?.closest?.('a[href]');if(!anchor)return;
  let requested;try{requested=new URL(anchor.href||anchor.getAttribute('href'),document.baseURI);}catch{return;}
  if(requested.origin!==baseURL.origin||!requested.pathname.startsWith(baseURL.pathname))return;
  const relative=requested.pathname.slice(baseURL.pathname.length).replace(/\.gz$/,'');
  if(!RUNTIME_PATH.test(relative)||relative==='data/series-transport.json')return;
  if(activeTransport&&!activeTransport.recordFor(requested))return;
  event.preventDefault();
  try{
   await installSeriesTransport();
   const file=await activeTransport.fetch(requested.href);if(!file.ok)throw Error('HTTP '+file.status);
   const url=URL.createObjectURL(await file.blob()),download=document.createElement('a');download.href=url;download.download=relative.split('/').at(-1);download.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){
   const message='Не удалось скачать данные: '+(error?.message||'ошибка загрузки'),status=document.getElementById('announcer');if(status)status.textContent=message;
   const box=document.createElement('div');box.className='toast';box.setAttribute('role','alert');box.textContent=message;document.body.append(box);setTimeout(()=>box.remove(),10000);
  }
 });
}
