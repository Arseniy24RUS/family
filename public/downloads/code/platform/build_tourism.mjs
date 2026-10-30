/** Publish the tourism study with explicit documentary and statistical boundaries. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {tourismPages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};

export function validateTourismContent(expertise){
  const result=validateResearchContent(expertise,'tourism',tourismPages);
  if(!/^[a-f0-9]{64}$/.test(expertise.meta.source_docx_sha256||''))throw Error('Tourism report needs its exact source checksum.');
  if(!expertise.meta.report_url||!expertise.meta.markdown_url)throw Error('Tourism report downloads are required.');
  const sources=new Set(expertise.sources.map(source=>source.id));
  for(const page of Object.values(expertise.pages)){
    if(!page.blocks.length)throw Error('Tourism route has no substantive material: '+page.id);
    for(const block of page.blocks){
      for(const row of block.cellSourceIds||[])for(const ids of row||[])for(const id of ids||[]){
        if(!sources.has(id))throw Error('Tourism table cell has an unknown source: '+id);
      }
      for(const ids of block.headerSourceIds||[])for(const id of ids||[]){
        if(!sources.has(id))throw Error('Tourism table header has an unknown source: '+id);
      }
    }
  }
  return result;
}

export async function buildTourismPages(root=path.resolve(import.meta.dirname,'..')){
  const expertise=JSON.parse(await fs.readFile(path.join(root,'public/data/projects/tourism/expertise.json'),'utf8'));
  validateTourismContent(expertise);
  return buildResearchPages('tourism',tourismPages,root);
}

const currentMethods={
  theory_of_change:['author_framework_published','Опубликована авторская рамка','Инвестиции, ввод объектов, поездки, ночёвки, расходы и местная добавленная стоимость рассматриваются как разные звенья туристской деятельности.'],
  project_hierarchy:['source_structure_published','Опубликована структура проекта','Национальный проект и пять федеральных направлений сохраняют документальные основания. Дата републикации паспорта отделяется от даты утверждения редакции.'],
  activity_inventory:['source_inventory_published','Опубликован реестр мер и результатов','Цели, задачи, результаты и показатели имеют отдельные записи и ссылки на источники. Количество записей зависит от редакции корпуса.'],
  activity_indicator_links:['evidence_classes_separated','Основания связей разделены','Общая задача, явная ссылка и лексическое сходство не обозначаются одинаковым видом связи. Неустановленный адресат связи сохраняется явно.'],
  source_quality:['definitions_and_periods_checked','Проверены определения и периоды','Экспорт туристских услуг в долларах США отделён от числа иностранных граждан в средствах размещения. Накопленные периоды, годовые значения и оперативные публикации различаются.'],
  observability:['source_coverage_published','Опубликовано фактическое покрытие','Карточки реестра, статистические источники и содержательно сопоставленные показатели подсчитываются раздельно. Исправленная привязка источника не означает получения новых наблюдений.'],
  time_dynamics:['source_periods_preserved','Сохранены исходные временные ряды','Накопленный итог внутри года не считается месячным потоком. Снижение накопленного значения и спорные нули отмечены для проверки, исходные числа сохранены.'],
  target_comparison:['source_linked_comparisons','Сопоставлены определения показателей и целей','Годовая цель сопоставляется только с подходящим годовым наблюдением той же единицы и совокупности. Промежуточная публикация не удостоверяет выполнение годового задания.'],
  forecasting:['model_not_validated','Прогнозная модель не подтверждена','Короткие ряды, накопленные итоги и спорные публикации ограничивают оценку прогноза. Условная траектория достижения цели не выдаётся за статистический прогноз.'],
  geographical_join:['explicit_territory_scope','Указан территориальный охват','Региональные значения относятся к конкретному источнику и периоду. Отсутствие наблюдения не заменяется нулём или значением прошлой публикации.'],
  regional_maps:['single_source_slices','Доступны карты одного показателя','Региональный слой отражает число туристских поездок в выбранном периоде. Карта не обобщает доступность, качество услуг и экономическую отдачу туризма.'],
  regional_descriptive:['unweighted_source_distribution','Рассчитаны описательные распределения','Квантили и доли относятся к опубликованным региональным наблюдениям. Число поездок не равно числу уникальных путешественников.'],
  correlations:['not_computed_single_regional_feature','Региональная корреляционная модель не рассчитана','Один сопоставимый региональный признак не образует многомерной базы. Корреляция национальных рядов разных периодов и единиц не подменяет такую базу.'],
  pca:['not_applicable_single_regional_feature','Главные компоненты не рассчитаны','В текущем наборе один региональный показатель. Матрица нескольких сопоставимых признаков отсутствует.'],
  kmeans:['not_applicable_single_regional_feature','Многомерная типология не рассчитана','Распределение по одному признаку не объявляется типологией туристского развития. Кластерный рейтинг эффективности не формируется.'],
  multivariate_stability:['not_applicable_without_multivariate_model','Устойчивость многомерной модели не оценивалась','Многомерное разбиение отсутствует, поэтому показатели его устойчивости не рассчитываются.'],
  isolation_forest:['not_applicable_single_regional_feature','Многомерный поиск нетипичных регионов не выполнен','Высокое число поездок само по себе не считается статистической ошибкой или признаком проблем территории.'],
  moran_global:['not_recomputed_in_current_study','Пространственная автокорреляция повторно не оценена','Предыдущие исследовательские расчёты сохраняют свою редакцию и предпосылки. Для текущего раздела значение Moran I и его значимость не заявляются.'],
  moran_local:['not_recomputed_in_current_study','Локальные пространственные ассоциации не переоценены','Текущая публикация не удостоверяет локальную статистическую значимость или распространение эффекта туристских мер между регионами.'],
  regional_similarity:['single_indicator_comparison','Доступно сравнение по одному показателю','Сходство числа туристских поездок не означает одинаковую структуру туристского хозяйства, сезонность и качество занятости.'],
  relative_profiles:['source_values_preserved','Сохранены исходные величины','Региональные значения показаны в единицах источника. Составной индекс результативности и ранжирование по скрытой компоненте не рассчитываются.'],
  budget_registry:['financial_sources_and_scopes_separated','Разделены финансовые источники и охват','Паспортные строки, бюджетная роспись, предложения и исполнение имеют разные основания. Арифметическая сумма строк не удостоверяет консолидированный ресурс проекта.'],
  budget_hhi:['row_concentration_with_scope_limits','Концентрация имеет ограниченный смысл','Доли и HHI описывают набор приведённых строк. Они не измеряют достаточность средств, стоимость дополнительного результата или экономическую эффективность.'],
  budget_observability:['financial_measurement_limits_published','Раскрыты ограничения финансового сопоставления','Общая сумма проекта не распределяется по результатам произвольно. Число показателей на рубль не используется в качестве оценки эффективности.'],
  activity_network:['documentary_network_published','Опубликованы документальные связи','Участие результата и показателя в общей задаче не доказывает влияние меры. Лексические кандидаты сохраняют предварительный статус.'],
  lexical_frequencies:['fixed_corpus_terms_published','Опубликованы частоты корпуса','Частоты зависят от объёма, жанра, повторов и очистки документов. Они интерпретируются вместе с исходными формулировками.'],
  dictionary_frames:['source_dictionary_evidence_published','Представлены тематические признаки','Упоминания инфраструктуры, путешествий и получателей услуг требуют контекстного прочтения. Словарная частота не измеряет общественную значимость направления.'],
  tfidf_cosine:['fixed_corpus_similarity_published','Опубликована текстовая близость','Косинусное сходство относится к указанному корпусу и способу обработки. Близость формулировок не устанавливает совпадение механизмов или результатов.'],
  text_clustering:['not_recomputed_in_current_study','Текстовая кластеризация повторно не выполнена','Матрица сходства не обозначается самостоятельной проверенной кластерной моделью.'],
  concept_cooccurrence:['not_recomputed_in_current_study','Модель совместного присутствия понятий не переоценена','Опубликованные словарные признаки и фрагменты документов не превращаются в новую модель без отдельного расчёта.'],
  context_search:['source_documents_published','Исходные документы доступны','Проверка формулировок выполняется по полному документу и его редакции. Поисковое совпадение сохраняет связь с источником.'],
  domain_evidence:['author_qualitative_analysis_published','Опубликован предметный анализ','Номерной фонд, морские курорты, туристская привлекательность, кадры и промышленное обеспечение рассматриваются через самостоятельные механизмы и ограничения.'],
  expert_domain_scale:['not_computed_without_scoring_protocol','Числовая экспертная шкала не добавлена','Качественные выводы отчёта не переводятся в баллы без исходных оценок и описания процедуры.'],
  policy_scenario_framework:['conditional_arithmetic_without_estimated_effect','Доступны условные расчёты','Предпосылки расчётов поездок, загрузки и расходов задаются явно. Полученные значения не являются оценкой причинного эффекта государственной поддержки.'],
  causal_designs:['design_proposed_effect_not_identified','Предложен дизайн причинной оценки','Для оценки дополнительного результата нужны данные о получателях поддержки, времени воздействия и сопоставимой группе. Агрегатные изменения этого не заменяют.'],
  heterogeneous_causal_effects:['effect_not_identified','Неоднородные причинные эффекты не оценены','Causal forests и double machine learning не обучались. Различия регионов не объявляются эффектами программы.'],
  recommendations:['author_recommendations_published','Опубликованы авторские предложения','Предложения сохранены в связи с результатами экспертизы, ограничениями исходных данных и необходимыми дополнительными наблюдениями.'],
  cohort_projection:['not_applicable_to_available_inputs','Когортная модель не переносится на туризм','Число поездок не представляет численность когорты путешественников. Данные о переходах одних и тех же лиц между состояниями отсутствуют.'],
  interactive_lab:['source_backed_and_conditional_calculations','Доступны предметные расчёты','Расчёты по наблюдениям сохраняют единицы и периоды. Сценарные калькуляторы показывают явные предпосылки, включая знаменатель и смысл денежной величины.']
};

const count=(value,label)=>{
  if(!Number.isInteger(value)||value<0)throw Error('Invalid tourism coverage: '+label);
  return value;
};

export async function buildTourismFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/tourism');
  const read=async name=>JSON.parse(await fs.readFile(path.join(directory,name+'.json'),'utf8'));
  const [foundation,expertise,methods,statistics,analytics,documentary,pkg]=await Promise.all([
    ...['foundation','expertise','methods','statistics','analytics','documentary'].map(read),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse)
  ]);
  validateTourismContent(expertise);
  if(!foundation.legacy_release_metadata)foundation.legacy_release_metadata={
    source_release:foundation.release_version,
    qualification:'Метаданные предыдущего исследовательского выпуска. Его расчёты и статусы сохраняют собственную редакцию. Поля верхнего уровня относятся к текущему разделу.',
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
  if(currentNumeric>registryCount||usable>numeric||numeric>observations)throw Error('Tourism coverage counts are inconsistent.');
  if(analytics.multivariate?.status==='computed')throw Error('Tourism multivariate results require a separately reviewed multi-indicator contract.');
  const targetComparisons=analytics.target_comparisons||statistics.target_comparisons||[];
  const eligible=targetComparisons.filter(row=>row.formal_attainment_eligible===true);
  const network=documentary.network?.counts||documentary.network?.summary||{};
  const documentCount=(documentary.sources||[]).length;
  const projectDocumentCount=(documentary.text?.documents||[]).length||documentCount;
  const total=documentary.finance?.totalThousandRub;
  if(total!==undefined&&total!==null&&!Number.isFinite(total))throw Error('Tourism finance total is not a finite number.');

  Object.assign(foundation,{
    release_version:pkg.version,
    release_date:expertise.meta.edition_date,
    statistical_as_of:statistics.statistical_as_of||expertise.meta.statistical_snapshot,
    documentary_as_of:expertise.meta.documentary_snapshot,
    author_expertise_status:'published',
    registry:{project_id:'tourism',project_name:foundation.project_name,
      n_registry:registryCount,n_with_numeric:currentNumeric,
      original_catalog_numeric_indicators:catalogNumeric,
      source_mapping_status:'definitions_reviewed_original_catalog_links_preserved',
      n_numeric_sources:c.numeric_sources??statistics.sources.filter(source=>(source.numeric_observations??source.n_numeric??source.counts?.numeric??0)>0||source.national?.length||source.regional_latest?.length).length,
      n_with_regional:regionalSources,n_with_national:statistics.sources.filter(source=>source.national?.length).length,
      n_unique_cells:observations,n_numeric:numeric,n_usable:usable,
      n_domain_violations:c.domain_violations??0,n_review_exclusions:c.review_exclusions??0,
      coverage_pct:registryCount?100*currentNumeric/registryCount:0,
      qualification:'Исходная каталожная привязка и предметно проверенная обеспеченность различаются. Источник иностранных размещений учитывается по его определению, отдельно от экспорта услуг.'},
    panel:{project_id:'tourism',status:analytics.multivariate?.status||'not_applicable',
      reason:analytics.multivariate?.reason||'Доступен один сопоставимый региональный показатель.',
      n_regions:c.regions??c.regional_territories??null,n_features:regionalSources,
      n_imputed_cells:0,common_regional_panel:false,k:null,silhouette:null,pc12_variance:null,
      pca_performed:false,clustering_performed:false,ranking_validated:false,
      spatial_autocorrelation_performed:false},
    research:{project_id:'tourism',project_name:foundation.project_name,
      registry_indicators:registryCount,indicators_with_numeric:currentNumeric,
      original_catalog_numeric_indicators:catalogNumeric,indicators_with_regional:regionalSources,
      observations_numeric:numeric,documents:documentCount,documentary_network_summary:network,
      multivariate_status:analytics.multivariate?.status||'not_applicable',
      passport_financing_2025_2030_thousand_rub:total??null,
      financing_total_meaning:documentary.finance?.totalMeaning||'Арифметическая сумма приведённых строк, консолидация не установлена.',
      strict_financing_hhi:null,arithmetic_financing_hhi:documentary.finance?.hhi??null,
      financing_status:'arithmetic_row_sum_without_consolidated_resource_claim',
      causal_effect_status:'not_identified_in_existing_sources',author_expertise_text_status:'published'},
    results:{project_id:'tourism',project_name:foundation.project_name,
      n_registry:registryCount,n_numeric_indicators:currentNumeric,n_regional_indicators:regionalSources,
      n_forecast_indicators:0,n_projected_series:0,forecast_status:'model_not_validated',
      n_documented_target_indicators:(documentary.targets?.items||[]).length,
      n_eligible_annual_comparisons:eligible.length,
      n_conditional_target_comparisons:targetComparisons.length-eligible.length,
      target_status:'source_linked_comparisons_with_explicit_period_status'},
    corpus:{project_documents:projectDocumentCount,documentary_sources:documentCount,
      source_corpus_documents:documentary.meta?.corpus_documents??null,
      source_corpus_projects:documentary.meta?.corpus_projects??null,
      documentary_snapshot:documentary.meta?.documentary_snapshot||expertise.meta.documentary_snapshot,
      qualification:'Число документов тематического корпуса, число паспортов и число источников экспертизы обозначают разные единицы учёта.'},
    sections:expertiseBlueprint.map(section=>({...section,title:expertise.pages[section.id].title,
      publication_status:'published',evidence:expertise.pages[section.id].summary})),
    interpretation:'Полный авторский отчёт сопровождается источниками и проверенными описательными расчётами. Дата сборки сайта не заменяет дату первичного наблюдения. Спорные публикации, исправленные привязки и условные сценарии имеют отдельные пояснения.'
  });
  const report={title:'Авторская экспертиза национального проекта «Туризм и гостеприимство»',
    url:expertise.meta.report_url,format:'DOCX',edition_date:expertise.meta.edition_date,
    qualification:'Исходный отчёт сохранён полностью. Авторские выводы, статистические наблюдения и документальные редакции сохраняют собственные даты.'};
  foundation.sources=[report,...(foundation.sources||[]).filter(source=>source.url!==report.url)];
  methods.release_version=pkg.version;
  methods.current_review_basis='published_tourism_report_sources_and_verified_descriptive_calculations';
  for(const item of methods.items){
    const current=currentMethods[item.method_id];
    if(!current)throw Error('Tourism method needs an explicit current status: '+item.method_id);
    [item.current_status,item.current_status_label,item.current_limitations]=current;
    item.numeric_indicators=currentNumeric;
    item.regional_indicators=regionalSources;
    item.multivariate_input_status=analytics.multivariate?.status||'not_applicable';
    if(item.method_id==='policy_scenario_framework')item.method_name='Условные сценарии развития туризма';
    if(item.method_id==='cohort_projection')item.method_name='Возможность когортного анализа путешественников';
  }
  foundation.method_summary={total:methods.items.length,by_status:methods.items.reduce((out,item)=>{
    out[item.current_status]=(out[item.current_status]||0)+1;
    return out;
  },{})};
  await fs.writeFile(path.join(directory,'methods.json'),JSON.stringify(methods,null,2)+'\n');
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}

if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildTourismPages();
