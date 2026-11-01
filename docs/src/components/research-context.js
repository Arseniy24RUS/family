import {h,select,para,fmt} from '../core/dom.js';
import {heading} from './ui.js';
import {ALL_RESEARCH_REGIONS,describePeriod,periodContextParams} from '../core/research-context.js';
import {projectHref} from '../platform/projects.js';

function focusField(field,key) {
  field.querySelector('select').dataset.focusKey = key;
  return field;
}

export function researchContextPanel(model,set) {
  const sourceUnit = model.source?.unit || '';
  const displayUnit = ['процент','процентов','Процент'].includes(sourceUnit) ? '%' : sourceUnit;
  const regions = [['','Все регионы'],...model.regions.map(region=>[String(region.id),region.name])];
  if (model.unknownRegion) regions.splice(1,0,[model.region,'Территория '+model.region+' · нет в каталоге']);
  const regionControl = focusField(select('Территория исследования',regions,model.region,value=>{
    const comparison = String(model.state.regions || '').split(',').filter(id=>/^\d{2}$/.test(id));
    if (value && !comparison.includes(value)) {if (comparison.length === 5) comparison.pop();comparison.push(value);}
    set({ctx_region:value || ALL_RESEARCH_REGIONS,[model.projectId === 'tourism' ? 'region' : 'r']:value || null,
      ...(model.projectId === 'tourism' ? {regions:value ? comparison.join(',') : 'none'} : {}),compare:null,fd:null});
  }),'research-context-region');
  const options = model.periods.slice().reverse().map(period=>[period.nativeKey,describePeriod(period)+(period.category ? ' · '+period.category : '')]);
  if (!model.selected) options.unshift(['',model.applied ? 'Выберите доступный период' : 'Период применяется на карте']);
  const periodControl = focusField(select('Доступный период исследования',options,model.selected?.nativeKey || '',nativeKey=>{
    const period = model.periods.find(item=>item.nativeKey === nativeKey);
    if (period) set({...periodContextParams(period),period:nativeKey,fd:null});
  }),'research-context-period');
  if (!model.applied) periodControl.querySelector('select').disabled = true;
  const requested = model.request.invalidPeriod ? 'Период в ссылке указан некорректно.' : model.request.period
    ? describePeriod(model.request.period) : model.resolution?.nativeRequest
      ? 'Период из ссылки: '+model.resolution.nativeRequest : 'Период пока не выбран.';
  let status;
  if (model.unknownRegion) status = 'Территория не найдена в каталоге. Выберите её в списке; исходный запрос сохранён.';
  else if (model.blocked) status = model.resolution.status === 'invalid'
    ? 'Укажите доступный период. Даты и вид наблюдения должны соответствовать источнику.'
    : 'В выбранном источнике нет наблюдения за этот период с таким же временным смыслом. Выберите один из доступных периодов.';
  else if (!model.applied) status = 'Выбор сохранён для перехода между проектами.';
  else if (model.region && !model.regionAvailable) status = 'Для выбранной территории нет пригодного значения за этот период. Это отсутствие данных, а не нулевое значение.';
  else if (model.region) status = model.territory.name+': '+fmt(model.regionValue,4)+' '+displayUnit+'.';
  else status = 'Показаны регионы с наблюдениями выбранного периода. Отсутствующие и исключённые значения отмечены отдельно.';
  return h('section',{
    class:'research-context','aria-label':'Общий выбор территории и периода',
    dataset:{contextStatus:model.status,contextProject:model.projectId,contextApplied:String(model.applied)}
  },
  h('div',{class:'research-context-heading'},h('h2',{},'Территория и период исследования'),
    model.source ? para(model.source.title,'research-context-source') : null),
  h('div',{class:'research-context-fields'},regionControl,periodControl),
  para('Запрошенный период: '+requested,'research-context-request'),
  para(status,'research-context-status'),
  model.projectId === 'tourism' && String(model.state.regions || '').split(',').length === 5
    ? para('В сравнении пять территорий. Выбор ещё одной в общей панели заменит пятую; первые четыре и их порядок сохранятся.','research-context-scope') : null,
  model.comparisonAdjusted ? para('Для выбранной территории сохранены первые четыре позиции сравнения; пятая заменена.','research-context-scope') : null,
  model.applied ? para(model.scope,'research-context-scope') : h('div',{class:'research-context-scope'},para(model.scope),
    model.supported ? h('a',{href:projectHref(model.projectId,'map',model.state),class:'text-link'},'Открыть карту с выбранным периодом') : null)
  );
}

export function researchContextEmpty(model,set) {
  const invalid = model.resolution?.status === 'invalid';
  const root = h('div',{class:'research-context-empty','aria-label':'Недоступный период исследования'},
    heading(invalid ? 'Период указан некорректно' : 'За выбранный период данных нет',
      'Запрос сохранён. Карта и таблица появятся после выбора периода, опубликованного для этого показателя.'),
    para('Годовые значения, месячные наблюдения, накопление с начала года и состояние на дату сохраняют свой смысл. Совпадение конечной даты само по себе не позволяет заменить одно наблюдение другим.')
  );
  if (model.sources.length) root.append(focusField(select('Показатель для выбранного периода',
    model.sources.map(source=>[String(source.id),source.short_title || source.label || source.title]),String(model.source.id),
    value=>set({source:value,period:null})),'research-context-source'));
  if (model.source?.source_url) root.append(h('a',{href:model.source.source_url,target:'_blank',rel:'noopener noreferrer',class:'text-link'},'Определение показателя и источник'));
  return root;
}
