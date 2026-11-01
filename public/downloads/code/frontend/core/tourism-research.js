/**
 * The tourism pilot deliberately retains the publication's cumulative values.
 * No operation in this module infers monthly flows or a causal effect.
 * All shares use the sum of eligible regional rows, never the national total.
 */
export const TOURISM_RESEARCH_VERSION = '3.0.0-stage.2';
export const TOURISM_RECONCILIATION_TOLERANCE = 1e-6;
export const TOURISM_COMPARISON_STATUS = 'requires_edition_review';

const SOURCE_ID = '62900';
const SOURCE_URL = 'https://www.fedstat.ru/indicator/62900';
const MONTHS = ['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь'];
const LIMITATIONS = Object.freeze([
  'Значения являются накопленными оценками с начала календарного года. Разности соседних публикаций не интерпретируются как месячные потоки.',
  'Сопоставимость редакций методики и статистических оценок за 2025–2026 годы не подтверждена. Сравнение лет является описательным.',
  'Количество поездок не является количеством уникальных людей или оценкой доступности отдыха для жителей.',
  'Доли и концентрация рассчитаны от суммы наблюдаемых региональных значений. Опубликованный итог России и остаток сверки сохраняются отдельно.',
  'Сведения о поездках не идентифицируют причинный эффект государственной поддержки.'
]);

const numeric = input => {
  if (input === null || input === undefined || typeof input === 'boolean') return null;
  if (typeof input === 'string' && input.trim() === '') return null;
  const result = typeof input === 'number' ? input : Number(String(input).replace(/[\s\u00a0]/g, '').replace(',', '.'));
  return Number.isFinite(result) ? result : null;
};
const sum = values => values.reduce((total, value) => total + value, 0);
const validPeriod = value => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + 'T00:00:00Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
};
const normalized = rows => Array.isArray(rows) && rows.every(row => row && row.tourismNormalized === true)
  ? rows : normalizeTourismRows(rows);
const regionKey = value => String(value ?? '').trim().toUpperCase() === 'RU'
  ? 'RU' : /^\d{1,2}$/.test(String(value ?? '').trim()) ? String(value).trim().padStart(2, '0') : String(value ?? '').trim();

export function shortRegionName(name = '') {
  const value = String(name);
  if (/^(Город )?Москва(?: |$)/i.test(value)) return 'Москва';
  if (/^(Город )?Санкт-Петербург(?: |$)/i.test(value)) return 'Санкт-Петербург';
  if (/^(Город (?:федерального значения )?)?Севастополь(?: |$)/i.test(value)) return 'Севастополь';
  return value.replace(/^Республика Татарстан \(Татарстан\)$/, 'Республика Татарстан')
    .replace(/^Кемеровская область(?:\s*[–—-]\s*Кузбасс)?$/, 'Кемеровская область')
    .replace(/^Ханты-Мансийский автономный округ\s*[–—-]\s*Югра$/, 'ХМАО – Югра')
    .replace(/^Ямало-Ненецкий автономный округ$/, 'ЯНАО')
    .replace(/^Ненецкий автономный округ$/, 'Ненецкий АО')
    .replace(/^Чукотский автономный округ$/, 'Чукотский АО')
    .replace(/^Республика Саха \(Якутия\)$/, 'Республика Саха (Якутия)');
}

/** Preserve every source row, including excluded and missing observations. */
export function normalizeTourismRows(payload) {
  const observations = Array.isArray(payload) ? payload : payload?.observations || [];
  const metadata = Array.isArray(payload) ? null : Object.fromEntries(
    Object.entries(payload || {}).filter(([key]) => key !== 'observations')
  );
  return observations.map((sourceRow, index) => {
    if (sourceRow?.tourismNormalized) return sourceRow;
    const row = payload?.observation_defaults ? {...payload.observation_defaults, ...sourceRow} : sourceRow || {};
    const name = row.name || row.territory_name || row.region_name || '';
    const isNational = ['national', 'russia', 'country'].includes(row.geo_level) || row.is_national === true || /^Российская Федерация(?:\s|$)/.test(name);
    const id = isNational ? 'RU' : regionKey(row.map_id ?? row.region_id ?? row.code ?? row.territory_code);
    const periodEnd = row.period_end || row.periodEnd || '';
    const originalValue = numeric(row.value);
    const excluded = row.excluded === true || (row.quality_flags || []).some(flag => flag.exclude_from_analysis === true);
    const analytical = Object.hasOwn(row, 'analytical_value') ? numeric(row.analytical_value) : originalValue;
    const sourceId = String(row.source_id || metadata?.source_id || SOURCE_ID);
    const invalidSource = sourceId !== SOURCE_ID;
    const invalidSemantics = !!row.frequency && row.frequency !== 'cumulative_ytd';
    const hasCategory = !!row.category && Object.keys(row.category).length > 0;
    const value = excluded || invalidSource || invalidSemantics || hasCategory || (analytical !== null && analytical < 0) ? null : analytical;
    return {
      ...row,
      tourismNormalized: true,
      source_id: sourceId,
      regionId: id,
      isNational,
      name,
      shortName: shortRegionName(name),
      periodEnd,
      month: validPeriod(periodEnd) ? Number(periodEnd.slice(5, 7)) : null,
      year: validPeriod(periodEnd) ? Number(periodEnd.slice(0, 4)) : numeric(row.year),
      value,
      originalValue,
      excluded,
      invalidSource,
      invalidSemantics,
      hasCategory,
      eligible: value !== null && value >= 0 && validPeriod(periodEnd) && (isNational || (/^\d{2}$/.test(id) && row.geo_level === 'regional' && row.geographic_comparison_eligible !== false)),
      sourceRowIndex: index,
      metadata: metadata || row.metadata || null,
      source_row: row
    };
  });
}

export function tourismPeriods(input) {
  return [...new Set(normalized(input).map(row => row.periodEnd).filter(validPeriod))].sort();
}

function periodLabel(period) {
  const month = Number(period.slice(5, 7));
  return (month === 1 ? 'Январь' : 'Январь–' + MONTHS[month - 1]) + ' ' + period.slice(0, 4);
}

function duplicateKeys(rows) {
  const counts = new Map();
  for (const row of rows) counts.set(row.regionId, (counts.get(row.regionId) || 0) + 1);
  return [...counts].filter(([, count]) => count > 1).map(([key]) => key);
}

/** An unavailable requested period is never replaced by the nearest period. */
export function tourismSlice(input, requestedPeriod) {
  const rows = normalized(input), availablePeriods = tourismPeriods(rows);
  if (!availablePeriods.includes(requestedPeriod)) return {
    available: false, requestedPeriod, period: null, availablePeriods,
    reason: 'requested_period_unavailable', rows: [], regions: [], ranked: [], concentration: [],
    total: null, nationalValue: null, residual: null, nationalMinusRegions: null,
    difference: null, top5Share: null, top10Share: null, hhi: null,
    comparisonStatus: TOURISM_COMPARISON_STATUS
  };
  const selected = rows.filter(row => row.periodEnd === requestedPeriod);
  const duplicateRegionIds = duplicateKeys(selected);
  const admitted = selected.filter(row => row.eligible && !duplicateRegionIds.includes(row.regionId));
  const regions = admitted.filter(row => !row.isNational);
  const national = admitted.find(row => row.isNational) || null;
  const expectedRegionIds = [...new Set(rows.filter(row => !row.isNational && /^\d{2}$/.test(row.regionId) && row.geo_level === 'regional').map(row => row.regionId))].sort();
  const observedRegionIds = new Set(regions.map(row => row.regionId));
  const total = regions.length ? sum(regions.map(row => row.value)) : null;
  const nationalValue = national?.value ?? null;
  const residual = nationalValue !== null && total !== null ? nationalValue - total : null;
  let cumulativeValue = 0;
  const ranked = [...regions].sort((a, b) => b.value - a.value || a.regionId.localeCompare(b.regionId)).map((row, index) => {
    cumulativeValue += row.value;
    return {...row, rank: index + 1, sharePct: total > 0 ? row.value / total * 100 : null,
      cumulativeValue, cumulativeSharePct: total > 0 ? cumulativeValue / total * 100 : null};
  });
  const topShare = count => total > 0 ? sum(ranked.slice(0, count).map(row => row.value)) / total * 100 : null;
  const missingRegionIds = expectedRegionIds.filter(id => !observedRegionIds.has(id));
  const complete = !missingRegionIds.length && !duplicateRegionIds.length && nationalValue !== null;
  return {
    available: true, requestedPeriod, period: requestedPeriod, periodLabel: periodLabel(requestedPeriod),
    availablePeriods, rows: selected, regions, ranked, national, total, nationalValue,
    residual, nationalMinusRegions: residual, difference: residual === null ? null : -residual,
    top5Share: topShare(5), top10Share: topShare(10),
    hhi: total > 0 ? sum(regions.map(row => (row.value / total) ** 2)) : null,
    concentration: [{k: 0, count: 0, value: 0, cumulativeValue: 0, cumulativeSharePct: 0}, ...ranked.map(row => ({
      k: row.rank, count: row.rank, value: row.cumulativeValue, cumulativeValue: row.cumulativeValue, cumulativeSharePct: row.cumulativeSharePct
    }))],
    coverage: {expected: expectedRegionIds.length, observed: regions.length, missingRegionIds, duplicateRegionIds, complete,
      excluded: selected.filter(row => row.excluded).length, missing: selected.filter(row => row.value === null && !row.excluded).length},
    reconciliation: {status: !complete || residual === null ? 'incomplete' : Math.abs(residual) <= TOURISM_RECONCILIATION_TOLERANCE ? 'matched' : 'mismatch',
      tolerance: TOURISM_RECONCILIATION_TOLERANCE, reason: residual !== null && Math.abs(residual) > TOURISM_RECONCILIATION_TOLERANCE ? 'Причина расхождения в сохранённых данных не установлена.' : null},
    unit: 'млн поездок', frequency: 'cumulative_ytd',
    shareDenominator: 'sum_of_eligible_observed_regions',
    comparisonStatus: TOURISM_COMPARISON_STATUS
  };
}

/** Cumulative lines, aligned by month; missing observations remain explicit gaps. */
export function tourismTrajectories(input, region = 'RU', endMonth = 12) {
  if (!Number.isInteger(Number(endMonth)) || Number(endMonth) < 1 || Number(endMonth) > 12) throw new RangeError('endMonth must be an integer from 1 through 12');
  const regionId = regionKey(region), rows = normalized(input).filter(row => row.regionId === regionId && validPeriod(row.periodEnd) && row.month >= 1 && row.month <= Number(endMonth));
  return [...new Set(rows.map(row => row.year))].sort((a, b) => a - b).map(year => {
    const yearRows = rows.filter(row => row.year === year).sort((a, b) => a.month - b.month);
    const counts = new Map();
    for (const row of yearRows) counts.set(row.month, (counts.get(row.month) || 0) + 1);
    const latestMonth = Math.max(...yearRows.map(row => row.month));
    const points = Array.from({length: latestMonth}, (_, index) => {
      const month = index + 1, row = yearRows.find(item => item.month === month);
      if (row) return {...row, period: row.periodEnd, value: row.eligible && counts.get(month) === 1 ? row.value : null};
      return {regionId, year, month, name: yearRows[0]?.name || regionId, shortName: yearRows[0]?.shortName || regionId,
        value: null, originalValue: null, period: null, periodEnd: null, eligible: false,
        missingReason: 'observation_not_published', source_row: null};
    });
    return {year, regionId, name: yearRows[0]?.name || regionId, shortName: yearRows[0]?.shortName || regionId,
      points, complete: points.filter(point => point.value !== null).length === Number(endMonth),
      calendarYearComplete: Number(endMonth) === 12 && points.filter(point => point.value !== null).length === 12,
      frequency: 'cumulative_ytd', comparisonStatus: TOURISM_COMPARISON_STATUS};
  });
}

export function tourismQuality(input) {
  const rows = normalized(input);
  const periods = tourismPeriods(rows).map(period => {
    const slice = tourismSlice(rows, period);
    return {period, period_end: period, periodLabel: slice.periodLabel, regions: slice.regions.length,
      regionalSum: slice.total, regional_sum: slice.total, nationalValue: slice.nationalValue, national_value: slice.nationalValue,
      residual: slice.residual, difference: slice.difference, tolerance: slice.reconciliation.tolerance,
      equal: slice.reconciliation.status === 'matched', status: slice.reconciliation.status,
      coverage: slice.coverage, sourceRows: slice.rows.map(row => row.id || row.source_observation_key || row.sourceRowIndex)};
  });
  return {
    periods, mismatchCount: periods.filter(row => row.status === 'mismatch').length,
    matchingCount: periods.filter(row => row.status === 'matched').length,
    incompleteCount: periods.filter(row => row.status === 'incomplete').length,
    observationCount: rows.length, eligibleCount: rows.filter(row => row.eligible).length,
    excludedCount: rows.filter(row => row.excluded).length,
    missingCount: rows.filter(row => row.value === null && !row.excluded).length,
    regionCount: new Set(rows.filter(row => !row.isNational && row.geo_level === 'regional').map(row => row.regionId)).size,
    nationalCount: rows.filter(row => row.isNational).length,
    tolerance: TOURISM_RECONCILIATION_TOLERANCE,
    comparisonStatus: TOURISM_COMPARISON_STATUS
  };
}

const exportRow = row => {
  const {metadata, source_row, tourismNormalized, ...rest} = row;
  return rest;
};

/** Self-contained evidence package: shown slice, trajectories, definitions and input rows. */
export function buildTourismExport(input, {period, regions = ['RU'], view = 'overview', version = TOURISM_RESEARCH_VERSION, sourceHash = null} = {}) {
  const rows = normalized(input);
  const requestedRegions = [...new Set((Array.isArray(regions) ? regions : String(regions).split(',')).map(regionKey).filter(Boolean))];
  const selectedIds = [...new Set(['RU', ...requestedRegions])];
  const slice = tourismSlice(rows, period);
  const trajectoryRows = rows.filter(row => selectedIds.includes(row.regionId));
  const rawRows = [...new Set([...slice.rows, ...trajectoryRows])];
  const meta = rows.find(row => row.metadata)?.metadata || {};
  const availableRegionIds = new Set(rows.map(row => row.regionId));
  const missingRegions = requestedRegions.filter(id => !availableRegionIds.has(id));
  const trajectories = selectedIds.flatMap(regionId => tourismTrajectories(rows, regionId).map(series => ({
    ...series, points: series.points.map(exportRow)
  })));
  return {
    schema: 'national-projects.tourism-research/1',
    project: 'tourism', indicator: SOURCE_ID,
    valid: slice.available && missingRegions.length === 0,
    settings: {requestedPeriod: period ?? null, appliedPeriod: slice.period, regions: requestedRegions, view, version,
      missingRegions, comparisonStatus: TOURISM_COMPARISON_STATUS},
    provenance: {source_id: SOURCE_ID, source_url: meta.source_url || SOURCE_URL,
      source_file: 'data/projects/tourism/series/62900.json', source_sha256: sourceHash || meta.source_sha256 || null,
      snapshot_ids: [...new Set(rows.map(row => row.snapshot_id || row.metadata?.snapshot_id).filter(Boolean))],
      statistical_as_of: meta.statistical_as_of || null, published_at: meta.published_at || null,
      code_version: version, source_metadata: meta},
    definitions: {unit: 'млн поездок', temporal_type: 'cumulative_ytd', period_start_rule: '1 January of each reported year',
      geography: 'Published destination regions; national row is stored separately',
      share_denominator: 'sum of eligible regional values in the requested period',
      residual_formula: 'published national value minus sum of eligible regional values',
      top5_formula: '100 * sum of five largest eligible regional values / sum of all eligible regional values',
      top10_formula: '100 * sum of ten largest eligible regional values / sum of all eligible regional values',
      hhi_formula: 'sum((eligible regional value / sum of eligible regional values)^2)',
      reconciliation_tolerance: TOURISM_RECONCILIATION_TOLERANCE,
      missing_policy: 'Retain null; do not impute. Excluded rows and duplicate territory-period keys do not enter analytical sums.'},
    slice: {...slice, rows: slice.rows.map(exportRow), regions: slice.regions.map(exportRow), ranked: slice.ranked.map(exportRow), national: slice.national ? exportRow(slice.national) : null},
    trajectories,
    quality: tourismQuality(rows),
    displayed_observation_ids: rawRows.map(row => row.id || row.source_observation_key || row.sourceRowIndex),
    source_observations: rows.map(row => row.source_row),
    limitations: [...LIMITATIONS],
    interpretation: 'descriptive_publication_comparison', causal_status: 'not_identified'
  };
}
