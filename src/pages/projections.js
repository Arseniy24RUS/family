import {h, para, select, check, note, fmt, button, download, sourceLink} from '../core/dom.js';
import {json} from '../core/data.js';
import {heading, panel, toolbar, stats, table, tabs, figure, empty, methodBox} from '../components/ui.js';
import {lineChart, legend, C} from '../components/charts.js';
import {mapView} from '../components/map.js';

const LABELS={data_21:'СКР',data_22:'СКР третьих и последующих детей'};
const dt=s=>Date.parse(s.length===7?s+'-01':s);
const points=rows=>rows.map(o=>({x:dt(o.date),y:o.value,label:o.date}));
const hasStructure=model=>model.forecast.some(o=>Number.isFinite(o.trend_value));
const localDate=s=>s?new Date(s).toLocaleDateString('ru-RU',{timeZone:'UTC'}):'—';
function chartWidth(withAside=true){
 const screen=innerWidth;
 if(screen<=760)return Math.max(250,screen-66);
 const sidebar=screen>1250?246:224,mainPad=screen>1250?64:48,panelPad=48;
 const aside=withAside&&screen>1050?(screen>1250?254:223):0;
 return Math.max(340,Math.min(1760,screen-sidebar)-mainPad-panelPad-aside);
}
function rangeSwitch(state,set){
 return h('div',{class:'range-switch','aria-label':'Горизонт просмотра'},
  button('До 2030 года',()=>set({horizon:null}),state.horizon!=='24'?'active':''),
  button('Ближайшие 24 месяца',()=>set({horizon:'24'}),state.horizon==='24'?'active':''));
}
function method(){
 return methodBox({name:'Нелинейный ансамбль: тренд, гармоника и гауссовский процесс',
  simple:'Ряд разделяется на общий ход изменения и отклонения от него. Гармоническая регрессия оценивает плавное повторяющееся отклонение. Гауссовский процесс позволяет его форме быть более гибкой и учитывать недавние изгибы. Их результаты сопоставляются с тремя простыми моделями и объединяются по ошибкам последовательной проверки.',
  formula:'log ŷ(h) = Σ wₘ · log ŷₘ(h); log ŷₘ = тренд + колебание + локальная поправка',
  why:'Для диагностического продолжения временных рядов, в которых прямой или быстро затухающий тренд недостаточно передаёт изменяющийся темп. Кривая возникает из вычисленных месячных значений, а не из графического сглаживания.',
  inputs:'Последовательные положительные месячные значения одного показателя для одной территории. Годовые и накопительные строки не добавляются как новые месячные наблюдения. При разрыве календаря или противоречивом дубле пересчёт останавливается.',
  python:'Python 3.11+ и NumPy. scripts/demography/indicator.py содержит полную реализацию; indicator_v11.py сохраняет три базовые модели. Параметры ядра, коэффициенты гармоники, веса, ошибки и хеш входа входят в скачиваемый JSON.',
  code:'python -m pip install numpy==2.3.5\npython scripts/build_indicator_forecasts.py\npython scripts/reproduce_projection.py indicator forecast.json',
  caveat:'12 месяцев — заданная календарная гипотеза, а не выявленная длина цикла. При истории 15 месяцев нельзя считать сезонность установленной. Проверки на 1 и 3 месяца не подтверждают точность до 2030 года. Условные 80/95%-полосы не откалиброваны по фактическому покрытию. Исходный прогноз экспертизы хранится отдельно.'});
}
async function trajectory(model,compare,ctx){
 const {state,set}=ctx,rid=model.region_id,sid=model.indicator_id;
 const obs=model.observations,fc=state.horizon==='24'?model.forecast.slice(0,24):model.forecast;
 const limit=fc.at(-1)?.date||obs.at(-1).date,visible=rows=>rows.filter(p=>p.date<=limit);
 const ss=[
  {name:'Наблюдения',color:'#031E4F',width:2.1,markers:true,radius:3,points:points(obs)},
  {name:'Прогноз · ансамбль',color:C[0],width:2.9,markers:false,points:points([obs.at(-1),...fc])}
 ];
 if(compare)ss.push(
  {name:compare.region_name+' · наблюдения',color:C[1],width:1.8,markers:true,points:points(visible(compare.observations))},
  {name:compare.region_name+' · прогноз',color:C[1],width:2,markers:false,dash:'5 4',points:points(visible([compare.observations.at(-1),...compare.forecast]))});
 if(state.members==='1')model.models.forEach((m,i)=>ss.push({name:m.name,color:C[(i+2)%C.length],width:1.2,markers:false,dash:'3 5',points:fc.map(p=>({x:dt(p.date),y:p.members[m.id],label:p.date}))}));
 if(state.trend==='1'&&hasStructure(model))ss.push({name:'Тренд без колебаний',color:'#647087',width:1.6,markers:false,dash:'6 5',points:fc.map(p=>({x:dt(p.date),y:p.trend_value,label:p.date}))});
 if(rid==='RU'&&state.targets!=='0'){
  const original=await json('data/forecasts.json'),code=sid==='data_21'?'2.14.Я.2':'2.14.Я.3';
  ss.push({name:'Цель нацпроекта · паспорт 2025 года',color:C[1],width:1.7,dash:'6 5',markers:true,points:original.targets.filter(p=>p.indicator_code===code&&p.target_year<=2030&&p.target_year+'-12-31'<=limit).map(p=>({x:dt(p.target_year+'-12-31'),y:p.target_value,label:String(p.target_year)}))});
 }
 if(rid==='RU'&&state.archive==='1'){
  const original=await json('data/forecasts.json'),code=sid==='data_21'?'2.14.Я.2':'2.14.Я.3';
  ss.push({name:'Прогноз исходной экспертизы',color:'#7F92BB',width:1.8,dash:'2 5',markers:false,points:original.points.filter(p=>p.indicator_code===code&&p.forecast_date<=limit).map(p=>({x:dt(p.forecast_date),y:p.forecast_ensemble_median,label:p.forecast_date}))});
 }
 const band=state.band==='none'?null:fc.map(p=>({x:dt(p.date),lo:p[state.band==='80'?'lo80':'lo95'],hi:p[state.band==='80'?'hi80':'hi95']}));
 const canvas=lineChart(ss,{width:chartWidth(),height:innerWidth<=760?300:380,unit:'детей на женщину',label:LABELS[sid]+' · '+model.region_name,band,forecastStart:dt(obs.at(-1).date),tickPlacement:'start',monthlyTicks:state.horizon==='24'});
 canvas.dataset.modelVersion=model.model_version;
 const chart=figure(canvas,{name:'forecast_'+sid+'_'+rid,title:LABELS[sid]+' · '+model.region_name,
  source:'Наблюдения до '+localDate(model.source_as_of)+'; '+model.model_version+'. '+(state.band==='none'?'Полоса скрыта.':'Условная '+(state.band==='80'?'80':'95')+'%-полоса; покрытие не валидировано.')+(rid==='RU'&&state.targets!=='0'?' Цели паспорта: архив 14.05.2026.':''),
  rows:fc.map(({members,...p})=>({...p,...members}))});
 const end=model.forecast.at(-1)||obs.at(-1);
 const names=[['','Без сравнения'],...ctx.manifest.series.filter(e=>e.indicator_id===sid&&e.file&&e.region_id!==rid).map(e=>[e.region_id,e.region_name])];
 const aside=h('aside',{class:'forecast-aside','aria-label':'Параметры и итог прогноза'},
  h('div',{class:'forecast-reading'},
   h('div',{},para('Декабрь 2030'),h('div',{class:'forecast-value'},fmt(end.value,3)),para('детей на женщину')),
   h('div',{class:'forecast-range'},h('strong',{},fmt(end.lo95,3)+'–'+fmt(end.hi95,3)),h('br'), 'Условный диапазон 95%',h('br'),h('br'),'Последний факт ('+localDate(model.source_as_of)+'): ',h('strong',{},fmt(obs.at(-1).value,3)))),
  select('Сравнение с территорией',names,state.compare||'',v=>set({compare:v})),
  select('Условная полоса',[['95','95%'],['80','80%'],['none','Без полосы']],state.band||'95',v=>set({band:v})),
  h('div',{class:'forecast-options'},
   check('Отдельные модели',state.members==='1',v=>set({members:v?'1':null})),
   hasStructure(model)?check('Тренд без колебаний',state.trend==='1',v=>set({trend:v?'1':null})):null,
   rid==='RU'?check('Целевые значения паспорта',state.targets!=='0',v=>set({targets:v?null:'0'})):null,
   rid==='RU'?check('Архивный прогноз экспертизы',state.archive==='1',v=>set({archive:v?'1':null})):null));
 const body=h('div',{},h('div',{class:'forecast-view-controls'},rangeSwitch(state,set)),legend(ss),
  h('div',{class:'forecast-workspace'},h('div',{class:'projection-chart'},chart),aside),
  h('p',{class:'forecast-note'},hasStructure(model)?'Изгибы рассчитываются по данным: гармоническая регрессия и гауссовский процесс дополняют три простые модели. Период 12 месяцев задан как гипотеза; короткая история не подтверждает устойчивую сезонность.':'Сохранён предыдущий расчёт; сведения о его модели находятся в JSON.'));
 const p=panel(LABELS[sid]+' · '+model.region_name,'Сплошная тёмная линия — наблюдения; синяя — расчёт. Вертикальная граница отделяет прогноз.',body);p.classList.add('forecast-panel');return p;
}
function structure(model,ctx){
 if(!hasStructure(model))return empty('Разложение недоступно для сохранённой модели','После успешного пересчёта новой моделью появятся тренд и рассчитанные колебания.');
 const fc=ctx.state.horizon==='24'?model.forecast.slice(0,24):model.forecast;
 const main=[{name:'Прогноз · ансамбль',color:C[0],markers:false,points:points(fc)},
  {name:'Тренд без колебаний',color:'#647087',markers:false,dash:'5 4',points:fc.map(p=>({x:dt(p.date),y:p.trend_value,label:p.date}))}];
 const components=[{name:'Календарная составляющая',color:C[1],markers:false,points:fc.map(p=>({x:dt(p.date),y:p.cycle_percent,label:p.date}))},
  {name:'Локальная поправка',color:C[2],markers:false,dash:'4 4',points:fc.map(p=>({x:dt(p.date),y:(p.local_factor-1)*100,label:p.date}))}];
 return h('div',{},h('div',{class:'forecast-view-controls'},rangeSwitch(ctx.state,ctx.set)),
  panel('Из чего складывается кривая','Разложение относится к вычислительной модели, а не к причинам изменения рождаемости.',
   h('div',{},legend(main),figure(lineChart(main,{width:chartWidth(false),height:innerWidth<=760?300:350,label:'Ансамбль и его тренд',unit:'детей на женщину',tickPlacement:'start',monthlyTicks:ctx.state.horizon==='24'}),{name:'forecast_trend',title:'Прогноз и тренд без колебаний',source:model.model_version,rows:fc.map(p=>({date:p.date,value:p.value,trend_value:p.trend_value,cycle_factor:p.cycle_factor,local_factor:p.local_factor}))}))),
  panel('Колебания относительно тренда','Процентное отклонение мультипликативных составляющих. На ровных рядах периодическое отклонение стремится к нулю.',
   h('div',{},legend(components),figure(lineChart(components,{width:chartWidth(false),height:innerWidth<=760?280:320,label:'Оценённые колебания и локальная поправка',unit:'% относительно тренда',tickPlacement:'start',monthlyTicks:ctx.state.horizon==='24',zero:true}),{name:'forecast_curvature',title:'Колебания относительно тренда',source:'Оценённые компоненты; не причинные эффекты',rows:fc.map(p=>({date:p.date,cycle_percent:p.cycle_percent,local_percent:(p.local_factor-1)*100}))}))),
  h('div',{class:'model-explainer'},
   h('article',{},h('h3',{},'Гармоническая регрессия'),para('Программа подбирает уровень, наклон и два коэффициента плавного годового колебания. Штраф на коэффициенты ограничивает подгонку под единичный всплеск. Положение и амплитуда изгибов определяются наблюдениями.'),h('div',{class:'model-equation'},'log y(t) = a + bt + c·sin(2πt/12) + d·cos(2πt/12)')),
   h('article',{},h('h3',{},'Гауссовский процесс'),para('После выделения тренда модель оценивает похожесть отклонений в близкие моменты и при одинаковой календарной фазе. Прогнозная поправка зависит от наблюдавшихся отклонений. С увеличением расстояния во времени сходство ослабевает.'),h('div',{class:'model-equation'},'Прогноз = тренд × календарный множитель × локальный множитель'))),
  note('Разделение на составляющие точно воспроизводит центральный расчёт в JSON. Наличие волны на графике не доказывает, что она повторится: проверяется гипотеза сохранения части наблюдавшейся формы.'));
}
function validation(model){
 const v=model.validation;
 const root=h('div',{});
 if(v)root.append(stats([['Проверок ансамбля',v.n_tests,'Без будущих наблюдений в весах'],['MAE ансамбля',fmt(v.mae,5),'Средняя абсолютная ошибка · ед. СКР'],['MAE сохранения уровня',fmt(v.last_value_mae,5),'На тех же проверяемых месяцах']]));
 root.append(panel('Модели и их вклад в прогноз','Веса оценены по скользящим временным проверкам на 1 и 3 месяца. Параметры каждой модели переоцениваются только на прошлом фрагменте.',
  table(model.models.map(m=>({...m,weight_percent:m.weight*100})),[
   {key:'name',label:'Модель'},{key:'n_tests',label:'Проверок',numeric:true},
   {key:'calendar_tests',label:'С календарным членом',numeric:true},
   {key:'mae',label:'MAE, ед. СКР',numeric:true,decimals:5},
   {key:'log_rmse',label:'RMSE в логарифмах',numeric:true,decimals:6},
   {key:'weight_percent',label:'Вес, %',numeric:true,decimals:2}],{pageSize:5,search:false,filename:'model_validation.csv'})),
  note('Гибкая форма не гарантирует более точный прогноз. При обучении короче 12 месяцев календарная часть отключена; столбец таблицы показывает, сколько проверок действительно проверяло её. Ошибки на 1 и 3 месяца не подтверждают качество на горизонте нескольких лет.','warning'));
 if(model.ensemble_backtest?.length)root.append(panel('Последовательная проверка всего ансамбля','Для каждого проверяемого месяца веса вычислены по ошибкам, уже известным на дату прогноза. Результаты не используют будущее для подбора весов.',
  table(model.ensemble_backtest,[{key:'train_end',label:'Конец обучения'},{key:'weight_errors_end',label:'Последняя ошибка для весов'},
   {key:'target',label:'Проверяемый месяц'},{key:'horizon',label:'Шагов',numeric:true},
   {key:'observed',label:'Наблюдение',numeric:true,decimals:5},{key:'predicted',label:'Ансамбль',numeric:true,decimals:5},
   {key:'last_value_prediction',label:'Сохранение уровня',numeric:true,decimals:5}],{filename:'ensemble_prequential_validation.csv'})));
 root.append(panel('Полный протокол отдельных моделей',null,
  table(model.backtest,[{key:'model',label:'Модель'},{key:'train_end',label:'Конец обучения'},{key:'target',label:'Проверяемый месяц'},
   {key:'horizon',label:'Горизонт',numeric:true},{key:'observed',label:'Наблюдение',numeric:true,decimals:5},{key:'predicted',label:'Расчёт',numeric:true,decimals:5}],{filename:'rolling_backtest.csv'})),
  note('В расчёте используются текущие версии исторических значений ЕМИСС. Архивные версии публикаций на каждую прошлую дату не восстановлены; возможные последующие пересмотры статистики отдельно не моделируются.'));
 return root;
}
export async function indicatorProjections(ctx){
 const {state,set,catalog}=ctx;
 const manifest=await json('data/projections/indicators/manifest.json');ctx={...ctx,manifest};
 const sid=LABELS[state.source]?state.source:'data_21',rid=state.r||'RU';
 const tab=['map','structure','validation','data'].includes(state.tab)?state.tab:'trajectory';
 const names=[['RU','Российская Федерация'],...catalog.regions.map(r=>[r.id,r.name])];
 const ent=manifest.series.find(e=>e.indicator_id===sid&&e.region_id===rid);
 const available=manifest.series.filter(e=>e.indicator_id===sid&&e.file);
 const root=h('div',{class:'projection-page forecast-page'},
  heading(state.page==='targets'?'Траектории и прогноз':'Прогнозы СКР и СКР3+','Россия и регионы до декабря 2030 года. Наблюдения, нелинейные траектории и открытый протокол расчёта.'),
  toolbar(select('Показатель',Object.entries(LABELS),sid,v=>set({source:v})),select('Территория прогноза',names,rid,v=>set({r:v}))),
  tabs([['trajectory','Траектория'],['map','Региональная карта'],['structure','Тренд и колебания'],['validation','Проверка модели'],['data','Числовые значения']],tab,v=>set({tab:v})));
 if(tab==='map'){
  const [geo,grid]=await Promise.all([json('data/map.json'),json('data/projections/indicators/maps.json')]);
  const mm=grid.values[sid]||{},dates=Object.keys(mm).sort(),month=dates.includes(state.month)?state.month:dates.at(-1);
  if(!month)root.append(empty('Нет прогнозных значений','Расчёт появится после успешной загрузки наблюдений.'));
  else{
   const values=new Map(Object.entries(mm[month]).filter(([id])=>id!=='RU').map(([id,value])=>[id,{value,detail:month}]));
   const m=mapView(geo,catalog.regions,values,{unit:'детей на женщину',selected:rid,title:LABELS[sid]+' · '+month,onSelect:r=>set({r,tab:'trajectory'})});
   root.append(toolbar(select('Месяц карты',dates.map(d=>[d,d]),month,v=>set({month:v}))),
    panel('Пространственное распределение · '+month,'Один месяц для всех территорий. Выберите регион, чтобы открыть его траекторию.',m.element),
    table(catalog.regions.map(r=>({name:r.name,value:values.get(r.id)?.value??null,id:r.id})),[{key:'name',label:'Территория'},{key:'value',label:LABELS[sid],numeric:true,decimals:4}],{filename:'projection_map_'+sid+'_'+month+'.csv',onSelect:r=>set({r:r.id,tab:'trajectory'})}));
  }
 }else if(!ent?.file){
  root.append(empty('Для выбранной территории нет расчётного ряда',ent?.message||'Нет достаточных сопоставимых наблюдений. Значения других регионов вместо них не используются.'));
 }else{
  const model=await json(ent.file),comparison=available.find(e=>e.region_id===state.compare&&e.region_id!==rid),compare=comparison?await json(comparison.file):null;
  if(ent.state==='retained')root.append(note('Показан предыдущий проверенный расчёт. Новая попытка: '+ent.message,'warning'));
  if(tab==='trajectory')root.append(await trajectory(model,compare,ctx));
  else if(tab==='structure')root.append(structure(model,ctx));
  else if(tab==='validation')root.append(validation(model));
  else{
   const rows=[...model.observations.map(o=>({...o,status:'Наблюдение'})),...model.forecast.map(o=>({...o,status:'Расчёт'}))];
   root.append(panel('Наблюдения и помесячное продолжение','Каждая прогнозная точка соответствует числу в этой таблице и скачиваемом JSON.',
    table(rows,[{key:'date',label:'Дата'},{key:'status',label:'Статус'},{key:'value',label:'Значение',numeric:true,decimals:5},
     {key:'trend_value',label:'Тренд',numeric:true,decimals:5},{key:'cycle_percent',label:'Колебание, %',numeric:true,decimals:4},
     {key:'lo95',label:'Граница 95%, нижняя',numeric:true,decimals:5},{key:'hi95',label:'Граница 95%, верхняя',numeric:true,decimals:5}],{filename:'monthly_'+sid+'_'+rid+'.csv'})));
  }
  root.append(h('div',{class:'forecast-meta'},
   h('span',{},h('strong',{},model.n_observations),' месячных наблюдений'),
   h('span',{},'Данные до ',h('strong',{},localDate(model.source_as_of))),
   h('span',{},model.source?.startsWith('data/baseline')?'Архив экспертизы':'Проверенный слой ЕМИСС'),
   h('span',{},'Пересчёт: ',localDate(model.calculated_at)),
   h('span',{},'Расчётных территорий: ',h('strong',{},available.length))),
   h('div',{class:'projection-links'},
    button('Расчёт, входы и параметры JSON',()=>download('forecast_'+sid+'_'+rid+'.json',JSON.stringify(model,null,2),'application/json'),'button primary','download'),
    sourceLink('Python: модель','./downloads/code/platform/demography/indicator.py'),
    button('Передвижка возрастов',()=>ctx.go('population',{r:rid}),'button','arrow')));
 }
 root.append(method(),h('p',{class:'forecast-result-note'},'Обновляемая модель не переписывает исходный прогноз, выводы, финансовые расчёты и текстовый анализ экспертизы от 14.05.2026.'));
 return root;
}
