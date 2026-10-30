import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {projects, foundationPages, expertiseBlueprint as blueprint, projectHref} from '../src/platform/projects.js';
import {siteOrigin} from './build-seo.mjs';
import {loadCurrentReports,renderCurrentReportCard} from './current_reports.mjs';

const root=path.resolve(import.meta.dirname,'..');
const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const requiredText=(value,label)=>{if(typeof value!=='string'||!value.trim())throw new Error(label+': required nonempty string');};
const sectionIds=new Set(blueprint.map(section=>section.id));

export function safeSourceUrl(value){
  if(typeof value!=='string'||!value||value!==value.trim()||/[\u0000-\u0020\\]/.test(value)||value.startsWith('//'))return false;
  if(/^[a-z][a-z\d+.-]*:/i.test(value)){
    try {const parsed=new URL(value);return ['http:','https:'].includes(parsed.protocol)&&Boolean(parsed.hostname)&&!parsed.username&&!parsed.password;}catch{return false;}
  }
  return true;
}

export function validateExpertise(data,projectId,sectionId){
  if(data.project_id!==projectId||data.id!==sectionId)throw new Error('Page identity must match content/projects/<project_id>/<id>.json');
  if(!sectionIds.has(sectionId))throw new Error('Unknown expertise section: '+sectionId);
  if(data.status!=='reviewed')throw new Error('Only reviewed pages may be published');
  for(const key of ['title','summary','updated_at'])requiredText(data[key],key);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(data.updated_at)||new Date(data.updated_at).toISOString().slice(0,10)!==data.updated_at)throw new Error('updated_at must be a valid YYYY-MM-DD date');
  if(!Array.isArray(data.sources)||!data.sources.length)throw new Error('At least one source is required');
  for(const source of data.sources){
    requiredText(source.title,'source.title');
    if(!safeSourceUrl(source.url))throw new Error('Unsafe or invalid source URL');
    if(source.locator!==undefined)requiredText(source.locator,'source.locator');
  }
  if(!Array.isArray(data.blocks)||!data.blocks.length)throw new Error('At least one content block is required');
  for(const block of data.blocks){
    if(['paragraph','heading','note'].includes(block.type)){
      requiredText(block.text,'block.text');
      if(block.type==='heading'&&block.level!==undefined&&![2,3].includes(block.level))throw new Error('Heading level must be 2 or 3');
    }else if(block.type==='list'){
      if(!Array.isArray(block.items)||!block.items.length)throw new Error('List must have items');
      block.items.forEach(item=>requiredText(item,'list item'));
    }else if(block.type==='table'){
      if(!Array.isArray(block.columns)||!block.columns.length||!Array.isArray(block.rows)||!block.rows.length)throw new Error('Table must have columns and rows');
      const keys=new Set();
      for(const column of block.columns){
        requiredText(column.label,'column.label');
        if(typeof column.key!=='string'||!/^[a-z][a-z\d_]*$/i.test(column.key)||keys.has(column.key))throw new Error('Invalid or duplicate table column key');
        keys.add(column.key);
      }
      for(const row of block.rows){
        if(!row||typeof row!=='object'||Array.isArray(row))throw new Error('Table row must be an object');
        for(const key of keys){
          const value=row[key];
          if(value!==null&&typeof value!=='string'&&typeof value!=='boolean'&&!(typeof value==='number'&&Number.isFinite(value)))throw new Error('Table cell must be text, a finite number, boolean or null');
        }
      }
    }else throw new Error('Unsupported content block: '+block.type);
  }
  return data;
}

export async function buildPublications(siteRoot=root){
  const input=path.join(siteRoot,'content/projects');
  const output=path.join(siteRoot,'public/data/projects/published');
  const registry={projects:Object.fromEntries(projects.map(project=>[project.id,[]]))};
  const checked=[];
  for(const project of projects){
    const directory=path.join(input,project.id);
    const files=await fs.readdir(directory,{withFileTypes:true}).catch(error=>{if(error.code==='ENOENT')return [];throw error;});
    for(const file of files.sort((a,b)=>a.name.localeCompare(b.name))){
      if(!file.isFile()||!file.name.endsWith('.json'))continue;
      const source=path.join(directory,file.name);
      const data=JSON.parse(await fs.readFile(source,'utf8'));
      if(data.status==='draft')continue;
      if(data.status!=='reviewed')throw new Error(source+': status must be draft or reviewed');
      const sectionId=file.name.slice(0,-5);
      try{validateExpertise(data,project.id,sectionId);}catch(error){throw new Error(source+': '+error.message);}
      checked.push({projectId:project.id,sectionId,data});
      registry.projects[project.id].push({id:sectionId,title:data.title});
    }
  }
  // Validate the complete batch before changing generated publications. Rebuild
  // the generated set so returning a reviewed page to draft removes stale output.
  await fs.rm(output,{recursive:true,force:true});
  await fs.mkdir(output,{recursive:true});
  for(const item of checked){
    const destination=path.join(output,item.projectId,item.sectionId+'.json');
    await fs.mkdir(path.dirname(destination),{recursive:true});
    await fs.writeFile(destination,JSON.stringify(item.data,null,2)+'\n');
  }
  for(const value of Object.values(registry.projects))value.sort((a,b)=>blueprint.findIndex(s=>s.id===a.id)-blueprint.findIndex(s=>s.id===b.id));
  await fs.writeFile(path.join(siteRoot,'public/data/projects/publications.json'),JSON.stringify(registry,null,2)+'\n');
  return checked.length;
}

function entryPage(project,foundation,currentReports){
  const url=siteOrigin+'/research/projects/'+project.id+'/index.html';
  const interactive=section=>'../../../'+projectHref(project.id,section);
  const title='Национальный проект «'+project.name+'»';
  const description='Исследовательская основа, показатели, методы и источники экспертизы национального проекта «'+project.name+'».';
  const stat=foundation.registry;
  const structured={'@context':'https://schema.org','@type':'WebPage',name:title,description,url,inLanguage:'ru'};
  const rail=projects.map(other=>`<a href="../${other.id}/index.html"${other.id===project.id?' aria-current="page"':''}><i style="--dot:${other.color}"></i>${esc(other.short)}</a>`).join('');
  const links=foundationPages.map(({id,title:label})=>`<li><a href="${interactive(id)}">${esc(label)}</a></li>`).join('');
  const sources=foundation.sources.filter(source=>source.url).slice(0,6).map(source=>`<li><a href="${esc(source.url)}" rel="noopener noreferrer">${esc(source.title)}</a>${source.qualification?`<p>${esc(source.qualification)}</p>`:''}</li>`).join('');
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)} · Исследовательская платформа</title>
<meta name="description" content="${esc(description)}"><link rel="canonical" href="${url}"><link rel="icon" href="../../../favicon.png"><link rel="stylesheet" href="../styles.css"><link rel="stylesheet" href="../../current-reports.css">
<meta property="og:type" content="article"><meta property="og:locale" content="ru_RU"><meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(description)}"><meta property="og:url" content="${url}">
<script type="application/ld+json">${JSON.stringify(structured).replaceAll('<','\\u003c')}</script></head>
<body style="--brand:${project.color}"><a class="skip" href="#main">К содержанию</a><header><a class="brand" href="../../../">Исследовательская платформа<span>Национальные проекты</span></a><nav class="rail" aria-label="Национальные проекты">${rail}</nav></header>
<main id="main"><div class="hero"><div><p class="eyebrow">Национальный проект</p><h1>${esc(project.name)}</h1><p class="lead">${esc(description)}</p></div><img class="project-logo" src="../../../assets/brand/${project.id}.svg" alt="Официальный логотип нацпроекта ${esc(project.name)}" width="136" height="116"></div>
<p><a class="action" href="${interactive('overview')}">Открыть интерактивную платформу</a></p><div class="metrics"><section><strong>${stat.n_registry}</strong><span>показателей в реестре</span></section><section><strong>${stat.n_with_numeric}</strong><span>с числовыми данными</span></section><section><strong>${stat.n_with_regional}</strong><span>с региональными данными</span></section></div>
${renderCurrentReportCard(currentReports,project.id,'../../../')}
<h2>Материалы проекта</h2><ul class="page-links">${links}</ul>
<div class="note"><p>Статистический срез: <strong>${esc(foundation.statistical_as_of)}</strong>. Документальная редакция: <strong>${esc(foundation.documentary_as_of)}</strong>.</p><p>Дата публикации сайта не заменяет дату первичных данных. ${project.id==='family'?'Авторская экспертиза «Семьи» сохраняет собственную документальную редакцию; актуальные статистические ряды доступны в интерактивных разделах.':'На этой странице представлена проверенная исследовательская основа. Содержательные страницы авторской экспертизы добавляются последовательно.'}</p></div>
<h2>Структура экспертизы</h2><ol>${foundation.sections.map(section=>`<li><strong>${esc(section.title)}</strong><p>${esc(section.evidence)}</p></li>`).join('')}</ol>
${sources?`<h2>Документальные источники</h2><ul>${sources}</ul>`:''}
<p><a href="${interactive('library')}">Все доступные источники и материалы</a></p>${project.hasAuthors?'<p><a href="../../../#/authors">Об авторах экспертизы «Семьи»</a></p>':''}
</main><footer>Национальные проекты · исследовательская платформа · <a href="${interactive('overview')}">Интерактивный обзор</a></footer></body></html>\n`;
}

const style=`@font-face{font-family:Roboto;src:url('../../assets/fonts/Roboto-Regular.woff') format('woff');font-style:normal;font-weight:400;font-display:swap}@font-face{font-family:Roboto;src:url('../../assets/fonts/Roboto-SemiBold.woff') format('woff');font-style:normal;font-weight:600;font-display:swap}@font-face{font-family:Roboto;src:url('../../assets/fonts/Roboto-Bold.woff') format('woff');font-style:normal;font-weight:700;font-display:swap}*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#192638;font:17px/1.65 Roboto,Arial,sans-serif;--accent:color-mix(in srgb,var(--brand),#111 40%)}a{color:var(--accent);text-underline-offset:3px}header,main,footer{max-width:1120px;margin:auto;padding:28px}.brand{font-weight:600;font-size:14px;text-decoration:none;color:#526071}.brand span{display:block;color:#15263f;font-weight:700;font-size:24px}.rail{display:flex;gap:8px;overflow-x:auto;padding:20px 0 8px;white-space:nowrap}.rail a{display:flex;align-items:center;gap:7px;flex:none;padding:6px 11px;border-radius:8px;color:#344154;text-decoration:none;font-size:13px}.rail a[aria-current]{background:white;box-shadow:inset 0 0 0 1px var(--brand);font-weight:700}.rail i{background:var(--dot);width:8px;height:8px;border-radius:50%;flex:none}main{background:white;border:1px solid #dde3ed;border-top:4px solid var(--brand);border-radius:16px;padding:clamp(22px,5vw,56px)}h1{font-size:clamp(30px,5vw,46px);line-height:1.15;margin:12px 0 20px;overflow-wrap:anywhere}h2{font-size:25px;line-height:1.3;margin-top:35px}.hero{display:flex;gap:26px;align-items:start}.hero>div{min-width:0;flex:1}.project-logo{object-fit:contain;flex:none;max-width:27%;background:white}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:700;color:var(--accent);margin:0}.lead{color:#536176;font-size:19px}.action{display:inline-block;background:var(--accent);color:white;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:600}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}.metrics section{padding:19px;border:1px solid #e3e7ee;border-radius:10px;background:#f7f9fc}.metrics strong{display:block;font-size:34px;line-height:1.3;color:var(--accent)}.metrics span{font-size:14px;color:#526071}.note{padding:14px 22px;border-left:4px solid var(--brand);background:#f5f7fb}.note p{margin:8px 0}.page-links{display:flex;flex-wrap:wrap;gap:12px 28px;list-style:none;padding:0}li{padding:5px 0}li p{margin:5px 0 10px;color:#526071}p,li{overflow-wrap:anywhere}.skip{position:absolute;left:-10000px}.skip:focus{left:12px;top:8px;background:white;padding:8px;z-index:2}footer{font-size:14px;color:#617086}@media(max-width:620px){header,footer{padding:18px}.brand span{font-size:22px}main{margin:0 12px;padding:22px;border-radius:12px}.hero{gap:12px}.project-logo{width:96px;height:82px;max-width:none}.metrics{grid-template-columns:1fr;gap:8px}.metrics section{display:flex;align-items:center;gap:15px;padding:12px 16px}.metrics strong{font-size:28px;min-width:50px}.lead{font-size:17px}.note{padding:10px 14px}.page-links{display:block}.page-links li{padding:7px 0}}\n`;

export async function buildProjects(){
  const output=path.join(root,'public/research/projects');
  const currentReports=await loadCurrentReports(root);
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'styles.css'),style);
  for(const project of projects){
    const foundation=JSON.parse(await fs.readFile(path.join(root,'public/data/projects',project.id,'foundation.json'),'utf8'));
    const destination=path.join(output,project.id,'index.html');
    await fs.mkdir(path.dirname(destination),{recursive:true});
    await fs.writeFile(destination,entryPage(project,foundation,currentReports));
  }
  const sitemapFile=path.join(root,'public/sitemap.xml');
  let sitemap=await fs.readFile(sitemapFile,'utf8');
  const additions=projects.map(project=>siteOrigin+'/research/projects/'+project.id+'/index.html').filter(url=>!sitemap.includes('<loc>'+url+'</loc>'));
  sitemap=sitemap.replace('</urlset>',additions.map(url=>'  <url><loc>'+url+'</loc></url>').join('\n')+'\n</urlset>');
  await fs.writeFile(sitemapFile,sitemap);
  const published=await buildPublications();
  console.log('Built '+projects.length+' national-project entry pages and '+published+' reviewed expertise pages.');
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await buildProjects();
