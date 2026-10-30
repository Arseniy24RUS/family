/** Publish the Competitive Economy study with source-specific evidence limits. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {competitivePages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};
export const validateCompetitiveContent=expertise=>validateResearchContent(expertise,'competitive_economy',competitivePages);
export const buildCompetitivePages=root=>buildResearchPages('competitive_economy',competitivePages,root);

const currentMethods={
  theory_of_change:['author_framework_published','Опубликована авторская рамка','Административный результат, изменение экономического показателя и дополнительный эффект поддержки имеют разные основания оценки.'],
  project_hierarchy:['source_structure_extracted','Структура извлечена из паспортов','Национальный паспорт и семь федеральных направлений сохраняют идентификаторы и даты исходной публикации. Дата публикации не удостоверяет дату утверждения редакции.'],
  activity_inventory:['source_inventory_extracted','Реестр извлечён из источников','Цели, задачи, результаты и показатели представлены отдельными записями. Контрольные точки и повторные формулировки отмечены явно.'],
  activity_indicator_links:['source_relationships_audited','Документальные связи проверены','Общая задача, адресная связь и лексический кандидат различаются. Неоднозначный адресат сохраняется как неразрешённая ссылка.'],
  source_quality:['source_specific_contracts_verified','Проверены определения источников','Годовой факт, оперативное повторение и накопленный квартал имеют отдельные признаки. Исходные нули и другие спорные значения сохраняются вместе с объяснением их аналитического статуса.'],
  observability:['computed_from_source_packets','Покрытие рассчитано по выгрузкам','Реестровые показатели, подтверждённые ID ЕМИСС, числовые источники и карточки без чисел подсчитаны раздельно.'],
  time_dynamics:['computed_matching_frequency_category','Рассчитана сопоставимая динамика','Сопоставляются одинаковые периоды, категории и единицы. Частота публикации может отличаться от частоты измерения экономического явления.'],
  target_comparison:['documented_annual_comparisons','Выполнены допустимые годовые сопоставления','Годовой факт связан с конкретной редакцией цели. Доля совпадений в доступной выборке не является официальной оценкой выполнения всего национального проекта.'],
  forecasting:['model_not_validated','Прогнозная модель не подтверждена','Плановая траектория показывает условный путь при заданных предпосылках. Прогнозная точность и вероятность достижения цели не оценены.'],
  geographical_join:['explicit_scope_mapping','Территории сопоставлены явно','Субъекты Федерации и общероссийские агрегаты сохраняют собственные записи. Отсутствие значения не заменяется нулём.'],
  regional_maps:['matched_source_slices','Показаны сопоставимые срезы','Карта относится к одному источнику, периоду, частоте и категории. Разные показатели имеют разные территориальные совокупности.'],
  regional_descriptive:['unweighted_regions','Рассчитаны региональные распределения','Квантили относятся к доступным субъектам. Среднее региональных процентов не подменяет опубликованный общероссийский показатель.'],
  correlations:['not_claimed_in_author_analysis','Общая корреляционная модель не рассчитывается','Шесть распределений различаются по содержанию, периодам и знаменателям. Их объединение требует отдельного обоснования.'],
  pca:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Анализ главных компонент не включён в подтверждённые результаты текущей авторской экспертизы.'],
  kmeans:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Кластерная типология и общий рейтинг экономической эффективности регионов не установлены.'],
  multivariate_stability:['not_applicable_without_model','Многомерная устойчивость не оценивается','Многомерная модель не обучалась. Проверки сопоставимости выполняются отдельно по источникам.'],
  isolation_forest:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Контроль допустимых значений основан на определении показателя. Модель Isolation Forest не обучалась.'],
  moran_global:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Глобальный индекс пространственной автокорреляции и его значимость не оценивались.'],
  moran_local:['not_claimed_in_author_analysis','В этой экспертизе не рассчитывается','Локальные пространственные ассоциации LISA не оценивались.'],
  regional_similarity:['descriptive_profiles','Доступно сопоставление отдельных показателей','Сочетания региональных значений рассматриваются описательно. Сходство значений не устанавливает одинаковый эффект поддержки.'],
  relative_profiles:['descriptive_source_values','Показаны исходные региональные значения','Доход МСП, производительность и вовлечение организаций сохраняют свои единицы, периоды и основания учёта.'],
  budget_registry:['plans_reconciled','Финансовые планы извлечены и сверены','Паспортные планы всех источников отделены от федеральной бюджетной росписи и предложений на 2027–2029 годы. Кассовое исполнение по этим таблицам не установлено.'],
  budget_hhi:['computed_disclosed_scope','Доли и HHI рассчитаны в раскрытой совокупности','Распределение относится к федеральным проектам с численно раскрытым финансированием. Отсутствие положительной суммы в публикации не удостоверяет нулевую стоимость направления.'],
  budget_observability:['descriptive_documentary_audit','Выполнен документальный анализ','Бюджетные расходы, гарантии, льготное финансирование и привлечённые инвестиции имеют разное экономическое содержание. Их нельзя складывать как однородные затраты без проверки границ.'],
  activity_network:['evidence_classes_separated','Классы связей разделены','Паспортная принадлежность и текстовое сходство не задают причинную силу связи. Исходные идентификаторы и основания отбора сохранены.'],
  lexical_frequencies:['fixed_corpus_audited','Частоты связаны с корпусом и знаменателем','Тематические частоты относятся к определённому словарю и очищенным формулировкам. Пересекающиеся словарные категории не складываются до 100%.'],
  dictionary_frames:['dictionary_frames_audited','Словарные рамки доступны для проверки','Совпадения связаны с исходными контекстами. Частота упоминаний занятости, технологий или конкуренции не измеряет фактический эффект.'],
  tfidf_cosine:['source_corpus_and_sensitivity_audited','Сходство проверяется при заданной спецификации','Состав корпуса, очистка, ограничение словаря и объединение документов раскрыты. Авторские значения сохраняют собственную методику и не заменяются результатом другой спецификации.'],
  text_clustering:['not_computed','Кластеризация не выполнялась','Матрица текстовой близости и ранжирование соседей не обозначаются кластерной моделью.'],
  concept_cooccurrence:['not_computed','Отдельная модель не рассчитывалась','Тематические частоты и контексты опубликованы. Отдельная модель совместного присутствия понятий не оценена.'],
  context_search:['source_contexts_published','Контексты доступны для проверки','Фрагмент связан с документом и его идентификатором. Полные тексты загружаются по запросу.'],
  domain_evidence:['author_qualitative_analysis_published','Опубликован предметный анализ','Семь федеральных направлений рассматриваются через свои механизмы, ограничения измерения и условия возникновения результата.'],
  expert_domain_scale:['not_computed','Шкала 0–4 не рассчитывалась','Числовые экспертные баллы не добавлены без протокола и исходных оценок автора.'],
  policy_scenario_framework:['conditional_arithmetic_no_causal_effect','Доступны условные расчёты','Номинальная и реальная динамика, доход на работника и удельные затраты рассчитываются при явных входных предпосылках. Дополнительность поддержки требует отдельной оценки.'],
  causal_designs:['design_proposed_effect_not_identified','Предложен дизайн оценки','Сопоставление получателей и неполучателей требует данных об исходном состоянии, отрасли, территории и сроке начала поддержки. Причинный эффект по имеющимся агрегатам не установлен.'],
  heterogeneous_causal_effects:['effect_not_identified','Причинный эффект не установлен','Causal forests и double machine learning не обучались. Неоднородность эффекта поддержки не оценена.'],
  recommendations:['author_synthesis_published','Опубликованы авторские предложения','Предложения сохраняют авторский статус и связь с проверяемыми результатами и ограничениями.'],
  cohort_projection:['not_implemented_without_population_inputs','Когортная проекция не рассчитывается','Согласованные данные о переходах предприятий и работников между состояниями отсутствуют. Описательные показатели не заменяют когортную модель.'],
  interactive_lab:['source_backed_calculations','Доступны проверяемые расчёты','Динамика и распределения связаны с наблюдениями. Дополнительные калькуляторы раскрывают предпосылки, денежные единицы и знаменатели.']
};

export async function buildCompetitiveFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/competitive_economy');
  const read=async name=>JSON.parse(await fs.readFile(path.join(directory,name+'.json'),'utf8'));
  const [foundation,expertise,methods,statistics,analytics,documentary,pkg]=await Promise.all([
    ...['foundation','expertise','methods','statistics','analytics','documentary'].map(read),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse)]);
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
  foundation.registry={project_id:'competitive_economy',project_name:foundation.project_name,
    n_registry:c.registry_indicators,n_with_numeric:c.indicators_with_numeric,
    n_with_regional:c.regional_sources,n_with_national:statistics.sources.filter(s=>s.national?.length).length,
    n_unique_cells:c.observations,n_numeric:c.numeric_observations,n_usable:c.usable_observations,
    n_domain_violations:c.domain_violations,n_review_exclusions:c.review_exclusions,
    coverage_pct:100*c.indicators_with_numeric/c.registry_indicators};
  foundation.panel={project_id:'competitive_economy',status:'source_specific_regional_profiles',
    n_features:c.regional_sources,n_imputed_cells:0,common_regional_panel:false,
    source_ids:statistics.sources.filter(s=>s.regional_latest?.length).map(s=>s.id),
    pca_performed:false,clustering_performed:false,spatial_autocorrelation_performed:false};
  foundation.research={project_id:'competitive_economy',project_name:foundation.project_name,
    registry_indicators:c.registry_indicators,indicators_with_numeric:c.indicators_with_numeric,
    indicators_with_regional:c.regional_sources,observations_numeric:c.numeric_observations,
    documents:documentary.sources.length,documentary_network_summary:n,
    multivariate_status:'separate_regional_distributions',
    passport_financing_2025_2030_thousand_rub:documentary.finance.totalThousandRub,
    strict_financing_hhi:documentary.finance.hhi,
    financing_status:'disclosed_plans_reconciled_separate_from_budget_bill',
    causal_effect_status:'not_identified_in_existing_sources',author_expertise_text_status:'published'};
  foundation.results={project_id:'competitive_economy',project_name:foundation.project_name,
    n_registry:c.registry_indicators,n_numeric_indicators:c.indicators_with_numeric,
    n_regional_indicators:c.regional_sources,n_forecast_indicators:0,n_projected_series:0,
    forecast_status:'model_not_validated',
    n_documented_target_indicators:documentary.targets.items.length,
    n_eligible_annual_comparisons:analytics.target_comparisons.length,
    target_status:'source_backed_annual_comparisons_with_version_limits'};
  foundation.corpus={documents:documentary.meta.corpus_documents,
    projects:documentary.meta.corpus_projects,project_documents:documentary.sources.length,
    document_kind:'fixed_mixed_text_corpus_with_structured_passport_comparison',
    project_passport_snapshot:documentary.meta.documentary_snapshot,
    compared_structured_projects:documentary.text.authorAnalysis.compared_structured_projects,
    text_profiles_sha256:documentary.text.authorAnalysis.shared_profiles_sha256,
    passport_source_archive_documents:98,passport_source_archive_projects:12,
    passport_source_archive_sha256:documentary.meta.input_archive_sha256,
    qualification:'Текстовый корпус из 137 документов и общий архив из 98 паспортов имеют разный состав. Восемь паспортов экономического проекта сверены с первичными HTML.'};
  foundation.sections=expertiseBlueprint.map(section=>({...section,
    title:expertise.pages[section.id].title,publication_status:'published',
    evidence:expertise.pages[section.id].summary}));
  const report={title:'Авторская экспертиза национального проекта «Эффективная и конкурентная экономика»',
    url:expertise.meta.report_url,format:'DOCX',edition_date:expertise.meta.edition_date,
    qualification:'Исходный отчёт сохранён полностью. Авторские выводы, статистические срезы и документальные редакции имеют собственные даты и источники.'};
  foundation.sources=[report,...foundation.sources.filter(source=>source.url!==report.url)];
  foundation.interpretation='Полный авторский отчёт сопровождается расчётами по сохранённым источникам. Дата сборки сайта не означает обновление первичных данных. Период наблюдения и результат последней попытки обновления указаны отдельно.';
  methods.release_version=pkg.version;
  methods.current_review_basis='published_competitive_sources_report_and_verified_calculations';
  for(const item of methods.items){
    const current=currentMethods[item.method_id];
    if(!current)throw Error('Competitive Economy method needs an explicit current status: '+item.method_id);
    [item.current_status,item.current_status_label,item.current_limitations]=current;
  }
  foundation.method_summary={total:methods.items.length,by_status:methods.items.reduce((out,item)=>{
    out[item.current_status]=(out[item.current_status]||0)+1;return out;
  },{})};
  await fs.writeFile(path.join(directory,'methods.json'),JSON.stringify(methods,null,2)+'\n');
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildCompetitivePages();
