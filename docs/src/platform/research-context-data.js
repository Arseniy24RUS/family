import {series,periods as familyPeriods,choosePeriod,regionRows,analyticalRow,metaUnit} from '../core/data.js';
import {normalizeTourismRows,tourismPeriods} from '../core/tourism-research.js';
import {RESEARCH_CONTEXT_PROJECTS,ALL_RESEARCH_REGIONS,contextParams,readResearchContext,sourcePeriodWindow,resolveContextPeriod,periodContextParams} from '../core/research-context.js';

const array = value => Array.isArray(value) ? value : [];
const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const regionId = row => String(row.r || row.map_id || row.regionId || row.code || '');
const sourceName = source => source.short_title || source.label || source.title || source.id;
const category = row => typeof row.category === 'object' ? Object.entries(row.category || {}).sort(([a],[b])=>a.localeCompare(b)).map(([key,value])=>key+':'+value).join(';') : String(row.category || '');
const longlifeKey = row => [row.frequency || '',row.period_end || '',category(row)].join('|');
const sourceValue = row => row.excluded || row.flag || row.geographic_comparison_eligible === false ? null : numeric(Object.hasOwn(row,'analytical_value') ? row.analytical_value : row.value);

export function familyContextModel(catalog,packet,sourceId = 'data_21') {
  const source = catalog.datasets.find(item=>item.id === sourceId);
  const sourcePeriods = familyPeriods(packet.rows);
  const periods = sourcePeriods.map(period=>({...sourcePeriodWindow(period),nativeKey:period.key,label:period.label})).filter(period=>period.start);
  return {
    source:{...source,title:source.label,unit:metaUnit(source)},sources:catalog.datasets,
    periods,defaultPeriod:choosePeriod(sourcePeriods,null,false),
    readings:key=>[...regionRows(packet.rows,key).values()].map(row=>({...analyticalRow(row),map_id:row.r}))
  };
}

export function tourismContextModel(packet) {
  const rows = normalizeTourismRows(packet);
  const periods = tourismPeriods(rows).map(period=>({start:period.slice(0,4)+'-01-01',end:period,kind:'cumulative_ytd',frequency:'monthly',nativeKey:period}));
  return {
    source:{id:packet.source_id,title:packet.title,unit:'млн поездок',source_unit:packet.unit,source_url:packet.source_url},sources:[],periods,
    defaultPeriod:periods.filter(period=>period.end.endsWith('-12-31')).at(-1)?.nativeKey || periods.at(-1)?.nativeKey,
    readings:key=>rows.filter(row=>!row.isNational && row.periodEnd === key).map(row=>({...row,value:row.eligible ? row.value : null,analytical_value:row.eligible ? row.value : null}))
  };
}

export function longlifeContextModel(statistics,observations,sourceId = '62971',page = 'map') {
  const sources = array(statistics.sources).filter(source=>array(source.regional_latest).length);
  const source = sources.find(item=>String(item.id) === String(sourceId)) || sources.find(item=>String(item.id) === '62971') || sources[0];
  const byKey = new Map();
  for (const row of observations.filter(row=>row.geo_level === 'regional')) {
    const nativeKey = longlifeKey(row),window = sourcePeriodWindow(row,source);
    if (!window) continue;
    if (!byKey.has(nativeKey)) byKey.set(nativeKey,{...window,nativeKey,category:category(row),numericCount:0});
    if (sourceValue(row) !== null) byKey.get(nativeKey).numericCount++;
  }
  const periods = [...byKey.values()].sort((a,b)=>a.end.localeCompare(b.end)||a.frequency.localeCompare(b.frequency)||a.category.localeCompare(b.category));
  const preferred = page === 'regions' && String(source?.id) === '62971' ? periods.find(period=>period.end === '2026-07-31' && period.frequency === 'monthly') : null;
  return {
    source:{...source,title:sourceName(source),unit:source.display_unit || source.unit},sources,periods,
    defaultPeriod:preferred?.nativeKey || periods.filter(period=>period.numericCount > 0).at(-1)?.nativeKey || periods.at(-1)?.nativeKey,
    readings:key=>observations.filter(row=>row.geo_level === 'regional' && longlifeKey(row) === key)
  };
}

export function personnelContextModel(context) {
  const year = String(context.year || '2024'),nativeKey = 'annual|'+year+'-12-31';
  return {
    source:{id:context.id,title:context.title,unit:context.unit,source_url:context.source_url},sources:[],
    periods:[{start:year+'-01-01',end:year+'-12-31',kind:'annual',frequency:'annual',nativeKey}],defaultPeriod:nativeKey,
    readings:key=>key === nativeKey ? array(context.regions) : []
  };
}

const scopes = {
  'family:map':'Период применяется к основной карте и её таблице. Выбранная территория открывает региональный профиль. Другие показатели профиля имеют собственные даты наблюдений.',
  'family:regions':'Выбранная территория выделяется в региональном анализе. Общий период здесь не применяется: многомерные расчёты объединяют показатели с собственными датами. Для одного периода откройте карту.',
  'long_active_life:map':'Период применяется к карте и её таблице. Выбранная территория открывает региональный профиль; отсутствие пригодного значения указано отдельно.',
  'long_active_life:regions':'Период применяется к основному распределению и выбранному региональному профилю. Исторические ряды, кадровый анализ июля 2026 года и многомерные расчёты сохраняют собственные даты.',
  'personnel:map':'Период применяется к региональной карте безработицы. Опубликованные значения за 2024 год описывают исходные условия рынка труда.',
  'personnel:regions':'Период применяется к распределению и профилю региональной безработицы. Значения за 2024 год описывают исходные условия рынка труда.',
  'tourism:map':'Период применяется к карте, таблице и распределению поездок. Выбранная территория выделяется; исторические траектории сохраняют собственную временную ось.',
  'tourism:regions':'Период применяется к региональному срезу. Выбранная территория входит в сравнение; исторические траектории сохраняют собственную временную ось.',
  'tourism:overview':'Период применяется к показателям территориальной концентрации и срезу поездок. Исторические траектории сохраняют собственную временную ось.'
};

export function resolveResearchContextModel({projectId,page,state,catalog,model = null}) {
  const supported = RESEARCH_CONTEXT_PROJECTS.includes(projectId),request = readResearchContext(state);
  if (!supported && !request.present) return null;
  const regions = array(catalog?.regions);
  const contextRegion = state.ctx_region === ALL_RESEARCH_REGIONS ? '' : state.ctx_region;
  const initialTourismRegions = state.ctx_region === ALL_RESEARCH_REGIONS ? '' : state.ctx_region || '77,23';
  const tourismRegions = [...new Set(String(Object.hasOwn(state,'regions') ? state.regions : Object.hasOwn(state,'region') ? state.region : initialTourismRegions).split(',').filter(id=>/^\d{2}$/.test(id)))].slice(0,5);
  const localRegion = projectId === 'tourism' ? state.region || tourismRegions[0] || '' : state.r;
  const selectedRegion = Object.hasOwn(state,'ctx_region') ? String(contextRegion || '') : String(localRegion || '');
  const territory = regions.find(region=>String(region.id) === selectedRegion);
  const unknownRegion = Boolean(selectedRegion && !territory);
  const applied = Boolean(model);
  const resolution = model ? resolveContextPeriod(state,model.periods,{defaultPeriod:model.defaultPeriod}) : null;
  const selected = resolution?.selected || null;
  const shared = {...contextParams(state),...(selected ? periodContextParams(selected) : {}),ctx_region:selectedRegion || (state.ctx_region === ALL_RESEARCH_REGIONS ? ALL_RESEARCH_REGIONS : null)};
  const next = {...state,...shared};
  if (applied && selected) next.period = selected.nativeKey;
  if (applied && model.sources.length) next.source = model.source.id;
  let comparisonAdjusted = false;
  if (supported) {
    if (projectId === 'tourism') {
      next.region = selectedRegion || null;
      if (selectedRegion && !tourismRegions.includes(selectedRegion)) {
        // Keep the existing comparison order and colours. The common selector
        // deliberately replaces the last comparison when all five are occupied.
        if (tourismRegions.length === 5) {tourismRegions.pop();comparisonAdjusted = true;}
        tourismRegions.push(selectedRegion);
      }
      next.regions = tourismRegions.join(',') || 'none';
    } else next.r = selectedRegion || null;
  }
  const readings = selected ? model.readings(selected.nativeKey) : [];
  const territoryRows = selectedRegion ? readings.filter(row=>regionId(row) === selectedRegion) : [];
  const eligible = territoryRows.filter(row=>sourceValue(row) !== null);
  const values = [...new Set(eligible.map(sourceValue))];
  const value = values.length === 1 ? values[0] : null;
  const status = unknownRegion ? 'unknown_region' : resolution?.status || 'outside';
  return {
    projectId,page,supported,applied,state:next,request:readResearchContext(next),
    status,blocked:Boolean(applied && !selected),resolution,
    source:model?.source,sources:model?.sources || [],periods:model?.periods || [],selected,
    regions,region:selectedRegion,territory,unknownRegion,comparisonAdjusted,
    regionValue:value,regionAvailable:values.length === 1,regionHasRows:territoryRows.length > 0,
    scope:scopes[projectId+':'+page] || (supported
      ? 'Территория и период сохранены для карт и региональных таблиц. На этой странице материалы и диаграммы используют собственные даты источников.'
      : 'Территория и период сохранены. Общий выбор применяется к картам и региональным таблицам проектов «Семья», «Здоровье», «Кадры» и «Туризм». Материалы этого проекта используют собственные параметры.')
  };
}

/** The adapter loads exactly the selected source and resolves against its rows. */
export async function prepareResearchContext({projectId,page,state,catalog,familyData,research,loadSeries = series,loadHealthObservations = null}) {
  const applies = (['map','regions'].includes(page) && !(projectId === 'family' && page === 'regions')) || (projectId === 'tourism' && page === 'overview');
  let model = null;
  if (applies && projectId === 'family') {
    const sourceId = catalog.datasets.some(item=>item.id === state.source) ? state.source : 'data_21';
    const packet = await loadSeries(sourceId,'latest',familyData.manifest);
    model = familyContextModel(catalog,packet,sourceId);
  } else if (applies && projectId === 'tourism') model = tourismContextModel(research);
  else if (applies && projectId === 'long_active_life') {
    const sources = array(research.statistics?.sources).filter(source=>array(source.regional_latest).length);
    const source = sources.find(source=>String(source.id) === state.source) || sources.find(source=>String(source.id) === '62971') || sources[0];
    if (source) {
      const load = loadHealthObservations || (await import('../pages/longlife.js')).loadSourceObservations;
      const rows = await load(source);
      model = longlifeContextModel(research.statistics,rows,String(source.id),page);
    }
  } else if (applies && projectId === 'personnel') model = personnelContextModel(research.analytics?.context || {});
  return resolveResearchContextModel({projectId,page,state,catalog,model});
}
