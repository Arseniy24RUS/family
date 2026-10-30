"""Youth statistical contracts shared by offline import, refresh and analytics.

No aggregation across categories, statistical periods or national/regional units.
Every raw observation survives; analysis exclusions are explicit and reversible.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'youth_children'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT
STATISTICAL_AS_OF = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'

SOURCE_NOTES = {
    '62932': ('Добровольчество и общественная деятельность', 'year', 'Накопленный с января зарегистрированный охват молодёжи 14–35 лет. Январский сброс не означает утрату участия.'),
    '62931': ('Программы развития и патриотического воспитания', 'year', 'Накопление с января. Региональная формула использует максимум двух долей; это не доля уникальных участников объединения программ.'),
    '62935': ('Культурные проекты и традиционные ценности', 'administrative', 'Доля финансируемых проектов по административному критерию; 100% не означает воздействие на ценности всей молодёжи. В методике отмечено расхождение обозначений периода знаменателя.'),
    '62936': ('Уверенность в самореализации', 'survey_max', 'Максимум квартальных долей положительных ответов респондентов 18–35 лет. Без характеристик выборок разность нельзя считать статистически значимой.'),
    '62934': ('Индекс условий воспитания', 'index', 'Составной индекс из четырёх компонентов, включая отношение к планам. Он не является измерением качества личности.'),
    '62969': ('Повышение квалификации педагогов', 'project', 'Накопление с начала национального проекта. Охват обучением не измеряет применение компетенций и качество преподавания.'),
    '62968': ('Развитие способностей и талантов', 'year', 'Зарегистрированный охват системой мер. Накопительные записи не являются независимыми наблюдениями; аномалия декабря 2025 года требует разъяснения производителя.'),
    '62895': ('Иностранные обучающиеся', 'stock', 'Контингент на конец периода, а не число новых поступивших. Отдельный годовой факт и оперативные месячные записи не объединяются.'),
    '62898': ('Несколько квалификаций', 'administrative', 'Факт дополнительной бесплатной квалификации не удостоверяет её трудовую отдачу. Годовое значение выделяется отдельно.'),
    '63036': ('Капитальный ремонт школьных зданий', 'project', 'Показатель состояния фонда зданий включает ремонты предшествующего периода; изменение не является чистым эффектом нового проекта.'),
}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(encode(value))
    temp.replace(path)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def territory_key(name):
    text = re.sub(r'\s+', ' ', str(name).casefold().replace('ё', 'е')).strip().replace('–', '-').replace('—', '-')
    text = re.sub(r'^(?:г\.?|город)\s+', '', text)
    return re.sub(r'\s*-\s*', '-', text)


def region_aliases(root=ROOT):
    catalog = load(root / 'public/data/catalog.json')
    aliases = {territory_key(r['name']): str(r['id']) for r in catalog['regions']}
    for entry in catalog['datasets']:
        p = root / f'public/data/baseline/{entry["id"]}.json'
        if not p.exists():
            continue
        packet = load(p)
        for values in packet['rows']:
            r = dict(zip(packet['columns'], values))
            if r.get('r'):
                aliases[territory_key(r['territory'])] = str(r['r'])
    aliases.update({territory_key('Город Москва столица Российской Федерации город федерального значения'): '77',
                    territory_key('Город Санкт-Петербург город федерального значения'): '78',
                    territory_key('Город федерального значения Севастополь'): '92',
                    territory_key('Республика Адыгея (Адыгея)'): '01',
                    territory_key('Республика Татарстан (Татарстан)'): '16'})
    # Use exactly the existing catalog's identifier formatting.
    by_number = {int(r['id']): str(r['id']) for r in catalog['regions'] if str(r['id']).isdigit()}
    aliases = {k: by_number.get(int(v), v) if str(v).isdigit() else v for k, v in aliases.items()}
    return aliases


def observation_key(source_id, name, frequency, start, end, category):
    values = [source_id, territory_key(name), frequency, start, end, json.dumps(category, ensure_ascii=False, sort_keys=True)]
    return hashlib.sha256('|'.join(values).encode()).hexdigest()


def classify_flags(source_id, value, period, geography, unit):
    flags = []
    def flag(code, message, exclude=True, severity='warning'):
        flags.append({'code': code, 'message': message, 'severity': severity, 'exclude_from_analysis': exclude})
    if value is None:
        flag('missing', 'В источнике нет числового значения.', severity='info')
    elif not math.isfinite(value):
        raise ValueError('Non-finite observation')
    elif value < 0:
        flag('negative', 'Отрицательное значение не соответствует области определения.')
    elif unit.casefold() in ('процент', '%') and value > 100:
        flag('outside_0_100', 'Значение находится вне интервала 0–100%.')
    if source_id == '62968' and geography == 'national' and period == '2025-12' and value == 6.31:
        flag('talent_december_2025', 'В первичной статистике опубликовано 6,31% после 95,95% в ноябре. Исключено из интерпретации динамики до разъяснения производителя.')
    if source_id == '62936' and geography == 'national' and period in ('2025-01', '2026-01', '2026-02') and value == 0:
        flag('survey_zero_requires_review', 'Нулевая запись опросного показателя не интерпретируется как отсутствие уверенности в самореализации.')
    return flags


def normalize_record(row, source, aliases):
    if str(row['source_id']) != str(source['indicator_id']):
        raise ValueError('Source identity mismatch')
    if row['unit'].casefold().strip() != source['unit'].casefold().strip():
        raise ValueError('Unit mismatch')
    frequency = row['period_kind']
    if frequency not in ('annual', 'monthly', 'cumulative_ytd', 'quarterly'):
        raise ValueError('Unsupported explicitly identified frequency: ' + str(frequency))
    start, end = row['period_start'], row['period_end']
    if not start or not end:
        raise ValueError('Observation lacks explicit dates')
    name = row['territory_name']
    code = aliases.get(territory_key(name))
    geography = 'national' if territory_key(name) == territory_key('Российская Федерация') else 'regional' if code else 'other'
    year = int(row['year'])
    if frequency == 'annual':
        period = str(year)
    elif frequency in ('monthly', 'cumulative_ytd'):
        period = end[:7]
    else:
        period = f'{year}-Q{(int(end[5:7]) - 1) // 3 + 1}'
    dimensions = json.loads(row.get('dimensions_json') or '{}')
    ignored = {'Показатель', 'Год', 'Период', 'Единица измерения', 'ОКАТО', 'ОКТМО', 'ОКСМ'}
    category = {k: v for k, v in dimensions.items() if k not in ignored}
    value = row.get('value_numeric')
    flags = classify_flags(source['indicator_id'], value, period, geography, source['unit'])
    excluded = any(f['exclude_from_analysis'] for f in flags)
    return {
        'id': observation_key(source['indicator_id'], name, frequency, start, end, category),
        'source_id': str(source['indicator_id']), 'source_observation_key': row.get('observation_key'),
        'name': name, 'code': code, 'map_id': code, 'geo_level': geography,
        'territory_code_source': row.get('territory_code'), 'territory_level_source': row.get('territory_level'),
        'period': period, 'period_start': start, 'period_end': end, 'year': year,
        'frequency': frequency, 'value': value, 'raw': row.get('value_raw'), 'unit': source['unit'],
        'category': category, 'quality_flags': flags, 'excluded': excluded,
        'analytical_value': None if excluded else value,
        'status': 'missing' if value is None else 'review_required' if excluded else 'valid',
    }


def normalize_payload(payload, aliases):
    snapshot = payload.get('snapshot')
    source = payload['config']
    if snapshot and snapshot['origin_kind'] != 'live_emiss':
        raise ValueError('Only verified live_emiss snapshot inputs are accepted')
    rows = [normalize_record(row, source, aliases) for row in payload['observations']]
    seen = {}
    for row in rows:
        if row['id'] in seen:
            raise ValueError('Duplicate observation identity after normalization')
        seen[row['id']] = row
    rows.sort(key=lambda row: (row['period_end'], row['frequency'], row['name'], row['id']))
    return {'schema_version': 1, 'project_id': PROJECT, 'source_id': source['indicator_id'],
            'unit': source['unit'], 'source_url': source['source_url'],
            'published_at': snapshot['acquired_at'] if snapshot else None,
            'snapshot_id': snapshot['snapshot_id'] if snapshot else None,
            'origin_kind': 'live_emiss' if snapshot else 'metadata_only',
            'observations': rows}


def csv_write(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in row.items() if k in fields})


def quantile(values, probability):
    """Hyndman–Fan type 7 / NumPy linear quantile, unweighted territories."""
    values = sorted(values)
    if not values:
        return None
    rank = (len(values) - 1) * probability
    lo, hi = math.floor(rank), math.ceil(rank)
    return values[lo] + (values[hi] - values[lo]) * (rank - lo)


def merge_observations(previous, incoming):
    lookup = {r['id']: dict(r) for r in previous}
    revisions = []
    added = 0
    received = {}
    for row in incoming:
        if row['id'] in received:
            old_incoming = received[row['id']]
            if any(old_incoming[key] != row[key] for key in ('value', 'unit', 'category')):
                raise ValueError('Conflicting duplicate observations in incoming source')
            continue
        received[row['id']] = row
        old = lookup.get(row['id'])
        if old is None:
            lookup[row['id']] = row
            added += 1
            continue
        if old['unit'] != row['unit'] or old['category'] != row['category']:
            raise ValueError('Historical unit or category changed')
        if row['value'] is None and old['value'] is not None:
            continue
        if old['value'] != row['value']:
            revisions.append({'id': row['id'], 'name': row['name'], 'period': row['period'], 'old_value': old['value'], 'new_value': row['value']})
        lookup[row['id']] = row
    out = sorted(lookup.values(), key=lambda row: (row['period_end'], row['frequency'], row['name'], row['id']))
    return out, added, revisions
