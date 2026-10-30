/** Shared, source-backed links for the current author editions of all studies. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {projects} from '../src/platform/projects.js';

export const CURRENT_REPORT_SCHEMA='national-projects.current-reports/1';
export const ORIGINAL_REPORT_LABEL='Исходный отчёт расчётной версии (DOCX)';
export const escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');

/** Only package-relative document paths are accepted; deployment prefixes stay intact. */
export function validateCurrentReports(manifest){
  if(manifest?.schema!==CURRENT_REPORT_SCHEMA||!Array.isArray(manifest.reports))throw Error('Invalid current-report catalogue schema');
  if(!/^\d{4}-\d{2}-\d{2}$/.test(manifest.edition_date||'')||Number.isNaN(Date.parse(manifest.edition_date))||new Date(manifest.edition_date).toISOString().slice(0,10)!==manifest.edition_date)throw Error('Current reports require an edition date');
  const ids=new Set();
  for(const report of manifest.reports){
    if(!projects.some(project=>project.id===report.project_id)||ids.has(report.project_id))throw Error('Unknown or repeated current-report project: '+report.project_id);
    ids.add(report.project_id);
    if(!report.title?.trim()||!report.edition_label?.trim()||report.edition_date!==manifest.edition_date)throw Error('Incomplete current-report identity: '+report.project_id);
    for(const format of ['pdf','docx']){
      const file=report[format];
      const expectedPrefix=`downloads/projects/${report.project_id}/current/`;
      if(!file?.url?.startsWith(expectedPrefix)||!file.url.endsWith('.'+format)||!/^downloads\/[A-Za-z0-9_./-]+$/.test(file.url)||file.url.split('/').some(part=>part==='.'||part==='..'))throw Error('Unsafe current-report '+format+' URL: '+report.project_id);
      if(!Number.isInteger(file.bytes)||file.bytes<=0||!/^[a-f\d]{64}$/.test(file.sha256||''))throw Error('Missing current-report file provenance: '+report.project_id);
    }
    if(!Number.isInteger(report.pdf.pages)||report.pdf.pages<1)throw Error('Missing PDF page count: '+report.project_id);
  }
  if(ids.size!==projects.length)throw Error('Current-report catalogue must cover all '+projects.length+' projects');
  return manifest;
}

export async function loadCurrentReports(root=path.resolve(import.meta.dirname,'..')){
  return validateCurrentReports(JSON.parse(await fs.readFile(path.join(root,'public/data/current-reports.json'),'utf8')));
}

export function currentReportFor(manifest,projectId){
  const report=manifest.reports.find(item=>item.project_id===projectId);
  if(!report)throw Error('Missing current report: '+projectId);
  return report;
}

export const documentSize=bytes=>new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(bytes/1_000_000)+' МБ';

export function renderReportDownloadLinks(report,publicPrefix){
  if(!/^(?:\.\.\/)+$/.test(publicPrefix)&&publicPrefix!=='./')throw Error('Invalid publication prefix');
  const esc=escapeHtml;
  return `<div class="current-report-actions"><a class="current-report-pdf" href="${esc(publicPrefix+report.pdf.url)}" type="application/pdf">Открыть PDF <span>${report.pdf.pages} стр. · ${esc(documentSize(report.pdf.bytes))}</span></a><a href="${esc(publicPrefix+report.docx.url)}" download>Скачать DOCX <span>${esc(documentSize(report.docx.bytes))}</span></a></div>`;
}

export function renderCurrentReportCard(manifest,projectId,publicPrefix){
  const report=currentReportFor(manifest,projectId),esc=escapeHtml;
  return `<aside class="current-report" data-current-report="${esc(projectId)}" aria-labelledby="current-report-title"><h2 id="current-report-title">Актуальная редакция экспертизы</h2><p><time datetime="${esc(report.edition_date)}">${esc(report.edition_label)}</time>. Полный авторский отчёт.</p>${renderReportDownloadLinks(report,publicPrefix)}<p class="current-report-catalogue"><a href="${esc(publicPrefix+'research/reports.html')}">Все ${manifest.reports.length} экспертиз национальных проектов</a></p></aside>`;
}

export const CURRENT_REPORT_STYLES=`.current-report{margin:26px 0;padding:22px 24px;border:1px solid #d8e0eb;border-left:4px solid var(--brand,#2947a0);border-radius:10px;background:#f8fafc}.current-report h2{font-size:22px;line-height:1.3;margin:0 0 10px;color:#192638}.current-report p{margin:8px 0;color:#526071}.current-report-actions{display:flex;flex-wrap:wrap;align-items:stretch;gap:10px;margin:16px 0}.current-report-actions a{display:flex;flex-direction:column;justify-content:center;gap:2px;min-height:52px;padding:10px 15px;border:1px solid #cbd5e2;border-radius:7px;background:#fff;color:#1f3656;text-decoration:none;font-weight:600;line-height:1.4}.current-report-actions a span{font-size:12px;font-weight:400}.current-report-actions .current-report-pdf{background:#233d60;color:#fff;border-color:#233d60}.current-report-actions a:hover{text-decoration:underline}.current-report-actions a:focus-visible,.current-report-catalogue a:focus-visible{outline:3px solid #2947a0;outline-offset:3px}.current-report .current-report-catalogue{font-size:14px;margin:12px 0 0}.current-report-catalogue a{color:#2947a0}@media(max-width:620px){.current-report{padding:18px 16px}.current-report h2{font-size:21px}.current-report-actions a{flex:1 1 135px}}`;
