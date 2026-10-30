import {createAsyncCache} from './cache.js';
/** One bounded cache for project JSON; retries and concurrent views share work. */
export function createJSONLoader(fetcher = (...args) => globalThis.fetch(...args), {maxEntries = 24} = {}) {
    const memo = createAsyncCache({maxEntries});
    return function loadJSON(path) {
        const key = String(path).replace(/^\.\//, '');
        return memo.getOrCreate(key, () => fetcher('./' + key, {cache: 'no-cache'}).then(response => {
                if (!response.ok) throw Error(`Файл ${key}: HTTP ${response.status}`);
                return response.json();
            }));
    };
}
export const json = createJSONLoader();
export async function bootstrap() { const [research, manifest, currentCatalog, currentResearch] = await Promise.all([json('data/research.json'), json('data/latest/manifest.json'), json('data/current/catalog.json'), json('data/current/research.json')]); return { catalog:currentCatalog, research:{...research,...currentResearch}, manifest }; }
export async function series(id, mode = 'latest', manifest = null) { manifest ??= await json('data/latest/manifest.json'); const info = manifest.sources?.find(s => s.source_id === id); const latest = info?.published_file; if (!latest) throw Error(`Для источника ${id} не опубликованы актуальные данные.`); const packet = await json(latest); if(packet.source_id!==id) throw Error(`Источник ${id}: опубликованный пакет относится к другому источнику.`); const rows = packet.rows.map(x => Object.fromEntries(packet.columns.map((k, i) => [k, x[i]]))); return { ...packet, rows, usingLatest: true, latestInfo: info, stale: !['updated','unchanged'].includes(info?.state) }; }
// Preserve source values for audit/export, but never treat flagged values as usable measurements.
export function analyticalRow(row) { return row?.flag ? {...row, rawValue:row.value, value:null, detail:'Исключено из расчёта: '+qualityFlag(row.flag)+(Number.isFinite(row.value)?' · исходное значение '+row.value:'')} : row; }
export function qualityFlag(flag) { return ({outside_0_100:'доля вне диапазона 0–100%',negative:'отрицательное значение',missing:'пропуск',conflicting_values:'противоречивые значения'})[flag] || flag; }
export function periods(rows) { const m = new Map(); for (const r of rows) {
    let k = r.type + '|' + r.end;
    if (!m.has(k))
        m.set(k, { key: k, type: r.type, end: r.end, start: r.start, label: r.label, n: 0, regions: new Set() });
    let p = m.get(k);
    p.n++;
    if (r.r && Number.isFinite(r.value))
        p.regions.add(r.r);
} return [...m.values()].map(p => ({ ...p, regions: p.regions.size })).sort((a, b) => a.end.localeCompare(b.end) || a.type.localeCompare(b.type)); }
export function periodText(p) { return `${p.end.slice(0, 4)} · ${p.label} (${p.type})`; }
export function choosePeriod(ps, requested, complete = false) { if (ps.some(p => p.key === requested))
    return requested; const regional = ps.filter(p => p.regions > 0), pool = regional.length ? regional : ps; if (complete) {
    let annual = pool.filter(p => p.type === 'год');
    if (annual.length)
        return annual.at(-1).key;
    let dec = pool.filter(p => p.end.slice(5, 7) === '12');
    if (dec.length)
        return dec.at(-1).key;
} const newest=pool.at(-1)?.end; return (pool.find(p=>p.end===newest&&p.type==='год')||pool.at(-1))?.key || ''; }
export const samePeriod = (r, key) => r.type + '|' + r.end === key;
// Administrative components and parent aggregates stay distinct in raw data. For maps use territory excluding nested autonomous districts when present.
export function regionRows(rows, key) { const grouped = new Map(); for (const r of rows.filter(x => x.r && samePeriod(x, key))) {
    if (!grouped.has(r.r))
        grouped.set(r.r, []);
    grouped.get(r.r).push(r);
} return new Map([...grouped].map(([id, arr]) => { const part = arr.filter(x => /кроме|без.*автоном/i.test(x.territory)); const candidates = part.length ? part : arr; const vals = [...new Set(candidates.filter(x => Number.isFinite(x.value)).map(x => x.value))]; if (vals.length > 1)
    return [id, { ...candidates[0], value: null, flag: 'conflicting_values', alternatives: arr }]; return [id, { ...candidates.find(x => Number.isFinite(x.value)) || candidates[0], alternatives: arr, aliasNote: part.length && arr.length > 1 ? 'Использована область без вложенных автономных округов.' : '' }]; })); }
export function nationalRows(rows) { return rows.filter(r => /^Российская Федерация/.test(r.territory)); }
export function metaUnit(d) { return d.unit === 'процент' ? '%' : d.id === 'data_31' || d.id === 'data_32' ? '‰' : d.id === 'data_21' || d.id === 'data_22' ? 'детей на женщину' : d.unit || ''; }
export function rawPath(name) { return './downloads/data/' + encodeURIComponent(name + '.csv'); }
export function datasetForFile(cat, file) { return cat.datasets.find(d => d.source_file === file); }
