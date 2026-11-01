/** Publish current implementation and documentation without recomputing data.
 *
 * public/ and docs/ may contain independently retained analytical editions.
 * This command updates only their code/documentation copies and checksums.
 * It never copies one data tree over the other. Use build.mjs for a deliberate
 * offline recalculation, then review its changes as a separate operation.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const relative = (base, file) => path.relative(base, file).split(path.sep).join('/');
const visible = name => !name.startsWith('.') && name !== '__pycache__' && !name.endsWith('.tmp');

async function files(directory) {
  const entries = await fs.readdir(directory, {withFileTypes: true});
  const result = [];
  for (const entry of entries.sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)) {
    if (!visible(entry.name)) continue;
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await files(filename));
    else if (entry.isFile()) result.push(filename);
    else throw new Error('Unsupported release source entry: ' + filename);
  }
  return result;
}

function category(filename) {
  if (filename.startsWith('code/original/')) return 'original_code';
  if (filename.startsWith('code/platform/')) return 'platform_code';
  if (filename.startsWith('code/frontend/')) return 'frontend_code';
  if (filename.startsWith('documents/') || /\.(docx|pdf)$/.test(filename)) return 'document';
  if (filename.startsWith('documentation/')) return 'platform_code';
  if (filename.startsWith('metadata/')) return 'metadata';
  if (filename.endsWith('.geojson')) return 'geometry';
  if (filename.includes('colab')) return 'notebook';
  if (filename.endsWith('.zip')) return 'raw';
  return 'data';
}

export async function syncReleaseSources(root, {dryRun = false} = {}) {
  root = path.resolve(root);
  const copies = new Map();
  const add = (source, destination) => {
    const existing = copies.get(destination);
    if (existing && existing !== source) throw new Error('Duplicate publication path: ' + destination);
    copies.set(destination, source);
  };
  for (const source of await files(path.join(root, 'src'))) {
    const name = relative(path.join(root, 'src'), source);
    add(source, path.join(root, 'docs/src', name));
    for (const base of ['public', 'docs']) add(source, path.join(root, base, 'downloads/code/frontend', name));
  }
  for (const source of await files(path.join(root, 'scripts'))) {
    if (!/\.(py|mjs|json|txt)$/.test(source)) continue;
    const name = relative(path.join(root, 'scripts'), source);
    for (const base of ['public', 'docs']) add(source, path.join(root, base, 'downloads/code/platform', name));
  }
  const documents = [
    ...await files(path.join(root, 'documentation')),
    ...['README.md', 'NOTICE.md', 'CHANGELOG.md'].map(name => path.join(root, name)),
  ];
  for (const source of documents) {
    for (const base of ['public', 'docs']) add(source, path.join(root, base, 'downloads/documentation', path.basename(source)));
  }
  for (const base of ['public', 'docs']) {
    add(path.join(root, 'requirements-youth-research.txt'), path.join(root, base, 'downloads/code/platform/requirements-youth-research.txt'));
  }

  const changed = [];
  for (const [destination, source] of copies) {
    const bytes = await fs.readFile(source);
    let previous;
    try { previous = await fs.readFile(destination); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (previous?.equals(bytes)) continue;
    changed.push(relative(root, destination));
    if (!dryRun) {
      await fs.mkdir(path.dirname(destination), {recursive: true});
      // Replace the target instead of modifying a possible hardlinked source.
      const temporary = destination + '.tmp';
      await fs.writeFile(temporary, bytes);
      await fs.rename(temporary, destination);
    }
  }

  const indexes = {};
  for (const base of ['public', 'docs']) {
    const downloadRoot = path.join(root, base, 'downloads');
    const indexPath = path.join(downloadRoot, 'index.json');
    const previous = JSON.parse(await fs.readFile(indexPath, 'utf8'));
    const priorEntries = new Map(previous.files.map(entry => [entry.path, entry]));
    const paths = new Set((await files(downloadRoot)).filter(file => file !== indexPath));
    for (const destination of copies.keys()) {
      if (destination.startsWith(downloadRoot + path.sep)) paths.add(destination);
    }
    const entries = [];
    for (const filename of paths) {
      const name = relative(downloadRoot, filename);
      const bytes = await fs.readFile(dryRun && copies.has(filename) ? copies.get(filename) : filename);
      if (bytes.length > 95 * 1024 * 1024) throw new Error('Download exceeds the repository file limit: ' + name);
      const old = priorEntries.get(name);
      entries.push({...old, path: name, title: old?.title || path.basename(name),
        category: old?.category || category(name), bytes: bytes.length, sha256: sha256(bytes)});
    }
    // Match the established index order; hash each tree against its own bytes.
    entries.sort((a, b) => a.path.localeCompare(b.path));
    const serialized = JSON.stringify({...previous, files: entries}, null, 2);
    const priorText = await fs.readFile(indexPath, 'utf8');
    const modified = serialized !== priorText;
    if (modified && !dryRun) {
      const temporary = indexPath + '.tmp';
      await fs.writeFile(temporary, serialized);
      await fs.rename(temporary, indexPath);
    }
    indexes[base] = {files: entries.length, changed: modified, sha256: sha256(serialized)};
  }
  return {schema: 'national-projects.source-sync/1', dry_run: dryRun,
    source_copies_checked: copies.size, changed_copies: changed.length, changed_paths: changed, indexes,
    data_recalculated: false, data_trees_copied: false};
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.some(arg => arg !== '--dry-run')) throw new Error('Usage: node scripts/sync_release_sources.mjs [--dry-run]');
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  console.log(JSON.stringify(await syncReleaseSources(root, {dryRun: args.includes('--dry-run')}), null, 2));
}
