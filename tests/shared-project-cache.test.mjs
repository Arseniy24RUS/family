import test from 'node:test';
import assert from 'node:assert/strict';
import {observationCache} from '../src/core/cache.js';
import {loadInfrastructureObservations} from '../src/pages/infrastructure.js';
import {loadCompetitiveObservations} from '../src/pages/competitive.js';
import {loadEnvironmentObservations} from '../src/pages/environment.js';
import {loadDataeconomyObservations} from '../src/pages/dataeconomy.js';

const source = id => ({id, downloads: {observations: `qa/shared-source-${id}.json`}});
const packet = (project, id, value = 0) => ({project_id: project, source_id: id,
  observations: [{source_id: id, value, raw_value: String(value), excluded: false,
    frequency: 'annual', period_end: '2025-12-31'}]});
const response = data => ({ok: true, json: async () => data});

test('shared observation cache isolates projects and evicts the least recently used source globally', async () => {
  observationCache.clear();
  const selected = source('same-id');
  const counts = new Map();
  const fixtures = [
    ['life_infrastructure', loadInfrastructureObservations],
    ['competitive_economy', loadCompetitiveObservations],
    ['environment', loadEnvironmentObservations],
    ['data_economy', loadDataeconomyObservations]
  ].map(([project, load], i) => {
    const data = packet(project, selected.id, i);
    return {project, load, data, fetcher: async () => {
      counts.set(project, (counts.get(project) || 0) + 1);
      return response(data);
    }};
  });
  for (const fixture of fixtures.slice(0, 3)) {
    assert.equal(await fixture.load(selected, fixture.fetcher), fixture.data.observations);
  }
  assert.equal(observationCache.size, 3);
  await fixtures[0].load(selected, fixtures[0].fetcher); // Keep the active comparison source warm.
  await fixtures[3].load(selected, fixtures[3].fetcher);
  await fixtures[0].load(selected, fixtures[0].fetcher);
  assert.equal(counts.get('life_infrastructure'), 1);
  assert.equal(await fixtures[1].load(selected, fixtures[1].fetcher), fixtures[1].data.observations);
  assert.equal(counts.get('competitive_economy'), 2);
  assert.equal(observationCache.size, 3);
  for (const fixture of fixtures) assert.equal(fixture.data.observations[0].excluded, false);
});

test('late failure of an evicted project request cannot remove a successful retry', async () => {
  observationCache.clear();
  const selected = source('late-failure');
  let fail;
  const pending = loadInfrastructureObservations(selected, () => new Promise((resolve, reject) => {fail = reject;}));
  const rejected = assert.rejects(pending, /offline/);
  await Promise.resolve();
  for (const id of ['new-1', 'new-2', 'new-3']) {
    await loadInfrastructureObservations(source(id), async () => response(packet('life_infrastructure', id)));
  }
  const corrected = packet('life_infrastructure', selected.id, 7);
  assert.equal(await loadInfrastructureObservations(selected, async () => response(corrected)), corrected.observations);
  fail(Error('offline'));
  await rejected;
  assert.equal(await loadInfrastructureObservations(selected, async () => {throw Error('unexpected refetch');}), corrected.observations);
});
