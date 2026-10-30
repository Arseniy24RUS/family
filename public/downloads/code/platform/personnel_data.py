"""Personnel statistical contracts shared by offline import, refresh and analytics.

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
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'personnel'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT / 'statistical'
STATISTICAL_AS_OF = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'

SOURCE_NOTES = {
    '62884': ('Демографически стандартизированный индекс занятости', 'index', 'Фактическая занятость относительно расчётной численности при возрастных уровнях занятости 2024 года. Это индекс, значения выше 100 допустимы. Он не измеряет долю закрытых вакансий или причинный вклад проекта.'),
    '63038': ('Участие в активных мерах относительно плана', 'year', 'Отношение участников к плановой численности. Значения выше 100 допустимы. Накопление начинается заново каждый год, плановый знаменатель может меняться. Декабрь приравнивается к году по методике № 126.'),
    '62907': ('Занятость завершивших обучение', 'cohort_ytd', 'Доля включает трудоустроенных и сохранивших занятость. Отдельная годовая запись имеет приоритет над декабрьской. В карточке ЕМИСС сохранена ссылка на № 543, тогда как приказ № 127 от 01.04.2026 заменил методику: сопоставимость требует проверки производителя.'),
    '63363': ('Оборудованные рабочие места для инвалидов', 'project', 'Накопление с начала мероприятия относительно квоты первого полугодия 2024 года. Декабрь приравнивается к году по методике № 645. Снижение после декабря не является предусмотренным календарным сбросом. Его причина требует проверки компонентов и истории публикаций.'),
    '63238': ('Престиж рабочих профессий', 'survey_quarterly', 'Квартальные опросные оценки по методике № 472. Подписи ЕМИСС март/июнь/сентябрь/декабрь обозначают последний месяц квартала. IV квартал приравнивается к году. Ошибки и веса конкретных волн не опубликованы.'),
    '63205': ('Занятость выпускников СПО через два года', 'cohort', 'Метаданные установлены, числовые наблюдения не опубликованы в проверенном срезе. Требуется одинаковое определение выпуска и занятости.'),
    '63204': ('Занятость выпускников СПО через год', 'cohort', 'Метаданные установлены, числовые наблюдения не опубликованы в проверенном срезе. Требуется одинаковое определение выпуска и занятости.'),
    '63190': ('Занятость выпускников вузов через год', 'cohort', 'Метаданные установлены, числовые наблюдения не опубликованы в проверенном срезе. При сравнении с целью необходимо сохранять редакцию паспорта.'),
    '63191': ('Занятость выпускников вузов через два года', 'cohort', 'Метаданные установлены, числовые наблюдения не опубликованы в проверенном срезе. При сравнении с целью необходимо сохранять редакцию паспорта.'),
}

ANNUAL_EQUIVALENCE = {
    '63038': {'suffix': '-12', 'frequencies': ['monthly', 'cumulative_ytd'], 'order': 'Приказ Минтруда России от 19.03.2025 № 126', 'basis': 'Значение на конец декабря приравнивается к значению за отчётный год.', 'url': 'https://base.garant.ru/412106472/'},
    '63363': {'suffix': '-12', 'frequencies': ['monthly', 'cumulative_ytd'], 'order': 'Приказ Минтруда России от 29.11.2024 № 645, редакция от 03.04.2025', 'basis': 'Годовое значение принимается численно равным значению за декабрь.', 'url': 'https://rulaws.ru/acts/Prikaz-Mintruda-Rossii-ot-29.11.2024-N-645/'},
    '63238': {'suffix': '-Q4', 'frequencies': ['quarterly'], 'order': 'Приказ Минтруда России от 30.07.2025 № 472', 'basis': 'Последний квартал отчётного года приравнивается к годовому значению.', 'url': 'https://rulaws.ru/acts/Prikaz-Mintruda-Rossii-ot-30.07.2025-N-472/'},
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
    elif unit.casefold() in ('процент', '%') and value > 100 and source_id not in {'62884', '63038'}:
        flag('outside_0_100', 'Значение находится вне интервала 0–100%.')
    if source_id == '63038' and value is not None and value > 100:
        flag('plan_ratio_above_100_allowed', 'Отношение фактической численности к плановой закономерно допускает значение выше 100%.', exclude=False, severity='info')
    if source_id == '62907' and value == 0:
        flag('zero_denominator_components_unavailable', 'Исходный ноль сохранён. Без числителя и знаменателя он не доказывает отсутствие занятости завершивших обучение.', exclude=False)
    if source_id == '62907':
        flag('methodology_543_127_comparability', 'Карточка ЕМИСС ссылается на приказ № 543, заменённый приказом № 127 от 01.04.2026. Наблюдения сохранены с явным ограничением сопоставимости.', exclude=False, severity='info')
    if source_id == '63238':
        flag('survey_sampling_uncertainty_unavailable', 'Опубликованная доля не содержит фактической стандартной ошибки и весов данной опросной волны.', exclude=False, severity='info')
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
    date.fromisoformat(start)
    date.fromisoformat(end)
    if start > end:
        raise ValueError('Observation starts after its end')
    source_frequency, source_start, source_end = frequency, start, end
    name = row['territory_name']
    code = aliases.get(territory_key(name))
    geography = 'national' if territory_key(name) == territory_key('Российская Федерация') else 'regional' if code else 'other'
    year = int(row['year'])
    if int(end[:4]) != year or int(start[:4]) != year:
        raise ValueError('Observation year and dates differ')
    transformations = []
    if source['indicator_id'] == '63238' and frequency in ('monthly', 'cumulative_ytd'):
        month = int(end[5:7])
        if month not in (3, 6, 9, 12) or end != f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]}':
            raise ValueError('Prestige survey period is not a confirmed quarter end')
        frequency = 'quarterly'
        start = f'{year}-{month - 2:02d}-01'
        transformations.append({'code': 'quarter_end_label', 'basis': 'Приказ Минтруда России от 30.07.2025 № 472, пункты 7–9', 'description': 'Подпись последнего месяца квартала в ЕМИСС приведена к квартальной периодичности; значение не усреднялось.'})
    if source['indicator_id'] == '62907' and frequency == 'monthly':
        frequency = 'cumulative_ytd'
        start = f'{year}-01-01'
        transformations.append({'code': 'training_ytd', 'basis': 'Накопительный состав завершивших обучение в течение отчётного года', 'description': 'Месячная подпись источника сохраняется отдельно от накопительного аналитического периода.'})
    month = int(end[5:7])
    if frequency == 'annual' and (start != f'{year}-01-01' or end != f'{year}-12-31'):
        raise ValueError('Annual observation does not cover a full year')
    if frequency in ('monthly', 'cumulative_ytd'):
        expected_start = f'{year}-01-01' if frequency == 'cumulative_ytd' else f'{year}-{month:02d}-01'
        if start != expected_start or end != f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]}':
            raise ValueError('Monthly observation has inconsistent explicit dates')
    if frequency == 'quarterly' and (month not in (3, 6, 9, 12) or start != f'{year}-{month - 2:02d}-01' or end != f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]}'):
        raise ValueError('Quarterly observation has inconsistent explicit dates')
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
        'source_frequency': source_frequency, 'source_period_start': source_start, 'source_period_end': source_end,
        'source_period_label': dimensions.get('Период'), 'period_transformations': transformations,
        'original_analysis_status': row.get('analysis_status'), 'original_quality_flags': row.get('quality_flags_json', row.get('quality_flags')),
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
    rows = series_flags(rows, source['indicator_id'])
    return {'schema_version': 1, 'project_id': PROJECT, 'source_id': source['indicator_id'],
            'unit': source['unit'], 'source_url': source['source_url'],
            'published_at': snapshot['acquired_at'] if snapshot else None,
            'snapshot_id': snapshot['snapshot_id'] if snapshot else None,
            'origin_kind': 'live_emiss' if snapshot else 'metadata_only',
            'observations': rows}


def series_flags(rows, source_id):
    """Flag observed decreases without inferring their cause or smoothing."""
    rows = [dict(row, quality_flags=[f for f in row['quality_flags'] if f['code'] not in {'cumulative_revision_requires_review', 'cumulative_decrease_requires_review'}]) for row in rows]
    if source_id == '63363':
        by_group = {}
        for row in sorted(rows, key=lambda r: (r['period_end'], r['id'])):
            if row['frequency'] not in ('monthly', 'cumulative_ytd') or row['value'] is None:
                continue
            key = (row['name'], json.dumps(row['category'], ensure_ascii=False, sort_keys=True))
            previous = by_group.get(key)
            if previous and row['value'] < previous['value']:
                row['quality_flags'].append({'code': 'cumulative_decrease_requires_review', 'message': f'Накопительный показатель снизился с {previous["value"]} за {previous["period"]} до {row["value"]}. Календарный сброс методикой не предусмотрен. Причина снижения не установлена; необходимы компоненты и история публикаций.', 'severity': 'warning', 'exclude_from_analysis': False})
            by_group[key] = row
    return rows


def annual_equivalents(source_id, rows):
    """References to existing final-period observations, never extra data cells."""
    rule = ANNUAL_EQUIVALENCE.get(str(source_id))
    if not rule:
        return []
    explicit_years = {r['year'] for r in rows if r['frequency'] == 'annual' and not r['excluded'] and not r['category'] and r['geo_level'] == 'national'}
    results = []
    for row in rows:
        if row['year'] in explicit_years or row['excluded'] or row['category'] or row['geo_level'] != 'national':
            continue
        if row['frequency'] not in rule['frequencies'] or not row['period'].endswith(rule['suffix']):
            continue
        results.append({**row, 'period': str(row['year']), 'period_start': f'{row["year"]}-01-01',
                        'frequency': 'annual_equivalent', 'original_period': row['period'], 'original_frequency': row['frequency'],
                        'reference_observation_id': row['id'], 'independent_observation': False,
                        'annual_basis': rule['basis'], 'methodology_order': rule['order'], 'methodology_url': rule['url']})
    if len({r['year'] for r in results}) != len(results):
        raise ValueError('Ambiguous annual equivalents')
    return results


def convert_live(items, meta, roles, selected, source, aliases, fetched_at):
    """Strict adapter extension for explicit quarterly personnel records.

    Shared Family/Youth parsing remains unchanged. Quarter-end month labels
    are interpreted only by the reviewed source-specific normalization above.
    """
    from emiss_adapter.errors import EmissConnectorError
    from emiss_adapter.metadata import norm
    from emiss_adapter.normalize import decode_period, values_for_field
    out = []
    for item in items:
        if item.value_status == 'invalid' or item.value is not None and not math.isfinite(item.value):
            raise EmissConnectorError('В SDMX есть нечисловое или бесконечное значение.', category='invalid_numeric')
        territory = values_for_field(item, roles.get('territory'), meta, selected) or 'Российская Федерация'
        year = values_for_field(item, roles.get('year'), meta, selected)
        if year is None:
            match = re.search(r'(?:19|20|21)\d{2}', item.period or '')
            year = match.group(0) if match else None
        if year is None:
            raise EmissConnectorError('Не определён год наблюдения.', category='ambiguous_period')
        year = int(year)
        label = values_for_field(item, roles.get('month'), meta, selected)
        quarter = re.fullmatch(r'([1-4]|iv|iii|ii|i)\s*(?:квартал|кв\.?)', norm(label or ''))
        iso_quarter = re.fullmatch(r'\d{4}-?Q([1-4])', item.period or '', re.I) if not label else None
        if quarter or iso_quarter:
            if source['indicator_id'] != '63238':
                raise EmissConnectorError('Квартальный период не предусмотрен проверенным контрактом.', category='period_schema_changed')
            number = (quarter or iso_quarter).group(1)
            q = int(number) if number.isdigit() else {'i': 1, 'ii': 2, 'iii': 3, 'iv': 4}[number]
            month = 3 * q
            typ, start, end = 'квартал', f'{year}-{month - 2:02d}-01', f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]}'
            label = f'{q} квартал'
        else:
            typ, start, end, label = decode_period(year, label, item.period, annual_only='month' not in roles)
        if typ not in source['expected_period_types']:
            raise EmissConnectorError('Новый тип периода требует проверки: ' + typ, category='period_schema_changed')
        dimensions = {}
        for field in meta['filters']:
            fid = str(field['field_id'])
            if fid == '0' or fid in roles.values():
                continue
            value = values_for_field(item, fid, meta, selected)
            if value is None:
                raise EmissConnectorError('Потеряно дополнительное измерение: ' + field['title'], category='ambiguous_dimension')
            dimensions[field['title']] = value
            if any(s in norm(field['title']) for s in ['единиц', 'ед. измер']):
                accepted = {norm(source['unit'])}
                if norm(source['unit']) == 'процент':
                    accepted |= {'процентов', '%', 'проценты'}
                if norm(value) not in accepted:
                    raise EmissConnectorError('Изменилась единица измерения.', category='unit_mismatch')
        code = aliases.get(territory_key(territory))
        if code is None and territory_key(territory) != territory_key('Российская Федерация'):
            raise EmissConnectorError('Неизвестная территория: ' + territory, category='territory_requires_mapping')
        out.append({'territory': territory, 'r': code, 'type': typ, 'year': year, 'start': start, 'end': end,
                    'label': label, 'value': item.value, 'raw': item.raw_value, 'dimensions': dimensions, 'fetched_at': fetched_at})
    if not out:
        raise EmissConnectorError('Нет нормализованных наблюдений.', category='empty_export')
    return out


def build_context(root=ROOT):
    """Reproduce the fixed pre-project 2024 context from retained source rows."""
    root = Path(root)
    provenance_path = root / DATA / 'context-source.json'
    if not provenance_path.exists():
        return None
    provenance = load(provenance_path)
    for entry in provenance['files']:
        file = root / 'public' / entry['path']
        if not file.resolve().is_relative_to((root / 'public').resolve()) or sha256(file) != entry['sha256']:
            raise ValueError('Context source checksum mismatch: ' + entry['path'])
    base = root / DOWNLOADS / 'context'
    with (base / 'regional_unemployment_2024.csv').open(encoding='utf-8-sig', newline='') as f:
        source_rows = list(csv.DictReader(f))
    with (base / 'region_join.csv').open(encoding='utf-8-sig', newline='') as f:
        join_rows = list(csv.DictReader(f))
    excerpt = (base / 'regional_source_excerpt.txt').read_text(encoding='utf-8')
    extracted = {}
    for line in excerpt.splitlines():
        match = re.fullmatch(r'(.+?)\s+—\s+(\d+(?:,\d+)?)\s*/\s*(\d+(?:,\d+)?)\s*', line)
        if match:
            extracted[match.group(1)] = (float(match.group(2).replace(',', '.')), float(match.group(3).replace(',', '.')))
    if len(extracted) != 86 or len(source_rows) != 86 or len(join_rows) != 85:
        raise ValueError('Context source coverage differs from the retained table')
    for row in source_rows:
        if extracted.get(row['source_name']) != (float(row['unemployment_2015']), float(row['unemployment_2024'])):
            raise ValueError('Context CSV differs from preserved source excerpt: ' + row['source_name'])
    source = {row['source_name']: float(row['unemployment_2024']) for row in source_rows}
    catalog = {str(row['id']): row for row in load(root / 'public/data/catalog.json')['regions']}
    regions = []
    for row in join_rows:
        code = str(row['region_code']).zfill(2)
        if code not in catalog or row['source_name'] not in source or source[row['source_name']] != float(row['value_2024']):
            raise ValueError('Unverified context geography join')
        item = catalog[code]
        regions.append({'code': code, 'map_id': code, 'name': row['source_name'], 'catalog_name': item['name'],
                        'fd': item['federal_district'], 'federal_district': item['federal_district'],
                        'value': source[row['source_name']], 'analytical_value': source[row['source_name']],
                        'unit': 'процент', 'period': '2024', 'year': 2024, 'geo_level': 'regional', 'role': 'pre_project_context'})
    if len({row['code'] for row in regions}) != 85:
        raise ValueError('Duplicate context region')
    values = [row['value'] for row in regions]
    national = source['Российская Федерация']
    bounds = [0, 2, 3, 5, 10, None]
    labels = ['Менее 2%', '2 – менее 3%', '3 – менее 5%', '5 – менее 10%', '10% и более']
    counts = [sum(value >= lo and (hi is None or value < hi) for value in values) for lo, hi in zip(bounds, bounds[1:])]
    if counts != [22, 42, 10, 9, 2] or national != 2.5:
        raise ValueError('Context distribution differs from source validation')
    summary = {'n': len(values), 'minimum': min(values), 'min': min(values), 'maximum': max(values), 'max': max(values),
               'q1': quantile(values, .25), 'median': quantile(values, .5), 'q3': quantile(values, .75),
               'unweighted_mean': sum(values) / len(values), 'national_value': national,
               'below_national': sum(v < national for v in values), 'equal_national': sum(v == national for v in values),
               'above_national': sum(v > national for v in values), 'weighting': 'unweighted_territories', 'quartile_method': 'Hyndman_Fan_type_7'}
    packet = {'schema_version': 1, 'id': 'unemployment_2024', 'title': 'Уровень безработицы в 2024 году', 'project_id': 'personnel',
              'role': 'pre_project_context', 'year': 2024, 'period': '2024', 'unit': 'процент', 'national_value': national,
              'national_value_origin': 'published_national_not_regional_average', 'source_url': provenance['source_url'],
              'source_page': 61, 'source_title': 'Росстат. Цели устойчивого развития в Российской Федерации. 2025. С. 61.',
              'source_hash': sha256(base / 'regional_source_excerpt.txt'), 'source_hash_kind': 'preserved_table_excerpt_not_pdf',
              'source_retrieval_note': provenance['source_retrieval_note'], 'source_provenance': provenance,
              'regions': regions, 'summary': summary, 'class_breaks': bounds, 'class_counts': counts,
              'classes': [{'label': label, 'lower': lo, 'upper': hi, 'count': count} for label, lo, hi, count in zip(labels, bounds, bounds[1:], counts)],
              'missing_codes': sorted(set(catalog) - {r['code'] for r in regions}),
              'interpretation': 'Среднегодовые значения для населения 15 лет и старше характеризуют исходные условия рынка труда до начала национального проекта. Они не являются проектными результатами и не измеряют незакрытые вакансии.',
              'geography_note': 'Архангельская и Тюменская области показаны без автономных округов; округа имеют самостоятельные наблюдения. Состав территорий воспроизводит сохранённую таблицу источника.',
              'downloads': {'table': 'downloads/projects/personnel/statistical/context_unemployment_2024.csv', 'source_excerpt': 'downloads/projects/personnel/statistical/context/regional_source_excerpt.txt'}}
    atomic(root / DATA / 'context.json', packet)
    csv_write(root / DOWNLOADS / 'context_unemployment_2024.csv', regions)
    csv_write(root / DOWNLOADS / 'context_summary.csv', [summary])
    return packet


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
