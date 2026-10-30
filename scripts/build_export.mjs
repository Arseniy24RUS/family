/** Publish the export expertise with separate statistical and documentary scopes. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {internationalExportPages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};

export function validateExportContent(expertise){
  const result=validateResearchContent(expertise,'international_export',internationalExportPages);
  if(!/^[a-f0-9]{64}$/.test(expertise.meta.source_docx_sha256||''))throw Error('Export report requires its exact source checksum.');
  if(!expertise.meta.report_url||!expertise.meta.markdown_url)throw Error('Export report downloads are required.');
  const sources=new Set(expertise.sources.map(source=>source.id));
  for(const page of Object.values(expertise.pages)){
    if(!page.blocks.length)throw Error('Export route has no substantive material: '+page.id);
    for(const block of page.blocks){
      for(const row of block.cellSourceIds||[])for(const ids of row||[])for(const id of ids||[]){
        if(!sources.has(id))throw Error('Export table cell has an unknown source: '+id);
      }
      for(const ids of block.headerSourceIds||[])for(const id of ids||[]){
        if(!sources.has(id))throw Error('Export table header has an unknown source: '+id);
      }
    }
  }
  return result;
}

export async function buildExportPages(root=path.resolve(import.meta.dirname,'..')){
  const expertise=JSON.parse(await fs.readFile(path.join(root,'public/data/projects/international_export/expertise.json'),'utf8'));
  validateExportContent(expertise);
  return buildResearchPages('international_export',internationalExportPages,root);
}

const currentMethods={
  theory_of_change:['author_framework_published','Опубликована авторская рамка','Меры поддержки, выход на рынок, оплаченный экспорт и дополнительный результат представлены как последовательные, самостоятельно проверяемые звенья.'],
  project_hierarchy:['source_structure_published','Опубликована структура проекта','Национальный проект и четыре федеральных направления сохранены вместе с редакциями паспортов и источниками вторичной публикации.'],
  activity_inventory:['source_inventory_published','Опубликован реестр мер и результатов','Учтены 47 результатов, 12 задач и 25 паспортных карточек показателей. Повторяющиеся карточки не увеличивают число уникальных показателей.'],
  activity_indicator_links:['evidence_classes_separated','Разделены основания связей','Общая задача, неоднозначное упоминание и лексический кандидат имеют разные статусы. Ни один из этих признаков не является оценкой причинного эффекта.'],
  source_quality:['source_cells_and_frequencies_checked','Проверены исходные ячейки и частоты','Годовая и месячная записи сохраняют самостоятельные идентификаторы. Смена регионального экспортного стандарта 2.0 на 3.0 не приравнивается к продолжению одной методики.'],
  observability:['source_coverage_published','Опубликовано фактическое покрытие','21 позиция реестра, 18 числовых источников и доступность сопоставимого определения учитываются раздельно. Источники без подтверждённых чисел сохраняют собственный статус.'],
  time_dynamics:['annual_monthly_scope_separated','Разделены годовые и месячные записи','Самостоятельный годовой итог имеет приоритет для годового сопоставления. Декабрьская публикация остаётся доступной и не подменяет годовую запись. Накопленный итог не трактуется как поток за месяц.'],
  target_comparison:['qualified_source_comparisons','Сопоставления сопровождаются условиями','Наблюдения проверяются по единицам, частоте и определению показателя. Цели редакции 16.10.2026 дают ретроспективное сравнение, но не удостоверяют исполнение первоначальных обязательств 2025 года.'],
  forecasting:['model_not_validated','Прогнозная модель не подтверждена','Короткие неоднородные ряды не поддерживают проверенный статистический прогноз. Плановые значения и требуемый постоянный темп опубликованы как условные траектории.'],
  geographical_join:['external_cbr_context_joined','Подключён отдельный территориальный источник','Таблицы Банка России сопоставлены с 85 непересекающимися территориями за 2024 и 2025 годы. Этот источник не увеличивает число региональных рядов ЕМИСС проекта.'],
  regional_maps:['external_services_context_mapped','Построена карта экспорта услуг','Карта отражает официальные территориальные операции в собственных единицах. Отсутствующие территории и нераспределённая сумма не заполняются нулями.'],
  regional_descriptive:['external_services_distribution_computed','Рассчитано распределение экспорта услуг','Доли, концентрация и годовые изменения рассчитаны по отдельной таблице Банка России. Национальный итог, распределённая сумма и нераспределённые операции имеют разные знаменатели.'],
  correlations:['not_computed_incomparable_series','Корреляционная модель не рассчитана','Совместное движение коротких экспортных и организационных рядов не выдаётся за установленную связь поддержки с результатом.'],
  pca:['not_applicable_without_regional_panel','Главные компоненты не рассчитаны','Один территориальный показатель экспорта услуг и его категории не образуют сопоставимую панель результатов национального проекта.'],
  kmeans:['not_applicable_without_regional_panel','Региональная кластеризация не выполнена','Карта услуг не объявляется многомерной типологией экспортного потенциала или эффективности поддержки.'],
  multivariate_stability:['not_applicable_without_multivariate_model','Устойчивость многомерной модели не оценивается','Многомерное разбиение отсутствует; показатели его устойчивости и качества не рассчитываются.'],
  isolation_forest:['not_applicable_without_regional_panel','Поиск многомерных выбросов не выполнен','Для модели не сформирована независимая сопоставимая региональная панель нескольких признаков.'],
  moran_global:['not_computed_without_spatial_design','Пространственная автокорреляция не рассчитана','Карта операций не определяет механизм пространственного взаимодействия. Обоснованная матрица связей и отдельный протокол оценки не заданы.'],
  moran_local:['not_computed_without_spatial_design','Локальные пространственные ассоциации не рассчитаны','Высокая концентрация операций не обозначается статистически значимым пространственным кластером без соответствующей проверки.'],
  regional_similarity:['not_computed_without_common_features','Многомерное сходство регионов не оценивается','Профили отражают опубликованные услуги и их изменение, без неподтверждённого интегрального ранжирования территорий.'],
  relative_profiles:['source_values_and_denominators_preserved','Сохранены исходные величины и знаменатели','Профиль региона различает объём, долю в национальном итоге и изменение за год. Средний процент исполнения разнородных показателей не используется как общая оценка проекта.'],
  budget_registry:['financial_horizon_and_transfer_separated','Согласованы горизонт и установленный трансферт','Паспортный план приведён к 2025–2030 годам. Подтверждённый повтор трансферта исключается отдельно; расходы 2031–2036 годов сохраняются вне выбранного горизонта.'],
  budget_hhi:['gross_plan_concentration_with_limits','Рассчитана концентрация паспортного плана','Доли и HHI описывают арифметическую сумму строк четырёх федеральных направлений до исключения трансферта. Они не характеризуют консолидированные исполненные расходы.'],
  budget_observability:['known_duplicate_removed_full_consolidation_unresolved','Проверена арифметика и раскрыт повторный счёт','Из суммы 723,3116451 млрд рублей исключён подтверждённый трансферт 1,3383563 млрд. Состав региональных назначений 2028–2029 годов не раскрыт полностью, поэтому 721,9732888 млрд не объявляется полностью консолидированной суммой.'],
  activity_network:['documentary_network_published','Опубликованы документальные связи','284 сочетания через общую задачу раскрывают структуру паспортов. Неоднозначные упоминания и 15 лексических кандидатов при пороге 0,10 представлены отдельно.'],
  lexical_frequencies:['fixed_profile_corpus_terms_published','Опубликованы признаки текстовых профилей','Корпус состоит из 47 описаний результатов и 18 названий показателей федеральных проектов. Частоты зависят от этого состава и раскрытой обработки текста.'],
  dictionary_frames:['explicit_dictionary_context_published','Представлены словарные признаки','Тематические формулировки сопровождаются контекстом. Частота упоминания механизма не измеряет объём его финансирования и полученный эффект.'],
  tfidf_cosine:['independent_replication_with_disclosed_difference','Расчёт сопоставлен с авторским результатом','Независимая модель для 65 текстов использует опубликованный список стоп-слов. При пороге 0,05 найдено 28 результатов против авторских 26; при 0,10, 0,15 и 0,20 совпадают 15, 8 и 6. Точный авторский препроцессинг не предоставлен.'],
  text_clustering:['not_recomputed_in_current_study','Текстовая кластеризация не переоценена','Матрица текстового сходства не представляется самостоятельно проверенной кластерной моделью.'],
  concept_cooccurrence:['not_recomputed_in_current_study','Модель совместного присутствия не переоценена','Словарные признаки не объявляются новой моделью понятийных связей без отдельного расчёта и проверки.'],
  context_search:['source_documents_published','Доступны исходные тексты и поиск','Совпадение связано с конкретным документом, профилем результата или показателя и редакцией. Лексический кандидат требует содержательной проверки.'],
  domain_evidence:['author_qualitative_analysis_published','Опубликован анализ четырёх направлений','Промышленный экспорт, зарубежная инфраструктура, системные меры и экспорт АПК рассмотрены по собственным механизмам, данным и ограничениям.'],
  expert_domain_scale:['not_computed_without_scoring_protocol','Числовая экспертная шкала не введена','Авторские выводы не переводятся в баллы без исходных оценок и описания процедуры.'],
  policy_scenario_framework:['conditional_arithmetic_without_estimated_effect','Доступны условные расчёты','Темп достижения цели, оплаченные поставки, повторный экспорт и дополнительность рассчитываются по явным предпосылкам. Результат калькулятора не является оценённым эффектом проекта.'],
  causal_designs:['design_proposed_effect_not_identified','Предложен дизайн причинной оценки','Для оценки поддержки нужны предприятия, даты участия, сопоставимая группа и результаты до и после вмешательства. Разность разностей доступна как формула с проверяемыми допущениями.'],
  heterogeneous_causal_effects:['effect_not_identified','Неоднородные причинные эффекты не оценены','Causal forests и double machine learning не обучались. Различия по предприятиям, территориям и работникам требуют дополнительных микроданных.'],
  recommendations:['author_recommendations_published','Опубликованы предложения экспертизы','Рекомендации связаны с историей методик, фактом оплаты поставок, устойчивостью участия и проверкой дополнительного результата.'],
  cohort_projection:['not_applicable_to_available_inputs','Когортная модель не рассчитывается','Экспортная статистика не содержит панели переходов одних и тех же работников или домохозяйств. Занятость и доходы рассматриваются через необходимые механизмы наблюдения.'],
  interactive_lab:['source_backed_and_conditional_calculations','Доступны предметные расчёты','Восемь расчётов сохраняют единицы, основания и допустимые диапазоны. Пропуски и нулевые знаменатели не дают ложного результата; отрицательная дополнительность остаётся допустимой.']
};

function count(value,label){
  if(!Number.isInteger(value)||value<0)throw Error('Invalid export coverage: '+label);
  return value;
}

export async function buildExportFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/international_export');
  const read=async name=>JSON.parse(await fs.readFile(path.join(directory,name+'.json'),'utf8'));
  const [foundation,expertise,methods,statistics,analytics,documentary,pkg]=await Promise.all([
    ...['foundation','expertise','methods','statistics','analytics','documentary'].map(read),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse)
  ]);
  validateExportContent(expertise);
  if(!foundation.legacy_release_metadata)foundation.legacy_release_metadata={
    source_release:foundation.release_version,
    qualification:'Метаданные предыдущего исследовательского выпуска сохраняют собственную редакцию. Поля верхнего уровня характеризуют текущую публикацию.',
    original:structuredClone(foundation)
  };
  const c=statistics.coverage;
  const registryCount=count(c.registry_indicators,'registry_indicators');
  const catalogNumeric=count(c.catalog_indicators_with_numeric??c.indicators_with_numeric,'catalog_indicators_with_numeric');
  const currentNumeric=count(c.semantically_available_indicators??c.indicators_with_numeric,'semantically_available_indicators');
  const regionalSources=count(c.regional_sources,'regional_sources');
  const observations=count(c.observations,'observations');
  const numeric=count(c.numeric_observations,'numeric_observations');
  const usable=count(c.usable_observations,'usable_observations');
  if(currentNumeric>registryCount||usable>numeric||numeric>observations)throw Error('Export coverage counts are inconsistent.');
  if(regionalSources!==0||analytics.multivariate?.status==='computed')throw Error('Export regional models require a separately reviewed source panel.');
  const comparisons=analytics.target_comparisons||statistics.target_comparisons||[];
  const eligible=comparisons.filter(row=>row.formal_attainment_eligible===true);
  const network=documentary.network?.counts||{};
  const sourceCount=(documentary.sources||[]).length;
  const finance=documentary.finance,context=analytics.regional_context?.services;
  if(!Number.isFinite(finance?.adjustedTotalThousandRub))throw Error('Export adjusted finance total is required.');
  Object.assign(foundation,{
    release_version:pkg.version,release_date:documentary.meta.prepared_at,author_edition_date:expertise.meta.edition_date,
    statistical_as_of:statistics.statistical_as_of||expertise.meta.statistical_snapshot,
    documentary_as_of:expertise.meta.documentary_snapshot,author_expertise_status:'published',
    registry:{project_id:'international_export',project_name:foundation.project_name,
      n_registry:registryCount,n_with_numeric:currentNumeric,original_catalog_numeric_indicators:catalogNumeric,
      source_mapping_status:'source_cells_frequencies_and_indicator_definitions_reviewed',n_numeric_sources:c.numeric_sources,
      n_with_regional:regionalSources,n_with_national:statistics.sources.filter(source=>source.national?.length).length,
      n_unique_cells:observations,n_numeric:numeric,n_usable:usable,
      n_domain_violations:c.domain_violations??0,n_review_exclusions:c.review_exclusions??0,
      coverage_pct:registryCount?100*currentNumeric/registryCount:0,
      qualification:'Наличие числовой ячейки отделено от сопоставимости определения, годового результата и редакции цели. Таблицы Банка России имеют самостоятельный охват.'},
    panel:{project_id:'international_export',status:'not_applicable',reason:'Сопоставимая региональная панель нескольких показателей проекта отсутствует. Отдельная таблица экспорта услуг не заменяет её.',
      n_regions:0,n_features:0,n_imputed_cells:0,common_regional_panel:false,k:null,silhouette:null,pc12_variance:null,
      pca_performed:false,clustering_performed:false,ranking_validated:false,spatial_autocorrelation_performed:false,
      external_context:{source:'Банк России',subject:'Экспорт услуг',years:context?.years||[],regions:context?.growth_summary?.comparable_regions??0,
        observations:context?.rows?.length??0,imputation:false,national_project_emiss_panel:false}},
    research:{project_id:'international_export',project_name:foundation.project_name,
      registry_indicators:registryCount,indicators_with_numeric:currentNumeric,original_catalog_numeric_indicators:catalogNumeric,
      indicators_with_regional:0,observations_numeric:numeric,documents:sourceCount,documentary_network_summary:network,
      multivariate_status:'not_applicable',passport_financing_2025_2030_thousand_rub:finance.totalThousandRub,
      adjusted_passport_financing_2025_2030_thousand_rub:finance.adjustedTotalThousandRub,
      known_duplicate_transfer_thousand_rub:finance.knownDuplicateTransferThousandRub,
      financing_total_meaning:finance.caveat,strict_financing_hhi:null,arithmetic_financing_hhi:finance.totalHhi??null,
      financing_status:'known_duplicate_removed_full_consolidation_unresolved',
      causal_effect_status:'not_identified_in_existing_sources',author_expertise_text_status:'published'},
    results:{project_id:'international_export',project_name:foundation.project_name,
      n_registry:registryCount,n_numeric_indicators:currentNumeric,n_regional_indicators:0,
      n_forecast_indicators:0,n_projected_series:0,forecast_status:'model_not_validated',
      n_documented_target_indicators:(documentary.targets?.items||analytics.targets||[]).length,
      n_eligible_annual_comparisons:eligible.length,n_conditional_target_comparisons:comparisons.length-eligible.length,
      target_status:'source_linked_comparisons_with_explicit_period_status'},
    corpus:{project_documents:documentary.meta.structured_passports,documentary_sources:sourceCount,
      source_corpus_documents:documentary.text.profileCount,source_corpus_projects:documentary.meta.comparable_text_projects,
      documentary_snapshot:documentary.meta.documentary_snapshot,
      qualification:'Пять паспортов, 65 текстовых профилей и источники авторского доклада являются самостоятельными единицами учёта. Точная авторская обработка текста не предоставлена.'},
    sections:expertiseBlueprint.map(section=>({...section,title:expertise.pages[section.id].title,
      publication_status:'published',evidence:expertise.pages[section.id].summary})),
    interpretation:'Полный авторский отчёт сопровождается исходными материалами и проверенными описательными расчётами. Годовые и месячные записи, территориальный контекст, бюджетный план и причинный эффект имеют самостоятельные основания. Дата сборки не заменяет дату наблюдения.'
  });
  const report={title:'Экспертиза национального проекта «Международная кооперация и экспорт»',url:expertise.meta.report_url,
    format:'DOCX',edition_date:expertise.meta.edition_date,qualification:'Исходный доклад сохранён полностью. Авторские выводы и первичные источники сохраняют собственные даты и основания.'};
  foundation.sources=[report,...(foundation.sources||[]).filter(source=>source.url!==report.url)];
  methods.release_version=pkg.version;
  methods.current_review_basis='published_export_report_verified_cells_and_distinct_regional_context';
  for(const item of methods.items){
    const current=currentMethods[item.method_id];
    if(!current)throw Error('Export method needs an explicit current status: '+item.method_id);
    [item.current_status,item.current_status_label,item.current_limitations]=current;
    item.numeric_indicators=currentNumeric;item.regional_indicators=0;item.multivariate_input_status='not_applicable';
    if(item.method_id==='policy_scenario_framework')item.method_name='Условные расчёты экспортного результата';
    if(item.method_id==='cohort_projection')item.method_name='Возможность когортного анализа занятости и доходов';
  }
  foundation.method_summary={total:methods.items.length,by_status:methods.items.reduce((out,item)=>{
    out[item.current_status]=(out[item.current_status]||0)+1;return out;
  },{})};
  for(const [name,data] of [['methods',methods],['foundation',foundation]]){
    const destination=path.join(directory,name+'.json'),temporary=destination+'.tmp';
    await fs.writeFile(temporary,JSON.stringify(data,null,2)+'\n');await fs.rename(temporary,destination);
  }
  return foundation;
}

if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildExportPages();
