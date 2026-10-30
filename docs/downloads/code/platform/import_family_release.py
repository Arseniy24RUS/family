#!/usr/bin/env python3
"""Read-only import of exact Family contracts from the research release.

Every source has a self-contained input ZIP. --from-inputs reproduces the
published JSON without a database or network connection.
"""
from __future__ import annotations
import argparse, calendar, gzip, hashlib, json, re, sqlite3, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATISTICAL_SNAPSHOT = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'
MONTHS = ['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь']
COLS = ['id','r','territory','type','year','start','end','label','value','raw','flag','dimensions','fetched_at']

def territory_key(text):
    text = re.sub(r'\s+', ' ', str(text).lower().replace('ё','е')).strip().replace('–','-').replace('—','-')
    text = re.sub(r'^(?:г\.?|город)\s+', '', text)
    return re.sub(r'\s*-\s*', '-', text)

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value))

def period(row):
    dimensions = json.loads(row['dimensions_json'])
    label = dimensions.get('Период', row['period_raw'] or '')
    kind, year = row['period_kind'], int(row['year'])
    start, end = row['period_start'], row['period_end']
    if kind == 'annual': return 'год', start, end, 'значение показателя за год'
    if kind == 'monthly': return 'месяц', start, end, label
    if kind == 'cumulative_ytd':
        month = int(end[5:7])
        return 'накопительно с января', start, end, 'январь' if month == 1 else 'январь–' + MONTHS[month-1]
    # Decode explicitly labelled quarters only; cell order is never evidence.
    match = re.fullmatch(r'\s*(I{1,3}|IV)\s+квартал\s*', label, re.I)
    if match:
        q = {'I': 1, 'II': 2, 'III': 3, 'IV': 4}[match.group(1).upper()]
        month = q*3
        return 'квартал', f'{year}-{month-2:02d}-01', f'{year}-{month:02d}-{calendar.monthrange(year,month)[1]}', label
    raise ValueError(f'Unresolved explicit period: {row["source_id"]} / {label}')

def aliases_for(root):
    cat = load(root/'public/data/catalog.json')
    aliases = {territory_key(r['name']): r['id'] for r in cat['regions']}
    for source in cat['datasets']:
        packet = load(root/f'public/data/baseline/{source["id"]}.json')
        for values in packet['rows']:
            row = dict(zip(packet['columns'], values))
            if row.get('r'): aliases[territory_key(row['territory'])] = row['r']
    return aliases

def packet_for(payload, aliases):
    config, snapshot = payload['config'], payload['snapshot']
    if snapshot['origin_kind'] != 'live_emiss': raise ValueError('Only current live_emiss sources may be imported')
    if snapshot['acquired_at'][:10] > STATISTICAL_SNAPSHOT: raise ValueError('Snapshot is later than the stated cutoff')
    rows, keys = [], set()
    for observation in payload['observations']:
        if observation['source_id'] != config['indicator_id'] or observation['unit'] != config['unit']:
            raise ValueError('Source identifier or unit differs from the original Family contract')
        typ, start, end, label = period(observation)
        if not start or not end: raise ValueError('Cannot publish a row without an explicit period')
        territory = observation['territory_name']
        rid = aliases.get(territory_key(territory))
        value = observation['value_numeric']
        flag = ''
        if value is None: flag = 'missing'
        elif value < 0: flag = 'negative'
        elif value > 100 and config['unit'] == 'процент' and config['source_id'] != 'data_35': flag = 'outside_0_100'
        natural = '|'.join([config['source_id'], territory_key(territory), typ, start, end])
        if natural in keys: raise ValueError('Additional dimensions collapse to duplicate browser-series keys')
        keys.add(natural)
        oid = 'emiss_' + hashlib.sha256(natural.encode()).hexdigest()[:18]
        rows.append(dict(zip(COLS, [oid,rid,territory,typ,int(observation['year']),start,end,label,value,observation['value_raw'],flag,{'Единица измерения':observation['unit']},snapshot['acquired_at']])))
    rows.sort(key=lambda r: (r['end'],r['type'],r['territory'],r['id']))
    return {'schema':'semya.series/1','source_id':config['source_id'],'columns':COLS,
            'rows':[[row[c] for c in COLS] for row in rows],'basis':'current',
            'snapshot':STATISTICAL_SNAPSHOT,'emiss_id':config['indicator_id'],
            'source_url':f'https://www.fedstat.ru/indicator/{config["indicator_id"]}',
            'unit':config['unit'],'research_release':RELEASE,'snapshot_id':snapshot['snapshot_id']}

def input_path(root, sid): return root/f'public/data/latest/{sid}_release_input.zip'

def bundle(path, payload, source_root):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr('input.json', encoded(payload))
        # Query files are omitted; normalized input and verified official source
        # files retain reproducibility without relying on transport parameters.
        for entry in json.loads(payload['snapshot']['raw_manifest_json']):
            rel = entry.get('path')
            if not rel: continue
            rel = '/'.join(part for part in rel.replace('\\','/').split('/') if part)
            actual = source_root/rel
            if not actual.is_file(): raise FileNotFoundError(actual)
            content = actual.read_bytes()
            # The collection manifest hashes uncompressed transport bytes.
            check = gzip.decompress(content) if rel.endswith('.gz') else content
            if entry.get('sha256') and hashlib.sha256(check).hexdigest() != entry['sha256']:
                raise ValueError(f'Original source checksum mismatch: {rel}')
            archive.writestr('source/'+rel,content)

def run(root, release=None, from_inputs=False):
    config = load(root/'scripts/emiss_sources.json')
    aliases = aliases_for(root)
    connection = None
    if not from_inputs:
        if not release: raise ValueError('--release is required unless --from-inputs is supplied')
        source_root = release/'source_statistics'
        connection = sqlite3.connect(f'file:{source_root}/data/national_projects.sqlite?mode=ro',uri=True)
        connection.row_factory = sqlite3.Row
    entries, receipts = [], []
    for source in config['sources']:
        sid = source['source_id']; path = input_path(root,sid)
        if from_inputs:
            with zipfile.ZipFile(path) as archive: payload = json.loads(archive.read('input.json'))
        else:
            matched = connection.execute('select 1 from indicator_sources where source_id=? and indicator_code=?',(source['indicator_id'],source['indicator_code'])).fetchone()
            if not matched: raise ValueError(f'Exact indicator/source match absent: {sid}')
            snap = dict(connection.execute('select s.* from snapshots s join current_sources c using(snapshot_id,source_id) where source_id=?',(source['indicator_id'],)).fetchone())
            observations = [dict(r) for r in connection.execute('select * from observations where snapshot_id=? order by observation_key',(snap['snapshot_id'],))]
            payload = {'schema':'semya.research-input/1','research_release':RELEASE,'statistical_snapshot':STATISTICAL_SNAPSHOT,'config':source,'snapshot':snap,'observations':observations}
            path.parent.mkdir(parents=True,exist_ok=True); bundle(path,payload,source_root)
        packet = packet_for(payload,aliases)
        if payload['config'] != source: raise ValueError('Bundled contract differs from emiss_sources.json')
        output = root/f'public/data/latest/{sid}.json'; write(output,packet)
        provenance = {'schema':'semya.release-provenance/1','research_release':RELEASE,
            'source_id':sid,'indicator_id':source['indicator_id'],'indicator_code':source['indicator_code'],
            'unit':source['unit'],'source_url':packet['source_url'],'origin_kind':'live_emiss',
            'snapshot_id':payload['snapshot']['snapshot_id'],'statistical_snapshot':STATISTICAL_SNAPSHOT,
            'acquired_at':payload['snapshot']['acquired_at'],'observations':len(packet['rows']),
            'published_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'input_bundle':f'data/latest/{path.name}','input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'period_policy':'Explicit annual, monthly, cumulative YTD and quarter labels kept distinct',
            'missing_policy':'Original missing cells retained; no imputation; no archive substitution'}
        write(root/f'public/data/latest/{sid}_provenance.json',provenance)
        entries.append({'source_id':sid,'state':'updated','message':'Проверенный срез ЕМИСС из исследовательского выпуска 1.2.0.',
            'checked_at':payload['snapshot']['acquired_at'],'fetched_at':payload['snapshot']['acquired_at'],
            'last_success':payload['snapshot']['acquired_at'],'indicator_id':source['indicator_id'],
            'new_rows':None,'revisions':None,'raw_file':f'data/latest/{path.name}',
            'provenance_file':f'data/latest/{sid}_provenance.json','published_file':f'data/latest/{sid}.json','rows':len(packet['rows'])})
        receipts.append(provenance)
    checked = max(e['checked_at'] for e in entries)
    write(root/'public/data/latest/manifest.json',{'schema':'semya.update/1','state':'updated','checked_at':checked,
        'last_success':checked,'snapshot':STATISTICAL_SNAPSHOT,'research_release':RELEASE,
        'message':'16 источников ЕМИСС. Статистический срез 15.10.2026; дата сборки сайта не означает обновление статистики.','sources':entries})
    write(root/'public/data/latest/import_validation.json',{'schema':'semya.import-validation/1','sources':receipts,
        'n_sources':len(entries),'n_observations':sum(e['rows'] for e in entries),'statistical_snapshot':STATISTICAL_SNAPSHOT,
        'source_contract':'exact indicator code + EMISS id + unit','replay_command':'python scripts/import_family_release.py --from-inputs'})
    if connection: connection.close()
    print(f'Imported {len(entries)} Family sources, {sum(e["rows"] for e in entries)} cells')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--release',type=Path); parser.add_argument('--from-inputs',action='store_true')
    args = parser.parse_args(); run(args.root,args.release,args.from_inputs)
