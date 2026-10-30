import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createJSONLoader} from '../src/core/data.js';
import {createAsyncCache} from '../src/core/cache.js';
import {completeProjectData} from '../src/platform/data.js';
import {completeProjectPages} from '../src/platform/projects.js';
import {familyPages} from '../src/platform/routes.js';
import {createRuntimeLoader, createStylesheetLoader, projectRuntimes} from '../src/platform/runtime.js';

test('bounded asynchronous cache evicts the least recently used result while preserving active callers', async () => {
  const cache = createAsyncCache({maxEntries: 2});
  const first = await cache.getOrCreate('a', async () => ({id: 'a'}));
  await cache.getOrCreate('b', async () => ({id: 'b'}));
  assert.equal(await cache.getOrCreate('a', () => {throw Error('cached');}), first);
  await cache.getOrCreate('c', async () => ({id: 'c'}));
  assert.equal(cache.size, 2);
  assert.equal(cache.has('a'), true);
  assert.equal(cache.has('b'), false);
  assert.equal(first.id, 'a');
  assert.deepEqual(await cache.getOrCreate('b', async () => ({id: 'b', refreshed: true})), {id: 'b', refreshed: true});
  assert.equal(cache.has('a'), false);
});

test('a late rejected request cannot delete a newer request with the same evicted key', async () => {
  const cache = createAsyncCache({maxEntries: 1});
  let rejectOld;
  const old = cache.getOrCreate('a', () => new Promise((resolve, reject) => {rejectOld = reject;}));
  await Promise.resolve();
  await cache.getOrCreate('b', async () => 'b');
  const replacement = cache.getOrCreate('a', async () => 'current a');
  rejectOld(Error('old request failed'));
  await assert.rejects(old, /old request/);
  assert.equal(cache.has('a'), true);
  assert.equal(await replacement, 'current a');
  assert.equal(await cache.getOrCreate('a', () => {throw Error('must remain cached');}), 'current a');
});

test('the shared JSON cache reuses concurrent paths and revalidates only the first HTTP request', async () => {
  const calls = [];
  const data = {value: 0, missing: null};
  const json = createJSONLoader(async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => data};
  });
  const [first, second] = await Promise.all([json('data/regions.json'), json('./data/regions.json')]);
  assert.equal(first, data);
  assert.equal(second, first);
  assert.equal(await json('data/regions.json'), first);
  assert.deepEqual(calls, [{url: './data/regions.json', options: {cache: 'no-cache'}}]);
});

test('HTTP failures and malformed JSON can be retried without reloading the page', async () => {
  let count = 0;
  const json = createJSONLoader(async () => {
    count++;
    if (count === 1) return {ok: false, status: 503};
    if (count === 2) return {ok: true, json: async () => {throw SyntaxError('incomplete JSON');}};
    return {ok: true, json: async () => ({ready: true})};
  });
  await assert.rejects(json('data/retry.json'), /503/);
  await assert.rejects(json('data/retry.json'), /incomplete JSON/);
  assert.deepEqual(await json('data/retry.json'), {ready: true});
  assert.equal(count, 3);
});

test('a partial project failure retries only the failed JSON while retaining successful neighbours', async () => {
  const previous = globalThis.fetch;
  const calls = new Map();
  try {
    globalThis.fetch = async url => {
      const count = (calls.get(url) || 0) + 1;
      calls.set(url, count);
      if (url.endsWith('analytics.json') && count === 1) return {ok: false, status: 502};
      return {ok: true, json: async () => ({url})};
    };
    await assert.rejects(completeProjectData('runtime_retry_fixture'), /502/);
    const bundle = await completeProjectData('runtime_retry_fixture');
    assert.deepEqual(Object.keys(bundle), ['expertise', 'statistics', 'analytics', 'refresh', 'documentary']);
    assert.equal(calls.size, 5);
    for (const [url, count] of calls) assert.equal(count, url.endsWith('analytics.json') ? 2 : 1);
  } finally { globalThis.fetch = previous; }
});

test('all completed projects have real lazy renderer exports and only their own stylesheet', async () => {
  assert.deepEqual(Object.keys(projectRuntimes).sort(), Object.keys(completeProjectPages).sort());
  const styles = [];
  const loader = createRuntimeLoader({stylesheet: async href => {styles.push(href);}});
  for (const [id, descriptor] of Object.entries(projectRuntimes)) {
    const runtime = await loader.study(id);
    assert.equal(runtime.key, descriptor.key);
    assert.equal(typeof runtime.render, 'function');
    assert.equal(styles.at(-1), descriptor.stylesheet);
    await fs.access(new URL('../src/' + descriptor.module.replace('../', ''), import.meta.url));
    await fs.access(new URL('../' + descriptor.stylesheet.replace('./', ''), import.meta.url));
  }
  for (const page of familyPages) assert.equal(typeof await loader.family(page), 'function', page);
  assert.equal(styles.length, Object.keys(projectRuntimes).length);
});

test('requesting one project imports no other project and shares an in-flight module', async () => {
  const imported = [], styles = [];
  let release;
  const wait = new Promise(resolve => {release = resolve;});
  const render = () => {};
  const loader = createRuntimeLoader({
    importer: async specifier => {imported.push(specifier); await wait; return {renderTourism: render};},
    stylesheet: async href => {styles.push(href);}
  });
  const first = loader.study('tourism'), second = loader.study('tourism');
  release();
  assert.equal((await first).render, render);
  assert.equal((await second).render, render);
  assert.deepEqual(imported, ['../pages/tourism.js']);
  assert.ok(styles.every(href => href === './src/tourism.css'));
});

test('a failed module import is not retained by the runtime loader', async () => {
  let attempts = 0;
  const render = () => {};
  const loader = createRuntimeLoader({
    importer: async () => {if (++attempts === 1) throw Error('offline'); return {renderTourism: render};},
    stylesheet: async () => {}
  });
  await assert.rejects(loader.study('tourism'), /offline/);
  assert.equal((await loader.study('tourism')).render, render);
  assert.equal(attempts, 2);
});

test('project styles deduplicate concurrent requests and failed links are removed before retry', async () => {
  const links = [];
  const document = {
    createElement() {
      const listeners = {};
      return {dataset: {}, addEventListener(type, fn) {listeners[type] = fn;},
        remove() {this.removed = true;}, fire(type) {listeners[type]();}};
    },
    head: {append(link) {links.push(link);}}
  };
  const stylesheet = createStylesheetLoader(() => document);
  const failed = stylesheet('./src/tourism.css');
  assert.equal(stylesheet('./src/tourism.css'), failed);
  assert.equal(links.length, 1);
  links[0].fire('error');
  await assert.rejects(failed, /оформление/);
  assert.equal(links[0].removed, true);
  const success = stylesheet('./src/tourism.css');
  assert.equal(links.length, 2);
  links[1].fire('load');
  assert.equal(await success, links[1]);
  assert.equal(await stylesheet('./src/tourism.css'), links[1]);
  assert.equal(links.length, 2);
});

test('shared regional metadata preserves every current catalogue field exactly', async () => {
  const read = async path => JSON.parse(await fs.readFile(new URL('../public/' + path, import.meta.url), 'utf8'));
  const [catalog, shared] = await Promise.all([read('data/current/catalog.json'), read('data/regions.json')]);
  assert.equal(shared.schema, 'national-projects.regions/1');
  assert.deepEqual(shared.regions, catalog.regions);
  assert.equal(new Set(shared.regions.map(region => region.id)).size, 89);
  assert.equal(Object.hasOwn(shared, 'datasets'), false);
});

test('initial HTML contains only shared CSS and direct current PDF links for all projects', async () => {
  const html = await fs.readFile(new URL('../index.html', import.meta.url), 'utf8');
  const styles = [...html.matchAll(/<link rel="stylesheet" href="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(styles, ['./src/styles.css', './src/platform.css']);
  const reports = JSON.parse(await fs.readFile(new URL('../public/data/current-reports.json', import.meta.url), 'utf8'));
  assert.equal(reports.reports.length, 12);
  for (const report of reports.reports) assert.ok(html.includes('href="./' + report.pdf.url + '"'), report.project_id);
  assert.ok(html.includes('research/reports.html'));
  const jsonld = JSON.parse(html.match(/<script type="application\/ld\+json">([^<]+)<\/script>/)[1]);
  assert.ok(jsonld.description.includes('Международная кооперация и экспорт'));
});
