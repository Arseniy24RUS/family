#!/usr/bin/env python3
"""Package the supplied research snapshot. Does not re-estimate the original study.
Usage: python scripts/build_data.py
Input files are retained verbatim in public/downloads/. JSON is a browser representation.
"""
from __future__ import annotations
import csv, hashlib, json, math, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'public/downloads/data'
M = ROOT / 'public/downloads/metadata'
OUT = ROOT / 'public/data'

def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [clean(v) for v in value]
    if isinstance(value, np.generic): value=value.item()
    if isinstance(value,float) and not math.isfinite(value): return None
    return value

def dump(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(clean(data),ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')

def read(name, meta=False): return pd.read_csv((M if meta else D)/(name+'.csv'),keep_default_na=True,low_memory=False)
def rows(name,meta=False): return clean(read(name,meta).to_dict('records'))
def norm(s):
    s=str(s).casefold().replace('ё','е').replace('–','-').replace('—','-')
    s=re.sub(r'\([^)]*\)','',s)
    s=re.sub(r'^(город|г\.)\s+','',s)
    return re.sub(r'[\s\-]+',' ',s).strip()
def sid(s):
    m=re.search(r'(\d+)',str(s)); return 'data_'+m.group(1) if m else str(s)

LABELS={
 'data_20':'Бедность многодетных семей','data_21':'Суммарный коэффициент рождаемости',
 'data_22':'Рождаемость третьих и последующих детей','data_23':'Долговременный уход',
 'data_24':'Центры аудиовизуального контента','data_25':'Удовлетворённость организациями культуры',
 'data_26':'Проактивная социальная поддержка','data_27':'Капитальный ремонт детских садов',
 'data_28':'Региональные темпы повышения рождаемости','data_29':'Репродуктивная диспансеризация',
 'data_30':'Помощь в женских консультациях','data_31':'Младенческая смертность · годовой ряд',
 'data_32':'Младенческая смертность · оперативный ряд','data_33':'Диспансерное наблюдение детей',
 'data_34':'Помощь в ситуации репродуктивного выбора','data_35':'Посещения организаций культуры'}

# Browser array keys: all source dimensions remain in the original CSV.
COLS=['id','r','territory','type','year','start','end','label','value','raw','flag']
def build():
    obs=read('observations_emiss_enriched')
    ref=rows('territory_reference_89')
    for r in ref:
        r['id']=str(int(r['region_code'])).zfill(2); r['name']=r['region_name'].strip()
    regions={r['id']:r for r in ref}
    meta=rows('source_metadata',True); targets=rows('target_trajectories_known')
    datasets=[]
    for m in meta:
        id=m['source_table_id']; sub=obs[obs.source_table_id==id]; packed=[]
        for o in sub.to_dict('records'):
            rc=o['region_code']; rc=str(int(rc)).zfill(2) if pd.notna(rc) else None
            value=o['value'];flag=''
            if pd.isna(value): flag='missing'
            elif value<0: flag='negative'
            elif o['unit']=='процент' and value>100 and id!='data_35':flag='outside_0_100'
            packed.append([int(o['observation_id']),rc,str(o['territory_name']).strip(),o['period_type'],int(o['year']),o['period_start'],o['period_end'],o['period_label'],value,str(o['value_raw']),flag])
        data={'schema':'semya.series/1','source_id':id,'columns':COLS,'rows':packed,'basis':'source_archive','snapshot':'2026-05-14'}
        dump(OUT/'baseline'/f'{id}.json',data)
        details={k:m.get(k) for k in ['indicator_code','indicator_name','source_file','source_title','unit_from_passport','last_update','periodicity','methodology','agency','comment','time_series_range']}
        periods=[]
        for (typ,start,end,label),g in sub.groupby(['period_type','period_start','period_end','period_label'],dropna=False,sort=False):
            periods.append({'key':f'{typ}|{end}','type':typ,'start':start,'end':end,'label':label,'n':len(g),'regions':int(g.loc[g.value.notna(),'region_code'].nunique())})
        periods.sort(key=lambda x:(x['end'],x['type']))
        datasets.append(dict(details,id=id,label=LABELS[id],unit=str(m['unit_from_passport']),n_rows=len(sub),regional_count=int(sub.loc[sub.value.notna(),'region_code'].nunique()),periods=periods,flags=sum(bool(o[-1]) for o in packed),min_year=int(sub.year.min()),max_year=int(sub.year.max())))
    coverage=rows('indicators_coverage',True)
    for c in coverage:
        c['datasets']=[d['id'] for d in datasets if d['indicator_code']==c['indicator_code']]
        ss=obs[obs.indicator_code==c['indicator_code']]
        c['n_rows']=len(ss);c['n_regions']=int(ss.loc[ss.value.notna(),'region_code'].nunique())
    # Static source results, always isolated from subsequent observations.
    static={n:rows(n) for n in ['activities_inventory','activities_indicators_matrix_long','activity_indicator_network_node_metrics','activity_indicator_network_summary','budget_by_federal_project','budget_by_source_raw_passport','regional_outlier_scores','region_clusters','cluster_profiles_feature_means','cluster_profiles_zscores','cluster_silhouette_selection','pca_explained_variance','pca_feature_loadings','spatial_moran_global','spatial_local_moran_long','region_similarity_network_edges','region_similarity_network_communities','spatial_adjacency_edges','indicator_observability_audit','indicator_activity_coverage']}
    for name in ['regional_latest_values_89_long','regional_last_complete_year_values_89_long']:
        static[name]=[{**{k:o.get(k) for k in ['region_code','source_file','indicator_code','year','period_type','period_label','period_end','unit','value','has_value']},'source_id':sid(o['source_file'])} for o in rows(name)]
    # Graph positions are a new deterministic layout only, not a new statistical network.
    G=nx.Graph();G.add_nodes_from(int(r['region_code']) for r in ref)
    for edge in static['region_similarity_network_edges']:G.add_edge(int(edge['region_code_1']),int(edge['region_code_2']),weight=edge['similarity_weight'])
    pos=nx.spring_layout(G,seed=20260922,iterations=220,weight='weight')
    static['region_network_layout']={str(k).zfill(2):[float(v[0]),float(v[1])] for k,v in pos.items()}
    dump(OUT/'research.json',static)
    dump(OUT/'forecasts.json',{'points':rows('national_forecast_ensemble_points'),'actuals':rows('national_forecast_input_actuals'),'targets':targets,'status':'archived_diagnostic_not_causal','band':'approximate_residual_band_not_calibrated_probability'})
    nlp={n:rows(n) for n in ['nlp_document_texts_extracted','nlp_frame_scores_by_document','nlp_document_similarity_tfidf','nlp_top_terms_all_documents','nlp_top_terms_by_document','nlp_concept_cooccurrence_by_page','nlp_narrative_blocks_dictionary']}
    fp=ROOT/'public/downloads/data/frames_original.json'
    if fp.exists():nlp['frame_dictionary']=json.loads(fp.read_text(encoding='utf-8'))
    dump(OUT/'texts.json',nlp)
    # Equal-area map from the user-supplied GeoJSON; no external tiles or CDN needed.
    geo=json.loads((ROOT/'public/downloads/ru_regions.geojson').read_text(encoding='utf-8'))
    lookup={norm(r['name']):r for r in ref};lookup.update({norm('Чувашская Республика'):lookup[norm('Чувашская Республика - Чувашия')]})
    project=Transformer.from_crs('EPSG:4326','+proj=laea +lat_0=62 +lon_0=100 +datum=WGS84 +units=m +no_defs',always_xy=True).transform
    geos=[]
    for f in geo['features']:
        props=f['properties'];name=props.get('name',props.get('territory_name'));rn=lookup.get(norm(name))
        if rn is None:raise ValueError('Unmatched geometry: '+str(name))
        geom=transform(project,shape(f['geometry']));geos.append((rn,geom))
    assert len(geos)==89 and len({r['id'] for r,g in geos})==89
    bounds=np.array([g.bounds for _,g in geos]); xmin,ymin=bounds[:,:2].min(axis=0);xmax,ymax=bounds[:,2:].max(axis=0)
    width,height=1050,580;s=min((width-52)/(xmax-xmin),(height-45)/(ymax-ymin))
    ox=(width-(xmax-xmin)*s)/2;oy=(height-(ymax-ymin)*s)/2
    def pt(x,y):return ((x-xmin)*s+ox,(ymax-y)*s+oy)
    def poly_path(poly):
        paths=[]
        for ring in [poly.exterior,*poly.interiors]:
            points=[pt(x,y) for x,y,*rest in ring.coords]
            paths.append('M'+'L'.join(f'{x:.2f},{y:.2f}' for x,y in points)+'Z')
        return ''.join(paths)
    geo_results=[]
    for reg,g in geos:
        g=g.simplify(1300,preserve_topology=True)
        polys=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
        center=g.representative_point();bb=g.bounds
        geo_results.append({'id':reg['id'],'name':reg['name'],'path':''.join(poly_path(p) for p in polys),'center':pt(center.x,center.y),'bounds':[pt(bb[0],bb[3]),pt(bb[2],bb[1])]})
    dump(OUT/'map.json',{'width':width,'height':height,'projection':'Lambert azimuthal equal-area, 62°N 100°E','source':'ru_regions.geojson, supplied by author','features':geo_results})
    basehash=hashlib.sha256((D/'observations_emiss_enriched.csv').read_bytes()).hexdigest()
    index={'schema':'semya.catalog/1','title':'Семья · исследовательская платформа','version':'1.0.0','snapshot_date':'2026-05-14','authors':['Ростовская Т.К.','Ситковский А.М.','Синельников А.Б.','Архангельский В.Н.'],'n_observations':len(obs),'n_indicators':len(coverage),'n_observed_indicators':int(obs.indicator_code.nunique()),'n_regions':len(ref),'data_sha256':basehash,'datasets':datasets,'indicators':coverage,'regions':ref,'targets':targets}
    dump(OUT/'catalog.json',index)
    status=OUT/'latest/manifest.json'
    if not status.exists():dump(status,{'schema':'semya.update/1','state':'not_yet_fetched','checked_at':None,'last_success':None,'snapshot':'2026-05-14','message':'Первичная загрузка из ЕМИСС ещё не выполнена. Доступен архивный срез экспертизы.','sources':[]})
    print(f'Packaged {len(obs):,} observations, {len(datasets)} sources, {len(ref)} geometries. Original CSV retained.')

if __name__=='__main__':build()
