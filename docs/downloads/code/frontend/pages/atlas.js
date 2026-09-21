import { h, button, select, check, para, note, fmt, sourceLink, codeRegion, csvDownload } from '../core/dom.js';
import { json, series, periods, periodText, choosePeriod, regionRows, samePeriod, metaUnit, nationalRows, rawPath, analyticalRow, qualityFlag } from '../core/data.js';
import { mean, median, quantile } from '../core/stats.js';
import { heading, panel, toolbar, stats, table, methodBox, evidence, sourceFoot, figure, empty } from '../components/ui.js';
import { mapView } from '../components/map.js';
import { lineChart, legend, C, bars } from '../components/charts.js';
import { sections } from '../content/sections.js';
export async function atlas(ctx) {
    const { catalog, research, state, set, go } = ctx, s = sections.find(x => x.id === 'map'), id = catalog.datasets.some(d => d.id === state.source) ? state.source : 'data_21', d = catalog.datasets.find(d => d.id === id), data = await series(id, state.mode, ctx.manifest), geo = await json('data/map.json'), ps = periods(data.rows), pk = choosePeriod(ps, state.period, state.mode === 'baseline'), p = ps.find(p => p.key === pk), rawMap = regionRows(data.rows, pk), rm = new Map([...rawMap].map(([id,row])=>[id,analyticalRow(row)])), unit = metaUnit(d);
    const fd = state.fd || '', regions = fd ? catalog.regions.filter(r => r.federal_district === fd) : catalog.regions, ids = new Set(regions.map(r => r.id));
    const values = new Map([...rm].filter(([id]) => ids.has(id)));
    let selected = catalog.regions.find(r => r.id === state.r), cmp = catalog.regions.find(r => r.id === state.compare);
    const vals = [...values.values()].map(r => r.value).filter(Number.isFinite);
    const root = h('div', {}, heading(s.title, s.description));
    root.append(toolbar(select('Показатель', catalog.datasets.map(d => [d.id, d.label]), id, v => set({ source: v, period: null })), select('Период и тип наблюдения', ps.slice().reverse().map(p => [p.key, periodText(p)]), pk, v => set({ period: v })), select('Округ', [['', 'Все территории'], ...[...new Set(catalog.regions.map(r => r.federal_district))].map(v => [v, v])], fd, v => set({ fd: v })), button(state.view === 'tile' ? 'Показать географию' : 'Плиточная карта', () => set({ view: state.view === 'tile' ? 'map' : 'tile' }), 'button subtle', 'grid')));
    if (!data.usingLatest && state.mode === 'latest')
        root.append(note('Для этого источника ещё нет проверенного обновления. Показан архивный срез от 14.05.2026, а не новые данные.', 'warning'));
    root.append(sourceFoot('Наблюдения выбранного источника: '+(data.usingLatest?'последняя проверенная выгрузка':'архив экспертизы'), './'+(data.usingLatest?data.latestInfo.published_file:'data/baseline/'+id+'.json')));
    if (data.latestInfo?.indicator_id)root.append(sourceFoot('Карточка показателя в ЕМИСС', 'https://www.fedstat.ru/indicator/'+data.latestInfo.indicator_id));
    if (data.stale) root.append(note('Показан последний успешный приём от '+(data.latestInfo.fetched_at||'неизвестной даты')+'. Последующая проверка источника не завершилась: '+data.latestInfo.message,'warning'));
    const suspect=[...rawMap.values()].filter(r=>r.flag&&Number.isFinite(r.value));
    if(suspect.length) root.append(note(suspect.length+' значений с флагами качества исключены из цветовой шкалы, медианы и диапазона. Исходные числа сохранены в таблице и выгрузках.', 'warning'));
    root.append(stats([['Источник', d.indicator_code, d.id + ' · ' + (data.usingLatest ? 'обновлённая серия' : 'срез экспертизы')], ['Территорий с числом', `${vals.length} / ${regions.length}`, p ? periodText(p) : ''], ['Медиана регионов', fmt(median(vals), 3), unit + ' · без взвешивания по населению'], ['Диапазон значений', vals.length ? `${fmt(Math.min(...vals), 2)} – ${fmt(Math.max(...vals), 2)}` : '—', unit + ' · не оценка эффективности']]));
    const m = mapView(geo, catalog.regions, values, { unit, selected: selected?.id, onSelect: r => set({ r }), tile: state.view === 'tile', title: d.label + ' · ' + periodText(p) }), aside = h('div', { class: 'atlas-aside' }, select('Регион', [['', 'Выберите на карте'], ...catalog.regions.map(r => [r.id, r.name])], selected?.id || '', v => set({ r: v })));
    if (selected) {
        const r = rm.get(selected.id);
        aside.append(h('div', { class: 'region-reading' }, h('h2', {}, selected.name), h('strong', {class:r?.flag?'quality-reading':''}, r?.flag&&Number.isFinite(r.rawValue)?'Требует проверки':fmt(r?.value, 4)), h('span', {}, unit), para(`${p.label} ${p.end.slice(0, 4)} · ${p.type}`, 'small muted')), ...(r?.flag ? [note('Значение исключено из расчётов: ' + qualityFlag(r.flag) + '. Исходное число: '+fmt(r.rawValue,4)+' '+unit+'. Оно сохранено для проверки источника.', 'warning')] : []), ...(r?.aliasNote ? [para(r.aliasNote, 'small muted')] : []), para(selected.federal_district, 'small'), button('Приблизить регион', () => m.zoomTo(geo.features.find(f => f.id === selected.id).bounds), 'button subtle'), select('Сравнить с регионом', [['', 'Без сравнения'], ...catalog.regions.filter(r => r.id !== selected.id).map(r => [r.id, r.name])], cmp?.id || '', v => set({ compare: v })));
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
        const chartSeries = idsChosen.map((id, i) => { const history = ps.filter(pp => pp.type === p.type).map(pp => regionRows(data.rows, pp.key).get(id) || {end: pp.end, value: null, label: pp.label, year: pp.end.slice(0, 4), type: pp.type}); return { name: catalog.regions.find(r => r.id === id).name, color: C[i === 0 ? 0 : 2], points: history.map(r => ({ x: Date.parse(r.end), y: analyticalRow(r).value, label: `${r.label} ${r.year} · ${r.type}` })) }; });
        root.append(panel('Динамика выбранных территорий', `Только тип периода «${p.type}». Пропуски не интерполируются.`, h('div', {}, legend(chartSeries), figure(lineChart(chartSeries, { unit, height: 320, label: d.label }), { name: 'region_history_' + id, title: d.label, source: 'Однородный тип периода; числа из выбранной версии данных' }))));
        if (id === 'data_21' || id === 'data_22') {
            const otherId = id === 'data_21' ? 'data_22' : 'data_21';
            const otherPacket = await series(otherId, state.mode, ctx.manifest);
            const otherMap = new Map([...regionRows(otherPacket.rows, pk)].map(([id,row])=>[id,analyticalRow(row)]));
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
        const profile = await Promise.all(catalog.datasets.map(async d=>{const packet=await series(d.id,state.mode,ctx.manifest), periodsList=periods(packet.rows), key=choosePeriod(periodsList,null,state.mode==='baseline'), period=periodsList.find(p=>p.key===key), value=analyticalRow(regionRows(packet.rows,key).get(selected.id));return {name:d.label,value:value?.value,raw:value?.rawValue,flag:qualityFlag(value?.flag||''),period:period?periodText(period):'Нет данных',unit:metaUnit(d),source:d.source_file};}));
        root.append(panel('Региональный профиль', 'Последнее доступное наблюдение каждого источника в выбранной версии. Периоды показаны отдельно; значения с флагами исключены.', table(profile, [{ key: 'name', label: 'Показатель' }, { key: 'value', label: 'Значение', numeric: true }, { key: 'period', label: 'Период' }, { key: 'unit', label: 'Единица' }, {key:'raw',label:'Исходное число',numeric:true}, {key:'flag',label:'Проверка'}], { pageSize: 12, filename: `profile_${selected.id}.csv` })));
    }
    const tableRows = regions.map(r => { const v = rm.get(r.id); return { id: r.id, region: r.name, district: r.federal_district, value: v?.value, raw: v?.rawValue ?? v?.value, unit, period: periodText(p), original: v?.territory || '', flag: qualityFlag(v?.flag || ''), alternatives: v?.alternatives?.length || 0 }; });
    root.append(panel('Все региональные значения', 'Нажатие на строку открывает регион. Сортировка — по заголовку столбца.', table(tableRows, [{ key: 'region', label: 'Территория' }, { key: 'value', label: unit, numeric: true, decimals: 4 }, { key: 'raw', label: 'Исходное число', numeric: true, decimals:4 }, { key: 'flag', label: 'Флаг качества' }, { key: 'original', label: 'Наименование источника' }], { pageSize: 10, onSelect: r => set({ r: r.id }), filename: `${id}_${p.end}_regions.csv` })), methodBox(s.method), evidence(s.finding + ' ' + s.proposal, 'Полная экспертиза от 14.05.2026', `раздел 5, с. ${s.pages}`));
    return root;
}
