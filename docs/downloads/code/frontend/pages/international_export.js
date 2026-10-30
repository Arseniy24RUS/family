import {observationCache, textPacketCache} from '../core/cache.js';
import {h,svg,para,note,button,select,fmt,icon,csvDownload} from '../core/dom.js';
import {heading,panel,toolbar,stats,table,figure,figureControls,empty} from '../components/ui.js';
import {bars,lineChart,legend,heatmap} from '../components/charts.js';
import {C} from '../platform/theme.js';
import {mapView} from '../components/map.js';
import {projectHref,internationalExportPages} from '../platform/projects.js';

const PROJECT='international_export',BASE='downloads/projects/international_export/';
const array=x=>Array.isArray(x)?x:[],text=x=>typeof x==='string'?x:typeof x==='number'?String(x):x?.text||x?.summary||x?.title||'';
const number=x=>x===null||x===undefined||String(x).trim()===''?null:Number.isFinite(Number(String(x).replace(/[\s\u00a0]/g,'').replace(/[−–]/g,'-').replace(',','.')))?Number(String(x).replace(/[\s\u00a0]/g,'').replace(/[−–]/g,'-').replace(',','.')):null;
const finite=x=>number(x)!==null;
const value=r=>r?.excluded?null:Object.hasOwn(r||{},'analytical_value')?number(r.analytical_value):number(r?.value);
const absolute=p=>/^https?:\/\//.test(p||'')?p:'./'+String(p||'').replace(/^\.\//,'');
const link=(label,path,cls='text-link')=>path?h('a',{href:absolute(path),class:cls,...(/^https?:/.test(path)?{target:'_blank',rel:'noopener noreferrer'}:{})},label):h('span',{},label);
const date=d=>/^\d{4}-\d{2}-\d{2}/.test(d||'')?new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow'}).format(new Date(d)):d||'Не установлена';
const data=ctx=>ctx.international_export,exp=ctx=>data(ctx).expertise,stat=ctx=>data(ctx).statistics,ana=ctx=>data(ctx).analytics||{},doc=ctx=>data(ctx).documentary||{};
const sourceId=s=>String(s?.source_id??s?.id??''),sourceName=s=>s?.short_title||s?.title||'Источник '+sourceId(s);
const sources=ctx=>array(stat(ctx).sources),report=ctx=>exp(ctx).meta.download_url||exp(ctx).meta.report_url||BASE+'report/expertise_export_2026.docx';
const pageData=ctx=>exp(ctx).pages[ctx.state.page]||{};
const route=(page,params={})=>projectHref(PROJECT,page,params);
const code=r=>r?.indicator_code||r?.code||r?.id||'';
const rowName=r=>r?.territory_name||r?.name||r?.region_name||r?.territory||'';
const regionId=r=>String(r?.map_id||r?.region_id||r?.code||r?.region_code||r?.territory_code||'').padStart(2,'0');
const national=r=>['national','russia','country'].includes(r.geo_level)||r.is_national===true||/^Российская Федерация/.test(rowName(r));
const categoryKey=r=>JSON.stringify(Object.fromEntries(Object.entries(r.category||{}).sort(([a],[b])=>a.localeCompare(b))));
const period=r=>r?.period||r?.period_end||r?.year||'';
export const observationBasis=r=>['annual','yearly'].includes(r?.source_frequency||r?.frequency)?'annual':['monthly','cumulative_ytd','monthly_stock','annual_repeated_monthly'].includes(r?.source_frequency||r?.frequency)?'monthly':r?.source_frequency||r?.frequency||'unknown';
const basisTitle=key=>({annual:'Годовая запись',monthly:'Месячная публикация',quarterly:'Квартальная публикация',unknown:'Режим не установлен'})[key]||key;
const frequency=r=>basisTitle(observationBasis(r))+(observationBasis(r)!=='annual'&&(['cumulative_ytd','cumulative_flow','cumulative_calendar_year'].includes(r?.frequency)||['cumulative_ytd','cumulative_flow','cumulative_calendar_year'].includes(r?.period_semantics))?' · с начала года':'');

const TITLE={overview:'Международная кооперация и экспорт',...Object.fromEntries(internationalExportPages.filter(p=>p.id!=='overview').map(p=>[p.id,p.title]))};
const LEAD={
 overview:'Экспортные поставки, зарубежная инфраструктура, использование инструментов поддержки и устойчивость хозяйственного результата.',
 framework:'Определения показателей, история поддержки и согласованный финансовый учёт задают основания оценки.',
 logic:'Четыре федеральных направления связывают производство, выход на рынок, инфраструктуру и сопровождение экспортёра.',
 audit:'Годовая запись, накопленное месячное значение и новая редакция методики требуют самостоятельной проверки.',
 targets:'Наблюдения и паспортные цели сопоставляются при одинаковых периодах, денежных единицах и предметных определениях.',
 map:'Экспорт услуг, аграрный экспорт и субсидии раскрывают разные стороны территориального распределения.',
 regions:'Регистрация внешнеторговой операции, место производства и охват предприятий поддержкой имеют самостоятельный смысл.',
 finance:'Суммы паспортов приводятся к общему горизонту с исключением установленного повторного счёта трансфертов.',
 network:'Общая задача, лексический кандидат и подтверждённый хозяйственный переход имеют разные основания.',
 texts:'Профили паспортных результатов и показателей помогают исследовать специализацию направлений и проверить возможные связи.',
 domains:'Промышленный экспорт, зарубежная инфраструктура, системные меры и аграрный экспорт оцениваются по собственным механизмам.',
 causal:'Дополнительность поддержки требует обоснованной оценки результата при отсутствии меры.',
 proposals:'Рекомендации соединяют историю методик, исполнение поставок, повторный экспорт и фактическое использование услуг.',
 projections:'Плановые значения и условные темпы показывают требования к движению от исходной базы к цели.',
 population:'Влияние экспорта на занятость и доходы зависит от места производства, добавленной стоимости и связей с поставщиками.',
 structure:'Товарная, территориальная и клиентская концентрация отражают разные стороны устойчивости экспортной деятельности.',
 methods:'Допустимость анализа определяется сопоставимостью наблюдений, единицами расчёта и полнотой источников.',
 lab:'Формулы экспертизы доступны для условных расчётов по явно заданным параметрам.',
 explorer:'Выбор источника, частоты, периода и категории сохраняет исходные записи и их ограничения.',
 library:'Полный авторский доклад, паспорта, статистические публикации, региональные источники, таблицы и код.',
 updates:'Редакция методики, период наблюдения, дата статистического среза и дата проверки источника учитываются отдельно.'
};


function references(ctx,ids=[]){return array(ids).length?h('div',{class:'international_export-references'},array(ids).map(id=>array(exp(ctx).sources).find(s=>s.id===id)).filter(Boolean).map(s=>link(s.note_number?'['+s.note_number+'] '+(s.title||s.text):s.title||s.text,s.url||report(ctx)))):null;}
function sourceFoot(ctx,label,path){return h('div',{class:'source-foot'},h('span',{},label||'Статистический срез: '+date(stat(ctx).statistical_as_of)),path?link('Источник и данные',path):link('Источники',route('library')));}
function tableNode(ctx,t){
 if(!t)return null;
 const rows=array(t.rows),cols=array(t.columns).map((c,i)=>({key:c.key||'c'+i,label:c.label||c.title||c.key,render:(v,r)=>h('span',{},v??'–',array(t.cellSourceIds?.[rows.indexOf(r)]?.[i]).length?h('sup',{},array(t.cellSourceIds[rows.indexOf(r)][i]).map(id=>{const s=array(exp(ctx).sources).find(s=>s.id===id);return s?link(' ['+(s.note_number||id.replace('fn_',''))+']',s.url||report(ctx)):null;})):null)}));
 return h('div',{},table(rows,cols,{caption:t.title,filename:'international_export-'+t.id+'.csv',pageSize:12}),t.note?para(t.note,'small muted'):null,references(ctx,t.sourceIds));
}
function reportTable(ctx,n,title){const t=array(exp(ctx).tables).find(t=>t.number===n);return t?panel(title||t.title,'Авторская экспертиза',tableNode(ctx,t)):null;}
function reportBlock(ctx,b){
 const attrs={id:'international_export-'+b.id,class:'international_export-report-block'};let node;
 if(b.type==='heading')node=h('h'+Math.max(2,Math.min(4,b.level||2)),attrs,b.text);
 else if(b.type==='table')node=h('section',attrs,h('h3',{},b.title),tableNode(ctx,b));
 else if(b.type==='formula')node=h('div',attrs,b.mathml?h('div',{class:'formula',html:b.mathml}):h('div',{class:'formula'},b.text||b.latex),b.number?h('div',{class:'international_export-formula-number'},'('+b.number+')'):null,b.note?para(b.note):null);
 else if(b.type==='figure_ref'){
  const f=array(exp(ctx).figures).find(f=>f.id===b.figureId),url=b.url||f?.url;
  node=h('figure',{...attrs,class:'international_export-report-figure'},url?link(h('img',{src:absolute(url),alt:b.title||f?.title||'Иллюстрация экспертизы',loading:'lazy'}),url):null,h('figcaption',{},b.title||f?.title),b.note||f?.note?para(b.note||f.note,'small muted'):null);
 }else if(b.type==='list')node=h('div',attrs,array(b.items).map(t=>para(text(t))));
 else node=b.rich_html?h('p',{...attrs,html:b.rich_html}):h('p',attrs,b.text||'');
 return h('div',{},node,references(ctx,b.sourceIds));
}
function start(ctx){return h('div',{class:'international_export-page',dataset:{international_exportPage:ctx.state.page,routeState:JSON.stringify(ctx.state)}},heading(TITLE[ctx.state.page]||pageData(ctx).title,LEAD[ctx.state.page],ctx.state.page==='overview'?h('img',{class:'international_export-logo',src:ctx.project.logo,alt:'Логотип национального проекта «Международная кооперация и экспорт»',width:136,height:116}):null));}
function end(ctx,root){
 const p=pageData(ctx);
 if(array(p.blocks).length)root.append(h('details',{class:'international_export-report'},h('summary',{},icon('table',18),'Текст экспертизы, таблицы и источники раздела'),h('div',{class:'international_export-report-body'},p.blocks.map(b=>reportBlock(ctx,b)),references(ctx,p.sources))));
 root.append(sourceFoot(ctx,'Авторская экспертиза: '+date(exp(ctx).meta.edition_date)+' · Статистический срез: '+date(stat(ctx).statistical_as_of),report(ctx)),h('p',{class:'small'},link('Читать полную текстовую страницу','research/projects/international_export/'+(ctx.state.page==='overview'?'index':ctx.state.page)+'.html')));
 return root;
}
function add(root,...nodes){root.append(...nodes.filter(Boolean));return root;}
function chart(ctx,node,name,title,rows=[],source=''){
 const result=figure(node,{name:'international_export-'+name,title:'Международная кооперация и экспорт · '+title,source:source||'Источник: ЕМИСС. Срез '+date(stat(ctx).statistical_as_of),rows});
 const wrapper=h('div',{class:'international_export-chart-scroll',tabindex:'0','aria-label':title});node.replaceWith(wrapper);wrapper.append(node);return result;
}
function cards(items){return h('div',{class:'project-grid international_export-cards'},items.map(item=>h('article',{class:'project-card'},h('h3',{},item.title),para(item.text),item.path?link('Открыть раздел',item.path):null)));}
function numericTable(rows,columns,filename){return table(rows,columns,{filename:'international_export-'+filename+'.csv',pageSize:12});}
function methodsTable(items){return table(items.map(m=>({title:m.name||m.method_name||m.title||m.method||m.method_id,status:m.current_label||m.current_status_label||m.status_label||m.status||'',reason:m.current_limitations||m.current_evidence||m.current_reason||m.current_note||m.evidence||m.reason||m.note||m.interpretation||''})),[{key:'title',label:'Метод'},{key:'status',label:'Состояние'},{key:'reason',label:'Основания и ограничения'}],{filename:'international_export-methods.csv'});}
export function validateExportSeries(packet,expectedId){
 const id=String(expectedId);
 if(!packet||packet.project_id!==PROJECT||String(packet.source_id)!==id||!Array.isArray(packet.observations))throw Error('Структура статистического источника '+id+' не соответствует выбранному проекту и показателю.');
 if(!packet.observations.every(r=>r&&typeof r==='object'&&String(r.source_id)===id&&typeof r.period_end==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(r.period_end)&&Object.hasOwn(r,'value')&&(r.value===null||typeof r.value==='number'&&Number.isFinite(r.value))))throw Error('Наблюдения источника '+id+' не прошли проверку структуры, периода и числовых значений.');
 return packet.observations;
}
export async function loadExportObservations(source){
 const id=sourceId(source);
 return observationCache.getOrCreate(PROJECT+':observations:'+id,async()=>{
  const response=await fetch('./data/projects/international_export/series/'+id+'.json');
  if(!response.ok)throw Error('Не удалось загрузить источник '+id+' (HTTP '+response.status+')');
  const packet=await response.json();
  return validateExportSeries(packet,id);
 });
}
const observations=loadExportObservations;
function selectedSource(ctx,regional=false){const eligible=sources(ctx).filter(s=>!regional||array(s.regional_latest).length||s.regional_count>0||s.has_regional_data);return eligible.find(s=>sourceId(s)===ctx.state.source)||eligible.find(s=>sourceId(s)==='62715')||eligible[0];}
function sourcePicker(ctx,selected,regional=false){return select('Показатель',sources(ctx).filter(s=>!regional||array(s.regional_latest).length||s.regional_count>0||s.has_regional_data).map(s=>[sourceId(s),sourceName(s)]),sourceId(selected),v=>ctx.set({source:v,series_basis:'',period:'',category:'',region:''}));}
function pointsTable(rows,source){return numericTable(rows.map(r=>({territory:rowName(r)||'Российская Федерация',period:period(r),frequency:frequency(r),value:r.value,unit:r.unit||source.unit,category:Object.entries(r.category||{}).map(([k,v])=>k+': '+v).join(' · '),quality:array(r.quality_flags).map(f=>typeof f==='string'?f:f.message||f.label||f.code).join(' · ')||(r.excluded?'Исключено из расчёта':'')})),[{key:'territory',label:'Территория'},{key:'period',label:'Период'},{key:'frequency',label:'Режим публикации'},{key:'value',label:'Значение',numeric:true,decimals:5},{key:'unit',label:'Единица'},{key:'category',label:'Категория'},{key:'quality',label:'Примечание'}],'source-'+sourceId(source));}
function sourceNote(source){return h('div',{class:'international_export-source-note'},para(source.semantic_note||source.temporal_note||source.interpretation||source.methodology_note||source.note||'Период и единица сохранены по исходной публикации.','small'),link('ЕМИСС '+sourceId(source),source.source_url||'https://www.fedstat.ru/indicator/'+sourceId(source)));}

function reportFigure(ctx,n){
 const f=array(exp(ctx).figures).find(f=>f.number===n||f.id==='figure_'+String(n).padStart(2,'0'));
 return f?panel(f.title,'Иллюстрация авторского доклада',h('figure',{class:'international_export-report-figure'},link(h('img',{src:absolute(f.url),alt:f.title,loading:'lazy'}),f.url),f.note?para(f.note,'small muted'):null,references(ctx,f.sourceIds))):null;
}
function reportPassages(ctx,ids){
 return Object.values(exp(ctx).pages).flatMap(p=>array(p.blocks)).filter(b=>ids.includes(Number(String(b.sourceBlock||b.id).replace(/^b/,'')))).map(b=>reportBlock(ctx,b));
}
function overview(ctx){
 const root=start(ctx),c=stat(ctx).coverage||{};
 add(root,stats([['Коды реестра',fmt(c.registry_indicators??c.indicators_total,0),'Предметный состав исходного каталога'],['Числовые источники',fmt(c.numeric_sources,0),'Собственные определения и периоды'],['Числовые наблюдения',fmt(c.numeric_observations,0),'Срез '+date(stat(ctx).statistical_as_of)],['Федеральные направления','4','Промышленность, инфраструктура, системные меры и АПК']]));
 if(c.coverage_note)add(root,note(c.coverage_note));
 add(root,panel('Что определяет экспортный результат','Вопросы авторской экспертизы',cards([
 {title:'Сопоставимость стоимости',text:'Номинальная выручка зависит от физических поставок, долларовых цен и товарного состава. Годовые и месячные записи различаются.',path:route('targets')},
 {title:'Результат поддержки',text:'Договор, отгрузка, оплата и повторная поставка требуют последовательного наблюдения за одной сделкой и организацией.',path:route('causal')},
 {title:'Однократный учёт ресурсов',text:'Финансовые строки сверяются по периоду, источнику и перечислениям между уровнями бюджета.',path:route('finance')},
 {title:'Территории и производство',text:'Юридический адрес экспортёра не определяет размещение рабочих мест и распределение добавленной стоимости.',path:route('map')}
 ])),reportTable(ctx,5,'Стоимость экспорта и плановые ориентиры'));
 add(root,note('Общероссийские показатели проекта дополнены отдельными территориальными источниками. Экспорт услуг, аграрные операции и распределение субсидий сохраняют свои определения и не подменяют друг друга.'));
 add(root,panel('Разделы исследования','Экспертиза и исследовательские инструменты',h('div',{class:'international_export-directory'},internationalExportPages.filter(p=>p.id!=='overview').map(p=>link(p.title,route(p.id),'international_export-directory-link')))));
 return end(ctx,root);
}
function framework(ctx){return end(ctx,add(start(ctx),panel('Основания оценки','Результативность, эффективность и дополнительность',cards([
 {title:'Исполнение результата',text:'Устанавливаются хозяйственный или организационный результат, совокупность участников и срок наблюдения.'},
 {title:'Соотношение с затратами',text:'Экспортная стоимость и бюджетная поддержка приводятся к согласованной денежной основе и периоду.'},
 {title:'Изменение благодаря поддержке',text:'Вклад меры требует обоснованного сопоставления с развитием без участия в программе.'},
 {title:'Устойчивость деятельности',text:'Повторные поставки, эксплуатация инфраструктуры и завершение услуг оцениваются после первоначального мероприятия.'}
 ])),reportTable(ctx,1),panel('История наблюдения',null,para('Сделка связывает инструменты поддержки единым идентификатором. Сведения о договоре, поставке, платеже, получателе и производственной площадке позволяют избежать двойного учёта.'))));}
const FEDERAL=[
 ['М1','Промышленный экспорт','Товарная специализация, исполнение контрактов, фактическая оплата и результат финансовой поддержки.'],
 ['М2','Создание зарубежной инфраструктуры','Ввод объектов, доступная мощность, эксплуатация и снижение издержек экспортёра.'],
 ['М3','Системные меры развития международной кооперации и экспорта','Финансовые инструменты, региональные программы, цифровые услуги и сопровождение сделки.'],
 ['М4','Экспорт продукции агропромышленного комплекса','Производственная база, переработка, хранение, ветеринарные условия и устойчивый выход на рынки.']
];
function logic(ctx){return end(ctx,add(start(ctx),cards(FEDERAL.map(([id,title,body])=>({title:id+'. '+title,text:body,path:route('domains',{domain:id})}))),reportTable(ctx,2),reportFigure(ctx,1),panel('Проверяемые переходы',null,para('Созданный объект должен использоваться, оказанная услуга – завершать задачу экспортёра, заключённый договор – переходить в поставку и оплату. Для каждого перехода требуются собственные наблюдения.'))));}
function audit(ctx){
 const root=start(ctx),c=stat(ctx).coverage||{},registry=array(stat(ctx).registry).length?stat(ctx).registry:array(ctx.indicators);
 add(root,stats([['Коды реестра',fmt(c.registry_indicators??registry.length,0),'Все позиции предметного каталога'],['С числовыми источниками',fmt(c.indicators_with_numeric??c.numeric_sources,0),'Доступность сохранённой статистики'],['Региональные ряды ЕМИСС',fmt(c.regional_sources??0,0),'Территориальный контекст взят из других публикаций']]));
 add(root,reportTable(ctx,4),reportTable(ctx,15));
 add(root,panel('Проверка обеспеченности показателей',null,numericTable(registry.map(r=>({code:code(r),title:r.title||r.indicator_name||r.name,sources:array(r.source_ids).join(', '),numeric:r.n_numeric??r.numeric_count,status:r.mapping_note||r.status_label||({numeric_data:'Числовые данные доступны',no_verified_numeric_source:'Нет подтверждённого числового источника',no_numeric_source:'Нет подтверждённого числового источника'})[r.status]||'Требует проверки источника'})),[{key:'code',label:'Код'},{key:'title',label:'Показатель'},{key:'sources',label:'ЕМИСС'},{key:'numeric',label:'Числовые записи',numeric:true,decimals:0},{key:'status',label:'Основание'}],'indicator-audit')));
 add(root,panel('Статистические публикации','Единицы, охват и методические ограничения',numericTable(sources(ctx).map(s=>({id:sourceId(s),title:sourceName(s),unit:s.unit,n:s.observations_count??s.observation_count,first:s.first_period,last:s.last_period,note:s.semantic_note||s.note||'',url:s.source_url})),[{key:'id',label:'ЕМИСС',render:(v,r)=>link(v,r.url)},{key:'title',label:'Показатель'},{key:'unit',label:'Единица'},{key:'n',label:'Записи',numeric:true,decimals:0},{key:'first',label:'Первый период'},{key:'last',label:'Последний период'},{key:'note',label:'Ограничения'}],'source-audit')));
 return end(ctx,root);
}

export function selectPublicationBasis(rows,requested){
 const available=[...new Set(rows.map(observationBasis))];
 return available.includes(requested)?requested:available.includes('annual')?'annual':available[0]||'unknown';
}
export function nationalChartSeries(rows,source){
 const groups=[...new Set(rows.map(observationBasis))];if(groups.length>1)throw Error('Нельзя соединять годовые и месячные записи в один статистический ряд.');
 const cumulative=groups[0]!=='annual'&&(rows.some(r=>['cumulative_flow','cumulative_ytd','year_to_date','cumulative_calendar_year'].includes(r.period_semantics)||r.frequency==='cumulative_ytd')||['cumulative_flow','cumulative_ytd','year_to_date','cumulative_calendar_year'].includes(source.period_semantics));
 const points=group=>group.map(r=>({x:Date.parse(r.period_end||String(r.year)+'-12-31'),y:value(r),label:period(r)}));
 const years=[...new Set(rows.map(r=>r.year||String(r.period_end||r.period).slice(0,4)))];
 return cumulative?years.map((year,i)=>({name:sourceName(source)+' · '+year+', с начала года',points:points(rows.filter(r=>String(r.year||String(r.period_end||r.period).slice(0,4))===String(year))),color:C[i%C.length]})):[{name:sourceName(source)+' · '+basisTitle(groups[0]),points:points(rows),color:C[0]}];
}
async function targets(ctx){
 const root=start(ctx),s=selectedSource(ctx);if(!s)return end(ctx,add(root,note('Числовой источник для выбранного показателя отсутствует.')));
 const all=await observations(s),nat=all.filter(national),basis=selectPublicationBasis(nat,ctx.state.series_basis),bases=[...new Set(nat.map(observationBasis))],byBasis=nat.filter(r=>observationBasis(r)===basis),categories=[...new Set(byBasis.map(categoryKey))],cat=categories.includes(ctx.state.category)?ctx.state.category:categories[0],rows=byBasis.filter(r=>categoryKey(r)===cat).sort((a,b)=>String(a.period_end).localeCompare(String(b.period_end)));
 add(root,toolbar(sourcePicker(ctx,s),select('Режим статистического ряда',bases.map(key=>[key,basisTitle(key)]),basis,v=>ctx.set({series_basis:v,period:'',category:''})),categories.length>1?select('Категория',categories.map(c=>[c,Object.values(JSON.parse(c)).join(' · ')||'Все категории']),cat,v=>ctx.set({category:v})):null),sourceNote(s));
 const series=nationalChartSeries(rows,s),cumulative=series.some(item=>item.name.includes(', с начала года'));
 if(rows.length)add(root,panel('Опубликованные значения',basisTitle(basis)+' · '+s.unit,h('div',{},chart(ctx,lineChart(series,{label:sourceName(s),unit:s.unit,monthlyTicks:basis!=='annual'}),'national-'+sourceId(s)+'-'+basis,sourceName(s),rows.map(r=>({period:period(r),frequency:frequency(r),value:r.value,unit:s.unit}))),series.length>1?legend(series):null)));
 if(cumulative)add(root,note('Годовые периоды накопления показаны отдельными линиями. Декабрьский итог и январское значение относятся к разной продолжительности накопления.'));
 if(bases.length>1)add(root,note('Годовые и месячные публикации представлены отдельно. Совпадение даты окончания периода не подтверждает тождество записи, её редакции и статуса.'));
 if(sourceId(s)==='62713')add(root,panel('Расхождение годовой и декабрьской записей','Сохранены обе публикации источника',h('div',{},para('Годовое значение 2025 года составляет 10,2%, декабрьская запись – 0,5%. До объяснения владельцем показателя декабрьская публикация не используется как итог года или прирост за месяц. Годовая величина согласуется с ННЭ 163,65 млрд долл. США и установленной базой 148,5 млрд.'),link('Проверить формулу прироста к базе',route('lab',{calculator:'nne_structure'})),references(ctx,['report']))));
 const comps=array(ana(ctx).target_comparisons||stat(ctx).target_comparisons).filter(r=>String(r.source_id)===sourceId(s));
 const excluded=array(ana(ctx).excluded_target_comparisons||stat(ctx).excluded_target_comparisons).find(r=>String(r.source_id)===sourceId(s));if(excluded)add(root,note('Сравнение с годовой целью не выполняется. '+excluded.reason));
 const reconciliation=array(ana(ctx).annual_monthly_reconciliation).filter(r=>String(r.source_id)===sourceId(s));if(reconciliation.length)add(root,panel('Годовая запись и декабрьская публикация','Проверка двух представлений одного года',numericTable(reconciliation.map(r=>({year:r.year,annual:r.annual_value,december:r.december_value,unit:r.unit,status:r.agree?'Значения совпадают':'Значения расходятся; обе записи сохранены'})),[{key:'year',label:'Год'},{key:'annual',label:'Годовая запись',numeric:true,decimals:5},{key:'december',label:'Декабрьская запись',numeric:true,decimals:5},{key:'unit',label:'Единица'},{key:'status',label:'Результат сверки'}],'annual-december-'+sourceId(s))));
 if(comps.length)add(root,panel('Сопоставление с паспортной целью','Пара наблюдения и плана имеет собственный период и статус',numericTable(comps.map(r=>({year:r.target_year||r.year,frequency:r.source_frequency||r.frequency?basisTitle(r.source_frequency||r.frequency):'Годовое сопоставление',fact:r.fact_value??r.value,target:r.target_value??r.target,difference:r.difference,unit:r.difference_unit||r.unit||s.unit,note:r.note||r.caveat||r.status_label||'',status:'Условное сопоставление'})),[{key:'year',label:'Год'},{key:'frequency',label:'Основание записи'},{key:'fact',label:'Наблюдение',numeric:true,decimals:5},{key:'target',label:'Цель',numeric:true,decimals:5},{key:'difference',label:'Разность',numeric:true,decimals:5},{key:'unit',label:'Единица разности'},{key:'note',label:'Условия сравнения'},{key:'status',label:'Статус'}],'target-comparison')));
 add(root,panel('Исходные наблюдения',basisTitle(basis),pointsTable(rows,s)),reportTable(ctx,5),reportTable(ctx,7));
 return end(ctx,root);
}
const CONTEXTS=[['services','Экспорт услуг'],['agriculture','Экспорт продукции АПК'],['subsidies','Субсидии центрам поддержки экспорта']];
function regionalContext(ctx,key){return(ana(ctx).regional_context||{})[key]||{};}
function contextRows(packet){return array(packet.rows||packet.regional||packet.observations);}
function contextYear(row){return String(row.year||row.period||row.period_end||'').slice(0,4);}
function contextNational(packet,year){const rows=array(packet.national);return number(rows.find(r=>contextYear(r)===String(year))?.value??packet.national_by_year?.[year]);}
function contextSource(packet,year){return array(packet.sources).find(s=>String(s.year)===String(year))?.url||packet.source_url;}
function contextNote(ctx,key,packet,year){return h('div',{class:'international_export-source-note'},para(packet.note||({services:'Региональная статистика Банка России по экспорту услуг описывает учтённые операции. Расположение головной организации может отличаться от места выполнения работ.',agriculture:'Территория экспортёра продукции АПК отличается от территории выращивания, переработки и распределения добавленной стоимости.',subsidies:'Распределение бюджетной субсидии показывает назначение ресурса региональным центрам. Результат поддержки требует наблюдения за получателями.'})[key],'small'),array(packet.notes).map(item=>para(text(item),'small')),contextSource(packet,year)?link('Источник территориальных сведений',contextSource(packet,year)):link('Источники авторской экспертизы',report(ctx)));}
function geography(ctx,profiles=false){
 const root=start(ctx),key=CONTEXTS.some(([id])=>id===ctx.state.context)?ctx.state.context:'services',packet=regionalContext(ctx,key),all=contextRows(packet),years=[...new Set(all.map(contextYear))].filter(Boolean).sort(),year=years.includes(ctx.state.year)?ctx.state.year:years.at(-1),rows=all.filter(r=>contextYear(r)===year),unit=packet.unit||({services:'млн долл. США',agriculture:'млн долл. США',subsidies:'млн руб.'})[key];
 add(root,toolbar(select('Территориальный источник',CONTEXTS,key,v=>ctx.set({context:v,year:'',region:'',measure:''})),years.length?select('Год',years.map(y=>[y,y]),year,v=>ctx.set({year:v,region:''})):null),contextNote(ctx,key,packet,year),packet.coverage_note?note(packet.coverage_note):null);
 if(!rows.length){
  add(root,note('Полный машиночитаемый территориальный набор для этого источника не включён в текущий статистический срез. Авторские таблицы и иллюстрации сохраняют опубликованные значения и ограничения.'));
  add(root,key==='services'?reportTable(ctx,8):null,key==='services'?reportFigure(ctx,6):key==='agriculture'?reportFigure(ctx,7):reportFigure(ctx,10));return end(ctx,root);
 }
 const numeric=rows.filter(r=>number(r.value)!==null),sum=numeric.reduce((a,r)=>a+number(r.value),0),nationalTotal=contextNational(packet,year),previous=r=>all.find(old=>regionId(old)===regionId(r)&&contextYear(old)===String(Number(year)-1)),canGrow=numeric.some(r=>number(previous(r)?.value)>0),measure=ctx.state.measure==='share'&&nationalTotal>0?'share':ctx.state.measure==='growth'&&canGrow?'growth':'value',displayUnit=measure==='share'?'% национального итога':measure==='growth'?'% к предыдущему году':unit,displayValue=r=>measure==='share'?ratioPercent(number(r.value),nationalTotal):measure==='growth'?number(previous(r)?.value)>0?growthFromBase(number(r.value),number(previous(r).value)):null:number(r.value),sorted=[...numeric].sort((a,b)=>number(b.value)-number(a.value)),displayRows=rows.map(r=>({territory:rowName(r),year,measure,value:displayValue(r),unit:displayUnit,source_value:number(r.value),source_unit:unit,source_url:r.source_url||contextSource(packet,year)}));
 add(root,toolbar(select('Показатель',[['value','Опубликованный объём'],...(nationalTotal>0?[['share','Доля в национальном итоге']]:[]),...(canGrow?[['growth','Изменение к предыдущему году']]:[])],measure,v=>ctx.set({measure:v})),!profiles?select('Представление',[['map','Картограмма'],['tiles','Плиточная карта']],ctx.state.view||'map',v=>ctx.set({view:v})):null));
 add(root,stats([['Наблюдаемые территории',fmt(numeric.length,0),packet.coverage_note||'Границы исходного источника'],['Сумма наблюдений',fmt(sum,3),unit],['Национальный итог',fmt(nationalTotal,3),nationalTotal===null?'Сопоставимый итог не установлен':unit],['Доля первых десяти',nationalTotal>0?fmt(sorted.slice(0,10).reduce((a,r)=>a+number(r.value),0)/nationalTotal*100,2)+'%':'Не рассчитывается','В национальном итоге того же источника']]));
 const unallocated=number(array(packet.unallocated).find(r=>contextYear(r)===year)?.value??packet.unallocated_by_year?.[year]);
 if(unallocated!==null&&nationalTotal!==null)add(root,note('Не распределено по территориям: '+fmt(unallocated,3)+' '+unit+'. Разность между национальным итогом и суммой региональных и нераспределённых записей: '+fmt(nationalTotal-sum-unallocated,5)+' '+unit+'. Исходное округление сохранено.'));
 if(!profiles&&ctx.geo&&ctx.catalog?.regions){
  const values=new Map(rows.filter(r=>r.map_id||r.region_id||r.code).map(r=>[regionId(r),{value:displayValue(r),detail:year+' · '+CONTEXTS.find(([id])=>id===key)[1]}]));
  const map=mapView(ctx.geo,ctx.catalog.regions,values,{unit:displayUnit,tile:ctx.state.view==='tiles',selected:ctx.state.region||null,title:CONTEXTS.find(([id])=>id===key)[1]+' · '+year,onSelect:id=>ctx.set({region:id})});
  add(root,panel('Территориальное распределение',year+' · '+displayUnit,h('div',{},figureControls(map.svg,{name:'international_export-'+key+'-'+year+'-'+measure,title:CONTEXTS.find(([id])=>id===key)[1],source:contextSource(packet,year)||'Источник авторской экспертизы',rows:displayRows}),map.element)));
 }
 const requested=ctx.state.region?rows.find(r=>regionId(r)===ctx.state.region):null,missing=ctx.state.region&&!requested?array(ctx.catalog?.regions).find(r=>r.id===ctx.state.region):null,selected=requested||(!missing?sorted[0]:null);
 if(missing)add(root,panel('Профиль территории',missing.name,note('Для выбранной территории в этом источнике за '+year+' год нет наблюдения. Значение не заменяется нулём и не включается в сумму или распределение.'),link('Вернуться к опубликованным территориям',route(profiles?'regions':'map',{context:key,year,measure,view:ctx.state.view||'map'}))));
 if(selected){
  const history=all.filter(r=>regionId(r)===regionId(selected)).sort((a,b)=>contextYear(a).localeCompare(contextYear(b)));
  add(root,panel('Профиль территории',null,h('div',{},select('Территория',rows.map(r=>[regionId(r),rowName(r)]).sort((a,b)=>a[1].localeCompare(b[1],'ru')),regionId(selected),v=>ctx.set({region:v})),stats([['Территория',rowName(selected),''],['Опубликованный объём',fmt(number(selected.value),4),unit],['Доля национального итога',nationalTotal>0?fmt(number(selected.value)/nationalTotal*100,3)+'%':'Не установлена','Год '+year]]),history.length>1?chart(ctx,lineChart([{name:rowName(selected),points:history.map(r=>({x:Date.UTC(Number(contextYear(r)),11,31),y:number(r.value)})),color:C[0]}],{unit,label:'Динамика территориальных операций'}),'region-'+key+'-'+regionId(selected),'Территориальные сведения',history,'Источник: '+(contextSource(packet,year)||'территориальная публикация доклада')):null)));
 }
 add(root,panel('Сопоставление территорий','15 наибольших опубликованных объёмов за выбранный год',chart(ctx,bars(sorted.slice(0,15).map(r=>({name:rowName(r),value:displayValue(r)})),{unit:displayUnit,label:'Территориальное распределение'}),'regional-'+key+'-'+year+'-'+measure,CONTEXTS.find(([id])=>id===key)[1],sorted.slice(0,15).map(r=>displayRows.find(row=>row.territory===rowName(r))),contextSource(packet,year)||'Источник авторской экспертизы')));
 add(root,panel('Территориальные наблюдения',year,numericTable(rows.map(r=>({name:rowName(r),value:r.value,unit,share:nationalTotal>0?ratioPercent(number(r.value),nationalTotal):null,growth:number(previous(r)?.value)>0?growthFromBase(number(r.value),number(previous(r).value)):null,note:r.note||r.qualification||''})),[{key:'name',label:'Территория'},{key:'value',label:'Объём',numeric:true,decimals:4},{key:'unit',label:'Единица'},{key:'share',label:'Доля национального итога, %',numeric:true,decimals:4},...(canGrow?[{key:'growth',label:'Изменение к предыдущему году, %',numeric:true,decimals:4}]:[]),{key:'note',label:'Ограничения'}],'regional-'+key+'-'+year)));
 if(key==='services')add(root,reportTable(ctx,8),note('На картограмме услуг отражено распределение операций по правилам Банка России. Значение не является оценкой эффективности региональной власти или вкладом территории в производство экспортной продукции.'));
 else if(key==='agriculture')add(root,reportFigure(ctx,7));else add(root,reportFigure(ctx,10));
 return end(ctx,root);
}
function finance(ctx){
 const root=start(ctx),f=doc(ctx).finance||{},mode=ctx.state.finance||'passport';
 add(root,toolbar(select('Финансовый раздел',[['passport','Паспорта по годам и направлениям'],['consolidation','Подтверждённый повторный счёт'],['budget','Федеральные бюджетные предложения'],['results','Стоимость и результаты поддержки']],mode,v=>ctx.set({finance:v}))));
 if(mode==='passport'){
  add(root,note(f.caveat||'Опубликованные строки приведены к периоду 2025–2030 годов. Арифметическая сумма и сумма после установленной корректировки различаются.'),reportTable(ctx,11));
  const rows=array(f.projects).map(r=>({name:(r.code||r.fp||'')+' '+(r.title||r.name||r.federal_project_name||''),value:number(r.totalBillionRub)??(number(r.totalThousandRub)!==null?number(r.totalThousandRub)/1e6:null)})).filter(r=>finite(r.value));
  if(rows.length)add(root,panel('Распределение паспортных назначений','До корректировки подтверждённого повторного счёта',chart(ctx,bars(rows,{unit:'млрд руб.',label:'Паспортное финансирование'}),'finance','Финансовые назначения',rows,'Источник: паспорта четырёх федеральных проектов. Общий горизонт 2025–2030.')));
  add(root,reportFigure(ctx,9));
 }else if(mode==='consolidation')add(root,stats([['Опубликованные строки',number(f.grossTotalThousandRub??f.totalThousandRub)!==null?fmt(number(f.grossTotalThousandRub??f.totalThousandRub)/1e6,6):'Не установлена','Млрд руб. за 2025–2030 годы'],['Подтверждённый повторный счёт',number(f.knownDuplicateTransferThousandRub)!==null?fmt(number(f.knownDuplicateTransferThousandRub)/1e6,6):'Не установлен','Млрд руб.'],['После известной корректировки',number(f.adjustedTotalThousandRub)!==null?fmt(number(f.adjustedTotalThousandRub)/1e6,6):'Не установлено','Млрд руб.'],['Окончательная консолидация',number(f.consolidatedTotalThousandRub)===null?'Не установлена':fmt(number(f.consolidatedTotalThousandRub)/1e6,6),'Статус подтверждения источников']]),reportTable(ctx,10),panel('Границы установленной корректировки',null,h('div',{},para('Подтверждённое повторное включение трансферта исключается из арифметической суммы один раз. Полученный результат сохраняет статус суммы после известной корректировки. Для окончательной консолидации требуется установить происхождение региональных назначений остальных лет.'),para('Финансирование АПК после 2030 года исключено из шестилетнего сравнения. Даты соглашений, перечислений и получения экспортного результата учитываются отдельно.'))));
 else if(mode==='budget')add(root,reportTable(ctx,12),reportFigure(ctx,11),note('Бюджетные предложения и паспортные назначения относятся к разным редакциям и правовым стадиям. Разность сохраняется для содержательной сверки состава и сроков обязательств.'));
 else add(root,reportFigure(ctx,10),panel('Результат на рубль поддержки',null,h('div',{},para('В отношении экспорта к субсидии обе величины выражаются в рублях. Коэффициент показывает масштаб поддержанной деятельности. Дополнительный эффект требует оценки поставок без меры.'),link('Коэффициент поддержанного экспорта',route('lab',{calculator:'support_ratio'})),h('span',{},' · '),link('Дополнительный экспорт на рубль поддержки',route('lab',{calculator:'additional_export'})))),panel('Риск и календарь обязательств',null,para('Кредит, процентная субсидия, страхование и компенсация перевозки имеют разные расходы и задержки результата. Банковский кредит не заменяет бюджетную стоимость его поддержки.')));
 return end(ctx,root);
}

const pairResult=r=>String(r.result_id||r.result_node_id||r.source_node_id||r.source_id||r.from||r.source||r.result||''),pairIndicator=r=>String(r.indicator_id||r.indicator_node_id||r.target_node_id||r.target_id||r.to||r.target||r.indicator||'');
function thresholdTable(ctx){const rows=array(doc(ctx).text?.candidateThresholds);return rows.length?panel('Чувствительность лексического отбора','Один наиболее близкий показатель собственного федерального проекта',numericTable(rows.map(r=>({threshold:r.threshold,computed:r.results_with_candidate??r.pairs,author:r.author_reported_results,without:r.results_without_candidate,status:r.matches_author===false?'Различие спецификаций':'Число совпало, коэффициенты проверяются отдельно'})),[{key:'threshold',label:'Порог косинуса',numeric:true,decimals:2},{key:'computed',label:'Независимый расчёт',numeric:true,decimals:0},{key:'author',label:'В авторском докладе',numeric:true,decimals:0},{key:'without',label:'Без кандидата',numeric:true,decimals:0},{key:'status',label:'Интерпретация'}],'lexical-thresholds')):null;}
function matrixFigure(ctx,m,values,name,title,source){
 const marks=heatmap(m.rows.map(r=>r.code),m.columns.map(c=>c.code),values,{width:1400,left:110,cellHeight:32,label:title,format:v=>fmt(v,3)});marks.classList.add('international_export-wide-matrix');
 return h('div',{},chart(ctx,marks,name,title,m.rows.flatMap((r,i)=>m.columns.map((c,j)=>({result:r.code,result_title:r.title,indicator:c.code,indicator_title:c.title,value:values[i][j]}))),source),h('details',{class:'international_export-matrix-key'},h('summary',{},'Названия результатов и показателей в матрице'),h('h3',{},'Результаты'),m.rows.map(r=>para(r.code+' – '+r.title,'small')),h('h3',{},'Показатели'),m.columns.map(c=>para(c.code+' – '+c.title,'small'))));
}
function network(ctx){
 const root=start(ctx),n=doc(ctx).network||{},t=doc(ctx).text||{},kind=['structural','lexical','ambiguous'].includes(ctx.state.evidence)?ctx.state.evidence:'structural',nodes=array(n.nodes),nodeName=id=>nodes.find(n=>String(n.id)===String(id))?.title||id;
 const thresholdChoices=array(t.candidateThresholds).map(r=>number(r.threshold)).filter(v=>v!==null),threshold=thresholdChoices.includes(number(ctx.state.threshold))?number(ctx.state.threshold):.1;
 const candidates=array(n.lexicalCandidates||t.bestCandidates),pairs=kind==='lexical'?candidates.filter(r=>number(r.cosine??r.score)!==null&&number(r.cosine??r.score)>=threshold):kind==='ambiguous'?array(n.ambiguousClaims):array(n.structuralPairs),view=ctx.state.network_view==='matrix'?'matrix':'table';
 add(root,stats([['Результаты',fmt(n.counts?.results??nodes.filter(x=>x.kind==='result').length,0),'Паспортные записи'],['Пары общей задачи',fmt(array(n.structuralPairs).length,0),'Документальное основание'],['Неоднозначные утверждения',fmt(array(n.ambiguousClaims).length,0),'Адресат требует проверки'],['Отобранные записи',fmt(pairs.length,0),kind==='lexical'?'Косинус не ниже '+fmt(threshold,2):'Выбранный тип основания']]));
 add(root,toolbar(select('Основание связи',[['structural','Принадлежность общей задаче'],['lexical','Лексическое сходство'],['ambiguous','Неоднозначные записи влияния']],kind,v=>ctx.set({evidence:v})),kind==='lexical'?select('Порог лексического сходства',thresholdChoices.map(v=>[String(v),fmt(v,2)]),String(threshold),v=>ctx.set({threshold:v})):null,kind!=='ambiguous'?select('Представление связей',[['table','Таблица связей'],['matrix','Матрица связей']],view,v=>ctx.set({network_view:v})):null));
 if(kind==='lexical')add(root,note('Платформа рассчитывает самостоятельную полностью заданную спецификацию для 65 текстов: 47 результатов и 18 показателей федеральных проектов. Точные стоп-слова исходного авторского расчёта не опубликованы. При пороге 0,05 получено 28 кандидатов, в докладе – 26. Авторские сведения сохраняются отдельно.'));
 const rows=pairs.map(r=>({fp:r.fp||'',from:r.result_title||nodeName(pairResult(r)),to:r.indicator_title||nodeName(pairIndicator(r))||'Адресат не установлен',basis:r.task_title||r.claim_text||r.value_raw||'',score:r.cosine??r.score,source:r.source_url||r.document_url||''}));
 add(root,panel(kind==='ambiguous'?'Записи с неустановленным адресатом':'Связи результатов и показателей',kind==='lexical'?'Лучшее лексическое соответствие внутри своего ФП':'Состав документального корпуса',numericTable(rows,[{key:'fp',label:'ФП'},{key:'from',label:'Результат'},{key:'to',label:'Показатель / адресат'},{key:'basis',label:'Документальное основание'},...(kind==='lexical'?[{key:'score',label:'Косинус',numeric:true,decimals:5}]:[]),{key:'source',label:'Паспорт',render:v=>link('Источник',v)}],'network-'+kind)));
 const matrix=t.resultIndicatorMatrix;
 if(kind!=='ambiguous'&&view==='matrix'&&matrix?.rows?.length&&matrix?.columns?.length){
  const lookup=new Map(pairs.map(r=>[pairResult(r)+'|'+pairIndicator(r),r]));
  const values=matrix.rows.map(r=>matrix.columns.map(c=>{const item=lookup.get(r.id+'|'+c.id);return item?(kind==='lexical'?number(item.cosine??item.score):1):null;}));
  add(root,panel('Матрица выбранных связей',kind==='lexical'?'Отобранные кандидаты; остальные пары не отмечены':'1 – принадлежность общей задаче',matrixFigure(ctx,matrix,values,'network-'+kind,'Матрица выбранных связей','Источник: сохранённые паспорта и независимая текстовая спецификация платформы. Причинная интерпретация не устанавливается.')));
 }
 if(kind==='lexical')add(root,thresholdTable(ctx),reportTable(ctx,13));
 add(root,note(kind==='ambiguous'?'Неустановленные адресаты и исходные числовые записи сохраняются для проверки. Им не присваиваются причинные веса.':kind==='lexical'?'Положительный коэффициент помогает выбрать пару для содержательного изучения. Он не устанавливает ответственность за изменение показателя или величину эффекта.':'Принадлежность общей задаче описывает конструкцию паспорта. Для проверки хозяйственного механизма нужны конкретный показатель, единица наблюдения и срок результата.'));
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
 add(root,stats([['Профили лексической матрицы',fmt(t.profileCount,0),'Результаты и показатели федеральных проектов'],['Результаты',fmt(t.resultProfiles,0),'Наименование и содержательная характеристика'],['Показатели ФП',fmt(t.indicatorProfiles,0),'Полные наименования'],['Признаки TF–IDF',fmt(t.features,0),'Независимая спецификация платформы']]),array(t.notes).length?note(t.notes[0]):null);
 const packets=await Promise.all(selectedDocuments.map(d=>t.documentFiles?.[d.id]?textPacket(t.documentFiles[d.id]):Promise.resolve({document:d,units:[]})));
 const searchUnits=packets.flatMap(p=>array(p.units).map(u=>({...u,documentTitle:p.document.title||p.document.id,sourceURL:u.source_url||p.source_url||p.document.url})));
 const input=h('input',{type:'search',value:q,placeholder:'Например: экспорт, оплата, цифровые услуги','aria-label':'Поиск по документам'});
 const found=h('div',{class:'international_export-text-results'});
 const draw=()=>{const query=input.value.trim().toLocaleLowerCase('ru');const matches=searchUnits.filter(b=>b.text&&(!query||b.text.toLocaleLowerCase('ru').includes(query)));found.replaceChildren(h('p',{class:'small muted'},'Фрагментов: '+matches.length+(matches.length>30?' · показаны первые 30, уточните запрос':'')),...matches.slice(0,30).map(b=>h('article',{class:'international_export-text-fragment'},h('p',{class:'small muted'},b.documentTitle),para(b.text),link('Паспортный источник',b.sourceURL))));};input.addEventListener('input',draw);input.addEventListener('keydown',e=>{if(e.key==='Enter')ctx.set({query:input.value});});draw();
 add(root,toolbar(select('Текстовый профиль',[['project','Все паспортные профили'],...documents.map(d=>[d.id,d.title||d.id])],profile,v=>ctx.set({document:v}))),panel('Поиск по формулировкам паспортов','Содержательные профили из сохранённых паспортов. Полные документы и правила формирования профиля доступны в источниках.',h('div',{},toolbar(input,button('Найти',()=>ctx.set({query:input.value}),'button')),found)));
 if(similarity.length)add(root,panel('Близость текстовых профилей','Одинаковые правила обработки документального корпуса',numericTable(similarity.map(r=>({project:r.project_name||r.project||r.target_project||r.name||'',score:r.cosine??r.similarity??r.value,kind:r.kind||r.method||''})),[{key:'project',label:'Проект'},{key:'score',label:'Косинус',numeric:true,decimals:5},{key:'kind',label:'Спецификация'}],'text-similarity')));
 if(terms.length)add(root,panel('Термины выбранного профиля','Вес TF–IDF',numericTable(terms.map(r=>({term:r.term||r.token||r.word,value:r.tfidf??r.weight??r.count??r.value,kind:r.document_id==='project'?'Весь проект':documents.find(d=>d.id===r.document_id)?.title||r.document_id||''})),[{key:'term',label:'Термин'},{key:'value',label:'Вес TF–IDF',numeric:true,decimals:5},{key:'kind',label:'Документ / профиль'}],'text-terms')));
 if(documents.length)add(root,panel('Документы корпуса',null,numericTable(documents.map(d=>({title:d.title||d.name||d.document_title||d.id,kind:({np:'Национальный паспорт',fp:'Федеральный паспорт'})[d.kind]||d.kind||'',url:d.url||d.source_url||d.text_url||'',tokens:d.tokens||d.token_count||d.n_tokens})),[{key:'title',label:'Документ'},{key:'kind',label:'Тип'},{key:'tokens',label:'Токены',numeric:true,decimals:0},{key:'url',label:'Источник',render:v=>link('Открыть',v)}],'text-documents')));
 if(array(t.sensitivity).length)add(root,panel('Чувствительность текстового сравнения','Проверка чувствительности состава и правил текстового сравнения',numericTable(t.sensitivity.map(r=>({variant:({base:'Исходная спецификация',stemmed:'Стемминг русских слов',unigram:'Униграммы',unigrams:'Униграммы',equal_levels:'Равные веса уровней',federal_only:'Только федеральные паспорта',national_only:'Только национальные паспорта'})[r.variant]||r.variant,rho:r.spearman,nearest:array(r.top3).join(' · ')})),[{key:'variant',label:'Спецификация'},{key:'rho',label:'Корреляция Спирмена',numeric:true,decimals:4},{key:'nearest',label:'Три ближайших проекта'}],'text-sensitivity')));
 const full=t.resultIndicatorMatrix;
 if(full?.rows?.length&&full?.columns?.length){
  const chosen=FEDERAL.some(([code])=>code===ctx.state.matrix_fp)?ctx.state.matrix_fp:'all',indexes=full.rows.map((r,i)=>({r,i})).filter(({r})=>chosen==='all'||r.fp===chosen),matrix={rows:indexes.map(({r})=>r),columns:full.columns},values=indexes.map(({i})=>full.values[i]);
  add(root,panel('Лексическая матрица результатов и показателей','Независимый расчёт на 65 текстах',h('div',{},toolbar(select('Строки лексической матрицы',[['all','Все 47 результатов'],...FEDERAL.map(([id,title])=>[id,id+'. '+title])],chosen,v=>ctx.set({matrix_fp:v}))),matrixFigure(ctx,matrix,values,'text-result-indicator','Лексическая матрица','Источник: собственная полностью заданная спецификация TF–IDF по сохранённым паспортным профилям. Межпроектные пары показаны для описания лексики; отбор кандидатов ограничен собственным ФП.'))));
 }
 const similarities=array(t.documentSimilarity),projectCodes=FEDERAL.map(([id])=>id);
 if(similarities.length){
  const values=projectCodes.map(a=>projectCodes.map(b=>a===b?null:number(similarities.find(r=>r.left===a&&r.right===b)?.cosine)));
  add(root,panel('Близость четырёх федеральных направлений','Отдельная модель на четырёх агрегированных профилях',h('div',{},chart(ctx,heatmap(projectCodes,projectCodes,values,{label:'Лексическая близость федеральных проектов',left:140,cellHeight:70,format:v=>fmt(v,3)}),'federal-profile-similarity','Близость федеральных направлений',similarities,'Источник: независимая спецификация платформы. Диагональ тождественна единице и исключена из цветовой шкалы.'),para('Диагональные клетки обозначают сравнение профиля с самим собой и не участвуют в шкале межпроектной близости. Коэффициенты этой модели не сравниваются напрямую с матрицей 47 × 18.','small'))));
 }
 const frameRows=array(t.frameScores),frames=[...new Map(frameRows.map(r=>[r.frame_id||r.frame,r.frame_name||r.frame])).entries()];
 if(frameRows.length){
  const frameValues=projectCodes.map(code=>frames.map(([id])=>number(frameRows.find(r=>r.code===code&&(r.frame_id||r.frame)===id)?.percent)));
  add(root,panel('Темы в результатах федеральных проектов','Доля результатов собственного направления, %',h('div',{},chart(ctx,heatmap(projectCodes,frames.map((_,i)=>'Т'+(i+1)),frameValues,{label:'Тематические признаки',left:140,cellHeight:66,max:100,format:v=>fmt(v,1)}),'federal-frames','Темы паспортных результатов',frameRows,'Источник: независимый словарь тематических признаков платформы. Темы пересекаются.'),h('div',{class:'international_export-matrix-key'},frames.map(([id,title],i)=>para('Т'+(i+1)+' – '+title,'small'))),note('Знаменатель – число результатов соответствующего ФП. Темы пересекаются, поэтому сумма их долей может превышать 100%.'))));
 }
 add(root,thresholdTable(ctx));
 if(array(t.notes).length)add(root,panel('Основания текстового расчёта',null,h('div',{},array(t.notes).map(item=>para(text(item))))));

 add(root,reportTable(ctx,13),reportFigure(ctx,14),reportFigure(ctx,15),note('Лексическое сходство и тематические признаки описывают документы. Темы пересекаются, поэтому их доли не образуют разбиение на 100%. Хозяйственный переход требует самостоятельного подтверждения.'));
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
 add(root,toolbar(select('Федеральное направление',FEDERAL.map(([id,title])=>[id,id+'. '+title]),selected[0],v=>ctx.set({domain:v}))),panel(selected[1],null,h('div',{},para(selected[2]),definition?.mechanism?para(definition.mechanism):null,definition?.transition?para('Проверяемый переход: '+definition.transition):null,...reportPassages(ctx,array(definition?.mechanismBlocks).map(id=>Number(String(id).replace(/^b/,'')))),definition?.source_url?link('Паспорт федерального проекта',definition.source_url):null,h('p',{}),link('Финансовые основания',route('finance')),h('span',{},' · '),link('Связи результатов и показателей',route('network')))));
 if(targetRows.length)add(root,panel('Плановые показатели направления',null,h('div',{class:'international_export-download-grid'},targetRows.map(t=>link(t.title||t.name||t.indicator_name,route('projections',{target:String(code(t))}))))));
 add(root,reportTable(ctx,2),reportTable(ctx,3));return end(ctx,root);
}
function proposals(ctx){return end(ctx,add(start(ctx),reportTable(ctx,14),cards([
 {title:'История определений',text:'Каждая запись получает версию методики, период, стадию уточнения и условие сопоставления.'},
 {title:'Исполненная сделка',text:'Договор связывается с отгрузкой, наступлением срока оплаты, платежом и использованными инструментами поддержки.'},
 {title:'Устойчивость экспортёра',text:'Повторные поставки оцениваются по полным группам наблюдения, включая компании, прекратившие деятельность.'},
 {title:'Использование результата',text:'Введённая инфраструктура и цифровая услуга оцениваются по фактической работе, завершённости и издержкам пользователя.'}
 ])));}
export function ratioPercent(numerator,denominator){return Number.isFinite(numerator)&&Number.isFinite(denominator)&&numerator>=0&&denominator>0?100*numerator/denominator:null;}
export function nneTotal(industrial,agriculture){return[industrial,agriculture].every(x=>Number.isFinite(x)&&x>=0)?industrial+agriculture:null;}
export function growthFromBase(value,base=148.5){return Number.isFinite(value)&&value>=0&&Number.isFinite(base)&&base>0?100*(value/base-1):null;}
export function supportRatio(exports,subsidies){return Number.isFinite(exports)&&exports>=0&&Number.isFinite(subsidies)&&subsidies>0?exports/subsidies:null;}
export function paidShipmentShare(shipments){if(!Array.isArray(shipments)||!shipments.length||!shipments.every(s=>Number.isFinite(s.due)&&s.due>=0&&Number.isFinite(s.paid)&&s.paid>=0))return null;return ratioPercent(shipments.reduce((sum,s)=>sum+Math.min(s.paid,s.due),0),shipments.reduce((sum,s)=>sum+s.due,0));}
export function cohortShare(completed,started){return Number.isInteger(completed)&&Number.isInteger(started)&&completed<=started?ratioPercent(completed,started):null;}
export function additionalExportRatio(observed,counterfactual,support){return[observed,counterfactual].every(x=>Number.isFinite(x)&&x>=0)&&Number.isFinite(support)&&support>0?(observed-counterfactual)/support:null;}
export function differenceInDifferences(t0,t1,c0,c1){return[t0,t1,c0,c1].every(Number.isFinite)?(t1-t0)-(c1-c0):null;}
export function requiredAnnualChange(base,target,years){return Number.isFinite(base)&&Number.isFinite(target)&&Number.isFinite(years)&&base>0&&target>=0&&years>0?100*(Math.pow(target/base,1/years)-1):null;}
const CALCULATORS=[['nne_structure','Состав ННЭ и прирост к базе'],['annual_change','Условный среднегодовой темп'],['support_ratio','Экспорт к сумме субсидии'],['paid_shipments','Доля оплаченных поставок'],['exporter_retention','Повторные экспортёры'],['additional_export','Дополнительный экспорт'],['service_completion','Завершённость услуг'],['did','Разность изменений']];
function calculator(ctx,kind){
 const specs={
  nne_structure:{title:'Состав ННЭ и прирост к базе 2023 года',description:'ННЭ = промышленный экспорт + экспорт АПК. Обе составляющие относятся к одному периоду и товарным перечням методики. Прирост к установленной базе 148,5 млрд долл. США рассчитывается для годового итога.',fields:[['industrial','Промышленный экспорт за год, млрд долл. США'],['agriculture','Экспорт АПК за год, млрд долл. США']],compute:v=>nneTotal(v.industrial,v.agriculture),unit:'млрд долл. США',extra:(v,result)=>'Прирост к базе 2023 года: '+fmt(growthFromBase(result),4)+'%. Номинальные значения не определяют физический объём и добавленную стоимость.',block:149,invalid:'Введите неотрицательные годовые стоимости промышленного экспорта и АПК в млрд долл. США.'},
  annual_change:{title:'Необходимый среднегодовой номинальный прирост',description:'100 × ((цель / исходное значение)^(1 / число годовых переходов) − 1). Между 2025 и 2030 годами пять переходов. Единица и определение сохраняются.',fields:[['base','Исходная стоимость, млрд долл. США'],['target','Целевая стоимость, млрд долл. США'],['years','Число годовых переходов']],compute:v=>requiredAnnualChange(v.base,v.target,v.years),unit:'% в год',block:274,invalid:'Введите положительное исходное значение и число годовых переходов, а также неотрицательную цель.'},
  support_ratio:{title:'Поддержанный экспорт к фактической субсидии',description:'Поддержанный экспорт / фактически предоставленные субсидии. Обе суммы выражаются в млн руб. за согласованный период. Прогнозная часть экспорта, если она используется, раскрывается отдельно.',fields:[['exports','Поддержанный экспорт, млн руб.'],['subsidies','Фактически предоставленные субсидии, млн руб.']],compute:v=>supportRatio(v.exports,v.subsidies),unit:'руб. экспорта на рубль субсидии',block:166,invalid:'Введите неотрицательный поддержанный экспорт и положительную фактическую субсидию в одной денежной основе.'},
  paid_shipments:{title:'Доля оплаченной стоимости поставок',description:'Включаются только отгрузки с наступившим сроком оплаты. Платёж ограничивается стоимостью каждой конкретной отгрузки до суммирования. Три отгрузки приведены к одной валютной оценке, лишние строки можно заполнить нулями.',fields:[['due1','Стоимость отгрузки 1, денежных единиц'],['paid1','Подтверждённая оплата отгрузки 1'],['due2','Стоимость отгрузки 2, денежных единиц'],['paid2','Подтверждённая оплата отгрузки 2'],['due3','Стоимость отгрузки 3, денежных единиц'],['paid3','Подтверждённая оплата отгрузки 3']],compute:v=>paidShipmentShare([1,2,3].map(i=>({due:v['due'+i],paid:v['paid'+i]}))),unit:'% стоимости с наступившим сроком',block:397,invalid:'Введите неотрицательные стоимости и платежи по трём отгрузкам. Общая стоимость должна быть положительной.'},
  exporter_retention:{title:'Повторные экспортёры второго года',description:'Компании с повторной поставкой в месяцы 13–24 / все впервые экспортировавшие компании с полным 24-месячным наблюдением × 100%. Прекратившие деятельность остаются в знаменателе.',fields:[['repeated','Компании с повторной поставкой в месяцы 13–24'],['cohort','Компании с полным наблюдением за 24 месяца']],compute:v=>cohortShare(v.repeated,v.cohort),unit:'% полной группы',block:400,invalid:'Введите целую положительную численность полной группы и целое число повторных экспортёров от нуля до её численности.'},
  additional_export:{title:'Дополнительный экспорт на рубль поддержки',description:'(Наблюдаемый экспорт − обоснованная оценка без поддержки) / расходы на группу. Суммы за согласованный горизонт приводятся к одной ценовой и валютной основе. Контрфактическая оценка вводится пользователем и этим калькулятором не устанавливается.',fields:[['observed','Наблюдаемый экспорт группы, млн руб.'],['counterfactual','Обоснованная оценка экспорта без поддержки, млн руб.'],['support','Расходы на поддержку группы, млн руб.']],compute:v=>additionalExportRatio(v.observed,v.counterfactual,v.support),unit:'руб. дополнительного экспорта на рубль поддержки',block:403,invalid:'Введите оба неотрицательных экспортных значения и положительные расходы. При отсутствии обоснованной оценки без поддержки расчёт не выполняется.'},
  service_completion:{title:'Завершение услуг за заданный срок',description:'Успешно завершённые обращения / обращения одной исходной группы × 100%. Все обращения наблюдаются одинаковый срок. Отказы, отзывы и незавершённые обращения остаются в знаменателе.',fields:[['done','Успешно завершённые обращения за срок наблюдения'],['started','Начатые обращения исходной группы']],compute:v=>cohortShare(v.done,v.started),unit:'% исходной группы обращений',block:413,invalid:'Введите целое положительное число начатых обращений и целое число завершённых от нуля до размера исходной группы.'},
  did:{title:'Разность изменений в двух группах',description:'(Получатели после − до) − (сравнение после − до). Арифметический результат приобретает причинный смысл только после проверки дизайна, предшествующих тенденций, отбора и сроков участия.',fields:[['t0','Получатели поддержки: до',null],['t1','Получатели поддержки: после',null],['c0','Группа сравнения: до',null],['c1','Группа сравнения: после',null]],compute:v=>differenceInDifferences(v.t0,v.t1,v.c0,v.c1),unit:'единиц выбранного результата',block:422,invalid:'Введите четыре сопоставимых значения результата для одних и тех же групп и периодов.'}
 };
 const key=Object.hasOwn(specs,kind)?kind:'nne_structure',spec=specs[key],inputs={},out=h('div',{class:'international_export-calculation-output',role:'status','aria-live':'polite'});
 const fields=spec.fields.map(([key,label,min=0])=>{const inp=h('input',{type:'number',step:'any',value:'','aria-label':label,...(min===null?{}:{min})});inputs[key]=inp;return h('label',{class:'field'},h('span',{},label),inp);});
 function calculate(){const vals=Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,number(v.value)]));const result=Object.values(vals).every(v=>v!==null)?spec.compute(vals):null;out.replaceChildren(finite(result)?h('div',{},h('strong',{},fmt(result,4)+' '+spec.unit),spec.extra?para(spec.extra(vals,result),'small'):null,para('Условный результат по введённым значениям.','small')):para(spec.invalid));}
 Object.values(inputs).forEach(inp=>inp.addEventListener('input',calculate));calculate();
 return panel(spec.title,'Формула и условия авторской экспертизы',h('div',{class:'international_export-calculator',dataset:{calculator:key}},para(spec.description),h('div',{class:'international_export-input-grid'},fields),out,link('Формула в полном докладе',(exp(ctx).meta.html_url||BASE+'report/expertise_export_2026.html')+'#b'+spec.block),note('Введённые параметры остаются в браузере. Калькулятор не создаёт статистическое наблюдение, прогноз или подтверждённую оценку эффекта.')));
}
function causal(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Исходная группа',text:'Организации группируются по началу участия, инструменту и исходным характеристикам до поддержки.'},
 {title:'Обоснованное сравнение',text:'Сопоставляются предшествующая динамика, отрасль, размер компании и прежний экспортный опыт.'},
 {title:'Полный срок наблюдения',text:'Недавние получатели не сравниваются с полным двухлетним результатом ранних участников. Закрывшиеся компании сохраняются.'},
 {title:'Общие воздействия',text:'Отдельно учитываются мировые цены, внешний спрос, ограничения торговли и другие меры поддержки.'}
 ]),calculator(ctx,'did'),panel('Предел имеющихся свидетельств',null,para('В авторской экспертизе причинный эффект по приведённой формуле не оценён. При разновременном вступлении в программу уже получившие поддержку компании не назначаются автоматически группой сравнения для новых участников.'))));}
function population(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Рабочие места',text:'Занятость связывается с производственной площадкой, фактическим выпуском и продолжительностью экспортной программы.'},
 {title:'Оплата труда',text:'Номинальная экспортная выручка сопоставляется с занятостью, фондом оплаты труда и ценовой динамикой.'},
 {title:'Местные поставщики',text:'Закупки и кооперационные связи раскрывают распределение результата за пределами головной организации.'},
 {title:'Устойчивость предприятия',text:'Повторная поставка и сохранение рынка проверяются по полной группе организаций с одинаковым сроком наблюдения.'}
 ]),calculator(ctx,'exporter_retention'),panel('Границы территориального вывода',null,h('div',{},para('Место регистрации внешнеторговой операции не определяет, где создаётся добавленная стоимость и оплачивается труд. Региональные агрегаты дополняются сведениями о производственных подразделениях и получателях поддержки.'),link('Территориальные источники',route('regions'))))));}
function structure(ctx){return end(ctx,add(start(ctx),cards([
 {title:'Стоимость и физический объём',text:'Номинальные доллары отражают количество, цены и товарный состав. Для физической динамики требуются сопоставимые товарные группы.'},
 {title:'Концентрация рынков',text:'Товарная специализация, страны назначения и покупатели имеют разные основания распределения и разные риски.'},
 {title:'Реализация поставки',text:'Контракт, отгрузка, наступление срока оплаты и фактический платёж учитываются последовательно.'},
 {title:'Использование инфраструктуры',text:'Взвешенный охват направлений дополняется доступной мощностью, временем работы и реально обслуженными предприятиями.'}
 ]),reportFigure(ctx,3),reportFigure(ctx,7),calculator(ctx,'paid_shipments')));}
function lab(ctx){const kind=CALCULATORS.some(([k])=>k===ctx.state.calculator)?ctx.state.calculator:'nne_structure';return end(ctx,add(start(ctx),toolbar(select('Расчёт',CALCULATORS,kind,v=>ctx.set({calculator:v}))),calculator(ctx,kind),panel('Согласование входных величин',null,para('Денежные показатели имеют одинаковую валюту и ценовую основу. Группы наблюдаются одинаковый срок, а неизвестные значения остаются пустыми. Разные значения знаменателя не подменяются друг другом.'))));}

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
 const scenarios=array(ana(ctx).scenario_trajectories);
 if(scenarios.length){
  const names={'62715':'ННЭ','62717':'Промышленный экспорт','62742':'Экспорт АПК'},lines=scenarios.map((s,i)=>({name:(names[s.source_id]||s.title)+' · '+fmt(s.required_cagr_pct,2)+'% в год',points:array(s.points).map(p=>({x:Date.UTC(p.year,11,31),y:p.value})),color:C[i%C.length]}));
  add(root,panel('Равномерный рост от наблюдаемого итога к цели','Условные номинальные траектории 2025–2030 годов',h('div',{},chart(ctx,lineChart(lines,{label:'Условные траектории экспорта',unit:'млрд долл. США'}),'conditional-export-paths','Условия достижения цели',scenarios.flatMap(s=>array(s.points).map(p=>({indicator:names[s.source_id]||s.title,source_id:s.source_id,year:p.year,value:p.value,unit:s.unit,annual_growth_pct:s.required_cagr_pct,status:'Условная траектория, не прогноз'}))),'Источник: декабрьские итоги ЕМИСС за 2025 год и паспортные цели 2030 года.'),legend(lines),note('Рассчитано пять одинаковых годовых переходов от фактической базы 2025 года. Промежуточные точки этой кривой не являются ни паспортными целями, ни прогнозом; цены, валютные условия и структура поставок здесь не моделируются.'))));
 }
 add(root,reportTable(ctx,3),reportTable(ctx,9),calculator(ctx,'annual_change'),panel('Допустимость прогноза',null,methodsTable(array(ana(ctx).forecast_eligibility).map(r=>({name:r.title||r.source_id,status:r.eligible?'Пригодность требует проверки модели':'Недостаточно оснований',reason:r.reason||r.note||'Короткая история, накопление, цены и изменение методик ограничивают экстраполяцию.'})))));
 return end(ctx,root);
}
async function explorer(ctx){
 const root=start(ctx),s=selectedSource(ctx);if(!s)return end(ctx,root);
 const all=await observations(s),bases=[...new Set(all.map(observationBasis))],basis=bases.includes(ctx.state.series_basis)?ctx.state.series_basis:'all',inBasis=all.filter(r=>basis==='all'||observationBasis(r)===basis),periods=[...new Set(inBasis.map(period))].sort(),cats=[...new Set(inBasis.map(categoryKey))];
 const rows=inBasis.filter(r=>(!ctx.state.period||String(period(r))===ctx.state.period)&&(!ctx.state.category||categoryKey(r)===ctx.state.category));
 add(root,toolbar(sourcePicker(ctx,s),select('Режим статистического ряда',[['all','Все режимы отдельными записями'],...bases.map(key=>[key,basisTitle(key)])],basis,v=>ctx.set({series_basis:v,period:''})),select('Период',[['','Все периоды'],...periods.map(p=>[String(p),String(p)])],ctx.state.period||'',v=>ctx.set({period:v})),cats.length>1?select('Категория',[['','Все категории'],...cats.map(c=>[c,Object.entries(JSON.parse(c)).map(([k,v])=>k+': '+v).join(' · ')||'Без дополнительной категории'])],ctx.state.category||'',v=>ctx.set({category:v})):null));
 add(root,stats([['Записей в выборке',fmt(rows.length,0),'Частота сохранена в каждой строке'],['Числовые значения',fmt(rows.filter(r=>value(r)!==null).length,0),'Пропуски не заменяются нулями'],['Единица',s.unit||'В источнике','ЕМИСС '+sourceId(s)]]),panel('Наблюдения',null,pointsTable(rows,s)),sourceNote(s));
 if(bases.length>1)add(root,note('Годовая и месячная запись могут иметь одинаковую дату окончания, но различаться по значению и редакции. Экспорт CSV сохраняет частоту каждой выбранной строки.'));
 return end(ctx,root);
}

const DOWNLOAD_LABELS={observations:'Все наблюдения CSV',registry:'Реестр показателей CSV',comparisons:'Сопоставления с целями CSV',original_snapshot:'Исходный статистический срез',full:'Полный документальный набор',source_archive:'Сохранённые паспорта',finance:'Финансирование по годам CSV',targets:'Паспортные цели CSV',network:'Связи через общую задачу CSV',lexical:'Лексические кандидаты CSV',sources:'Исходные источники',inputs:'Входные данные',sources_index:'Реестр источников',full_documentary:'Полный документальный набор',finance_years:'Финансирование по годам',finance_sources:'Финансовые строки',text:'Текстовый анализ',code:'Код расчётов'};
function downloads(records){return(Array.isArray(records)?records.map((r,i)=>[i,r]):Object.entries(records||{})).map(([key,v])=>link(v?.label||v?.title||DOWNLOAD_LABELS[key]||String(key),typeof v==='string'?v:v?.path||v?.url));}
function library(ctx){
 const root=start(ctx),meta=exp(ctx).meta;
 add(root,panel('Авторская экспертиза',date(meta.edition_date),h('div',{class:'international_export-download-grid'},link('Полный отчёт Word',report(ctx)),link('Читаемый отчёт HTML',meta.html_url||BASE+'report/expertise_export_2026.html'),link('Полный текст Markdown',meta.markdown_url),link('Структурированное извлечение',meta.extract_url),link('Проверка полноты',meta.coverage_url))));
 add(root,stats([['Таблицы',fmt(array(exp(ctx).tables).length,0),'Исходные таблицы и CSV'],['Иллюстрации',fmt(array(exp(ctx).figures).length,0),'Файлы из авторского отчёта'],['Сноски',fmt(meta.footnotes,0),'Полные ссылки и исходные номера']]));
 const docs=array(doc(ctx).sources).map(r=>({title:r.genre==='presentation'?'Архивная презентация «Международная кооперация и экспорт»':r.title||r.document_title||r.id,kind:({np:'Национальный паспорт',fp:'Федеральный паспорт',pdf_archive:'Архивный PDF',html_passport:'Паспорт HTML'})[r.kind||r.source_kind||r.genre]||r.format||'',date:r.retrieved_at||r.snapshot_at||r.date||'',url:r.url||r.source_url,local:r.local_url||r.download_url||r.text_url,note:r.qualification||''}));
 if(docs.length)add(root,panel('Паспортные и сопутствующие источники',null,numericTable(docs,[{key:'title',label:'Документ'},{key:'kind',label:'Тип'},{key:'date',label:'Дата получения',render:date},{key:'url',label:'Публикация',render:v=>link('Источник',v)},{key:'local',label:'Сохранённый файл',render:v=>v?link('Открыть',v):'В исходном корпусе'},{key:'note',label:'Статус источника'}],'document-sources')));
 add(root,panel('Статистика и расчёты',null,h('div',{class:'international_export-download-grid'},['statistics','analytics','documentary','refresh-status','expertise'].map(name=>link(({statistics:'Статистические публикации',analytics:'Расчёты по наблюдениям',documentary:'Документальная аналитика','refresh-status':'Состояние обновления',expertise:'Структура полной экспертизы'})[name],'data/projects/international_export/'+name+'.json')),downloads(stat(ctx).downloads),downloads(doc(ctx).downloads))));
 const contextDownloads=CONTEXTS.flatMap(([key,title])=>{const packet=regionalContext(ctx,key);return[...array(packet.sources).filter(s=>s.local_file).map(s=>({label:title+' · '+s.year+' · исходный файл',url:s.local_file})),...(packet.download_csv?[{label:title+' · наблюдения CSV',url:packet.download_csv}]:[])];});
 if(contextDownloads.length)add(root,panel('Территориальные источники',null,h('div',{class:'international_export-download-grid'},contextDownloads.map(item=>link(item.label,item.url)))));
 add(root,panel('Исходные таблицы',null,h('div',{class:'international_export-download-grid'},array(exp(ctx).tables).map(t=>link(t.title,t.csv_url||t.download_url||BASE+'report/'+t.id+'.csv')))),panel('Иллюстрации',null,h('div',{class:'international_export-download-grid'},array(exp(ctx).figures).map(f=>link(f.title,f.url)))));
 add(root,panel('Повторить сборку',null,h('div',{},para('Исходные файлы и процедуры входят в накопительный комплект. Сборка использует сохранённые данные. Обращение к ЕМИСС выполняется отдельной командой.'),h('pre',{},h('code',{},'npm run build\nnpm run validate\nnpm run analytics:export\nnpm run refresh:export')),link('Код платформы','downloads/code/platform/build_export_analytics.py'))));
 return end(ctx,root);
}
function updates(ctx){
 const root=start(ctx),r=data(ctx).refresh||{},status={imported_verified_snapshot:'Импортирован проверенный срез',verified_source_snapshot:'Проверенный исходный срез',retained_verified_snapshot:'Сохранён проверенный срез',imported:'Импортирован проверенный срез',not_checked:'Новая проверка не выполнялась',not_attempted:'Новая проверка не выполнялась',failed:'Запрос не подтвердил обновление',partial:'Частичное обновление',updated:'Опубликованы проверенные данные',success:'Проверка завершена'};
 add(root,stats([['Статистический срез',date(r.statistical_as_of||stat(ctx).statistical_as_of),'Периоды наблюдений указаны в рядах'],['Последняя проверка',date(r.checked_at||r.last_checked_at),'Дата сетевого обращения, если оно выполнялось'],['Состояние',status[r.state]||r.message||r.state||'Сохранённый срез','']]));
 if(r.message)add(root,note(r.message));
 const rows=array(r.sources).map(s=>({id:sourceId(s),title:s.title||sourceName(s),state:status[s.state]||s.state||s.status||'',checked:s.checked_at||'',success:s.last_success||s.published_at||'',detail:s.message||s.error||''}));
 if(rows.length)add(root,panel('Состояние источников',null,numericTable(rows,[{key:'id',label:'ЕМИСС'},{key:'title',label:'Показатель'},{key:'state',label:'Состояние'},{key:'checked',label:'Последняя проверка',render:date},{key:'success',label:'Последние проверенные данные',render:date},{key:'detail',label:'Примечание'}],'refresh-status')));
 add(root,panel('Правила обновления',null,h('div',{},para('При неуспешном запросе сохраняются последние проверенные значения и их происхождение. Новый ответ сначала проходит проверку структуры, единицы и территориального состава. Авторский отчёт сохраняет дату своей редакции.'),link('Проверить наблюдения',route('explorer')),h('span',{},' · '),link('Состояние обновления JSON','data/projects/international_export/refresh-status.json'))));
 return end(ctx,root);
}
function methods(ctx){return end(ctx,add(start(ctx),panel('Пригодность методов','Статус, основания и ограничения',methodsTable(ctx.methods)),note('Региональные источники услуг, АПК и бюджетной поддержки имеют разные совокупности. Их доли и индексы концентрации не сопоставляются как одна шкала. Короткие ряды и смена методик ограничивают прогноз, а документальная близость не идентифицирует эффект поддержки.'),reportTable(ctx,1),reportTable(ctx,4)));}
const renderers={overview,framework,logic,audit,targets,map:ctx=>geography(ctx,false),regions:ctx=>geography(ctx,true),finance,network,texts,domains,causal,proposals,projections,population,structure,methods,lab,explorer,library,updates};
export async function renderInternationalExport(ctx){return(renderers[ctx.state.page]||overview)(ctx);}
