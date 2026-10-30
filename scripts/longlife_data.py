"""Strict statistical contracts for the Long and Active Life project.

The original source periods, numbers and geographical labels are retained.
Source-specific domains distinguish bounded shares, indices and growth rates.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import re
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'long_active_life'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT / 'statistical'
STATISTICAL_AS_OF = '2026-10-15'
RELEASE = 'NationalProjects_Analytics_1.2.0'
ANNUAL_EQUIVALENCE = {}  # No unverified substitution of December for an annual fact.

SHORT_TITLES = {
    '63006': 'Индекс временной нетрудоспособности к 2023 году',
    '62926': 'Использование передвижных подразделений',
    '63039': 'Проактивное наблюдение с передачей данных',
    '62927': 'Доступность модернизированной первичной помощи',
    '62930': 'Полнота наблюдения при хронических заболеваниях',
    '62914': 'Удовлетворённость медицинской помощью',
    '62956': 'Больничная летальность при инфаркте миокарда',
    '62954': 'Больничная летальность при инсульте',
    '62953': 'Реперфузионная терапия при инфаркте',
    '62952': 'Тромбэкстракция при инфаркте мозга',
    '62951': 'Лекарства для пациентов высокого сердечного риска',
    '62950': 'Изменение числа лиц без острых сердечных событий',
    '62948': 'Первая стадия опухолей визуальных локализаций',
    '62947': 'Одногодичная летальность при новообразованиях',
    '62946': 'Полнота онкологического наблюдения',
    '62945': 'Доля наблюдаемых с диагнозом давностью 5 лет и более',
    '62959': 'Непрерывный мониторинг глюкозы у правомочных групп',
    '62958': 'Обучение в школах диабета',
    '62957': 'Полнота диспансерного наблюдения при диабете',
    '62941': 'Полнота регистра гепатита C',
    '62939': 'Завершение лечения гепатита C амбулаторно',
    '62942': 'Скрининг гепатита C в возрасте 25 лет и старше',
    '62938': 'Завершение лечения гепатита C в дневном стационаре',
    '62940': 'Вирусологический ответ после лечения гепатита C',
    '63034': 'Суточные койки приёмных отделений',
    '62949': 'Информация о реабилитации на Госуслугах',
    '62955': 'Изменение числа получивших медицинскую реабилитацию',
    '63041': 'Использование личного кабинета «Моё здоровье»',
    '63040': 'Доступность цифрового проактивного мониторинга',
    '63151': 'Пациенты с БСК под наблюдением: прокси-показатель',
    '62983': 'Госпитализация после экспертной телемедицины',
    '62982': 'Выездные консультации сотрудников НМИЦ',
    '62989': 'Высокотехнологичная помощь в модернизированных центрах',
    '62965': 'Профилактическое консультирование при факторах риска',
    '62964': 'Индивидуальные программы здорового образа жизни',
    '62963': 'Рекомендации по питанию в центрах здоровья',
    '63005': 'Алкоголь на душу населения: скользящие 12 месяцев',
    '63348': 'Курение табака среди взрослых',
    '62943': 'Отсутствие четырёх факторов риска у обследованных',
    '62970': 'Средний медицинский персонал на 10 тыс. населения',
    '62972': 'Индекс остаточного дефицита врачей',
    '62971': 'Врачи на 10 тыс. населения',
}

LOWER = {'63006', '62956', '62954', '62947', '63005', '63348', '62972'}
NOTES = {
    '63006': 'Отношение накопленных дней нетрудоспособности на 100 работающих к одинаковому периоду 2023 года. 85,1 означает уровень на 14,9% ниже базы, а не сокращение на 85,1%. Значения выше 100 допустимы.',
    '62926': 'Знаменатель — расчётная пропускная способность передвижного подразделения, а не численность населения. Значения выше 100 допустимы и не означают полный охват населения.',
    '63039': 'Доля пациентов с передачей данных от оборудования имеет собственную совокупность. Она не складывается с доступностью цифровых сервисов или использованием личного кабинета.',
    '62927': 'Ряд характеризует доступность модернизированных подразделений в опубликованном периоде. Последнее значение не переносится на последующие месяцы или годы.',
    '62930': 'Числитель накапливается с начала года; знаменатель — состоящие под наблюдением на конец периода. Снижение доли не устанавливает причину незавершения наблюдения.',
    '62914': 'Доля положительных ответов среди участников опроса. Состав респондентов и фактическая неопределённость волны необходимы для более широких выводов.',
    '62956': 'Доля умерших среди взрослых стационарных пациентов с инфарктом; это не смертность населения. Необходим учёт тяжести, возраста и переводов.',
    '62954': 'Доля умерших среди взрослых стационарных пациентов с инсультом; это не смертность населения. Изменение состава госпитализированных требует отдельной проверки.',
    '62953': 'Знаменатель ограничен пациентами, госпитализированными в первые сутки инфаркта. Поздняя доставка остаётся за его пределами.',
    '62952': 'Знаменатель охватывает учтённый стационарный контингент с инфарктом мозга, а не только пациентов с показаниями к вмешательству. Доля не задаёт клиническую норму назначения.',
    '62951': 'Охват относится к правомочному контингенту мероприятия. Выдача препаратов не доказывает непрерывность последующего лечения.',
    '62950': 'Опубликованы значения изменения относительно базы 2023 года, включая отрицательные. Краткое описание формулы говорит об отношении и не раскрывает полностью преобразование к приросту: сохраняются исходные числа и оговорка, без обрезки на 0 или 100.',
    '62948': 'Первая стадия среди визуальных локализаций, не среди всех опухолей. Раннее выявление само по себе не устанавливает прирост продолжительности жизни.',
    '62947': 'Умершие в течение года среди впервые взятых под наблюдение в предыдущем периоде. Сопоставимость состава заболеваний и прослеживания требует проверки.',
    '62946': 'Доля получивших полный набор обследований среди онкологических пациентов, завершивших лечение; не самостоятельная оценка причинного эффекта.',
    '62945': 'Состав текущего диспансерного контингента, не пятилетняя когортная выживаемость. После последнего опубликованного числа пропуски сохраняются, срок жизни вновь выявленного пациента из доли не выводится.',
    '62959': 'Методика ЕМИСС включает нуждающихся детей с диабетом 1 типа и беременных женщин; паспортная формула требует редакционного согласования. Годовой и декабрьский факты самостоятельны; охват всех взрослых не выводится.',
    '62958': 'Доля обученных в школе среди пациентов с диабетом 1 и 2 типов; измеряет участие, а не последующее состояние здоровья.',
    '62957': 'Годовая и оперативная отчётность имеют разные регламенты и источники. Числитель включает другие организации помимо оснащённых проектом; отдельный эффект модернизации не измерен.',
    '62941': 'Полнота учёта зарегистрированных пациентов в федеральном регистре; не выявляемость всех инфицированных в населении.',
    '62939': 'Завершение курса в амбулаторных условиях относительно зарегистрированного контингента. Нельзя складывать с дневным стационаром без проверки пересечений пациентов.',
    '62942': 'Знаменатель — население 25 лет и старше. Показатель не совпадает с охватом только групп повышенного риска.',
    '62938': 'Завершение курса в дневном стационаре относительно зарегистрированного контингента. Вложенность и взаимная исключительность когорт не установлены.',
    '62940': 'Устойчивый вирусологический ответ среди завершивших лечение. Его нельзя распространить на невыявленных, ожидающих лечения или прервавших курс.',
    '62955': 'Показатель увеличения относительно базы, не ограниченная доля пациентов. Отрицательные и значения выше 100 сохранены. Краткая формула отношения не раскрывает полностью масштаб прироста; нужны компоненты и полная методика.',
    '63151': 'Абсолютное число наблюдаемых пациентов — прокси-показатель. Допустимо отдельное сопоставление с собственной абсолютной паспортной целью; число не подменяет долю доступности цифрового мониторинга и не сопоставляется с процентной целью.',
    '63005': 'Каждая месячная оценка охватывает последние 12 календарных месяцев. Соседние окна пересекаются; значения не суммируются и не считаются независимым месячным потреблением.',
    '63348': 'Методика использует обследованных взрослых и поправочный коэффициент. Оценка отличается от простой доли всего взрослого населения; контингент обследования необходимо учитывать.',
    '62943': 'Доля обследованных взрослых без четырёх факторов риска. Это не автоматически распространённость здорового образа жизни среди всех взрослых. Нормативный ориентир 13,6 и паспортный 14,6 имеют разные документальные основания.',
    '62970': 'Физические лица в организациях программы государственных гарантий на 10 тыс. населения; не полная занятость и не обеспеченность каждой специальностью. Для авторского сравнения исключены областные строки 29 и 72 с неоднозначным охватом АО.',
    '62971': 'Физические лица в организациях программы государственных гарантий на 10 тыс. населения; не ставки и не длительность ожидания помощи. Областные строки 29 и 72 исключены из авторского сравнения из-за охвата АО.',
    '62972': 'Отношение текущего неудовлетворённого кадрового спроса к максимальному положительному базовому разрыву 2023–2030 годов. Меньше — меньший остаточный дефицит; 33,10 не означает сокращение на 33,10%. База и потребность могут уточняться.',
}


def source_rules(sid, title, unit):
    sid = str(sid)
    domain, lo, hi = 'proportion_0_100', 0, 100
    if sid in {'63006', '62926'}:
        domain, hi = 'nonnegative_ratio', None
    elif sid in {'62950', '62955'}:
        domain, lo, hi = 'growth_rate', -100, None
    elif sid in {'62970', '62971'}:
        domain, hi = 'rate_per_10000', None
    elif sid == '63151':
        domain, hi = 'count', None
    elif sid == '63005':
        domain, hi = 'nonnegative_volume', None
    elif sid == '62972':
        domain = 'bounded_index'
    semantics = 'cumulative_ytd' if sid in {'63006', '62930'} else 'rolling_12_months' if sid == '63005' else 'stock_at_period_end' if sid in {'62970', '62971', '63151', '62972'} else 'operational_monitoring'
    note = NOTES.get(sid, 'Показатель относится к определённой наблюдаемой совокупности. Агрегированная доля не устанавливает причинный эффект проекта; компоненты и охват необходимы для интерпретации.')
    period_note = {'cumulative_ytd': 'Накопление с начала календарного года; сравнивайте одинаковые месяцы.', 'rolling_12_months': 'Окно последних 12 календарных месяцев; соседние окна пересекаются.', 'stock_at_period_end': 'Состояние контингента или ресурса на конец периода.', 'operational_monitoring': 'Оперативный административный или опросный мониторинг; независимость соседних месяцев не предполагается.'}[semantics]
    return {'short_title': SHORT_TITLES.get(sid, title), 'direction': 'lower' if sid in LOWER else 'higher',
            'domain': domain, 'lower_bound': lo, 'upper_bound': hi, 'note': note,
            'display_unit': 'человек на 10 тыс. населения' if sid in {'62970', '62971'} else unit,
            'period_semantics': semantics, 'period_note': period_note,
            'cumulative': 'year' if semantics == 'cumulative_ytd' else semantics,
            'annual_reset': semantics == 'cumulative_ytd', 'annual_equivalence': None,
            'target_comparison_allowed': True, 'proxy_only': sid == '63151',
            'target_comparison_note': 'Прокси в абсолютных числах не подменяет процентную цель.' if sid == '63151' else None}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def encode(value, compact=False):
    options = {'separators': (',', ':')} if compact else {'indent': 2}
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, **options) + '\n').encode('utf-8')


def atomic(path, value, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(encode(value, compact))
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
    root = Path(root)
    catalog = load(root / 'public/data/catalog.json')
    aliases = {territory_key(r['name']): str(r['id']) for r in catalog['regions']}
    additions = {
        'Город Москва столица Российской Федерации город федерального значения': '77',
        'Город Санкт-Петербург город федерального значения': '78',
        'Город федерального значения Севастополь': '92',
        'Республика Адыгея (Адыгея)': '01', 'Республика Татарстан (Татарстан)': '16',
        'Кемеровская область': '42', 'Архангельская область (кроме Ненецкого автономного округа)': '29',
        'Ненецкий автономный округ (Архангельская область)': '83',
        'Тюменская область (кроме Ханты-Мансийского автономного округа-Югры и Ямало-Ненецкого автономного округа)': '72',
        'Ханты-Мансийский автономный округ - Югра (Тюменская область)': '86',
        'Ямало-Ненецкий автономный округ (Тюменская область)': '89',
    }
    aliases.update({territory_key(k): v for k, v in additions.items()})
    by_number = {int(r['id']): str(r['id']) for r in catalog['regions'] if str(r['id']).isdigit()}
    return {k: by_number.get(int(v), v) if str(v).isdigit() else v for k, v in aliases.items()}


def observation_key(source_id, name, frequency, start, end, category):
    values = [source_id, territory_key(name), frequency, start, end, json.dumps(category, ensure_ascii=False, sort_keys=True)]
    return hashlib.sha256('|'.join(values).encode()).hexdigest()


def classify_flags(source, value):
    flags = []
    def add(code, message, exclude=False, severity='warning'):
        flags.append({'code': code, 'message': message, 'severity': severity, 'exclude_from_analysis': exclude})
    if value is None:
        add('missing', 'Числовое значение не опубликовано; не заменяется нулём или последним наблюдением.', True, 'info')
        return flags
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Non-finite or non-numeric observation')
    if source.get('lower_bound') is not None and value < source['lower_bound']:
        add('below_domain', 'Значение ниже предметной области определения; исходное число сохранено.', True)
    if source.get('upper_bound') is not None and value > source['upper_bound']:
        add('above_domain', 'Значение выше предметной области определения; исходное число сохранено.', True)
    if source['domain'] in {'growth_rate', 'nonnegative_ratio'} and (value < 0 or value > 100):
        add('unbounded_ratio_or_growth', 'Процент представляет отношение к базе или прирост; общий диапазон 0–100 к нему не применяется.', severity='info')
    if source['domain'] == 'growth_rate':
        add('growth_formula_requires_components', 'Краткое описание отношения не раскрывает полностью масштаб опубликованного прироста; число сохранено без преобразования, требуются полная формула и компоненты.', severity='info')
    if value == 0:
        add('zero_preserved_components_unavailable', 'Исходный ноль сохранён. Числитель, знаменатель и контингент необходимы для содержательного вывода.', severity='info')
    return flags


def normalize_record(row, source, aliases, regions=None):
    if str(row['source_id']) != str(source['indicator_id']):
        raise ValueError('Source identity mismatch')
    if row['unit'].casefold().strip() != source['unit'].casefold().strip():
        raise ValueError('Unit mismatch')
    frequency = row['period_kind']
    if frequency not in ('annual', 'monthly', 'cumulative_ytd'):
        raise ValueError('Unsupported explicitly identified frequency: ' + str(frequency))
    start, end = row['period_start'], row['period_end']
    if not start or not end:
        raise ValueError('Observation lacks explicit dates')
    date.fromisoformat(start)
    date.fromisoformat(end)
    year, month = int(row['year']), int(end[5:7])
    if start > end or int(start[:4]) != year or int(end[:4]) != year:
        raise ValueError('Observation year and dates differ')
    expected_start = f'{year}-01-01' if frequency in {'annual', 'cumulative_ytd'} else f'{year}-{month:02d}-01'
    expected_end = f'{year}-12-31' if frequency == 'annual' else f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]}'
    if start != expected_start or end != expected_end:
        raise ValueError('Observation has inconsistent explicit period dates')
    name = row['territory_name']
    code = aliases.get(territory_key(name))
    geography = 'national' if territory_key(name) == territory_key('Российская Федерация') else 'regional' if code else 'other'
    if geography == 'other' and not name.casefold().endswith('федеральный округ'):
        raise ValueError('Unmapped source territory: ' + name)
    dimensions = json.loads(row.get('dimensions_json') or '{}')
    ignored = {'Показатель', 'Год', 'Период', 'Единица измерения', 'ОКАТО', 'ОКТМО', 'ОКСМ'}
    geography_dimensions = {k: v for k, v in dimensions.items() if re.match(r'^(?:ОКАТО|ОКТМО|ОКСМ)(?:\s|$)', k, re.I)}
    category = {k: v for k, v in dimensions.items() if k not in ignored and k not in geography_dimensions}
    value = row.get('value_numeric')
    flags = classify_flags(source, value)
    excluded = any(f['exclude_from_analysis'] for f in flags)
    period = str(year) if frequency == 'annual' else end[:7]
    semantics = 'independent_annual' if frequency == 'annual' else source['period_semantics']
    window_start = start
    if frequency != 'annual' and semantics == 'cumulative_ytd':
        window_start = f'{year}-01-01'
    elif frequency != 'annual' and semantics == 'rolling_12_months':
        previous = year * 12 + month - 12
        window_start = f'{previous // 12}-{previous % 12 + 1:02d}-01'
    region = (regions or {}).get(code, {})
    ambiguous = code in {'29', '72'} and 'кроме' not in name.casefold()
    return {'id': observation_key(str(source['indicator_id']), name, frequency, start, end, category),
            'source_id': str(source['indicator_id']), 'source_observation_key': row.get('observation_key'),
            'name': name, 'code': code, 'map_id': code, 'geo_level': geography,
            'fd': region.get('federal_district'), 'federal_district': region.get('federal_district'),
            'territory_code_source': row.get('territory_code'), 'territory_level_source': row.get('territory_level'),
            'period': period, 'period_start': start, 'period_end': end, 'year': year, 'frequency': frequency,
            'source_frequency': frequency, 'source_period_start': start, 'source_period_end': end,
            'source_geography_dimensions': geography_dimensions,
            'source_period_label': dimensions.get('Период'), 'period_semantics': semantics,
            'measurement_window_start': window_start, 'measurement_window_end': end,
            'value': value, 'raw': row.get('value_raw'), 'unit': source['unit'], 'display_unit': source['display_unit'],
            'category': category, 'quality_flags': flags, 'excluded': excluded,
            'analytical_value': None if excluded else value,
            'status': 'missing' if value is None else 'review_required' if excluded else 'valid',
            'geographic_comparison_eligible': not ambiguous,
            'geographic_exclusion_reason': 'unclear_autonomous_okrug_scope' if ambiguous else None,
            'author_comparison_eligible': code not in {'29', '72', '90', '93', '94', '95'} if code else None,
            'source_attributes': json.loads(row.get('attributes_json') or '{}')}


def normalize_payload(payload, aliases, regions=None):
    snapshot = payload.get('snapshot')
    source = payload['config']
    if snapshot and snapshot['origin_kind'] != 'live_emiss':
        raise ValueError('Only verified live_emiss snapshot inputs are accepted')
    rows = [normalize_record(row, source, aliases, regions) for row in payload['observations']]
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate observation identity after normalization')
    rows.sort(key=lambda row: (row['period_end'], row['frequency'], row['name'], row['id']))
    return {'schema_version': 1, 'project_id': PROJECT, 'source_id': source['indicator_id'],
            'unit': source['unit'], 'source_url': source['source_url'],
            'published_at': snapshot['acquired_at'] if snapshot else None,
            'snapshot_id': snapshot['snapshot_id'] if snapshot else None,
            'origin_kind': 'live_emiss' if snapshot else 'metadata_only', 'observations': rows}


def annual_equivalents(source_id, rows):
    return []


def series_flags(rows, source_id):
    return rows


def convert_live(items, meta, roles, selected, source, aliases, fetched_at):
    # The shared strict parser retains negative values; source-specific domain
    # decisions are made by normalize_record, not its generic display flag.
    from emiss_adapter.normalize import convert
    return convert(items, meta, roles, selected, source, aliases, fetched_at)


def csv_write(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as f:
            temporary = Path(f.name)
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in row.items() if k in fields})
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def quantile(values, probability):
    values = sorted(values)
    if not values:
        return None
    rank = (len(values) - 1) * probability
    lo, hi = math.floor(rank), math.ceil(rank)
    return values[lo] + (values[hi] - values[lo]) * (rank - lo)


def merge_observations(previous, incoming):
    lookup = {r['id']: dict(r) for r in previous}
    revisions, received, added = [], {}, 0
    for row in incoming:
        if row['id'] in received:
            if any(received[row['id']][key] != row[key] for key in ('value', 'unit', 'category')):
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
        lookup[row['id']] = {**row, 'source_observation_key': row.get('source_observation_key') or old.get('source_observation_key')}
    return sorted(lookup.values(), key=lambda row: (row['period_end'], row['frequency'], row['name'], row['id'])), added, revisions
