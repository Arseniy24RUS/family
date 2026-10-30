/** Publish the shared document catalogue independently of the interactive app. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {projects,projectHref} from '../src/platform/projects.js';
import {siteOrigin} from './build-seo.mjs';
import {loadCurrentReports,currentReportFor,renderReportDownloadLinks,escapeHtml as esc,CURRENT_REPORT_STYLES} from './current_reports.mjs';

const ROOT=path.resolve(import.meta.dirname,'..');
const STYLE=`.reports-intro{max-width:800px}.reports-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:28px 0}.report-document{min-width:0;display:flex;flex-direction:column;padding:24px;border:1px solid #dce2ec;border-top:4px solid var(--report-color);border-radius:11px;background:#fff}.report-document-heading{display:flex;align-items:flex-start;gap:17px}.report-document-heading img{flex:none;object-fit:contain;width:87px;height:73px}.report-document h2{margin:0;font-size:22px;line-height:1.3;overflow-wrap:anywhere}.report-document time{display:block;margin:13px 0 0;font-size:14px;color:#526071}.report-document .current-report-actions{margin-top:auto;padding-top:16px}.report-document>p{margin:8px 0 0;font-size:14px}.report-document .current-report-actions a{flex:1 1 125px}.reports-page header{align-items:center}.reports-page main{max-width:1120px}.reports-page header>a{font-size:21px;text-decoration:none}.reports-page main>h1{max-width:900px}.reports-page footer{max-width:1120px}@media(max-width:720px){.reports-grid{grid-template-columns:1fr}.report-document{padding:20px}.report-document h2{font-size:21px}.report-document-heading img{width:76px;height:64px}.reports-page main{padding:22px}.reports-page header>a{font-size:19px}}`;

export async function buildReportsCatalogue(root=ROOT){
  const manifest=await loadCurrentReports(root);
  const output=path.join(root,'public/research');
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'current-reports.css'),CURRENT_REPORT_STYLES+'\n');
  await fs.writeFile(path.join(output,'reports-catalogue.css'),STYLE+'\n');
  const cards=projects.map(project=>{
    const report=currentReportFor(manifest,project.id);
    return `<article class="report-document" id="${esc(project.id)}" style="--report-color:${esc(project.color)}"><div class="report-document-heading"><img src="../assets/brand/${esc(project.id)}.svg" width="87" height="73" alt="Официальный логотип нацпроекта ${esc(project.name)}"><div><h2>${esc(project.name)}</h2><time datetime="${esc(report.edition_date)}">${esc(report.edition_label)}</time></div></div>${renderReportDownloadLinks(report,'../')}<p><a href="../${projectHref(project.id)}">Интерактивное исследование</a> · <a href="${project.id==='family'?'./index.html':'./projects/'+project.id+'/index.html'}">Текстовые страницы</a></p></article>`;
  }).join('\n');
  const title='Экспертизы национальных проектов';
  const description=`Полные авторские отчёты по ${manifest.reports.length} национальным проектам. ${manifest.reports[0].edition_label}. Актуальные PDF и исходные файлы DOCX.`;
  const url=siteOrigin+'/research/reports.html';
  const schema={'@context':'https://schema.org','@type':'CollectionPage',name:title,description,url,inLanguage:'ru',dateModified:manifest.edition_date,mainEntity:{'@type':'ItemList',numberOfItems:manifest.reports.length,itemListElement:projects.map((project,i)=>({'@type':'ListItem',position:i+1,name:project.name,url:url+'#'+project.id}))}};
  await fs.writeFile(path.join(output,'reports.html'),`<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title} · Исследовательская платформа</title><meta name="description" content="${esc(description)}"><meta name="robots" content="index,follow"><link rel="canonical" href="${url}"><link rel="icon" href="../favicon.png"><link rel="stylesheet" href="./styles.css"><link rel="stylesheet" href="./current-reports.css"><link rel="stylesheet" href="./reports-catalogue.css"><script type="application/ld+json">${JSON.stringify(schema).replaceAll('<','\\u003c')}</script></head><body class="reports-page"><a class="skip" href="#main">К содержанию</a><header><a href="../">Национальные проекты России · Исследовательская платформа</a><nav aria-label="Навигация"><a href="../#/overview">Интерактивная платформа</a></nav></header><main id="main"><h1>${title}</h1><p class="lead reports-intro">${esc(description)}</p><p class="reports-intro">Выберите национальный проект, чтобы открыть полный отчёт в PDF или скачать авторский файл DOCX. Текстовые страницы, данные и расчёты каждого исследования доступны по отдельным ссылкам.</p><div class="reports-grid">${cards}</div></main><footer>Институт социальной демографии ФНИСЦ РАН · <a href="../">Интерактивная платформа</a></footer></body></html>\n`);
  const sitemapFile=path.join(root,'public/sitemap.xml');
  let sitemap=await fs.readFile(sitemapFile,'utf8');
  if(!sitemap.includes('<loc>'+url+'</loc>')){
    sitemap=sitemap.replace('</urlset>',`  <url><loc>${url}</loc></url>\n</urlset>`);
    await fs.writeFile(sitemapFile,sitemap);
  }
  console.log(`Built current-report catalogue: ${manifest.reports.length} PDF and DOCX editions.`);
  return {reports:manifest.reports.length,pages:manifest.reports.reduce((sum,report)=>sum+report.pdf.pages,0)};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await buildReportsCatalogue();
