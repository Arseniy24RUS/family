import { h, button, select, check, para, note, fmt, csvDownload, download, codeRegion } from '../core/dom.js';
import { series, periods, choosePeriod, periodText, regionRows, metaUnit, rawPath } from '../core/data.js';
import { heading, panel, toolbar, stats, table, sourceFoot, figure, tabs, empty, methodBox } from '../components/ui.js';
import { scatter, legend, C } from '../components/charts.js';
import { pearson, spearman, mean } from '../core/stats.js';
export async function lab(ctx) {
    const { catalog, state, set } = ctx, root = h('div', {}, heading('Вычислительная лаборатория', 'Новые исследовательские расчёты в браузере. Архив экспертизы остаётся неизменным.')), tab = state.tab || 'correlation', available = catalog.datasets.filter(d => d.regional_count > 0);
    root.append(tabs([['correlation', 'Связь двух показателей'], ['cluster', 'Новая кластеризация'], ['moran', 'Перестановочный Moran']], tab, v => set({ tab: v })), note('Результат зависит от выбранных источников, периодов и правил. Выходные файлы содержат параметры расчёта и входную матрицу. Эти вычисления не обозначаются как результаты первоначальной экспертизы.'));
    const x = available.find(d => d.id === state.x) || available.find(d => d.id === 'data_21'), y = available.find(d => d.id === state.y) || available.find(d => d.id === 'data_22'), xp = await series(x.id, state.mode, ctx.manifest), yp = await series(y.id, state.mode, ctx.manifest), pxs = periods(xp.rows), pys = periods(yp.rows), px = choosePeriod(pxs, state.px, true), py = choosePeriod(pys, state.py, true), xm = regionRows(xp.rows, px), ym = regionRows(yp.rows, py), rows = catalog.regions.map(r => ({ id: r.id, name: r.name, x: xm.get(r.id)?.value, y: ym.get(r.id)?.value, xFlag: xm.get(r.id)?.flag, yFlag: ym.get(r.id)?.flag })).filter(r => Number.isFinite(r.x) && Number.isFinite(r.y)), safe = state.flagged === '1' ? rows : rows.filter(r => !r.xFlag && !r.yFlag);
    let config = { version: 'semya-lab/1', snapshot: '2026-05-14', x_basis: xp.usingLatest ? 'latest' : 'baseline', y_basis: yp.usingLatest ? 'latest' : 'baseline', checked_at: ctx.manifest.checked_at || null, mode: state.mode || 'baseline', x: x.id, y: y.id, px, py, exclude_flags: state.flagged !== '1', seed: 42 };
    root.append(toolbar(select('Показатель X', available.map(d => [d.id, d.label]), x.id, v => set({ x: v, px: null })), select('Период X', pxs.slice().reverse().map(p => [p.key, periodText(p)]), px, v => set({ px: v })), tab === 'moran' ? null : select('Показатель Y', available.map(d => [d.id, d.label]), y.id, v => set({ y: v, py: null })), tab === 'moran' ? null : select('Период Y', pys.slice().reverse().map(p => [p.key, periodText(p)]), py, v => set({ py: v })), check('Включить значения с флагами качества', state.flagged === '1', v => set({ flagged: v ? '1' : '0' }))));
    if (!xp.usingLatest && state.mode === 'latest')
        root.append(note('Для X используется архив: проверенное обновление ещё не опубликовано.', 'warning'));
    if (!yp.usingLatest && state.mode === 'latest' && tab !== 'moran') root.append(note('Для Y используется архив: проверенное обновление ещё не опубликовано.', 'warning'));
    if (tab !== 'moran' && px !== py)
        root.append(note('Периоды или их типы различаются. Результат представляет связь этих конкретных срезов, а не синхронную временную зависимость.', 'warning'));
    if (xp.stale || (tab !== 'moran' && yp.stale)) root.append(note('Один из рядов относится к последнему успешному приёму: последующая проверка ЕМИСС завершилась ошибкой. Подробности — на странице обновления.', 'warning'));
    let worker = null;
    async function compute(task, payload) {
        worker?.terminate();
        const response = await fetch(new URL('../../workers/lab-worker.js', import.meta.url));
        if (!response.ok) throw Error('Не загружен локальный вычислительный модуль: HTTP ' + response.status);
        const workerUrl = URL.createObjectURL(new Blob([await response.text()], {type:'text/javascript'}));
        worker = new Worker(workerUrl);
        return new Promise((resolve,reject) => {
            const finish = () => {worker.terminate(); URL.revokeObjectURL(workerUrl);};
            const timer = setTimeout(()=>{finish();reject(Error('Вычисление превысило 30 секунд'));},30000);
            worker.onmessage = e => {clearTimeout(timer); finish(); e.data.error ? reject(Error(e.data.error)) : resolve(e.data.result);};
            worker.onerror = e => {clearTimeout(timer); finish(); reject(Error(e.message || 'Браузер не разрешил вычислительный модуль. Скачайте JSON и повторите расчёт в Python.'));};
            worker.postMessage({id:1,task,payload});
        });
    }
    if (tab === 'correlation') {
        const vx = safe.map(r => r.x), vy = safe.map(r => r.y), result = { pearson: pearson(vx, vy), spearman: spearman(vx, vy), n: safe.length };
        root.append(stats([['Сопоставимых пар', safe.length, `Из ${catalog.regions.length} территорий`], ['Корреляция Пирсона', fmt(result.pearson, 4), 'Линейная связь между числами'], ['Корреляция Спирмена', fmt(result.spearman, 4), 'Связь между рангами, со средними рангами для совпадений']]));
        root.append(panel('Каждая точка — регион', 'Клик открывает региональный атлас. Оси содержат исходные значения.', figure(scatter(safe, { xLabel: x.label + ' (' + metaUnit(x) + ')', yLabel: y.label + ' (' + metaUnit(y) + ')', onSelect: r => ctx.go('map', { r: r.id, source: x.id, period: px }), label: 'Исследовательская диаграмма связи' }), { name: 'correlation', title: 'Связь региональных показателей', source: `X: ${x.id}, ${px}; Y: ${y.id}, ${py}; новый расчёт`, rows: safe })), note('Корреляция не устанавливает причинность и не описывает индивидуальное поведение семьи. Показатели с общим знаменателем и пространственной зависимостью могут давать связь без причинного воздействия.'));
        root.append(toolbar(button('Скачать расчёт и параметры', () => download('correlation_result.json', JSON.stringify({ config, result, input: safe }, null, 2), 'application/json'), 'button primary', 'download')));
    }
    else if (tab === 'cluster') {
        const k = Math.max(2, Math.min(6, Number(state.k) || 3)), selectedFeatures = (state.features || [x.id, y.id].join(',')).split(',').filter(id => available.some(d => d.id === id)), features = [...new Set(selectedFeatures)];
        root.append(panel('Признаки новой кластеризации', 'Два выбранных показателя задают оси диаграммы; признаки группировки выбираются отдельно.', h('div', { class: 'feature-checks' }, available.map(d => check(d.label, features.includes(d.id), v => set({ features: (v ? [...features, d.id] : features.filter(id => id !== d.id)).join(',') }))))));
        const resultBox = h('div', {}, empty('Расчёт ещё не выполнен', 'Выберите признаки и число групп. Используются последние полные периоды каждого выбранного источника.')), periodBox = h('div', {});
        let run = button('Рассчитать кластеры', async () => { run.disabled = true; resultBox.replaceChildren(para('Стандартизация и кластеризация…')); try {
            if (features.length < 2)
                throw Error('Выберите минимум два признака');
            const data = await Promise.all(features.map(async (id) => { const p = await series(id, state.mode, ctx.manifest), ps = periods(p.rows), key = choosePeriod(ps, id === x.id ? px : id === y.id ? py : null, true); return { id, key, map: regionRows(p.rows, key), basis: p.usingLatest ? 'latest' : 'baseline' }; })), input = catalog.regions.map(r => ({ id: r.id, name: r.name, values: data.map(d => d.map.get(r.id)?.value), flags: data.map(d => d.map.get(r.id)?.flag) })).filter(r => r.values.every(Number.isFinite) && (state.flagged === '1' || r.flags.every(f => !f)));
            if (input.length < Math.max(10, k * 2))
                throw Error('Слишком мало полных строк. Измените признаки или флаги.');
            const result = await compute('cluster', { matrix: input.map(r => r.values), k, seed: 42 }), out = input.map((r, i) => ({ ...r, cluster: result.labels[i] })), configFull = { ...config, method: 'kmeans++ single initialisation; population z-score; no imputation', features: data.map(d => ({ id: d.id, period: d.key, basis: d.basis })), k };
            periodBox.replaceChildren(note('Входные срезы: ' + data.map(d => `${catalog.datasets.find(a => a.id === d.id).label} — ${d.key}`).join('; ')));
            resultBox.replaceChildren(stats([['Полных строк', input.length, 'Пропуски не заполнены'], ['Групп', k, 'Инициализация K-means++ · seed 42'], ['Силуэт', fmt(result.silhouette, 4), 'Евклидово расстояние на z-признаках'], ['Итераций', result.iterations, 'До стабилизации меток']]), legend(Array.from({ length: k }, (_, i) => ({ name: `Группа ${i + 1}: ${out.filter(r => r.cluster === i + 1).length}`, color: C[i] }))), figure(scatter(out.map(r => ({ id: r.id, name: r.name, group: r.cluster, x: xm.get(r.id)?.value, y: ym.get(r.id)?.value, detail: 'Новая группа ' + r.cluster })), { xLabel: x.label, yLabel: y.label, label: 'Новая кластеризация · исходные оси' }), { name: 'new_clusters', title: 'Новая исследовательская кластеризация', source: 'K-means++, z-score, seed 42; не архивный результат' }), toolbar(button('Результат + входы + параметры', () => download('new_clusters.json', JSON.stringify({ config: configFull, result, input: out }, null, 2), 'application/json'), 'button primary', 'download'), button('CSV с метками', () => csvDownload('new_cluster_labels.csv', out.map(r => ({ region: r.name, id: r.id, cluster: r.cluster, ...Object.fromEntries(features.map((f, j) => [f, r.values[j]])) }))), 'button subtle', 'download')), table(out.map(r => ({ id: r.id, name: r.name, cluster: r.cluster })), [{ key: 'id', label: 'Код' }, { key: 'name', label: 'Регион' }, { key: 'cluster', label: 'Новая группа', numeric: true, decimals: 0 }], { pageSize: 10 }));
        }
        catch (e) {
            resultBox.replaceChildren(note(e.message, 'warning'));
        }
        finally {
            run.disabled = false;
        } }, 'button primary');
        root.append(toolbar(select('Число групп', [2, 3, 4, 5, 6].map(k => [String(k), String(k)]), String(k), v => set({ k: v })), run), periodBox, resultBox, note('Номера групп условны. Отсутствует автоматическое соответствие новым группам и кластерам исходного отчёта. Результат чувствителен к признакам, выбросам и одной инициализации.'));
    }
    else {
        let run = button('Рассчитать Moran I', async () => { run.disabled = true; box.replaceChildren(para('Выполняются 999 перестановок…')); try {
            const vals = Object.fromEntries([...xm].filter(([id, r]) => Number.isFinite(r.value) && (state.flagged === '1' || !r.flag)).map(([id, r]) => [id, r.value])), adjacency = ctx.research.spatial_adjacency_edges.map(e => [codeRegion(e.region_code_1), codeRegion(e.region_code_2)]), result = await compute('moran', { values: vals, adjacency, permutations: 999, seed: 42 }), configFull = { ...config, method: 'Moran I; induced undirected original adjacency; row normalisation after missing exclusion', permutations: 999, p_definition: 'two-sided absolute deviation from permutation mean' };
            box.replaceChildren(stats([['Moran I', fmt(result.I, 5), 'Новый расчёт'], ['Перестановочное p', fmt(result.p, 4), '999 перестановок; seed 42'], ['Регионов', result.n, 'С числом без исключённых флагов'], ['Изолированных', result.islands, 'После исключения пропусков']]), note('Эта процедура нормирует веса после исключения пропусков и использует двустороннее отклонение от перестановочного среднего. Она намеренно обозначена как новый анализ, а не точное повторение исходных 99 перестановок.'), button('Скачать расчёт и входы', () => download('moran_result.json', JSON.stringify({ config: configFull, result, values: vals, adjacency }, null, 2), 'application/json'), 'button primary', 'download'));
        }
        catch (e) {
            box.replaceChildren(note(e.message, 'warning'));
        }
        finally {
            run.disabled = false;
        } }, 'button primary'), box = h('div', {}, empty('Готово к расчёту', 'Используется архивный список соседств и выбранный срез X.'));
        root.append(run, box);
    }
    root.append(sourceFoot('Реализация лаборатории открыта: src/core/stats.js, worker.js и переносимый scripts/lab_reproduce.py.', './downloads/code/platform/lab_reproduce.py'));
    return root;
}
