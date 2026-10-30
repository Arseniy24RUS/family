import {observationCache, textPacketCache} from '../core/cache.js';
import {h,svg,para,note,button,select,fmt,icon,csvDownload} from '../core/dom.js';
import {heading,panel,toolbar,stats,table,figure,figureControls,empty} from '../components/ui.js';
import {bars,lineChart,legend,heatmap} from '../components/charts.js';
import {mapView} from '../components/map.js';
import {C} from '../platform/theme.js';
import {projectHref,tourismPages} from '../platform/projects.js';

const PROJECT='tourism',BASE='downloads/projects/tourism/';
const array=x=>Array.isArray(x)?x:[],text=x=>typeof x==='string'?x:typeof x==='number'?String(x):x?.text||x?.summary||x?.title||'';
const number=x=>x===null||x===undefined||String(x).trim()===''?null:Number.isFinite(Number(String(x).replace(/[\s\u00a0]/g,'').replace(',','.')))?Number(String(x).replace(/[\s\u00a0]/g,'').replace(',','.')):null;
const finite=x=>number(x)!==null;
const value=r=>r?.excluded?null:Object.hasOwn(r||{},'analytical_value')?number(r.analytical_value):number(r?.value);
const absolute=p=>/^https?:\/\//.test(p||'')?p:'./'+String(p||'').replace(/^\.\//,'');
const link=(label,path,cls='text-link')=>path?h('a',{href:absolute(path),class:cls,...(/^https?:/.test(path)?{target:'_blank',rel:'noopener noreferrer'}:{})},label):h('span',{},label);
const date=d=>/^\d{4}-\d{2}-\d{2}/.test(d||'')?new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow'}).format(new Date(d)):d||'Не установлена';
const data=ctx=>ctx.tourism,exp=ctx=>data(ctx).expertise,stat=ctx=>data(ctx).statistics,ana=ctx=>data(ctx).analytics,doc=ctx=>data(ctx).documentary;
const sourceId=s=>String(s?.source_id??s?.id??''),sourceName=s=>s?.short_title||s?.title||'Источник '+sourceId(s);
const sources=ctx=>array(stat(ctx).sources),report=ctx=>exp(ctx).meta.download_url||exp(ctx).meta.report_url||BASE+'report/expertise_tourism_2026.docx';
const pageData=ctx=>exp(ctx).pages[ctx.state.page]||{};
const route=(page,params={})=>projectHref(PROJECT,page,params);
const code=r=>r?.indicator_code||r?.code||r?.id||'';
const rowName=r=>r?.territory_name||r?.name||r?.region_name||r?.territory||'';
const regionId=r=>String(r?.map_id||r?.region_id||r?.code||r?.region_code||r?.territory_code||'').padStart(2,'0');
const national=r=>['national','russia','country'].includes(r.geo_level)||r.is_national===true||/^Российская Федерация/.test(rowName(r));
const categoryKey=r=>JSON.stringify(Object.fromEntries(Object.entries(r.category||{}).sort(([a],[b])=>a.localeCompare(b))));
const period=r=>r?.period||r?.period_end||r?.year||'';
const frequency=r=>({annual:'Год',yearly:'Год',monthly:'Месяц',quarterly:'Квартал',cumulative_ytd:'С начала года',quarterly_cumulative:'С начала года, квартальная оценка',monthly_stock:'На конец месяца',annual_repeated_monthly:'Публикация годовой оценки',annual_estimate:'Годовая оценка'})[r?.frequency]||r?.frequency||'';
const TITLE={overview:'Туризм и гостеприимство',...Object.fromEntries(tourismPages.filter(p=>p.id!=='overview').map(p=>[p.id,p.title]))};
const LEAD={
 overview:'Туристические поездки, работа средств размещения, доступность отдыха и результаты государственной поддержки.',
 framework:'Определения показателей, стадии реализации проекта и источники определяют границы каждого вывода.',
 logic:'Пять федеральных направлений связывают инфраструктуру, спрос, кадры и промышленное обеспечение туристической отрасли.',
 audit:'Карточка показателя сохраняет единицу измерения, период, совокупность, источник и условия сопоставления с целью.',
 targets:'Паспортные ориентиры сопоставляются с наблюдениями при совпадении определения, единицы и календарного периода.',
 map:'Картограмма показывает распределение туристических поездок по наблюдаемым территориям за выбранный период.',
 regions:'Региональные различия рассматриваются в пределах одного показателя и сопоставимого периода.',
 finance:'Паспортные суммы, бюджетная роспись и предложения будущих лет имеют разные основания и стадии финансового учёта.',
 network:'Общая задача, неоднозначная запись влияния и лексическая близость имеют самостоятельные основания.',
 texts:'Формулировки паспортов доступны вместе с исходными документами, текстовыми совпадениями и ограничениями интерпретации.',
 domains:'Номерной фонд, морские курорты, туристическая привлекательность, кадры и отечественная продукция оцениваются по собственным механизмам.',
 causal:'Оценка дополнительного эффекта требует даты начала воздействия, исходной динамики и обоснованной группы сравнения.',
 proposals:'Предложения связаны с определениями показателей, учётом ресурсов, использованием мощности и доступностью туристических услуг.',
 projections:'Плановые значения и условный расчёт требуемого изменения сохраняют исходные единицы и горизонт.',
 population:'Количество поездок не определяет долю населения, имеющего возможность отдыхать. Для оценки доступности нужны наблюдения людей и домохозяйств.',
 structure:'Номер в реестре, действующая мощность, проданная ночёвка и местный экономический результат требуют разных наблюдений.',
 methods:'Применимость каждого метода определяется составом источников, числом независимых наблюдений и сопоставимостью измерений.',
 lab:'Расчёты загрузки, сезонности, доступности и удельных затрат выполняются при явно заданных исходных величинах.',
 explorer:'Наблюдения можно отобрать по источнику, территории, периоду и категории. Выгрузка сохраняет единицы и признаки качества.',
 library:'Полный авторский отчёт, паспорта, статистические публикации, таблицы, иллюстрации и код расчётов.',
 updates:'Сохранённый статистический срез и результат последнего обращения к источнику имеют самостоятельные даты.'
};

function references(ctx,ids=[]){return array(ids).length?h('div',{class:'tourism-references'},array(ids).map(id=>array(exp(ctx).sources).find(s=>s.id===id)).filter(Boolean).map(s=>link(s.note_number?'['+s.note_number+'] '+(s.title||s.text):s.title||s.text,s.url||report(ctx)))):null;}
function sourceFoot(ctx,label,path){return h('div',{class:'source-foot'},h('span',{},label||'Статистический срез: '+date(stat(ctx).statistical_as_of)),path?link('Источник и данные',path):link('Источники',route('library')));}
function tableNode(ctx,t){
 if(!t)return null;
 const rows=array(t.rows),cols=array(t.columns).map((c,i)=>({key:c.key||'c'+i,label:c.label||c.title||c.key,render:(v,r)=>h('span',{},v??'–',array(t.cellSourceIds?.[rows.indexOf(r)]?.[i]).length?h('sup',{},array(t.cellSourceIds[rows.indexOf(r)][i]).map(id=>{const s=array(exp(ctx).sources).find(s=>s.id===id);return s?link(' ['+(s.note_number||id.replace('fn_',''))+']',s.url||report(ctx)):null;})):null)}));
 return h('div',{},table(rows,cols,{caption:t.title,filename:'tourism-'+t.id+'.csv',pageSize:12}),t.note?para(t.note,'small muted'):null,references(ctx,t.sourceIds));
}
function reportTable(ctx,n,title){const t=array(exp(ctx).tables).find(t=>t.number===n);return t?panel(title||t.title,'Авторская экспертиза',tableNode(ctx,t)):null;}
function reportBlock(ctx,b){
 const attrs={id:'tourism-'+b.id,class:'tourism-report-block'};let node;
 if(b.type==='heading')node=h('h'+Math.max(2,Math.min(4,b.level||2)),attrs,b.text);
 else if(b.type==='table')node=h('section',attrs,h('h3',{},b.title),tableNode(ctx,b));
 else if(b.type==='formula')node=h('div',attrs,h('div',{class:'formula'},b.text||b.latex),b.note?para(b.note):null);
 else if(b.type==='figure_ref'){
  const f=array(exp(ctx).figures).find(f=>f.id===b.figureId),url=b.url||f?.url;
  node=h('figure',{...attrs,class:'tourism-report-figure'},url?link(h('img',{src:absolute(url),alt:b.title||f?.title||'Иллюстрация экспертизы',loading:'lazy'}),url):null,h('figcaption',{},b.title||f?.title),b.note||f?.note?para(b.note||f.note,'small muted'):null);
 }else if(b.type==='list')node=h('div',attrs,array(b.items).map(t=>para(text(t))));
 else node=h('p',attrs,b.text||'');
 return h('div',{},node,references(ctx,b.sourceIds));
}
function start(ctx){return h('div',{class:'tourism-page',dataset:{tourismPage:ctx.state.page,routeState:JSON.stringify(ctx.state)}},heading(TITLE[ctx.state.page]||pageData(ctx).title,LEAD[ctx.state.page],ctx.state.page==='overview'?h('img',{class:'tourism-logo',src:ctx.project.logo,alt:'Логотип национального проекта «Туризм и гостеприимство»',width:136,height:116}):null));}
function end(ctx,root){
 const p=pageData(ctx);
 if(array(p.blocks).length)root.append(h('details',{class:'tourism-report'},h('summary',{},icon('table',18),'Текст экспертизы, таблицы и источники раздела'),h('div',{class:'tourism-report-body'},p.blocks.map(b=>reportBlock(ctx,b)),references(ctx,p.sources))));
 root.append(sourceFoot(ctx,'Авторская экспертиза: '+date(exp(ctx).meta.edition_date)+' · Статистический срез: '+date(stat(ctx).statistical_as_of),report(ctx)),h('p',{class:'small'},link('Читать полную текстовую страницу','research/projects/tourism/'+(ctx.state.page==='overview'?'index':ctx.state.page)+'.html')));
 return root;
}
function add(root,...nodes){root.append(...nodes.filter(Boolean));return root;}
function chart(ctx,node,name,title,rows=[],source=''){
 const result=figure(node,{name:'tourism-'+name,title:'Туризм и гостеприимство · '+title,source:source||'Источник: ЕМИСС. Срез '+date(stat(ctx).statistical_as_of),rows});
 const wrapper=h('div',{class:'tourism-chart-scroll',tabindex:'0','aria-label':title});node.replaceWith(wrapper);wrapper.append(node);return result;
}
function cards(items){return h('div',{class:'project-grid tourism-cards'},items.map(item=>h('article',{class:'project-card'},h('h3',{},item.title),para(item.text),item.path?link('Открыть раздел',item.path):null)));}
function numericTable(rows,columns,filename){return table(rows,columns,{filename:'tourism-'+filename+'.csv',pageSize:12});}
function methodsTable(items){return table(items.map(m=>({title:m.name||m.method_name||m.title||m.method||m.method_id,status:m.current_label||m.current_status_label||m.status_label||m.status||'',reason:m.current_limitations||m.current_evidence||m.current_reason||m.current_note||m.evidence||m.reason||m.note||m.interpretation||''})),[{key:'title',label:'Метод'},{key:'status',label:'Состояние'},{key:'reason',label:'Основания и ограничения'}],{filename:'tourism-methods.csv'});}
async function observations(source){
 if(Array.isArray(source?.observations))return source.observations;
 const id=sourceId(source);
 return observationCache.getOrCreate(PROJECT+':observations:'+id,async()=>{
  const response=await fetch('./data/projects/tourism/series/'+id+'.json');
  if(!response.ok)throw Error('Не удалось загрузить источник '+id+' (HTTP '+response.status+')');
  const packet=await response.json();
  return array(packet.observations||packet.rows);
 });
}
function selectedSource(ctx,regional=false){const eligible=sources(ctx).filter(s=>!regional||array(s.regional_latest).length||s.regional_count>0||s.has_regional_data);return eligible.find(s=>sourceId(s)===ctx.state.source)||eligible.find(s=>sourceId(s)==='62900')||eligible[0];}
function sourcePicker(ctx,selected,regional=false){return select('Показатель',sources(ctx).filter(s=>!regional||array(s.regional_latest).length||s.regional_count>0||s.has_regional_data).map(s=>[sourceId(s),sourceName(s)]),sourceId(selected),v=>ctx.set({source:v,period:'',category:'',region:''}));}
function pointsTable(rows,source){return numericTable(rows.map(r=>({territory:rowName(r)||'Российская Федерация',period:period(r),frequency:frequency(r),value:r.value,unit:r.unit||source.unit,category:Object.entries(r.category||{}).map(([k,v])=>k+': '+v).join(' · '),quality:array(r.quality_flags).map(f=>typeof f==='string'?f:f.message||f.label||f.code).join(' · ')||(r.excluded?'Исключено из расчёта':'')})),[{key:'territory',label:'Территория'},{key:'period',label:'Период'},{key:'frequency',label:'Периодичность'},{key:'value',label:'Значение',numeric:true,decimals:5},{key:'unit',label:'Единица'},{key:'category',label:'Категория'},{key:'quality',label:'Примечание'}],'source-'+sourceId(source));}
function sourceNote(source){return h('div',{class:'tourism-source-note'},para(source.semantic_note||source.temporal_note||source.interpretation||source.methodology_note||source.note||'Период и единица сохранены по исходной публикации.','small'),link('ЕМИСС '+sourceId(source),source.source_url||'https://www.fedstat.ru/indicator/'+sourceId(source)));}

function overview(ctx){
 const root=start(ctx),c=stat(ctx).coverage;
 add(root,stats([['Коды каталога',fmt(c.registry_indicators??10,0),'14 карточек паспортов относятся к 11 различным показателям'],['Числовые источники',fmt(c.numeric_sources??6,0),'Публикации сохраняют собственные определения'],['Исходные наблюдения',fmt(c.observations??1924,0),'Срез '+date(stat(ctx).statistical_as_of)],['Территории',fmt(c.regions??85,0),'Один региональный показатель поездок']]));
 add(root,panel('От поездки к результату','Основные вопросы экспертизы',cards([
  {title:'Наблюдаемая динамика',text:'Годовые факты, накопленные значения и пересмотренные оценки сопоставляются в пределах одной версии и определения.',path:route('targets')},
  {title:'Работа туристических объектов',text:'Реестровая ёмкость, физический ввод, открытые номеро-сутки и коммерческая загрузка измеряют разные стадии.',path:route('structure')},
  {title:'Ресурсы и их использование',text:'Консолидация требует исключения межбюджетных трансфертов и согласования паспортов с бюджетными документами.',path:route('finance')},
  {title:'Доступность отдыха',text:'Участие жителей в отдыхе, стоимость поездки и возможность завершить маршрут требуют дополнительных наблюдений.',path:route('population')}
 ])));
 add(root,reportTable(ctx,3,'Наблюдения и цели 2025 года'),note('В авторском отчёте показаны результаты исходного среза и отдельно опубликованные уточнения. Позднейшие сообщения не подменяют сохранённые статистические ряды.'));
 add(root,panel('Разделы исследования','Экспертиза и исследовательские инструменты',h('div',{class:'tourism-directory'},tourismPages.filter(p=>p.id!=='overview').map(p=>link(p.title,route(p.id),'tourism-directory-link')))));
 return end(ctx,root);
}
function framework(ctx){return end(ctx,add(start(ctx),panel('Предмет оценки','От ресурса к общественному результату',cards([
 {title:'Условия реализации',text:'Земля, сети, транспорт, финансирование и кадры определяют возможность ввода и работы туристического объекта.'},
 {title:'Фактическое использование',text:'Ночёвки, дни работы, загрузка и расходы посетителей связывают созданную мощность с использованием.'},
 {title:'Дополнительный результат',text:'Занятость, доходы, доступность отдыха и воздействие на среду требуют оценки изменения по отношению к обоснованному сравнению.'}
 ])),reportTable(ctx,1),panel('Границы измерения',null,para('Поездки и размещения могут учитывать повторные события. Доля туристской отрасли, число номеров, экспорт услуг и удовлетворённость имеют разные совокупности и знаменатели. Их рост не сводится к единой шкале результативности.'))));}
const FEDERAL=[
 ['П1','Создание номерного фонда, инфраструктуры и новых точек притяжения','Ввод, подключение, начало работы и использование созданной мощности.'],
 ['П2','Пять морей и озеро Байкал','Согласование инженерной инфраструктуры, финансирования и сроков открытия курортов.'],
 ['П3','Туристическая привлекательность страны','Дополнительный спрос, ценовая доступность и изменения статистического охвата.'],
 ['П4','Кадры для туризма','Применение полученных навыков и результаты работы туристических предприятий.'],
 ['П5','Производство отечественной продукции для туристской индустрии','Дополнительные поставки, качество и полная стоимость обслуживания оборудования.']
];
function logic(ctx){return end(ctx,add(start(ctx),cards(FEDERAL.map(([id,title,body])=>({title:id+'. '+title,text:body,path:route('domains',{domain:id})}))),reportTable(ctx,2),reportTable(ctx,12,'Документальная структура проекта')));}
function audit(ctx){
 const root=start(ctx),registry=array(stat(ctx).registry).length?stat(ctx).registry:ctx.indicators;
 add(root,stats([['Карточки паспортов','14','В национальном и федеральных паспортах'],['Различные показатели','11','Три национальных показателя повторяются'],['Коды каталога','10','Подготовленные специалисты выделены отдельно']]));
 add(root,reportTable(ctx,16,'Показатели и условия их интерпретации'));
 add(root,panel('Статистические источники','Определения и единицы каждой публикации',numericTable(sources(ctx).map(s=>({id:sourceId(s),title:sourceName(s),unit:s.unit,n:s.observations_count??s.observation_count??array(s.observations).length,status:'Сохранённая числовая публикация',url:s.source_url||'https://www.fedstat.ru/indicator/'+sourceId(s)})),[{key:'id',label:'ЕМИСС',render:(v,r)=>link(v,r.url)},{key:'title',label:'Показатель'},{key:'unit',label:'Единица'},{key:'n',label:'Наблюдения',numeric:true,decimals:0},{key:'status',label:'Статус'}],'source-audit')));
 add(root,note('Источник 62902 измеряет экспорт в долларах США. Источник 63347 измеряет число иностранных граждан, размещённых в коллективных средствах размещения. Совпадающая ссылка в каталоге не делает эти величины взаимозаменяемыми.'));
 return end(ctx,root);
}
async function targets(ctx){
 const root=start(ctx),s=selectedSource(ctx);if(!s)return end(ctx,root);
 const all=await observations(s),nat=all.filter(national),categories=[...new Set(nat.map(categoryKey))],cat=categories.includes(ctx.state.category)?ctx.state.category:categories[0],rows=nat.filter(r=>categoryKey(r)===cat).sort((a,b)=>String(a.period_end).localeCompare(String(b.period_end)));
 add(root,toolbar(sourcePicker(ctx,s),categories.length>1?select('Категория',categories.map(c=>[c,Object.values(JSON.parse(c)).join(' · ')||'Все категории']),cat,v=>ctx.set({category:v})):null),sourceNote(s));
 const points=group=>group.map(r=>({x:Date.parse(r.period_end||String(r.year)+'-12-31'),y:value(r),label:period(r)}));
 const cumulative=rows.some(r=>['cumulative_flow','quarterly_cumulative','quarterly_cumulative_publication'].includes(r.period_semantics)||(!r.period_semantics&&['cumulative_ytd','quarterly_cumulative'].includes(r.frequency)));
 const years=[...new Set(rows.map(r=>r.year))];
 const series=cumulative?years.map((year,i)=>({name:sourceName(s)+' · '+year+', с начала года',points:points(rows.filter(r=>r.year===year)),color:C[i%C.length]})):sourceId(s)==='62159'?[{name:'Публикации до 2026 года',points:points(rows.filter(r=>r.year<2026)),color:C[2]},{name:'Публикации с 2026 года',points:points(rows.filter(r=>r.year>=2026)),color:C[0]}]:[{name:sourceName(s),points:points(rows),color:C[0]}];
 add(root,panel('Опубликованные значения',cumulative?'Нарастающим итогом с начала года · '+s.unit:sourceId(s)==='62903'?'История публикаций годовой оценки · '+s.unit:s.unit,h('div',{},chart(ctx,lineChart(series,{label:sourceName(s),unit:s.unit,monthlyTicks:true}),'national-'+sourceId(s),sourceName(s),rows.map(r=>({period:period(r),value:r.value,unit:s.unit}))),series.length>1?legend(series):null)));
 if(cumulative)add(root,note('Линии разных лет показаны раздельно. Переход от декабря к январю связан с началом нового периода накопления и не интерпретируется как снижение месячного потока.'));
 if(sourceId(s)==='62903')add(root,note('Месячные колонки содержат публикации или повторения годовой оценки. Точки не представляют независимые измерения месячной доли туристской отрасли.'));
 if(sourceId(s)==='62159')add(root,note(h('div',{},para('Методика по приказу Минэкономразвития России от 09.02.2026 № 87 распространяется на правоотношения с 1 января 2026 года. Показатель отражает реестровый запас на конец месяца и включает комнаты классифицированных гостевых домов. Сопоставимость с более ранними значениями требует проверки редакций и состава реестра. Разделение линий обозначает границу применения методики, величина статистического разрыва не установлена.'),references(ctx,['fn_032','fn_064']))));
 const comps=array(ana(ctx).target_comparisons||stat(ctx).target_comparisons).filter(r=>String(r.source_id)===sourceId(s));
 if(comps.length)add(root,panel('Сопоставление с паспортной целью','Статус сравнения определён для каждой пары',numericTable(comps.map(r=>({year:r.target_year||r.year,fact:r.fact_value??r.value,target:r.target_value??r.target,difference:r.difference,unit:r.difference_unit||(['62903','62780'].includes(sourceId(s))?'п.п.':r.unit||s.unit),status:[r.status_label||'',r.note||r.caveat||''].filter(Boolean).join('. ')||r.status||'',formal:r.formal_attainment_eligible===true?'Подтверждено условиями сравнения':'Условное сопоставление'})),[{key:'year',label:'Год'},{key:'fact',label:'Наблюдение',numeric:true,decimals:5},{key:'target',label:'Цель',numeric:true,decimals:5},{key:'difference',label:'Разность',numeric:true,decimals:5},{key:'unit',label:'Единица разности'},{key:'status',label:'Основание'},{key:'formal',label:'Статус'}],'target-comparison')));
 add(root,panel('Исходные наблюдения',null,pointsTable(rows,s)),reportTable(ctx,4),reportTable(ctx,5,'Несовпадения статистических публикаций'));
 return end(ctx,root);
}
async function territorial(ctx,profiles=false){
 const root=start(ctx),s=selectedSource(ctx,true);if(!s)return end(ctx,add(root,note('В сохранённом наборе отсутствуют региональные публикации.')));
 const raw=await observations(s),all=raw.filter(r=>r.geo_level==='regional'&&r.geographic_comparison_eligible!==false&&regionId(r)&&finite(r.value)),periods=[...new Set(all.map(r=>r.period_end))].filter(Boolean).sort(),selected=periods.includes(ctx.state.period)?ctx.state.period:(periods.find(p=>p==='2025-12-31')||periods.at(-1));
 const categories=[...new Set(all.filter(r=>r.period_end===selected).map(categoryKey))],cat=categories.includes(ctx.state.category)?ctx.state.category:categories[0];
 const rows=all.filter(r=>r.period_end===selected&&categoryKey(r)===cat),usable=rows.filter(r=>value(r)!==null),sum=usable.reduce((s,r)=>s+value(r),0),sorted=[...usable].sort((a,b)=>value(b)-value(a));
 add(root,toolbar(sourcePicker(ctx,s,true),select('Период',periods.map(p=>[p,p.slice(0,7)]),selected,v=>ctx.set({period:v,region:''})),profiles?null:select('Представление карты',[['map','Картограмма'],['tiles','Плиточная карта']],ctx.state.view||'map',v=>ctx.set({view:v})),categories.length>1?select('Категория',categories.map(c=>[c,Object.values(JSON.parse(c)).join(' · ')||'Все категории']),cat,v=>ctx.set({category:v})):null));
 add(root,stats([['Наблюдаемые территории',fmt(usable.length,0),'Сопоставимый срез'],['Сумма по территориям',fmt(sum,4),s.unit],['Доля первых 10 территорий',sum>0?fmt(sorted.slice(0,10).reduce((s,r)=>s+value(r),0)/sum*100,2)+'%':'Не рассчитывается','В сумме наблюдаемого среза']]));
 const country=raw.find(r=>national(r)&&r.period_end===selected&&categoryKey(r)===cat),nationalValue=value(country);
 if(nationalValue!==null&&Math.abs(sum-nationalValue)>1e-6)add(root,note('Сумма наблюдаемых территорий '+fmt(sum,5)+' '+s.unit+' отличается от опубликованного итога РФ '+fmt(nationalValue,5)+' '+s.unit+'. Разность '+fmt(sum-nationalValue,5)+' '+s.unit+' сохранена. Доли территорий рассчитаны от их собственной суммы.'));
 add(root,note('Региональные значения описывают территорию поездки. Число поездок не является числом уникальных жителей, участвовавших в отдыхе. Один доступный региональный признак не даёт основания для PCA, многомерной кластеризации или Isolation Forest.'));
 if(!profiles&&ctx.geo){
  const regs=ctx.catalog.regions,values=new Map(rows.map(r=>[regionId(r),{value:value(r),detail:period(r)+' · '+s.unit,flag:r.excluded}]));
  const map=mapView(ctx.geo,regs,values,{unit:s.unit,tile:ctx.state.view==='tiles',selected:ctx.state.region||null,title:'Туристические поездки · '+selected,onSelect:id=>ctx.set({region:id})});
  add(root,panel('Туристические поездки по территориям',selected.slice(0,7),h('div',{},figureControls(map.svg,{name:'tourism-map-'+selected,title:'Туристические поездки · '+selected,source:'ЕМИСС '+sourceId(s)+'; единица: '+s.unit+'; срез '+stat(ctx).statistical_as_of,rows:rows.map(r=>({territory:rowName(r),code:regionId(r),value:r.value,period:period(r),unit:s.unit}))}),map.element)));
 }
 const selectedRow=rows.find(r=>regionId(r)===ctx.state.region)||sorted[0];
 if(selectedRow){
  add(root,panel('Профиль территории',null,h('div',{},select('Территория',rows.map(r=>[regionId(r),rowName(r)]).sort((a,b)=>a[1].localeCompare(b[1],'ru')),regionId(selectedRow),v=>ctx.set({region:v})),stats([['Территория',rowName(selectedRow),''],['Поездки',fmt(value(selectedRow),5),s.unit],['Доля в наблюдаемом срезе',sum>0?fmt(value(selectedRow)/sum*100,3)+'%':'Не рассчитывается','Период '+selected.slice(0,7)] ]),link('Наблюдения территории',route('explorer',{source:sourceId(s),region:regionId(selectedRow)})))));
 }
 add(root,panel('Распределение поездок','Первые 15 территорий по объёму в выбранном срезе',chart(ctx,bars(sorted.slice(0,15).map(r=>({name:rowName(r),value:value(r)})),{unit:s.unit,label:'Распределение поездок'}),'regions-'+selected,'Распределение туристических поездок',rows)));
 add(root,panel('Все территории выбранного среза',null,pointsTable(rows,s)),sourceNote(s),profiles?reportTable(ctx,6,'Федеральные округа в авторской экспертизе'):null);
 return end(ctx,root);
}

function finance(ctx){
 const root=start(ctx),f=doc(ctx).finance,mode=ctx.state.finance||'passport';
 add(root,toolbar(select('Финансовый раздел',[['passport','Паспорта 2025–2030'],['consolidation','Исключение трансфертов'],['budget','Бюджетная роспись и проект'],['cost','Стоимость результатов']],mode,v=>ctx.set({finance:v}))));
 if(mode==='passport'){
  add(root,note(f.caveat||f.totalMeaning||'Арифметическая сумма финансовых строк включает повторный учёт межбюджетных трансфертов. Она не определяет консолидированный бюджет проекта.'));
  add(root,reportTable(ctx,8),reportTable(ctx,9));
  const rows=array(f.projects).map(r=>{const total=number(r.totalThousandRub??r.total_thousand_rub??r.total);return{name:({П1:'П1. Номерной фонд',П2:'П2. Морские курорты',П3:'П3. Привлекательность',П4:'П4. Кадры',П5:'П5. Отечественная продукция'})[r.code||r.fp]||r.title||r.name||r.federal_project_name||r.project_name||r.id,value:total===null?null:total/1e6};}).filter(r=>finite(r.value));
  if(rows.length)add(root,panel('Распределение раскрытых финансовых строк','Арифметическая структура в пределах горизонта 2025–2030',chart(ctx,bars(rows,{unit:'млрд руб.',label:'Арифметические финансовые строки'}),'finance','Раскрытые финансовые строки',rows,'Источник: паспорта федеральных проектов. Строки до исключения повторных трансфертов.')));
 }else if(mode==='consolidation'){
  add(root,reportTable(ctx,7,'Согласование уровней финансового учёта'),panel('Проверка консолидации','Пример из ранней редакции национального паспорта',h('div',{},h('div',{class:'formula'},'444,8534541 + 174,2519172 − 169,7702371 = 449,3351342 млрд руб.'),para('Федеральные и региональные бюджетные строки суммируются после исключения межбюджетного оборота. С учётом внебюджетных источников 162,8571426 млрд руб. итог этой редакции составляет 612,1922768 млрд руб.'),para('Результат относится к ранней редакции национального паспорта. Перенос этой поправки на более поздние федеральные планы требует их собственной сверки.'))));
 }else if(mode==='budget')add(root,reportTable(ctx,10),note('Показатели 2026 года относятся к бюджетной росписи на 1 сентября. Значения 2027–2029 годов в экспертизе относятся к проекту бюджета. Их статус сохраняется по дате исходного документа.'));
 else add(root,reportTable(ctx,11),panel('Удельные затраты',null,h('div',{},para('Отношение бюджетной строки к числу слушателей или единиц продукции характеризует среднее распределение ресурса при заданном составе. Экономическая отдача требует отдельной оценки результата.'),link('Калькулятор удельных затрат',route('lab',{calculator:'cost'})))));
 return end(ctx,root);
}
const pairResult=r=>String(r.result_id||r.result_node_id||r.source_node_id||r.source_id||r.from||r.source||r.result||''),pairIndicator=r=>String(r.indicator_id||r.indicator_node_id||r.target_node_id||r.target_id||r.to||r.target||r.indicator||'');
function network(ctx){
 const root=start(ctx),n=doc(ctx).network,kind=ctx.state.evidence||'structural',nodes=array(n.nodes),nodeName=id=>nodes.find(n=>String(n.id)===String(id))?.title||nodes.find(n=>String(n.id)===String(id))?.label||id;
 const pairs=kind==='lexical'?array(n.lexicalPairs||n.semanticCandidates):kind==='ambiguous'?array(n.ambiguousClaims||n.unresolvedClaims):array(n.structuralPairs||n.sharedTaskPairs);
 add(root,stats([['Результаты','31','Карточки паспортов'],['Общая задача','49 пар','Структурная принадлежность'],['Неоднозначные записи','73','Адресаты прямого влияния не установлены'],['Лексические кандидаты','20 пар','Порог 0,10, 13 результатов']]));
 add(root,toolbar(select('Основание связи',[['structural','Принадлежность общей задаче'],['lexical','Лексическое сходство'],['ambiguous','Неоднозначные записи влияния']],kind,v=>ctx.set({evidence:v}))));
 const rows=pairs.map(r=>({from:r.result_title||r.source_title||r.result_name||nodeName(pairResult(r)),to:r.indicator_title||r.target_title||r.indicator_name||nodeName(pairIndicator(r))||(kind==='ambiguous'?'Адресат не установлен':''),task:r.task_title||r.task_id||r.claim_text||r.text||r.raw_target||(kind==='ambiguous'?'Опубликованная запись: '+(r.value_raw??'не задана')+'. Адресат требует проверки.':''),score:r.cosine??r.similarity??r.weight??r.score,source:r.document_url||r.source_url||r.url||''}));
 add(root,panel(kind==='ambiguous'?'Записи с неустановленными адресатами':'Пары результатов и показателей',kind==='lexical'?'Косинусная близость формулировок':'Связи документального корпуса',numericTable(rows,[{key:'from',label:'Результат / исходная запись'},{key:'to',label:'Показатель / адресат'},{key:'task',label:kind==='ambiguous'?'Исходная запись':'Задача и основание'},...(kind==='lexical'?[{key:'score',label:'Косинус',numeric:true,decimals:4}]:[]),{key:'source',label:'Документ',render:v=>v?link('Источник',v):'Паспортный корпус'}],'network-'+kind)));
 if(kind!=='ambiguous'&&pairs.length){
  const resultIds=[...new Set(pairs.map(pairResult))].filter(Boolean),indicatorIds=[...new Set(pairs.map(pairIndicator))].filter(Boolean);
  const labels=ids=>ids.map(id=>{const name=nodeName(id);return String(name).length>44?String(name).slice(0,41)+'…':name;});
  const columnLabels=indicatorIds.map((id,i)=>nodes.find(n=>String(n.id)===id)?.code||'И'+(i+1));
  if(resultIds.length&&indicatorIds.length)add(root,panel('Матрица документальных связей',kind==='lexical'?'Косинусное сходство, без причинной интерпретации':'1 – результат и показатель связаны общей задачей',h('div',{},chart(ctx,heatmap(labels(resultIds),columnLabels,resultIds.map(r=>indicatorIds.map(i=>{const p=pairs.find(p=>pairResult(p)===r&&pairIndicator(p)===i);return p?(kind==='lexical'?number(p.cosine??p.similarity??p.weight??p.score):1):null;})),{label:'Матрица связей',cellHeight:36,left:300,format:v=>v===null?'':fmt(v,kind==='lexical'?2:0)}),'network-'+kind,'Матрица связей',rows,'Источник: паспорта проекта. Классы документальных связей учитываются раздельно.'),h('details',{class:'tourism-matrix-key'},h('summary',{},'Обозначения показателей в матрице'),indicatorIds.map((id,i)=>para(columnLabels[i]+' — '+nodeName(id),'small'))))));
 }
 add(root,note(kind==='lexical'?'Косинусная близость помогает выбрать формулировки для содержательной проверки. Порог 0,10 не является уровнем статистической значимости.':kind==='ambiguous'?'Неоднозначные записи сохраняются для проверки. Их адресатам и силе влияния не присваиваются значения.':'Принадлежность общей задаче описывает структуру паспорта. Она не устанавливает величину или направление причинного эффекта.'),reportTable(ctx,12),kind==='lexical'?reportTable(ctx,13):null);
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
 const root=start(ctx),t=doc(ctx).text,documents=array(t.documents),similarity=array(t.similarity||t.projectSimilarity||t.project_similarity),profile=ctx.state.document||'project',terms=array(t.terms||t.topTerms).filter(r=>r.document_id===profile),q=ctx.state.query||'';
 const selectedDocuments=documents.filter(d=>profile==='project'||d.id===profile);
 const packets=await Promise.all(selectedDocuments.map(d=>t.documentFiles?.[d.id]?textPacket(t.documentFiles[d.id]):Promise.resolve({document:d,units:[]})));
 const searchUnits=packets.flatMap(p=>array(p.units).map(u=>({...u,documentTitle:p.document.title||p.document.id,sourceURL:u.source_url||p.source_url||p.document.url})));
 const input=h('input',{type:'search',value:q,placeholder:'Например: доступность, номера, кадры','aria-label':'Поиск по документам'});
 const found=h('div',{class:'tourism-text-results'});
 const draw=()=>{const query=input.value.trim().toLocaleLowerCase('ru');const matches=searchUnits.filter(b=>b.text&&(!query||b.text.toLocaleLowerCase('ru').includes(query)));found.replaceChildren(h('p',{class:'small muted'},'Фрагментов: '+matches.length+(matches.length>30?' · показаны первые 30, уточните запрос':'')),...matches.slice(0,30).map(b=>h('article',{class:'tourism-text-fragment'},h('p',{class:'small muted'},b.documentTitle),para(b.text),link('Паспортный источник',b.sourceURL))));};input.addEventListener('input',draw);input.addEventListener('keydown',e=>{if(e.key==='Enter')ctx.set({query:input.value});});draw();
 add(root,toolbar(select('Текстовый профиль',[['project','Все шесть паспортов'],...documents.map(d=>[d.id,d.title||d.id])],profile,v=>ctx.set({document:v}))),panel('Поиск по формулировкам паспортов','Цели, задачи, результаты и показатели в нормализованном текстовом профиле. Полные документы доступны по ссылкам.',h('div',{},toolbar(input,button('Найти',()=>ctx.set({query:input.value}),'button')),found)));
 if(similarity.length)add(root,panel('Близость текстовых профилей','Одинаковые правила обработки документального корпуса',numericTable(similarity.map(r=>({project:r.project_name||r.project||r.target_project||r.name||'',score:r.cosine??r.similarity??r.value,kind:r.kind||r.method||''})),[{key:'project',label:'Проект'},{key:'score',label:'Косинус',numeric:true,decimals:5},{key:'kind',label:'Спецификация'}],'text-similarity')));
 if(terms.length)add(root,panel('Термины выбранного профиля','Вес TF–IDF',numericTable(terms.map(r=>({term:r.term||r.token||r.word,value:r.tfidf??r.weight??r.count??r.value,kind:r.document_id==='project'?'Весь проект':documents.find(d=>d.id===r.document_id)?.title||r.document_id||''})),[{key:'term',label:'Термин'},{key:'value',label:'Вес TF–IDF',numeric:true,decimals:5},{key:'kind',label:'Документ / профиль'}],'text-terms')));
 if(documents.length)add(root,panel('Документы корпуса',null,numericTable(documents.map(d=>({title:d.title||d.name||d.document_title||d.id,kind:({np:'Национальный паспорт',fp:'Федеральный паспорт'})[d.kind]||d.kind||'',url:d.url||d.source_url||d.text_url||'',tokens:d.tokens||d.token_count||d.n_tokens})),[{key:'title',label:'Документ'},{key:'kind',label:'Тип'},{key:'tokens',label:'Токены',numeric:true,decimals:0},{key:'url',label:'Источник',render:v=>link('Открыть',v)}],'text-documents')));
 if(array(t.sensitivity).length)add(root,panel('Чувствительность текстового сравнения','Сопоставление рангов девяти других проектов с базовой спецификацией',numericTable(t.sensitivity.map(r=>({variant:({base:'Исходная спецификация',stemmed:'Стемминг русских слов',unigram:'Униграммы',unigrams:'Униграммы',equal_levels:'Равные веса уровней',federal_only:'Только федеральные паспорта',national_only:'Только национальные паспорта'})[r.variant]||r.variant,rho:r.spearman,nearest:array(r.top3).join(' · ')})),[{key:'variant',label:'Спецификация'},{key:'rho',label:'Корреляция Спирмена',numeric:true,decimals:4},{key:'nearest',label:'Три ближайших проекта'}],'text-sensitivity')));
 add(root,reportTable(ctx,13),note('Частоты слов и близость формулировок описывают документы. Они не измеряют удовлетворённость путешественников, экономическую отдачу или эффективность проекта.'));
 return end(ctx,root);
}
function domains(ctx){
 const root=start(ctx),selected=FEDERAL.find(p=>p[0]===ctx.state.domain)||FEDERAL[0];
 const definition=array(exp(ctx).derived?.federalProjects).find(p=>p.code===selected[0]);
 const sourceBlocks=Object.values(exp(ctx).pages).flatMap(p=>array(p.blocks)).filter(b=>array(definition?.mechanismBlocks).includes(b.sourceBlock||b.id));
 add(root,toolbar(select('Федеральное направление',FEDERAL.map(([id,title])=>[id,title]),selected[0],v=>ctx.set({domain:v}))),panel(selected[1],null,h('div',{},para(selected[2]),definition?para(definition.mechanism):null,definition?para('Проверяемый переход: '+definition.transition):null,...sourceBlocks.map(b=>reportBlock(ctx,b)),definition?link('Паспорт федерального проекта',definition.source_url):null,h('p',{}),link('Проверить финансовые основания',route('finance')),h('span',{},' · '),link('Проверить связи мер и показателей',route('network')))),reportTable(ctx,2),reportTable(ctx,11));
 return end(ctx,root);
}
function proposals(ctx){return end(ctx,add(start(ctx),reportTable(ctx,14,'Предлагаемые измерения результатов'),reportTable(ctx,15,'Последовательность изменений'),panel('Проверка результата изменений',null,para('Каждое изменение системы мониторинга связывается с конкретной совокупностью, источником, периодом и ответственным за наблюдение. Решение о продолжении или расширении поддержки требует сопоставления дополнительного эффекта с полной стоимостью.'))));}

export function ratioPercent(numerator,denominator){return Number.isFinite(numerator)&&Number.isFinite(denominator)&&numerator>=0&&denominator>0?100*numerator/denominator:null;}
export function differenceInDifferences(t0,t1,c0,c1){return[t0,t1,c0,c1].every(Number.isFinite)?(t1-t0)-(c1-c0):null;}
export function requiredAnnualChange(base,target,years){return Number.isFinite(base)&&Number.isFinite(target)&&base>0&&target>=0&&years>0?100*(Math.pow(target/base,1/years)-1):null;}
function calculator(kind){
 const specs={
  occupancy:{title:'Коммерческая загрузка',description:'Проданные номеро-сутки / открытые номеро-сутки × 100%. Одинаковый период и состав объектов.',fields:[['sold','Проданные номеро-сутки',0],['open','Открытые номеро-сутки',0]],compute:v=>v.sold<=v.open?ratioPercent(v.sold,v.open):null,unit:'%',invalid:'Укажите положительное число открытых номеро-суток и объём продаж не выше доступной мощности.'},
  seasonality:{title:'Сезонная концентрация',description:'Ночёвки трёх наиболее посещаемых месяцев / годовые ночёвки × 100%. При полном годе из 12 месяцев допустимый результат составляет от 25 до 100%.',fields:[['peak','Ночёвки за три ведущих месяца',0],['annual','Ночёвки за год',0]],compute:v=>v.peak<=v.annual&&v.peak>=v.annual/4?ratioPercent(v.peak,v.annual):null,unit:'%',invalid:'Проверьте полный год и три наиболее посещаемых месяца: их доля должна составлять от 25 до 100% при положительном годовом объёме.'},
  affordability:{title:'Ценовая доступность',description:'Стоимость стандартной поездки / располагаемый доход домохозяйства за выбранный период × 100%. Зафиксируйте состав поездки, сезон и период дохода.',fields:[['price','Стоимость поездки, руб.',0],['income','Доход за выбранный период, руб.',0]],compute:v=>ratioPercent(v.price,v.income),unit:'% дохода',invalid:'Введите стоимость поездки и положительный располагаемый доход.'},
  cost:{title:'Удельные затраты',description:'Полная сумма затрат / количественный результат. Согласуйте получателей, период и состав объектов.',fields:[['cost','Затраты, млн руб.',0],['count','Количество результатов, ед.',0]],compute:v=>v.cost>=0&&v.count>0?v.cost*1000/v.count:null,unit:'тыс. руб. на единицу',invalid:'Введите неотрицательные затраты и положительное число результатов.'},
  did:{title:'Разность изменений',description:'(Результат участников после − до) − (результат группы сравнения после − до). Арифметический расчёт требует независимого обоснования причинного дизайна.',fields:[['t0','Участники: до',0],['t1','Участники: после',0],['c0','Сравнение: до',0],['c1','Сравнение: после',0]],compute:v=>differenceInDifferences(v.t0,v.t1,v.c0,v.c1),unit:'единиц показателя',invalid:'Введите четыре сопоставимых значения.'}
 };
 const spec=specs[kind]||specs.occupancy,inputs={},out=h('div',{class:'tourism-calculation-output',role:'status','aria-live':'polite'});
 const fields=spec.fields.map(([key,label,initial])=>{const inp=h('input',{type:'number',step:'any',value:initial,'aria-label':label,...(kind==='did'?{}:{min:0})});inputs[key]=inp;return h('label',{class:'field'},h('span',{},label),inp);});
 function calculate(){const vals=Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,number(v.value)]));const result=Object.values(vals).every(v=>v!==null)?spec.compute(vals):null;out.replaceChildren(finite(result)?h('div',{},h('strong',{},fmt(result,4)+' '+spec.unit),para('Расчёт по введённым значениям.','small')):para(spec.invalid));}
 Object.values(inputs).forEach(inp=>inp.addEventListener('input',calculate));calculate();
 return panel(spec.title,'Условный расчёт по параметрам пользователя',h('div',{class:'tourism-calculator',dataset:{calculator:kind}},para(spec.description),h('div',{class:'tourism-input-grid'},fields),out,note('Введённые значения используются только для расчёта в браузере. Результат не является наблюдением статистики или установленным эффектом государственной поддержки.')));
}
function causal(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Определить воздействие',text:'Зафиксировать инструмент поддержки, объект, получателя и фактическую дату начала воздействия.'},
 {title:'Подготовить сопоставление',text:'Собрать предысторию, учесть отбор получателей и обосновать группу сравнения.'},
 {title:'Проверить предпосылки',text:'Оценить различия в предшествующей динамике, побочные воздействия и изменение состава наблюдений.'}
 ]),calculator('did'),note('Имеющиеся агрегированные источники не идентифицируют причинный эффект проекта. Число поездок и объём финансирования сами по себе не определяют дополнительность государственной поддержки.')));}
function population(ctx){return end(ctx,add(start(ctx),cards(array(exp(ctx).derived?.populationGroups).map(g=>({title:g.name,text:g.description||g.need}))),reportTable(ctx,14,'Социальная доступность и местные результаты'),calculator('affordability'),panel('Наблюдение участия населения',null,para('Опросы должны учитывать жителей без туристических поездок, повторные поездки, цель отдыха, доходную группу, возраст и состав домохозяйства. Индекс удовлетворённости путешественников не описывает барьеры людей, которые не смогли поехать.'))));}
function structure(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Номер в реестре',text:'Классификация устанавливает учтённую ёмкость. Изменение охвата реестра может увеличить показатель без строительного ввода.'},
 {title:'Открытая мощность',text:'Открытые номеро-сутки учитывают фактические дни работы, сезонность и доступность номеров.'},
 {title:'Коммерческое использование',text:'Проданные номеро-сутки и расходы посетителей описывают использование мощности.'},
 {title:'Результат для территории',text:'Занятость, доходы, местные закупки, нагрузка на сети и среду требуют отдельных наблюдений.'}
 ]),calculator('occupancy'),reportTable(ctx,14)));}
function lab(ctx){const kind=ctx.state.calculator||'occupancy';return end(ctx,add(start(ctx),toolbar(select('Расчёт',[['occupancy','Коммерческая загрузка'],['seasonality','Сезонная концентрация'],['affordability','Ценовая доступность'],['cost','Удельные затраты'],['did','Разность изменений']],kind,v=>ctx.set({calculator:v}))),calculator(kind),panel('Условия применения',null,para('Числитель и знаменатель относятся к одинаковому периоду и совокупности. При нулевом или неизвестном знаменателе отношение не рассчитывается. Разные типы оборудования, услуг и объектов требуют раздельного учёта.'))));}

function targetSeries(t){
 const raw=t.years||t.targets||t.annual_targets||t.values||t.series||[];
 if(Array.isArray(raw))return raw.map(r=>({year:Number(r.year||String(r.period||'').slice(0,4)),value:number(r.value??r.target??r.target_value)})).filter(r=>r.year>=2025&&r.year<=2030);
 return Object.entries(raw).map(([year,v])=>({year:Number(year),value:number(v!==null&&typeof v==='object'?v.value??v.target:v)})).filter(r=>r.year>=2025&&r.year<=2030);
}
function projections(ctx){
 const root=start(ctx),targets=array(doc(ctx).targets?.items||ana(ctx).targets),selected=targets.find(t=>String(code(t))===ctx.state.target)||targets.find(t=>targetSeries(t).length)||targets[0];
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
 add(root,reportTable(ctx,4),panel('Допустимость прогноза',null,methodsTable(array(ana(ctx).forecast_eligibility).map(r=>({name:r.title||r.source_id,status:r.eligible?'Пригодность требует проверки модели':'Недостаточно оснований',reason:r.reason||r.note||'Краткая история, накопленные итоги и пересмотры ограничивают прогноз.'})))));
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
 add(root,panel('Авторская экспертиза',date(meta.edition_date),h('div',{class:'tourism-download-grid'},link('Полный отчёт Word',report(ctx)),link('Читаемый отчёт HTML',meta.html_url||BASE+'report/expertise_tourism_2026.html'),link('Полный текст Markdown',meta.markdown_url),link('Структурированное извлечение',meta.extract_url),link('Проверка полноты',meta.coverage_url))));
 add(root,stats([['Таблицы',fmt(array(exp(ctx).tables).length,0),'Исходные таблицы и CSV'],['Иллюстрации',fmt(array(exp(ctx).figures).length,0),'Файлы из авторского отчёта'],['Сноски',fmt(meta.footnotes??130,0),'Полные ссылки и исходные номера']]));
 const docs=array(doc(ctx).sources).map(r=>({title:r.title||r.document_title||r.id,kind:r.kind||r.format||'',date:r.retrieved_at||r.date||'',url:r.url||r.source_url,local:r.local_url||r.download_url||r.text_url}));
 if(docs.length)add(root,panel('Паспортные источники',null,numericTable(docs,[{key:'title',label:'Документ'},{key:'kind',label:'Тип'},{key:'date',label:'Дата получения',render:date},{key:'url',label:'Публикация',render:v=>link('Источник',v)},{key:'local',label:'Сохранённый файл',render:v=>v?link('Открыть',v):'В исходном корпусе'}],'document-sources')));
 add(root,panel('Статистика и расчёты',null,h('div',{class:'tourism-download-grid'},['statistics','analytics','documentary','refresh-status','expertise'].map(name=>link(({statistics:'Статистические публикации',analytics:'Расчёты по наблюдениям',documentary:'Документальная аналитика','refresh-status':'Состояние обновления',expertise:'Структура полной экспертизы'})[name],'data/projects/tourism/'+name+'.json')),downloads(stat(ctx).downloads),downloads(doc(ctx).downloads))));
 add(root,panel('Исходные таблицы',null,h('div',{class:'tourism-download-grid'},array(exp(ctx).tables).map(t=>link(t.title,t.csv_url||t.download_url||BASE+'report/'+t.id+'.csv')))),panel('Иллюстрации',null,h('div',{class:'tourism-download-grid'},array(exp(ctx).figures).map(f=>link(f.title,f.url)))));
 add(root,panel('Повторить сборку',null,h('div',{},para('Исходные файлы и процедуры входят в накопительный комплект. Сборка использует сохранённые данные. Обращение к ЕМИСС выполняется отдельной командой.'),h('pre',{},h('code',{},'npm run build\nnpm run validate\nnpm run analytics:tourism\nnpm run refresh:tourism')),link('Код платформы','downloads/code/platform/build_tourism_analytics.py'))));
 return end(ctx,root);
}
function updates(ctx){
 const root=start(ctx),r=data(ctx).refresh,status={imported_verified_snapshot:'Импортирован проверенный срез',verified_source_snapshot:'Проверенный исходный срез',retained_verified_snapshot:'Сохранён проверенный срез',imported:'Импортирован проверенный срез',not_checked:'Новая проверка не выполнялась',not_attempted:'Новая проверка не выполнялась',failed:'Запрос не подтвердил обновление',partial:'Частичное обновление',updated:'Опубликованы проверенные данные',success:'Проверка завершена'};
 add(root,stats([['Статистический срез',date(r.statistical_as_of||stat(ctx).statistical_as_of),'Периоды наблюдений указаны в рядах'],['Последняя проверка',date(r.checked_at||r.last_checked_at),'Дата сетевого обращения, если оно выполнялось'],['Состояние',status[r.state]||r.message||r.state||'Сохранённый срез','']]));
 if(r.message)add(root,note(r.message));
 const rows=array(r.sources).map(s=>({id:sourceId(s),title:s.title||sourceName(s),state:status[s.state]||s.state||s.status||'',checked:s.checked_at||'',success:s.last_success||s.published_at||'',detail:s.message||s.error||''}));
 if(rows.length)add(root,panel('Состояние источников',null,numericTable(rows,[{key:'id',label:'ЕМИСС'},{key:'title',label:'Показатель'},{key:'state',label:'Состояние'},{key:'checked',label:'Последняя проверка',render:date},{key:'success',label:'Последние проверенные данные',render:date},{key:'detail',label:'Примечание'}],'refresh-status')));
 add(root,panel('Правила обновления',null,h('div',{},para('При неуспешном запросе сохраняются последние проверенные значения и их происхождение. Новый ответ сначала проходит проверку структуры, единицы и территориального состава. Авторский отчёт сохраняет дату своей редакции.'),link('Проверить наблюдения',route('explorer')),h('span',{},' · '),link('Состояние обновления JSON','data/projects/tourism/refresh-status.json'))));
 return end(ctx,root);
}
function methods(ctx){return end(ctx,add(start(ctx),panel('Пригодность методов','Статус и доказательные основания',methodsTable(ctx.methods)),note('В наличии один региональный признак поездок. Многомерная типология, PCA и Isolation Forest не рассчитываются. Пространственная статистика одного признака, если представлена в исходном исследовании, сохраняет собственную спецификацию и не становится оценкой эффекта проекта.'),reportTable(ctx,1)));}

const renderers={overview,framework,logic,audit,targets,map:ctx=>territorial(ctx,false),regions:ctx=>territorial(ctx,true),finance,network,texts,domains,causal,proposals,projections,population,structure,methods,lab,explorer,library,updates};
export async function renderTourism(ctx){return(renderers[ctx.state.page]||overview)(ctx);}
