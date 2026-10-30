import {h,para,note,icon,select,fmt,sourceLink} from '../core/dom.js';
import {heading,panel,stats,table,figure,empty} from '../components/ui.js';
import {bars} from '../components/charts.js';
import {C} from '../platform/theme.js';
import {expertiseBlueprint,foundationPages,projectHref} from '../platform/projects.js';
const date=value=>value?new Intl.DateTimeFormat('ru-RU',{timeZone:'UTC'}).format(new Date(value)):'Не указана';
const sourceAnchor=(label,url)=>h('a',{href:url,target:'_blank',rel:'noopener noreferrer',class:'text-link'},label);
const localURL=url=>url.startsWith('./')?url:'./'+url;
const registryStatus={numeric_data:'Числовые данные доступны',linked_no_numeric:'Источник связан, чисел нет',no_table_link:'Таблица не найдена',temporarily_unavailable:'Источник временно недоступен'};
const frequency={monthly:'Месяц',quarterly:'Квартал',annual:'Год',yearly:'Год',daily:'День'};
const methodLabels={
 computed_with_documented_scope:'Рассчитано в пределах доступных данных',
 retained_and_independently_verified:'Сохранено и независимо проверено',
 retained_from_1_1_source_unchanged:'Сохранено: источник не изменился',
 retained_with_input_and_coverage_checks:'Проверены исходные данные и охват',
 robustness_computed_for_eligible_panels:'Проверена устойчивость допустимой панели',
 candidate_partitions_checked_no_forced_baseline_typology:'Проверены варианты группировки',
 documentary_structure_completed_substantive_review_deferred:'Документы разобраны, выводы требуют экспертизы',
 documentary_and_structural_links_computed_candidates_unapproved:'Связи извлечены, кандидаты требуют проверки',
 evidence_matrix_completed_expert_scores_deferred:'Собраны основания, экспертные оценки не выставлены',
 financial_measurement_bridge_computed_not_cost_effectiveness:'Расходы сопоставлены с измеримостью результатов',
 designs_and_readiness_audit_completed_no_effect_estimated:'Подготовлен дизайн, причинный эффект не оценён',
 specialized_family_extension_not_generalized:'Специализированный модуль «Семьи»',
 family_reference_preserved_with_separate_edition:'Материалы «Семьи» сохранены с собственной датой',
 deferred_by_user:'Предстоит авторская подготовка',
 reproducible_analysis_code_available:'Доступен воспроизводимый код'
};
function methodStatus(value){return methodLabels[value]||((value||'').startsWith('not_computable_current_input')?'Недостаточно сопоставимых данных':'Требует проверки');}
function methodGroup(value){if((value||'').startsWith('not_computable'))return 'Недостаточно данных';if(/deferred|unapproved|no_effect_estimated/.test(value))return 'Нужна содержательная оценка';if(/specialized/.test(value))return 'Специализированный метод';if(/code_available/.test(value))return 'Воспроизводимый код';return 'Расчёт и проверка выполнены';}
function hero(project,foundation){
 return h('header',{class:'project-hero'},h('div',{class:'project-hero-copy'},h('div',{class:'project-eyebrow'},'Национальный проект'),h('h1',{},project.name),para('Документы, статистика и исследовательская основа экспертизы.','lede'),h('div',{class:'project-dates'},h('span',{},'Статистика: ',h('strong',{},date(foundation.statistical_as_of))),h('span',{},'Документальный корпус: ',h('strong',{},date(foundation.documentary_as_of))))),h('img',{src:project.logo,alt:'Официальный логотип национального проекта «'+project.name+'»',class:'project-logo',width:136,height:116}));
}
function sourceFooter(ctx){return h('div',{class:'source-foot'},h('span',{},'Исследовательский выпуск '+ctx.foundation.release_version+' · '+date(ctx.foundation.release_date)),h('a',{href:projectHref(ctx.project.id,'library'),class:'text-link'},'Источники, даты и ограничения'));}
function overview(ctx){
 const {project:p,foundation:f}=ctx,r=f.registry;
 const root=h('div',{class:'project-page'},hero(p,f),stats([['Показателей в реестре',fmt(r.n_registry,0),'национальный и федеральный уровни'],['С числовыми данными',fmt(r.n_with_numeric,0),'по аудиту источников'],['С региональными данными',fmt(r.n_with_regional,0),'до проверки сопоставимости'],['Документов',fmt(f.research.documents,0),'в исследовательском корпусе']]));
 const values=[{name:'Реестр показателей',value:r.n_registry,color:C[0]},{name:'Есть числовые данные',value:r.n_with_numeric,color:C[1]},{name:'Есть региональный слой',value:r.n_with_regional,color:C[2]}];
 root.append(panel('Измеримость проекта','Количество показателей, а не степень достижения целей.',figure(bars(values,{height:220,label:'Доступность статистики по показателям',unit:'показателей'}),{name:p.id+'-coverage',title:p.name+': доступность статистики',source:'Аудит источников ЕМИСС, '+date(f.statistical_as_of)+'. Категории пересекаются.',rows:values.map(({name,value})=>({Категория:name,Показателей:value}))})),h('div',{class:'project-card-grid'},foundationPages.filter(x=>x.id!=='overview').map(page=>h('a',{class:'project-card',href:projectHref(p.id,page.id)},icon(page.icon,22),h('h2',{},page.title),para(({structure:'12 разделов, исследовательские вопросы и подготовленные основания.',methods:'39 методов: статус расчёта, применимость и пределы интерпретации.',explorer:'Реестр показателей и последние опубликованные значения с источниками.',library:'Документы, исходные таблицы и даты проверки.'})[page.id]),h('span',{class:'text-link'},'Открыть ',icon('arrow',16))))),panel('Что уже подготовлено',null,h('div',{class:'two-col'},h('div',{},h('h3',{},'Данные и воспроизводимость'),para(`Реестр содержит ${r.n_registry} показателей. Для ${r.n_with_numeric} найдены числовые наблюдения; для ${r.n_with_regional} есть региональный слой. Карточки сохраняют единицы, периоды и ссылки на конкретные источники.`),para('Методические материалы позволяют определить, какие расчёты применимы к имеющимся данным.')),h('div',{},h('h3',{},'Последовательная экспертиза'),para('Содержательные главы будут добавляться по мере подготовки и проверки. Для каждой предусмотрены исследовательский вопрос, доказательства, ограничения и выводы.'),para('Доступность таблиц и число рассчитанных методов сами по себе не характеризуют эффективность проекта.')))),note('На платформе показана последняя проверенная публикация данных. Дата статистического среза не означает, что все показатели относятся к одному периоду. Для каждого значения указан его период.'),sourceFooter(ctx));
 return root;
}
function sectionEvidence(id,evidence,foundation){
 if(id!=='regions')return evidence||'Источники будут уточнены при подготовке раздела.';
 const p=foundation.panel;
 if(p.status==='no_regional_data')return 'В текущем наборе нет региональных данных для многомерного сравнения. Построение типологии требует территориально сопоставимых наблюдений.';
 if(p.status==='fewer_than_two_comparable_regional_features')return 'Пока недостаточно сопоставимых региональных признаков для многомерного анализа. Наличие одного регионального показателя ещё не позволяет обосновать типологию территорий.';
 if(p.status==='computed')return `Подготовлена сопоставимая панель: ${p.n_regions} территорий, ${p.n_features} признаков; период до ${date(p.period_end)}. `+(p.cluster_status==='no_partition_meets_minimum_size'?'Проверенные разбиения не удовлетворяют ограничению на минимальный размер группы. ':'Варианты группировки рассчитаны и требуют содержательной интерпретации. ')+'Региональная типология не тождественна оценке эффективности.';
 return 'Условия многомерного сравнения требуют отдельной проверки сопоставимости данных.';
}
function structure(ctx){
 const {project:p,foundation:f}=ctx;
 return h('div',{class:'project-page'},heading('Структура экспертизы',p.name+': единая последовательность из 12 исследовательских разделов.'),note('Это план содержательной экспертизы. Уже подготовленные данные и методы указаны как основания; авторские выводы появятся после отдельной проверки.'),h('div',{class:'expertise-outline'},expertiseBlueprint.map(b=>{const s=f.sections.find(x=>x.section_id===b.id);return h('section',{class:'expertise-step'},h('span',{class:'expertise-number'},String(b.order).padStart(2,'0')),h('div',{},h('h2',{},b.title),para(b.question,'project-question'),h('h3',{},'Подготовленная основа'),para(sectionEvidence(b.id,s?.evidence,f)),h('div',{class:'project-meta'},`${s?.method_ids?.length||0} методов · содержательная глава готовится`)));})),h('div',{class:'project-links'},h('a',{href:projectHref(p.id,'methods'),class:'button'},'Методы и ограничения'),h('a',{href:projectHref(p.id,'explorer'),class:'button'},'Перейти к данным')),sourceFooter(ctx));
}
function methods(ctx){
 const {project:p,methods:items}=ctx,groups=new Map();
 for(const item of items){const key=methodGroup(item.status_1_2);groups.set(key,(groups.get(key)||0)+1);}
 const summary=[...groups].map(([name,value],i)=>({name,value,color:C[i%C.length]}));
 const rows=items.map(x=>({...x,status_label:methodStatus(x.status_1_2)}));
 return h('div',{class:'project-page'},heading('Методы и ограничения',p.name+': состояние исследовательских процедур и условия их применения.'),note('Статус относится к подготовке метода и наличию исходных данных. Он не является оценкой качества реализации национального проекта.'),panel('Готовность исследовательских процедур',`${items.length} методов в общей рамке экспертизы.`,figure(bars(summary,{height:Math.max(250,summary.length*48+55),label:'Статус методов экспертизы'}),{name:p.id+'-methods',title:p.name+': методы',source:'Матрица методов исследовательского выпуска '+ctx.foundation.release_version,rows:summary.map(({name,value})=>({Статус:name,Методов:value}))})),panel('Реестр методов','Поиск работает по названиям, статусам и ограничениям.',table(rows,[{key:'section_number',label:'Раздел',numeric:true},{key:'method_name',label:'Метод'},{key:'status_label',label:'Состояние'},{key:'transfer_limitations',label:'Пределы интерпретации'}],{pageSize:12,filename:p.id+'-methods.csv',caption:'Методы экспертизы проекта «'+p.name+'»'})),sourceFooter(ctx));
}
function explorer(ctx){
 const {project:p,indicators:items,state,set}=ctx;
 const selected=items.find(x=>x.indicator_code===state.indicator)||items.find(x=>x.latest_national.length)||items[0];
 const root=h('div',{class:'project-page'},heading('Исследователь данных',p.name+': показатель, источник, период и единица измерения.'),note('Значения относятся к последним доступным наблюдениям проверенного среза. Источники, связанные с одним показателем реестра, могут измерять разные величины; их названия и единицы показаны отдельно.'));
 if(selected){
  const details=h('div',{},select('Показатель реестра',items.map(x=>[x.indicator_code,x.indicator_name]),selected.indicator_code,value=>set({indicator:value})),h('p',{class:'project-selection-meta'},selected.indicator_code+' · '+registryStatus[selected.status]),para(selected.federal_project_name||'Показатель национального проекта','muted small'));
  if(selected.latest_national.length){
   const rows=selected.latest_national.map(x=>({...x,frequency_label:frequency[x.frequency]||x.frequency,category_label:Object.entries(x.category||{}).map(([k,v])=>k+': '+v).join('; ')||'Без дополнительного разреза'}));
   details.append(table(rows,[{key:'source_title',label:'Название в источнике',render:(value,row)=>sourceAnchor(value,row.source_url)},{key:'value',label:'Значение',numeric:true,decimals:6},{key:'unit',label:'Единица'},{key:'period',label:'Период'},{key:'frequency_label',label:'Частота'},{key:'category_label',label:'Разрез'}],{pageSize:8,filename:p.id+'-'+selected.indicator_code+'-latest.csv',caption:'Последние национальные значения по связанным источникам'}));
  }else details.append(empty('Национальные значения пока не опубликованы','Отсутствие значения не означает нулевой результат. Проверьте статус и территориальный охват источника в реестре.'));
  root.append(panel('Последние национальные значения','Для каждого ряда сохранены собственные единицы и период.',details));
 }
 root.append(panel('Все показатели проекта',`${items.length} записей. Выберите строку, чтобы открыть связанные источники.`,table(items.map(x=>({...x,status_label:registryStatus[x.status]||x.status})),[{key:'indicator_code',label:'Код'},{key:'indicator_name',label:'Показатель'},{key:'status_label',label:'Доступность'},{key:'n_regions',label:'Регионов',numeric:true},{key:'last_end',label:'Последний период'}],{pageSize:12,filename:p.id+'-registry.csv',onSelect:row=>set({indicator:row.indicator_code}),caption:'Реестр показателей проекта «'+p.name+'»'})),sourceFooter(ctx));return root;
}
function library(ctx){
 const {project:p,foundation:f}=ctx;
 return h('div',{class:'project-page'},heading('Данные и источники',p.name+': проверяемая основа исследовательских страниц.'),stats([['Проверка статистики',date(f.statistical_as_of),'срез ЕМИСС'],['Получение документов',date(f.documentary_as_of),'дата сбора, не редакции'],['Исследовательский выпуск',f.release_version,date(f.release_date)]]),note('Для этого проекта автоматическое обновление пока не подключено. Страницы исследовательской основы используют последнюю проверенную публикацию исходного комплекта. Дата получения документа не подтверждает актуальность его редакции.'),panel('Документальные источники','Ссылки ведут к материалам, использованным в исследовательском выпуске.',h('div',{class:'project-source-list'},f.sources.map(s=>h('article',{},h('h3',{},sourceAnchor(s.title,s.url)),para(s.qualification,'small'),h('div',{class:'project-meta'},`${s.format||'Документ'} · получен ${date(s.retrieved_at)} · редакция: ${s.edition_date?date(s.edition_date):'не установлена источником'}`))))),panel('Скачать данные','Компактные наборы проекта и общие таблицы аудита.',h('div',{class:'project-downloads'},[['foundation','Основа и источники проекта'],['indicators','Реестр и последние значения'],['methods','Методы и ограничения']].map(([id,title])=>sourceLink(title+' · JSON',`./data/projects/${p.id}/${id}.json`)),f.downloads.map(d=>sourceLink(d.title+' · CSV',localURL(d.url))))),panel('Как читать эти материалы',null,h('div',{class:'two-col'},h('div',{},h('h3',{},'Статистические значения'),para('Период наблюдения, дата получения и дата публикации набора различаются. Сравнивать показатели можно только при совпадении определений, единиц, территорий и частоты. Пропуски сохраняются как пропуски.')),h('div',{},h('h3',{},'Документы и выводы'),para('Паспортные ориентиры и распределение средств относятся к конкретной редакции документа. Текстовая похожесть, совместная принадлежность задаче и документированная связь имеют разный доказательный статус.')))),sourceFooter(ctx));
}
export function projectPage(ctx){return ({overview,structure,methods,explorer,library}[ctx.state.page]||overview)(ctx);}
export function renderReviewedPage(project,page){
 const root=h('div',{class:'project-page reviewed-page'},heading(page.title,page.summary),para('Проверенная авторская страница · '+date(page.updated_at),'muted small'));
 for(const block of page.blocks){
  if(block.type==='paragraph')root.append(para(block.text));
  else if(block.type==='heading')root.append(h('h'+(block.level||2),{},block.text));
  else if(block.type==='list')root.append(h(block.ordered?'ol':'ul',{},block.items.map(item=>h('li',{},item))));
  else if(block.type==='note')root.append(note(block.text,block.kind==='warning'?'warning':'info'));
  else if(block.type==='table')root.append(panel(block.title||'Данные',null,table(block.rows,block.columns,{caption:block.caption||block.title||page.title,filename:project.id+'-'+page.id+'.csv'})));
 }
 root.append(panel('Источники',null,h('ol',{},page.sources.map(s=>h('li',{},sourceAnchor(s.title,s.url),s.locator||s.note?para([s.locator,s.note].filter(Boolean).join(' · '),'small'):null)))));return root;
}
