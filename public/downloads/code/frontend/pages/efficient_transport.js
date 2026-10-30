import {observationCache, textPacketCache} from '../core/cache.js';
import {h,svg,para,note,button,select,fmt,icon,csvDownload} from '../core/dom.js';
import {heading,panel,toolbar,stats,table,figure,figureControls,empty} from '../components/ui.js';
import {bars,lineChart,legend,heatmap} from '../components/charts.js';
import {C} from '../platform/theme.js';
import {projectHref,efficientTransportPages} from '../platform/projects.js';

const PROJECT='efficient_transport',BASE='downloads/projects/efficient_transport/';
const array=x=>Array.isArray(x)?x:[],text=x=>typeof x==='string'?x:typeof x==='number'?String(x):x?.text||x?.summary||x?.title||'';
const number=x=>x===null||x===undefined||String(x).trim()===''?null:Number.isFinite(Number(String(x).replace(/[\s\u00a0]/g,'').replace(/[−–]/g,'-').replace(',','.')))?Number(String(x).replace(/[\s\u00a0]/g,'').replace(/[−–]/g,'-').replace(',','.')):null;
const finite=x=>number(x)!==null;
const value=r=>r?.excluded?null:Object.hasOwn(r||{},'analytical_value')?number(r.analytical_value):number(r?.value);
const absolute=p=>/^https?:\/\//.test(p||'')?p:'./'+String(p||'').replace(/^\.\//,'');
const link=(label,path,cls='text-link')=>path?h('a',{href:absolute(path),class:cls,...(/^https?:/.test(path)?{target:'_blank',rel:'noopener noreferrer'}:{})},label):h('span',{},label);
const date=d=>/^\d{4}-\d{2}-\d{2}/.test(d||'')?new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow'}).format(new Date(d)):d||'Не установлена';
const data=ctx=>ctx.efficient_transport,exp=ctx=>data(ctx).expertise,stat=ctx=>data(ctx).statistics,ana=ctx=>data(ctx).analytics||{},doc=ctx=>data(ctx).documentary||{};
const sourceId=s=>String(s?.source_id??s?.id??''),sourceName=s=>s?.short_title||s?.title||'Источник '+sourceId(s);
const sources=ctx=>array(stat(ctx).sources),report=ctx=>exp(ctx).meta.download_url||exp(ctx).meta.report_url||BASE+'report/expertise_transport_2026.docx';
const pageData=ctx=>exp(ctx).pages[ctx.state.page]||{};
const route=(page,params={})=>projectHref(PROJECT,page,params);
const code=r=>r?.indicator_code||r?.code||r?.id||'';
const rowName=r=>r?.territory_name||r?.name||r?.region_name||r?.territory||'';
const regionId=r=>String(r?.map_id||r?.region_id||r?.code||r?.region_code||r?.territory_code||'').padStart(2,'0');
const national=r=>['national','russia','country'].includes(r.geo_level)||r.is_national===true||/^Российская Федерация/.test(rowName(r));
const categoryKey=r=>JSON.stringify(Object.fromEntries(Object.entries(r.category||{}).sort(([a],[b])=>a.localeCompare(b))));
const period=r=>r?.period||r?.period_end||r?.year||'';
const frequency=r=>({previous_annual_result_published_monthly:'Месячная публикация результата предыдущего года',cumulative_project_capacity_stock:'Накопленная мощность в пределах проекта',technical_capacity_stock:'Публикация технической мощности',cumulative_fixed_denominator_index:'С начала года, фиксированный знаменатель'})[r?.period_semantics]||({annual:'Год',yearly:'Год',monthly:'Месячная публикация',quarterly:'Квартал',cumulative_ytd:'С начала года',quarterly_cumulative:'С начала года, квартальная оценка',monthly_stock:'На конец месяца',annual_repeated_monthly:'Публикация годовой оценки',annual_estimate:'Годовая оценка'})[r?.frequency]||r?.frequency||'';
const TITLE={overview:'Эффективная транспортная система',...Object.fromEntries(efficientTransportPages.filter(p=>p.id!=='overview').map(p=>[p.id,p.title]))};
const LEAD={
 overview:'Мощность транспортной сети, фактические перевозки, доступность сообщения и обязательства по созданной инфраструктуре.',
 framework:'Оценка соединяет техническую готовность, условия предоставления услуги и изменение возможностей населения и экономики.',
 logic:'Девять федеральных направлений требуют согласования объектов, сроков, источников финансирования и фактического спроса.',
 audit:'Формула, знаменатель, период накопления и редакция методики определяют допустимость каждого сопоставления.',
 targets:'Сохранённые наблюдения и паспортные цели рассматриваются в собственных единицах, периодах и версиях.',
 map:'География отраслевых публикаций раскрывает бассейны, коридоры и маршруты в пределах доступного источника.',
 regions:'Территориальный результат определяется изменением достижимых возможностей и условиями пользования транспортом.',
 finance:'Паспортный план, бюджетная роспись, проект бюджета и долгосрочные обязательства имеют разные основания финансового учёта.',
 network:'Документальная принадлежность, неоднозначная запись и лексическое сходство сохраняют самостоятельные основания.',
 texts:'Поиск по формулировкам паспортов и сравнение текстовых профилей помогают проверять согласованность описаний.',
 domains:'Каждое федеральное направление рассматривается через собственный механизм, измеряемый результат и смежные ограничения.',
 causal:'Дополнительный эффект требует наблюдения до и после ввода, сопоставимой группы и проверки переноса потоков.',
 proposals:'Предложения связывают методики, готовность маршрутов, пользовательский результат и финансовые обязательства.',
 projections:'Паспортные траектории сохраняют сроки федеральных проектов и неизвестные плановые значения.',
 population:'Полное время, стоимость, регулярность сообщения и возможность завершить поездку определяют доступность для разных групп населения.',
 structure:'Расчётная мощность, согласованность последовательных звеньев и фактическое использование описывают разные стороны работы сети.',
 methods:'Применимость метода определяется составом наблюдений, независимостью периодов и полнотой раскрытия исходных величин.',
 lab:'Формулы авторской экспертизы доступны для условных расчётов по значениям пользователя.',
 explorer:'Отбор по источнику, периоду и категории сохраняет исходные значения, единицы и признаки качества.',
 library:'Полный авторский доклад, паспорта, статистические источники, таблицы, иллюстрации и процедуры расчёта.',
 updates:'Дата сохранённого среза, период наблюдения и дата проверки источника учитываются раздельно.'
};

function references(ctx,ids=[]){return array(ids).length?h('div',{class:'efficient_transport-references'},array(ids).map(id=>array(exp(ctx).sources).find(s=>s.id===id)).filter(Boolean).map(s=>link(s.note_number?'['+s.note_number+'] '+(s.title||s.text):s.title||s.text,s.url||report(ctx)))):null;}
function sourceFoot(ctx,label,path){return h('div',{class:'source-foot'},h('span',{},label||'Статистический срез: '+date(stat(ctx).statistical_as_of)),path?link('Источник и данные',path):link('Источники',route('library')));}
function tableNode(ctx,t){
 if(!t)return null;
 const rows=array(t.rows),cols=array(t.columns).map((c,i)=>({key:c.key||'c'+i,label:c.label||c.title||c.key,render:(v,r)=>h('span',{},v??'–',array(t.cellSourceIds?.[rows.indexOf(r)]?.[i]).length?h('sup',{},array(t.cellSourceIds[rows.indexOf(r)][i]).map(id=>{const s=array(exp(ctx).sources).find(s=>s.id===id);return s?link(' ['+(s.note_number||id.replace('fn_',''))+']',s.url||report(ctx)):null;})):null)}));
 return h('div',{},table(rows,cols,{caption:t.title,filename:'efficient_transport-'+t.id+'.csv',pageSize:12}),t.note?para(t.note,'small muted'):null,references(ctx,t.sourceIds));
}
function reportTable(ctx,n,title){const t=array(exp(ctx).tables).find(t=>t.number===n);return t?panel(title||t.title,'Авторская экспертиза',tableNode(ctx,t)):null;}
function reportBlock(ctx,b){
 const attrs={id:'efficient_transport-'+b.id,class:'efficient_transport-report-block'};let node;
 if(b.type==='heading')node=h('h'+Math.max(2,Math.min(4,b.level||2)),attrs,b.text);
 else if(b.type==='table')node=h('section',attrs,h('h3',{},b.title),tableNode(ctx,b));
 else if(b.type==='formula')node=h('div',attrs,b.mathml?h('div',{class:'formula',html:b.mathml}):h('div',{class:'formula'},b.text||b.latex),b.note?para(b.note):null);
 else if(b.type==='figure_ref'){
  const f=array(exp(ctx).figures).find(f=>f.id===b.figureId),url=b.url||f?.url;
  node=h('figure',{...attrs,class:'efficient_transport-report-figure'},url?link(h('img',{src:absolute(url),alt:b.title||f?.title||'Иллюстрация экспертизы',loading:'lazy'}),url):null,h('figcaption',{},b.title||f?.title),b.note||f?.note?para(b.note||f.note,'small muted'):null);
 }else if(b.type==='list')node=h('div',attrs,array(b.items).map(t=>para(text(t))));
 else node=b.rich_html?h('p',{...attrs,html:b.rich_html}):h('p',attrs,b.text||'');
 return h('div',{},node,references(ctx,b.sourceIds));
}
function start(ctx){return h('div',{class:'efficient_transport-page',dataset:{efficient_transportPage:ctx.state.page,routeState:JSON.stringify(ctx.state)}},heading(TITLE[ctx.state.page]||pageData(ctx).title,LEAD[ctx.state.page],ctx.state.page==='overview'?h('img',{class:'efficient_transport-logo',src:ctx.project.logo,alt:'Логотип национального проекта «Эффективная транспортная система»',width:136,height:116}):null));}
function end(ctx,root){
 const p=pageData(ctx);
 if(array(p.blocks).length)root.append(h('details',{class:'efficient_transport-report'},h('summary',{},icon('table',18),'Текст экспертизы, таблицы и источники раздела'),h('div',{class:'efficient_transport-report-body'},p.blocks.map(b=>reportBlock(ctx,b)),references(ctx,p.sources))));
 root.append(sourceFoot(ctx,'Авторская экспертиза: '+date(exp(ctx).meta.edition_date)+' · Статистический срез: '+date(stat(ctx).statistical_as_of),report(ctx)),h('p',{class:'small'},link('Читать полную текстовую страницу','research/projects/efficient_transport/'+(ctx.state.page==='overview'?'index':ctx.state.page)+'.html')));
 return root;
}
function add(root,...nodes){root.append(...nodes.filter(Boolean));return root;}
function chart(ctx,node,name,title,rows=[],source=''){
 const result=figure(node,{name:'efficient_transport-'+name,title:'Эффективная транспортная система · '+title,source:source||'Источник: ЕМИСС. Срез '+date(stat(ctx).statistical_as_of),rows});
 const wrapper=h('div',{class:'efficient_transport-chart-scroll',tabindex:'0','aria-label':title});node.replaceWith(wrapper);wrapper.append(node);return result;
}
function cards(items){return h('div',{class:'project-grid efficient_transport-cards'},items.map(item=>h('article',{class:'project-card'},h('h3',{},item.title),para(item.text),item.path?link('Открыть раздел',item.path):null)));}
function numericTable(rows,columns,filename){return table(rows,columns,{filename:'efficient_transport-'+filename+'.csv',pageSize:12});}
function methodsTable(items){return table(items.map(m=>({title:m.name||m.method_name||m.title||m.method||m.method_id,status:m.current_label||m.current_status_label||m.status_label||m.status||'',reason:m.current_limitations||m.current_evidence||m.current_reason||m.current_note||m.evidence||m.reason||m.note||m.interpretation||''})),[{key:'title',label:'Метод'},{key:'status',label:'Состояние'},{key:'reason',label:'Основания и ограничения'}],{filename:'efficient_transport-methods.csv'});}
export function validateTransportSeries(packet,expectedId){
 const id=String(expectedId);
 if(!packet||packet.project_id!==PROJECT||String(packet.source_id)!==id||!Array.isArray(packet.observations))throw Error('Структура статистического источника '+id+' не соответствует выбранному проекту и показателю.');
 if(!packet.observations.every(r=>r&&typeof r==='object'&&String(r.source_id)===id&&typeof r.period_end==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(r.period_end)&&Object.hasOwn(r,'value')&&(r.value===null||typeof r.value==='number'&&Number.isFinite(r.value))))throw Error('Наблюдения источника '+id+' не прошли проверку структуры, периода и числовых значений.');
 return packet.observations;
}
export async function loadTransportObservations(source){
 const id=sourceId(source);
 return observationCache.getOrCreate(PROJECT+':observations:'+id,async()=>{
  const response=await fetch('./data/projects/efficient_transport/series/'+id+'.json');
  if(!response.ok)throw Error('Не удалось загрузить источник '+id+' (HTTP '+response.status+')');
  const packet=await response.json();
  return validateTransportSeries(packet,id);
 });
}
const observations=loadTransportObservations;
function selectedSource(ctx,regional=false){const eligible=sources(ctx).filter(s=>!regional||array(s.regional_latest).length||s.regional_count>0||s.has_regional_data);return eligible.find(s=>sourceId(s)===ctx.state.source)||eligible.find(s=>sourceId(s)==='62820')||eligible[0];}
function sourcePicker(ctx,selected,regional=false){return select('Показатель',sources(ctx).filter(s=>!regional||array(s.regional_latest).length||s.regional_count>0||s.has_regional_data).map(s=>[sourceId(s),sourceName(s)]),sourceId(selected),v=>ctx.set({source:v,period:'',category:'',region:''}));}
function pointsTable(rows,source){return numericTable(rows.map(r=>({territory:rowName(r)||'Российская Федерация',period:period(r),frequency:frequency(r),value:r.value,unit:r.unit||source.unit,category:Object.entries(r.category||{}).map(([k,v])=>k+': '+v).join(' · '),quality:array(r.quality_flags).map(f=>typeof f==='string'?f:f.message||f.label||f.code).join(' · ')||(r.excluded?'Исключено из расчёта':'')})),[{key:'territory',label:'Территория'},{key:'period',label:'Период'},{key:'frequency',label:'Режим публикации'},{key:'value',label:'Значение',numeric:true,decimals:5},{key:'unit',label:'Единица'},{key:'category',label:'Категория'},{key:'quality',label:'Примечание'}],'source-'+sourceId(source));}
function sourceNote(source){return h('div',{class:'efficient_transport-source-note'},para(source.semantic_note||source.temporal_note||source.interpretation||source.methodology_note||source.note||'Период и единица сохранены по исходной публикации.','small'),link('ЕМИСС '+sourceId(source),source.source_url||'https://www.fedstat.ru/indicator/'+sourceId(source)));}

function reportFigure(ctx,n){
 const f=array(exp(ctx).figures).find(f=>f.number===n||f.id==='figure_'+String(n).padStart(2,'0'));
 return f?panel(f.title,'Иллюстрация авторского доклада',h('figure',{class:'efficient_transport-report-figure'},link(h('img',{src:absolute(f.url),alt:f.title,loading:'lazy'}),f.url),f.note?para(f.note,'small muted'):null,references(ctx,f.sourceIds))):null;
}
function reportPassages(ctx,ids){
 return Object.values(exp(ctx).pages).flatMap(p=>array(p.blocks)).filter(b=>ids.includes(Number(String(b.sourceBlock||b.id).replace(/^b/,'')))).map(b=>reportBlock(ctx,b));
}
function overview(ctx){
 const root=start(ctx),c=stat(ctx).coverage||{};
 add(root,stats([['Коды каталога',fmt(c.registry_indicators??c.indicators_total,0),'Предметный реестр показателей'],['Числовые источники',fmt(c.numeric_sources,0),'Собственные определения и единицы'],['Числовые наблюдения',fmt(c.numeric_observations,0),'Срез '+date(stat(ctx).statistical_as_of)],['Региональные разрезы',fmt(c.regional_sources??0,0),'География отраслевых источников учитывается отдельно']]));
 add(root,panel('Что определяет результат','Вопросы авторской экспертизы',cards([
  {title:'Согласованная мощность',text:'Новый объект обеспечивает возможный поток при достаточной мощности подходов, готовности смежных звеньев и наличии спроса.',path:route('structure')},
  {title:'Фактическая работа сети',text:'Мощность, масса грузов, транспортная работа и число поездок сохраняют собственные единицы и периоды.',path:route('targets')},
  {title:'Финансовые обязательства',text:'Арифметическая сумма планов требует проверки трансфертов, договорного обеспечения и стоимости жизненного цикла.',path:route('finance')},
  {title:'Доступность сообщения',text:'Полное время, стоимость, расписание и надёжность определяют возможность завершить поездку.',path:route('population')}
 ])),reportTable(ctx,15,'Сводная экспертная оценка'));
 add(root,note('Статистические таблицы проекта содержат общероссийские наблюдения. Региональные рейтинги и причинные оценки по этим рядам не рассчитаны. Отраслевые территориальные сведения представлены с их собственными источниками.'));
 add(root,panel('Разделы исследования','Экспертиза и инструменты проверки',h('div',{class:'efficient_transport-directory'},efficientTransportPages.filter(p=>p.id!=='overview').map(p=>link(p.title,route(p.id),'efficient_transport-directory-link')))));
 return end(ctx,root);
}
function framework(ctx){return end(ctx,add(start(ctx),panel('Предмет оценки','Переход от объекта к услуге и общественному результату',cards([
 {title:'Техническая готовность',text:'Пропускная способность, дата ввода и режим эксплуатации устанавливаются для конкретного объекта и его смежных участков.'},
 {title:'Условия перевозки',text:'Полное время, тариф, ожидание и потери от ненадёжности формируют издержки пользователя.'},
 {title:'Изменение возможностей',text:'Доступ к рынкам, рабочим местам и услугам зависит от всей транспортной цепочки и распределения результата между группами.'}
 ])),panel('Границы национального проекта',null,h('div',{},para('Производство техники, грузовая база, дорожное хозяйство и городской транспорт связаны с другими программами. Отраслевое изменение требует проверки совместного действия направлений и риска двойного учёта.'),link('Рассчитать обобщённые издержки перевозки',route('lab',{calculator:'generalized_cost'})))),reportTable(ctx,4)));}
const FEDERAL=[
 ['Т1','Развитие высокоскоростных железнодорожных магистралей','Экономия полного времени поездки, доходная доступность и обязательства жизненного цикла. Срок паспорта заканчивается в 2028 году.'],
 ['Т2','Развитие Большого Северного морского пути','Грузовая база, сезонность, флот, ледовые условия и обеспечивающая инфраструктура.'],
 ['Т3','Развитие опорной сети железных дорог','Согласованная провозная способность направлений, подходов и конечных узлов.'],
 ['Т4','Развитие опорной сети морских портов','Мощность терминалов, грузовая специализация, подъездные пути и фактическая перевалка.'],
 ['Т5','Развитие опорной сети внутренних водных путей','Гарантированные габариты, продолжительность навигации и безопасность сооружений.'],
 ['Т6','Развитие опорной сети аэродромов','Пропускная способность, расписание, регулярность и доступность завершённой поездки.'],
 ['Т7','Развитие пунктов пропуска через Государственную границу Российской Федерации','Полное ожидание и прохождение границы с учётом всех необходимых процедур.'],
 ['Т8','Цифровая трансформация транспортной отрасли','Использование цифровых функций, состав документооборота и прослеживаемость расходов.'],
 ['Т9','Развитие кадрового потенциала транспортной отрасли','Проверка навыков, кадровая потребность объектов и фактическое применение результатов обучения.']
];
function logic(ctx){return end(ctx,add(start(ctx),cards(FEDERAL.map(([id,title,body])=>({title:id+'. '+title,text:body,path:route('domains',{domain:id})}))),reportTable(ctx,1),reportTable(ctx,12,'Документальная структура проекта')));}
function audit(ctx){
 const root=start(ctx),c=stat(ctx).coverage||{},registry=array(stat(ctx).registry).length?stat(ctx).registry:array(ctx.indicators);
 add(root,stats([['Коды каталога',fmt(c.registry_indicators??registry.length,0),'Все позиции предметного реестра'],['С числовыми источниками',fmt(c.indicators_with_numeric??c.numeric_sources,0),'Статус раскрытия исходного среза'],['Пропущенные значения',fmt(c.missing_observations,0),'Не заменены нулём']]));
 add(root,reportTable(ctx,4,'Методические режимы показателей'));
 add(root,panel('Реестр показателей','Проверка статистической обеспеченности',numericTable(registry.map(r=>({code:code(r),title:r.title||r.indicator_name||r.name,unit:r.unit||r.indicator_unit||'',sources:array(r.source_ids).join(', '),numeric:r.n_numeric??r.numeric_count,status:r.mapping_note||r.status_label||({numeric_data:'Числовые данные доступны',no_verified_numeric_source:'Нет подтверждённого числового источника',no_numeric_source:'Нет подтверждённого числового источника',linked:'Источник указан в каталоге',unmapped:'Связь с источником не установлена'})[r.status||r.catalog_status]||'Требует проверки источника'})),[{key:'code',label:'Код'},{key:'title',label:'Показатель'},{key:'unit',label:'Единица'},{key:'sources',label:'ЕМИСС'},{key:'numeric',label:'Числовые значения',numeric:true,decimals:0},{key:'status',label:'Состояние'}],'indicator-audit')));
 add(root,panel('Статистические источники','Определения и единицы каждой публикации',numericTable(sources(ctx).map(s=>({id:sourceId(s),title:sourceName(s),unit:s.unit,n:s.observations_count??s.observation_count??array(s.observations).length,detail:s.semantic_note||s.period_semantics||'',url:s.source_url||'https://www.fedstat.ru/indicator/'+sourceId(s)})),[{key:'id',label:'ЕМИСС',render:(v,r)=>link(v,r.url)},{key:'title',label:'Показатель'},{key:'unit',label:'Единица'},{key:'n',label:'Записи',numeric:true,decimals:0},{key:'detail',label:'Период и содержание'}],'source-audit')));
 add(root,note('Повторение месячного уровня может обозначать техническую мощность или нормативное использование годового результата прошлого периода. Число строк не определяет число независимых наблюдений.'));
 return end(ctx,root);
}
export function nationalChartSeries(rows,source){
 const cumulative=rows.some(r=>['cumulative_flow','cumulative_ytd','year_to_date','quarterly_cumulative','quarterly_cumulative_publication'].includes(r.period_semantics)||['cumulative_ytd','quarterly_cumulative'].includes(r.frequency))||['cumulative_flow','cumulative_ytd','year_to_date'].includes(source.period_semantics);
 const points=group=>group.map(r=>({x:Date.parse(r.period_end||String(r.year)+'-12-31'),y:value(r),label:period(r)}));
 const years=[...new Set(rows.map(r=>r.year||String(r.period_end||r.period).slice(0,4)))];
 return cumulative?years.map((year,i)=>({name:sourceName(source)+' · '+year+', с начала года',points:points(rows.filter(r=>String(r.year||String(r.period_end||r.period).slice(0,4))===String(year))),color:C[i%C.length]})):[{name:sourceName(source),points:points(rows),color:C[0]}];
}
async function targets(ctx){
 const root=start(ctx),s=selectedSource(ctx);if(!s)return end(ctx,add(root,note('Числовой источник для выбранного показателя отсутствует.')));
 const all=await observations(s),nat=all.filter(national),categories=[...new Set(nat.map(categoryKey))],cat=categories.includes(ctx.state.category)?ctx.state.category:categories[0],rows=nat.filter(r=>categoryKey(r)===cat).sort((a,b)=>String(a.period_end).localeCompare(String(b.period_end)));
 add(root,toolbar(sourcePicker(ctx,s),categories.length>1?select('Категория',categories.map(c=>[c,Object.values(JSON.parse(c)).join(' · ')||'Все категории']),cat,v=>ctx.set({category:v})):null),sourceNote(s));
 const series=nationalChartSeries(rows,s),cumulative=series.some(item=>item.name.includes(', с начала года'));
 if(rows.length)add(root,panel('Опубликованные значения',s.unit,h('div',{},chart(ctx,lineChart(series,{label:sourceName(s),unit:s.unit,monthlyTicks:true}),'national-'+sourceId(s),sourceName(s),rows.map(r=>({period:period(r),value:r.value,unit:s.unit,frequency:frequency(r)}))),cumulative?legend(series):null)));
 if(cumulative)add(root,note('Годовые периоды накопления показаны отдельными линиями. Переход от декабря к январю не трактуется как изменение месячного потока.'));
 const comps=array(ana(ctx).target_comparisons||stat(ctx).target_comparisons).filter(r=>String(r.source_id)===sourceId(s));
 const excluded=array(stat(ctx).excluded_target_comparisons).find(r=>String(r.source_id)===sourceId(s));if(excluded)add(root,note('Сопоставление с годовой целью не выполняется. '+excluded.reason));
 if(comps.length)add(root,panel('Сопоставление с паспортной целью','Условия сравнения сохраняются для каждой пары',numericTable(comps.map(r=>({year:r.target_year||r.year,fact:r.fact_value??r.value,target:r.target_value??r.target,difference:r.difference,unit:r.difference_unit||r.unit||s.unit,status:[r.status_label||'',r.note||r.caveat||''].filter(Boolean).join('. ')||r.status||'',formal:r.formal_attainment_eligible===true?'Допущено условиями сравнения':'Условное сопоставление'})),[{key:'year',label:'Год'},{key:'fact',label:'Наблюдение',numeric:true,decimals:5},{key:'target',label:'Цель',numeric:true,decimals:5},{key:'difference',label:'Разность',numeric:true,decimals:5},{key:'unit',label:'Единица разности'},{key:'status',label:'Основание'},{key:'formal',label:'Статус'}],'target-comparison')));
 add(root,panel('Исходные наблюдения',null,pointsTable(rows,s)),reportTable(ctx,5),reportTable(ctx,7));
 return end(ctx,root);
}
function geography(ctx){
 const root=start(ctx),kind=ctx.state.geography||'ports';
 add(root,toolbar(select('География публикации',[['ports','Морские бассейны'],['nsr','Северный морской путь'],['aviation','Авиационное сообщение'],['corridors','Транспортные коридоры']],kind,v=>ctx.set({geography:v}))),note('В статистическом срезе ЕМИСС отсутствует разбивка проекта по субъектам Федерации. Показанные отраслевые территории и маршруты имеют собственные единицы наблюдения.'));
 if(kind==='ports'){
  const measure=['2024','2025','change'].includes(ctx.state.basin_measure)?ctx.state.basin_measure:'2025',sourceTable=array(exp(ctx).tables).find(t=>t.number===6),column=measure==='2024'?'c1':measure==='2025'?'c2':'c3',unit=measure==='change'?'% к 2024 году':'млн т',rows=array(sourceTable?.rows).filter(r=>r.c0!=='Всего').map(r=>({name:r.c0,value:number(r[column])}));
  add(root,toolbar(select('Показатель перевалки',[['2024','Перевалка 2024 года'],['2025','Перевалка 2025 года'],['change','Изменение 2025 года к 2024 году']],measure,v=>ctx.set({basin_measure:v}))),rows.length?panel('Морские бассейны',unit,chart(ctx,bars(rows,{unit,label:'Перевалка по морским бассейнам'}),'basins-'+measure,'Морские бассейны',rows,'Источник: таблица 6 авторской экспертизы, единая редакция бюллетеня Минтранса. Уровни и изменения опубликованы с округлением.')):null,reportTable(ctx,6),reportFigure(ctx,2),panel('Условия сопоставления бассейнов',null,para('Сравниваются одинаковые редакции отраслевой публикации и состав перевалки. Изменение потока по бассейну не определяет загрузку каждого терминала или дополнительный эффект нового объекта.')));
 }
 else if(kind==='nsr')add(root,reportFigure(ctx,3),panel('Годовой поток и навигационный сезон',null,h('div',{},...reportPassages(ctx,[200,201,202,205,206]),link('Сохранённый ряд перевозок',route('targets',{source:'62820'})))));
 else if(kind==='aviation')add(root,reportFigure(ctx,4),panel('Пропускная способность и выполненные поездки',null,h('div',{},...reportPassages(ctx,[213,217,218,219,220]),link('Доступность для населения',route('population')))));
 else add(root,panel('Согласование направлений',null,h('div',{},...reportPassages(ctx,[74,184,185,186,187]),para('Географическое совпадение формулировок требует проверки конкретного направления, узла и смежного ограничения.'),link('Проверить границы лексических связей',route('network',{evidence:'lexical'})))),reportTable(ctx,14));
 return end(ctx,root);
}
function regions(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Маршрут и зона доступа',text:'Для станции, аэродрома и терминала границы наблюдения задаются по механизму воздействия и сохраняются при оценке результата.'},
 {title:'Доступные возможности',text:'Рабочие места, образование, медицинская помощь и рынки оцениваются с учётом расписания, полного времени и стоимости пути.'},
 {title:'Перераспределение потоков',text:'Рост перевозок одного узла может сопровождаться сокращением соседнего. Общесистемный прирост требует отдельной проверки.'},
 {title:'Отсутствующая информация',text:'Общероссийские значения не дают основания ранжировать субъекты, рассчитывать региональные кластеры или пространственную автокорреляцию.'}
 ]),panel('Что нужно для территориального анализа',null,h('div',{},para('Минимальный набор связывает объект, зону воздействия, дату ввода, фактическое использование, альтернативный маршрут и население с улучшившимся доступом.'),link('Отраслевые территориальные сведения',route('map')),h('span',{},' · '),link('Условный расчёт доступности',route('lab',{calculator:'accessibility'})))),reportTable(ctx,16)));}
function finance(ctx){
 const root=start(ctx),f=doc(ctx).finance||{},mode=ctx.state.finance||'passport';
 add(root,toolbar(select('Финансовый раздел',[['passport','Паспорта и источники'],['consolidation','Согласование и трансферты'],['budget','Роспись и проект бюджета'],['risk','Долгосрочные обязательства']],mode,v=>ctx.set({finance:v}))));
 if(mode==='passport'){
  add(root,note(f.caveat||f.totalMeaning||'Арифметическая сумма опубликованных строк не удостоверяет консолидацию трансфертов и договорное обеспечение всех ресурсов.'),reportTable(ctx,8),reportTable(ctx,9));
  const rows=array(f.projects).map(r=>{const total=number(r.totalThousandRub??r.total_thousand_rub??r.total);return{name:(r.code||r.fp||'')+' '+(r.title||r.name||r.federal_project_name||r.project_name||r.id||''),value:total===null?null:total/1e6};}).filter(r=>finite(r.value));
  if(rows.length)add(root,panel('Распределение раскрытых финансовых строк','Арифметическая структура паспортных планов',chart(ctx,bars(rows,{unit:'млрд руб.',label:'Паспортные финансовые строки'}),'finance','Финансирование федеральных направлений',rows,'Источник: паспорта федеральных проектов. Трансферты требуют отдельной сверки.')));
  add(root,reportFigure(ctx,5));
 }else if(mode==='consolidation')add(root,reportTable(ctx,11),panel('Границы арифметической проверки',null,h('div',{},para('Совпадение сумм по источникам, годам и федеральным направлениям подтверждает внутреннюю арифметику представления. Отдельно устанавливаются повторное отражение перечислений, договорное обеспечение, возвратность ресурсов и расходы за пределами горизонта.'),para('Нераспределённая по опубликованным результатам сумма обозначает предел детализации. По такой разности нельзя устанавливать утрату средств.'))));
 else if(mode==='budget')add(root,reportTable(ctx,10),reportFigure(ctx,7),note('Роспись текущего года и бюджетные предложения последующих лет сохраняют собственные даты и правовой статус. Разность с паспортом требует таблицы изменений редакций.'));
 else add(root,panel('Стоимость жизненного цикла','Паспортный горизонт и срок обязательств',h('div',{},...reportPassages(ctx,[280,281,282,283,284,285,346,363]),para('Неизвестные годы за пределами срока отдельного паспорта не заменяются нулём. Долгосрочная оценка охватывает содержание объекта, обслуживание долга, гарантии и условия компенсаций.'))),reportTable(ctx,11),link('Плановые траектории',route('projections')));
 return end(ctx,root);
}

const pairResult=r=>String(r.result_id||r.result_node_id||r.source_node_id||r.source_id||r.from||r.source||r.result||''),pairIndicator=r=>String(r.indicator_id||r.indicator_node_id||r.target_node_id||r.target_id||r.to||r.target||r.indicator||'');
function network(ctx){
 const root=start(ctx),n=doc(ctx).network||{},kind=ctx.state.evidence||'structural',nodes=array(n.nodes),nodeName=id=>nodes.find(n=>String(n.id)===String(id))?.title||nodes.find(n=>String(n.id)===String(id))?.label||id;
 const pairs=kind==='lexical'?array(n.lexicalPairs||n.semanticCandidates):kind==='ambiguous'?array(n.ambiguousClaims||n.unresolvedClaims):array(n.structuralPairs||n.sharedTaskPairs);
 if(kind==='lexical'&&n.counts?.lexicalIndicators!==n.counts?.authorReportedLexicalIndicators)add(root,note('При одинаковых косинусных коэффициентах на границе отбора правило разрешения равенства меняет охват показателей. Текущий расчёт содержит '+fmt(n.counts?.lexicalIndicators,0)+' различных показателей, авторский доклад указывает '+fmt(n.counts?.authorReportedLexicalIndicators,0)+'. Число пар и результатов сохраняется. В разделе текстов приведены альтернативные правила отбора.'),link('Проверить чувствительность к равным коэффициентам',route('texts')));
 add(root,stats([['Результаты',fmt(nodes.filter(x=>['result','результат'].includes(x.type||x.kind)).length||n.counts?.results,0),'Карточки паспортов'],['Общая задача',fmt(array(n.structuralPairs||n.sharedTaskPairs).length,0),'Документальные пары'],['Неоднозначные записи',fmt(array(n.ambiguousClaims||n.unresolvedClaims).length,0),'Требуют установления адресата'],['Лексические кандидаты',fmt(array(n.lexicalPairs||n.semanticCandidates).length,0),'Отдельная содержательная проверка']]));
 add(root,toolbar(select('Основание связи',[['structural','Принадлежность общей задаче'],['lexical','Лексическое сходство'],['ambiguous','Неоднозначные записи влияния']],kind,v=>ctx.set({evidence:v}))));
 const rows=pairs.map(r=>({from:r.result_title||r.source_title||r.result_name||nodeName(pairResult(r)),to:r.indicator_title||r.target_title||r.indicator_name||nodeName(pairIndicator(r))||(kind==='ambiguous'?'Адресат не установлен':''),task:r.task_title||r.task_id||r.claim_text||r.text||r.raw_target||(kind==='ambiguous'?'Опубликованная запись: '+(r.value_raw??'не задана')+'. Адресат требует проверки.':''),score:r.cosine??r.similarity??r.weight??r.score,source:r.document_url||r.source_url||r.url||''}));
 add(root,panel(kind==='ambiguous'?'Записи с неустановленными адресатами':'Пары результатов и показателей',kind==='lexical'?'Косинусная близость формулировок':'Связи документального корпуса',numericTable(rows,[{key:'from',label:'Результат / исходная запись'},{key:'to',label:'Показатель / адресат'},{key:'task',label:kind==='ambiguous'?'Исходная запись':'Задача и основание'},...(kind==='lexical'?[{key:'score',label:'Косинус',numeric:true,decimals:4}]:[]),{key:'source',label:'Документ',render:v=>v?link('Источник',v):'Паспортный корпус'}],'network-'+kind)));
 if(kind!=='ambiguous'&&pairs.length){
  const resultIds=[...new Set(pairs.map(pairResult))].filter(Boolean),indicatorIds=[...new Set(pairs.map(pairIndicator))].filter(Boolean);
  const labels=ids=>ids.map(id=>{const name=nodeName(id);return String(name).length>44?String(name).slice(0,41)+'…':name;});
  const columnLabels=indicatorIds.map((id,i)=>nodes.find(n=>String(n.id)===id)?.code||'И'+(i+1));
  if(resultIds.length&&indicatorIds.length)add(root,panel('Матрица документальных связей',kind==='lexical'?'Косинусное сходство, без причинной интерпретации':'1 – результат и показатель связаны общей задачей',h('div',{},chart(ctx,heatmap(labels(resultIds),columnLabels,resultIds.map(r=>indicatorIds.map(i=>{const p=pairs.find(p=>pairResult(p)===r&&pairIndicator(p)===i);return p?(kind==='lexical'?number(p.cosine??p.similarity??p.weight??p.score):1):null;})),{label:'Матрица связей',cellHeight:36,left:300,format:v=>v===null?'':fmt(v,kind==='lexical'?2:0)}),'network-'+kind,'Матрица связей',rows,'Источник: паспорта проекта. Классы документальных связей учитываются раздельно.'),h('details',{class:'efficient_transport-matrix-key'},h('summary',{},'Обозначения показателей в матрице'),indicatorIds.map((id,i)=>para(columnLabels[i]+' — '+nodeName(id),'small'))))));
 }
 add(root,note(kind==='lexical'?'Косинусная близость помогает выбрать формулировки для содержательной проверки. Порог 0,10 не является уровнем статистической значимости.':kind==='ambiguous'?'Неоднозначные записи сохраняются для проверки. Их адресатам и силе влияния не присваиваются значения.':'Принадлежность общей задаче описывает структуру паспорта. Она не устанавливает величину или направление причинного эффекта.'),reportTable(ctx,12),kind==='lexical'?reportTable(ctx,13):null,kind==='lexical'?reportTable(ctx,14):null);
 return end(ctx,root);
}
async function textPacket(path){
 const url=absolute(path);
 return textPacketCache.getOrCreate(PROJECT+':texts:'+url,async()=>{
  const response=await fetch(url);
  if(!response.ok)throw Error('Не удалось открыть текст документа');
  return response.json();
 });
}
async function texts(ctx){
 const root=start(ctx),t=doc(ctx).text||{},documents=array(t.documents),similarity=array(t.similarity||t.projectSimilarity||t.project_similarity),profile=ctx.state.document||'project',terms=array(t.terms||t.topTerms).filter(r=>r.document_id===profile),q=ctx.state.query||'';
 const selectedDocuments=documents.filter(d=>profile==='project'||d.id===profile);
 const packets=await Promise.all(selectedDocuments.map(d=>t.documentFiles?.[d.id]?textPacket(t.documentFiles[d.id]):Promise.resolve({document:d,units:[]})));
 const searchUnits=packets.flatMap(p=>array(p.units).map(u=>({...u,documentTitle:p.document.title||p.document.id,sourceURL:u.source_url||p.source_url||p.document.url})));
 const input=h('input',{type:'search',value:q,placeholder:'Например: мощность, перевозки, доступность','aria-label':'Поиск по документам'});
 const found=h('div',{class:'efficient_transport-text-results'});
 const draw=()=>{const query=input.value.trim().toLocaleLowerCase('ru');const matches=searchUnits.filter(b=>b.text&&(!query||b.text.toLocaleLowerCase('ru').includes(query)));found.replaceChildren(h('p',{class:'small muted'},'Фрагментов: '+matches.length+(matches.length>30?' · показаны первые 30, уточните запрос':'')),...matches.slice(0,30).map(b=>h('article',{class:'efficient_transport-text-fragment'},h('p',{class:'small muted'},b.documentTitle),para(b.text),link('Паспортный источник',b.sourceURL))));};input.addEventListener('input',draw);input.addEventListener('keydown',e=>{if(e.key==='Enter')ctx.set({query:input.value});});draw();
 add(root,toolbar(select('Текстовый профиль',[['project','Все паспорта проекта'],...documents.map(d=>[d.id,d.title||d.id])],profile,v=>ctx.set({document:v}))),panel('Поиск по формулировкам паспортов','Цели, задачи, результаты и показатели в нормализованном текстовом профиле. Полные документы доступны по ссылкам.',h('div',{},toolbar(input,button('Найти',()=>ctx.set({query:input.value}),'button')),found)));
 if(similarity.length)add(root,panel('Близость текстовых профилей','Одинаковые правила обработки документального корпуса',numericTable(similarity.map(r=>({project:r.project_name||r.project||r.target_project||r.name||'',score:r.cosine??r.similarity??r.value,kind:r.kind||r.method||''})),[{key:'project',label:'Проект'},{key:'score',label:'Косинус',numeric:true,decimals:5},{key:'kind',label:'Спецификация'}],'text-similarity')));
 if(terms.length)add(root,panel('Термины выбранного профиля','Вес TF–IDF',numericTable(terms.map(r=>({term:r.term||r.token||r.word,value:r.tfidf??r.weight??r.count??r.value,kind:r.document_id==='project'?'Весь проект':documents.find(d=>d.id===r.document_id)?.title||r.document_id||''})),[{key:'term',label:'Термин'},{key:'value',label:'Вес TF–IDF',numeric:true,decimals:5},{key:'kind',label:'Документ / профиль'}],'text-terms')));
 if(documents.length)add(root,panel('Документы корпуса',null,numericTable(documents.map(d=>({title:d.title||d.name||d.document_title||d.id,kind:({np:'Национальный паспорт',fp:'Федеральный паспорт'})[d.kind]||d.kind||'',url:d.url||d.source_url||d.text_url||'',tokens:d.tokens||d.token_count||d.n_tokens})),[{key:'title',label:'Документ'},{key:'kind',label:'Тип'},{key:'tokens',label:'Токены',numeric:true,decimals:0},{key:'url',label:'Источник',render:v=>link('Открыть',v)}],'text-documents')));
 if(array(t.sensitivity).length)add(root,panel('Чувствительность текстового сравнения','Сопоставление рангов других проектов с базовой спецификацией',numericTable(t.sensitivity.map(r=>({variant:({base:'Исходная спецификация',stemmed:'Стемминг русских слов',unigram:'Униграммы',unigrams:'Униграммы',equal_levels:'Равные веса уровней',federal_only:'Только федеральные паспорта',national_only:'Только национальные паспорта'})[r.variant]||r.variant,rho:r.spearman,nearest:array(r.top3).join(' · ')})),[{key:'variant',label:'Спецификация'},{key:'rho',label:'Корреляция Спирмена',numeric:true,decimals:4},{key:'nearest',label:'Три ближайших проекта'}],'text-sensitivity')));
 if(array(t.notes).length)add(root,panel('Основания текстового расчёта',null,h('div',{},array(t.notes).map(item=>para(text(item))))));
 if(array(t.tieSensitivity).length)add(root,panel('Устойчивость отбора лексических пар','Разрешение равенства коэффициентов на границе трёх кандидатов',numericTable(t.tieSensitivity.map(r=>({rule:({source_node_sha:'По идентификатору исходного узла',source_card_order:'По порядку карточек источника',title_ascending:'По названию, в алфавитном порядке',title_descending:'По названию, в обратном порядке'})[r.rule]||r.rule,pairs:r.pairs,results:r.results,indicators:r.unique_indicators})),[{key:'rule',label:'Правило разрешения равенства'},{key:'pairs',label:'Пары',numeric:true,decimals:0},{key:'results',label:'Результаты',numeric:true,decimals:0},{key:'indicators',label:'Различные показатели',numeric:true,decimals:0}],'text-tie-sensitivity')));
 add(root,reportTable(ctx,13),reportTable(ctx,14),note('Близость формулировок описывает лексический состав документов. Для вывода о связи нужны проверка географии, объекта, механизма и временного лага. Коэффициент сходства не измеряет причинный эффект.'));
 return end(ctx,root);
}
export function targetsForDomain(targets,domain){
 const normalize=value=>String(value||'').toLocaleLowerCase('ru').replace(/ё/g,'е').replace(/\s+/g,' ').trim();
 const membership=new Set(array(targets?.allCards).filter(card=>card.fp===domain||card.federal_project_code===domain).map(card=>normalize(card.title||card.name||card.indicator_name)));
 return array(targets?.items).filter(item=>[item.federal_project_code,item.fp,item.project_code].some(value=>value===domain)||membership.has(normalize(item.title||item.name||item.indicator_name)));
}
function domains(ctx){
 const root=start(ctx),selected=FEDERAL.find(p=>p[0]===ctx.state.domain)||FEDERAL[0],definition=array(exp(ctx).derived?.federalProjects).find(p=>p.code===selected[0]);
 const targetRows=targetsForDomain(doc(ctx).targets||data(ctx).targets||{items:ana(ctx).targets},selected[0]);
 add(root,toolbar(select('Федеральное направление',FEDERAL.map(([id,title])=>[id,id+'. '+title]),selected[0],v=>ctx.set({domain:v}))),panel(selected[1],null,h('div',{},para(selected[2]),definition?.mechanism?para(definition.mechanism):null,definition?.transition?para('Проверяемый переход: '+definition.transition):null,...reportPassages(ctx,array(definition?.mechanismBlocks).map(id=>Number(String(id).replace(/^b/,'')))),definition?.source_url?link('Паспорт федерального проекта',definition.source_url):null,h('p',{}),link('Финансовые основания',route('finance')),h('span',{},' · '),link('Документальные связи',route('network')))));
 if(targetRows.length)add(root,panel('Плановые показатели направления',null,h('div',{class:'efficient_transport-download-grid'},targetRows.map(t=>link(t.title||t.name||t.indicator_name,route('projections',{target:String(code(t))}))))));
 add(root,reportTable(ctx,1),reportTable(ctx,3));return end(ctx,root);
}
function proposals(ctx){return end(ctx,add(start(ctx),reportTable(ctx,15,'Основания экспертной оценки'),reportTable(ctx,16,'Приоритетные изменения мониторинга'),panel('Проверка применения рекомендаций',null,para('Для каждого изменения определяются совокупность наблюдения, ответственный за источник, период и решение, для которого собираются данные. Рекомендуемые этапы сохраняют авторский статус и не выдаются за нормативные сроки.'))));}

export function ratioPercent(numerator,denominator){return Number.isFinite(numerator)&&Number.isFinite(denominator)&&numerator>=0&&denominator>0?100*numerator/denominator:null;}
export function generalizedCost(payment,time,timeValue,reliabilityLoss){return[payment,time,timeValue,reliabilityLoss].every(x=>Number.isFinite(x)&&x>=0)?payment+time*timeValue+reliabilityLoss:null;}
export function bottleneckCapacity(capacities){return Array.isArray(capacities)&&capacities.length>0&&capacities.every(x=>Number.isFinite(x)&&x>=0)?Math.min(...capacities):null;}
export function accessiblePopulationShare(areas,threshold){if(!Array.isArray(areas)||!areas.length||!Number.isFinite(threshold)||threshold<0||!areas.every(r=>Number.isFinite(r.population)&&r.population>=0&&Number.isFinite(r.time)&&r.time>=0))return null;return ratioPercent(areas.reduce((sum,r)=>sum+(r.time<=threshold?r.population:0),0),areas.reduce((sum,r)=>sum+r.population,0));}
export function capacityIndex(goods,passengers){return[goods,passengers].every(x=>Number.isFinite(x)&&x>=0)?100*(.72*goods+.28*passengers):null;}
export function digitalIndex(electronicDocuments){return ratioPercent(electronicDocuments,5e9);}
export function investmentIndex(efficiency,selectedFunding,totalFunding){return Number.isFinite(efficiency)&&Number.isFinite(selectedFunding)&&selectedFunding>=0&&Number.isFinite(totalFunding)&&totalFunding>0&&selectedFunding<=totalFunding?100+efficiency/.66*(selectedFunding/totalFunding)*100:null;}
export function requiredAnnualChange(base,target,years){return Number.isFinite(base)&&Number.isFinite(target)&&Number.isFinite(years)&&base>0&&target>=0&&years>0?100*(Math.pow(target/base,1/years)-1):null;}
const CALCULATORS=[['generalized_cost','Обобщённые издержки'],['bottleneck','Ограничивающее звено'],['accessibility','Доступность населения'],['capacity_index','Индекс мощности сети'],['digital_index','Индекс цифровизации'],['investment_index','Индекс эффективности инвестиций']];
function calculator(ctx,kind){
 const specs={
  generalized_cost:{title:'Обобщённые издержки перевозки',description:'C = P + vT + R. Платежи, стоимость времени и ожидаемые потери от ненадёжности относятся к одной поездке или перевозке.',fields:[['payment','Денежные платежи, руб.'],['time','Полное время, часов'],['time_value','Стоимость часа, руб.'],['loss','Ожидаемые потери от ненадёжности, руб.']],compute:v=>generalizedCost(v.payment,v.time,v.time_value,v.loss),unit:'руб.',block:84,invalid:'Введите четыре неотрицательных значения в указанных единицах. Стоимость времени и ненадёжности требует самостоятельного обоснования.'},
  bottleneck:{title:'Пропускная способность последовательной цепи',description:'Q ≤ min(C₁, C₂, C₃). Три последовательных звена должны обслуживать одну категорию потока за одинаковый период. Альтернативные пути требуют отдельной модели.',fields:[['capacity1','Мощность первого звена, ед. за период'],['capacity2','Мощность второго звена, ед. за период'],['capacity3','Мощность третьего звена, ед. за период']],compute:v=>bottleneckCapacity([v.capacity1,v.capacity2,v.capacity3]),unit:'ед. за период – верхняя граница потока',block:87,invalid:'Введите неотрицательные мощности трёх последовательных звеньев в одной единице и за один период.'},
  accessibility:{title:'Доля населения в пределах времени доступа',description:'Доли взвешиваются численностью населения. Для каждой из трёх выбранных территорий задайте полное время достижения одной и той же услуги, затем единый порог. Результат относится только к введённой совокупности.',fields:[['population1','Население территории 1, человек'],['time1','Время доступа территории 1, минут'],['population2','Население территории 2, человек'],['time2','Время доступа территории 2, минут'],['population3','Население территории 3, человек'],['time3','Время доступа территории 3, минут'],['threshold','Порог доступности, минут']],compute:v=>accessiblePopulationShare([1,2,3].map(i=>({population:v['population'+i],time:v['time'+i]})),v.threshold),unit:'% введённого населения',block:94,invalid:'Введите неотрицательные численности, время и порог. Суммарная численность должна быть положительной.'},
  capacity_index:{title:'Агрегированный индекс мощности сети',description:'100 × (0,72 × Kг + 0,28 × Kп). Вводятся отношения мощностей к базовому уровню 2024 года: 1 означает сохранение базы, 1,1 – увеличение на 10%.',fields:[['goods','Отношение грузовой мощности к базе'],['passengers','Отношение пассажирской мощности к базе']],compute:v=>capacityIndex(v.goods,v.passengers),unit:'% к базе 2024 года',block:124,invalid:'Введите два неотрицательных отношения к одной базовой редакции. Значение 1 означает 100% базовой мощности.'},
  digital_index:{title:'Индекс цифровой трансформации грузоперевозок',description:'Электронные документы с начала года / 5 000 000 000 × 100%. Пять миллиардов – фиксированный прогнозный знаменатель 2030 года. Текущая доля электронных документов требует фактического сопоставимого знаменателя.',fields:[['documents','Электронные документы с начала года, штук']],compute:v=>digitalIndex(v.documents),unit:'% фиксированного ориентира',block:151,invalid:'Введите неотрицательное число электронных перевозочных документов с начала выбранного года.'},
  investment_index:{title:'Индекс эффективности инвестиций по методике',description:'100 + (I / 0,66) × (Qпроект / Qвсего) × 100. Расчётная эффективность измеряется в т·км/руб. В доле финансирования сопоставляются отобранные с применением ГИС проекты и все инвестиционные мероприятия данного национального проекта за одинаковый период. Формула не идентифицирует причинный эффект применения ГИС.',fields:[['efficiency','Расчётная эффективность, т·км/руб.',null],['selected','Федеральное финансирование проектов, отобранных с применением ГИС, руб.'],['total','Федеральное финансирование всех инвестиционных мероприятий нацпроекта, руб.']],compute:v=>investmentIndex(v.efficiency,v.selected,v.total),unit:'пунктов индекса',block:155,invalid:'Введите эффективность, положительное общее финансирование и неотрицательную сумму отобранных проектов, не превышающую общий объём.'}
 };
 const key=Object.hasOwn(specs,kind)?kind:'generalized_cost',spec=specs[key],inputs={},out=h('div',{class:'efficient_transport-calculation-output',role:'status','aria-live':'polite'});
 const fields=spec.fields.map(([key,label,min=0])=>{const inp=h('input',{type:'number',step:'any',value:'','aria-label':label,...(min===null?{}:{min})});inputs[key]=inp;return h('label',{class:'field'},h('span',{},label),inp);});
 function calculate(){const vals=Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,number(v.value)]));const result=Object.values(vals).every(v=>v!==null)?spec.compute(vals):null;out.replaceChildren(finite(result)?h('div',{},h('strong',{},fmt(result,4)+' '+spec.unit),para('Условный результат по введённым значениям.','small')):para(spec.invalid));}
 Object.values(inputs).forEach(inp=>inp.addEventListener('input',calculate));calculate();
 return panel(spec.title,'Формула авторской экспертизы',h('div',{class:'efficient_transport-calculator',dataset:{calculator:key}},para(spec.description),h('div',{class:'efficient_transport-input-grid'},fields),out,link('Формула и условия применения в докладе',(exp(ctx).meta.html_url||BASE+'report/expertise_transport_2026.html')+'#b'+spec.block),note('Параметры остаются в браузере. Условный расчёт не является статистическим наблюдением, прогнозом или установленным эффектом проекта.')));
}
function causal(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Объект и начало воздействия',text:'Фиксируются состав инфраструктуры, дата фактического ввода, зона действия и ожидаемый временной лаг.'},
 {title:'Сопоставимая предыстория',text:'Группа сравнения определяется до анализа результата. Проверяются исходная динамика, отбор объектов и изменение спроса.'},
 {title:'Перенос потока',text:'Соседние и альтернативные маршруты позволяют различить дополнительную перевозку и её перераспределение.'},
 {title:'Стоимость и устойчивость',text:'Сценарии согласуют спрос, сроки, стоимость, эксплуатационную готовность и обязательства при неблагоприятном исходе.'}
 ]),panel('Границы имеющихся сведений',null,para('Общероссийские агрегаты и паспортные связи не идентифицируют дополнительный эффект отдельного объекта. Для разновременного ввода требуется оценка, учитывающая различия сроков воздействия и групп.')),reportTable(ctx,15)));}
function population(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Полная поездка',text:'Подход к узлу, ожидание, пересадка и сопровождение учитываются вместе со временем магистрального участка.'},
 {title:'Различия пользователей',text:'Семьи с детьми, маломобильные граждане, пожилые и жители удалённых поселений сталкиваются с различными ограничениями.'},
 {title:'Расписание и надёжность',text:'Наличие инфраструктуры проверяется вместе с частотой рейсов, отменами и возможностью возвращения.'},
 {title:'Социально необходимое сообщение',text:'Низкая коммерческая загрузка требует рассмотрения стандарта доступности, последствий срыва и доступных альтернатив.'}
 ]),calculator(ctx,'accessibility'),panel('Участие населения в наблюдениях',null,para('Количество поездок не определяет число людей с улучшившимся доступом. Нужны устойчивые группы наблюдения и сведения о людях, которые не смогли воспользоваться сообщением.'))));}
function structure(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Расчётная мощность',text:'Техническая возможность относится к конкретному составу объектов, грузов и режиму работы.'},
 {title:'Согласованная цепь',text:'Подходы, терминал, граница, флот и расписание могут ограничивать итоговый поток.'},
 {title:'Фактическое использование',text:'Перевозки, транспортная работа и надёжность сохраняют разные единицы и содержание.'},
 {title:'Дополнительный результат',text:'Общесистемное изменение проверяется с учётом переноса потока и спроса на альтернативных маршрутах.'}
 ]),calculator(ctx,'bottleneck'),reportFigure(ctx,1),reportTable(ctx,4)));}
function lab(ctx){const kind=CALCULATORS.some(([k])=>k===ctx.state.calculator)?ctx.state.calculator:'generalized_cost';return end(ctx,add(start(ctx),toolbar(select('Расчёт',CALCULATORS,kind,v=>ctx.set({calculator:v}))),calculator(ctx,kind),panel('Условия применения',null,para('Вводимые величины относятся к сопоставимым периодам, единицам и совокупностям. Неизвестные значения сохраняются пустыми. Отношения с нулевым знаменателем не вычисляются. Для оценки пользователя и объекта предпосылки задаются отдельно.'))));}


export function targetSeries(t){
 const raw=t.years||t.targets||t.annual_targets||t.values||t.series||[];
 if(Array.isArray(raw))return raw.map(r=>({year:Number(r.year||String(r.period||'').slice(0,4)),value:number(r.value??r.target??r.target_value)})).filter(r=>r.year>=2025&&r.year<=2030);
 return Object.entries(raw).map(([year,v])=>({year:Number(year),value:number(v!==null&&typeof v==='object'?v.value??v.target:v)})).filter(r=>r.year>=2025&&r.year<=2030);
}
function projections(ctx){
 const root=start(ctx),targets=array(doc(ctx).targets?.items||ana(ctx).targets||data(ctx).targets?.items),selected=targets.find(t=>String(code(t))===ctx.state.target)||targets.find(t=>targetSeries(t).length)||targets[0];
 if(selected){
  const series=targetSeries(selected),rows=series.map(r=>({...r,unit:selected.unit||selected.target_unit||''}));
  add(root,toolbar(select('Паспортный показатель',targets.map(t=>[String(code(t)),t.title||t.name||t.indicator_name||String(code(t))]),String(code(selected)),v=>ctx.set({target:v}))),para(selected.title||selected.name||selected.indicator_name||''),note('Паспортные цели представлены как плановая траектория. Пропущенные ранние годы не заменяются нулевыми значениями. Вероятность достижения цели и прогнозная точность по этой траектории не определяются.'));
  if(rows.length){
   add(root,panel('Паспортные цели 2025–2030 годов',selected.unit||selected.target_unit||'',chart(ctx,lineChart([{name:'Паспортный план',points:rows.map(r=>({x:Date.UTC(r.year,11,31),y:r.value})),color:C[0]}],{unit:selected.unit||selected.target_unit||'',label:'Паспортная траектория'}),'plans-'+String(code(selected)),'Паспортная траектория',rows,'Источник: паспортные редакции в документальном корпусе. Плановые значения.'),link('Паспортный источник',selected.source_url||selected.url)));
   add(root,panel('Плановые значения',null,numericTable(rows,[{key:'year',label:'Год'},{key:'value',label:'План',numeric:true,decimals:5},{key:'unit',label:'Единица'}],'plans')));
   const usable=rows.filter(r=>r.value!==null),first=usable[0],last=usable.at(-1),growth=first&&last?requiredAnnualChange(first.value,last.value,last.year-first.year):null;
   if(growth!==null)add(root,stats([['Среднегодовое изменение плана',fmt(growth,3)+'%',first.year+'–'+last.year+'; геометрический темп между плановыми точками']]));
  }
 }
 add(root,reportTable(ctx,2),reportTable(ctx,3),panel('Допустимость прогноза',null,methodsTable(array(ana(ctx).forecast_eligibility).map(r=>({name:r.title||r.source_id,status:r.eligible?'Пригодность требует проверки модели':'Недостаточно оснований',reason:r.reason||r.note||'Повторные публикации технических и годовых уровней требуют проверки числа независимых наблюдений.'})))));
 return end(ctx,root);
}
async function explorer(ctx){
 const root=start(ctx),s=selectedSource(ctx);if(!s)return end(ctx,root);
 const all=await observations(s),regions=[...new Map(all.map(r=>[national(r)?'national':regionId(r),rowName(r)||'Российская Федерация'])).entries()],periods=[...new Set(all.map(period))].sort(),cats=[...new Set(all.map(categoryKey))];
 const rows=all.filter(r=>(!ctx.state.region||(ctx.state.region==='national'?national(r):regionId(r)===ctx.state.region))&&(!ctx.state.period||String(period(r))===ctx.state.period)&&(!ctx.state.category||categoryKey(r)===ctx.state.category));
 add(root,toolbar(sourcePicker(ctx,s),select('Территория',[['','Все территории'],...regions],ctx.state.region||'',v=>ctx.set({region:v})),select('Период',[['','Все периоды'],...periods.map(p=>[String(p),String(p)])],ctx.state.period||'',v=>ctx.set({period:v})),cats.length>1?select('Категория',[['','Все категории'],...cats.map(c=>[c,Object.entries(JSON.parse(c)).map(([k,v])=>k+': '+v).join(' · ')||'Без дополнительной категории'])],ctx.state.category||'',v=>ctx.set({category:v})):null));
 add(root,stats([['Записей в выборке',fmt(rows.length,0),''],['Пригодны к расчёту',fmt(rows.filter(r=>value(r)!==null).length,0),'Исходные значения сохранены'],['Единица',s.unit||'В источнике','ЕМИСС '+sourceId(s)]]),panel('Наблюдения',null,pointsTable(rows,s)),sourceNote(s));
 return end(ctx,root);
}
const DOWNLOAD_LABELS={observations:'Все наблюдения CSV',registry:'Реестр показателей CSV',comparisons:'Сопоставления с целями CSV',original_snapshot:'Исходный статистический срез',full:'Полный документальный набор',source_archive:'Сохранённые паспорта',finance:'Финансирование по годам CSV',targets:'Паспортные цели CSV',network:'Связи через общую задачу CSV',lexical:'Лексические кандидаты CSV',sources:'Исходные источники',inputs:'Входные данные',sources_index:'Реестр источников',full_documentary:'Полный документальный набор',finance_years:'Финансирование по годам',finance_sources:'Финансовые строки',text:'Текстовый анализ',code:'Код расчётов'};
function downloads(records){return(Array.isArray(records)?records.map((r,i)=>[i,r]):Object.entries(records||{})).map(([key,v])=>link(v?.label||v?.title||DOWNLOAD_LABELS[key]||String(key),typeof v==='string'?v:v?.path||v?.url));}
function library(ctx){
 const root=start(ctx),meta=exp(ctx).meta;
 add(root,panel('Авторская экспертиза',date(meta.edition_date),h('div',{class:'efficient_transport-download-grid'},link('Полный отчёт Word',report(ctx)),link('Читаемый отчёт HTML',meta.html_url||BASE+'report/expertise_transport_2026.html'),link('Полный текст Markdown',meta.markdown_url),link('Структурированное извлечение',meta.extract_url),link('Проверка полноты',meta.coverage_url))));
 add(root,stats([['Таблицы',fmt(array(exp(ctx).tables).length,0),'Исходные таблицы и CSV'],['Иллюстрации',fmt(array(exp(ctx).figures).length,0),'Файлы из авторского отчёта'],['Сноски',fmt(meta.footnotes,0),'Полные ссылки и исходные номера']]));
 const docs=array(doc(ctx).sources).map(r=>({title:r.genre==='presentation'?'Архивная презентация «Эффективная транспортная система»':r.title||r.document_title||r.id,kind:({np:'Национальный паспорт',fp:'Федеральный паспорт',pdf_archive:'Архивный PDF',html_passport:'Паспорт HTML'})[r.kind||r.source_kind||r.genre]||r.format||'',date:r.retrieved_at||r.snapshot_at||r.date||'',url:r.url||r.source_url,local:r.local_url||r.download_url||r.text_url,note:r.qualification||''}));
 if(docs.length)add(root,panel('Паспортные и сопутствующие источники',null,numericTable(docs,[{key:'title',label:'Документ'},{key:'kind',label:'Тип'},{key:'date',label:'Дата получения',render:date},{key:'url',label:'Публикация',render:v=>link('Источник',v)},{key:'local',label:'Сохранённый файл',render:v=>v?link('Открыть',v):'В исходном корпусе'},{key:'note',label:'Статус источника'}],'document-sources')));
 add(root,panel('Статистика и расчёты',null,h('div',{class:'efficient_transport-download-grid'},['statistics','analytics','documentary','refresh-status','expertise'].map(name=>link(({statistics:'Статистические публикации',analytics:'Расчёты по наблюдениям',documentary:'Документальная аналитика','refresh-status':'Состояние обновления',expertise:'Структура полной экспертизы'})[name],'data/projects/efficient_transport/'+name+'.json')),downloads(stat(ctx).downloads),downloads(doc(ctx).downloads))));
 add(root,panel('Исходные таблицы',null,h('div',{class:'efficient_transport-download-grid'},array(exp(ctx).tables).map(t=>link(t.title,t.csv_url||t.download_url||BASE+'report/'+t.id+'.csv')))),panel('Иллюстрации',null,h('div',{class:'efficient_transport-download-grid'},array(exp(ctx).figures).map(f=>link(f.title,f.url)))));
 add(root,panel('Повторить сборку',null,h('div',{},para('Исходные файлы и процедуры входят в накопительный комплект. Сборка использует сохранённые данные. Обращение к ЕМИСС выполняется отдельной командой.'),h('pre',{},h('code',{},'npm run build\nnpm run validate\nnpm run analytics:transport\nnpm run refresh:transport')),link('Код платформы','downloads/code/platform/build_transport_analytics.py'))));
 return end(ctx,root);
}
function updates(ctx){
 const root=start(ctx),r=data(ctx).refresh||{},status={imported_verified_snapshot:'Импортирован проверенный срез',verified_source_snapshot:'Проверенный исходный срез',retained_verified_snapshot:'Сохранён проверенный срез',imported:'Импортирован проверенный срез',not_checked:'Новая проверка не выполнялась',not_attempted:'Новая проверка не выполнялась',failed:'Запрос не подтвердил обновление',partial:'Частичное обновление',updated:'Опубликованы проверенные данные',success:'Проверка завершена'};
 add(root,stats([['Статистический срез',date(r.statistical_as_of||stat(ctx).statistical_as_of),'Периоды наблюдений указаны в рядах'],['Последняя проверка',date(r.checked_at||r.last_checked_at),'Дата сетевого обращения, если оно выполнялось'],['Состояние',status[r.state]||r.message||r.state||'Сохранённый срез','']]));
 if(r.message)add(root,note(r.message));
 const rows=array(r.sources).map(s=>({id:sourceId(s),title:s.title||sourceName(s),state:status[s.state]||s.state||s.status||'',checked:s.checked_at||'',success:s.last_success||s.published_at||'',detail:s.message||s.error||''}));
 if(rows.length)add(root,panel('Состояние источников',null,numericTable(rows,[{key:'id',label:'ЕМИСС'},{key:'title',label:'Показатель'},{key:'state',label:'Состояние'},{key:'checked',label:'Последняя проверка',render:date},{key:'success',label:'Последние проверенные данные',render:date},{key:'detail',label:'Примечание'}],'refresh-status')));
 add(root,panel('Правила обновления',null,h('div',{},para('При неуспешном запросе сохраняются последние проверенные значения и их происхождение. Новый ответ сначала проходит проверку структуры, единицы и территориального состава. Авторский отчёт сохраняет дату своей редакции.'),link('Проверить наблюдения',route('explorer')),h('span',{},' · '),link('Состояние обновления JSON','data/projects/efficient_transport/refresh-status.json'))));
 return end(ctx,root);
}
function methods(ctx){return end(ctx,add(start(ctx),panel('Пригодность методов','Состояние расчёта и доказательные основания',methodsTable(ctx.methods)),note('Региональные разрезы исследованных статистических таблиц отсутствуют. Региональные рейтинги, PCA, кластеризация, пространственная статистика и механическое продолжение повторяющихся месячных уровней не рассчитаны. Документальные связи и условные формулы сохраняют собственный смысл.'),reportTable(ctx,4)));}
const renderers={overview,framework,logic,audit,targets,map:geography,regions,finance,network,texts,domains,causal,proposals,projections,population,structure,methods,lab,explorer,library,updates};
export async function renderEfficientTransport(ctx){return(renderers[ctx.state.page]||overview)(ctx);}
