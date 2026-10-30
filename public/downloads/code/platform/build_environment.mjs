/** Publish the Environment study with explicitly scoped current evidence. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {environmentPages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};
export const validateEnvironmentContent=expertise=>validateResearchContent(expertise,'environment',environmentPages);
export const buildEnvironmentPages=root=>buildResearchPages('environment',environmentPages,root);

const currentMethods={
  theory_of_change:['author_framework_published','Опубликована авторская рамка','Различаются мероприятия, изменение экологической нагрузки, состояние природной среды и общественный результат. Предполагаемый механизм не подтверждает причинный эффект.'],
  project_hierarchy:['source_structure_extracted','Структура извлечена из паспортов','Семь паспортов охватывают национальный проект и шесть федеральных направлений. Дата републикации не заменяет дату утверждения редакции.'],
  activity_inventory:['source_inventory_extracted','Реестр извлечён из источников','Цели, задачи, результаты и показатели имеют отдельные записи и ссылки на источник. Повторение задачи на разных уровнях отмечено явно.'],
  activity_indicator_links:['source_relationships_audited','Документальные связи проверены','Принадлежность задаче, ссылка влияния и текстовое сходство разделены. Неразрешённые ссылки сохраняются без назначения произвольного адресата.'],
  source_quality:['source_specific_contracts_verified','Проверены определения источников','Исходные значения и подписи сохранены. Доли ТКО вне 0–100 исключаются из расчётов. Отношение лесовосстановления может превышать 100%.'],
  observability:['computed_from_source_packets','Покрытие рассчитано по выгрузкам','Числа, пропуски, исключения, самостоятельные годовые факты и территориальный охват подсчитаны раздельно.'],
  time_dynamics:['computed_matching_frequency_category','Рассчитана сопоставимая динамика','Сопоставляются одинаковые категории и горизонты наблюдения. Год, месяц, накопление с начала года и накопление с начала проекта различаются.'],
  target_comparison:['documented_annual_comparisons','Выполнены допустимые годовые сопоставления','Самостоятельный годовой факт сопоставляется с датированной редакцией плана. Редакция октября 2026 года не удостоверяет выполнение первоначального задания на 2025 год.'],
  forecasting:['model_not_validated','Прогнозная модель не подтверждена','Условные плановые траектории зависят от явно заданных предпосылок. Вероятность достижения цели и точность прогноза не оценены.'],
  geographical_join:['explicit_scope_mapping','Территории сопоставлены явно','Исходные подписи сохранены. Субъекты Федерации, агрегаты и две группы городов проекта «Чистый воздух» рассматриваются раздельно.'],
  regional_maps:['matched_source_slices','Показаны сопоставимые срезы','Карта относится к одному источнику, периоду, частоте и категории. Отсутствие значения показано отдельно от нуля.'],
  regional_descriptive:['unweighted_regions','Рассчитаны региональные распределения','Средние и квантили регионов не взвешены по массе отходов, площади или населению. Значение Российской Федерации берётся из источника.'],
  correlations:['waste_spearman_with_sensitivity','Ранговая связь долей ТКО пересчитана','Основная совокупность 2025 года включает 85 субъектов. Отдельная проверка исключает исходную пару 0/0 Еврейской автономной области и охватывает 84 субъекта.'],
  pca:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Анализ главных компонент не включён в подтверждённые результаты опубликованной экспертизы.'],
  kmeans:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Кластерная типология и интегральный рейтинг экологичности не установлены.'],
  multivariate_stability:['explicit_sample_sensitivity','Проверена чувствительность к составу выборки','Сопоставлены коэффициенты Спирмена для 85 и 84 субъектов. Проверка касается указанной пары показателей и не подтверждает многомерную типологию.'],
  isolation_forest:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Модель Isolation Forest не обучалась. Контроль допустимых значений выполняется по определению каждого показателя.'],
  moran_global:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Глобальный индекс Moran I и пространственная значимость не оценивались.'],
  moran_local:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Локальные пространственные ассоциации LISA не оценивались.'],
  regional_similarity:['descriptive_profiles','Доступно сопоставление профилей','Региональные сочетания обработки и захоронения отходов рассматриваются описательно. Сходство профилей не устанавливает одинаковый экологический результат.'],
  relative_profiles:['descriptive_source_values','Показаны исходные региональные значения','Показатели сохраняют свои единицы, периоды и знаменатели. Для городских групп используются разные базовые годы.'],
  budget_registry:['plans_reconciled','Финансовые планы извлечены и сверены','Паспортные планы всех источников на 2025–2030 годы отделены от росписи 2026 года и бюджетных предложений на 2027–2029 годы. Кассовое исполнение не установлено.'],
  budget_hhi:['computed_source_scope','Доли и HHI рассчитаны','Индекс концентрации описывает распределение паспортного финансирования между федеральными проектами. Экологическую эффективность расходов он не измеряет.'],
  budget_observability:['descriptive_documentary_audit','Выполнен документальный анализ','Ресурсы и измеряемые результаты сопоставлены в пределах своих финансовых рамок. Стоимость предотвращённого ущерба и причинного эффекта не рассчитана.'],
  activity_network:['evidence_classes_separated','Классы связей разделены','Документальные связи и смысловые кандидаты имеют разные основания. Причинная сила ребра и влияние узла не назначаются автоматически.'],
  lexical_frequencies:['fixed_corpus_recomputed','Частоты корпуса пересчитаны','Расчёт использует сохранённый корпус и опубликованные параметры. Расхождения с авторскими числами показаны отдельно, исходный авторский код отсутствует.'],
  dictionary_frames:['dictionary_frames_recomputed','Словарные рамки рассчитаны','Совпадения доступны в исходном контексте. Частота тематической лексики не измеряет фактическое состояние окружающей среды.'],
  tfidf_cosine:['independent_sensitivity_recomputed','Сходство пересчитано в шести спецификациях','Параметры представления текста и объединения уровней документов раскрыты. Лексическая близость не устанавливает содержательное тождество проектов.'],
  text_clustering:['not_computed','Кластеризация не выполнялась','Матрица близости и ранжирование соседей не обозначаются иерархической кластеризацией.'],
  concept_cooccurrence:['not_computed','Отдельная модель не рассчитывалась','Опубликованы тематические частоты и контексты. Отдельная модель совместного присутствия понятий не оценена.'],
  context_search:['source_contexts_published','Контексты доступны для проверки','Фрагмент связан с исходным документом. Полные тексты загружаются по запросу.'],
  domain_evidence:['author_qualitative_analysis_published','Опубликован предметный анализ','Выводы по отходам, воздуху, воде, накопленному загрязнению, лесам и биоразнообразию связаны с соответствующими разделами авторского отчёта.'],
  expert_domain_scale:['not_computed','Шкала 0–4 не рассчитывалась','Числовые экспертные баллы не добавлены без исходного протокола и выставленных автором оценок.'],
  policy_scenario_framework:['conditional_arithmetic_no_causal_effect','Доступны условные расчёты','Баланс отходов, сокращение относительно базового уровня и концентрация с весами по населению зависят от введённых предпосылок. Причинный вклад проекта не оценён.'],
  causal_designs:['design_proposed_effect_not_identified','Предложен дизайн оценки','Авторские предложения по определению дополнительного эффекта опубликованы. Контрфактическая оценка по доступным данным не выполнена.'],
  heterogeneous_causal_effects:['effect_not_identified','Причинный эффект не установлен','Causal forests и double machine learning не обучались. Неоднородность причинного эффекта не оценена.'],
  recommendations:['author_synthesis_published','Опубликованы авторские предложения','Предложения сохраняют статус авторской экспертизы и ссылки на собственные основания.'],
  cohort_projection:['not_implemented_without_population_inputs','Нет данных для когортной проекции','Согласованный комплект половозрастных входов отсутствует. Взвешенная по населению концентрация описывает экспозицию при заданных входах.'],
  interactive_lab:['source_backed_calculations','Доступны проверяемые расчёты','Динамика, распределения и корреляции связаны с наблюдениями. Дополнительные калькуляторы обозначают пользовательские предпосылки и единицы.']
};

export async function buildEnvironmentFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/environment');
  const read=async name=>JSON.parse(await fs.readFile(path.join(directory,name+'.json'),'utf8'));
  const [foundation,expertise,methods,statistics,analytics,documentary,pkg]=await Promise.all([
    ...['foundation','expertise','methods','statistics','analytics','documentary'].map(read),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse)]);
  // Preserve the inherited metadata as a dated reference, without presenting its
  // old PCA, cluster or forecast counts as results of the new author study.
  if(!foundation.legacy_release_metadata){
    foundation.legacy_release_metadata={source_release:foundation.release_version,
      qualification:'Метаданные предыдущего исследовательского этапа. Текущие результаты определяются полями верхнего уровня и опубликованными источниками.',
      original:structuredClone(foundation)};
  }
  const c=statistics.coverage,n=documentary.network.summary||{};
  foundation.release_version=pkg.version;
  foundation.release_date='2026-10-29';
  foundation.statistical_as_of=statistics.statistical_as_of;
  foundation.documentary_as_of=expertise.meta.documentary_snapshot;
  foundation.author_expertise_status='published';
  foundation.registry={project_id:'environment',project_name:foundation.project_name,
    n_registry:c.registry_indicators,n_with_numeric:c.indicators_with_numeric,
    n_with_regional:c.regional_sources,n_with_national:statistics.sources.filter(s=>s.national?.length).length,
    n_unique_cells:c.observations,n_numeric:c.numeric_observations,n_usable:c.usable_observations,
    n_domain_violations:c.excluded_numeric_observations,coverage_pct:100*c.indicators_with_numeric/c.registry_indicators};
  foundation.panel={project_id:'environment',status:'descriptive_waste_pair',
    period:analytics.correlations.period,frequency:analytics.correlations.frequency,
    n_regions:analytics.correlations.n,n_features:2,n_imputed_cells:0,
    sensitivity_n_regions:analytics.correlations.strict.n,
    pca_performed:false,clustering_performed:false,spatial_autocorrelation_performed:false};
  foundation.research={project_id:'environment',project_name:foundation.project_name,
    registry_indicators:c.registry_indicators,indicators_with_numeric:c.indicators_with_numeric,
    indicators_with_regional:c.regional_sources,observations_numeric:c.numeric_observations,
    documents:documentary.sources.length,documentary_network_summary:n,
    multivariate_status:'descriptive_pair_only',
    passport_financing_2025_2030_thousand_rub:documentary.finance.totalThousandRub,
    strict_financing_hhi:documentary.finance.hhi,
    financing_status:'documented_plan_separate_from_budget_bill',
    causal_effect_status:'not_identified_in_existing_sources',author_expertise_text_status:'published'};
  foundation.results={project_id:'environment',project_name:foundation.project_name,
    n_registry:c.registry_indicators,n_numeric_indicators:c.indicators_with_numeric,
    n_regional_indicators:c.regional_sources,n_forecast_indicators:0,n_projected_series:0,
    forecast_status:'model_not_validated',
    n_documented_target_indicators:documentary.targets.items.length,
    n_eligible_annual_comparisons:analytics.target_comparisons.length,
    target_status:'source_backed_annual_comparisons_with_version_limits'};
  foundation.corpus={documents:documentary.meta.corpus_documents,
    projects:documentary.meta.corpus_projects,project_documents:documentary.sources.length,
    document_kind:'dated_passport_html',documentary_snapshot:documentary.meta.documentary_snapshot,
    source_archive_sha256:documentary.meta.input_archive_sha256};
  foundation.sections=expertiseBlueprint.map(section=>({...section,section_id:section.id,
    title:expertise.pages[section.id].title,publication_status:'published',
    evidence:expertise.pages[section.id].summary}));
  const report={title:'Авторская экспертиза национального проекта «Экологическое благополучие»',
    url:expertise.meta.report_url,format:'DOCX',edition_date:expertise.meta.edition_date,
    qualification:'Исходный отчёт сохранён полностью. Авторские выводы, статистические срезы и документальные редакции имеют собственные даты и источники.'};
  foundation.sources=[report,...foundation.sources.filter(source=>source.url!==report.url)];
  foundation.interpretation='Полный авторский отчёт сопровождается расчётами по сохранённым источникам. Дата сборки сайта не означает обновление первичных данных. Период наблюдения и результат последней попытки обновления указаны отдельно.';
  methods.release_version=pkg.version;
  methods.current_review_basis='published_environment_sources_report_and_independent_recalculation';
  for(const item of methods.items){
    const current=currentMethods[item.method_id];
    if(!current)throw Error('Environment method needs an explicit current status: '+item.method_id);
    [item.current_status,item.current_status_label,item.current_limitations]=current;
  }
  foundation.method_summary={total:methods.items.length,by_status:methods.items.reduce((out,item)=>{
    out[item.current_status]=(out[item.current_status]||0)+1;return out;
  },{})};
  await fs.writeFile(path.join(directory,'methods.json'),JSON.stringify(methods,null,2)+'\n');
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildEnvironmentPages();
