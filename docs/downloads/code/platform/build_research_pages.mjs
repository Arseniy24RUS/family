/** Shared source-linked static pages for completed national-project studies. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {projects,projectHref} from '../src/platform/projects.js';
import {siteOrigin} from './build-seo.mjs';
import {safeSourceUrl} from './build_projects.mjs';
import {loadCurrentReports,renderCurrentReportCard,ORIGINAL_REPORT_LABEL} from './current_reports.mjs';

const ROOT=path.resolve(import.meta.dirname,'..');
const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const href=value=>{
  if(!safeSourceUrl(value))return '';
  return /^(https?:|#)/i.test(value)?value:'../../../'+value.replace(/^\.\//,'');
};
const link=(url,label)=>{
  const resolved=href(url);
  const originalReport=/(?:^|\/)report\/[^/]+\.docx(?:[?#]|$)/.test(url||'');
  const text=originalReport&&!String(label).includes(ORIGINAL_REPORT_LABEL)?label+' · '+ORIGINAL_REPORT_LABEL:label;
  return resolved?`<a href="${esc(resolved)}" rel="noopener noreferrer">${esc(text)}</a>`:esc(text);
};
const fileFor=id=>id==='overview'?'index.html':id+'.html';

export function renderReportBlocks(page,expertise){
  const figures=new Map(expertise.figures.map(x=>[x.id,x]));
  const sources=new Map(expertise.sources.map(x=>[x.id,x]));
  const citations=block=>{
    const ids=(block.sourceIds||[]).filter(id=>id!=='report'&&sources.has(id));
    const refs=ids.map(id=>`<a href="#source-${esc(id)}" aria-label="Источник ${esc(sources.get(id).note_number||id)}">[${esc(sources.get(id).note_number||id)}]</a>`).join(' ');
    return refs||block.page?`<span class="citations">${refs}${block.page?` <span>с. ${esc(block.page)} исходного отчёта</span>`:''}</span>`:'';
  };
  return page.blocks.map(block=>{
    const id=block.id?` id="${esc(block.id)}"`:'';
    if(block.type==='heading')return `<h${block.level===3?'3':'2'}${id}>${esc(block.text)}</h${block.level===3?'3':'2'}>`;
    if(block.type==='paragraph')return `<p${id}>${esc(block.text)} ${citations(block)}</p>`;
    if(block.type==='note')return `<aside class="note"${id}><p>${esc(block.text)} ${citations(block)}</p></aside>`;
    if(block.type==='formula')return `<div class="formula"${id} role="math" aria-label="${esc(block.text)}">${esc(block.text)}${block.number?` <span>(${esc(block.number)})</span>`:''}</div>`;
    if(block.type==='list')return `<${block.ordered?'ol':'ul'}${id}>${block.items.map(x=>`<li>${esc(x)}</li>`).join('')}</${block.ordered?'ol':'ul'}>`;
    if(block.type==='table'){
      const cellCitations=ids=>ids?.length?` <sup>${citations({sourceIds:ids})}</sup>`:'';
      return `<section class="report-table"${id}><h3>${esc(block.title)}</h3><div class="table-scroll" tabindex="0" role="region" aria-label="${esc(block.title)}"><table><thead><tr>${block.columns.map((c,ci)=>`<th scope="col">${esc(c.label||c.title)}${cellCitations(block.headerSourceIds?.[ci])}</th>`).join('')}</tr></thead><tbody>${block.rows.map((row,ri)=>`<tr>${block.columns.map((c,ci)=>`<td>${esc(row[c.key])}${cellCitations(block.cellSourceIds?.[ri]?.[ci])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>${block.note?`<p class="small">${esc(block.note)}</p>`:''}${citations(block)}</section>`;
    }
    if(block.type==='figure_ref'){
      const figure=figures.get(block.figureId)||block;
      return `<figure class="source-figure"${id}><figcaption><strong>${esc(figure.title||block.title)}</strong>${figure.note?`<p>${esc(figure.note)}</p>`:''}${link(figure.url||block.url,'Открыть иллюстрацию исходного отчёта')} ${citations(block)}</figcaption></figure>`;
    }
    throw Error('Unsupported research report block: '+block.type);
  }).join('\n');
}

export function validateResearchContent(expertise,projectId,pageSpecs){
  if(expertise.meta?.project_id!==projectId)throw Error('Research content identity mismatch: '+projectId);
  const ids=new Set();
  const sourceIds=new Set(expertise.sources.map(x=>x.id));
  const figureIds=new Set(expertise.figures.map(x=>x.id));
  for(const clarification of expertise.meta.source_clarifications||[]){
    if(!pageSpecs.some(page=>page.id===clarification.route))throw Error('Unknown clarification route: '+clarification.route);
    if(clarification.source_url&&!safeSourceUrl(clarification.source_url))throw Error('Unsafe research clarification URL: '+clarification.route);
  }
  for(const source of expertise.sources){
    if(source.url&&!safeSourceUrl(source.url))throw Error('Unsafe research source URL: '+source.id);
    for(const url of source.urls||[])if(!safeSourceUrl(url))throw Error('Unsafe research additional source URL: '+source.id);
  }
  for(const spec of pageSpecs){
    const page=expertise.pages[spec.id];
    if(!page||page.id!==spec.id||!page.title||!page.summary||!Array.isArray(page.blocks))throw Error('Incomplete research route: '+spec.id);
    for(const id of page.sources||[])if(!sourceIds.has(id))throw Error('Missing page source: '+id);
    for(const block of page.blocks){
      if(block.id){if(ids.has(block.id))throw Error('Repeated report block: '+block.id);ids.add(block.id);}
      for(const id of block.sourceIds||[])if(!sourceIds.has(id))throw Error('Missing block source: '+id);
      if(block.type==='figure_ref'&&!figureIds.has(block.figureId))throw Error('Missing report figure: '+block.figureId);
      if(block.type==='table'&&(!block.columns?.length||!block.rows?.length))throw Error('Empty report table: '+block.id);
    }
    renderReportBlocks(page,expertise);
  }
  return {routes:pageSpecs.length,blocks:ids.size,sources:sourceIds.size,figures:figureIds.size};
}

const STYLE=`.article-rail{display:flex;gap:8px;overflow-x:auto;padding:10px 0;margin-bottom:25px}.article-rail a{white-space:nowrap;font-size:14px}.article-rail a[aria-current]{font-weight:700}.article-body{max-width:880px}.article-body h2{margin-top:42px}.article-body h3{font-size:21px;line-height:1.35;margin-top:28px}.article-body p{text-align:left}.article-body .citations{font-size:12px;color:#637084;white-space:normal}.citations a{font-weight:700;text-decoration:none}.source-list{font-size:14px}.source-list li{padding:8px 0}.source-list p{margin:4px 0}.table-scroll{overflow:auto;max-width:100%;border:1px solid var(--study-border,#e2d9f2);border-radius:9px}.table-scroll:focus{outline:2px solid var(--brand)}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.5;min-width:620px}th,td{padding:11px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--study-border,#e5e1ef)}th{background:var(--study-table-head,var(--study-soft,#eee8f7));color:var(--study-ink,#432b68)}tbody tr:last-child td{border-bottom:0}.small{font-size:14px;color:#59677b}.source-figure{margin:24px 0;padding:18px 22px;border-left:3px solid var(--brand);background:var(--study-soft,#f7f4fb);font-size:15px}.source-figure p{margin:9px 0}.formula{white-space:pre-wrap;overflow-wrap:anywhere;padding:18px 22px;background:var(--study-soft,#f7f4fb);font-size:17px;border:1px solid var(--study-border,#e2d9f2);border-radius:8px}.section-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.section-grid a{padding:12px 15px;background:var(--study-soft,#f7f4fb);border:1px solid var(--study-border,#e7e0f2);border-radius:9px;text-decoration:none}.section-grid p{margin:5px 0;font-size:14px;color:#58657a}.source-list [id]{scroll-margin-top:20px}@media(max-width:620px){.section-grid{grid-template-columns:1fr}.article-body h2{font-size:24px}.article-body h3{font-size:20px}.formula{font-size:15px;padding:14px}.source-figure{padding:14px;margin:20px 0}.table-scroll{margin-right:-8px}}`;

export async function buildResearchPages(projectId,pageSpecs,root=ROOT){
  const project=projects.find(p=>p.id===projectId);
  if(!project||projectId==='family')throw Error('Unsupported research project: '+projectId);
  const base=path.join(root,'public/data/projects',projectId);
  const expertise=JSON.parse(await fs.readFile(path.join(base,'expertise.json'),'utf8'));
  const check=validateResearchContent(expertise,projectId,pageSpecs);
  const currentReports=await loadCurrentReports(root);
  const target=path.join(root,'public/research/projects',projectId);
  await fs.mkdir(target,{recursive:true});
  await fs.writeFile(path.join(target,'research.css'),STYLE+'\n');
  const rail=projects.map(p=>`<a href="../${p.id}/index.html"${p.id===projectId?' aria-current="page"':''}><i style="--dot:${p.color}"></i>${esc(p.short)}</a>`).join('');
  const navigation=pageSpecs.map(p=>`<a href="./${fileFor(p.id)}">${esc(p.title)}</a>`).join(' · ');
  for(const spec of pageSpecs){
    const page=expertise.pages[spec.id],file=fileFor(spec.id),url=siteOrigin+'/research/projects/'+projectId+'/'+file;
    const sourceSet=new Set(page.sources||[]);
    for(const block of page.blocks)for(const id of block.sourceIds||[])sourceSet.add(id);
    sourceSet.add('report');
    const sources=expertise.sources.filter(s=>sourceSet.has(s.id)).map(s=>`<li id="source-${esc(s.id)}">${link(s.url,s.id==='report'?s.title+' · '+ORIGINAL_REPORT_LABEL:s.note_number?`[${s.note_number}] ${s.title}`:s.title)}${(s.urls||[]).filter(u=>u!==s.url).map(u=>`<p>${link(u,'Дополнительный источник')}</p>`).join('')}</li>`).join('\n');
    const catalogue=spec.id==='overview'?`<section><h2>Разделы исследования и инструменты</h2><div class="section-grid">${pageSpecs.filter(s=>s.id!=='overview').map(s=>`<a href="./${fileFor(s.id)}"><strong>${esc(s.title)}</strong><p>${esc(expertise.pages[s.id].summary)}</p></a>`).join('')}</div></section>`:'';
    const schema={'@context':'https://schema.org','@type':'Article',headline:page.title,description:page.summary,inLanguage:'ru',url,datePublished:expertise.meta.edition_date,isPartOf:{'@type':'WebSite',name:'Национальные проекты – исследовательская платформа',url:siteOrigin+'/'} };
    const clarifications=(expertise.meta.source_clarifications||[]).filter(item=>item.route===spec.id&&(item.text||item.note)).map(item=>`<aside class="note source-clarification"><h2>${esc(item.title||'Примечание к методике')}</h2><p>${esc(item.text||item.note)}</p>${item.source_url?`<p>${link(item.source_url,'Источник'+(item.source_page?', с. '+item.source_page:''))}</p>`:''}</aside>`).join('\n');
    const html=`<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(page.title)} · ${esc(project.name)}</title><meta name="description" content="${esc(page.summary)}"><meta name="robots" content="index,follow"><link rel="canonical" href="${url}"><link rel="icon" href="../../../favicon.png"><link rel="stylesheet" href="../styles.css"><link rel="stylesheet" href="./research.css"><link rel="stylesheet" href="../../current-reports.css"><meta property="og:type" content="article"><meta property="og:locale" content="ru_RU"><meta property="og:title" content="${esc(page.title)}"><meta property="og:description" content="${esc(page.summary)}"><meta property="og:url" content="${url}"><script type="application/ld+json">${JSON.stringify(schema).replaceAll('<','\\u003c')}</script></head>
<body style="--brand:${project.color};${({personnel:'--study-soft:#fff3ec;--study-border:#f1d6ca;--study-ink:#7d2c18;',long_active_life:'--study-soft:#fff1f5;--study-border:#f1cbd8;--study-ink:#7d0f35;--study-table-head:#fff;',health_technologies:'--study-soft:#edf8fc;--study-border:#c5e5f1;--study-ink:#075476;--study-table-head:#fff;',life_infrastructure:'--study-soft:#eef8f2;--study-border:#c5e5d2;--study-ink:#175b38;--study-table-head:#fff;',environment:'--study-soft:#f1f8ee;--study-border:#d2e6c9;--study-ink:#305c2b;--study-table-head:#fff;',competitive_economy:'--study-soft:#fff3f2;--study-border:#edcbcb;--study-ink:#813636;--study-table-head:#fff;',data_economy:'--study-soft:#f3f1ff;--study-border:#d9d2fa;--study-ink:#2e1c88;--study-table-head:#fff;',tourism:'--study-soft:#eef8f6;--study-border:#c7e3df;--study-ink:#175b53;--study-table-head:#fff;',efficient_transport:'--study-soft:#fff8e8;--study-border:#e8d49d;--study-ink:#6e5117;--study-table-head:#fff;',international_export:'--study-soft:#f2f4f7;--study-border:#cbd2db;--study-ink:#253342;--study-table-head:#fff;'})[projectId]||''}"><a class="skip" href="#main">К содержанию</a><header><a class="brand" href="../../../">Исследовательская платформа<span>Национальные проекты</span></a><nav class="rail" aria-label="Национальные проекты">${rail}</nav></header>
<main id="main"><div class="hero"><div><p class="eyebrow">${esc(project.name)}</p><h1>${esc(page.title)}</h1><p class="lead">${esc(page.summary)}</p></div><img class="project-logo" src="../../../assets/brand/${projectId}.svg" alt="Логотип нацпроекта ${esc(project.name)}" width="136" height="116"></div><p><a class="action" href="../../../${projectHref(projectId,spec.id)}">Открыть интерактивную страницу</a></p>
${renderCurrentReportCard(currentReports,projectId,'../../../')}
<aside class="note"><p>Авторская экспертиза: ${esc(expertise.meta.edition_date)}. Статистика исходного исследования: ${esc(expertise.meta.statistical_snapshot)}. Документальный срез: ${esc(expertise.meta.documentary_snapshot)}.</p><p>Обновляемые наблюдения, их периоды и результаты проверки ЕМИСС доступны в интерактивной странице. Содержание авторского отчёта сохраняет свою редакцию.</p></aside>
${catalogue}${clarifications}<article class="article-body">${renderReportBlocks(page,expertise)}</article>
<section><h2>Данные и воспроизведение</h2><p>${link(expertise.meta.report_url,ORIGINAL_REPORT_LABEL)} · ${link(expertise.meta.markdown_url,'Полный текст Markdown')} · ${link('data/projects/'+projectId+'/statistics.json','Текущий статистический набор JSON')} · ${link('data/projects/'+projectId+'/documentary.json','Документальные расчёты JSON')}</p><p><a href="../../../${projectHref(projectId,'library')}">Исходные выгрузки, таблицы, документы и код</a></p></section>
<section><h2>Источники раздела</h2><ol class="source-list">${sources}</ol></section><details><summary>Все страницы проекта</summary><nav class="article-rail" aria-label="Разделы экспертизы">${navigation}</nav></details></main><footer>Экспертиза национального проекта «${esc(project.name)}» · <a href="../../../${projectHref(projectId)}">Интерактивная платформа</a></footer></body></html>\n`;
    await fs.writeFile(path.join(target,file),html);
  }
  const sitemapFile=path.join(root,'public/sitemap.xml');
  let sitemap=await fs.readFile(sitemapFile,'utf8');
  const additions=pageSpecs.map(p=>siteOrigin+'/research/projects/'+projectId+'/'+fileFor(p.id)).filter(url=>!sitemap.includes('<loc>'+url+'</loc>'));
  sitemap=sitemap.replace('</urlset>',additions.map(url=>`  <url><loc>${url}</loc></url>`).join('\n')+'\n</urlset>');
  await fs.writeFile(sitemapFile,sitemap);
  console.log(`Built ${check.routes} ${projectId} research pages: ${check.blocks} source blocks, ${check.figures} figures, ${check.sources} source notes.`);
  return check;
}


