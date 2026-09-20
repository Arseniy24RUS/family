from pathlib import Path
import shutil, math, textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import patches, patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.gridspec import GridSpec
import geopandas as gpd
from shapely import wkt
from shapely.ops import unary_union
import networkx as nx
from PIL import Image, ImageStat
from docx import Document
from docx.shared import Cm
from docx.oxml.ns import qn

ROOT = Path('/mnt/data/np_family_expertise_update_v6')
if ROOT.exists():
    shutil.rmtree(ROOT)
(ROOT/'code').mkdir(parents=True)
(ROOT/'figures_fixed').mkdir(parents=True)
(ROOT/'report').mkdir(parents=True)
(ROOT/'logs').mkdir(parents=True)

DATA_DIR = Path('/mnt/data/analytics_v3/np_family_expertise_artifacts_v3/data')
BASE_DOC = Path('/mnt/data/np_family_full_expertise_report_v5.docx')
OUT_DOC = ROOT/'report'/'np_family_full_expertise_report_v6.docx'

plt.rcParams.update({
    'font.family': 'Liberation Serif',
    'axes.unicode_minus': False,
    'font.size': 10,
    'axes.labelsize': 11,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 8,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'savefig.facecolor': 'white',
    'savefig.bbox': 'tight',
})

CLUSTER_COLORS = ['#4E79A7','#59A14F','#E15759','#F28E2B','#B07AA1','#76B7B2','#9C755F','#BAB0AC']
COMMUNITY_COLORS = ['#4E79A7','#59A14F','#E15759','#F28E2B','#B07AA1','#76B7B2','#9C755F','#BAB0AC','#FF9DA7','#8CD17D']
ACTIVITY_FILL = '#BDD7EE'
INDICATOR_FILL = '#F4C7C3'

SHORT = {
    '2.14.Я.1':'Бедность многодетных семей',
    '2.14.Я.2':'Суммарный коэффициент рождаемости',
    '2.14.Я.3':'СКР третьих и последующих детей',
    '2.14.Я.4':'Долговременный уход',
    '2.14.Я.5':'Центры аудиовизуального контента',
    '2.14.Я.6':'Удовлетворённость культурой',
    '2.14.Я1.1':'Ежегодная семейная выплата',
    '2.14.Я1.2':'Проактивные меры поддержки',
    '2.14.Я1.3':'Капремонт детсадов',
    '2.14.Я1.4':'Комнаты матери и ребёнка в вузах',
    '2.14.Я1.5':'Поддержка студенческих семей',
    '2.14.Я2.1':'Социальный контракт',
    '2.14.Я2.2':'Группы продлённого дня',
    '2.14.Я2.3':'Прирост многодетных семей',
    '2.14.Я2.4':'Регионы с темпами выше среднероссийских',
    '2.14.Я3.1':'Охват диспансеризацией',
    '2.14.Я3.2':'Помощь женщинам в сельской местности',
    '2.14.Я3.3':'Младенческая смертность',
    '2.14.Я3.4':'Диспансерное наблюдение детей',
    '2.14.Я3.5':'Помощь беременным',
    '2.14.Я4.1':'Активное долголетие',
    '2.14.Я5.1':'Семья как главная ценность',
    '2.14.Я5.2':'Посещения культуры',
}

def wrap_text(s, width):
    return '\n'.join(textwrap.wrap(str(s), width=width, break_long_words=False, break_on_hyphens=False))


def draw_number(ax, x, y, s, size=6.4):
    ax.text(x, y, str(s), fontsize=size, fontweight='bold', ha='center', va='center', color='black', zorder=10,
            path_effects=[pe.withStroke(linewidth=1.4, foreground='white')])


def draw_entries(ax, entries, ncols=3, fontsize=6.8, wrap_width=32, color_boxes=None, line_h=0.022, top=0.98, col_gap=0.012):
    ax.axis('off')
    wrapped = [wrap_text(e, wrap_width) for e in entries]
    n = len(wrapped)
    nrows = math.ceil(n / ncols)
    col_width = (1 - col_gap*(ncols-1)) / ncols
    columns = [wrapped[i*nrows:(i+1)*nrows] for i in range(ncols)]
    colorcols = [color_boxes[i*nrows:(i+1)*nrows] if color_boxes is not None else [None]*len(columns[i]) for i in range(ncols)]
    y = top
    for r in range(nrows):
        row_lines = 1
        row_items = []
        row_colors = []
        for c in range(ncols):
            if r < len(columns[c]):
                item = columns[c][r]
                row_items.append(item)
                row_colors.append(colorcols[c][r])
                row_lines = max(row_lines, item.count('\n')+1)
            else:
                row_items.append(None)
                row_colors.append(None)
        for c,item in enumerate(row_items):
            if item is None:
                continue
            x = c*(col_width+col_gap) + 0.01
            if row_colors[c] is not None:
                ax.add_patch(patches.Rectangle((x, y-line_h*0.85), 0.012, 0.012, transform=ax.transAxes,
                                               facecolor=row_colors[c], edgecolor='black', linewidth=0.3))
                tx = x + 0.018
            else:
                tx = x
            ax.text(tx, y, item, transform=ax.transAxes, ha='left', va='top', fontsize=fontsize, color='black')
        y -= row_lines*line_h + 0.006

# geography for map figs not changed here, but available if needed
territory_ref = pd.read_csv(DATA_DIR/'territory_reference_89.csv')
poly_raw = pd.read_csv('/mnt/data/Карта 89 субъектов РФ с населением.csv')
poly_raw['geometry'] = poly_raw['WKT'].apply(wkt.loads).apply(unary_union)
poly = gpd.GeoDataFrame(poly_raw[['Name_full','geometry']], geometry='geometry', crs='EPSG:4326')
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
geo = territory_ref.merge(poly, left_on='polygon_name', right_on='Name_full', how='left')
geo = gpd.GeoDataFrame(geo, geometry='geometry', crs='EPSG:4326')
DISPLAY_CRS = '+proj=laea +lat_0=60 +lon_0=100 +datum=WGS84 +units=m +no_defs'
display_geo = geo.to_crs(DISPLAY_CRS)


def fig1(path):
    fig = plt.figure(figsize=(13.4, 4.2), dpi=220)
    ax = fig.add_axes([0.005, 0.03, 0.99, 0.95])
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis('off')
    x0s = [0.01, 0.206, 0.402, 0.598, 0.794]
    w = 0.186
    y = 0.19
    h = 0.68
    colors = ['#E8F1FA','#EAF6EC','#FBF4E6','#F9ECE8','#F0EBF8']
    titles = ['Ресурсы','Мероприятия','Непосредственные\nрезультаты','Промежуточные\nрезультаты','Итоговые\nэффекты']
    texts = [
        'Финансирование\nНормативная база\nФедеральные и региональные\nисполнители\nИнформационные системы\nМежведомственная координация',
        'Выплаты и льготы\nРазвитие инфраструктуры\nПоддержка репродуктивного\nздоровья\nДолговременный уход\nКультурные инициативы',
        'Получатели мер поддержки\nОтремонтированные объекты\nОхват диспансеризацией\nОснащённые консультации\nСозданные сервисы\nРост доступности услуг',
        'Снижение бедности\nСнижение барьеров рождения\nУлучшение здоровья\nУкрепление устойчивости семей\nРост доступности ухода',
        'Рост реализованной\nрождаемости\nСнижение младенческой\nсмертности\nПовышение качества жизни\nсемей\nУстойчивое демографическое\nразвитие'
    ]
    for x, col, title, txt in zip(x0s, colors, titles, texts):
        box = patches.FancyBboxPatch((x,y), w,h, boxstyle='round,pad=0.007,rounding_size=0.014', facecolor=col, edgecolor='#666666', linewidth=1.0)
        ax.add_patch(box)
        ax.text(x+w/2, y+h-0.03, title, ha='center', va='top', fontsize=11.1, fontweight='bold')
        ax.text(x+w/2, y+h-0.105, txt, ha='center', va='top', fontsize=9.0, linespacing=1.18)
    for i in range(len(x0s)-1):
        ax.annotate('', xy=(x0s[i+1]-0.006, y+h/2), xytext=(x0s[i]+w+0.006, y+h/2), arrowprops=dict(arrowstyle='-|>', lw=1.8, color='#666666'))
    band = patches.FancyBboxPatch((0.03,0.045), 0.94, 0.09, boxstyle='round,pad=0.005,rounding_size=0.01', facecolor='#F7F7F7', edgecolor='#8A8A8A', linewidth=0.8)
    ax.add_patch(band)
    ax.text(0.5,0.09, 'Экспертная логика: проверка согласованности ресурсов, мероприятий, системы показателей, территориальных различий и конечного демографического эффекта', ha='center', va='center', fontsize=9.0)
    fig.savefig(path)
    plt.close(fig)


def fig14(path):
    df = pd.read_csv(DATA_DIR/'region_clusters.csv').sort_values('region_name').reset_index(drop=True)
    df['num'] = np.arange(1, len(df)+1)
    cluster_ids = sorted(df['cluster_id'].dropna().astype(int).unique())
    cmap = {cid: CLUSTER_COLORS[(i)%len(CLUSTER_COLORS)] for i,cid in enumerate(cluster_ids)}
    fig = plt.figure(figsize=(13.7, 14.5), dpi=220)
    gs = GridSpec(2,1, height_ratios=[3.2,2.1], hspace=0.06)
    ax = fig.add_subplot(gs[0])
    for cid, part in df.groupby('cluster_id', dropna=False):
        if pd.isna(cid):
            ax.scatter(part['pca1'].fillna(0), part['pca2'].fillna(0), s=130, color='#CFCFCF', edgecolors='black', linewidths=0.45, alpha=0.98, label='Недостаточно данных', zorder=3)
        else:
            cid = int(cid)
            ax.scatter(part['pca1'], part['pca2'], s=130, color=cmap[cid], edgecolors='black', linewidths=0.45, alpha=0.98, label=f'Кластер {cid}', zorder=3)
    for _,r in df.iterrows():
        draw_number(ax, r['pca1'], r['pca2'], int(r['num']), size=5.8)
    ax.axhline(0, color='#888888', lw=0.8)
    ax.axvline(0, color='#888888', lw=0.8)
    ax.grid(alpha=0.22)
    ax.set_xlabel('Первая главная компонента')
    ax.set_ylabel('Вторая главная компонента')
    ax.legend(ncol=min(4,len(cluster_ids)), loc='upper center', bbox_to_anchor=(0.5,1.02), frameon=False)
    ax.text(0.01,0.01,'Номера точек соответствуют субъектам РФ в легенде ниже', transform=ax.transAxes, fontsize=8)
    ax2 = fig.add_subplot(gs[1])
    entries = [f'{int(n)} — {name}' for n,name in zip(df['num'], df['region_name'])]
    colors = [('#CFCFCF' if pd.isna(cid) else cmap[int(cid)]) for cid in df['cluster_id']]
    draw_entries(ax2, entries, ncols=4, fontsize=7.0, wrap_width=28, color_boxes=colors, line_h=0.020)
    fig.savefig(path)
    plt.close(fig)


def fig19(path):
    edges = pd.read_csv(DATA_DIR/'activities_indicators_matrix_long.csv')
    acts = edges[['activity_id','activity']].drop_duplicates().sort_values('activity_id').reset_index(drop=True)
    inds = edges[['indicator_code']].drop_duplicates().sort_values('indicator_code').reset_index(drop=True)
    inds['indicator_name'] = inds['indicator_code'].map(lambda x: SHORT.get(x, x))
    acts['num'] = np.arange(1, len(acts)+1)
    inds['num'] = np.arange(1, len(inds)+1)
    G = nx.Graph()
    for _,r in acts.iterrows():
        G.add_node('A'+r['activity_id'], kind='A', num=int(r['num']))
    for _,r in inds.iterrows():
        G.add_node('I'+r['indicator_code'], kind='I', num=int(r['num']))
    for _,r in edges.iterrows():
        G.add_edge('A'+r['activity_id'], 'I'+r['indicator_code'], rel=r['relationship_type'])
    act_nodes = ['A'+x for x in acts['activity_id']]
    ind_nodes = ['I'+x for x in inds['indicator_code']]
    pos={}
    for i,n in enumerate(act_nodes, start=1):
        pos[n]=(0.17, 1-i/(len(act_nodes)+1))
    for i,n in enumerate(ind_nodes, start=1):
        pos[n]=(0.83, 1-i/(len(ind_nodes)+1))
    fig = plt.figure(figsize=(14.2, 22.5), dpi=220)
    gs = GridSpec(3,1, height_ratios=[3.0,1.8,1.25], hspace=0.07)
    ax = fig.add_subplot(gs[0]); ax.axis('off')
    for u,v,d in G.edges(data=True):
        ax.plot([pos[u][0],pos[v][0]],[pos[u][1],pos[v][1]], color='#6699CC' if d['rel']=='direct' else '#D0D0D0', lw=1.1 if d['rel']=='direct' else 0.75, alpha=0.72, zorder=1)
    ax.scatter([pos[n][0] for n in act_nodes],[pos[n][1] for n in act_nodes], s=155, c=ACTIVITY_FILL, edgecolors='black', linewidths=0.4, zorder=3)
    ax.scatter([pos[n][0] for n in ind_nodes],[pos[n][1] for n in ind_nodes], s=170, marker='s', c=INDICATOR_FILL, edgecolors='black', linewidths=0.4, zorder=3)
    for n in act_nodes+ind_nodes:
        x,y = pos[n]
        draw_number(ax, x, y, G.nodes[n]['num'], size=5.9)
    ax.text(0.10,1.01,'Мероприятия', transform=ax.transAxes, fontsize=11, fontweight='bold')
    ax.text(0.74,1.01,'Показатели', transform=ax.transAxes, fontsize=11, fontweight='bold')
    handles=[
        Line2D([0],[0], marker='o', markersize=8, markerfacecolor=ACTIVITY_FILL, markeredgecolor='black', color='none', label='Мероприятия'),
        Line2D([0],[0], marker='s', markersize=8, markerfacecolor=INDICATOR_FILL, markeredgecolor='black', color='none', label='Показатели'),
        Line2D([0,1],[0,0], color='#6699CC', lw=1.1, label='Прямая связь'),
        Line2D([0,1],[0,0], color='#D0D0D0', lw=0.75, label='Косвенная связь'),
    ]
    ax.legend(handles=handles, ncol=4, loc='lower center', bbox_to_anchor=(0.5,-0.03), frameon=False)
    ax1 = fig.add_subplot(gs[1])
    ax1.text(0.0,1.02,'Нумерация мероприятий', transform=ax1.transAxes, fontsize=10, fontweight='bold')
    act_entries=[f'{int(n)} — {a}' for n,a in zip(acts['num'], acts['activity'])]
    draw_entries(ax1, act_entries, ncols=3, fontsize=6.3, wrap_width=27, line_h=0.018)
    ax2 = fig.add_subplot(gs[2])
    ax2.text(0.0,1.02,'Нумерация показателей', transform=ax2.transAxes, fontsize=10, fontweight='bold')
    ind_entries=[f'{int(n)} — {code}: {name}' for n,code,name in zip(inds['num'], inds['indicator_code'], inds['indicator_name'])]
    draw_entries(ax2, ind_entries, ncols=2, fontsize=6.6, wrap_width=42, line_h=0.019)
    fig.savefig(path)
    plt.close(fig)


def fig24(path):
    edges = pd.read_csv(DATA_DIR/'region_similarity_network_edges.csv')
    comm = pd.read_csv(DATA_DIR/'region_similarity_network_communities.csv').sort_values(['community_id','region_name']).reset_index(drop=True)
    comm['num']=np.arange(1,len(comm)+1)
    G = nx.Graph()
    for _,r in comm.iterrows():
        G.add_node(int(r['region_code']), num=int(r['num']), name=r['region_name'], community=int(r['community_id']))
    # Use all available edges to ensure the network is visible.
    for _,r in edges.iterrows():
        G.add_edge(int(r['region_code_1']), int(r['region_code_2']), weight=float(r['similarity_weight']))
    pos = nx.spring_layout(G, seed=42, weight='weight', k=0.55, iterations=500)
    communities = sorted(comm['community_id'].astype(int).unique())
    cmap = {cid: COMMUNITY_COLORS[(i)%len(COMMUNITY_COLORS)] for i,cid in enumerate(communities)}
    fig = plt.figure(figsize=(14.2, 18.5), dpi=220)
    gs = GridSpec(2,1, height_ratios=[3.0,2.35], hspace=0.05)
    ax = fig.add_subplot(gs[0]); ax.axis('off')
    wmin, wmax = edges['similarity_weight'].min(), edges['similarity_weight'].max()
    for u,v,d in G.edges(data=True):
        lw = 0.25 + 1.15*((d['weight']-wmin)/(wmax-wmin+1e-9))
        ax.plot([pos[u][0],pos[v][0]],[pos[u][1],pos[v][1]], color='#B8B8B8', lw=lw, alpha=0.55, zorder=1)
    for cid in communities:
        nodes=[n for n in G.nodes if G.nodes[n]['community']==cid]
        ax.scatter([pos[n][0] for n in nodes],[pos[n][1] for n in nodes], s=115, c=cmap[cid], edgecolors='black', linewidths=0.35, label=f'Сообщество {cid}', zorder=3)
    for n in G.nodes:
        draw_number(ax, pos[n][0], pos[n][1], G.nodes[n]['num'], size=5.7)
    ax.legend(ncol=min(4,len(communities)), loc='upper center', bbox_to_anchor=(0.5,1.02), frameon=False)
    ax.text(0.01,0.01,'Номера точек соответствуют субъектам РФ в легенде ниже; цвет обозначает принадлежность к сообществу', transform=ax.transAxes, fontsize=8)
    ax2 = fig.add_subplot(gs[1])
    entries=[f'{int(n)} — {name} (сообщество {int(cid)})' for n,name,cid in zip(comm['num'], comm['region_name'], comm['community_id'])]
    colors=[cmap[int(cid)] for cid in comm['community_id']]
    draw_entries(ax2, entries, ncols=4, fontsize=6.7, wrap_width=30, color_boxes=colors, line_h=0.018)
    fig.savefig(path)
    plt.close(fig)

FIXED={
    1: ROOT/'figures_fixed'/'figure_01_logic_model_fixed_v6.png',
    14: ROOT/'figures_fixed'/'figure_14_pca_clusters_fixed_v6.png',
    19: ROOT/'figures_fixed'/'figure_19_activity_indicator_network_fixed_v6.png',
    24: ROOT/'figures_fixed'/'figure_24_region_similarity_network_fixed_v6.png',
}
fig1(FIXED[1]); fig14(FIXED[14]); fig19(FIXED[19]); fig24(FIXED[24])

# qc
rows=[]
for k,p in FIXED.items():
    img=Image.open(p).convert('RGB')
    arr=np.array(img)
    gray=np.array(img.convert('L'))
    mask = gray < 250
    rows.append({
        'figure_number':k,
        'filename':p.name,
        'size':f'{img.size[0]}x{img.size[1]}',
        'fill_ratio': float(mask.mean()),
        'std_gray': float(gray.std()),
        'unique_colors_sample': int(len(np.unique(arr.reshape(-1,3), axis=0)))
    })
pd.DataFrame(rows).to_csv(ROOT/'logs'/'qc_v6.csv', index=False)

# patch docx
base = Document(str(BASE_DOC))
def get_rids(doc):
    ids=[]
    for p in doc.paragraphs:
        if p._element.xpath('.//w:drawing'):
            for b in p._element.xpath('.//a:blip'):
                ids.append(b.get(qn('r:embed')))
    return ids
rids = get_rids(base)
for num,path in FIXED.items():
    rid = rids[num-1]
    base.part.related_parts[rid]._blob = path.read_bytes()
# sizes
for idx, shape in enumerate(base.inline_shapes, start=1):
    if idx in FIXED:
        img = Image.open(FIXED[idx])
        target_width_cm = 15.5 if idx==1 else 15.0
        target_h_cm = target_width_cm * img.size[1]/img.size[0]
        shape.width = Cm(target_width_cm)
        shape.height = Cm(target_h_cm)
base.save(str(OUT_DOC))

# save script and zip
shutil.copy2('/mnt/data/fix_v6_script.py', ROOT/'code'/'fix_figures_and_report_v6.py')
manifest=[]
for p in ROOT.rglob('*'):
    if p.is_file():
        manifest.append({'path': str(p.relative_to(ROOT)), 'size_bytes': p.stat().st_size})
pd.DataFrame(manifest).sort_values('path').to_csv(ROOT/'logs'/'manifest_v6.csv', index=False)
import shutil as sh
zip_base='/mnt/data/np_family_expertise_update_v6_package'
for ext in ['.zip']:
    try: Path(zip_base+ext).unlink()
    except: pass
sh.make_archive(zip_base, 'zip', ROOT)
print('done', OUT_DOC)
print('zip', zip_base+'.zip')
