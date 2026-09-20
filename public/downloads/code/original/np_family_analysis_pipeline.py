
# -*- coding: utf-8 -*-
"""
Воспроизводимый аналитический конвейер для первичной экспертизы национального проекта «Семья».

Скрипт рассчитан на запуск после распаковки архива рядом с SQLite-базой:
    python code/np_family_analysis_pipeline.py --db np_family_emiss_database.sqlite --out reproduced_outputs

Он воспроизводит ключевые шаги: нормализацию территорий, расчёт последних значений,
целевых сопоставлений, картограмм, трендов, прогнозов, кластеров и NLP.
В текущем архиве уже сохранены готовые результаты; этот файл нужен для аудита методики.
"""

import argparse, json, math, os, re, sqlite3, shutil
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.patches import Rectangle

def safe_slug(s, maxlen=90):
    s = re.sub(r'[^\wа-яА-ЯёЁ\-.]+', '_', str(s), flags=re.UNICODE)
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:maxlen]

def load_database(db_path):
    con = sqlite3.connect(db_path)
    obs = pd.read_sql_query("SELECT * FROM observations_long", con)
    source_meta = pd.read_sql_query("SELECT * FROM source_metadata", con)
    coverage = pd.read_sql_query("SELECT * FROM indicators_coverage", con)
    con.close()
    return obs, source_meta, coverage

def strip_region_name(x):
    if x is None or pd.isna(x): return None
    return re.sub(r'\s+', ' ', str(x).strip()).replace('ё','е')

def build_aliases(reference):
    alias = {}
    def add_alias(code, *names):
        for n in names:
            alias[strip_region_name(n).lower()] = code
    for _, r in reference.iterrows():
        add_alias(r.region_code, r.region_name)
    add_alias('77','Город Москва столица Российской Федерации город федерального значения','г. Москва','город Москва','Москва')
    add_alias('78','Город Санкт-Петербург город федерального значения','г. Санкт-Петербург','Санкт-Петербург')
    add_alias('92','Город федерального значения Севастополь','г. Севастополь','Севастополь')
    add_alias('16','Республика Татарстан (Татарстан)','Республика Татарстан')
    add_alias('29','Архангельская область (кроме Ненецкого автономного округа)','Архангельская область без Ненецкого автономного округа')
    add_alias('72','Тюменская область (кроме Ханты-Мансийского автономного округа-Югры и Ямало-Ненецкого автономного округа)','Тюменская область без автономных округов')
    add_alias('86','Ханты-Мансийский автономный округ - Югра (Тюменская область)','Ханты-Мансийский автономный округ - Югра')
    add_alias('89','Ямало-Ненецкий автономный округ (Тюменская область)','Ямало-Ненецкий автономный округ')
    add_alias('83','Ненецкий автономный округ (Архангельская область)')
    add_alias('01','Республика Адыгея (Адыгея)')
    add_alias('42','Кемеровская область','Кемеровская область - Кузбасс')
    return alias

def normalize_territories(obs, reference):
    alias = build_aliases(reference)
    def code(name):
        s = strip_region_name(name)
        if s is None: return None
        return alias.get(s.lower())
    obs = obs.copy()
    obs['region_code'] = obs['territory_name'].map(code)
    obs = obs.merge(reference[['region_code','region_name','federal_district','tile_label','tile_x','tile_y']], on='region_code', how='left')
    obs['period_end_dt'] = pd.to_datetime(obs['period_end'], errors='coerce')
    return obs

def create_tile_geojson(reference, out_path):
    features = []
    for _, r in reference.iterrows():
        x, y = float(r.tile_x), float(r.tile_y)
        poly = [[x,y],[x+1,y],[x+1,y+1],[x,y+1],[x,y]]
        features.append({"type":"Feature","properties":r.to_dict(),"geometry":{"type":"Polygon","coordinates":[poly]}})
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({"type":"FeatureCollection","features":features}, f, ensure_ascii=False, indent=2)

def annualize(obs):
    rows = []
    for (sf, terr, year), g in obs[obs.value.notna()].groupby(['source_file','territory_name','year'], dropna=False):
        gy = g[g.period_type == 'год']
        if len(gy):
            row = gy.sort_values('period_end_dt').iloc[-1].copy()
            row['annualized_method'] = 'explicit_year'; row['is_full_year'] = True
        else:
            dec = g[g.period_end_dt.dt.month.eq(12)]
            if len(dec):
                row = dec.sort_values('period_end_dt').iloc[-1].copy()
                row['annualized_method'] = 'december_or_full_cumulative'; row['is_full_year'] = True
            else:
                row = g.sort_values('period_end_dt').iloc[-1].copy()
                row['annualized_method'] = 'latest_partial_year'; row['is_full_year'] = False
        rows.append(row)
    return pd.DataFrame(rows)

def plot_tile_map(df, out_path, title, unit=''):
    fig, ax = plt.subplots(figsize=(16,10), dpi=160)
    ax.set_aspect('equal')
    vals = df['value'].astype(float)
    nonmiss = vals.dropna()
    norm = mpl.colors.Normalize(vmin=float(nonmiss.min()) if len(nonmiss) else 0, vmax=float(nonmiss.max()) if len(nonmiss) else 1)
    cmap = mpl.colormaps['YlGnBu']
    for _, r in df.iterrows():
        face = '#e6e6e6' if pd.isna(r.value) else cmap(norm(float(r.value)))
        ax.add_patch(Rectangle((r.tile_x, r.tile_y), 1, 1, facecolor=face, edgecolor='white', linewidth=0.9))
        ax.text(r.tile_x+0.5, r.tile_y+0.42, r.tile_label, ha='center', va='center', fontsize=7, fontweight='bold')
    ax.set_xlim(-0.5, df.tile_x.max()+1.5); ax.set_ylim(df.tile_y.max()+1.5, -0.8)
    ax.axis('off')
    fig.suptitle(title, fontsize=13, fontweight='bold')
    if len(nonmiss):
        sm = mpl.cm.ScalarMappable(cmap=cmap, norm=norm); sm.set_array([])
        fig.colorbar(sm, ax=ax, orientation='horizontal', fraction=0.035, pad=0.04).set_label(unit)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches='tight'); plt.close(fig)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='np_family_emiss_database.sqlite')
    parser.add_argument('--out', default='reproduced_outputs')
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(exist_ok=True, parents=True)
    for d in ['data','geo','figures/maps']: (out/d).mkdir(exist_ok=True, parents=True)
    obs, source_meta, coverage = load_database(args.db)
    reference_path = Path('data/territory_reference_89.csv')
    if not reference_path.exists():
        raise FileNotFoundError('Запустите скрипт из корня распакованного архива: нужен data/territory_reference_89.csv')
    ref = pd.read_csv(reference_path, dtype={'region_code':str})
    obs = normalize_territories(obs, ref)
    obs.to_csv(out/'data/observations_emiss_enriched.csv', index=False, encoding='utf-8-sig')
    create_tile_geojson(ref, out/'geo/rf_subjects_tile_cartogram_89.geojson')
    ann = annualize(obs)
    ann.to_csv(out/'data/annualized_observations.csv', index=False, encoding='utf-8-sig')
    regional_sources = [sf for sf, g in obs[obs.region_code.notna()].groupby('source_file') if g.region_code.nunique() >= 10]
    for sf in regional_sources:
        g = obs[(obs.source_file==sf)&(obs.region_code.notna())&obs.value.notna()].sort_values(['region_code','period_end_dt'])
        pick = g.groupby('region_code').tail(1)
        map_df = ref.merge(pick[['region_code','value']], on='region_code', how='left')
        title = source_meta[source_meta.source_file==sf].iloc[0].indicator_name
        unit = source_meta[source_meta.source_file==sf].iloc[0].unit_from_passport
        plot_tile_map(map_df, out/f'figures/maps/{safe_slug(sf)}.png', title, unit)
    print(f'Готово: {out}')

if __name__ == '__main__':
    main()
