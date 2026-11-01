/** Source-linked static pages for the Infrastructure for Life study. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {infrastructurePages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};
export const validateInfrastructureContent=expertise=>validateResearchContent(expertise,'life_infrastructure',infrastructurePages);
export const buildInfrastructurePages=root=>buildResearchPages('life_infrastructure',infrastructurePages,root);
// Editorial statuses are versioned separately from calculated method metadata.
// Both the analytics step and this publication step use the same review file.
export function applyInfrastructureMethodReview(methods,review){
  const fields=['current_status','current_status_label','current_limitations'];
  if(review.schema_version!==1||review.project_id!=='life_infrastructure'||methods.project_id!==review.project_id)
    throw Error('Infrastructure method review has an unsupported schema or project');
  if(typeof review.current_review_basis!=='string'||!review.current_review_basis.trim())
    throw Error('Infrastructure method review needs a review basis');
  if(!Array.isArray(review.items)||!Array.isArray(methods.items))
    throw Error('Infrastructure method review and catalogue need item arrays');
  const editorial=new Map();
  for(const item of review.items){
    if(typeof item.method_id!=='string'||!item.method_id.trim()||editorial.has(item.method_id))
      throw Error('Infrastructure method review has a missing or duplicate method id');
    if(Object.keys(item).length!==fields.length+1||fields.some(key=>typeof item[key]!=='string'||!item[key].trim()))
      throw Error('Infrastructure method review needs exactly three nonempty editorial fields: '+item.method_id);
    editorial.set(item.method_id,item);
  }
  const ids=new Set();
  for(const item of methods.items){
    if(ids.has(item.method_id)||!editorial.has(item.method_id))
      throw Error('Infrastructure method catalogue has a duplicate or unreviewed method: '+item.method_id);
    ids.add(item.method_id);
  }
  if(ids.size!==editorial.size)throw Error('Infrastructure method review contains methods absent from the catalogue');
  // Validate the entire review before changing any field. Computed values stay intact.
  for(const item of methods.items)for(const field of fields)item[field]=editorial.get(item.method_id)[field];
  methods.current_review_basis=review.current_review_basis;
  return methods;
}
export async function buildInfrastructureFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/life_infrastructure');
  const read=async file=>JSON.parse(await fs.readFile(path.join(directory,file+'.json'),'utf8'));
  const [foundation,expertise,methods,pkg,review]=await Promise.all([read('foundation'),read('expertise'),read('methods'),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse),
    fs.readFile(path.join(root,'scripts/infrastructure_method_review.json'),'utf8').then(JSON.parse)]);
  foundation.release_version=pkg.version;
  foundation.release_date='2026-10-29';
  foundation.author_expertise_status='published';
  foundation.documentary_as_of=expertise.meta.documentary_snapshot;
  foundation.sections=expertiseBlueprint.map(section=>({...section,section_id:section.id,
    title:expertise.pages[section.id].title,publication_status:'published',
    evidence:expertise.pages[section.id].summary}));
  if(foundation.research)foundation.research.author_expertise_text_status='published';
  const report={title:'Авторская экспертиза национального проекта «Инфраструктура для жизни»',
    url:expertise.meta.report_url,format:'DOCX',edition_date:expertise.meta.edition_date,
    qualification:'Исходный отчёт сохранён полностью. Статистические срезы, паспортные планы и авторские выводы имеют собственные даты и источники.'};
  foundation.sources=[report,...(foundation.sources||[]).filter(source=>source.url!==report.url)];
  foundation.interpretation='Опубликованы полный авторский отчёт и воспроизводимые расчёты. Дата сборки сайта не означает обновление первичных данных. Для каждого ряда доступны период наблюдения, источник и результат последней попытки прямого обновления.';
  methods.release_version=pkg.version;
  applyInfrastructureMethodReview(methods,review);
  await fs.writeFile(path.join(directory,'methods.json'),JSON.stringify(methods,null,2)+'\n');
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildInfrastructurePages();
