/**
 * A request is independent of a project's native source and period keys.
 * Equal end dates do not make different observation windows interchangeable.
 */
export const RESEARCH_CONTEXT_PROJECTS = Object.freeze(['tourism','family','long_active_life','personnel']);
export const RESEARCH_CONTEXT_KEYS = Object.freeze(['ctx_region','ctx_start','ctx_end','ctx_kind','ctx_frequency']);
// Missing ctx_region permits the project's initial selection. The explicit
// ctx_region=all choice means «Все регионы» and must survive page/project links.
export const ALL_RESEARCH_REGIONS = 'all';
export const PERIOD_KIND_LABELS = Object.freeze({
  annual:'Годовое наблюдение',
  monthly:'Месячное наблюдение источника',
  quarterly:'Квартальное наблюдение',
  cumulative_ytd:'С начала календарного года',
  rolling_12_months:'Скользящие 12 месяцев',
  stock_at_period_end:'Состояние на конец периода',
  point_in_time:'Состояние на дату',
  operational_monitoring:'Оперативное наблюдение источника'
});
const FREQUENCIES = new Set(['annual','monthly','quarterly','daily','cumulative_ytd']);

export function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value+'T00:00:00Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0,10) === value;
}

export function contextParams(state = {}) {
  return Object.fromEntries(RESEARCH_CONTEXT_KEYS
    .filter(key => state[key] !== undefined && state[key] !== null && state[key] !== '')
    .map(key => [key,String(state[key])]));
}

export function readResearchContext(state = {}) {
  const region = state.ctx_region === ALL_RESEARCH_REGIONS ? '' : String(state.ctx_region || '');
  const hasPeriod = ['ctx_start','ctx_end','ctx_kind','ctx_frequency'].some(key => Boolean(state[key]));
  const invalidRegion = Boolean(region && !/^(?:0[1-9]|[1-9]\d)$/.test(region));
  const kind = String(state.ctx_kind || ''), frequency = String(state.ctx_frequency || '');
  const start = String(state.ctx_start || ''), end = String(state.ctx_end || '');
  const invalidPeriod = hasPeriod && (!validDate(start) || !validDate(end) || start > end ||
    !Object.hasOwn(PERIOD_KIND_LABELS,kind) || (frequency && !FREQUENCIES.has(frequency)) ||
    (['point_in_time','stock_at_period_end'].includes(kind) && start !== end));
  return {
    region,hasPeriod,invalidRegion,invalidPeriod,
    period:hasPeriod && !invalidPeriod ? {start,end,kind,frequency} : null,
    present:Boolean(region || state.ctx_region === ALL_RESEARCH_REGIONS || hasPeriod)
  };
}

export function periodIdentity(period) {
  return period ? [period.start,period.end,period.kind,period.frequency || ''].join('|') : '';
}

export function sameContextPeriod(left,right) {
  return Boolean(left && right && periodIdentity(left) === periodIdentity(right));
}

export function periodContextParams(period) {
  return period ? {ctx_start:period.start,ctx_end:period.end,ctx_kind:period.kind,ctx_frequency:period.frequency || null}
    : {ctx_start:null,ctx_end:null,ctx_kind:null,ctx_frequency:null};
}

export function describePeriod(period) {
  if (!period) return 'Период не выбран';
  const format = value => value.split('-').reverse().join('.');
  const window = period.start === period.end ? format(period.end) : format(period.start)+' – '+format(period.end);
  const frequency = !['annual','monthly','quarterly'].includes(period.kind)
    ? ({annual:'годовая публикация',monthly:'месячная публикация',quarterly:'квартальная публикация'})[period.frequency] : '';
  return window+' · '+(PERIOD_KIND_LABELS[period.kind] || 'Наблюдение источника')+(frequency ? ' · '+frequency : '');
}

/** An explicit same-project link may intentionally select another territory. */
export function researchNavigationContext(current,target,{periods = [],sourceId = current.source} = {}) {
  const result = {...contextParams(current),...contextParams(target)};
  if (current.nationalProject !== target.nationalProject) return result;
  if (!Object.hasOwn(target,'ctx_region')) {
    if (Object.hasOwn(target,'r')) result.ctx_region = target.r || ALL_RESEARCH_REGIONS;
    if (Object.hasOwn(target,'region')) result.ctx_region = target.region || ALL_RESEARCH_REGIONS;
  }
  const hasExplicitWindow = ['ctx_start','ctx_end','ctx_kind','ctx_frequency'].some(key=>Object.hasOwn(target,key));
  if (target.period && !hasExplicitWindow) {
    // A link explicitly naming another source and its period must be resolved
    // from that source's rows, never from the previous indicator's metadata.
    if (target.source && String(target.source) !== String(sourceId)) Object.assign(result,periodContextParams(null));
    else {
      const period = periods.find(period=>period.nativeKey === target.period);
      if (period) Object.assign(result,periodContextParams(period));
      else Object.assign(result,periodContextParams(null));
    }
  }
  return result;
}

/** No nearest, newest or December substitution when a request is present. */
export function resolveContextPeriod(state,periods,{nativePeriod = state.period,defaultPeriod = null} = {}) {
  const request = readResearchContext(state);
  if (request.invalidPeriod) return {status:'invalid',selected:null,request:request.period};
  if (request.hasPeriod) {
    const matches = periods.filter(period => sameContextPeriod(period,request.period));
    const selected = matches.find(period => period.nativeKey === nativePeriod) || matches.find(period => !period.category) || matches[0] || null;
    return {status:selected ? 'available' : 'unavailable',selected,request:request.period};
  }
  // Native links are requests too; a mistyped or unavailable period stays visible.
  if (nativePeriod) {
    const selected = periods.find(period => period.nativeKey === nativePeriod) || null;
    return {status:selected ? 'available' : 'unavailable',selected,request:selected,nativeRequest:nativePeriod};
  }
  const selected = periods.find(period => period.nativeKey === defaultPeriod) || periods.at(-1) || null;
  return {status:selected ? 'available' : 'unavailable',selected,request:selected};
}

/** Metadata, never a difference of cumulative values, defines the window. */
export function sourcePeriodWindow(row,source = {}) {
  const end = row.period_end || row.end || '';
  if (!validDate(end)) return null;
  const nativeFrequency = row.source_frequency || row.frequency || ({год:'annual',месяц:'monthly',квартал:'quarterly'})[row.type] || '';
  const semantics = row.period_semantics || source.period_semantics || '';
  const frequency = nativeFrequency === 'cumulative_ytd' ? 'monthly' : nativeFrequency;
  let kind = frequency,start = row.period_start || row.start || '';
  if (['cumulative_ytd','cumulative_flow'].includes(semantics) || row.frequency === 'cumulative_ytd') {
    kind = 'cumulative_ytd';start = end.slice(0,4)+'-01-01';
  } else if (semantics === 'stock_at_period_end') {
    kind = 'stock_at_period_end';start = end;
  } else if (semantics === 'rolling_12_months') {
    kind = 'rolling_12_months';
    const date = new Date(end+'T00:00:00Z');
    // A monthly rolling interval begins on the first day eleven months earlier.
    start = new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()-11,1)).toISOString().slice(0,10);
  } else if (semantics === 'operational_monitoring') {
    kind = 'operational_monitoring';
  }
  if (!start) {
    if (frequency === 'annual') start = end.slice(0,4)+'-01-01';
    if (frequency === 'monthly') start = end.slice(0,7)+'-01';
    if (frequency === 'quarterly') start = end.slice(0,4)+'-'+String(Math.floor((Number(end.slice(5,7))-1)/3)*3+1).padStart(2,'0')+'-01';
  }
  if (!validDate(start) || start > end || !Object.hasOwn(PERIOD_KIND_LABELS,kind)) return null;
  return {start,end,kind,frequency};
}

/** Local controls can intentionally change a request, but source changes cannot. */
export function updateContextFromLocalControl(state,patch,periods = []) {
  const next = {...state,...patch};
  const resetsLocalSelection = Object.hasOwn(patch,'source') || Boolean(patch.period);
  const explicitTourismSelection = Object.hasOwn(patch,'regions');
  if (!Object.hasOwn(patch,'ctx_region')) {
    if (Object.hasOwn(patch,'r') && (!resetsLocalSelection || patch.r)) next.ctx_region = patch.r || ALL_RESEARCH_REGIONS;
    if (Object.hasOwn(patch,'region') && (!resetsLocalSelection || patch.region || explicitTourismSelection)) {
      const remaining = explicitTourismSelection ? String(patch.regions || '').split(',').find(id=>/^\d{2}$/.test(id)) : null;
      next.ctx_region = patch.region || remaining || ALL_RESEARCH_REGIONS;
    }
  }
  if (patch.period && !Object.hasOwn(patch,'source')) {
    const selected = periods.find(period => period.nativeKey === patch.period);
    if (selected) Object.assign(next,periodContextParams(selected));
  }
  return next;
}
