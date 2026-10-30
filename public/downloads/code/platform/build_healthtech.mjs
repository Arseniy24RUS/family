/** Source-linked static pages for the health-technology national project. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {healthtechPages,expertiseBlueprint,getProject} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};
export const validateHealthtechContent=expertise=>validateResearchContent(expertise,'health_technologies',healthtechPages);
export const buildHealthtechPages=root=>buildResearchPages('health_technologies',healthtechPages,root);

/** Derive the new project's entry metadata from its own current evidence. */
export async function buildHealthtechFoundation(root=path.resolve(import.meta.dirname,'..')){
  const id='health_technologies',directory=path.join(root,'public/data/projects',id);
  const read=async name=>JSON.parse(await fs.readFile(path.join(directory,name+'.json'),'utf8'));
  const [statistics,expertise,methods]=await Promise.all([read('statistics'),read('expertise'),read('methods')]);
  const summary=statistics.summary;
  if(!summary||!Array.isArray(statistics.sources))throw Error('Missing health-technology statistics summary.');
  const pkg=JSON.parse(await fs.readFile(path.join(root,'package.json'),'utf8'));
  const project=getProject(id);
  const registry={n_registry:summary.registry_indicators,n_with_numeric:summary.available_sources,
    n_with_regional:summary.regional_sources,n_with_national:summary.available_sources,
    n_unique_cells:summary.observations,n_numeric:summary.numeric_observations,
    coverage_pct:100*summary.available_sources/summary.registry_indicators};
  const foundation={schema_version:1,project_id:id,project_name:project.name,
    release_version:pkg.version,release_date:'2026-10-29',author_expertise_status:'published',
    statistical_as_of:statistics.meta.statistical_as_of,documentary_as_of:expertise.meta.documentary_snapshot,
    registry,method_summary:{total:methods.items.length},
    sections:expertiseBlueprint.map((section,index)=>({order:index+1,section_id:section.id,
      title:expertise.pages[section.id].title,publication_status:'published',evidence:expertise.pages[section.id].summary})),
    sources:[{title:'Авторская экспертиза национального проекта «Новые технологии сбережения здоровья»',
      url:expertise.meta.report_url,format:'DOCX',edition_date:expertise.meta.edition_date,
      qualification:'Исходный отчёт сохранён без изменения байтов. Расчёты и ссылки привязаны к его редакции.'},
      {title:'ЕМИСС: реестр установленных показателей',url:'https://www.fedstat.ru/',format:'Статистический реестр',
        qualification:'Связь с каждой карточкой и состояние прямого обновления раскрыты в реестре источников.'},
      {title:'Репозиторий НЦСЭД: сохранённые публикации ЕМИСС',url:'https://repository.nsedc.ru/',format:'XLS и CSV',
        retrieved_at:statistics.meta.acquired_at,qualification:'Вторичная публикация исходных файлов. Дата получения и дата обновления данных в паспорте файла сохраняются отдельно.'}],
    downloads:[],
    note:'Проект добавлен к исходным одиннадцати. Реестр исследовательского выпуска 1.2.0 сохранён в его исходном объёме. Национальные данные не образуют региональную панель.'};
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildHealthtechPages();
