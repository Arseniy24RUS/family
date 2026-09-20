import { standardize, kmeans, moran, pearson, spearman } from './stats.js';
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
