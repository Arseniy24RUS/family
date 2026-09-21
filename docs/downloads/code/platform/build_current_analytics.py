"""Build current coverage and regional diagnostics from the validated EMISS layer.

Original research files are never overwritten. Missing/flagged values are not
imputed; each feature retains its own observation period and source provenance.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ['data_20', 'data_21', 'data_22', 'data_23']


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')


def valid(row):
    value = row.get('value')
    return isinstance(value, (int, float)) and math.isfinite(value) and not row.get('flag')


def period_rows(rows):
    regional = [r for r in rows if r.get('r') and isinstance(r.get('value'), (int, float))]
    pool = regional or rows
    if not pool:
        return None, {}
    # Latest date first; annual observation wins only if dates coincide.
    last = max(pool, key=lambda r: (r['end'], r['type'] == 'год', r['type']))
    key = last['type'] + '|' + last['end']
    grouped = {}
    for r in rows:
        if r.get('r') and r['type'] + '|' + r['end'] == key:
            grouped.setdefault(r['r'], []).append(r)
    result = {}
    for rid, group in grouped.items():
        parts = [r for r in group if re.search(r'кроме|без.*автоном', r['territory'], re.I)]
        candidates = parts or group
        numbers = {r['value'] for r in candidates if isinstance(r.get('value'), (int, float))}
        if len(numbers) == 1:
            result[rid] = next(r for r in candidates if r.get('value') is not None)
    return key, result


def spatial(values, edges, permutations=999):
    ids = list(values)
    x = np.array(list(values.values()), dtype=float)
    if len(x) < 5 or np.std(x) == 0:
        return None
    index = {rid: i for i, rid in enumerate(ids)}
    w = np.zeros((len(x), len(x)))
    for a, b in edges:
        if a in index and b in index:
            w[index[a], index[b]] = w[index[b], index[a]] = 1
    sums = w.sum(axis=1)
    w = np.divide(w, sums[:, None], out=np.zeros_like(w), where=sums[:, None] != 0)
    if not w.sum():
        return None
    z = (x-x.mean())/x.std()
    lag = w @ z
    local = z*lag
    glob = float(len(x)/w.sum()*local.sum()/(z@z))
    rng = np.random.default_rng(42)
    q = np.array([rng.permutation(z) for _ in range(permutations)])
    null_local = q*(q @ w.T)
    null_global = len(x)/w.sum()*null_local.sum(axis=1)/(z@z)
    p = float((1+np.sum(abs(null_global-null_global.mean()) >= abs(glob-null_global.mean())))/(permutations+1))
    expected = null_local.mean(axis=0)
    lp = (1+(abs(null_local-expected) >= abs(local-expected)).sum(axis=0))/(permutations+1)
    # Benjamini-Hochberg correction across all local tests for this indicator.
    order = np.argsort(lp)
    adjusted = np.minimum.accumulate((lp[order]*len(lp)/np.arange(1, len(lp)+1))[::-1])[::-1]
    qvals = np.empty_like(lp)
    qvals[order] = np.minimum(1, adjusted)
    return dict(I=glob, p=p, ids=ids, z=z, lag=lag, local=local, p_local=lp, q=qvals,
                islands=int((sums == 0).sum()))


def build(root=ROOT):
    public = root/'public'
    cat = read(public/'data/catalog.json')
    original = read(public/'data/research.json')
    manifest = read(public/'data/latest/manifest.json')
    sources = {s['source_id']: s for s in manifest.get('sources', [])}
    packets, periods, selected, provenance = {}, {}, {}, []
    for d in cat['datasets']:
        info = sources.get(d['id'], {})
        path = info.get('published_file') or f"data/baseline/{d['id']}.json"
        packed = read(public/path)
        rows = [dict(zip(packed['columns'], row)) for row in packed['rows']]
        packets[d['id']] = rows
        key, selected[d['id']] = period_rows(rows)
        periods[d['id']] = key
        regions = {r['r'] for r in rows if r.get('r') and valid(r)}
        d.update(n_rows=len(rows), regional_count=len(regions), flags=sum(bool(r.get('flag')) for r in rows))
        provenance.append(dict(id=d['id'], label=d['label'], period=key, source=path,
                               sha256=hashlib.sha256((public/path).read_bytes()).hexdigest(),
                               basis='latest' if info.get('published_file') else 'baseline',
                               state=info.get('state'), fetched_at=info.get('fetched_at')))
    cat['n_observations'] = sum(len(rows) for rows in packets.values())
    cat['basis'] = 'current'
    cat['checked_at'] = manifest.get('checked_at')
    for i in cat['indicators']:
        rows = [r for sid in i['datasets'] for r in packets[sid]]
        i['n_rows'] = len(rows)
        i['n_regions'] = len({r['r'] for r in rows if r.get('r') and valid(r)})
        i['coverage_status'] = 'Есть проверенные данные' if rows else 'Нет опубликованного ряда'
    regions = cat['regions']
    included = [r for r in regions if all(valid(selected[sid].get(r['id'], {})) for sid in FEATURES)]
    meta = dict(schema='semya.current-analytics/1', model_version='regional-current/1',
                checked_at=manifest.get('checked_at'), sources=provenance, features=FEATURES,
                seed=42, permutations=999, missing_policy='complete cases; flagged values excluded; no imputation',
                period_policy='latest regional observation per source; annual preferred only on equal dates',
                parameters={'standardization':'population z-score', 'kmeans':{'k':3,'n_init':20},
                            'pca':{'n_components':4,'svd_solver':'full'},
                            'isolation_forest':{'contamination':.15,'n_estimators':100},
                            'network':{'nearest_neighbors':4,'metric':'positive cosine similarity','edges':'undirected union','communities':'greedy modularity'},
                            'spatial':{'weights':'original adjacency; induced row-standardized', 'p':'two-sided deviation from permutation mean', 'local_correction':'Benjamini-Hochberg per indicator','q_threshold':.05}},
                excluded_regions=[r['id'] for r in regions if r not in included])
    out = {'current_metadata': meta}
    if len(included) < 6:
        raise ValueError('Too few complete current regional profiles; refusing stale substitution')
    matrix = np.array([[selected[sid][r['id']]['value'] for sid in FEATURES] for r in included])
    z = StandardScaler().fit_transform(matrix)
    clusters = KMeans(n_clusters=3, random_state=42, n_init=20).fit(z)
    pca = PCA(n_components=min(4, len(FEATURES)), svd_solver='full').fit(z)
    coords = pca.transform(z)
    def region_info(r):
        return dict(region_code=int(r['id']), region_name=r['name'], federal_district=r['federal_district'])
    out['region_clusters'] = [{**region_info(r), 'cluster_id': int(clusters.labels_[i])+1,
                               'cluster_label': f'Кластер {int(clusters.labels_[i])+1}',
                               'pca1': float(coords[i, 0]), 'pca2': float(coords[i, 1])} for i, r in enumerate(included)]
    keys = {d['id']: d['source_file']+' | '+d['indicator_code'] for d in cat['datasets']}
    out['cluster_profiles_feature_means'] = [dict(cluster_id=g+1, cluster_label=f'Кластер {g+1}',
        n_regions=int((clusters.labels_ == g).sum()), **{keys[sid]: float(matrix[clusters.labels_ == g, j].mean()) for j, sid in enumerate(FEATURES)}) for g in range(3)]
    out['cluster_silhouette_selection'] = []
    for k in range(2, min(7, len(included))):
        model = clusters if k == 3 else KMeans(n_clusters=k, random_state=42, n_init=20).fit(z)
        out['cluster_silhouette_selection'].append(dict(k=k, silhouette=float(silhouette_score(z, model.labels_)),
            inertia=float(model.inertia_), counts='/'.join(str(int((model.labels_ == g).sum())) for g in range(k))))
    out['pca_explained_variance'] = [dict(component=f'PC{i+1}', explained_variance_ratio=float(v)) for i, v in enumerate(pca.explained_variance_ratio_)]
    out['pca_feature_loadings'] = [{'Unnamed: 0': keys[sid], **{f'PC{i+1}': float(v) for i, v in enumerate(pca.components_[:, j])}} for j, sid in enumerate(FEATURES)]
    iso = IsolationForest(random_state=42, contamination=.15).fit(z)
    scores, labels = -iso.score_samples(z), iso.predict(z)
    out['regional_outlier_scores'] = [{**region_info(r), 'outlier_score': float(scores[i]), 'is_outlier': bool(labels[i] == -1)} for i, r in enumerate(included)]
    norm = np.linalg.norm(z, axis=1)
    normalized = np.divide(z, norm[:, None], out=np.zeros_like(z), where=norm[:, None] != 0)
    sim = normalized @ normalized.T
    np.fill_diagonal(sim, -np.inf)
    graph = nx.Graph()
    graph.add_nodes_from(r['id'] for r in included)
    for i, r in enumerate(included):
        for j in np.argsort(sim[i])[-4:]:
            if sim[i, j] > 0:
                graph.add_edge(r['id'], included[j]['id'], weight=float(sim[i, j]))
    communities = list(nx.community.greedy_modularity_communities(graph, weight='weight')) if graph.number_of_edges() else [{n} for n in graph]
    community = {node: j+1 for j, group in enumerate(communities) for node in group}
    names = {r['id']: r['name'] for r in included}
    out['region_similarity_network_edges'] = [dict(region_code_1=int(a), region_name_1=names[a], region_code_2=int(b), region_name_2=names[b], similarity_weight=d['weight']) for a, b, d in graph.edges(data=True)]
    out['region_similarity_network_communities'] = [{**region_info(r), 'community_id': community[r['id']]} for r in included]
    out['region_network_layout'] = {rid: pos.tolist() for rid, pos in nx.spring_layout(graph, seed=42, iterations=220).items()}
    edges = [(str(e['region_code_1']).zfill(2), str(e['region_code_2']).zfill(2)) for e in original['spatial_adjacency_edges']]
    by_id = {r['id']: r for r in regions}
    out['spatial_moran_global'], out['spatial_local_moran_long'] = [], []
    for d in cat['datasets']:
        vals = {rid: r['value'] for rid, r in selected[d['id']].items() if valid(r)}
        result = spatial(vals, edges)
        if result is None:
            continue
        common = dict(source_file=d['source_file'], indicator_code=d['indicator_code'], period=periods[d['id']])
        out['spatial_moran_global'].append(dict(**common, moran_I=result['I'], p_value=result['p'], n_regions_with_data=len(vals), islands=result['islands']))
        for j, rid in enumerate(result['ids']):
            quad = ('H' if result['z'][j] >= 0 else 'L') + ('H' if result['lag'][j] >= 0 else 'L')
            out['spatial_local_moran_long'].append(dict(**common, **region_info(by_id[rid]),
                z_score=float(result['z'][j]), spatial_lag_z=float(result['lag'][j]), local_moran_I=float(result['local'][j]),
                p_value=float(result['p_local'][j]), q_value=float(result['q'][j]), cluster_type=quad if result['q'][j] <= .05 else 'NS'))
    out['current_inputs'] = [{'id': r['id'], **{sid: float(matrix[i, j]) for j, sid in enumerate(FEATURES)}} for i, r in enumerate(included)]
    write(public/'data/current/catalog.json', cat)
    write(public/'data/current/research.json', out)
    print(f'Current analytics: {cat["n_observations"]} rows, {len(included)} regional profiles, {len(out["spatial_moran_global"])} spatial indicators')


if __name__ == '__main__':
    build()
