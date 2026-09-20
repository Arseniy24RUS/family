import { h, svg, fmt, bindTip, button, icon, tooltip, hideTip } from '../core/dom.js';
import { quantile, mean } from '../core/stats.js';
export const C = ['#2947A0','#539D96','#6280D9','#031E4F','#67AEA7','#7F92BB','#315C83','#A7DBD6'];
export const fieldColors = {HH:'#2947A0',LL:'#A7DBD6',HL:'#6280D9',LH:'#539D96',NS:'#EEF3F9'};
export function ramp(t) {
 t=Math.max(0,Math.min(1,t));
 const stops=[[238,243,249],[215,239,235],[167,219,214],[103,174,167],[83,157,150],[68,107,164],[41,71,160],[25,47,112],[3,30,79]];
 const u=t*8,i=Math.min(7,Math.floor(u)),f=u-i;
 return '#'+stops[i].map((c,j)=>Math.round(c+(stops[i+1][j]-c)*f).toString(16).padStart(2,'0')).join('');
}
export function extent(values) { const a = values.filter(Number.isFinite); if (!a.length)
    return [0, 1]; let lo = Math.min(...a), hi = Math.max(...a); if (lo === hi) {
    const d = Math.abs(lo) * .1 || 1;
    lo -= d;
    hi += d;
} return [lo, hi]; }
export function base(w = 1000, ht = 400, label = 'Диаграмма') { return svg('svg', { viewBox: `0 0 ${w} ${ht}`, class: 'chart-svg', role: 'img', 'aria-label': label, style: 'font-family:Onest,Segoe UI,Arial,sans-serif' }, svg('title', {}, label)); }
function text(x, y, t, opts = {}) { return svg('text', { x, y, 'font-size': 12, fill: '#3D4A60', ...opts }, t); }
const compactAxis = new Intl.NumberFormat('ru-RU', { notation:'compact', maximumFractionDigits:2 });
const axisValue = value => Math.abs(value)>=10000 ? compactAxis.format(value) : fmt(value,3);
function grid(root, x, y, w, ht, lo, hi, n = 4) { for (let i = 0; i <= n; i++) {
    let yy = y + ht - ht * i / n;
    root.append(svg('line', { x1: x, x2: x + w, y1: yy, y2: yy, stroke: '#F4F6FA' }), text(x - 12, yy + 4, axisValue(lo + (hi - lo) * i / n), { 'text-anchor': 'end', class:'axis-y-label' }));
} }
export function lineChart(series, {
    height=380, width=1000, unit='', label='Динамика показателя', band=null,
    xLabel='Период', zero=false, tickPlacement='end', forecastStart=null, monthlyTicks=false
}={}) {
    const root=base(width,height,label);
    const m={l:width<440?52:64,r:width<440?15:24,t:38,b:54},H=height-m.t-m.b;
    const all=series.flatMap(s=>s.points).filter(p=>Number.isFinite(p.y)&&Number.isFinite(p.x));
    if(!all.length){root.append(text(width/2,height/2,'Нет сопоставимых наблюдений',{'text-anchor':'middle'}));return root;}
    const [x0,x1]=extent(all.map(p=>p.x)),ys=all.map(p=>p.y);
    if(band)ys.push(...band.flatMap(p=>[p.lo,p.hi]).filter(Number.isFinite));
    let [y0,y1]=extent(ys);if(zero&&y0>0)y0=0;
    const pad=(y1-y0)*.1;y0-=pad;y1+=pad;
    const ticks=width<440?3:4;
    m.l=Math.max(m.l,...Array.from({length:ticks+1},(_,i)=>axisValue(y0+(y1-y0)*i/ticks).length*7+18));
    const W=width-m.l-m.r;
    const X=x=>m.l+(x-x0)/(x1-x0)*W,Y=y=>m.t+H-(y-y0)/(y1-y0)*H;
    if(Number.isFinite(forecastStart)&&forecastStart>=x0&&forecastStart<=x1){
        const x=X(forecastStart);
        root.append(svg('rect',{x,y:m.t,width:width-m.r-x,height:H,fill:'#F4F6FA',opacity:.55}));
        root.append(svg('line',{x1:x,x2:x,y1:m.t-7,y2:height-m.b,stroke:'#9FAEC7','stroke-dasharray':'4 4'}));
        root.append(text(width-m.r,20,'Прогноз',{'font-size':11,fill:'#647087','text-anchor':'end'}));
    }
    grid(root,m.l,m.t,W,H,y0,y1,width<440?3:4);
    root.append(text(m.l,20,unit,{'font-size':11,fill:'#647087'}));
    const years=[...new Set(all.map(p=>new Date(p.x).getUTCFullYear()))];
    const tickLimit=Math.max(3,Math.min(9,Math.floor(W/65)));
    if(monthlyTicks&&x1-x0<32*31*86400000){
        const start=new Date(x0),end=new Date(x1),startId=start.getUTCFullYear()*12+start.getUTCMonth(),endId=end.getUTCFullYear()*12+end.getUTCMonth();
        const step=Math.max(3,Math.ceil((endId-startId+1)/Math.max(3,Math.floor(W/85))/3)*3);
        for(let id=startId;id<=endId;id+=step){
            const y=Math.floor(id/12),mm=id%12,date=Date.UTC(y,mm+1,0),xx=X(date);
            if(xx>=m.l-1&&xx<=width-m.r+1)root.append(text(xx,height-29,String(mm+1).padStart(2,'0')+'.'+String(y).slice(2),{'text-anchor':'middle','font-size':11}));
        }
    }else{
        for(const [i,y] of years.entries()){
            if(i%Math.ceil(years.length/tickLimit)!==0)continue;
            let xx=X(tickPlacement==='start'?Date.UTC(y,0,1):Date.UTC(y,11,31));
            if(i===0&&xx<m.l&&tickPlacement==='start')xx=m.l;
            if(xx>=m.l-1&&xx<=width-m.r+1)root.append(text(xx,height-29,y,{'text-anchor':'middle','font-size':11}));
        }
    }
    if(band?.length){
        const b=band.filter(p=>Number.isFinite(p.lo)&&Number.isFinite(p.hi)).sort((a,b)=>a.x-b.x);
        if(b.length)root.append(svg('path',{class:'forecast-band',d:'M'+b.map(p=>`${X(p.x)},${Y(p.hi)}`).join('L')+'L'+b.slice().reverse().map(p=>`${X(p.x)},${Y(p.lo)}`).join('L')+'Z',fill:'#DCE7F6',opacity:.8}));
    }
    series.forEach((s,i)=>{
        const ordered=s.points.filter(p=>Number.isFinite(p.x)).sort((a,b)=>a.x-b.x),ps=ordered.filter(p=>Number.isFinite(p.y)),color=s.color||C[i%C.length];
        if(!ps.length)return;
        const line=svg('path',{class:'data-line',d:ordered.reduce((out,p,j)=>Number.isFinite(p.y)?out+((j===0||!Number.isFinite(ordered[j-1].y))?'M':'L')+`${X(p.x)},${Y(p.y)}`:out,''),fill:'none',stroke:color,'stroke-width':s.width||2.5,'stroke-dasharray':s.dash||null,'stroke-linecap':'round','stroke-linejoin':'round'});
        line.dataset.series=s.name;root.append(line);
        const visible=s.markers!==false&&(s.markers===true||ps.length<=24);
        ps.forEach((p,j)=>{
            if(visible)root.append(svg('circle',{cx:X(p.x),cy:Y(p.y),r:s.radius||3,fill:color,stroke:'#fff','stroke-width':1}));
            const hit=svg('circle',{class:'point-hit',cx:X(p.x),cy:Y(p.y),r:7,fill:'transparent',tabindex:j%Math.max(1,Math.floor(ps.length/15))===0?0:null});
            bindTip(hit,s.name,[p.label||new Date(p.x).toLocaleDateString('ru-RU'),`${fmt(p.y,4)} ${unit}`]);root.append(hit);
        });
    });
    root.dataset.exportLegend=JSON.stringify(series.map((s,i)=>({name:s.name,color:s.color||C[i%C.length],dash:s.dash||null})));
    root.append(text(width/2,height-5,xLabel,{'text-anchor':'middle','font-size':11}));
    return root;
}
export function legend(items) { return h('div', { class: 'legend' }, items.map((x, i) => h('span', {}, h('i', { style: `background:${x.color || C[i % C.length]}` }), x.name || x))); }
export function bars(items, { width = 1000, height = null, label = 'Сопоставление значений', unit = '', horizontal = true } = {}) { height = height || Math.max(240, items.length * 42 + 60); const root = base(width, height, label), l = horizontal ? Math.min(width * .38, 340) : 65, r = 45, t = 30, b = horizontal ? 22 : 65; let [lo, hi] = extent(items.map(x => x.value)); lo = Math.min(0, lo); hi = Math.max(0, hi); const W = width - l - r, H = height - t - b; if (horizontal) {
    const xx = v => l + (v - lo) / (hi - lo) * W;
    for (let i = 0; i < 5; i++) {
        let v = lo + (hi - lo) * i / 4, x = xx(v);
        root.append(svg('line', { x1: x, x2: x, y1: t - 5, y2: height - b, stroke: '#F4F6FA' }), text(x, 16, fmt(v, 2), { 'text-anchor': 'middle' }));
    }
    items.forEach((a, i) => { const yy = t + (i + .5) * H / items.length, rect = svg('rect', { x: Math.min(xx(0), xx(a.value)), y: yy - 10, width: Math.max(1, Math.abs(xx(a.value) - xx(0))), height: 20, rx: 2, fill: a.color || C[i % C.length], tabindex: 0 }); bindTip(rect, a.name, [`${fmt(a.value, 4)} ${unit}`], a.click); root.append(text(l - 12, yy + 4, a.short || a.name, { 'text-anchor': 'end', 'font-size': 13 }), rect, text(Math.min(width - 6, xx(a.value) + 8), yy + 4, fmt(a.value, 2), { 'font-weight': 600, fill: '#0A132D' })); });
}
else {
    const Y = v => t + H - (v - lo) / (hi - lo) * H;
    grid(root, l, t, W, H, lo, hi);
    const bw = W / items.length;
    items.forEach((a, i) => { let x = l + bw * (i + .18); const rect = svg('rect', { x, y: Y(a.value), width: bw * .64, height: Math.abs(Y(0) - Y(a.value)), rx: 3, fill: a.color || C[i % C.length], tabindex: 0 }); bindTip(rect, a.name, [`${fmt(a.value, 4)} ${unit}`], a.click); root.append(rect, text(x + bw * .32, height - 38, a.short || a.name, { 'text-anchor': 'middle' }), text(x + bw * .32, Y(a.value) - 10, fmt(a.value, 2), { 'text-anchor': 'middle', fill: '#0A132D', 'font-weight': 600 })); });
} return root; }
export function scatter(points, { width = 1000, height = 480, xLabel = '', yLabel = '', label = 'Распределение регионов', onSelect = null, selected = null, zeroLines = false } = {}) { const root = base(width, height, label), m = { l: 80, r: 30, t: 35, b: 70 }, W = width - m.l - m.r, H = height - m.t - m.b; const ps = points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y)); if (!ps.length) {
    root.append(text(300, 160, 'Нет пар наблюдений'));
    return root;
} let [x0, x1] = extent(ps.map(x => x.x)), [y0, y1] = extent(ps.map(x => x.y)); const dx = (x1 - x0) * .1, dy = (y1 - y0) * .1; x0 -= dx; x1 += dx; y0 -= dy; y1 += dy; const X = x => m.l + (x - x0) / (x1 - x0) * W, Y = y => m.t + H - (y - y0) / (y1 - y0) * H; grid(root, m.l, m.t, W, H, y0, y1); for (let i = 0; i < 6; i++)
    root.append(text(m.l + i * W / 5, height - 43, fmt(x0 + i * (x1 - x0) / 5), { 'text-anchor': 'middle' })); if (zeroLines) {
    root.append(svg('line', { x1: X(0), x2: X(0), y1: m.t, y2: height - m.b, stroke: '#D9DEE8', 'stroke-dasharray': '4 4' }), svg('line', { x1: m.l, x2: width - m.r, y1: Y(0), y2: Y(0), stroke: '#D9DEE8', 'stroke-dasharray': '4 4' }));
} ps.forEach(p => { let e = svg('circle', { cx: X(p.x), cy: Y(p.y), r: p.id === selected ? 8 : 5.5, fill: p.color || C[(p.group - 1 || 0) % C.length], stroke: p.id === selected ? '#0A132D' : 'white', 'stroke-width': p.id === selected ? 3 : 1.1, tabindex: 0, role: onSelect ? 'button' : null, 'aria-label': `${p.name}: ${fmt(p.x)}, ${fmt(p.y)}` }); bindTip(e, p.name, [`${xLabel}: ${fmt(p.x, 4)}`, `${yLabel}: ${fmt(p.y, 4)}`, p.detail || ''], () => onSelect?.(p)); root.append(e); if (p.id === selected)
    root.append(text(X(p.x) + 12, Y(p.y) - 10, p.name, { fill: '#0A132D', 'font-weight': 700 })); }); root.append(text(m.l + W / 2, height - 12, xLabel.length > 116 ? xLabel.slice(0,113)+'…' : xLabel, { 'text-anchor': 'middle', 'font-size': 11 }), text(m.l, 19, yLabel.length > 116 ? yLabel.slice(0,113)+'…' : yLabel, { 'font-size': 11 })); return root; }
export function heatmap(rowLabels, colLabels, values, { width = 1000, cellHeight = 52, label = 'Матрица', min = 0, max = null, format = v => fmt(v, 2), onSelect = null, colors = null, left = 220 } = {}) { const top = 70, hgt = top + rowLabels.length * cellHeight + 20, root = base(width, hgt, label), cw = (width - left - 25) / colLabels.length; max = max ?? Math.max(...values.flat().filter(Number.isFinite)); colLabels.forEach((c, i) => root.append(text(left + (i + .5) * cw, top - 18, c, { 'text-anchor': 'middle', 'font-size': 12 }))); rowLabels.forEach((r, j) => { root.append(text(left - 12, top + (j + .5) * cellHeight + 4, r, { 'text-anchor': 'end', 'font-size': 13 })); colLabels.forEach((c, i) => { const v = values[j][i], t = (v - min) / (max - min || 1), rect = svg('rect', { x: left + i * cw + 2, y: top + j * cellHeight + 2, width: cw - 4, height: cellHeight - 4, rx: 3, fill: v == null ? '#F4F6FA' : colors ? colors(v) : ramp(t), tabindex: 0 }); bindTip(rect, r, [`${c}: ${v == null ? 'Нет данных' : format(v)}`], () => onSelect?.(j, i)); root.append(rect, text(left + (i + .5) * cw, top + (j + .5) * cellHeight + 5, v == null ? '—' : format(v), { 'text-anchor': 'middle', 'font-size': 14, fill: t > .65 ? 'white' : '#0A132D', 'font-weight': 600, 'pointer-events': 'none' })); }); }); return root; }
export function panZoom(root, group, width, height) { let z = 1, tx = 0, ty = 0, start = null, dragged = false; const apply = () => group.setAttribute('transform', `translate(${tx} ${ty}) scale(${z})`); const set = (newz, cx = width / 2, cy = height / 2) => { newz = Math.max(1, Math.min(8, newz)); tx = cx - (cx - tx) * newz / z; ty = cy - (cy - ty) * newz / z; z = newz; if (z === 1) {
    tx = 0;
    ty = 0;
} apply(); }; const point = e => { const r = root.getBoundingClientRect(); return [(e.clientX - r.left) * width / r.width, (e.clientY - r.top) * height / r.height]; }; root.addEventListener('wheel', e => { if (!e.ctrlKey)
    return; e.preventDefault(); const [x, y] = point(e); set(z * (e.deltaY < 0 ? 1.12 : .88), x, y); }, { passive: false }); root.addEventListener('pointerdown', e => { if (e.button !== 0)
    return; start = { xy: point(e), tx, ty, id: e.pointerId }; dragged = false; }); root.addEventListener('pointermove', e => { if (!start || e.buttons !== 1)
    return; const p = point(e), dx = p[0] - start.xy[0], dy = p[1] - start.xy[1]; if (Math.abs(dx) + Math.abs(dy) > 5) {
    dragged = true;
    root.setPointerCapture(e.pointerId);
    tx = start.tx + dx;
    ty = start.ty + dy;
    apply();
    hideTip();
} }); root.addEventListener('pointerup', () => { start = null; }); root.addEventListener('click', e => { if (dragged) {
    e.stopImmediatePropagation();
    e.preventDefault();
    dragged = false;
} }, true); return { controls: h('div', { class: 'zoom-controls' }, button('', () => set(z * 1.45), 'icon-button', 'plus'), button('', () => set(z / 1.45), 'icon-button', 'minus'), button('', () => { z = 1; tx = ty = 0; apply(); }, 'icon-button', 'reset')), zoomTo(bounds) { const [[x0, y0], [x1, y1]] = bounds; z = Math.min(6, Math.max(1, Math.min(width / (x1 - x0 + 80), height / (y1 - y0 + 80)))); tx = width / 2 - z * (x0 + x1) / 2; ty = height / 2 - z * (y0 + y1) / 2; apply(); } }; }
