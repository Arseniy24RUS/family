import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { sections } from '../src/content/sections.js';

const root=path.resolve(import.meta.dirname,'..');
export const siteOrigin='https://xn-----6kcba0adcljuh3ahqihlhjqil4g2hb3f.xn--p1ai';
const siteName='Экспертиза национального проекта «Семья»';
const esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const sectionLinks=()=>sections.map(s=>`<li><a href="./${s.id}.html">${esc(s.title)}</a><p>${esc(s.description)}</p></li>`).join('\n');
const paragraph=(title,value)=>value?`<section><h2>${esc(title)}</h2><p>${esc(value)}</p></section>`:'';
function page(file,title,description,body){
  const url=`${siteOrigin}/research/${file}`;
  const structured={'@context':'https://schema.org','@type':'WebPage',name:title,description,url,inLanguage:'ru',isPartOf:{'@type':'WebSite',name:siteName,url:siteOrigin+'/'}};
  return `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)} — ${esc(siteName)}</title>
<meta name="description" content="${esc(description)}"><meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${url}"><link rel="icon" href="../favicon.png" type="image/png" sizes="120x120"><link rel="stylesheet" href="./styles.css">
<meta property="og:type" content="article"><meta property="og:locale" content="ru_RU"><meta property="og:site_name" content="${esc(siteName)}">
<meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(description)}"><meta property="og:url" content="${url}">
<script type="application/ld+json">${JSON.stringify(structured).replaceAll('<','\\u003c')}</script></head>
<body><a class="skip" href="#main">К содержанию</a><header><a href="../">${esc(siteName)}</a><nav aria-label="Навигация"><a href="./index.html">Тексты исследований</a><a href="../#/authors">Авторы</a><a href="../#/library">Данные и источники</a></nav></header>
<main id="main"><h1>${esc(title)}</h1><p class="lead">${esc(description)}</p>${body}</main>
<footer>Институт социальной демографии ФНИСЦ РАН · <a href="../">Интерактивная платформа</a></footer></body></html>\n`;
}

export async function buildSeo(){
  const output=path.join(root,'public/research');
  await fs.mkdir(output,{recursive:true});
  await fs.writeFile(path.join(output,'styles.css'),`*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#0a132d;font:17px/1.65 "Segoe UI",Arial,sans-serif}a{color:#2947a0;text-underline-offset:3px}header,main,footer{max-width:1000px;margin:auto;padding:28px}header{display:flex;flex-wrap:wrap;gap:20px;justify-content:space-between;border-bottom:1px solid #d9dee8}header>a{font-weight:700;max-width:440px}nav{display:flex;flex-wrap:wrap;gap:18px}main{background:#fff;border:1px solid #d9dee8;margin-top:28px;border-radius:16px;padding:clamp(22px,5vw,56px)}h1{font-size:clamp(29px,5vw,44px);line-height:1.2;color:#031e4f}h2{font-size:24px;line-height:1.3;margin-top:32px}.lead{font-size:20px;color:#647087}p{overflow-wrap:anywhere}li{padding:8px 0}li p{margin:5px 0;color:#647087}.action{display:inline-block;background:#031e4f;color:white;padding:12px 20px;border-radius:8px}.note{padding:18px;background:#f4f6fa;border-left:4px solid #2947a0}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:20px;background:#f4f6fa;border-radius:8px;font-size:14px}.skip{position:absolute;left:-9999px}.skip:focus{left:12px;top:8px;background:white;padding:8px}footer{font-size:14px;color:#647087}@media(max-width:600px){header,footer{padding:20px}main{margin:12px;border-radius:12px}nav{font-size:15px}}\n`);
  await fs.writeFile(path.join(output,'index.html'),page('index.html','Тексты исследований','Методика, результаты и ограничения 12 исследований национального проекта «Семья».',`<p>Текстовые материалы дополняют интерактивные карты, таблицы и расчёты платформы. В каждом разделе представлены метод, исходные данные, авторский вывод и ограничения.</p><p class="note">Документальная экспертиза от 14 мая 2026 года. Авторы: Ростовская Т.К., Ситковский А.М., Синельников А.Б., Архангельский В.Н. Обновляемая статистика ЕМИСС и прогнозы доступны в интерактивной платформе.</p><ol>${sectionLinks()}</ol>`));
  for(const s of sections){
    const m=s.method;
    const body=`<p><a class="action" href="../#/${s.id}">Открыть интерактивное исследование</a></p><p class="note">Документальная экспертиза от 14 мая 2026 года · раздел ${Number(s.n)}, с. ${esc(s.pages)}. Авторские выводы относятся к исходному срезу; актуальные статистические ряды имеют собственные даты источников.</p>`+
      paragraph('Метод: '+m.name,m.simple)+paragraph('Схема метода',m.formula)+paragraph('Для каких задач подходит',m.why)+paragraph('Исходные данные',m.inputs)+paragraph('Воспроизведение расчётов',m.python)+
      (m.code?`<pre><code>${esc(m.code)}</code></pre>`:'')+paragraph('Ограничения интерпретации',m.caveat)+paragraph('Вывод авторов',s.finding)+paragraph('Предложение авторов',s.proposal)+
      `<p><a href="../downloads/expertise_2026-05-14.docx">Скачать полный исходный отчёт (Word)</a></p><details><summary>Все разделы исследования</summary><ol>${sectionLinks()}</ol></details>`;
    await fs.writeFile(path.join(output,s.id+'.html'),page(s.id+'.html',s.title,s.description,body));
  }
  const urls=['/','/research/index.html',...sections.map(s=>`/research/${s.id}.html`)];
  await fs.writeFile(path.join(root,'public/sitemap.xml'),`<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map(url=>`  <url><loc>${siteOrigin}${url}</loc></url>`).join('\n')}\n</urlset>\n`);
  await fs.writeFile(path.join(root,'public/robots.txt'),`User-agent: *\nAllow: /\n\nSitemap: ${siteOrigin}/sitemap.xml\n`);
  console.log(`Built ${urls.length} indexable URLs with self-referencing canonical links.`);
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))await buildSeo();
