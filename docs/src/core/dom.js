export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export function h(tag, attrs = {}, ...children) { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class')
        e.className = v;
    else if (k === 'html')
        e.innerHTML = v;
    else if (k.startsWith('on'))
        e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k.startsWith('aria-') && v != null) e.setAttribute(k,String(v));
        else if (k === 'dataset')
        Object.assign(e.dataset, v);
    else if (v !== false && v != null)
        e.setAttribute(k, v === true ? '' : v);
} for (const c of children.flat(Infinity)) {
    if (c !== null && c !== undefined && c !== false)
        e.append(c instanceof Node ? c : document.createTextNode(String(c)));
} return e; }
export function svg(tag, attrs = {}, ...children) { const e = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith('on'))
        e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v != null)
        e.setAttribute(k, String(v));
} for (const c of children.flat(Infinity)) {
    if (c != null)
        e.append(c instanceof Node ? c : document.createTextNode(String(c)));
} return e; }
export const icon = (name, size = 18) => { const paths = { trend:'M3 17l5-5 4 2 8-10M15 4h5v5', population:'M4 20V12h4v8m3 0V7h4v13m3 0V3h4v17', table:'M3 4h18v16H3zM3 10h18M9 4v16', users:'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M2 21v-3a7 7 0 0 1 14 0v3M17 4a4 4 0 0 1 0 7m2 3a6 6 0 0 1 3 5v2', menu: 'M4 6h16M4 12h16M4 18h16', close: 'm6 6 12 12M6 18 18 6', download: 'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4', arrow: 'M5 12h14m-5-5 5 5-5 5', search: 'm16 16 5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0', link: 'm9 15 6-6M8 17l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2-1 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0', reset: 'M4 10a8 8 0 1 1 0 5m0-11v6h6', plus: 'M12 4v16M4 12h16', minus: 'M4 12h16', code: 'm8 5-7 7 7 7m8-14 7 7-7 7m-3-15-2 18', info: 'M12 11v6m0-10v1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0', chevron: 'm9 5 7 7-7 7', grid: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z' }; return svg('svg', { viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' }, svg('path', { d: paths[name] || paths.info })); };
export function button(text, fn, cls = 'button', ico) { return h('button', { type: 'button', class: cls, onClick: fn }, ico ? icon(ico) : null, text); }
export function select(label, values, value, onChange) { const inp = h('select', { 'aria-label': label, onChange: e => onChange(e.target.value) }, values.map(x => { let [v, t] = Array.isArray(x) ? x : [x, x]; return h('option', { value: v, selected: String(v) === String(value) }, t); })); return h('label', { class: 'field' }, h('span', {}, label), inp); }
export function check(label, checked, fn) { return h('label', { class: 'check' }, h('input', { type: 'checkbox', checked, onChange: e => fn(e.target.checked) }), label); }
export const note = (text, kind = 'info') => h('div', { class: `note ${kind}` }, icon('info'), h('div', {}, text));
export const para = (text, cls = '') => h('p', { class: cls }, text);
export function download(name, content, type = 'text/plain;charset=utf-8') { const blob = content instanceof Blob ? content : new Blob([content], { type }); const url = URL.createObjectURL(blob); const a = h('a', { href: url, download: name }); a.click(); setTimeout(() => URL.revokeObjectURL(url), 3000); }
export function toCSV(rows, columns) { columns = columns || Object.keys(rows[0] || {}); const q = v => { let s = String(v ?? ''); if (/^[=+@\t\r]/.test(s) || (/^-/.test(s) && !Number.isFinite(Number(s))))
    s = "'" + s; return '"' + s.replaceAll('"', '""') + '"'; }; return '\uFEFF' + [columns.map(q).join(';'), ...rows.map(r => columns.map(c => q(r[c])).join(';'))].join('\r\n'); }
export function csvDownload(name, rows, columns) { download(name, toCSV(rows, columns), 'text/csv;charset=utf-8'); }
export function tooltip(event, title, lines = []) { const e = $('#tooltip'); e.replaceChildren(h('strong', {}, title), ...lines.map(t => h('div', {}, t))); e.hidden = false; const x = event.clientX ?? 30, y = event.clientY ?? 90; requestAnimationFrame(() => { e.style.left = Math.max(8, Math.min(x + 16, innerWidth - e.offsetWidth - 10)) + 'px'; e.style.top = Math.max(8, Math.min(y + 16, innerHeight - e.offsetHeight - 10)) + 'px'; }); }
export const hideTip = () => { const e = $('#tooltip'); if (e)
    e.hidden = true; };
export function bindTip(e, title, lines, click) { e.addEventListener('pointerenter', ev => tooltip(ev, title, typeof lines === 'function' ? lines() : lines)); e.addEventListener('pointermove', ev => tooltip(ev, title, typeof lines === 'function' ? lines() : lines)); e.addEventListener('pointerleave', hideTip); e.addEventListener('focus', () => { const r = e.getBoundingClientRect(); tooltip({ clientX: r.x + r.width / 2, clientY: r.y }, title, typeof lines === 'function' ? lines() : lines); }); e.addEventListener('blur', hideTip); if (click) {
    e.addEventListener('click', ev => { hideTip(); click(ev); });
    e.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        hideTip();
        click(ev);
    } });
} }
export async function copyLink() { try {
    await navigator.clipboard.writeText(location.href);
    announce('Ссылка на выбранный вид скопирована');
}
catch {
    prompt('Ссылка на выбранный вид', location.href);
} }
export function announce(text) { $('#announcer').textContent = text; const t = h('div', { class: 'toast' }, text); document.body.append(t); setTimeout(() => t.remove(), 2800); }
export const fmt = (v, d = 2) => v === null || v === undefined || !Number.isFinite(Number(v)) ? 'Нет данных' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: d }).format(Number(v));
export const codeRegion = v => String(parseInt(v)).padStart(2, '0');
export function sourceLink(text, path) { return h('a', { href: path, download: classifyDownload(path), class: 'text-link' }, icon('download', 15), text); }
function classifyDownload(path) { return path.includes('/downloads/') ? true : null; }
export function article(title, body) { return h('section', { class: 'article-block' }, h('h3', {}, title), ...(Array.isArray(body) ? body : [body]).map(x => typeof x === 'string' ? para(x) : x)); }
