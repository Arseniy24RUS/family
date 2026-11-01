import {h,svg,button,select,para,fmt,download,csvDownload,announce} from '../core/dom.js';
import {heading,panel,table,figureControls} from '../components/ui.js';
import {mapView} from '../components/map.js';
import {projectHref} from '../platform/projects.js';
import {normalizeTourismRows,tourismPeriods,tourismSlice,tourismTrajectories,tourismQuality,shortRegionName,buildTourismExport,TOURISM_RESEARCH_VERSION} from '../core/tourism-research.js';

const MONTHS=['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
const COLORS=['#166463','#a44d15','#334f87','#80549a','#7b6919'];
const P='tourism',SOURCE='https://www.fedstat.ru/indicator/62900';
const a=(label,href,cls='text-link')=>h('a',{href,class:cls,...(/^https?:/.test(href)?{target:'_blank',rel:'noopener noreferrer'}:{})},label);
const periodLabel=p=>{const m=Number(String(p).slice(5,7));return (m===1?'Январь':'Январь–'+['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь'][m-1])+' '+String(p).slice(0,4);};
const dateLabel=d=>String(d||'').slice(0,10).split('-').reverse().join('.');
const historyLabel=packet=>{const periods=[...new Set(packet.observations.map(r=>r.period_end||packet.observation_defaults.period_end))].sort();return [...new Set(periods.map(p=>p.slice(0,4)))].map(year=>periodLabel(periods.filter(p=>p.startsWith(year)).at(-1))).join(', ');};
const safeRegions=state=>[...new Set(String(Object.hasOwn(state,'regions')?state.regions:Object.hasOwn(state,'region')?state.region:'77,23').split(',').filter(x=>/^\d{2}$/.test(x)))].slice(0,5);
const small=()=>matchMedia('(max-width:600px)').matches;
const mobileChartWidth=()=>Math.max(260,document.documentElement.clientWidth-66);
const metric=(label,value,detail)=>h('div',{class:'v3-metric'},h('span',{},label),h('strong',{},value),h('small',{},detail));
const frame=(width,height,title,desc)=>svg('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':title,style:'font-family:Roboto,Arial,sans-serif;max-width:100%;height:auto;display:block'},svg('title',{},title),svg('desc',{},desc));
const txt=(x,y,text,extra={})=>svg('text',{x,y,fill:'#33444a','font-size':12,...extra},text);
const line=(x1,y1,x2,y2,extra={})=>svg('line',{x1,y1,x2,y2,stroke:'#dce5e5','stroke-width':1,...extra});
function path(points,x,y){let d='',pen=false;for(const p of points){if(p.value===null){pen=false;continue;}d+=(pen?'L':'M')+x(p)+' '+y(p)+' ';pen=true;}return d;}

/** Bespoke SVG keeps the 21 cumulative observations visible without a chart runtime. */
function trajectoryChart(series,{title='Накопительные траектории',compact=false}={}){
 const mobile=small(),W=mobile?mobileChartWidth():780,H=compact?250:mobile?285:320,L=mobile?45:48,R=mobile?63:100,T=25,B=45;
 const values=series.flatMap(s=>s.points.map(p=>p.value)).filter(Number.isFinite),max=Math.max(...values,0.001),power=10**Math.floor(Math.log10(max/4)),step=([1,2,2.5,5,10].find(v=>v>=max/4/power)||10)*power,top=Math.ceil(max/step)*step;
 const x=p=>L+(p.month-1)*(W-L-R)/11,y=p=>H-B-(p.value/top)*(H-T-B),digits=Math.min(6,Math.max(0,Math.ceil(-Math.log10(step))+((step/power)===2.5?1:0)));
 const root=frame(W,H,title,'По горизонтали календарные месяцы, по вертикали накопленное количество поездок, млн. Разрывы означают отсутствие допустимых наблюдений.');
 for(let i=0;i<=Math.round(top/step);i++){const value=step*i,py=y({value});root.append(line(L,py,W-R+6,py),txt(L-9,py+4,fmt(value,digits),{'text-anchor':'end'}));}
 for(let m=1;m<=12;m++)if(!mobile||m%2===1||m===12)root.append(txt(x({month:m}),H-20,MONTHS[m-1],{'text-anchor':'middle','font-size':mobile?11:12}));
 root.append(txt(L,13,'млн поездок',{'font-size':11}));
 series.forEach((s,index)=>{
  const color=s.color||COLORS[index%COLORS.length],valid=s.points.filter(p=>p.value!==null),last=valid.at(-1);
  root.append(svg('path',{d:path(s.points,x,y),fill:'none',stroke:color,'stroke-width':2.8,'stroke-dasharray':s.dash||null,'stroke-linejoin':'round','stroke-linecap':'round'}));
  valid.forEach(p=>root.append(svg('circle',{cx:x(p),cy:y(p),r:3.2,fill:color},svg('title',{},`${s.label||s.year} · ${MONTHS[p.month-1]}: ${fmt(p.value,5)} млн поездок`))));
  if(last)root.append(txt(x(last)+9,y(last)-6,`${s.year}`,{fill:color,'font-weight':700}),txt(x(last)+9,y(last)+10,fmt(last.value,max<.1?4:max<1?3:2),{fill:color,'font-size':11}));
 });
 root.dataset.exportLegend=JSON.stringify(series.map((s,i)=>({name:s.label||String(s.year),color:s.color||COLORS[i%COLORS.length],dash:s.dash||''})));
 return root;
}

function rankChart(slice,selected=[],onSelect=null,limit=10){
 const mobile=small(),W=mobile?mobileChartWidth():620,L=mobile?140:205,R=52,T=15,ROW=32,rows=slice.ranked.slice(0,limit),H=rows.length*ROW+34,max=rows[0]?.value||1;
 const root=frame(W,H,'Крупнейшие направления поездок',`${slice.periodLabel}. Объём в миллионах поездок. Полные названия и исходные значения доступны в таблице.`);
 if(onSelect)root.setAttribute('role','group');
 rows.forEach((r,i)=>{
  const yy=T+i*ROW,chosen=selected.includes(r.regionId),width=(W-L-R)*r.value/max,color=chosen?'#115e5b':'#569795';
  const name=r.shortName.replace(' область',' обл.').replace('Республика ','Респ. ');
  const group=svg('g',onSelect?{tabindex:0,role:'button','aria-pressed':chosen,'aria-label':`${r.shortName}: ${fmt(r.value,4)} млн. Выбрать территорию`,onClick:()=>onSelect(r.regionId),onKeydown:e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(r.regionId);}}}:{});
  group.append(svg('title',{},r.name),txt(L-9,yy+16,name,{'text-anchor':'end','font-size':mobile?10.8:12,'font-weight':chosen?700:400}),svg('rect',{x:L,y:yy+3,width:W-L-R,height:19,fill:'#eef3f2',rx:2}),svg('rect',{x:L,y:yy+3,width,height:19,fill:color,rx:2,stroke:chosen?'#123f3d':'none','stroke-width':chosen?2:0}),txt(L+width+7,yy+17,fmt(r.value,2),{'font-size':12,'font-weight':600}));
  root.append(group);
 });
 root.append(txt(L,H-2,'млн поездок',{'font-size':11}));return root;
}

function concentrationChart(slice){
 const W=small()?mobileChartWidth():470,H=310,L=43,R=20,T=39,B=43,x=k=>L+k/slice.ranked.length*(W-L-R),y=v=>H-B-v/100*(H-T-B);
 const root=frame(W,H,'Концентрация туристических поездок',`${slice.periodLabel}. Территории упорядочены по убыванию объёма. Доля первых пяти ${fmt(slice.top5Share,2)}%, первых десяти ${fmt(slice.top10Share,2)}% от суммы регионов.`);
 [0,25,50,75,100].forEach(v=>root.append(line(L,y(v),W-R,y(v)),txt(L-7,y(v)+4,v+'%',{'text-anchor':'end','font-size':11})));
 [0,20,40,60,slice.ranked.length].forEach(k=>root.append(txt(x(k),H-24,k,{'text-anchor':'middle','font-size':11})));
 root.append(svg('path',{d:'M'+x(0)+' '+y(0)+' '+slice.concentration.slice(1).map(p=>'L'+x(p.k)+' '+y(p.cumulativeSharePct)).join(' '),fill:'none',stroke:'#166463','stroke-width':3}),line(x(0),y(0),x(slice.ranked.length),y(100),{stroke:'#919fa3','stroke-dasharray':'4 4'}));
 for(const k of [5,10]){const point=slice.concentration.find(p=>p.k===k);if(point)root.append(svg('circle',{cx:x(k),cy:y(point.cumulativeSharePct),r:4,fill:'#166463'}));}
 root.append(txt(L,17,`5 территорий: ${fmt(slice.top5Share,1)}%`,{'font-weight':700,fill:'#166463'}),txt(W-R,17,`10: ${fmt(slice.top10Share,1)}%`,{'text-anchor':'end','font-weight':700,fill:'#166463'}),txt(W/2,H-4,'Число ведущих территорий',{'text-anchor':'middle','font-size':11}));return root;
}

function sourceCaption(packet,period,extra=''){
 return `ЕМИСС 62900. ${periodLabel(period)}; млн поездок, накопленным итогом. Срез получен ${dateLabel(packet.statistical_as_of)}. Доли от суммы наблюдаемых регионов. Межгодовое сопоставление описательное: редакции требуют сверки. Данные ${packet.source_sha256?.slice(0,12)}; код ${TOURISM_RESEARCH_VERSION}. ${extra}`;
}
function chartBlock(node,{name,title,packet,period,extra=''}){
 return h('div',{class:'v3-figure'},node,h('div',{class:'v3-figure-footer'},h('span',{},'ЕМИСС 62900 · млн поездок'),figureControls(node,{name,title,source:name.includes('cumulative')||name.includes('region-')?`ЕМИСС 62900. Накопительные траектории: ${historyLabel(packet)}. Млн поездок. Получено ${dateLabel(packet.statistical_as_of)}. Сравнение редакций описательное, сопоставимость требует проверки. Данные ${packet.source_sha256?.slice(0,12)}; код ${TOURISM_RESEARCH_VERSION}. ${extra}`:sourceCaption(packet,period,extra)})));
}
function stateLink(ctx,page,patch={}){
 const state={period:ctx.state.period,region:ctx.state.region,regions:ctx.state.regions,edition:ctx.tourism.snapshot_id,...patch};
 return projectHref(P,page,Object.fromEntries(Object.entries(state).filter(([,v])=>v)));
}
export function researchNav(ctx){return h('nav',{class:'v3-research-nav','aria-label':'Исследование туризма'},[['overview','Обзор'],['map','Территории'],['regions','Сравнение'],['causal','Оценка воздействия']].map(([p,label])=>{const link=a(label,stateLink(ctx,p),ctx.state.page===p?'active':'');if(ctx.state.page===p)link.setAttribute('aria-current','page');return link;}));}

function exportControls(ctx,rows,period,regions,view='overview'){
 const state={period,regions:regions.length?regions.join(','):'none',region:ctx.state.region||regions[0]||'',view,edition:ctx.tourism.snapshot_id};
 const share=async()=>{const url=new URL(location.href);url.hash=projectHref(P,ctx.state.page,state);try{await navigator.clipboard.writeText(url.href);announce('Ссылка на срез, территории и редакцию скопирована.');}catch{let field=controls.querySelector('input');if(!field){field=h('input',{type:'url',readonly:true,'aria-label':'Ссылка на исследование для копирования',class:'v3-share-field'});controls.append(field);}field.value=url.href;field.focus();field.select();announce('Готовая ссылка выделена для копирования.');}};
 const save=()=>download(`tourism-research-${period}.json`,JSON.stringify(buildTourismExport(rows,{period,regions,view:ctx.state.page+'/'+view,sourceHash:ctx.tourism.source_sha256}),null,2),'application/json;charset=utf-8');
 const controls=h('div',{class:'v3-actions'},button('Ссылка на исследование',share,'button subtle','link'),button('Скачать исследование',save,'button primary','download'));return controls;
}
function sliceCSV(slice,packet){return slice.ranked.map(r=>({territory:r.name,region_id:r.regionId,period_start:r.period_start,period_end:r.periodEnd,value:r.value,unit:'млн поездок',temporal_type:'cumulative_ytd',share_of_observed_regions_pct:r.sharePct,rank:r.rank,regional_sum:slice.total,national_value:slice.nationalValue,national_minus_regions:slice.residual,source_id:'62900',source_cell:r.source_cell_attributes?.source_cell||'',source_url:SOURCE,snapshot_id:packet.snapshot_id,source_sha256:packet.source_sha256,comparison_status:'requires_edition_review',code_version:TOURISM_RESEARCH_VERSION}));}
function regionTable(slice,packet,choose,selected=[]){
 const values=sliceCSV(slice,packet);
 const result=table(values,[{key:'rank',label:'Место',numeric:true,decimals:0},{key:'territory',label:'Территория',render:(v,r)=>button((selected.includes(r.region_id)?'✓ ':'')+shortRegionName(v),()=>choose(r.region_id),'v3-table-link')},{key:'value',label:'Млн поездок',numeric:true,decimals:4},{key:'share_of_observed_regions_pct',label:'Доля, %',numeric:true,decimals:2},{key:'source_cell',label:'Ячейка источника'}],{pageSize:15,caption:'Территории, '+slice.periodLabel,filename:'tourism-regions-'+slice.period+'.csv'});
 // The visible table's CSV keeps every provenance field, including the exact period.
 result.querySelector('.toolbar .button')?.remove();result.querySelector('.toolbar')?.append(button('CSV всего среза',()=>csvDownload('tourism-regions-'+slice.period+'.csv',values),'button subtle','download'));
 return result;
}
function inspector(ctx,rows,slice){
 const packet=ctx.tourism,quality=tourismQuality(rows),root=h('details',{class:'v3-inspector',id:'tourism-source-inspector',open:ctx.state.inspector==='quality'},h('summary',{},'Источник, определения и проверка данных',h('span',{class:'v3-inspector-summary'},`${quality.mismatchCount} расхождений · ${packet.exclusions.length} исключений в корпусе`)));
 const meta=h('dl',{class:'v3-definition-grid'},h('dt',{},'Показатель'),h('dd',{},a(packet.title,SOURCE)),h('dt',{},'Смысл значения'),h('dd',{},'Количество поездок по территории назначения, накопленным итогом с начала года. Повторные поездки одного человека учитываются отдельно.'),h('dt',{},'Время и единица'),h('dd',{},'Миллионы поездок. '+historyLabel(packet)+'. Граница года разрывает накопление.'),h('dt',{},'Редакция массива'),h('dd',{},'Получен '+dateLabel(packet.statistical_as_of)+'. Дата получения массива не устанавливает дату публикации или уточнения отдельной ячейки.'),h('dt',{},'Сопоставимость'),h('dd',{},packet.methodology_review.note,' ',a('Перечень методик Росстата',packet.methodology_review.url)),h('dt',{},'Знаменатель долей'),h('dd',{},'Сумма 85 опубликованных региональных значений выбранного среза. Итог РФ и остаток сверки хранятся отдельно.'),h('dt',{},'SHA-256 источника'),h('dd',{},h('code',{},packet.source_sha256)));
 const checks=quality.periods.map(r=>({period:r.periodLabel,n:r.regions,sum:r.regionalSum,national:r.nationalValue,residual:r.residual,status:r.status==='matched'?'Совпадает в пределах допуска':r.status==='mismatch'?'Есть расхождение':'Неполное покрытие'}));
 const exc=packet.exclusions.map(r=>({source:r.source_id,title:r.source_title,period:r.period,value:r.value,cell:r.source_cell_attributes?.source_cell,reason:r.quality_flags.filter(f=>f.exclude_from_analysis).map(f=>f.message).join(' ')}));
 root.append(h('div',{class:'v3-inspector-body'},meta,h('h3',{},'Сверка суммы регионов с опубликованным итогом РФ'),para(`${quality.matchingCount} из ${quality.periods.length} дат совпадают в пределах допуска 0,000001 млн поездок (одна поездка). Для ${quality.mismatchCount} дат причина расхождения не установлена. Остаток определён как РФ минус сумма регионов и не распределяется между территориями.`),table(checks,[{key:'period',label:'Накопленный период'},{key:'n',label:'Территории',numeric:true,decimals:0},{key:'sum',label:'Сумма регионов, млн',numeric:true,decimals:5},{key:'national',label:'РФ, млн',numeric:true,decimals:5},{key:'residual',label:'РФ − регионы, млн',numeric:true,decimals:5},{key:'status',label:'Проверка'}],{pageSize:21,search:false,filename:'tourism-reconciliation.csv'}),h('h3',{},'Исключения в остальных показателях туризма'),para('В ряду поездок 62900 исключённых записей нет. Ниже сохранены исходные нули других показателей, статус которых требует проверки. В аналитике они представлены пропуском.'),table(exc,[{key:'source',label:'ЕМИСС'},{key:'title',label:'Показатель'},{key:'period',label:'Период'},{key:'value',label:'Исходное значение',numeric:true,decimals:0},{key:'cell',label:'Ячейка'},{key:'reason',label:'Причина исключения'}],{pageSize:14,search:false,filename:'tourism-exclusions.csv'}),h('div',{class:'v3-actions'},button('Исходный ряд с ячейками',async()=>{try{const response=await fetch('./'+packet.source_path);if(!response.ok)throw Error('HTTP '+response.status);download('tourism-source-62900.json',await response.text(),'application/json;charset=utf-8');}catch(error){announce('Исходный файл не получен: '+error.message);}},'button subtle'),a('Код вычислений','downloads/code/frontend/core/tourism-research.js','button subtle'),a('Проверка сохранённого исследования','downloads/code/platform/reproduce_tourism_research.py','button subtle'))));
 return root;
}

function qualityStrip(ctx,rows,slice){
 const q=tourismQuality(rows),open=()=>{const d=document.getElementById('tourism-source-inspector');d.open=true;d.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth',block:'start'});d.querySelector('summary').focus();};
 return h('div',{class:'v3-quality-strip'},h('div',{},h('strong',{},`${q.mismatchCount} из ${q.periods.length} срезов требуют сверки итогов`),para('Исходные расхождения сохранены. Сравнение лет требует проверки редакций.')),button('Проверить данные',open,'button subtle'));
}
function contextWarning(ctx,slice){
 const messages=[];
 if(ctx.state.edition&&ctx.state.edition!==ctx.tourism.snapshot_id)messages.push('Ссылка относится к иной редакции данных. Показан текущий сохранённый массив от '+dateLabel(ctx.tourism.statistical_as_of)+'. Для восстановления прежнего результата используйте сохранённый JSON исследования.');
 if(!slice.available)messages.push('Период '+String(ctx.state.period)+' отсутствует в сохранённых данных. Выберите доступный период. Автоматическая замена не выполнялась.');
 if(slice.available&&slice.reconciliation.status!=='matched')messages.push('В выбранном срезе итог РФ отличается от суммы регионов. Остаток РФ − регионы: '+fmt(slice.residual,5)+' млн поездок. Причина не установлена.');
 return messages.length?h('div',{class:'v3-warning',role:'status'},messages.map(t=>para(t))):null;
}
function common(ctx){
 const packet=ctx.tourism,rows=normalizeTourismRows(packet),periods=tourismPeriods(rows),period=ctx.state.period|| (periods.filter(p=>p.endsWith('-12-31')).at(-1)||periods.at(-1)),slice=tourismSlice(rows,period);
 const root=h('div',{class:'tourism-page tourism-v3',dataset:{tourismPage:ctx.state.page,routeState:JSON.stringify(ctx.state),dataVersion:packet.snapshot_id}},heading(ctx.state.page==='overview'?'Туризм и гостеприимство':'География туристических поездок',ctx.state.page==='overview'?'Накопительные траектории, территориальные различия и качество опубликованных оценок.':'Один период для карты, ранжировки, таблицы и выбранных территорий.'),researchNav(ctx));
 const options=[...periods].reverse().map(p=>[p,periodLabel(p)]);if(!slice.available)options.unshift([period,'Нет данных: '+period]);
 root.append(h('div',{class:'v3-controls'},select('Период с начала года',options,period,v=>ctx.set({period:v,edition:packet.snapshot_id})),h('div',{class:'v3-data-stamp'},h('span',{class:'v3-eyebrow'},'Срез ЕМИСС · '+dateLabel(packet.statistical_as_of)),h('span',{},'Поездки, накопленным итогом · '+packet.coverage.regions+' территорий'))));
 const warning=contextWarning(ctx,slice);if(warning)root.append(warning);
 return {packet,rows,period,slice,root};
}

export function tourismOverviewV3(ctx){
 const {packet,rows,period,slice,root}=common(ctx);if(!slice.available)return root;
 root.querySelector('.lede').textContent=`В срезе «${slice.periodLabel.toLocaleLowerCase('ru')}» пять территорий дают ${fmt(slice.top5Share,1)}% поездок по сумме регионов.`;
 const series=tourismTrajectories(rows,'RU'),latest=series.at(-1),latestPoint=latest.points.filter(p=>p.value!==null).at(-1),prior=series.at(-2)?.points.find(p=>p.month===latestPoint.month&&p.value!==null);
 const hero=panel('Как формируется годовой объём','Россия · накопительный итог · сопоставимость редакций требует проверки',chartBlock(trajectoryChart(series),{name:'tourism-cumulative-russia',title:'Туристические поездки в России: накопительные траектории',packet,period,extra:'Годы показаны по календарным месяцам. 2026 год заканчивается последним опубликованным месяцем. Выбранный территориальный срез: '+slice.periodLabel}));hero.classList.add('v3-main-chart');
 const summary=h('aside',{class:'v3-summary','aria-label':'Вывод выбранного среза'},h('span',{class:'v3-eyebrow'},slice.periodLabel),h('h2',{},'Пять территорий'),h('div',{class:'v3-key-number'},fmt(slice.top5Share,1),h('span',{},'%')),para('опубликованного объёма поездок по сумме регионов.'),h('div',{class:'v3-summary-divider'}),metric('Российская Федерация',fmt(slice.nationalValue,2)+' млн','накопленная оценка выбранного периода'),metric('Первые десять территорий',fmt(slice.top10Share,1)+'%','доля в сумме регионов'),a('Исследовать территории',stateLink(ctx,'map',{period}),'button primary'));
 root.append(h('div',{class:'v3-overview-hero'},hero,summary));
 if(prior)root.append(h('div',{class:'v3-comparison-note'},h('strong',{},periodLabel(latestPoint.periodEnd)+': '+fmt(latestPoint.value,2)+' млн'),h('span',{},'В те же месяцы '+prior.year+' года опубликовано '+fmt(prior.value,2)+' млн. Разность '+fmt(latestPoint.value-prior.value,2)+' млн описывает публикации. Сопоставимость редакций пока не подтверждена.')));
 const top=panel('Крупнейшие направления',slice.periodLabel,chartBlock(rankChart(slice,[],id=>{location.hash=stateLink(ctx,'map',{period,region:id,regions:id});}),{name:'tourism-top10-'+period,title:'Крупнейшие направления туристических поездок · '+slice.periodLabel,packet,period}));
 const conc=panel('Насколько концентрируются поездки',slice.periodLabel,h('div',{},chartBlock(concentrationChart(slice),{name:'tourism-concentration-'+period,title:'Концентрация туристических поездок · '+slice.periodLabel,packet,period}),para('Территории упорядочены от большего объёма к меньшему. Пунктир показывает равные доли. Концентрация описывает поездки по месту назначения.','v3-caption')));
 root.append(h('div',{class:'v3-support-grid'},top,conc),qualityStrip(ctx,rows,slice),inspector(ctx,rows,slice),exportControls(ctx,rows,period,[]),h('div',{class:'v3-next-research'},h('h2',{},'Продолжить исследование'),a('Сравнить несколько территорий',stateLink(ctx,'regions',{period})),a('Протокол оценки поддержки модульных гостиниц',stateLink(ctx,'causal')),a('Цели и другие показатели проекта',projectHref(P,'targets'))),h('div',{'data-report-slot':'true'}));
 return root;
}

export function tourismTerritoriesV3(ctx){
 const {packet,rows,period,slice,root}=common(ctx);if(!slice.available)return root;
 const allIds=new Set(slice.regions.map(r=>r.regionId)),requested=safeRegions(ctx.state),selected=requested.filter(id=>allIds.has(id)),missing=requested.filter(id=>!allIds.has(id));
 const focused=ctx.state.region?(allIds.has(ctx.state.region)?ctx.state.region:null):selected[0]||null;
 const choose=id=>{if(!id)return;if(!selected.includes(id)&&selected.length>=5){announce('Выбрано пять территорий. Удалите одну из сравнения, чтобы добавить другую.');ctx.set({regions:selected.join(','),region:focused||''});return;}const ids=selected.includes(id)?selected:[...selected,id];ctx.set({region:id,regions:ids.join(','),period,edition:packet.snapshot_id});};
 if(missing.length)root.append(h('div',{class:'v3-warning',role:'status'},'В выбранном срезе нет допустимых значений территорий '+missing.join(', ')+'. Они не заменены другими регионами.'));
 root.append(h('div',{class:'v3-territory-controls'},select('Территория',[['','Выбрать для сравнения…'],...slice.ranked.map(r=>[r.regionId,r.shortName]).sort((a,b)=>a[1].localeCompare(b[1],'ru'))],focused||'',choose),h('div',{class:'v3-selected',role:'group','aria-label':'Территории для сравнения'},selected.map((id,i)=>{const r=slice.regions.find(r=>r.regionId===id);return button(r.shortName+' ×',()=>ctx.set({regions:selected.filter(x=>x!==id).join(',')||'none',region:focused===id?'':focused,period}),'v3-chip');}),h('span',{class:'v3-caption'},'До пяти территорий · выбор связан с картой и таблицей'))));
 const view=['map','tiles','table','ranking'].includes(ctx.state.view)?ctx.state.view:(ctx.state.page==='map'?'map':'ranking');
 root.append(h('div',{class:'v3-view-controls'},h('div',{class:'v3-segmented',role:'group','aria-label':'Представление территорий'},[['ranking','Ранжировка'],['map','Карта'],['tiles','Плитки'],['table','Таблица']].map(([v,label])=>h('button',{type:'button',class:view===v?'active':'','aria-pressed':view===v,'data-focus-key':'view-'+v,onClick:()=>ctx.set({view:v,period,regions:requested.join(',')||'none',edition:packet.snapshot_id})},label))),h('span',{class:'v3-caption'},slice.periodLabel+' · '+slice.regions.length+' территорий')));
 if(view==='table')root.append(panel('Все территории выбранного среза','Точные значения, доли и ячейки первичного файла',regionTable(slice,packet,choose,selected)));
 else if((view==='map'||view==='tiles')&&ctx.geo){
  const values=new Map(slice.regions.map(r=>[r.regionId,{value:r.value,detail:slice.periodLabel+' · '+fmt(slice.ranked.find(x=>x.regionId===r.regionId).sharePct,2)+'% суммы регионов'}]));
  const map=mapView(ctx.geo,ctx.catalog.regions,values,{unit:'млн поездок',tile:view==='tiles',tileFormat:v=>fmt(v,v<.1?3:2),selected:focused,selectedRegions:selected,title:'Туристические поездки · '+slice.periodLabel,onSelect:choose,domain:[0,Math.max(...slice.regions.map(r=>r.value))]});
  map.svg.setAttribute('role','group');
  root.append(panel('Туристические поездки по территориям','Абсолютный объём · общий период и линейная шкала от нуля',h('div',{},map.element,h('div',{class:'v3-figure-footer'},para('Площадь региона не определяет объём поездок. Для точного сравнения используйте ранжировку или таблицу.','v3-caption'),figureControls(map.svg,{name:'tourism-map-'+period,title:'Туристические поездки · '+slice.periodLabel,source:sourceCaption(packet,period)})))));
 }else root.append(panel('Распределение поездок','Первые 15 территорий · нажмите на территорию для сравнения',chartBlock(rankChart(slice,selected,choose,15),{name:'tourism-rank-'+period,title:'Территории по объёму поездок · '+slice.periodLabel,packet,period})));
 const row=slice.ranked.find(r=>r.regionId===focused);
 if(row){const profile=panel('Профиль территории',row.name,h('div',{class:'v3-profile'},h('h3',{},row.shortName),h('div',{class:'v3-profile-metrics'},metric('Поездки',fmt(row.value,4)+' млн',slice.periodLabel),metric('Доля в сумме регионов',fmt(row.sharePct,2)+'%','Знаменатель '+fmt(slice.total,4)+' млн'),metric('Место по объёму',row.rank+' из '+slice.regions.length,'В выбранном срезе')),a('Наблюдения территории',projectHref(P,'explorer',{source:'62900',region:row.regionId})),h('details',{class:'v3-row-source'},h('summary',{},'Исходная строка и ячейка'),h('pre',{},JSON.stringify(row.source_row,null,2)))));root.append(profile);}
 const cards=selected.map((id,index)=>{const r=slice.ranked.find(r=>r.regionId===id),series=tourismTrajectories(rows,id).map((s,j)=>({...s,color:j===0?'#166463':'#a44d15'}));return panel(r.shortName,`${fmt(r.value,4)} млн · ${fmt(r.sharePct,2)}% среза`,chartBlock(trajectoryChart(series,{title:r.shortName+' · накопительные поездки',compact:true}),{name:'tourism-region-'+id,title:r.shortName+' · накопительные траектории',packet,period,extra:'Панель имеет собственную шкалу. Уровни между панелями сравниваются по подписям значений.'}));});
 if(cards.length)root.append(h('section',{class:'v3-comparison-section'},h('h2',{},'История выбранных территорий'),para('Каждый график совмещает календарные месяцы разных лет. Шкалы отдельных территорий различаются, значения подписаны. Сравнение редакций остаётся описательным.','v3-caption'),h('div',{class:'v3-profile-grid'},cards)));
 root.append(qualityStrip(ctx,rows,slice),inspector(ctx,rows,slice),exportControls(ctx,rows,period,requested,view),h('div',{class:'v3-next-research'},a('Полная экспертиза и источники',projectHref(P,'library')),a('Цели и другие показатели',projectHref(P,'targets'))));return root;
}
