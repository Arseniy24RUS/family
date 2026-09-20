/* Generated from src/core/stats.js and worker.js. */
const finite = x => typeof x === 'number' && Number.isFinite(x);
const mean = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
function quantile(a, q) { let s = a.filter(finite).sort((a, b) => a - b); if (!s.length)
    return null; const p = (s.length - 1) * q, i = Math.floor(p); return s[i] + (s[Math.min(i + 1, s.length - 1)] - s[i]) * (p - i); }
const median = a => quantile(a, .5);
function pearson(x, y) { if (x.length < 3 || x.length !== y.length)
    return null; const mx = mean(x), my = mean(y); let xx = 0, yy = 0, xy = 0; for (let i = 0; i < x.length; i++) {
    let a = x[i] - mx, b = y[i] - my;
    xx += a * a;
    yy += b * b;
    xy += a * b;
} return xx > 0 && yy > 0 ? xy / Math.sqrt(xx * yy) : null; }
function ranks(xs) { const idx = xs.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v), out = []; for (let i = 0; i < idx.length;) {
    let j = i;
    while (j + 1 < idx.length && idx[j + 1].v === idx[i].v)
        j++;
    for (let k = i; k <= j; k++)
        out[idx[k].i] = (i + j) / 2 + 1;
    i = j + 1;
} return out; }
const spearman = (x, y) => pearson(ranks(x), ranks(y));
const hhi = values => { let sum = values.reduce((s, x) => s + x, 0); return sum > 0 ? values.reduce((s, x) => s + (x / sum) ** 2, 0) : null; };
const did = (beforeTreatment, afterTreatment, beforeControl, afterControl) => (afterTreatment - beforeTreatment) - (afterControl - beforeControl);
const rng = seed => () => { let t = seed += 0x6D2B79F5; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
function standardize(matrix) { const p = matrix[0].length; let means = Array.from({ length: p }, (_, j) => mean(matrix.map(r => r[j]))), std = Array.from({ length: p }, (_, j) => Math.sqrt(mean(matrix.map(r => (r[j] - means[j]) ** 2))) || 1); return { z: matrix.map(r => r.map((v, j) => (v - means[j]) / std[j])), means, std }; }
function kmeans(matrix, k = 3, seed = 42) {
    if (!Array.isArray(matrix) || !matrix.length || !matrix[0].length || matrix.some(r=>r.length!==matrix[0].length || r.some(v=>!finite(v)))) throw Error('Матрица должна содержать конечные числа и одинаковое число столбцов');
    if (!Number.isInteger(k) || k<2 || k>matrix.length) throw Error('Некорректное число групп');
    if (new Set(matrix.map(r=>JSON.stringify(r))).size < k) throw Error('Число различных профилей меньше числа групп'); if (matrix.length < k)
    throw Error('Недостаточно наблюдений'); const random = rng(seed), n = matrix.length, p = matrix[0].length, dist = (a, b) => a.reduce((s, v, j) => s + (v - b[j]) ** 2, 0); let centres = [matrix[Math.floor(random() * n)].slice()]; while (centres.length < k) {
    const ds = matrix.map(x => Math.min(...centres.map(c => dist(x, c))));
    let pick = random() * ds.reduce((a, b) => a + b, 0), i = 0;
    for (; i < n - 1; i++) {
        pick -= ds[i];
        if (pick <= 0)
            break;
    }
    centres.push(matrix[i].slice());
} let labels = Array(n).fill(-1), iterations = 0; for (; iterations < 150; iterations++) {
    let next = matrix.map(r => { let ds = centres.map(c => dist(c, r)); return ds.indexOf(Math.min(...ds)); });
    if (next.every((v, i) => v === labels[i]))
        break;
    labels = next;
    centres = centres.map((c, i) => { let rs = matrix.filter((_, j) => labels[j] === i); return rs.length ? Array.from({ length: p }, (_, j) => mean(rs.map(r => r[j]))) : matrix[Math.floor(random() * n)].slice(); });
} const inertia = matrix.reduce((s, r, i) => s + dist(r, centres[labels[i]]), 0); let scores = matrix.map((r, i) => { let own = matrix.map((v, j) => ({ v, j })).filter(x => x.j !== i && labels[x.j] === labels[i]); if (!own.length)
    return 0; const a = mean(own.map(x => Math.sqrt(dist(r, x.v)))); const bs = centres.map((_, g) => g === labels[i] ? Infinity : mean(matrix.filter((_, j) => labels[j] === g).map(x => Math.sqrt(dist(r, x))))).filter(v => v !== null); let b = Math.min(...bs); return (b - a) / Math.max(a, b) || 0; }); return { labels: labels.map(x => x + 1), centres, inertia, silhouette: mean(scores), iterations }; }
function moran(values, adjacency, permutations = 999, seed = 42) { const ids = Object.keys(values).filter(k => finite(values[k])), n = ids.length; if (n < 5)
    throw Error('Нужны не менее пяти регионов с данными'); const index = new Map(ids.map((r, i) => [r, i])), W = Array.from({ length: n }, () => Array(n).fill(0)); for (const [a, b] of adjacency) {
    if (index.has(a) && index.has(b)) {
        W[index.get(a)][index.get(b)] = 1;
        W[index.get(b)][index.get(a)] = 1;
    }
} W.forEach(row => { let s = row.reduce((a, b) => a + b, 0); if (s)
    row.forEach((v, j) => row[j] = v / s); }); const S0 = W.flat().reduce((a, b) => a + b, 0), x = ids.map(id => values[id]), m = mean(x), z = x.map(x => x - m), den = z.reduce((s, v) => s + v * v, 0); if (!den || !S0)
    throw Error('Нет вариации или связей соседства'); const calc = q => n / S0 * q.reduce((s, v, i) => s + v * W[i].reduce((s, w, j) => s + w * q[j], 0), 0) / den; const I = calc(z), random = rng(seed), nulls = []; for (let t = 0; t < permutations; t++) {
    let q = z.slice();
    for (let j = n - 1; j > 0; j--) {
        let k = Math.floor(random() * (j + 1));
        [q[k], q[j]] = [q[j], q[k]];
    }
    nulls.push(calc(q));
} const expectation = mean(nulls), p = (1 + nulls.filter(x => Math.abs(x - expectation) >= Math.abs(I - expectation)).length) / (permutations + 1); return { I, p, n, permutations, expected: expectation, islands: W.filter(row => row.every(v => v === 0)).length }; }

self.onmessage = e => { const { id, task, payload } = e.data; try {
    let result;
    if (task === 'cluster') {
        const { z, means, std } = standardize(payload.matrix);
        result = { ...kmeans(z, payload.k, payload.seed), means, std };
    }
    else if (task === 'moran')
        result = moran(payload.values, payload.adjacency, payload.permutations, payload.seed);
    else if (task === 'correlation')
        result = { pearson: pearson(payload.x, payload.y), spearman: spearman(payload.x, payload.y), n: payload.x.length };
    else
        throw Error('Неизвестная операция');
    self.postMessage({ id, result });
}
catch (e) {
    self.postMessage({ id, error: e.message });
} };
