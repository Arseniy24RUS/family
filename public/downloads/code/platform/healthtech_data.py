#!/usr/bin/env python3
"""Explicit statistical contracts for New Health Preservation Technologies.

The source exports contain national cells only. Published zeroes, absent cells,
December records and independent annual observations remain distinguishable.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import math
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'health_technologies'
DATA = Path('public/data/projects') / PROJECT
DOWNLOADS = Path('public/downloads/projects') / PROJECT / 'statistics'
INPUTS = Path('inputs/healthtech_statistics')
REPORT_DATE = '2026-10-28'
MONTHS = {'январь':1,'февраль':2,'март':3,'апрель':4,'май':5,'июнь':6,
          'июль':7,'август':8,'сентябрь':9,'октябрь':10,'ноябрь':11,'декабрь':12}
MISSING = {'', '–', '—', '-', '...', '…', 'н/д', 'n/a', 'null'}


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(value if isinstance(value, bytes) else encode(value))
    temporary.replace(path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csv_write(path, rows, fields):
    target = io.StringIO(newline='')
    writer = csv.DictWriter(target, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    atomic(path, ('\ufeff' + target.getvalue()).encode('utf-8'))


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip()


def number(value):
    raw = '' if value is None else str(value)
    text = raw.strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    if text.casefold() in MISSING:
        return None
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('Unrecognised numeric source cell: ' + raw[:80]) from exc
    if not result.is_finite():
        raise ValueError('Nonfinite statistical value')
    if abs(result) > Decimal('9007199254740991'):
        raise ValueError('Source number exceeds safe browser numeric representation')
    return int(result) if result == result.to_integral_value() else float(result)


def period(year, raw_label):
    year = int(year)
    if not 2025 <= year <= 2100:
        raise ValueError('Unverified year in source')
    label = re.sub(r'^\d+\s+', '', clean(raw_label)).casefold()
    if label in {'значение показателя за год', 'год', 'за год'}:
        return {'period':str(year), 'year':year, 'frequency':'annual', 'period_start':f'{year}-01-01', 'period_end':f'{year}-12-31', 'month':None, 'quarter':None}
    if label in MONTHS:
        month = MONTHS[label]
        return {'period':f'{year}-{month:02d}', 'year':year, 'frequency':'monthly', 'period_start':f'{year}-{month:02d}-01',
                'period_end':f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}', 'month':month, 'quarter':None}
    quarters = {'i квартал':1, 'ii квартал':2, 'iii квартал':3, 'iv квартал':4}
    if label in quarters:
        quarter = quarters[label]
        month = quarter * 3
        return {'period':f'{year}-Q{quarter}', 'year':year, 'frequency':'quarterly', 'period_start':f'{year}-{month-2:02d}-01',
                'period_end':f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}', 'month':None, 'quarter':quarter}
    raise ValueError('Unrecognised source period: ' + raw_label)


RULES = {
 '62986':('Успешные исследования', 'ordinary_proportion', 'annual_with_monthly_publication_placeholders', 'Годовая доля исследований. Только отдельная строка «значение показателя за год» представляет самостоятельный годовой факт. Месячные нули сохранены как форма публикации и не подменяют годовой результат.'),
 '62987':('Прирост коммерциализации РИД', 'growth_percent', 'annual_with_monthly_publication_placeholders', 'Прирост относительно базы 2023 года. Отдельной годовой строки нет; декабрьская запись сохраняет месячный тип. Нули других месяцев не удостоверяют отсутствие коммерциализации.'),
 '63062':('Технологическая независимость', 'bounded_index', 'quarterly_index', 'Индекс оценок технологической готовности и критических компонентов. Квартальная запись не заменяет самостоятельный годовой итог и не является долей пациентов или изделий.'),
 '63059':('Прирост добавленной стоимости', 'growth_percent', 'methodology_break_unresolved', 'Квартальные значения 2025 года сохранены. Редакции методики различаются базовым годом, отраслевым составом и периодичностью. Сравнение с годовым планом и экстраполяция блокируются до согласования ряда и методики.'),
 '63130':('Допущенные разработки НП', 'count', 'cumulative_since_2025', 'Число учтённых допусков накоплено с 2025 года. Месячные значения не суммируются. Совокупность может пересекаться с прокси С2; оба счётчика нельзя складывать.'),
 '63132':('Объём коммерциализации РИД', 'nonnegative_currency', 'cumulative_calendar_year', 'Объём накоплен с января. Включает денежные поступления, имущественные оценки и операции с капиталом. Месячные точки не суммируются, разные календарные срезы не образуют межгодовое сравнение.'),
 '62985':('Медизделия на 1 млрд руб.', 'unit_conflict', 'annual_with_monthly_publication_placeholders', 'В исходной таблице единица обозначена как процент, хотя название описывает изделия на 1 млрд рублей исследований. Исходная единица и значение сохранены; сопоставление с планом требует уточнения единицы.'),
 '62928':('Учёт и мониторинг исследований', 'ordinary_proportion', 'annual_with_monthly_publication_placeholders', 'Годовая доля опубликована в месячной сетке. Декабрь остаётся декабрьской записью, нули других месяцев не означают отсутствие учёта исследований.'),
 '62984':('Лекарства на 5 млрд руб.', 'nonnegative_ratio', 'annual_with_monthly_publication_placeholders', 'Нормированный результат на каждые 5 млрд рублей прикладных исследований. Дробное число допустимо. Декабрьская запись не объявляется годовой.'),
 '63446':('Прокси С1: медицинские изделия', 'count', 'rolling_five_calendar_years', 'Окно включает текущий и четыре предшествующих года: для 2026 года – 2022–2026. Показатель не равен числу изделий только текущего года и не измеряет объём продаж.'),
 '63447':('Прокси С1: лекарственные препараты', 'count', 'rolling_five_calendar_years', 'Окно включает текущий и четыре предшествующих года: для 2026 года – 2022–2026. Показатель не равен числу лекарств только текущего года; переход календарного года меняет состав окна.'),
 '62929':('Доля допущенных разработок С2', 'ordinary_proportion', 'annual_with_monthly_publication_placeholders', 'Доля продуктов имеет другой знаменатель, чем доля успешных исследований НП. Годовая по методике, опубликована в декабрьской месячной ячейке.'),
 '62988':('Охват пациентов С2', 'ordinary_proportion', 'cumulative_calendar_year_ratio', 'Числитель и знаменатель накоплены с января. Знаменатель – специализированная помощь в федеральных организациях с клиниками. В исходной републикации отсутствовала строка июня 2026 года; пропуск не интерполируется.'),
 '63445':('Допущенные разработки С2', 'count', 'cumulative_since_2025', 'Учтённые допуски федерального проекта. Совокупность пересекается с национальным прокси и не складывается с ним без пообъектного реестра.'),
 '63223':('Внедрение технологий С3', 'ordinary_proportion', 'annual_contract_unverified', 'Числовая публикация не восстановлена. План не подставляется вместо факта.'),
 '63224':('Пациенты технологий С3', 'ordinary_proportion', 'annual_contract_unverified', 'Знаменатель ограничен организациями, внедрившими технологии. Числовая публикация не восстановлена.'),
 '63225':('Внедрение технологий С4', 'ordinary_proportion', 'annual_contract_unverified', 'Числовая публикация не восстановлена. Межорганизационный перенос требует отдельного учёта.'),
 '63226':('Доступ к технологиям С4', 'ordinary_proportion', 'annual_contract_unverified', 'Знаменатель – обратившиеся в организации-участники. Открытая числовая публикация не восстановлена.'),
 '63272':('Стратегические лекарства полного цикла', 'ordinary_proportion', 'annual_contract_unverified', 'Доля номенклатуры стратегического перечня с технологической возможностью полного цикла. Объёмы упаковок и мощности поставок не выводятся из этой доли.'),
 '63275':('Локальные радиофармпрепараты', 'ordinary_proportion', 'annual_contract_unverified', 'Доля потребления препаратов локального производства в натуральном выражении. Локализация готовой лекарственной формы не равна полному циклу. Числовая публикация не восстановлена.')
}


def source_rule(sid):
    short, domain, semantics, note = RULES[str(sid)]
    return {'short_title':short, 'domain':domain, 'period_semantics':semantics, 'period_note':note,
            'note':note, 'direction':'higher', 'target_comparison_allowed':sid not in {'63059','62985'},
            'proxy_only':sid in {'63130','63132','63445','63446','63447'},
            'cumulative':semantics.startswith('cumulative'), 'annual_reset':semantics.startswith('cumulative_calendar_year')}


def observation(sid, raw, config):
    sid = str(sid)
    if clean(raw['territory_label']) != '643 Российская Федерация':
        raise ValueError('Unreviewed geographic expansion: ' + raw['territory_label'])
    unit_label = clean(raw['unit_label'])
    expected = clean(config['unit'])
    if re.sub(r'^\d+\s+', '', unit_label) != expected:
        raise ValueError('Source unit does not match the verified workbook passport')
    p = period(raw['year'], raw['period_label'])
    val = number(raw['value_raw'])
    flags = []
    def add(code, message, excluded=False, severity='info'):
        flags.append({'code':code,'message':message,'severity':severity,'exclude_from_analysis':excluded})
    if val is None:
        add('source_missing', 'В исходной ячейке отсутствует число. Пропуск сохранён.')
    if config['period_semantics'] == 'annual_with_monthly_publication_placeholders' and p['frequency'] == 'monthly':
        if sid == '62986' or p['month'] != 12:
            add('monthly_cell_for_annual_indicator', 'Месячная ячейка годового показателя не подтверждает значение годового результата.', True, 'warning')
        else:
            add('december_not_annual', 'Декабрьская запись сохранена с месячным типом. Самостоятельный годовой факт отсутствует.', False, 'warning')
    if sid == '62985':
        add('unit_conflict', 'Исходная единица «процент» противоречит смыслу числа изделий на 1 млрд руб.; преобразование не выполнялось.', True, 'warning')
    if sid == '63059':
        add('methodology_break_unresolved', 'База, отраслевой охват и периодичность методик не согласованы. Число доступно для просмотра, производные оценки заблокированы.', True, 'warning')
    if sid in {'63130','63132'} and p['period_end'] < '2025-05-01':
        add('before_source_effective_start', 'Ячейка предшествует указанному в паспорте началу действия показателя 1 мая 2025 года.', True, 'warning')
    if val is not None:
        domain = config['domain']
        if domain in {'ordinary_proportion','bounded_index'} and not 0 <= val <= 100:
            add('outside_domain', 'Значение вне допустимых пределов 0–100; исходное число сохранено.', True, 'warning')
        if domain in {'count','nonnegative_ratio','nonnegative_currency'} and val < 0:
            add('outside_domain', 'Отрицательное значение не соответствует определению показателя.', True, 'warning')
        if domain == 'count' and not float(val).is_integer():
            add('noninteger_count', 'Неожиданное дробное число для счётчика объектов.', True, 'warning')
        if domain == 'growth_percent' and val < -100:
            add('outside_domain', 'Прирост ниже −100% требует проверки определения.', True, 'warning')
        if val == 0:
            add('zero_preserved', 'Исходный ноль сохранён и отличается от пропуска.')
    excluded = any(flag['exclude_from_analysis'] for flag in flags)
    key = '|'.join([sid, raw['territory_label'], raw['unit_label'], str(raw['year']), raw['period_label']])
    return {'id':sid + ':' + hashlib.sha256(key.encode()).hexdigest()[:20], 'source_id':sid,
            'source_observation_key':key, 'name':'Российская Федерация', 'code':'643', 'geo_level':'national',
            'map_id':None, 'fd':None, **p, 'value':val, 'analytical_value':val if not excluded else None,
            'raw_value':str(raw['value_raw']), 'value_raw':str(raw['value_raw']), 'excluded':excluded,
            'status':'missing' if val is None else 'excluded' if excluded else 'ok', 'unit':expected, 'category':{},
            'original_period_label':raw['period_label'], 'original_unit_label':raw['unit_label'],
            'original_territory_label':raw['territory_label'], 'source_locator':raw.get('source_locator'),
            'quality_flags':flags, 'geographic_comparison_eligible':False,
            'annual_comparison_eligible':p['frequency'] == 'annual' and val is not None and not excluded,
            'origin_kind':raw.get('origin_kind', 'secondary_emiss_republication')}


def canonical_key(row):
    return (row['source_id'], row['code'], row['period'], row['frequency'], row['unit'], json.dumps(row.get('category', {}), sort_keys=True, ensure_ascii=False))


def merge_observations(old, incoming):
    result = {canonical_key(row):row for row in old}
    if len(result) != len(old):
        raise ValueError('Duplicate existing source observation')
    seen, added, revisions = set(), 0, []
    for row in incoming:
        key = canonical_key(row)
        if key in seen:
            raise ValueError('Duplicate incoming source observation')
        seen.add(key)
        previous = result.get(key)
        if previous is None:
            added += 1
        elif previous['value'] != row['value']:
            revisions.append({'period':row['period'], 'frequency':row['frequency'], 'previous_value':previous['value'],
                              'value':row['value'], 'previous_observation_id':previous['id'], 'observation_id':row['id']})
        result[key] = row
    return sorted(result.values(), key=lambda r:(r['period_end'],r['frequency'],r['id'])), added, revisions


CSV_FIELDS = ['id','source_id','name','code','geo_level','period','frequency','period_start','period_end','year','month','quarter',
              'unit','value','analytical_value','raw_value','excluded','status','original_period_label','original_unit_label',
              'source_observation_key','source_locator','origin_kind','quality_flags']
