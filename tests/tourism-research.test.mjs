import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  normalizeTourismRows, tourismPeriods, tourismSlice, tourismTrajectories,
  tourismQuality, shortRegionName, buildTourismExport
} from '../src/core/tourism-research.js';

const payload = JSON.parse(fs.readFileSync(new URL('../public/data/projects/tourism/series/62900.json', import.meta.url), 'utf8'));
const rows = normalizeTourismRows(payload);
const close = (actual, expected, tolerance = 1e-10) => assert.ok(Math.abs(actual - expected) < tolerance, `${actual} != ${expected}`);

test('December 2025 concentration matches independently summed publication values', () => {
  const slice = tourismSlice(rows, '2025-12-31');
  assert.equal(slice.available, true);
  assert.equal(slice.regions.length, 85);
  assert.equal(slice.rows.length, 86);
  close(slice.total, 92.0428);
  close(slice.nationalValue, 92.0428);
  close(slice.top5Share, 41.79370901363279);
  close(slice.top10Share, 52.70591507429152);
  close(slice.ranked.reduce((total, row) => total + row.sharePct, 0), 100);
  assert.equal(slice.ranked[0].regionId, '77');
  assert.equal(slice.ranked[0].shortName, 'Москва');
  assert.equal(slice.concentration.length, 86);
  assert.equal(slice.concentration[0].cumulativeSharePct, 0);
  close(slice.concentration.at(-1).cumulativeSharePct, 100);
  assert.equal(slice.shareDenominator, 'sum_of_eligible_observed_regions');
});

test('all 21 dates reconcile independently and retain eight unexplained discrepancies', () => {
  const quality = tourismQuality(rows);
  assert.equal(quality.observationCount, 1806);
  assert.equal(quality.regionCount, 85);
  assert.equal(quality.periods.length, 21);
  assert.equal(quality.mismatchCount, 8);
  assert.equal(quality.matchingCount, 13);
  assert.equal(quality.incompleteCount, 0);
  const january = quality.periods[0];
  close(january.regionalSum, 6.2949);
  close(january.nationalValue, 6.243);
  close(january.difference, 0.0519);
  close(january.residual, -0.0519);
  const rawByPeriod = Map.groupBy(payload.observations, row => row.period_end);
  for (const reconciliation of quality.periods) {
    const raw = rawByPeriod.get(reconciliation.period);
    const national = raw.find(row => row.geo_level === 'national').value;
    const regional = raw.filter(row => row.geo_level === 'regional').reduce((total, row) => total + row.value, 0);
    close(reconciliation.residual, national - regional);
  }
});

test('an unsupported month remains unavailable rather than silently changing the request', () => {
  const slice = tourismSlice(rows, '2026-12-31');
  assert.equal(slice.available, false);
  assert.equal(slice.period, null);
  assert.equal(slice.requestedPeriod, '2026-12-31');
  assert.equal(slice.reason, 'requested_period_unavailable');
  assert.equal(slice.availablePeriods.at(-1), '2026-09-30');
  assert.equal(tourismSlice(rows, '2025-12').available, false);
  assert.equal(buildTourismExport(rows, {period: '2026-12-31'}).valid, false);
});

test('trajectory lines retain cumulative estimates, differing year coverage, and source cells', () => {
  const lines = tourismTrajectories(rows);
  assert.deepEqual(lines.map(line => line.year), [2025, 2026]);
  assert.deepEqual(lines.map(line => line.points.length), [12, 9]);
  assert.equal(lines[0].complete, true);
  assert.equal(lines[1].complete, false);
  close(lines[0].points[8].value, 75.7022);
  close(lines[1].points[8].value, 74.4464);
  assert.equal(lines[0].comparisonStatus, 'requires_edition_review');
  assert.ok(lines[0].points[0].source_cell_attributes.source_cell);
  assert.deepEqual(tourismTrajectories(rows, 'RU', 9).map(line => line.points.length), [9, 9]);
  assert.deepEqual(tourismTrajectories(rows, '99'), []);
  assert.throws(() => tourismTrajectories(rows, 'RU', 13), RangeError);
});

test('missing, excluded, duplicate, and geographically ineligible rows are not zero or double-counted', () => {
  const original = payload.observations.filter(row => ['2025-11-30', '2025-12-31'].includes(row.period_end));
  const altered = structuredClone(original);
  const december = altered.filter(row => row.period_end === '2025-12-31' && row.geo_level === 'regional');
  december[0].value = null;
  december[0].analytical_value = null;
  december[1].excluded = true;
  december[2].geographic_comparison_eligible = false;
  altered.push(structuredClone(december[3]));
  const normalized = normalizeTourismRows(altered);
  const slice = tourismSlice(normalized, '2025-12-31');
  assert.equal(slice.regions.length, 81);
  assert.equal(slice.coverage.expected, 85);
  assert.equal(slice.coverage.missingRegionIds.length, 4);
  assert.equal(slice.coverage.duplicateRegionIds.length, 1);
  assert.equal(slice.reconciliation.status, 'incomplete');
  assert.equal(slice.rows.find(row => row.id === december[0].id).value, null);
  assert.equal(slice.rows.find(row => row.id === december[1].id).value, null);
  assert.ok(slice.rows.find(row => row.id === december[1].id).originalValue > 0);
  const trajectory = tourismTrajectories(normalized, december[0].map_id).find(line => line.year === 2025);
  assert.equal(trajectory.points.at(-1).value, null);
  const pureZero = normalizeTourismRows([{...december[0], value: 0, analytical_value: 0, excluded: false}]);
  assert.equal(pureZero[0].value, 0);
  assert.equal(pureZero[0].eligible, true);
});

test('export includes the displayed full slice, selected and national histories, input edition, and exact source records', () => {
  const exported = buildTourismExport(rows, {period: '2025-12-31', regions: ['77', '24'], view: 'territories', sourceHash: 'verified-byte-hash'});
  assert.equal(exported.valid, true);
  assert.equal(exported.settings.version, '3.0.0-stage.2');
  assert.equal(exported.settings.appliedPeriod, '2025-12-31');
  assert.equal(exported.slice.regions.length, 85);
  assert.deepEqual([...new Set(exported.trajectories.map(line => line.regionId))], ['RU', '77', '24']);
  assert.deepEqual(exported.provenance.snapshot_ids, [payload.snapshot_id]);
  assert.equal(exported.provenance.source_sha256, 'verified-byte-hash');
  assert.equal(exported.provenance.statistical_as_of, '2026-10-15');
  assert.equal(exported.source_observations.length, 1806);
  assert.equal(exported.displayed_observation_ids.length, 146);
  for (const source of exported.source_observations) assert.deepEqual(source, payload.observations.find(row => row.id === source.id));
  const reopened = JSON.parse(JSON.stringify(exported));
  close(reopened.slice.top5Share, 41.79370901363279);
  assert.equal(reopened.causal_status, 'not_identified');
  assert.equal(buildTourismExport(rows, {period: '2025-12-31', regions: ['99']}).valid, false);
});

test('short display names preserve the underlying registry names', () => {
  const name = 'Город Москва столица Российской Федерации город федерального значения';
  assert.equal(shortRegionName(name), 'Москва');
  assert.equal(shortRegionName('Город Санкт-Петербург город федерального значения'), 'Санкт-Петербург');
  assert.equal(shortRegionName('Московская область'), 'Московская область');
  assert.ok(rows.some(row => row.name === name && row.shortName === 'Москва'));
  assert.deepEqual(tourismPeriods(rows).slice(0, 2), ['2025-01-31', '2025-02-28']);
  assert.equal(payload.observations[0].tourismNormalized, undefined);
});

test('a compact packet expands every original field before analysis and export', () => {
  const commonKeys = Object.keys(payload.observations[0]).filter(key => payload.observations.every(row => JSON.stringify(row[key]) === JSON.stringify(payload.observations[0][key])));
  const defaults = Object.fromEntries(commonKeys.map(key => [key, payload.observations[0][key]]));
  const compact = {...payload, source_sha256: 'original-series-byte-hash', observation_defaults: defaults,
    observations: payload.observations.map(row => Object.fromEntries(Object.entries(row).filter(([key]) => !commonKeys.includes(key))))};
  const expanded = normalizeTourismRows(compact);
  for (let index = 0; index < rows.length; index++) assert.deepEqual(expanded[index].source_row, payload.observations[index]);
  close(tourismSlice(expanded, '2025-12-31').top5Share, 41.79370901363279);
  assert.equal(buildTourismExport(expanded, {period: '2025-12-31'}).provenance.source_sha256, 'original-series-byte-hash');
});

test('an absent month creates a gap inside a trajectory and never a zero or interpolated observation', () => {
  const absentMarch = payload.observations.filter(row => !(row.geo_level === 'national' && row.period_end === '2025-03-31'));
  const series = tourismTrajectories(normalizeTourismRows(absentMarch)).find(line => line.year === 2025);
  assert.equal(series.points.length, 12);
  assert.equal(series.points[2].month, 3);
  assert.equal(series.points[2].value, null);
  assert.equal(series.points[2].missingReason, 'observation_not_published');
  assert.equal(series.complete, false);
});

test('malformed calendar dates never enter the period selector or trajectories', () => {
  const malformed = ['2025-13-31', '2025-02-31', '2025-00-31', 'not-a-date'].map(period_end => ({...payload.observations[0], period_end}));
  const normalized = normalizeTourismRows(malformed);
  assert.deepEqual(tourismPeriods(normalized), []);
  assert.deepEqual(tourismTrajectories(normalized, payload.observations[0].map_id), []);
  assert.equal(normalized.filter(row => row.eligible).length, 0);
});
