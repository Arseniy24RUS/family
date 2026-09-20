# -*- coding: utf-8 -*-
"""
V2 supplement builder for the national project "Family" analytics package.
Adds polygon-based maps for all 89 RF subjects, cartodiagrams, spatial diagnostics,
composite indices, anomaly detection, regional similarity networks, activity-indicator
network analysis, data observability audit and advanced NLP frame scores.
"""
from pathlib import Path
import shutil
import textwrap
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely import wkt
import matplotlib.pyplot as plt
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
import networkx as nx
from scipy.cluster.hierarchy import linkage, dendrogram
from scipy.spatial.distance import squareform

ROOT = Path('/mnt/data/np_family_expertise_artifacts_v2')
DATA = ROOT / 'data'
INPUT_POLYGONS = Path('/mnt/data/Карта 89 субъектов РФ с населением.csv')

for rel in [
    'figures/maps_geo_latest', 'figures/maps_geo_complete_year',
    'figures/maps_geo_cartodiagram_latest', 'figures/maps_geo_cartodiagram_complete_year',
    'figures/spatial', 'figures/spatial_local_clusters', 'figures/composite',
    'figures/networks', 'figures/data_quality', 'figures/outliers', 'figures/nlp_advanced',
    'reports', 'geo'
]:
    p = ROOT / rel
    if p.exists() and rel.startswith('figures/'):
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)

latest = pd.read_csv(DATA / 'regional_latest_values_89_long.csv')
complete = pd.read_csv(DATA / 'regional_last_complete_year_values_89_long.csv')
obs = pd.read_csv(DATA / 'observations_emiss_enriched.csv', low_memory=False)
territory_ref = pd.read_csv(DATA / 'territory_reference_89.csv')
activities_long = pd.read_csv(DATA / 'activities_indicators_matrix_long.csv')
nlp_docs = pd.read_csv(DATA / 'nlp_document_texts_extracted.csv')

# ----- polygon join -----
poly_raw = pd.read_csv(INPUT_POLYGONS)
poly_raw['geometry'] = poly_raw['WKT'].apply(wkt.loads)
poly = gpd.GeoDataFrame(poly_raw, geometry='geometry', crs='EPSG:4326')
name_map = {
    'Республика Адыгея': 'Республика Адыгея (Адыгея)',
    'Республика Татарстан': 'Республика Татарстан (Татарстан)',
    'Республика Северная Осетия - Алания': 'Республика Северная Осетия – Алания',
    'Кемеровская область - Кузбасс': 'Кемеровская область – Кузбасс',
    'Ханты-Мансийский автономный округ - Югра': 'Ханты-Мансийский автономный округ – Югра',
    'Москва': 'Город Москва',
    'Санкт-Петербург': 'Город Санкт-Петербург',
    'Севастополь': 'Город Севастополь',
}
territory_ref['polygon_name'] = territory_ref['region_name'].map(name_map).fillna(territory_ref['region_name'])
geo = territory_ref.merge(poly[['Name_full','Name_small','name_en','Population_2021','Voters_2024','geometry']], left_on='polygon_name', right_on='Name_full', how='left')
geo = gpd.GeoDataFrame(geo, geometry='geometry', crs='EPSG:4326')
geo['Population_2021'] = pd.to_numeric(geo['Population_2021'], errors='coerce')
geo['Voters_2024'] = pd.to_numeric(geo['Voters_2024'], errors='coerce')
cent = geo.to_crs(3857).geometry.centroid.to_crs(4326)
geo['centroid_x'] = cent.x
geo['centroid_y'] = cent.y
plot_geo = geo.copy()
plot_geo['geometry'] = plot_geo.geometry.simplify(0.05, preserve_topology=True)

pd.DataFrame({
    'metric': ['n_reference_regions','n_polygon_regions','n_joined_regions','n_missing_geometries','n_unique_reference_codes','n_unique_polygon_names'],
    'value': [len(territory_ref), len(poly), int(geo.geometry.notna().sum()), int(geo.geometry.isna().sum()), territory_ref['region_code'].nunique(), poly['Name_full'].nunique()]
}).to_csv(DATA / 'polygon_join_integrity_check.csv', index=False)
geo[['region_code','region_name','polygon_name','Name_full','Name_small','Population_2021','Voters_2024','centroid_x','centroid_y']].to_csv(DATA / 'polygon_join_reference.csv', index=False)
geo.drop(columns=[]).to_file(ROOT / 'geo' / 'rf_subjects_polygons_89.geojson', driver='GeoJSON')

# ----- helpers -----
def safe_slug(s: str) -> str:
    for ch in ' /\\():;,\"\'–—«»':
        s = s.replace(ch, '_')
    while '__' in s:
        s = s.replace('__','_')
    return s.strip('_')

def prepare_group(sub: pd.DataFrame) -> pd.DataFrame:
    return sub.sort_values(['region_code','year','period_end']).drop_duplicates('region_code', keep='last')

def choropleth(vals: pd.DataFrame, title: str, out_path: Path):
    g = plot_geo.merge(vals[['region_code','value']], on='region_code', how='left')
    fig, ax = plt.subplots(figsize=(14,8))
    g.plot(column='value', ax=ax, cmap='YlGnBu', linewidth=0.25, edgecolor='black', missing_kwds={'color':'#dddddd','edgecolor':'black','label':'Нет данных'}, legend=True)
    ax.set_title(title, fontsize=11)
    ax.axis('off')
    ax.set_aspect('equal')
    ax.text(0.01,0.02, f"89 субъектов; с данными: {int(g['value'].notna().sum())}", transform=ax.transAxes, fontsize=8, bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray'))
    plt.tight_layout(); plt.savefig(out_path, dpi=120, bbox_inches='tight'); plt.close()

def cartodiagram(vals: pd.DataFrame, title: str, out_path: Path):
    g = plot_geo.merge(vals[['region_code','value']], on='region_code', how='left')
    fig, ax = plt.subplots(figsize=(14,8))
    g.plot(ax=ax, color='#f5f5f5', edgecolor='gray', linewidth=0.25)
    non = g[g['value'].notna()].copy(); miss = g[g['value'].isna()].copy()
    if len(non):
        vmin, vmax = float(non['value'].min()), float(non['value'].max())
        sizes = np.full(len(non), 180) if vmin == vmax else 30 + 600*((non['value']-vmin)/(vmax-vmin))**0.8
        sc = ax.scatter(non['centroid_x'], non['centroid_y'], s=sizes, c=non['value'], cmap='viridis', alpha=0.75, edgecolors='black', linewidths=0.3)
        cbar = fig.colorbar(sc, ax=ax, shrink=0.75)
        cbar.set_label('Значение', fontsize=8)
    if len(miss):
        ax.scatter(miss['centroid_x'], miss['centroid_y'], s=20, c='#cccccc', marker='x')
    ax.set_title(title, fontsize=11)
    ax.axis('off'); ax.set_aspect('equal')
    plt.tight_layout(); plt.savefig(out_path, dpi=120, bbox_inches='tight'); plt.close()

# ----- polygon maps -----
manifest = []
for dataset_name, df, folder_ch, folder_cd in [
    ('latest', latest, ROOT/'figures/maps_geo_latest', ROOT/'figures/maps_geo_cartodiagram_latest'),
    ('complete_year', complete, ROOT/'figures/maps_geo_complete_year', ROOT/'figures/maps_geo_cartodiagram_complete_year'),
]:
    for (source_file, ind), sub in df.groupby(['source_file','indicator_code'], dropna=False):
        vals = prepare_group(sub)
        meta = vals.iloc[0]
        year = int(meta['year']) if pd.notna(meta['year']) else ''
        title = f"{ind}. {meta['indicator_name']} — {dataset_name}, {year}"
        slug = safe_slug(f"{source_file}_{ind}_{dataset_name}")
        ch = folder_ch / f'{slug}.png'
        cd = folder_cd / f'{slug}.png'
        choropleth(vals, title, ch)
        cartodiagram(vals, title, cd)
        manifest.append({'dataset':dataset_name, 'source_file':source_file, 'indicator_code':ind, 'map_type':'geo_choropleth', 'path':str(ch.relative_to(ROOT)), 'n_regions':89, 'n_regions_with_data':int(vals['value'].notna().sum())})
        manifest.append({'dataset':dataset_name, 'source_file':source_file, 'indicator_code':ind, 'map_type':'geo_cartodiagram', 'path':str(cd.relative_to(ROOT)), 'n_regions':89, 'n_regions_with_data':int(vals['value'].notna().sum())})
pd.DataFrame(manifest).to_csv(DATA / 'geo_map_manifest.csv', index=False)

# ----- cross-sectional wide features -----
complete_unique = complete.sort_values(['region_code','source_file','indicator_code','year','period_end']).drop_duplicates(['region_code','source_file','indicator_code'], keep='last').copy()
complete_unique['indicator_key'] = complete_unique['source_file'].astype(str) + ' | ' + complete_unique['indicator_code'].astype(str)
key_labels = complete_unique[['indicator_key','source_file','indicator_code','indicator_name']].drop_duplicates('indicator_key')
key_labels.to_csv(DATA / 'indicator_keys_for_multivariate_analysis.csv', index=False)
wide = complete_unique.pivot_table(index=['region_code','region_name','federal_district'], columns='indicator_key', values='value', aggfunc='first').reset_index()
wide.columns.name = None
feature_cols = [c for c in wide.columns if ' | 2.14.' in c]

benefit_by_code = {'2.14.Я.1':'decrease','2.14.Я.2':'increase','2.14.Я.3':'increase','2.14.Я.4':'increase','2.14.Я.6':'increase','2.14.Я3.1':'increase','2.14.Я3.2':'increase','2.14.Я3.3':'decrease','2.14.Я3.4':'increase','2.14.Я3.5':'increase','2.14.Я5.2':'increase'}
X = wide[feature_cols].copy()
for c in feature_cols:
    code = c.split(' | ', 1)[1]
    if benefit_by_code.get(code) == 'decrease':
        X[c] = -X[c]
X_imp = SimpleImputer(strategy='median').fit_transform(X)
X_scaled = StandardScaler().fit_transform(X_imp)

# ----- spatial weights -----
coords = np.column_stack([geo['centroid_x'], geo['centroid_y']])
neighbors = {i:set() for i in range(len(geo))}
sidx = plot_geo.sindex
for i, geom in enumerate(plot_geo.geometry):
    for j in sidx.intersection(geom.bounds):
        if i == j:
            continue
        other = plot_geo.geometry.iloc[j]
        try:
            if geom.touches(other) or geom.intersects(other):
                neighbors[i].add(int(j))
        except Exception:
            pass
nn = NearestNeighbors(n_neighbors=5).fit(coords)
_, idx = nn.kneighbors(coords)
for i in range(len(geo)):
    if len(neighbors[i]) == 0:
        neighbors[i].update(map(int, idx[i,1:]))
for i in range(len(geo)):
    for j in list(neighbors[i]):
        neighbors[j].add(i)
W = np.zeros((len(geo), len(geo)))
for i, ns in neighbors.items():
    if ns:
        for j in ns:
            W[i,j] = 1.0 / len(ns)
adj = []
for i, ns in neighbors.items():
    for j in sorted(ns):
        if i < j:
            adj.append({'region_code_1':int(geo.iloc[i]['region_code']), 'region_name_1':geo.iloc[i]['region_name'], 'region_code_2':int(geo.iloc[j]['region_code']), 'region_name_2':geo.iloc[j]['region_name']})
pd.DataFrame(adj).to_csv(DATA / 'spatial_adjacency_edges.csv', index=False)

key_to_meta = key_labels.set_index('indicator_key').to_dict('index')
def moran_global(x, permutations=199):
    x = np.asarray(x, float); mask = np.isfinite(x); ii = np.where(mask)[0]
    if len(ii) < 5:
        return np.nan, np.nan, np.nan
    xx = x[mask]; WW = W[np.ix_(ii, ii)]; n = len(xx)
    z = xx - xx.mean(); S0 = WW.sum(); denom = z @ z
    if S0 == 0 or denom == 0:
        return np.nan, np.nan, np.nan
    I = (n/S0) * (z @ WW @ z) / denom
    rng = np.random.default_rng(42); perms=[]
    for _ in range(permutations):
        xp = rng.permutation(xx); zp = xp - xp.mean(); perms.append((n/S0)*(zp @ WW @ zp)/(zp @ zp))
    perms = np.array(perms); p = (np.sum(np.abs(perms) >= abs(I))+1)/(len(perms)+1)
    zsc = (I-perms.mean())/(perms.std(ddof=1)+1e-9)
    return I, zsc, p

def moran_local(x, permutations=99):
    x = np.asarray(x, float); mask = np.isfinite(x); ii = np.where(mask)[0]
    xx = x[mask]; WW = W[np.ix_(ii, ii)]
    z = (xx - xx.mean())/(xx.std(ddof=1)+1e-9); lag = WW @ z; I = z*lag
    rng=np.random.default_rng(42); pvals=[]
    for k in range(len(z)):
        perms=[]
        for _ in range(permutations):
            zp=rng.permutation(z); perms.append(zp[k]*(WW[k]@zp))
        perms=np.array(perms); pvals.append((np.sum(np.abs(perms) >= abs(I[k]))+1)/(len(perms)+1))
    pvals=np.array(pvals)
    quad=np.where((z>=0)&(lag>=0),'HH',np.where((z<=0)&(lag<=0),'LL',np.where((z>=0)&(lag<=0),'HL','LH')))
    typ=np.where(pvals<=0.05, quad, 'NS')
    return ii,z,lag,I,pvals,typ

spatial_rows=[]; local_rows=[]
palette={'HH':'#b2182b','LL':'#2166ac','HL':'#ef8a62','LH':'#67a9cf','NS':'#dddddd'}
for key in feature_cols:
    vals = wide[key].values
    I,zsc,p = moran_global(vals)
    meta = key_to_meta.get(key,{})
    spatial_rows.append({'indicator_key':key, 'source_file':meta.get('source_file'), 'indicator_code':meta.get('indicator_code'), 'indicator_name':meta.get('indicator_name'), 'moran_I':I, 'z_score':zsc, 'p_value':p, 'n_regions_with_data':int(np.isfinite(vals).sum())})
    ii,zs,lag,Il,pv,ctype = moran_local(vals)
    loc = pd.DataFrame({'region_code':geo.iloc[ii]['region_code'].values, 'region_name':geo.iloc[ii]['region_name'].values, 'indicator_key':key, 'source_file':meta.get('source_file'), 'indicator_code':meta.get('indicator_code'), 'z_score':zs, 'spatial_lag_z':lag, 'local_moran_I':Il, 'p_value':pv, 'cluster_type':ctype})
    local_rows.append(loc)
    g = plot_geo.merge(loc[['region_code','cluster_type']], on='region_code', how='left')
    g['cluster_type'] = g['cluster_type'].fillna('NS')
    fig, ax = plt.subplots(figsize=(14,8))
    for typ in ['HH','LL','HL','LH','NS']:
        sub = g[g['cluster_type'] == typ]
        if len(sub):
            sub.plot(ax=ax, color=palette[typ], edgecolor='black', linewidth=0.25, label=typ)
    ax.set_title(f"LISA: {meta.get('indicator_code')} {meta.get('source_file')} — {meta.get('indicator_name')}", fontsize=10)
    ax.axis('off'); ax.set_aspect('equal')
    # manual legend
    handles=[plt.Line2D([0],[0], marker='s', color='w', markerfacecolor=palette[t], markersize=8, label=t) for t in ['HH','LL','HL','LH','NS']]
    ax.legend(handles=handles, title='Тип', loc='lower left', fontsize=8)
    plt.tight_layout(); plt.savefig(ROOT/'figures/spatial_local_clusters'/f"{safe_slug(key)}_lisa.png", dpi=120, bbox_inches='tight'); plt.close()
spatial_global = pd.DataFrame(spatial_rows).sort_values('moran_I', ascending=False)
spatial_global.to_csv(DATA / 'spatial_moran_global.csv', index=False)
pd.concat(local_rows, ignore_index=True).to_csv(DATA / 'spatial_local_moran_long.csv', index=False)
fig, ax = plt.subplots(figsize=(11,7)); ax.barh(spatial_global['indicator_key'], spatial_global['moran_I']); ax.axvline(0, color='black', linewidth=0.8); ax.set_title("Глобальная пространственная автокорреляция (Moran's I)"); ax.set_xlabel("Moran's I"); plt.tight_layout(); plt.savefig(ROOT/'figures/spatial'/'global_moran_bar.png', dpi=120, bbox_inches='tight'); plt.close()

# ----- composite index / outliers -----
pc = PCA(n_components=min(5, X_scaled.shape[1]))
pcs = pc.fit_transform(X_scaled)
pc1 = pcs[:,0]
if np.corrcoef(pc1, X_scaled.mean(axis=1))[0,1] < 0:
    pc1 = -pc1
perf = pd.Series(pc1).rank(pct=True)*100
comp = wide[['region_code','region_name','federal_district']].copy()
comp['family_project_performance_index'] = perf.round(2)
comp['family_project_risk_index'] = (100-perf).round(2)
comp['pc1_score'] = pc1
comp.to_csv(DATA / 'regional_composite_indices.csv', index=False)
pd.DataFrame({'component':[f'PC{i+1}' for i in range(len(pc.explained_variance_ratio_))], 'explained_variance_ratio':pc.explained_variance_ratio_}).to_csv(DATA / 'pca_explained_variance.csv', index=False)
loadings = pd.DataFrame(pc.components_.T, index=feature_cols, columns=[f'PC{i+1}' for i in range(pc.components_.shape[0])])
loadings.to_csv(DATA / 'pca_feature_loadings.csv')
for col, title, file in [('family_project_performance_index','Интегральный индекс положения регионов','composite_index_geo.png'), ('family_project_risk_index','Интегральный индекс риска регионов','composite_risk_index_geo.png')]:
    g = plot_geo.merge(comp[['region_code', col]], on='region_code', how='left')
    fig, ax = plt.subplots(figsize=(14,8)); g.plot(column=col, ax=ax, cmap='YlGnBu', edgecolor='black', linewidth=0.25, legend=True); ax.set_title(title, fontsize=11); ax.axis('off'); ax.set_aspect('equal'); plt.tight_layout(); plt.savefig(ROOT/'figures/composite'/file, dpi=120, bbox_inches='tight'); plt.close()
ctile = territory_ref.merge(comp[['region_code','family_project_performance_index']], on='region_code', how='left')
fig, ax = plt.subplots(figsize=(12,8)); sc=ax.scatter(ctile.tile_x, ctile.tile_y, c=ctile.family_project_performance_index, cmap='YlGnBu', s=1000, marker='s', edgecolors='black')
for _,r in ctile.iterrows(): ax.text(r.tile_x, r.tile_y, r.tile_label, ha='center', va='center', fontsize=6)
ax.invert_yaxis(); ax.axis('off'); ax.set_title('Интегральный индекс по плиточной картограмме'); plt.colorbar(sc, ax=ax, shrink=0.7); plt.tight_layout(); plt.savefig(ROOT/'figures/composite'/'composite_index_tile.png', dpi=120, bbox_inches='tight'); plt.close()

iso = IsolationForest(random_state=42, contamination=0.15).fit(X_scaled)
out = comp.copy(); out['outlier_score'] = -iso.score_samples(X_scaled); out['is_outlier_top15pct'] = iso.predict(X_scaled) == -1
out.sort_values('outlier_score', ascending=False).to_csv(DATA / 'regional_outlier_scores.csv', index=False)
fig, ax = plt.subplots(figsize=(10,8)); top = out.sort_values('outlier_score').tail(20); ax.barh(top.region_name, top.outlier_score); ax.set_title('Топ-20 наиболее нетипичных регионов'); ax.set_xlabel('Outlier score'); plt.tight_layout(); plt.savefig(ROOT/'figures/outliers'/'regional_outlier_scores_top20.png', dpi=120, bbox_inches='tight'); plt.close()

# ----- region similarity network -----
sim = cosine_similarity(X_scaled); np.fill_diagonal(sim,0)
G = nx.Graph()
for _,r in comp.iterrows(): G.add_node(int(r.region_code), region_name=r.region_name)
for i in range(sim.shape[0]):
    for j in np.argsort(sim[i])[-4:]:
        if i < j:
            G.add_edge(int(comp.iloc[i].region_code), int(comp.iloc[j].region_code), weight=float(sim[i,j]))
communities = list(nx.community.greedy_modularity_communities(G, weight='weight'))
comm_map = {node:cid+1 for cid, com in enumerate(communities) for node in com}
pd.DataFrame([{'region_code_1':u,'region_name_1':G.nodes[u]['region_name'],'region_code_2':v,'region_name_2':G.nodes[v]['region_name'],'similarity_weight':d['weight']} for u,v,d in G.edges(data=True)]).to_csv(DATA / 'region_similarity_network_edges.csv', index=False)
comm_df = comp[['region_code','region_name','federal_district']].copy(); comm_df['community_id'] = comm_df['region_code'].map(comm_map); comm_df.to_csv(DATA/'region_similarity_network_communities.csv', index=False)
pos = nx.spring_layout(G, seed=42, weight='weight')
fig, ax = plt.subplots(figsize=(12,12)); nx.draw_networkx_edges(G,pos,ax=ax,alpha=0.25,width=0.8); nx.draw_networkx_nodes(G,pos,ax=ax,node_size=75,node_color=[comm_map.get(n,0) for n in G.nodes()],cmap=plt.cm.tab20)
label_nodes = set(out.sort_values('outlier_score', ascending=False).head(15)['region_code'].astype(int))
labels = {n:G.nodes[n]['region_name'] for n in G.nodes() if n in label_nodes}
nx.draw_networkx_labels(G,pos,labels=labels,font_size=7,ax=ax); ax.set_title('Сеть межрегиональной схожести по профилю показателей'); ax.axis('off'); plt.tight_layout(); plt.savefig(ROOT/'figures/networks'/'region_similarity_network.png', dpi=120, bbox_inches='tight'); plt.close()
g = plot_geo.merge(comm_df[['region_code','community_id']], on='region_code', how='left')
fig, ax = plt.subplots(figsize=(14,8)); g.plot(column='community_id', ax=ax, cmap='tab20', edgecolor='black', linewidth=0.25, legend=True); ax.set_title('Сообщества регионов в сети схожести'); ax.axis('off'); ax.set_aspect('equal'); plt.tight_layout(); plt.savefig(ROOT/'figures/networks'/'region_similarity_communities_map.png', dpi=120, bbox_inches='tight'); plt.close()

# ----- activity-indicator network -----
B = nx.Graph()
for _,r in activities_long.iterrows():
    act=f"A::{r['activity_id']}"; ind=f"I::{r['indicator_code']}"
    B.add_node(act, bipartite='activity', label=r['activity'])
    B.add_node(ind, bipartite='indicator', label=r['indicator_code'])
    B.add_edge(act, ind, weight=(2 if r['relationship_type']=='direct' else 1), relation=r['relationship_type'])
bet = nx.betweenness_centrality(B)
node_rows=[]
for n,d in B.nodes(data=True):
    node_rows.append({'node_id':n, 'node_type':d['bipartite'], 'label':d['label'], 'degree':B.degree(n), 'weighted_degree':sum(ed['weight'] for _,_,ed in B.edges(n,data=True)), 'betweenness':bet[n]})
node_df = pd.DataFrame(node_rows).sort_values(['node_type','weighted_degree'], ascending=[True,False])
node_df.to_csv(DATA / 'activity_indicator_network_node_metrics.csv', index=False)
pd.DataFrame([{'metric':'n_activity_nodes','value':sum(1 for _,d in B.nodes(data=True) if d['bipartite']=='activity')},{'metric':'n_indicator_nodes','value':sum(1 for _,d in B.nodes(data=True) if d['bipartite']=='indicator')},{'metric':'n_edges','value':B.number_of_edges()},{'metric':'density','value':nx.density(B)}]).to_csv(DATA / 'activity_indicator_network_summary.csv', index=False)
acts = node_df[node_df.node_type=='activity'].node_id.tolist(); inds = node_df[node_df.node_type=='indicator'].node_id.tolist()
pos = {n:(0,-i) for i,n in enumerate(acts)}; pos.update({n:(4,-i) for i,n in enumerate(inds)})
fig, ax = plt.subplots(figsize=(14,10)); nx.draw_networkx_edges(B,pos,ax=ax,alpha=0.35,width=[0.8+0.8*B[u][v]['weight'] for u,v in B.edges()]); nx.draw_networkx_nodes(B,pos,nodelist=acts,node_color='#fdb863',node_size=220,label='Мероприятия',ax=ax); nx.draw_networkx_nodes(B,pos,nodelist=inds,node_color='#80cdc1',node_size=220,label='Показатели',ax=ax)
lab={n:B.nodes[n]['label'][:60]+('...' if len(B.nodes[n]['label'])>60 else '') for n in acts[:12]}; lab.update({n:B.nodes[n]['label'] for n in inds}); nx.draw_networkx_labels(B,pos,labels=lab,font_size=7,ax=ax); ax.legend(loc='lower center',ncol=2); ax.set_title('Сеть «мероприятия — показатели»'); ax.axis('off'); plt.tight_layout(); plt.savefig(ROOT/'figures/networks'/'activity_indicator_network.png', dpi=120, bbox_inches='tight'); plt.close()

# ----- data observability audit -----
qrows=[]
for ind, sub in obs.groupby('indicator_code'):
    reg = sub[sub['is_subject_89']==True]
    years = pd.to_numeric(reg['year'], errors='coerce').dropna().astype(int)
    qrows.append({'indicator_code':ind, 'indicator_name':sub['indicator_name'].iloc[0], 'observations_total':len(sub), 'value_completeness_ratio':float(sub['value'].notna().mean()), 'regional_coverage_ratio':float(sub['is_subject_89'].mean()), 'n_regions_with_any_data':reg['region_code'].nunique(), 'n_years_with_regional_data':years.nunique(), 'min_year':years.min() if len(years) else np.nan, 'max_year':years.max() if len(years) else np.nan, 'period_types':'; '.join(sorted(sub['period_type'].dropna().astype(str).unique())), 'unit':sub['unit'].iloc[0]})
qual = pd.DataFrame(qrows).sort_values('regional_coverage_ratio', ascending=False)
qual.to_csv(DATA / 'indicator_observability_audit.csv', index=False)
q = qual.set_index('indicator_code')[['value_completeness_ratio','regional_coverage_ratio','n_regions_with_any_data','n_years_with_regional_data']].copy(); q['n_regions_with_any_data'] /= 89.0; q['n_years_with_regional_data'] /= max(1, q['n_years_with_regional_data'].max())
fig, ax = plt.subplots(figsize=(8,max(6,len(q)*0.45))); im=ax.imshow(q.values, aspect='auto', cmap='YlGnBu'); ax.set_xticks(range(q.shape[1])); ax.set_xticklabels(['Полнота значений','Региональный охват','Охват 89 субъектов','Временная глубина'], rotation=30, ha='right'); ax.set_yticks(range(q.shape[0])); ax.set_yticklabels(q.index); ax.set_title('Аудит измеримости и наблюдаемости показателей'); plt.colorbar(im, ax=ax, shrink=0.7); plt.tight_layout(); plt.savefig(ROOT/'figures/data_quality'/'indicator_observability_heatmap.png', dpi=120, bbox_inches='tight'); plt.close()

# ----- advanced NLP -----
frames = {
    'pronatality':['рождаем','многодет','деторожд','третьих и последующих','увеличение числа семей','репродуктивн'],
    'welfare_income':['доход','бедност','выплат','пособ','социальн','ипотек','материнск','семейн'],
    'healthcare_reproductive':['диспансер','женских консультац','беремен','младенчес','перинатал','эко','репродуктивного здоровья'],
    'infrastructure_services':['детских сад','продлен','инфраструктур','капитальн','центров','учрежден','комнат матери и ребенка'],
    'culture_values':['ценност','культур','искусств','народного творчества','семью главной ценностью'],
    'ageing_care':['старшего поколения','долговременн','активного долголетия','уход','пожилых граждан'],
    'governance_implementation':['реализац','монитор','показател','управлен','координац','федеральн','региональн'],
    'rights_autonomy':['прав','выбор','поддержк','семейных ценностей','доступност'],
    'work_education':['образователь','вуз','студенчес','труд','занятост','работодател'],
}
fr=[]
for _,r in nlp_docs.iterrows():
    txt=str(r['text']).lower(); nt=max(1,len(txt.split())); rec={'document_id':r['document_id'], 'file_name':r['file_name'], 'n_tokens':nt}
    for k,pats in frames.items():
        cnt=sum(txt.count(p.lower()) for p in pats); rec[f'{k}_count']=cnt; rec[f'{k}_per_1000_words']=cnt/nt*1000
    fr.append(rec)
fr_df=pd.DataFrame(fr); fr_df.to_csv(DATA / 'nlp_frame_scores_by_document.csv', index=False)
heat=fr_df.set_index('file_name')[[c for c in fr_df.columns if c.endswith('_per_1000_words')]].copy(); heat.columns=[c.replace('_per_1000_words','') for c in heat.columns]
fig, ax = plt.subplots(figsize=(11,6)); im=ax.imshow(heat.values, aspect='auto', cmap='OrRd'); ax.set_xticks(range(heat.shape[1])); ax.set_xticklabels(heat.columns, rotation=35, ha='right'); ax.set_yticks(range(heat.shape[0])); ax.set_yticklabels(heat.index); ax.set_title('Фреймовый профиль стратегических документов'); plt.colorbar(im, ax=ax, shrink=0.7, label='Упоминаний на 1000 слов'); plt.tight_layout(); plt.savefig(ROOT/'figures/nlp_advanced'/'document_frame_heatmap.png', dpi=120, bbox_inches='tight'); plt.close()
Xtxt = TfidfVectorizer(max_features=4000, ngram_range=(1,2)).fit_transform(nlp_docs['text'].fillna(''))
cos = cosine_similarity(Xtxt); sim_df = pd.DataFrame(cos, index=nlp_docs['file_name'], columns=nlp_docs['file_name']); sim_df.to_csv(DATA / 'nlp_document_similarity_tfidf.csv')
fig, ax = plt.subplots(figsize=(7,6)); im=ax.imshow(sim_df.values, cmap='Blues', vmin=0, vmax=1); ax.set_xticks(range(sim_df.shape[1])); ax.set_xticklabels(sim_df.columns, rotation=45, ha='right'); ax.set_yticks(range(sim_df.shape[0])); ax.set_yticklabels(sim_df.index); ax.set_title('TF-IDF схожесть документов'); plt.colorbar(im, ax=ax, shrink=0.7); plt.tight_layout(); plt.savefig(ROOT/'figures/nlp_advanced'/'document_similarity_heatmap.png', dpi=120, bbox_inches='tight'); plt.close()
Z = linkage(squareform(1-cos, checks=False), method='average'); fig, ax = plt.subplots(figsize=(8,5)); dendrogram(Z, labels=nlp_docs['file_name'].tolist(), orientation='right', ax=ax); ax.set_title('Дендограмма тематической близости документов'); plt.tight_layout(); plt.savefig(ROOT/'figures/nlp_advanced'/'document_similarity_dendrogram.png', dpi=120, bbox_inches='tight'); plt.close()

# ----- report and inventory -----
report = textwrap.dedent('''
# Дополнительный аналитический слой v2

Архив дополнен географическими картограммами и картодиаграммами на основе реальных полигонов 89 субъектов РФ из файла `Карта 89 субъектов РФ с населением.csv`. Нормализация названий субъектов выполнена через `data/polygon_join_reference.csv`; контроль соединения — `data/polygon_join_integrity_check.csv`. На каждой географической карте присутствуют все 89 субъектов РФ, включая территории без значения показателя.

## Добавленные блоки

1. Географические карты: `figures/maps_geo_latest/`, `figures/maps_geo_complete_year/`, `figures/maps_geo_cartodiagram_latest/`, `figures/maps_geo_cartodiagram_complete_year/`; реестр карт — `data/geo_map_manifest.csv`; геослой — `geo/rf_subjects_polygons_89.geojson`.

2. Пространственная статистика: глобальный Moran's I (`data/spatial_moran_global.csv`), локальные LISA-кластеры (`data/spatial_local_moran_long.csv`, `figures/spatial_local_clusters/`) и график `figures/spatial/global_moran_bar.png`.

3. Многомерная диагностика: интегральный индекс положения и риска регионов (`data/regional_composite_indices.csv`), PCA-нагрузки (`data/pca_feature_loadings.csv`), выявление аномальных регионов (`data/regional_outlier_scores.csv`).

4. Сетевые модели: сеть межрегиональной схожести (`data/region_similarity_network_edges.csv`, `data/region_similarity_network_communities.csv`) и сеть «мероприятия — показатели» (`data/activity_indicator_network_node_metrics.csv`, `figures/networks/activity_indicator_network.png`).

5. Аудит данных: `data/indicator_observability_audit.csv` и тепловая карта `figures/data_quality/indicator_observability_heatmap.png`.

6. Расширенный NLP-блок: фреймовый профиль документов (`data/nlp_frame_scores_by_document.csv`) и TF-IDF-схожесть документов (`data/nlp_document_similarity_tfidf.csv`, `figures/nlp_advanced/`).
''')
(ROOT/'reports'/'supplement_v2.md').write_text(report, encoding='utf-8')
readme = ROOT/'README.md'
old = readme.read_text(encoding='utf-8') if readme.exists() else ''
if '## Обновление v2' not in old:
    readme.write_text(old + '\n\n## Обновление v2\n\nДобавлены полигональные карты и картодиаграммы по 89 субъектам РФ, пространственная статистика, интегральные индексы, поиск аномалий, сети схожести, аудит измеримости и расширенный NLP-анализ. Методические пояснения: `reports/supplement_v2.md`.\n', encoding='utf-8')

# inventory
rows=[]
for p in ROOT.rglob('*'):
    if p.is_file():
        rows.append({'path':str(p.relative_to(ROOT)), 'size_bytes':p.stat().st_size})
pd.DataFrame(rows).sort_values('path').to_csv(DATA/'artifact_manifest_v2.csv', index=False)
pd.DataFrame([r for r in rows if any(x in r['path'] for x in ['maps_geo','spatial','composite','outlier','network','data_quality','nlp_advanced','supplement_v2','polygon_join','geo_map_manifest','observability','similarity','pca'])]).sort_values('path').to_csv(DATA/'v2_new_files_inventory.csv', index=False)
print('V2 complete. Files:', len(rows))
