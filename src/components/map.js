import { h, svg, fmt, bindTip, button, codeRegion } from '../core/dom.js';
import { base, ramp, extent, panZoom } from './charts.js';
export function mapView(geo, regions, values, { unit = '', selected = null, onSelect = null, tile = false, title = 'Региональная картограмма', categorical = null, domain = null } = {}) {
    const W = 1050, H = 580, root = base(W, H, title), group = svg('g', {});
    root.append(svg('defs', {}, svg('pattern', { id: 'missing', patternUnits: 'userSpaceOnUse', width: 8, height: 8 }, svg('rect', { width: 8, height: 8, fill: '#F4F6FA' }), svg('path', { d: 'M-2,2L2,-2M0,8L8,0M6,10L10,6', stroke: '#D9DEE8', 'stroke-width': 1.1 }))), group);
    const entries = [...values.values()], numbers = entries.map(v => v.value).filter(Number.isFinite);
    const [lo, hi] = domain || extent(numbers);
    const [tx0, tx1] = extent(regions.map(r => r.tile_x)), [ty0, ty1] = extent(regions.map(r => r.tile_y));
    const dx = Math.min(48, (W - 85) / (tx1 - tx0 + 1)), dy = Math.min(48, (H - 60) / (ty1 - ty0 + 1));
    const tileSize = Math.min(dx, dy), tileLeft = (W - (tx1 - tx0 + 1) * tileSize) / 2, tileTop = (H - (ty1 - ty0 + 1) * tileSize) / 2;
    for (const feature of geo.features) {
        const r = regions.find(r => r.id === feature.id), row = values.get(feature.id);
        const v = row?.value;
        const color = categorical ? categorical.color(row) : Number.isFinite(v) ? ramp((v - lo) / (hi - lo || 1)) : 'url(#missing)';
        let mark;
        if (tile) {
            mark = svg('g', {});
            const x = tileLeft + (r.tile_x - tx0) * tileSize, y = tileTop + (r.tile_y - ty0) * tileSize;
            mark.append(svg('rect', { x, y, width: tileSize - 3, height: tileSize - 3, rx: 3, fill: color, stroke: selected === r.id ? '#0A132D' : '#D9DEE8', 'stroke-width': selected === r.id ? 3 : .6 }), svg('text', { x: x + (tileSize - 3) / 2, y: y + tileSize * .38, 'font-size': 10, 'text-anchor': 'middle', fill: !categorical && Number.isFinite(v) && (v - lo) / (hi - lo) > .66 ? 'white' : '#0A132D', 'font-weight': 700 }, r.tile_label), svg('text', { x: x + (tileSize - 3) / 2, y: y + tileSize * .76, 'font-size': 9, 'text-anchor': 'middle', fill: !categorical && Number.isFinite(v) && (v - lo) / (hi - lo) > .66 ? 'white' : '#0A132D' }, categorical ? row?.category || '—' : Number.isFinite(v) ? fmt(v, 1) : '—'));
        }
        else
            mark = svg('path', { d: feature.path, fill: color, 'fill-rule': 'evenodd', stroke: selected === r.id ? '#0A132D' : '#D9DEE8', 'stroke-width': selected === r.id ? 2.5 : .6, 'vector-effect': 'non-scaling-stroke' });
        mark.setAttribute('tabindex', '0');
        mark.setAttribute('role', 'button');
        mark.setAttribute('aria-label', `${r.name}: ${Number.isFinite(v) ? fmt(v, 4) + ' ' + unit : row?.detail || row?.category || 'нет данных'}`);
        mark.classList.add('region');
        mark.dataset.region = r.id;
        const lines = categorical ? [row?.category || 'Нет данных', row?.detail || ''] : [`${fmt(v, 4)} ${Number.isFinite(v) ? unit : ''}`, row?.end ? `${row.label} ${row.end.slice(0, 4)} · ${row.type}` : '', row?.detail || (row?.flag ? 'Требуется проверка исходного значения' : ''), row?.aliasNote || ''];
        bindTip(mark, r.name, lines, () => onSelect?.(r.id));
        group.append(mark);
    }
    root.dataset.exportLegend = JSON.stringify(categorical ? categorical.legend.map(([color,name])=>({color,name})) : [{name: `${fmt(lo,3)} — ${fmt(hi,3)} ${unit}; светлый → тёмный`,color:ramp(.5)}, {name:'Нет данных — штриховка', color:'#D9DEE8'}]);
    const pan = panZoom(root, group, W, H);
    const wrap = h('div', { class: 'map-surface' }, root, pan.controls, h('div', { class: 'map-hint' }, 'Нажмите на регион · масштаб кнопками или Ctrl + колесо'));
    pan.controls.querySelectorAll('button').forEach((b, i) => { b.setAttribute('aria-label', ['Увеличить карту', 'Уменьшить карту', 'Сбросить масштаб'][i]); b.title = b.getAttribute('aria-label'); });
    if (!categorical) {
        wrap.append(h('div', { class: 'map-legend' }, h('span', {}, fmt(lo, 2)), h('div', { class: 'ramp', style: `background:linear-gradient(90deg,${[0, .25, .5, .75, 1].map(ramp).join(',')})` }), h('span', {}, fmt(hi, 2)), h('span', { class: 'legend-unit' }, unit), h('span', { class: 'missing-key' }, h('i', {}), 'Нет данных')));
    }
    else
        wrap.append(h('div', { class: 'legend' }, categorical.legend.map(([c, label]) => h('span', {}, h('i', { style: `background:${c}` }), label))));
    return { element: wrap, svg: root, zoomTo: pan.zoomTo };
}
