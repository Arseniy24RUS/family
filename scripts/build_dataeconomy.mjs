/** Publish Data Economy with explicit source periods and model sensitivity. */
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import {dataeconomyPages,expertiseBlueprint} from '../src/platform/projects.js';
import {buildResearchPages,validateResearchContent,renderReportBlocks} from './build_research_pages.mjs';
export {renderReportBlocks};
export const validateDataeconomyContent=expertise=>validateResearchContent(expertise,'data_economy',dataeconomyPages);
export const buildDataeconomyPages=root=>buildResearchPages('data_economy',dataeconomyPages,root);

const currentMethods={
  theory_of_change:['author_framework_published','Опубликована авторская рамка','Техническая возможность, использование и завершённый общественно значимый результат имеют разные единицы наблюдения.'],
  project_hierarchy:['source_structure_extracted','Структура извлечена из паспортов','Национальный паспорт и девять федеральных направлений сохраняют идентификаторы и даты публикации. Дата обновления вторичного представления не удостоверяет дату утверждения редакции.'],
  activity_inventory:['source_inventory_extracted','Реестр извлечён из источников','Цели, задачи, результаты и показатели представлены отдельными записями с адресами в исходных документах.'],
  activity_indicator_links:['source_relationships_audited','Документальные связи проверены','Принадлежность общей задаче, адресная ссылка и лексический кандидат имеют отдельный статус. Неопределённый адресат сохраняется явно.'],
  source_quality:['source_specific_contracts_verified','Проверены определения источников','Ежемесячная публикация может повторять годовую оценку или содержать накопленный итог. Проценты, индексы и числа объектов имеют разные допустимые области.'],
  observability:['computed_from_source_packets','Покрытие рассчитано по выгрузкам','Реестровые коды, уникальные источники, числовые публикации и территориальные совокупности учитываются раздельно.'],
  time_dynamics:['source_periods_preserved','Сохранён смысл временных рядов','Повторения последнего годового массива не считаются независимыми месячными измерениями. Нули технологических серий сохраняются с пояснением статуса публикации.'],
  target_comparison:['conditional_december_comparisons','Доступны условные сопоставления с целями','Декабрьские публикации и годовые планы связаны с конкретными источниками. Без подтверждённого годового статуса факта такое сравнение не устанавливает официальное выполнение показателя.'],
  forecasting:['model_not_validated','Прогнозная модель не подтверждена','Плановые траектории являются условными расчётами. Краткие ряды и повторные публикации не дают основания объявлять прогнозную точность или вероятность достижения цели.'],
  geographical_join:['explicit_scope_mapping','Территории сопоставлены явно','Общероссийский агрегат без учёта новых субъектов сохраняет собственный охват. Неполный территориальный ряд не заменяется сплошной совокупностью.'],
  regional_maps:['matched_source_slices','Показаны сопоставимые срезы','Каждая карта относится к одному показателю и периоду. Отсутствующие наблюдения имеют отдельное обозначение.'],
  regional_descriptive:['unweighted_regions','Рассчитаны региональные распределения','Квантили характеризуют доступные субъекты. Среднее региональных долей не заменяет национальный показатель с собственным знаменателем.'],
  correlations:['not_computed_in_current_report','Отдельная корреляционная модель не представлена','Многомерная панель используется для описания сочетаний административных признаков и проверки чувствительности. Причинное направление по этим агрегатам не устанавливается.'],
  pca:['source_panel_recomputed','Главные компоненты пересчитаны','Матрица, стандартизация, нагрузки, доли объяснённой вариации и маска заполнения пропуска доступны для проверки. Компоненты не являются шкалой цифрового благополучия.'],
  kmeans:['computed_with_instability_evidence','Разбиения рассчитаны с проверкой допустимости','Выбор числа групп учитывает силуэт и минимальную численность. Результаты начальных состояний, исключения признаков и соседних периодов показываются вместе с базовым разбиением.'],
  multivariate_stability:['seed_feature_time_sensitivity_computed','Устойчивость проверена несколькими способами','Отсутствие допустимого разбиения сохраняется как результат проверки. ARI для единственного допустимого варианта не удостоверяет общую устойчивость.'],
  isolation_forest:['computed_multiple_initial_states','Нетипичность проверена при разных начальных состояниях','Параметры Isolation Forest и частота отметки каждого региона раскрыты. Алгоритмический флаг требует проверки компонентов и знаменателей и не доказывает неблагополучие территории.'],
  moran_global:['not_recomputed_in_current_report','Текущая пространственная модель не представлена','Глобальная пространственная автокорреляция не включена в подтверждённые результаты нового раздела. Прежние материалы сохраняют собственный статус.'],
  moran_local:['not_recomputed_in_current_report','Локальные пространственные ассоциации не оценены','Модель LISA и локальная статистическая значимость для текущей панели не заявляются.'],
  regional_similarity:['descriptive_profiles_with_sensitivity','Доступно сопоставление профилей','Сходство административных показателей помогает ставить вопросы о механизмах различий. Основания адресной поддержки требуют дополнительных данных.'],
  relative_profiles:['source_values_and_standardization_published','Сохранены значения и преобразования','Исходные единицы доступны вместе со стандартизованной матрицей. Заполненный пропуск отделён от наблюдаемых значений.'],
  budget_registry:['matching_horizon_plans_reconciled','Планы сверены на общем горизонте','Годовые суммы 2025–2030 отделены от обязательств 2031–2036. Паспорт, бюджетная роспись, предложения и сведения об исполнении имеют собственные даты и основания.'],
  budget_hhi:['computed_common_horizon','Концентрация рассчитана на сопоставимом горизонте','Доли и HHI относятся к раскрытым суммам федеральных проектов одного периода. Отсутствующая строка не приравнивается к нулю.'],
  budget_observability:['documentary_financial_boundaries_audited','Проверены границы финансового учёта','Источники и подстроки трансфертов не складываются без проверки иерархии. Процент исполнения не используется для восстановления кассовой суммы по знаменателю другой даты.'],
  activity_network:['evidence_classes_separated','Классы связей разделены','Документальная принадлежность и лексическое сходство не задают причинную силу связи. Основания отбора и исходные адреса сохранены.'],
  lexical_frequencies:['fixed_corpus_audited','Частоты связаны с корпусом','Тематические частоты относятся к фиксированному словарю и набору документов. Пересекающиеся категории не образуют разбиение на сто процентов.'],
  dictionary_frames:['dictionary_frames_audited','Словарь и контексты доступны','Упоминания пользователей, доступности, технологий и безопасности проверяются в исходных формулировках. Частота слов не измеряет общественную результативность.'],
  tfidf_cosine:['source_corpus_and_sensitivity_audited','Текстовая близость проверена','Состав корпуса, очистка, словарь и объединение документов раскрыты. Авторская спецификация и дополнительные варианты платформы различаются.'],
  text_clustering:['not_computed','Текстовая кластеризация не выполнялась','Матрица близости и ранжирование соседних проектов не обозначаются самостоятельной кластерной моделью.'],
  concept_cooccurrence:['not_computed','Отдельная модель не рассчитывалась','Словарные частоты и контексты опубликованы. Модель совместного присутствия понятий не оценена.'],
  context_search:['source_contexts_published','Контексты доступны для проверки','Каждый фрагмент связан с документом. Полные тексты загружаются при обращении к соответствующему разделу.'],
  domain_evidence:['author_qualitative_analysis_published','Опубликован предметный анализ','Девять федеральных направлений рассматриваются через доступность, использование, качество, стоимость и дополнительный результат.'],
  expert_domain_scale:['not_computed','Числовая экспертная шкала не добавлена','Баллы требуют исходных оценок и протокола. Авторские качественные выводы сохраняют собственный статус.'],
  policy_scenario_framework:['conditional_arithmetic_no_causal_effect','Доступны условные расчёты','Последовательность цифрового процесса, стоимость завершённой услуги и жизненного цикла платформы рассчитываются при явных входных предпосылках.'],
  causal_designs:['design_proposed_effect_not_identified','Предложен дизайн оценки','Дополнительный эффект требует сопоставимой группы, исходного состояния и времени начала воздействия. Изменение агрегата само по себе его не устанавливает.'],
  heterogeneous_causal_effects:['effect_not_identified','Неоднородный причинный эффект не оценён','Causal forests и double machine learning не обучались. Межрегиональные различия не обозначаются оценками эффекта политики.'],
  recommendations:['author_synthesis_published','Опубликованы авторские предложения','Предложения связаны с проверенными результатами, ограничениями источников и дополнительными наблюдениями.'],
  cohort_projection:['not_implemented_without_transition_inputs','Когортная модель не рассчитывается','Данные о переходах пользователей и организаций между состояниями не образуют полную когортную базу. Возрастные границы показателей указаны отдельно.'],
  interactive_lab:['source_backed_and_conditional_calculations','Доступны проверяемые расчёты','Расчёты по наблюдениям сохраняют одинаковые периоды и совокупности. Дополнительные калькуляторы раскрывают знаменатели, денежные единицы и условия применения.']
};

export async function buildDataeconomyFoundation(root=path.resolve(import.meta.dirname,'..')){
  const directory=path.join(root,'public/data/projects/data_economy');
  const read=async name=>JSON.parse(await fs.readFile(path.join(directory,name+'.json'),'utf8'));
  const [foundation,expertise,methods,statistics,analytics,documentary,pkg]=await Promise.all([
    ...['foundation','expertise','methods','statistics','analytics','documentary'].map(read),
    fs.readFile(path.join(root,'package.json'),'utf8').then(JSON.parse)]);
  if(!foundation.legacy_release_metadata)foundation.legacy_release_metadata={
    source_release:foundation.release_version,
    qualification:'Метаданные предыдущего исследовательского этапа. Текущие результаты определяются полями верхнего уровня и опубликованными источниками.',
    original:structuredClone(foundation)};
  const c=statistics.coverage,mv=analytics.multivariate;
  const computed=mv?.status==='computed';
  if(!mv||!['computed','no_common_publication_period','insufficient_observed_matrix','constant_feature'].includes(mv.status)||!mv.summary)throw Error('Data Economy needs an explicit current multivariate status.');
  if(computed&&!mv.replication)throw Error('A computed Data Economy model needs its audit.');
  const annualComparisons=analytics.target_comparisons.filter(row=>row.formal_attainment_eligible===true);
  foundation.release_version=pkg.version;
  foundation.release_date='2026-10-29';
  foundation.statistical_as_of=statistics.statistical_as_of;
  foundation.documentary_as_of=expertise.meta.documentary_snapshot;
  foundation.author_expertise_status='published';
  foundation.registry={project_id:'data_economy',project_name:foundation.project_name,
    n_registry:c.registry_indicators,n_with_numeric:c.indicators_with_numeric,
    n_with_regional:c.regional_sources,n_with_national:statistics.sources.filter(s=>s.national?.length).length,
    n_unique_cells:c.observations,n_numeric:c.numeric_observations,n_usable:c.usable_observations,
    n_domain_violations:c.domain_violations,n_review_exclusions:c.review_exclusions,
    coverage_pct:100*c.indicators_with_numeric/c.registry_indicators};
  foundation.panel=computed?{project_id:'data_economy',status:'recomputed_with_instability_evidence',
    period_end:mv.period_end,n_regions:mv.summary.regions,n_features:mv.summary.features,
    n_imputed_cells:mv.summary.imputed_cells,common_regional_panel:true,
    source_ids:mv.features.map(feature=>feature.source_id),k:mv.summary.baseline_k,
    silhouette:mv.summary.silhouette,pc12_variance:mv.summary.pc12_variance,
    pca_performed:true,clustering_performed:true,ranking_validated:false,
    eligible_seed_runs:mv.summary.eligible_seed_runs,seed_runs:mv.summary.seed_runs,
    eligible_feature_omissions:mv.summary.eligible_feature_omissions,
    feature_omissions:mv.summary.feature_omissions,spatial_autocorrelation_performed:false}:{
    project_id:'data_economy',status:mv.status,period_end:mv.period_end??null,
    n_regions:mv.summary.regions??0,n_features:mv.summary.features??0,n_imputed_cells:0,
    common_regional_panel:false,source_ids:mv.source_ids??[],k:null,silhouette:null,pc12_variance:null,
    pca_performed:false,clustering_performed:false,ranking_validated:false,
    eligible_seed_runs:0,seed_runs:0,eligible_feature_omissions:0,feature_omissions:0,
    spatial_autocorrelation_performed:false};
  foundation.research={project_id:'data_economy',project_name:foundation.project_name,
    registry_indicators:c.registry_indicators,indicators_with_numeric:c.indicators_with_numeric,
    indicators_with_regional:c.regional_sources,observations_numeric:c.numeric_observations,
    documents:documentary.sources.length,documentary_network_summary:documentary.network.summary,
    multivariate_status:computed?'recomputed_with_seed_feature_and_time_sensitivity':mv.status,
    passport_financing_2025_2030_thousand_rub:documentary.finance.totalThousandRub,
    strict_financing_hhi:documentary.finance.hhi,
    financing_status:'matching_years_reconciled_later_commitments_separate',
    causal_effect_status:'not_identified_in_existing_sources',author_expertise_text_status:'published'};
  foundation.results={project_id:'data_economy',project_name:foundation.project_name,
    n_registry:c.registry_indicators,n_numeric_indicators:c.indicators_with_numeric,
    n_regional_indicators:c.regional_sources,n_forecast_indicators:0,n_projected_series:0,
    forecast_status:'model_not_validated',n_documented_target_indicators:documentary.targets.items.length,
    n_eligible_annual_comparisons:annualComparisons.length,
    n_conditional_target_comparisons:analytics.target_comparisons.length-annualComparisons.length,
    target_status:'source_linked_comparisons_with_explicit_period_status'};
  foundation.corpus={documents:documentary.meta.corpus_documents,projects:documentary.meta.corpus_projects,
    project_documents:documentary.sources.length,document_kind:'fixed_mixed_text_corpus_with_structured_passport_comparison',
    project_passport_snapshot:documentary.meta.documentary_snapshot,
    compared_structured_projects:documentary.text.authorAnalysis.compared_structured_projects,
    text_profiles_sha256:documentary.text.authorAnalysis.shared_profiles_sha256,
    passport_source_archive_documents:98,passport_source_archive_projects:12,
    passport_source_archive_sha256:documentary.meta.input_archive_sha256,
    qualification:'Текстовый корпус из 137 документов и общий архив из 98 паспортов имеют разный состав. Десять паспортов «Экономики данных» сверены с исходными HTML.'};
  foundation.sections=expertiseBlueprint.map(section=>({...section,title:expertise.pages[section.id].title,
    publication_status:'published',evidence:expertise.pages[section.id].summary}));
  const report={title:'Авторская экспертиза национального проекта «Экономика данных и цифровая трансформация государства»',
    url:expertise.meta.report_url,format:'DOCX',edition_date:expertise.meta.edition_date,
    qualification:'Исходный отчёт сохранён полностью. Авторские выводы, статистические срезы и документальные редакции имеют собственные даты и источники.'};
  foundation.sources=[report,...foundation.sources.filter(source=>source.url!==report.url)];
  foundation.interpretation='Полный авторский отчёт сопровождается расчётами по сохранённым источникам. Дата сборки сайта не означает обновление первичных данных. Период наблюдения и результат последней попытки обновления указаны отдельно.';
  methods.release_version=pkg.version;
  methods.current_review_basis='published_dataeconomy_sources_report_and_verified_calculations';
  for(const item of methods.items){
    const current=currentMethods[item.method_id];
    if(!current)throw Error('Data Economy method needs an explicit status: '+item.method_id);
    [item.current_status,item.current_status_label,item.current_limitations]=current;
    if(!computed&&['pca','kmeans','multivariate_stability','isolation_forest','relative_profiles'].includes(item.method_id)){
      item.current_status='not_computed_'+mv.status;
      item.current_status_label='Условия текущего многомерного расчёта не выполнены';
      item.current_limitations='Статус текущих входов: '+mv.status+'. Исходные наблюдения сохраняются. Результаты прежней матрицы не выдаются за расчёт по новому срезу.';
    }
  }
  foundation.method_summary={total:methods.items.length,by_status:methods.items.reduce((out,item)=>{
    out[item.current_status]=(out[item.current_status]||0)+1;return out;
  },{})};
  await fs.writeFile(path.join(directory,'methods.json'),JSON.stringify(methods,null,2)+'\n');
  await fs.writeFile(path.join(directory,'foundation.json'),JSON.stringify(foundation,null,2)+'\n');
  return foundation;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===path.resolve(process.argv[1]))await buildDataeconomyPages();
