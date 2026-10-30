/** Publish the transport expertise with its documented measurement boundaries. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {efficientTransportPages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};

export function validateTransportContent(expertise){
  const result=validateResearchContent(expertise,'efficient_transport',efficientTransportPages);
  if(!/^[a-f0-9]{64}$/.test(expertise.meta.source_docx_sha256||''))throw Error('Transport report needs its exact source checksum.');
  if(!expertise.meta.report_url||!expertise.meta.markdown_url)throw Error('Transport report downloads are required.');
  const sources=new Set(expertise.sources.map(source=>source.id));
  for(const page of Object.values(expertise.pages)){
    if(!page.blocks.length)throw Error('Transport route has no substantive material: '+page.id);
    for(const block of page.blocks){
      for(const row of block.cellSourceIds||[])for(const ids of row||[])for(const id of ids||[]){
        if(!sources.has(id))throw Error('Transport table cell has an unknown source: '+id);
      }
      for(const ids of block.headerSourceIds||[])for(const id of ids||[]){
        if(!sources.has(id))throw Error('Transport table header has an unknown source: '+id);
      }
    }
  }
  return result;
}

export async function buildTransportPages(root=path.resolve(import.meta.dirname,'..')){
  const expertise=JSON.parse(await fs.readFile(path.join(root,'public/data/projects/efficient_transport/expertise.json'),'utf8'));
  validateTransportContent(expertise);
  return buildResearchPages('efficient_transport',efficientTransportPages,root);
}

const currentMethods={
  theory_of_change:['author_framework_published','Опубликована авторская рамка','Расчётная мощность, фактическая работа сети, полное время и стоимость услуги представлены как самостоятельные звенья транспортных изменений.'],
  project_hierarchy:['source_structure_published','Опубликована структура проекта','Сохранены национальный проект и девять федеральных направлений. Дата вторичной публикации паспорта отделена от даты утверждения редакции.'],
  activity_inventory:['source_inventory_published','Опубликован реестр мер и результатов','Цели, задачи, результаты и показатели имеют самостоятельные идентификаторы и ссылки на исходные паспорта.'],
  activity_indicator_links:['evidence_classes_separated','Разделены основания связей','Общая задача, неоднозначное упоминание и лексическое сходство представлены отдельно. Совместное присутствие в документе не устанавливает причинного влияния.'],
  source_quality:['source_cells_and_definitions_checked','Проверены ячейки и определения','Статистические ячейки сопоставлены с исходными таблицами. Техническая мощность, перевозки, индекс с фиксированным знаменателем и образовательный результат имеют разные правила интерпретации.'],
  observability:['source_coverage_published','Опубликовано фактическое покрытие','Реестровые показатели, доступные числовые источники, первичные ячейки и независимые наблюдения не отождествляются. Пропуски сохраняются.'],
  time_dynamics:['period_semantics_preserved','Сохранены временные основания','Накопленный итог не трактуется как месячный поток. Для показателей обучения месячная публикация характеризует предыдущий отчётный год. Повторение уровня мощности не означает новое независимое наблюдение.'],
  target_comparison:['qualified_source_comparisons','Сопоставления сопровождаются условиями','Проверяются показатель, единица, период, базовая дата и редакция цели. Декабрьское значение не считается универсальным подтверждением годового результата.'],
  forecasting:['model_not_validated','Прогнозная модель не подтверждена','Повторяемые уровни и короткие ряды не дают основания механически продолжать тренд. Плановые траектории опубликованы с собственным статусом.'],
  geographical_join:['no_regional_source_panel','Региональная статистическая панель отсутствует','В проверенных таблицах проекта представлены федеральные значения. Они не распределяются по субъектам России расчётным способом.'],
  regional_maps:['not_computed_without_regional_observations','Региональная статистическая карта не строится','География коридоров, морских бассейнов и доступности раскрывается в авторском анализе. Федеральные наблюдения не превращаются в региональные оценки.'],
  regional_descriptive:['not_computed_without_regional_observations','Региональные распределения не рассчитываются','Сопоставимые значения по субъектам отсутствуют. Число территорий и показатели распределения не подменяются нулями.'],
  correlations:['not_computed_incomparable_series','Корреляционная модель не рассчитана','Ряды разного экономического содержания, периода и способа формирования не соединяются в неподтверждённую модель транспортной эффективности.'],
  pca:['not_applicable_without_regional_panel','Главные компоненты не рассчитаны','Общая региональная матрица нескольких сопоставимых транспортных признаков отсутствует.'],
  kmeans:['not_applicable_without_regional_panel','Региональная кластеризация не выполнена','Нет входной панели для эмпирической типологии регионов. Качественные различия направлений не обозначаются статистическими кластерами.'],
  multivariate_stability:['not_applicable_without_multivariate_model','Устойчивость многомерной модели не оценивается','Многомерное разбиение отсутствует, его устойчивость и качество не рассчитываются.'],
  isolation_forest:['not_applicable_without_regional_panel','Поиск многомерных выбросов не выполнен','Федеральные уровни инфраструктурной мощности не образуют региональную выборку для Isolation Forest.'],
  moran_global:['not_applicable_without_regional_panel','Пространственная автокорреляция не рассчитана','Нет сопоставимых региональных наблюдений и обоснованной матрицы пространственных связей для данного показателя.'],
  moran_local:['not_applicable_without_regional_panel','Локальные пространственные ассоциации не рассчитаны','Территориальные выводы доклада не выдаются за статистические оценки локальной значимости.'],
  regional_similarity:['not_computed_without_regional_observations','Числовое сходство регионов не оценивается','Коридор, морской бассейн, зона доступа аэропорта и административный регион представляют разные единицы анализа.'],
  relative_profiles:['source_values_preserved','Сохранены исходные величины','Показатели доступны в собственных единицах. Средний процент исполнения разнородных показателей не используется как оценка общей эффективности.'],
  budget_registry:['financial_scopes_separated','Разделены финансовые основания','Паспортный план, федеральные бюджетные предложения, кассовое исполнение и долгосрочные обязательства имеют разные даты, охват и статус.'],
  budget_hhi:['row_concentration_with_scope_limits','Рассчитана концентрация опубликованного плана','Доли и HHI описывают набор паспортных строк. Они не удостоверяют обеспеченность договорами, консолидацию трансфертов и эффективность инвестиций.'],
  budget_observability:['financial_reconciliation_with_limits','Раскрыты согласованность и ограничения','Сходимость сумм по годам, источникам и направлениям проверяется отдельно от полноты раскрытия обязательств. Нераспределённая сумма не объявляется утратой средств.'],
  activity_network:['documentary_network_published','Опубликованы документальные связи','Сочетания результата и показателя через общую задачу представлены как структура паспортов. Причинный эффект по этим связям не оценён.'],
  lexical_frequencies:['fixed_corpus_terms_published','Опубликованы признаки текста','Частоты и ключевые формулировки зависят от состава корпуса, объёма документов и повторяющихся наименований.'],
  dictionary_frames:['source_dictionary_evidence_published','Представлены тематические признаки','Упоминания мощности, перевозок, пользователя, цифровизации и кадров проверяются в контексте исходного документа.'],
  tfidf_cosine:['fixed_corpus_similarity_published','Опубликована лексическая близость','Косинусное сходство относится к фиксированному корпусу и указанной обработке. Коэффициент не измеряет межпроектный или причинный эффект.'],
  text_clustering:['not_recomputed_in_current_study','Текстовая кластеризация не переоценена','Матрица текстового сходства не объявляется самостоятельно проверенной кластерной моделью.'],
  concept_cooccurrence:['not_recomputed_in_current_study','Модель совместного присутствия не переоценена','Словарные признаки сопровождаются контекстом и не обозначаются новой статистической моделью без отдельного расчёта.'],
  context_search:['source_documents_published','Доступен поиск по документам','Поисковое совпадение связано с документом, единицей текста и редакцией. Автоматический кандидат требует содержательной проверки.'],
  domain_evidence:['author_qualitative_analysis_published','Опубликован предметный анализ','Железные дороги, морские порты, Севморпуть, водные пути, авиация, граница, цифровизация и кадры рассматриваются по самостоятельным механизмам.'],
  expert_domain_scale:['not_computed_without_scoring_protocol','Числовая экспертная шкала не введена','Выводы авторов не переводятся в баллы без исходных оценок и описания процедуры.'],
  policy_scenario_framework:['conditional_arithmetic_without_estimated_effect','Доступны условные расчёты','Расчёты обобщённых издержек, ограничивающего звена и индексов используют явные пользовательские предпосылки. Значение калькулятора не является измеренным эффектом проекта.'],
  causal_designs:['design_proposed_effect_not_identified','Предложен дизайн причинной оценки','Нужны даты ввода, сопоставимые маршруты и наблюдения до воздействия. Перераспределение потока и дополнительный общесистемный результат требуют раздельной оценки.'],
  heterogeneous_causal_effects:['effect_not_identified','Неоднородные причинные эффекты не оценены','Causal forests и double machine learning не обучались. Различия по территориям и группам населения представлены как предмет дальнейшего наблюдения.'],
  recommendations:['author_recommendations_published','Опубликованы предложения экспертизы','Рекомендации сохраняют связь с установленными ограничениями, необходимыми данными и стадиями принятия решений.'],
  cohort_projection:['not_applicable_to_available_inputs','Когортная модель не рассчитывается','Количество поездок и обученных не образует наблюдаемую панель переходов одних и тех же людей. Демографические различия рассматриваются содержательно.'],
  interactive_lab:['source_backed_and_conditional_calculations','Доступны предметные расчёты','Формулы сопровождаются единицами и правилами допустимых входных значений. Пропуск, нулевой знаменатель и несопоставимая совокупность не дают ложного числового результата.']
};

function count(value,label){
  if(!Number.isInteger(value)||value<0)throw Error('Invalid transport coverage: '+label);
  return value;
}

export async function buildTransportFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/efficient_transport');
  const read=async name=>JSON.parse(await fs.readFile(path.join(directory,name+'.json'),'utf8'));
  const [foundation,expertise,methods,statistics,analytics,documentary,pkg]=await Promise.all([
    ...['foundation','expertise','methods','statistics','analytics','documentary'].map(read),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse)
  ]);
  validateTransportContent(expertise);
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
  if(currentNumeric>registryCount||usable>numeric||numeric>observations)throw Error('Transport coverage counts are inconsistent.');
  if(regionalSources!==0||analytics.multivariate?.status==='computed')throw Error('Transport regional models require a separately reviewed source panel.');
  const comparisons=analytics.target_comparisons||statistics.target_comparisons||[];
  const eligible=comparisons.filter(row=>row.formal_attainment_eligible===true);
  const network=documentary.network?.counts||documentary.network?.summary||{};
  const sourceCount=(documentary.sources||[]).length;
  const total=documentary.finance?.totalThousandRub;
  if(total!==undefined&&total!==null&&!Number.isFinite(total))throw Error('Transport finance total must be finite.');
  Object.assign(foundation,{
    release_version:pkg.version,release_date:expertise.meta.edition_date,
    statistical_as_of:statistics.statistical_as_of||expertise.meta.statistical_snapshot,
    documentary_as_of:expertise.meta.documentary_snapshot,author_expertise_status:'published',
    registry:{project_id:'efficient_transport',project_name:foundation.project_name,
      n_registry:registryCount,n_with_numeric:currentNumeric,original_catalog_numeric_indicators:catalogNumeric,
      source_mapping_status:'source_cells_and_indicator_definitions_reviewed',n_numeric_sources:c.numeric_sources,
      n_with_regional:regionalSources,n_with_national:statistics.sources.filter(source=>source.national?.length).length,
      n_unique_cells:observations,n_numeric:numeric,n_usable:usable,
      n_domain_violations:c.domain_violations??0,n_review_exclusions:c.review_exclusions??0,
      coverage_pct:registryCount?100*currentNumeric/registryCount:0,
      qualification:'Наличие числовой ячейки не удостоверяет независимость наблюдения, сопоставимость методики и завершённый годовой результат.'},
    panel:{project_id:'efficient_transport',status:'not_applicable',reason:'В проверенных источниках отсутствует сопоставимая региональная панель.',
      n_regions:0,n_features:0,n_imputed_cells:0,common_regional_panel:false,k:null,silhouette:null,pc12_variance:null,
      pca_performed:false,clustering_performed:false,ranking_validated:false,spatial_autocorrelation_performed:false},
    research:{project_id:'efficient_transport',project_name:foundation.project_name,
      registry_indicators:registryCount,indicators_with_numeric:currentNumeric,original_catalog_numeric_indicators:catalogNumeric,
      indicators_with_regional:0,observations_numeric:numeric,documents:sourceCount,documentary_network_summary:network,
      multivariate_status:'not_applicable',passport_financing_2025_2030_thousand_rub:total??null,
      financing_total_meaning:documentary.finance?.caveat||'Арифметическая сумма паспортного плана, консолидация и договорная обеспеченность не установлены.',
      strict_financing_hhi:null,arithmetic_financing_hhi:documentary.finance?.totalHhi??null,
      financing_status:'published_plan_reconciled_without_consolidation_claim',
      causal_effect_status:'not_identified_in_existing_sources',author_expertise_text_status:'published'},
    results:{project_id:'efficient_transport',project_name:foundation.project_name,
      n_registry:registryCount,n_numeric_indicators:currentNumeric,n_regional_indicators:0,
      n_forecast_indicators:0,n_projected_series:0,forecast_status:'model_not_validated',
      n_documented_target_indicators:(documentary.targets?.items||analytics.targets||[]).length,
      n_eligible_annual_comparisons:eligible.length,n_conditional_target_comparisons:comparisons.length-eligible.length,
      target_status:'source_linked_comparisons_with_explicit_period_status'},
    corpus:{project_documents:(documentary.text?.documents||[]).length||sourceCount,documentary_sources:sourceCount,
      source_corpus_documents:documentary.meta?.corpus_documents??null,source_corpus_projects:documentary.meta?.corpus_projects??null,
      documentary_snapshot:documentary.meta?.documentary_snapshot||expertise.meta.documentary_snapshot,
      qualification:'Паспорта проекта, документы лексического корпуса и источники авторской экспертизы являются самостоятельными единицами учёта.'},
    sections:expertiseBlueprint.map(section=>({...section,title:expertise.pages[section.id].title,
      publication_status:'published',evidence:expertise.pages[section.id].summary})),
    interpretation:'Полный авторский отчёт сопровождается исходными материалами и проверенными описательными расчётами. Мощность, использование сети и доступность услуги представлены отдельно. Дата сборки не заменяет дату наблюдения.'
  });
  const report={title:'Экспертиза национального проекта «Эффективная транспортная система»',url:expertise.meta.report_url,
    format:'DOCX',edition_date:expertise.meta.edition_date,qualification:'Исходный отчёт сохранён полностью. Авторские выводы и первичные источники сохраняют собственные даты и основания.'};
  foundation.sources=[report,...(foundation.sources||[]).filter(source=>source.url!==report.url)];
  methods.release_version=pkg.version;
  methods.current_review_basis='published_transport_report_sources_and_verified_descriptive_calculations';
  for(const item of methods.items){
    const current=currentMethods[item.method_id];
    if(!current)throw Error('Transport method needs an explicit current status: '+item.method_id);
    [item.current_status,item.current_status_label,item.current_limitations]=current;
    item.numeric_indicators=currentNumeric;item.regional_indicators=0;item.multivariate_input_status='not_applicable';
    if(item.method_id==='policy_scenario_framework')item.method_name='Условные расчёты транспортных изменений';
    if(item.method_id==='cohort_projection')item.method_name='Возможность когортного анализа пользователей транспорта';
  }
  foundation.method_summary={total:methods.items.length,by_status:methods.items.reduce((out,item)=>{
    out[item.current_status]=(out[item.current_status]||0)+1;return out;
  },{})};
  await fs.writeFile(path.join(directory,'methods.json'),JSON.stringify(methods,null,2)+'\n');
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}

if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildTransportPages();
