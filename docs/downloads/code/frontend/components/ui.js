import { h, svg, button, icon, fmt, esc, download, csvDownload, select, para, sourceLink, note, announce } from '../core/dom.js';
export function heading(title, description, aside) { return h('header', { class: 'page-heading' }, h('div', {}, h('h1', {}, title), description ? para(description, 'lede') : null), aside || null); }
export function panel(title, subtitle, body, actions) { return h('section', { class: 'panel' }, h('div', { class: 'panel-head' }, h('div', {}, h('h2', {}, title), subtitle ? para(subtitle, 'muted small') : null), actions ? h('div', { class: 'panel-actions' }, actions) : null), body); }
export const toolbar = (...items) => h('div', { class: 'toolbar' }, ...items);
export function stats(items) { return h('div', { class: 'stats' }, items.map(([label, value, detail]) => h('div', { class: 'stat' }, h('span', {}, label), h('strong', {}, value), detail ? h('small', {}, detail) : null))); }
export function tabs(options, selected, fn) { return h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Представление' }, options.map(([v, t]) => h('button', { class: v === selected ? 'active' : '', type: 'button', role: 'tab', 'aria-selected': v === selected, onClick: () => fn(v) }, t))); }
export function table(rows, columns, { pageSize = 12, search = true, filename = 'selection.csv', caption = '', onSelect = null } = {}) {
    const wrap = h('div', { class: 'data-table' }), body = h('div', { class: 'table-scroll', tabindex: '0' }), foot = h('div', { class: 'table-foot' });
    let query = '', page = 0, sortKey = null, dir = 1;
    const data = rows;
    const inp = h('input', { type: 'search', placeholder: 'Поиск по таблице…', 'aria-label': 'Поиск по таблице', onInput: e => { query = e.target.value.toLocaleLowerCase('ru'); page = 0; draw(); } });
    if (search)
        wrap.append(toolbar(inp, button('CSV', () => csvDownload(filename, filtered().map(r => Object.fromEntries(columns.map(c => [c.label, r[c.key] ?? ''])))), 'button subtle', 'download')));
    else
        wrap.append(h('div', { class: 'export-inline' }, button('CSV', () => csvDownload(filename, data), 'button subtle', 'download')));
    wrap.append(body, foot);
    function filtered() { let arr = query ? data.filter(r => columns.some(c => String(r[c.key] ?? '').toLocaleLowerCase('ru').includes(query))) : data.slice(); if (sortKey) {
        arr = arr.slice().sort((a, b) => { let av = a[sortKey], bv = b[sortKey]; if (av == null)
            return 1; if (bv == null)
            return -1; return dir * (typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv), 'ru')); });
    } return arr; }
    function draw() { const arr = filtered(), max = Math.max(1, Math.ceil(arr.length / pageSize)); page = Math.min(page, max - 1); const t = h('table', {}, caption ? h('caption', { class: 'sr-only' }, caption) : null, h('thead', {}, h('tr', {}, columns.map(c => h('th', { scope: 'col', 'aria-sort': sortKey === c.key ? (dir === 1 ? 'ascending' : 'descending') : 'none' }, button(c.label + (sortKey === c.key ? (dir === 1 ? ' ↑' : ' ↓') : ''), () => { dir = sortKey === c.key ? -dir : 1; sortKey = c.key; draw(); }, 'th-button'))))), h('tbody', {}, arr.slice(page * pageSize, (page + 1) * pageSize).map(r => h('tr', { class: onSelect ? 'clickable' : '', onClick: onSelect ? () => onSelect(r) : () => { }, tabindex: onSelect ? '0' : null, onKeydown: e => { if (onSelect && e.key === 'Enter')
            onSelect(r); } }, columns.map(c => h('td', { class: c.numeric ? 'num' : '' }, c.render ? c.render(r[c.key], r) : typeof r[c.key] === 'number' ? fmt(r[c.key], c.decimals ?? 3) : r[c.key] ?? '—')))))); body.replaceChildren(t); if (!arr.length)
        body.append(h('div', { class: 'empty' }, 'Совпадений нет. Измените фильтр.')); foot.replaceChildren(h('span', {}, `${arr.length ? page * pageSize + 1 : 0}–${Math.min((page + 1) * pageSize, arr.length)} из ${arr.length}`), h('div', {}, h('button', { class: 'button subtle', disabled: page === 0, onClick: () => { page--; draw(); }, 'aria-label': 'Предыдущая страница' }, 'Назад'), h('span', { class: 'page-count' }, `${page + 1} / ${max}`), h('button', { class: 'button subtle', disabled: page === max - 1, onClick: () => { page++; draw(); }, 'aria-label': 'Следующая страница' }, 'Далее'))); }
    draw();
    return wrap;
}
export function methodBox(method) { return h('details', { class: 'method-box' }, h('summary', {}, icon('code'), h('span', {}, 'Метод, данные и воспроизведение'), icon('chevron', 15)), h('div', { class: 'method-body' }, h('h3', {}, method.name), para(method.simple), method.formula ? h('div', { class: 'formula' }, method.formula) : null, h('div', { class: 'two-col' }, h('div', {}, h('h4', {}, 'Для каких задач'), para(method.why), h('h4', {}, 'Исходные данные'), para(method.inputs)), h('div', {}, h('h4', {}, 'Повторить в Python'), para(method.python), method.code ? h('pre', {}, h('code', {}, method.code)) : null)), method.caveat ? note(method.caveat, 'warning') : null)); }
export function evidence(text, source = 'Полная экспертиза от 14.05.2026', section = '') { return h('div', { class: 'evidence' }, h('div', { class: 'evidence-rule' }), h('div', {}, h('h3', {}, 'Интерпретация в экспертизе'), para(text), h('a', { href: './downloads/expertise_2026-05-14.docx', class: 'small text-link' }, source + (section ? ' · ' + section : '')))); }
export function empty(title, body) { return h('div', { class: 'empty' }, h('h3', {}, title), para(body)); }
export function sourceFoot(text, path) { return h('div', { class: 'source-foot' }, h('span', {}, text), path ? sourceLink('Исходные данные', path) : null); }
export function figureControls(node, {name='figure',title='Семья',source='Срез экспертизы 14.05.2026',rows=null}={}) {
    const tools=h('div',{class:'figure-tools'},button('SVG',()=>exportSVG(node,name,title,source),'button mini'),button('PNG',()=>exportPNG(node,name,title,source),'button mini'));
    if(rows) tools.append(button('CSV',()=>csvDownload(name+'.csv',rows),'button mini'));
    return tools;
}
export function figure(svgNode, { name = 'figure', title = 'Экспертиза национального проекта «Семья»', source = 'Срез экспертизы 14.05.2026', rows = null } = {}) { const wrap = h('div', { class: 'figure' }), actions = h('div', { class: 'figure-tools' }, button('SVG', () => exportSVG(svgNode, name, title, source), 'button mini'), button('PNG', () => exportPNG(svgNode, name, title, source), 'button mini')); if (rows)
    actions.append(button('CSV', () => csvDownload(name + '.csv', rows), 'button mini')); wrap.append(actions, svgNode); return wrap; }
export function serialized(node, title, source) {
    const copy = node.cloneNode(true);
    const vb = (copy.getAttribute('viewBox') || '0 0 1000 500').split(/\s+/).map(Number);
    const w = vb[2], height = vb[3];
    let legends = [];
    try { legends = JSON.parse(node.dataset.exportLegend || '[]'); } catch { /* optional metadata */ }
    const wrapText = (value, max) => {
        const lines = []; let line = '';
        for (const word of String(value).split(/\s+/)) {
            if ((line + word).length > max && line) { lines.push(line); line = ''; }
            line += (line ? ' ' : '') + word;
        }
        if (line) lines.push(line);
        return lines;
    };
    const titleLines = wrapText(title, Math.floor(w / 10));
    const legendLines = legends.flatMap(item => wrapText(item.name, Math.floor((w - 80) / 7)).map((name, i) => ({ ...item, name, continuation: i > 0 })));
    const sourceLines = wrapText(source, Math.floor((w - 32) / 6));
    const top = titleLines.length * 24 + 16;
    const total = top + height + legendLines.length * 22 + sourceLines.length * 18 + 26;
    const out = svg('svg', { xmlns: 'http://www.w3.org/2000/svg', viewBox: `0 0 ${w} ${total}`, width: w, height: total, style: 'font-family:Arial,sans-serif' },
        svg('rect', {width:w, height:total, fill:'white'}), svg('title', {}, title), svg('desc', {}, source));
    titleLines.forEach((line,i) => out.append(svg('text', {x:16,y:26+i*24,'font-size':17,fill:'#0A132D'}, line)));
    copy.setAttribute('x','0'); copy.setAttribute('y',String(top)); copy.setAttribute('width',String(w)); copy.setAttribute('height',String(height));
    copy.setAttribute('overflow','hidden'); copy.removeAttribute('class'); copy.removeAttribute('data-export-legend');
    out.append(copy);
    let y = top + height + 18;
    legendLines.forEach(item => {
        if (!item.continuation) out.append(svg('line', {x1:16,x2:36,y1:y-4,y2:y-4,stroke:item.color,'stroke-width':5,'stroke-dasharray':item.dash || null}));
        out.append(svg('text', {x:46,y,'font-size':12,fill:'#0A132D'},item.name)); y += 22;
    });
    sourceLines.forEach(line => {out.append(svg('text', {x:16,y,'font-size':11,fill:'#3D4A60'},line)); y += 18;});
    return new XMLSerializer().serializeToString(out);
}
function exportSVG(node, name, title, source) { download(name + '.svg', serialized(node, title, source), 'image/svg+xml;charset=utf-8'); }
async function exportPNG(node, name, title, source) { const xml = serialized(node, title, source), url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' })); try {
    const image = new Image();
    await new Promise((res, rej) => { image.onload = res; image.onerror = rej; image.src = url; });
    const canvas = document.createElement('canvas');
    canvas.width = image.width * 2;
    canvas.height = image.height * 2;
    canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => download(name + '.png', blob), 'image/png');
}
catch (error) { announce('Экспорт PNG не выполнен. Используйте SVG: ' + (error?.message || 'ошибка браузера')); }
    finally {
        URL.revokeObjectURL(url);
    } }
