/** Source-linked static pages for the Infrastructure for Life study. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {infrastructurePages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};
export const validateInfrastructureContent=expertise=>validateResearchContent(expertise,'life_infrastructure',infrastructurePages);
export const buildInfrastructurePages=root=>buildResearchPages('life_infrastructure',infrastructurePages,root);
// The inherited catalogue records earlier research stages. Current labels describe
// only the evidence actually published in this release, including methods not used.
const currentMethods={
  theory_of_change:['author_framework_published','Опубликована авторская рамка','Критерии экспертизы и предполагаемые механизмы перенесены из отчёта. Теория изменений сама по себе не подтверждает причинный эффект.'],
  project_hierarchy:['source_structure_extracted','Структура извлечена из паспортов','Национальный проект и федеральные проекты сохраняют собственные документы, редакции и адреса карточек.'],
  activity_inventory:['source_inventory_extracted','Реестр извлечён из источников','Цели, задачи, результаты и показатели различаются. Повтор задачи в структуре национального проекта маркируется отдельно.'],
  activity_indicator_links:['source_relationships_audited','Документальные связи проверены','Общая задача, принадлежность проекту и текстовое сходство показаны раздельно. Неразрешённые ссылки и веса не назначаются произвольной паре.'],
  source_quality:['source_specific_contracts_verified','Контракты источников проверены','Исходные ячейки и подписи сохранены. Единицы, периоды, пропуски, будущие даты и синхронные нули проверяются по контракту каждого источника.'],
  observability:['computed_from_source_packets','Покрытие рассчитано по выгрузкам','Карточки каталога и независимые источники различаются. Числа, пропуски и исключения считаются отдельно.'],
  time_dynamics:['computed_matching_frequency_category','Рассчитана сопоставимая динамика','Сравниваются одинаковые категории, частоты и календарные горизонты. Для индекса 62872 временное сравнение заблокировано из-за изменения методики.'],
  target_comparison:['documented_annual_comparisons','Выполнены годовые сопоставления','Годовые факты и явно обозначенное полное ипотечное накопление сравниваются с датированной редакцией цели. Это не подтверждает выполнение первоначального задания.'],
  forecasting:['model_not_validated','Прогнозная модель не подтверждена','Доступны условные траектории при заданных предпосылках. Вероятности достижения целей и качество прогнозной модели не установлены.'],
  geographical_join:['explicit_scope_mapping','Территории сопоставлены явно','Исходные названия сохранены. Строки без автономных округов отделены от агрегатов; неуточнённый территориальный охват отмечен.'],
  regional_maps:['matched_source_slices','Показаны сопоставимые срезы','Каждая карта относится к одному источнику, периоду, частоте и категории. Отсутствующие значения не заменяются нулём.'],
  regional_descriptive:['unweighted_regions','Рассчитаны региональные распределения','Квантили type 7 и невзвешенное среднее относятся к сопоставимым территориям. Показатель России берётся из источника.'],
  correlations:['author_82_strict_80_recomputed','Корреляции пересчитаны','Шесть характеристик сопоставлены на авторской выборке из 82 территорий и строгой выборке из 80. Импутация не применяется; корреляция не устанавливает эффект.'],
  pca:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Анализ главных компонент не включён в подтверждённые результаты данной экспертизы.'],
  kmeans:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Кластерная типология и интегральный рейтинг не установлены.'],
  multivariate_stability:['explicit_geographic_sensitivity','Проверена чувствительность к составу территорий','Корреляции на 82 и 80 территориях сопоставляются при сохранении исходных единиц, частот и периодов каждого признака.'],
  isolation_forest:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Модель Isolation Forest не обучалась. Контроль исходных значений не обозначается машинным поиском аномалий.'],
  moran_global:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Глобальный индекс Moran I и пространственная значимость не оценивались.'],
  moran_local:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Локальные пространственные ассоциации LISA не оценивались.'],
  regional_similarity:['descriptive_profiles','Доступно сопоставление профилей','Профили жилищных и транспортных условий сопоставляются описательно. Сеть сходства не выдаётся за выявленную типологию.'],
  relative_profiles:['descriptive_source_values','Показаны исходные региональные значения','Профили сохраняют единицы, частоты, годы и территориальный охват источников. Сводный рейтинг не строится.'],
  budget_registry:['plans_reconciled','Планы извлечены и сверены','Паспортный план 2025–2030 годов отделён от ассигнований и бюджетных предложений 2026–2029 годов. Разница сумм НП и ФП раскрыта; кассовое исполнение не установлено.'],
  budget_hhi:['computed_source_scope','Доли и HHI рассчитаны','Индекс концентрации относится к выбранной сопоставимой финансовой рамке и не измеряет эффективность расходов.'],
  budget_observability:['descriptive_documentary_audit','Выполнен документальный анализ','Показаны структура ресурсов, результатов и измерений. Стоимость причинного эффекта и бюджетная результативность не оценены.'],
  activity_network:['evidence_classes_separated','Классы связей разделены','Документальная принадлежность и кандидаты по смысловому сходству доступны раздельно. Центральность и причинная сила связи не заявляются.'],
  lexical_frequencies:['fixed_corpus_recomputed','Частоты корпуса пересчитаны','Независимая обработка фиксированного корпуса воспроизводима. Отличия от чисел отчёта раскрыты; исходный авторский код отсутствует.'],
  dictionary_frames:['dictionary_frames_recomputed','Словарные рамки рассчитаны','Совпадения проверяются в контексте. Частота слов не измеряет результативность политики.'],
  tfidf_cosine:['independent_sensitivity_recomputed','Сходство пересчитано в шести спецификациях','Представления текста и способ объединения документов заданы явно. Лексическое сходство не подтверждает содержательное или причинное тождество.'],
  text_clustering:['not_computed','Кластеризация не выполнялась','Матрица близости и ранжирование соседей не обозначаются иерархической кластеризацией.'],
  concept_cooccurrence:['not_computed','Отдельная модель не рассчитывалась','Опубликованы словарные частоты и контексты. Отдельная сеть совместного присутствия понятий не оценена.'],
  context_search:['source_contexts_published','Контексты доступны для проверки','Совпадение связано с документом и исходным фрагментом. Тексты загружаются по запросу.'],
  domain_evidence:['author_qualitative_analysis_published','Опубликован предметный анализ','Авторские выводы о жилищных, коммунальных, транспортных и пространственных условиях связаны с исходными разделами отчёта.'],
  expert_domain_scale:['not_computed','Шкала 0–4 не рассчитывалась','Числовые экспертные оценки не добавлены без исходного протокола и выставленных автором баллов.'],
  policy_scenario_framework:['conditional_arithmetic_no_causal_effect','Условный расчёт','Сценарии зависят от задаваемых предпосылок. Расчёт не оценивает причинный вклад национального проекта.'],
  causal_designs:['design_proposed_effect_not_identified','Предложен дизайн оценки','Авторские предложения по идентификации эффекта опубликованы. Контрфактическая оценка по доступным данным не выполнена.'],
  heterogeneous_causal_effects:['effect_not_identified','Причинный эффект не установлен','Causal forests и double machine learning не обучались; неоднородность причинного эффекта не оценена.'],
  recommendations:['author_synthesis_published','Опубликованы авторские предложения','Выводы и рекомендации сохраняют статус авторской экспертизы и собственные основания.'],
  cohort_projection:['not_implemented_without_population_inputs','Нет данных для когортной проекции','Для этой экспертизы нет согласованного комплекта половозрастных входов. Жилищная декомпозиция H/N не заменяет когортную передвижку.'],
  interactive_lab:['source_backed_reproducible_calculations','Доступны воспроизводимые расчёты','Динамика, распределения и корреляции используют проверенные наблюдения. Дополнительные калькуляторы и сценарии обозначают пользовательские предпосылки.']
};
export async function buildInfrastructureFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/life_infrastructure');
  const read=async file=>JSON.parse(await fs.readFile(path.join(directory,file+'.json'),'utf8'));
  const [foundation,expertise,methods,pkg]=await Promise.all([read('foundation'),read('expertise'),read('methods'),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse)]);
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
  methods.current_review_basis='published_infrastructure_sources_report_and_independent_recalculation';
  for(const item of methods.items){
    const current=currentMethods[item.method_id];
    if(!current)throw Error('Infrastructure method needs an explicit current status: '+item.method_id);
    [item.current_status,item.current_status_label,item.current_limitations]=current;
  }
  await fs.writeFile(path.join(directory,'methods.json'),JSON.stringify(methods,null,2)+'\n');
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildInfrastructurePages();
