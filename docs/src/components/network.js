import { h, svg, fmt, bindTip, button, select, para, codeRegion } from '../core/dom.js';
import { base, C, panZoom } from './charts.js';
import { sourceFoot, table, toolbar, figure } from './ui.js';
const relationship = { direct: 'Прямая', indirect: 'Косвенная', hypothetical: 'Гипотетическая' };
const nodeColor = node => C[(node.group - 1 || 0) % C.length];
export function networkView({ nodes, edges, selected, onSelect, regional = false, focusOnly = true, layout = {} }) {
    const selectedNode = nodes.find(n => n.id === selected) || nodes[0], sid = selectedNode?.id;
    const neighbors = new Set(edges.filter(e => e.a === sid || e.b === sid).flatMap(e => [e.a, e.b]));
    const visible = focusOnly ? nodes.filter(n => neighbors.has(n.id) || n.id === sid) : nodes;
    const visibleIds = new Set(visible.map(n => n.id)), links = edges.filter(e => visibleIds.has(e.a) && visibleIds.has(e.b));
    const w = 950, height = focusOnly ? Math.max(420, Math.min(1000, (visible.length - 1) * 57 + 60)) : 610, root = base(w, height, regional ? 'Сеть статистической схожести регионов' : 'Связи мероприятий и показателей'), g = svg('g', {}), position = new Map();
    root.append(g);
    if (focusOnly) {
        position.set(sid, [220, height / 2]);
        const others = visible.filter(n => n.id !== sid);
        others.forEach((n, i) => position.set(n.id, [550, 40 + (i + .5) * (height - 80) / Math.max(1, others.length)]));
    }
    else if (regional) {
        visible.forEach(n => { const p = layout[n.id] || [0, 0]; position.set(n.id, [w / 2 + p[0] * w * .40, height / 2 + p[1] * height * .41]); });
    }
    else {
        const a = visible.filter(n => n.kind === 'activity'), b = visible.filter(n => n.kind !== 'activity');
        a.forEach((n, i) => position.set(n.id, [220, 35 + i * (height - 70) / Math.max(1, a.length - 1)]));
        b.forEach((n, i) => position.set(n.id, [730, 35 + i * (height - 70) / Math.max(1, b.length - 1)]));
    }
    links.forEach(e => { const a = position.get(e.a), b = position.get(e.b), active = e.a === sid || e.b === sid; const path = svg('path', { d: `M${a[0]},${a[1]}C${(a[0] + b[0]) / 2},${a[1]} ${(a[0] + b[0]) / 2},${b[1]} ${b[0]},${b[1]}`, fill: 'none', stroke: active ? '#539D96' : '#D9DEE8', opacity: active ? .95 : .4, 'stroke-width': regional ? 1 + (e.weight || 0) * 2 : e.type === 'direct' ? 2 : 1.1, 'stroke-dasharray': e.type === 'indirect' ? '5 4' : null }); bindTip(path, regional ? 'Сходство профилей' : relationship[e.type] || 'Связь', [nodes.find(n => n.id === e.a)?.name || e.a, nodes.find(n => n.id === e.b)?.name || e.b, regional ? `Вес: ${fmt(e.weight, 4)}` : 'Экспертная разметка, не оценка воздействия']); g.append(path); });
    for (const n of visible) {
        const [x, y] = position.get(n.id), active = n.id === sid, near = neighbors.has(n.id);
        const group = svg('g', { class: 'network-node', tabindex: 0, role: 'button', 'aria-label': n.name, 'data-node': n.id });
        group.append(svg('circle', { cx: x, cy: y, r: active ? 14 : focusOnly ? 9 : regional ? 8 : 5.5, fill: nodeColor(n), stroke: active ? '#6280D9' : 'white', 'stroke-width': active ? 4 : 1.6, opacity: focusOnly || active || near ? 1 : .7 }));
        const full = focusOnly;
        const label = full ? n.name : n.short || n.id;
        const anchor = focusOnly ? (active ? 'end' : 'start') : regional ? 'middle' : n.kind === 'activity' ? 'end' : 'start', lx = focusOnly ? (active ? x - 24 : x + 20) : regional ? x : n.kind === 'activity' ? x - 15 : x + 15, ly = regional && !full ? y - 15 : y + 4;
        if (full) {
            const words = label.split(' '), lines = [];
            let cur = '';
            for (const word of words) {
                if ((cur + ' ' + word).length > (active ? 27 : 45) && cur) {
                    lines.push(cur);
                    cur = word;
                }
                else
                    cur += (cur ? ' ' : '') + word;
            }
            if (cur)
                lines.push(cur);
            const labelnode = svg('text', { x: lx, y: ly - (Math.min(lines.length, 4) - 1) * 7, 'text-anchor': anchor, fill: '#0A132D', 'font-size': active ? 13 : 12, 'font-weight': active ? 700 : 500, 'pointer-events': 'none' });
            lines.slice(0, 4).forEach((line, i) => labelnode.append(svg('tspan', { x: lx, dy: i ? 15 : 0 }, line + (i === 3 && lines.length > 4 ? '…' : ''))));
            group.append(labelnode);
        }
        else if (!regional || active || near) {
            group.append(svg('text', { x: lx, y: ly, 'text-anchor': anchor, fill: '#3D4A60', 'font-size': regional ? 11 : 10.5, 'pointer-events': 'none' }, label));
        }
        bindTip(group, n.name, [n.kind === 'activity' ? 'Мероприятие' : n.kind === 'indicator' ? 'Показатель' : `Сообщество ${n.group || '—'}`, `Связей в текущей выборке: ${edges.filter(e => e.a === n.id || e.b === n.id).length}`], () => onSelect(n.id));
        g.append(group);
    }
    const pz = panZoom(root, g, w, height);
    pz.controls.querySelectorAll('button').forEach((b, i) => b.setAttribute('aria-label', ['Увеличить сеть', 'Уменьшить сеть', 'Сбросить сеть'][i]));
    const canvas = h('div', { class: 'network-surface' }, root, pz.controls), inspector = h('aside', { class: 'network-inspector' }, h('span', { class: 'eyeline' }, regional ? 'Выбранный регион' : selectedNode?.kind === 'activity' ? 'Мероприятие' : 'Показатель'), h('h3', {}, selectedNode?.name || 'Узел не найден'), selectedNode?.detail ? para(selectedNode.detail, 'small') : null, h('div', { class: 'inspector-count' }, h('strong', {}, neighbors.size ? neighbors.size - 1 : 0), h('span', {}, 'связанных узлов')), h('h4', {}, 'Непосредственные связи'));
    for (const e of edges.filter(e => e.a === sid || e.b === sid)) {
        const other = nodes.find(n => n.id === (e.a === sid ? e.b : e.a));
        if (!other)
            continue;
        inspector.append(h('button', { class: 'neighbor', onClick: () => onSelect(other.id) }, h('span', {}, other.name), h('small', {}, regional ? `Сходство ${fmt(e.weight, 3)}` : relationship[e.type] || '')));
    }
    if (!neighbors.size)
        inspector.append(para('В выбранном фильтре связей нет. Сбросьте фильтр или выберите другой узел.', 'small'));
    const groups=[...new Map(nodes.map(n=>[n.group,{name:n.groupLabel||(regional?'Сообщество '+n.group:n.kind==='indicator'?'Показатели':'Мероприятия'),color:nodeColor(n)}])).values()];
    const nodeKey=h('div',{class:'network-key',role:'group','aria-label':'Цвета узлов'},h('strong',{},regional?'Цвет окружности — сообщество':'Цвет окружности — федеральный проект мероприятия или показатель'),h('div',{class:'legend'},groups.map(item=>h('span',{},h('i',{class:'node-swatch',style:'background:'+item.color,'aria-hidden':'true'}),item.name))));
    const edgeItems=regional?[['selected','Связи выбранного региона'],['other','Остальные связи']]:[['direct','Прямая связь'],['indirect','Косвенная связь'],['selected','Связи выбранного узла'],['other','Остальные связи']];
    const edgeKey=h('div',{class:'network-key',role:'group','aria-label':'Обозначения связей'},h('strong',{},'Линии и выделение'),h('div',{class:'legend'},edgeItems.map(([kind,name])=>h('span',{},h('i',{class:'edge-swatch '+kind,'aria-hidden':'true'}),name)),h('span',{},h('i',{class:'selected-node-swatch','aria-hidden':'true'}),'Обводка — выбранный узел')),para(regional?'Толщина линии отражает вес сходства профилей.':'Цвет линий показывает фокус выбора. Цвет окружностей обозначает принадлежность узлов.','small muted'));
    root.dataset.exportLegend=JSON.stringify([...groups,...edgeItems.map(([kind,name])=>({name,color:kind==='selected'?'#539D96':'#D9DEE8',dash:kind==='indirect'?'5 4':null})),{name:'Обводка — выбранный узел',color:'#6280D9'}]);
    return { element: h('div', {}, h('div',{class:'network-legend'},nodeKey,edgeKey),h('div', { class: 'network-layout' }, canvas, inspector)), svg: root };
}
