import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {syncReleaseSources} from '../scripts/sync_release_sources.mjs';

const hash = value => crypto.createHash('sha256').update(value).digest('hex');

test('release source sync retains distinct published data editions and hashes each download tree', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'platform-source-sync-'));
  const write = async (name, value) => {
    await fs.mkdir(path.dirname(path.join(root, name)), {recursive: true});
    await fs.writeFile(path.join(root, name), value);
  };
  try {
    await write('src/app.js', 'export const version = 3;\n');
    await write('scripts/review.json', '{"review":"published"}\n');
    await write('scripts/helper.py', 'print("source")\n');
    await write('documentation/RELEASE.md', '# Release\n');
    for (const name of ['README.md', 'NOTICE.md', 'CHANGELOG.md', 'requirements-youth-research.txt']) await write(name, name + '\n');
    for (const base of ['public', 'docs']) {
      await write(base + '/data/series.json', JSON.stringify({edition: base}));
      await write(base + '/downloads/data/series.csv', 'edition\n' + base + '\n');
      await write(base + '/downloads/.transfer.tmp', 'ignored');
      await write(base + '/downloads/index.json', JSON.stringify({schema: 'semya.files/1', files: [
        {path: 'data/series.csv', title: 'Original series', category: 'data', bytes: 0, sha256: 'stale'},
      ]}, null, 2));
    }
    const preview = await syncReleaseSources(root, {dryRun: true});
    assert.ok(preview.changed_copies > 0);
    await assert.rejects(fs.access(path.join(root, 'docs/src/app.js')));
    assert.equal(JSON.parse(await fs.readFile(path.join(root, 'public/downloads/index.json'), 'utf8')).files[0].sha256, 'stale');
    const result = await syncReleaseSources(root);
    assert.equal(result.data_recalculated, false);
    assert.equal(result.data_trees_copied, false);
    assert.equal(await fs.readFile(path.join(root, 'docs/src/app.js'), 'utf8'), 'export const version = 3;\n');
    for (const base of ['public', 'docs']) {
      assert.deepEqual(JSON.parse(await fs.readFile(path.join(root, base, 'data/series.json'), 'utf8')), {edition: base});
      assert.equal(await fs.readFile(path.join(root, base, 'downloads/data/series.csv'), 'utf8'), 'edition\n' + base + '\n');
      const index = JSON.parse(await fs.readFile(path.join(root, base, 'downloads/index.json'), 'utf8'));
      const series = index.files.find(file => file.path === 'data/series.csv');
      assert.equal(series.sha256, hash('edition\n' + base + '\n'));
      assert.equal(series.title, 'Original series');
      assert.ok(index.files.some(file => file.path === 'code/platform/review.json'));
      assert.ok(!index.files.some(file => file.path.includes('.transfer')));
    }
    const repeated = await syncReleaseSources(root);
    assert.equal(repeated.changed_copies, 0);
    assert.equal(repeated.indexes.public.changed, false);
    assert.equal(repeated.indexes.docs.changed, false);
  } finally {
    await fs.rm(root, {recursive: true, force: true});
  }
});
