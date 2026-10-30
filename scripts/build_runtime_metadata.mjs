/** Shared regional labels without loading the Family indicator catalogue. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

export async function buildRuntimeMetadata(root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')) {
  const catalog = JSON.parse(await fs.readFile(path.join(root, 'public/data/current/catalog.json'), 'utf8'));
  const regions = catalog.regions;
  if (!Array.isArray(regions) || !regions.length || regions.some(region => !region.id || !region.name) || new Set(regions.map(region => region.id)).size !== regions.length)
    throw Error('The current catalogue must contain distinct regional identifiers and names.');
  const output = path.join(root, 'public/data/regions.json');
  const content = JSON.stringify({schema: 'national-projects.regions/1', regions}) + '\n';
  await fs.writeFile(output, content, 'utf8');
  return {regions: regions.length, bytes: Buffer.byteLength(content)};
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href)
  console.log(JSON.stringify(await buildRuntimeMetadata()));
