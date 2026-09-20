import { h, button, select, check, para, note, fmt, sourceLink, codeRegion, csvDownload } from '../core/dom.js';
import { json, series, periods, periodText, choosePeriod, regionRows, samePeriod, metaUnit, nationalRows, rawPath } from '../core/data.js';
import { mean, median, quantile } from '../core/stats.js';
import { heading, panel, toolbar, stats, table, methodBox, evidence, sourceFoot, figure, empty } from '../components/ui.js';
import { mapView } from '../components/map.js';
import { lineChart, legend, C, bars } from '../components/charts.js';
import { sections } from '../content/sections.js';
export async function atlas(ctx) {
    const { catalog, research, state, set, go } = ctx, s = sections.find(x => x.id === 'map'), id = catalog.datasets.some(d => d.id === state.source) ? state.source : 'data_21', d = catalog.datasets.find(d => d.id === id), data = await series(id, state.mode, ctx.manifest), geo = await json('data/map.json'), ps = periods(data.rows), pk = choosePeriod(ps, state.period, true), p = ps.find(p => p.key === pk), rm = regionRows(data.rows, pk), unit = metaUnit(d);
    const fd = state.fd || '', regions = fd ? catalog.regions.filter(r => r.federal_district === fd) : catalog.regions, ids = new Set(regions.map(r => r.id));
    const values = new Map([...rm].filter(([id]) => ids.has(id)));
    let selected = catalog.regions.find(r => r.id === state.r), cmp = catalog.regions.find(r => r.id === state.compare);
    const vals = [...values.values()].map(r => r.value).filter(Number.isFinite);
    const root = h('div', {}, heading(s.title, s.description));
    root.append(toolbar(select('Показатель', catalog.datasets.map(d => [d.id, d.label]), id, v => set({ source: v, period: null })), select('Период и тип наблюдения', ps.slice().reverse().map(p => [p.key, periodText(p)]), pk, v => set({ period: v })), select('Округ', [['', 'Все территории'], ...[...new Set(catalog.regions.map(r => r.federal_district))].map(v => [v, v])], fd, v => set({ fd: v })), button(state.view === 'tile' ? 'Показать географию' : 'Плиточная карта', () => set({ view: state.view === 'tile' ? 'map' : 'tile' }), 'button subtle', 'grid')));
    if (!data.usingLatest && state.mode === 'latest')
        root.append(note('Для этого источника ещё нет проверенного обновления. Показан архивный срез от 14.05.2026, а не новые данные.', 'warning'));
    if (data.stale) root.append(note('Показан последний успешный приём от '+(data.latestInfo.fetched_at||'неизвестной даты')+'. Последующая проверка источника не завершилась: '+data.latestInfo.message,'warning'));
    root.append(stats([['Источник', d.indicator_code, d.id + ' · ' + (data.usingLatest ? 'обновлённая серия' : 'срез экспертизы')], ['Территорий с числом', `${vals.length} / ${regions.length}`, p ? periodText(p) : ''], ['Медиана регионов', fmt(median(vals), 3), unit + ' · без взвешивания по населению'], ['Диапазон значений', vals.length ? `${fmt(Math.min(...vals), 2)} – ${fmt(Math.max(...vals), 2)}` : '—', unit + ' · не оценка эффективности']]));
    const m = mapView(geo, catalog.regions, values, { unit, selected: selected?.id, onSelect: r => set({ r }), tile: state.view === 'tile', title: d.label + ' · ' + periodText(p) }), aside = h('div', { class: 'atlas-aside' }, select('Регион', [['', 'Выберите на карте'], ...catalog.regions.map(r => [r.id, r.name])], selected?.id || '', v => set({ r: v })));
    if (selected) {
        const r = rm.get(selected.id);
        aside.append(h('div', { class: 'region-reading' }, h('h2', {}, selected.name), h('strong', {}, fmt(r?.value, 4)), h('span', {}, unit), para(`${p.label} ${p.end.slice(0, 4)} · ${p.type}`, 'small muted')), ...(r?.flag ? [note('Значение имеет флаг качества: ' + r.flag + '. Оно сохранено, а не заменено.', 'warning')] : []), ...(r?.aliasNote ? [para(r.aliasNote, 'small muted')] : []), para(selected.federal_district, 'small'), button('Приблизить регион', () => m.zoomTo(geo.features.find(f => f.id === selected.id).bounds), 'button subtle'), select('Сравнить с регионом', [['', 'Без сравнения'], ...catalog.regions.filter(r => r.id !== selected.id).map(r => [r.id, r.name])], cmp?.id || '', v => set({ compare: v })));
        if (cmp) {
            const cr = rm.get(cmp.id);
            aside.append(h('div', { class: 'comparison-reading' }, h('span', {}, cmp.name), h('strong', {}, fmt(cr?.value, 4)), h('small', {}, Number.isFinite(r?.value) && Number.isFinite(cr?.value) ? `Разность: ${fmt(r.value - cr.value, 4)} ${unit}` : 'Нет сопоставимых значений')));
        }
    }
    else
        aside.append(h('h2', {}, 'Регион крупным планом'), para('Наведите курсор, чтобы прочитать значение. Нажмите на регион, чтобы открыть его динамику, сопоставить с другой территорией и скачать профиль.'), h('div', { class: 'range-summary' }, h('span', {}, `Нижний квартиль: ${fmt(quantile(vals, .25), 3)}`), h('span', {}, `Верхний квартиль: ${fmt(quantile(vals, .75), 3)}`)), note('Светлый цвет означает меньшее число; тёмный — большее. Направление цвета не меняется для «положительных» и «отрицательных» показателей.'));
    root.append(panel(d.label, `${d.source_file} · ${periodText(p)} · ${unit}`, h('div', { class: 'atlas-layout' }, figure(m.element.querySelector('svg'), { name: id + '_' + p.end, title: d.label, source: `ЕМИСС; ${periodText(p)}; ${data.usingLatest ? 'проверенное обновление' : 'архив 14.05.2026'}` }), aside)));
    // Move map controls and legend with its SVG into the figure container.
    const fg = root.querySelector('.figure');
    fg.append(m.element);
    m.element.prepend(fg.querySelector('svg'));
    root.append(sourceFoot('Проекция LAEA; пользовательская геометрия. Серый штрих — отсутствие наблюдения.', './downloads/ru_regions.geojson'));
    if (!d.regional_count)
        root.append(note('В исходной выгрузке этот показатель имеет только федеральные значения. Пустая картограмма не означает нулевых значений в регионах.', 'warning'));
    if (selected) {
        const idsChosen = [selected.id, ...cmp ? [cmp.id] : []];
        const chartSeries = idsChosen.map((id, i) => { const history = ps.filter(pp => pp.type === p.type).map(pp => regionRows(data.rows, pp.key).get(id) || {end: pp.end, value: null, label: pp.label, year: pp.end.slice(0, 4), type: pp.type}); return { name: catalog.regions.find(r => r.id === id).name, color: C[i === 0 ? 0 : 2], points: history.map(r => ({ x: Date.parse(r.end), y: r.value, label: `${r.label} ${r.year} · ${r.type}` })) }; });
        root.append(panel('Динамика выбранных территорий', `Только тип периода «${p.type}». Пропуски не интерполируются.`, h('div', {}, legend(chartSeries), figure(lineChart(chartSeries, { unit, height: 320, label: d.label }), { name: 'region_history_' + id, title: d.label, source: 'Однородный тип периода; числа из выбранной версии данных' }))));
        if (id === 'data_21' || id === 'data_22') {
            const otherId = id === 'data_21' ? 'data_22' : 'data_21';
            const otherPacket = await series(otherId, state.mode, ctx.manifest);
            const otherMap = regionRows(otherPacket.rows, pk);
            if (data.usingLatest === otherPacket.usingLatest) {
                const totalMap = id === 'data_21' ? rm : otherMap;
                const thirdMap = id === 'data_22' ? rm : otherMap;
                const shares = idsChosen.map(rid => {
                    const total = totalMap.get(rid)?.value, third = thirdMap.get(rid)?.value;
                    return { region: catalog.regions.find(r => r.id === rid).name, total, third,
                        share: Number.isFinite(total) && total > 0 && Number.isFinite(third) ? 100 * third / total : null,
                        period: periodText(p), basis: data.usingLatest ? 'Проверенный слой ЕМИСС' : 'Архив экспертизы' };
                });
                root.append(panel('Вклад третьих и последующих рождений в СКР',
                    'Дополнительный расчёт по двум источникам за строго одинаковый период.',
                    h('div', {class: 'parity-share'},
                        h('div', {class: 'formula'}, 'ПДСКР 3+ = СКР 3+ / СКР × 100%'),
                        table(shares, [{key:'region',label:'Территория'}, {key:'total',label:'СКР',numeric:true,decimals:4},
                            {key:'third',label:'СКР 3+',numeric:true,decimals:4}, {key:'share',label:'Вклад, %',numeric:true,decimals:2},
                            {key:'period',label:'Период'}], {pageSize:2,filename:'parity_share_'+selected.id+'.csv'}),
                        note('Отношение характеризует вклад компоненты в периодный СКР. Оно не является вероятностью рождения третьего ребёнка или долей многодетных женщин. При отсутствии одной компоненты результат не рассчитывается.'),
                        sourceFoot('Расчёт платформы: data_21 и data_22, '+periodText(p)+'. Основание показателя: раздел 3 экспертизы.', './downloads/expertise_2026-05-14.docx'))));
            } else root.append(note('Вклад СКР 3+ не рассчитан: у двух компонентов разные версии данных. Выберите общий архивный срез или дождитесь успешной проверки обоих источников.', 'warning'));
        }
        const profile = research.regional_last_complete_year_values_89_long.filter(r => codeRegion(r.region_code) === selected.id).map(r => ({ name: catalog.datasets.find(d => d.id === r.source_id)?.label || r.source_id, value: r.value, period: `${r.period_label || ''} ${r.year || ''}`, unit: r.unit, source: r.source_file }));
        root.append(panel('Профиль последнего полного периода', 'Фиксированный профиль экспертизы. Периоды разных индикаторов явно показаны.', table(profile, [{ key: 'name', label: 'Показатель' }, { key: 'value', label: 'Значение', numeric: true }, { key: 'period', label: 'Период' }, { key: 'unit', label: 'Единица' }], { pageSize: 12, filename: `profile_${selected.id}.csv` })));
    }
    const tableRows = regions.map(r => { const v = rm.get(r.id); return { id: r.id, region: r.name, district: r.federal_district, value: v?.value, unit, period: periodText(p), original: v?.territory || '', flag: v?.flag || '', alternatives: v?.alternatives?.length || 0 }; });
    root.append(panel('Все региональные значения', 'Нажатие на строку открывает регион. Сортировка — по заголовку столбца.', table(tableRows, [{ key: 'region', label: 'Территория' }, { key: 'value', label: unit, numeric: true, decimals: 4 }, { key: 'flag', label: 'Флаг качества' }, { key: 'original', label: 'Наименование источника' }], { pageSize: 10, onSelect: r => set({ r: r.id }), filename: `${id}_${p.end}_regions.csv` })), methodBox(s.method), evidence(s.finding + ' ' + s.proposal, 'Полная экспертиза от 14.05.2026', `раздел 5, с. ${s.pages}`));
    return root;
}
