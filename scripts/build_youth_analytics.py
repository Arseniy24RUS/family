#!/usr/bin/env python3
"""Recompute source-backed Youth summaries and CSV downloads, offline.

All numerical calculations use published series/*.json. Cumulative monthly
observations never become independent annual facts or a causal-effect estimate.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

from download_manifest import download_records
from youth_data import ROOT, DATA, DOWNLOADS, load, atomic, sha256, csv_write, quantile


def summary(rows):
    values = [r['analytical_value'] for r in rows if r.get('analytical_value') is not None]
    return {'n': len(values), 'minimum': min(values) if values else None,
            'q1': quantile(values, .25), 'median': quantile(values, .5), 'q3': quantile(values, .75),
            'maximum': max(values) if values else None,
            'at_100': sum(v == 100 for v in values), 'below_80': sum(v < 80 for v in values),
            'weighting': 'unweighted_territories', 'quartile_method': 'Hyndman_Fan_type_7'}


def latest(rows):
    numeric = [r for r in rows if r['value'] is not None]
    return max(numeric, key=lambda r: (r['period_end'], r['frequency'] == 'annual')) if numeric else None


def current_raw_download(root, source_id, status):
    """Expose only the exact successful response recorded in provenance."""
    raw_file = status.get('raw_file')
    if not raw_file:
        return None
    expected = f'downloads/projects/youth_children/emiss_current/{source_id}.zip'
    if raw_file != expected:
        raise ValueError(f'Unexpected current source response path: {source_id}')
    provenance = load(Path(root) / DATA / 'provenance' / (source_id + '.json'))
    path = Path(root) / 'public' / raw_file
    if provenance.get('current_raw') != raw_file or not path.is_file():
        raise ValueError(f'Current source response lacks matching provenance: {source_id}')
    if not path.resolve().is_relative_to((Path(root) / 'public').resolve()):
        raise ValueError(f'Current source response lies outside public files: {source_id}')
    if sha256(path) != provenance.get('current_raw_sha256'):
        raise ValueError(f'Current source response checksum mismatch: {source_id}')
    return raw_file


def make_source(config, packet, status, root=ROOT):
    rows = packet['observations']
    national = [r for r in rows if r['geo_level'] == 'national']
    regional = [r for r in rows if r['geo_level'] == 'regional']
    regional_periods = sorted({r['period_end'] for r in regional if r['analytical_value'] is not None})
    regional_end = regional_periods[-1] if regional_periods else None
    region_latest = [r for r in regional if r['period_end'] == regional_end]
    method_flags = []
    if config['annual_reset']:
        method_flags.append({'code': 'annual_reset', 'message': 'Сравнивайте одинаковые месяцы разных лет; январский сброс накопления не является падением общественного результата.', 'severity': 'info', 'exclude_from_analysis': False})
    downloads = {'observations': f'data/projects/youth_children/series/{config["indicator_id"]}.json',
                 'provenance': f'data/projects/youth_children/provenance/{config["indicator_id"]}.json',
                 'source_input': f'downloads/projects/youth_children/emiss_inputs/{config["indicator_id"]}.zip'}
    current_raw = current_raw_download(root, config['indicator_id'], status)
    if current_raw:
        downloads['current_raw'] = current_raw
    return {
        'id': config['indicator_id'], 'title': config['title'], 'short_title': config['short_title'],
        'indicator_codes': config['indicator_codes'], 'indicator_level': config['indicator_level'],
        'federal_project_name': config['federal_project_name'], 'unit': config['unit'],
        'source_url': config['source_url'], 'cumulative': config['cumulative'],
        'annual_reset': config['annual_reset'], 'note': config['note'],
        'methodology': config['methodology'], 'periodicity': config['periodicity'],
        'available': any(r['value'] is not None for r in rows),
        'published_at': packet['published_at'], 'last_success': status.get('last_success') or packet['published_at'],
        'snapshot_id': packet.get('snapshot_id'),
        'last_checked_at': status.get('checked_at'), 'refresh_state': status.get('state'),
        'observation_count': len(rows), 'numeric_count': sum(r['value'] is not None for r in rows),
        'missing_count': sum(r['value'] is None for r in rows),
        'excluded_numeric_count': sum(r['value'] is not None and r['excluded'] for r in rows),
        'latest_national': latest(national), 'national': national,
        'annual': [r for r in national if r['frequency'] == 'annual'],
        'regional_latest': region_latest, 'regional_history': regional,
        'other_territories': [r for r in rows if r['geo_level'] == 'other'],
        'regional_periods': regional_periods, 'regional_period_end': regional_end,
        'quality_flags': method_flags,
        'downloads': downloads,
    }


def target_rows(root):
    # The documentary module supplies the exact chosen edition and all years.
    path = root / DATA / 'targets.json'
    if not path.exists():
        return []
    data = load(path)
    return data if isinstance(data, list) else data.get('items', data.get('targets', []))


def validate_target_unit(source, target):
    if str(target.get('unit', '')).strip().casefold() != source['unit'].strip().casefold():
        raise ValueError(f'Target unit differs from confirmed source unit: {source["id"]}')


def difference_unit(source):
    if source.get('cumulative') == 'index':
        return 'пункты индекса'
    return 'п.п.' if source['unit'].casefold() == 'процент' else source['unit']


def forecast_eligibility(source):
    count = len({r['year'] for r in source['annual'] if not r['excluded'] and not r['category']})
    insufficient = count < 4
    return {'source_id': source['id'], 'title': source['short_title'],
            'annual_observations': count, 'eligible': False,
            'status': 'insufficient_independent_annual_history' if insufficient else 'model_not_validated',
            'reason': 'Независимого годового ряда недостаточно для проверяемого прогноза. Накопительные месячные записи не заменяют независимые годы. Допустим условный расчёт требуемой траектории к цели.' if insufficient else 'Годовые наблюдения накоплены; прогнозная модель ещё не выбрана и не проверена на ретроспективных данных. Автоматическая публикация прогноза требует отдельной валидации.'}


def build(root=ROOT):
    root = Path(root)
    config = load(root / 'scripts/youth_emiss_sources.json')
    registry_packet = load(root / DATA / 'indicators.json')
    registry = registry_packet['items']
    refresh = load(root / DATA / 'refresh-status.json')
    status = {str(r['source_id']): r for r in refresh.get('sources', [])}
    sources = []
    all_rows = []
    for contract in config['sources']:
        packet = load(root / DATA / 'series' / (contract['indicator_id'] + '.json'))
        source = make_source(contract, packet, status.get(contract['indicator_id'], {}), root)
        sources.append(source)
        all_rows.extend(packet['observations'])
    by_id = {s['id']: s for s in sources}
    published_dates = [s['published_at'] for s in sources if s['published_at']]
    published_at = max(published_dates) if published_dates else None
    rows_by_source = collections.defaultdict(list)
    for row in all_rows:
        rows_by_source[row['source_id']].append(row)
    current_registry = []
    region_count = len(load(root / 'public/data/catalog.json')['regions'])
    for indicator in registry:
        linked = [by_id[sid] for sid in indicator['source_ids']]
        rows = [row for source in linked for row in rows_by_source[source['id']]]
        numeric = [row for row in rows if row['value'] is not None]
        regions_seen = {row['code'] for row in numeric if row['geo_level'] == 'regional'}
        latest_points = []
        for source in linked:
            groups = collections.defaultdict(list)
            for point in source['national']:
                if point['value'] is not None:
                    groups[(point['frequency'], json.dumps(point['category'], sort_keys=True))].append(point)
            for points in groups.values():
                point = latest(points)
                latest_points.append({**point, 'source_title': source['title'], 'source_url': source['source_url'],
                                      'territory_name': point['name'], 'acquired_at': source['published_at'],
                                      'snapshot_id': source['snapshot_id'], 'origin_kind': 'live_emiss',
                                      'series_id': 'youth_' + hashlib.sha256((source['id'] + '|' + point['frequency'] + '|' + json.dumps(point['category'], sort_keys=True)).encode()).hexdigest()[:20],
                                      'observation_key': point['source_observation_key'] or point['id'],
                                      'analysis_status': 'excluded' if point['excluded'] else 'usable'})
        current_registry.append({**indicator, 'n_linked_sources': len(linked),
                                 'n_loaded_sources': sum(bool(source['observation_count']) for source in linked),
                                 'n_cells': len(rows), 'n_numeric': len(numeric),
                                 'n_usable': sum(not row['excluded'] for row in numeric),
                                 'n_regions': len(regions_seen), 'region_coverage_pct': 100 * len(regions_seen) / region_count,
                                 'n_national': sum(row['geo_level'] == 'national' for row in numeric),
                                 'n_domain_violations': sum(any(f['code'] in ('negative', 'outside_0_100') for f in row['quality_flags']) for row in numeric),
                                 'first_end': min((row['period_end'] for row in numeric), default=''),
                                 'last_end': max((row['period_end'] for row in numeric), default=''),
                                 'status': 'numeric_data' if numeric else 'linked_no_numeric' if linked else 'no_table_link',
                                 'latest_national': latest_points})
    registry = current_registry
    statistics = {'schema_version': 1, 'project_id': 'youth_children', 'published_at': published_at,
                  'statistical_as_of': published_at[:10] if published_at else None,
                  'last_checked_at': refresh.get('checked_at'),
                  'geography_note': 'Состав территориальных позиций воспроизводит перечень статистического источника. Картографическое представление не выражает позиции по международно-правовому статусу территорий.',
                  'sources': sources, 'unmapped_indicators': config['unmapped_indicators']}

    coverage = {'indicators_total': len(registry), 'national_indicators': sum(r['indicator_level'] == 'national_project' for r in registry),
                'federal_indicators': sum(r['indicator_level'] != 'national_project' for r in registry),
                'known_sources': len(sources), 'numeric_sources': sum(s['available'] for s in sources),
                'indicators_with_numeric': sum(any(by_id[sid]['available'] for sid in r['source_ids']) for r in registry),
                'metadata_only_sources': sum(not s['available'] for s in sources),
                'unmapped_indicators': len(config['unmapped_indicators']), 'observations': len(all_rows),
                'numeric_observations': sum(r['value'] is not None for r in all_rows),
                'missing_observations': sum(r['value'] is None for r in all_rows),
                'excluded_numeric_observations': sum(r['value'] is not None and r['excluded'] for r in all_rows),
                'independent_annual_national_facts': sum(len([r for r in s['annual'] if not r['excluded']]) for s in sources),
                'regional_sources': sum(bool(s['regional_latest']) for s in sources),
                'other_territory_observations': sum(r['geo_level'] == 'other' for r in all_rows)}
    distributions = []
    for source in sources:
        if not source['regional_latest']:
            continue
        matching_national = next((r for r in source['national'] if r['period_end'] == source['regional_period_end'] and r['frequency'] == source['regional_latest'][0]['frequency']), None)
        distributions.append({'source_id': source['id'], 'title': source['short_title'],
                              'period_end': source['regional_period_end'], 'unit': source['unit'],
                              **summary(source['regional_latest']),
                              'national_value': matching_national['analytical_value'] if matching_national else None,
                              'national_value_origin': 'published_national_series_not_regional_average'})

    changes = []
    for source in sources:
        monthly = {r['period']: r for r in source['national'] if r['frequency'] in ('monthly', 'cumulative_ytd') and r['analytical_value'] is not None}
        for period, row in sorted(monthly.items()):
            prior_period = f'{int(period[:4]) - 1}{period[4:]}'
            if prior_period not in monthly:
                continue
            previous = monthly[prior_period]
            changes.append({'source_id': source['id'], 'title': source['short_title'], 'period': period,
                            'prior_period': prior_period, 'value': row['value'], 'prior_value': previous['value'],
                            'change': round(row['value'] - previous['value'], 10), 'unit': source['unit'],
                            'change_unit': difference_unit(source),
                            'interpretation': 'Описательная разность одинаковых месяцев; не причинный эффект и не подтверждение годового исполнения.'})

    availability = [{'source_id': s['id'], 'title': s['short_title'], 'period': r['period'], 'frequency': r['frequency'],
                     'status': r['status'], 'value': r['value'], 'excluded': r['excluded']} for s in sources for r in s['national']]
    quality = [{'source_id': r['source_id'], 'name': r['name'], 'period': r['period'], 'value': r['value'], **flag}
               for r in all_rows for flag in r['quality_flags'] if flag['code'] != 'missing']
    forecast = [forecast_eligibility(s) for s in sources if s['available']]
    regions = {}
    for source in sources:
        for row in source['regional_latest']:
            regions.setdefault(row['code'], {'code': row['code'], 'name': row['name'], 'observations': []})['observations'].append({'source_id': source['id'], 'title': source['short_title'], 'unit': source['unit'], **row})

    comparisons = []
    targets = target_rows(root)
    target_points = []
    for target in targets:
        if target.get('years'):
            target_points.extend({**target, 'year': int(year), 'value': value} for year, value in target['years'].items())
        else:
            target_points.append(target)
    for target in target_points:
        sid = str(target.get('source_id', target.get('emiss_id', '')))
        source = by_id.get(sid)
        year = target.get('year', target.get('target_year'))
        goal = target.get('value', target.get('target_value'))
        if source is None or year is None or goal is None:
            continue
        validate_target_unit(source, target)
        year = int(year)
        annual = [r for r in source['annual'] if int(r['year']) == year and not r['excluded'] and not r['category']]
        fact = annual[-1] if annual else latest([r for r in source['national'] if r['year'] == year and r['frequency'] != 'annual' and not r['excluded'] and not r['category']])
        if fact:
            comparisons.append({'source_id': sid, 'target_year': year, 'target_value': goal,
                                'fact_value': fact['value'], 'fact_period': fact['period'], 'fact_frequency': fact['frequency'],
                                'difference': round(fact['value'] - float(goal), 10), 'unit': source['unit'],
                                'difference_unit': difference_unit(source),
                                'comparison_kind': 'annual_fact_vs_annual_plan' if annual else 'operational_point_vs_annual_plan',
                                'formal_attainment_eligible': bool(annual), 'target_source': target})
    analytics = {'schema_version': 1, 'project_id': 'youth_children', 'published_at': published_at,
                 'coverage': coverage, 'regional_summaries': distributions, 'regions': list(regions.values()),
                 'same_month_changes': changes, 'availability': availability, 'quality_flags': quality,
                 'forecast_eligibility': forecast, 'targets': targets, 'target_comparisons': comparisons,
                 'causal': {'identified': False, 'reason': 'В доступных источниках отсутствуют дизайн сопоставления, контрольная группа и достаточная панель; причинный эффект не оценён.'},
                 'multivariate': {'computed': False, 'reason': 'Два региональных показателя имеют разные последние даты и разные единицы наблюдения; общий рейтинг, PCA и кластеризация не рассчитываются.'},
                 'methods': [{'id': 'regional_distribution', 'status': 'computed', 'description': 'Невзвешенные распределения отдельно для каждого источника и периода; квартиль type 7.'},
                             {'id': 'same_month', 'status': 'computed', 'description': 'Сравнение одинаковых месяцев без склейки накопления через январь.'},
                             {'id': 'target_comparison', 'status': 'computed_when_matching', 'description': 'Совпадение источника, единицы и года; оперативная запись отдельно от годового факта.'},
                             {'id': 'forecast', 'status': 'not_computable', 'description': 'Не хватает независимых годовых наблюдений.'},
                             {'id': 'causal_effect', 'status': 'not_identified', 'description': 'Нужен отдельный дизайн исследования.'}],
                 'reproduction': 'python scripts/build_youth_analytics.py'}
    atomic(root / DATA / 'statistics.json', statistics)
    atomic(root / DATA / 'analytics.json', analytics)
    atomic(root / DATA / 'indicators.json', {**registry_packet, 'as_of': published_at[:10] if published_at else None,
           'origin_policy': 'verified_current_youth_sources; explicit periods and units; raw anomalies retained with analytical flags', 'items': current_registry})
    methods_path = root / DATA / 'methods.json'
    if methods_path.exists():
        methods_packet = load(methods_path)
        overrides = {
            'theory_of_change': ('author_review_completed', 'Авторская экспертиза раскрывает механизмы девяти федеральных проектов; причинный эффект не оценён.'),
            'domain_evidence': ('author_review_completed', 'Предметная проверка и 18 тематических категорий доступны; частоты и наличие мер не превращаются в балл эффективности.'),
            'recommendations': ('author_review_completed', 'Размещены авторские предложения, последовательность внедрения и протоколы последующего наблюдения.'),
            'expert_domain_scale': ('not_assigned_by_author', 'Авторская экспертиза не присваивает сводных баллов 0–4. Показана матрица свидетельств без вымышленных оценок.'),
            'activity_indicator_links': ('author_documentary_review_completed', 'Для десяти результатов рассмотрены прямые паспортные привязки. Отдельно показаны структурные связи и неутверждённые смысловые кандидаты.'),
            'source_quality': ('computed_current_source', f'Все первичные значения сохранены; числовых записей, исключённых только из анализа с явным основанием: {coverage["excluded_numeric_observations"]}.'),
            'observability': ('computed_current_source', 'Доступность пересчитывается из текущих источников. Число ячеек не является числом независимых годовых фактов.'),
            'time_dynamics': ('computed_current_source', 'Накопительные годы разделяются; доступны сравнения одинаковых месяцев и полная выгрузка исходных значений.'),
            'target_comparison': ('computed_current_source', '54 официальных цели девяти национальных показателей; годовые факты отделены от оперативных. Единицы и категории проверяются до сравнения.'),
            'forecasting': ('model_not_validated' if any(f['status'] == 'model_not_validated' for f in forecast) else 'not_computable_independent_annual_history', 'Накопительные месячные записи не заменяют независимый годовой ряд. Показан арифметический целевой сценарий без вероятности достижения и доверительных интервалов.'),
            'geographical_join': ('computed_current_source', 'Используются явные соответствия территорий геометрии. Другие территориальные позиции сохранены отдельно.'),
            'regional_maps': ('computed_current_source', 'Исторические срезы выбираются внутри одного показателя; цвет не является оценкой эффективности.'),
            'regional_descriptive': ('computed_current_source', 'Квантили type 7 отдельно для каждого периода и показателя. Общероссийская доля взята из национального ряда, а не усреднена по регионам.'),
            'moran_global': ('not_in_author_expertise', 'Диагностика исследовательского выпуска 1.2 сохранена в исходном статусе. В текущей авторской экспертизе вместо вывода об эффекте рассматриваются карты и самостоятельные распределения.'),
            'moran_local': ('not_in_author_expertise', 'Локальная пространственная ассоциация не является оценкой эффекта. Авторская экспертиза не использует LISA как рейтинг результатов.'),
            'cohort_projection': ('not_applicable_to_project', 'Когортная демографическая передвижка остаётся специализированным модулем «Семьи». Для «Молодёжи и детей» представлены определения целевых групп и образовательные переходы.'),
            'interactive_lab': ('implemented_reproducible', 'В интерфейсе повторяются квантили, изменения одинаковых месяцев, аудит и сверка финансов; исходники и входы доступны для скачивания.'),
        }
        for method in methods_packet['items']:
            if method['method_id'] in overrides:
                method['current_status'], method['current_limitations'] = overrides[method['method_id']]
        methods_packet['current_review_basis'] = 'author_expertise_and_current_platform; original status_1_2 retained for provenance'
        atomic(methods_path, methods_packet)
    downloads = root / DOWNLOADS
    csv_write(downloads / 'observations.csv', all_rows)
    csv_write(downloads / 'source_registry.csv', [{k: s[k] for k in ('id', 'title', 'short_title', 'unit', 'source_url', 'indicator_codes', 'available', 'published_at', 'last_checked_at', 'observation_count', 'numeric_count', 'missing_count', 'note')} for s in sources])
    csv_write(downloads / 'regional_latest.csv', [r for s in sources for r in s['regional_latest']])
    csv_write(downloads / 'regional_summaries.csv', distributions)
    csv_write(downloads / 'same_month_changes.csv', changes)
    csv_write(downloads / 'quality_flags.csv', quality)
    csv_write(downloads / 'availability.csv', availability)
    csv_write(downloads / 'target_comparisons.csv', comparisons, ['source_id', 'target_year', 'target_value', 'fact_value', 'fact_period', 'fact_frequency', 'difference', 'unit', 'difference_unit', 'comparison_kind', 'formal_attainment_eligible', 'target_source'])
    downloads_manifest = download_records(downloads, root / 'public', suffixes=('.csv', '.zip'))
    atomic(root / DATA / 'data-downloads.json', {'schema_version': 1, 'files': downloads_manifest})
    print(json.dumps(coverage))
    return statistics, analytics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    build(args.root)
