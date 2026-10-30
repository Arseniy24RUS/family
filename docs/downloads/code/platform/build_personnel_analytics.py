#!/usr/bin/env python3
"""Recompute source-backed Personnel summaries and CSV downloads, offline.

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
from personnel_data import ROOT, DATA, DOWNLOADS, load, atomic, sha256, csv_write, quantile, annual_equivalents, build_context


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
    expected = f'downloads/projects/personnel/statistical/emiss_current/{source_id}.zip'
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
    downloads = {'observations': f'data/projects/personnel/series/{config["indicator_id"]}.json',
                 'provenance': f'data/projects/personnel/provenance/{config["indicator_id"]}.json',
                 'source_input': f'downloads/projects/personnel/statistical/emiss_inputs/{config["indicator_id"]}.zip'}
    current_raw = current_raw_download(root, config['indicator_id'], status)
    if current_raw:
        downloads['current_raw'] = current_raw
    return {
        'id': config['indicator_id'], 'title': config['title'], 'short_title': config['short_title'],
        'indicator_codes': config['indicator_codes'], 'indicator_level': config['indicator_level'],
        'federal_project_name': config['federal_project_name'], 'unit': config['unit'],
        'source_url': config['source_url'], 'cumulative': config['cumulative'],
        'annual_reset': config['annual_reset'], 'note': config['note'],
        'upper_bound': config.get('upper_bound', 100), 'annual_equivalence_rule': config.get('annual_equivalence'),
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
        'annual_equivalents': annual_equivalents(config['indicator_id'], national),
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
    def canonical(value):
        value = str(value).strip().casefold()
        return 'процент' if value in {'%', 'процент', 'проценты', 'процентов'} else value
    if canonical(target.get('unit', '')) != canonical(source['unit']):
        raise ValueError(f'Target unit differs from confirmed source unit: {source["id"]}')


def difference_unit(source):
    if source.get('cumulative') == 'index':
        return 'пункты индекса'
    return 'п.п.' if source['unit'].casefold() == 'процент' else source['unit']


def forecast_eligibility(source):
    count = len({r['year'] for r in source['annual'] + source.get('annual_equivalents', []) if not r['excluded'] and not r['category']})
    insufficient = count < 4
    return {'source_id': source['id'], 'title': source['short_title'],
            'annual_observations': count, 'distinct_annual_years': count, 'eligible': False,
            'status': 'insufficient_independent_annual_history' if insufficient else 'model_not_validated',
            'reason': 'Независимого годового ряда недостаточно для проверяемого прогноза. Накопительные месячные записи не заменяют независимые годы. Допустим условный расчёт требуемой траектории к цели.' if insufficient else 'Годовые наблюдения накоплены; прогнозная модель ещё не выбрана и не проверена на ретроспективных данных. Автоматическая публикация прогноза требует отдельной валидации.'}


def build(root=ROOT):
    root = Path(root)
    context = build_context(root)
    review_path = root / DATA / 'provenance/analytical-review.json'
    prior_review = load(review_path) if review_path.exists() else None
    if prior_review:
        original_audit = root / 'public' / prior_review['source_file']
        if not original_audit.resolve().is_relative_to((root / 'public').resolve()) or sha256(original_audit) != prior_review['source_sha256']:
            raise ValueError('Original analytical audit checksum mismatch')
    config = load(root / 'scripts/personnel_emiss_sources.json')
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
                                      'series_id': 'personnel_' + hashlib.sha256((source['id'] + '|' + point['frequency'] + '|' + json.dumps(point['category'], sort_keys=True)).encode()).hexdigest()[:20],
                                      'observation_key': point['source_observation_key'] or point['id'],
                                      'analysis_status': 'excluded' if point['excluded'] else 'usable'})
        current_registry.append({**indicator, 'source_release_counts': indicator.get('source_release_counts') or {key: indicator.get(key) for key in ('n_cells', 'n_numeric', 'n_usable', 'n_domain_violations')}, 'n_linked_sources': len(linked),
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
    statistics = {'schema_version': 1, 'project_id': 'personnel', 'published_at': published_at,
                  'statistical_as_of': published_at[:10] if published_at else None,
                  'last_checked_at': refresh.get('checked_at'),
                  'geography_note': 'Состав территориальных позиций воспроизводит перечень статистического источника. Картографическое представление не выражает позиции по международно-правовому статусу территорий.',
                  'sources': sources, 'unmapped_indicators': config['unmapped_indicators'],
                  'source_release_analytical_review': 'data/projects/personnel/provenance/analytical-review.json' if prior_review else None,
                  'downloads': [{'label': label, 'path': f'downloads/projects/personnel/statistical/{name}.csv'} for name, label in [
                      ('observations', 'Все исходные наблюдения'), ('source_registry', 'Реестр источников'),
                      ('target_comparisons', 'Сопоставления с целями'), ('annual_equivalents', 'Методические годовые эквиваленты'),
                      ('same_month_changes', 'Изменения одинаковых периодов'), ('quality_flags', 'Примечания к качеству'),
                      ('availability', 'Календарь наблюдений'), ('context_unemployment_2024', 'Безработица 2024 – контекст регионов'),
                      ('context_summary', 'Распределение контекста')]]}
    if prior_review:
        statistics['downloads'].append({'label': 'Исходный аналитический аудит 1.2.0', 'path': prior_review['source_file']})

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
                'annual_equivalent_references': sum(len(s['annual_equivalents']) for s in sources),
                'usable_observations': sum(r['analytical_value'] is not None for r in all_rows),
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
        monthly = {r['period']: r for r in source['national'] if r['frequency'] in ('monthly', 'cumulative_ytd', 'quarterly') and r['analytical_value'] is not None}
        for period, row in sorted(monthly.items()):
            prior_period = f'{int(period[:4]) - 1}{period[4:]}'
            if prior_period not in monthly:
                continue
            previous = monthly[prior_period]
            changes.append({'source_id': source['id'], 'title': source['short_title'], 'period': period,
                            'prior_period': prior_period, 'value': row['value'], 'prior_value': previous['value'],
                            'change': round(row['value'] - previous['value'], 10), 'unit': source['unit'], 'frequency': row['frequency'],
                            'change_unit': difference_unit(source),
                            'interpretation': 'Описательная разность одинаковых календарных периодов. Плановый знаменатель, состав когорты и методика требуют отдельной проверки; причинный эффект не установлен.'})

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
        equivalents = [r for r in source['annual_equivalents'] if int(r['year']) == year]
        fact = annual[-1] if annual else equivalents[-1] if equivalents else latest([r for r in source['national'] if r['year'] == year and r['frequency'] != 'annual' and not r['excluded'] and not r['category']])
        if fact:
            comparisons.append({'source_id': sid, 'target_year': year, 'target_value': goal,
                                'fact_value': fact['value'], 'fact_period': fact['period'], 'fact_frequency': fact['frequency'],
                                'difference': round(fact['value'] - float(goal), 10), 'unit': source['unit'],
                                'difference_unit': difference_unit(source),
                                'comparison_kind': 'annual_fact_vs_annual_plan' if annual else 'annual_equivalent_vs_annual_plan' if equivalents else 'operational_point_vs_annual_plan',
                                'annual_basis': 'Самостоятельная годовая запись ЕМИСС.' if annual else fact.get('annual_basis'),
                                'methodology_url': fact.get('methodology_url'), 'reference_observation_id': fact.get('reference_observation_id', fact['id']),
                                'original_period': fact.get('original_period', fact['period']),
                                'annual_comparison_eligible': bool(annual or equivalents),
                                'formal_attainment_eligible': False, 'target_source': target,
                                'interpretation': 'Арифметическое сопоставление с выбранной редакцией цели; оно не удостоверяет выполнение первоначального обязательства или причинный результат.'})
    analytics = {'schema_version': 1, 'project_id': 'personnel', 'published_at': published_at,
                 'coverage': coverage, 'regional_summaries': distributions, 'regions': list(regions.values()), 'context': context,
                 'same_month_changes': changes, 'availability': availability, 'quality_flags': quality,
                 'forecast_eligibility': forecast, 'targets': targets, 'target_comparisons': comparisons,
                 'causal': {'identified': False, 'reason': 'В доступных источниках отсутствуют дизайн сопоставления, контрольная группа и достаточная панель; причинный эффект не оценён.'},
                 'multivariate': {'computed': False, 'reason': 'Региональные проектные наблюдения отсутствуют. Отдельный контекст безработицы 2024 года не образует многомерной матрицы результатов проекта.'},
                 'methods': [{'id': 'regional_context', 'status': 'computed_context_only', 'description': 'Отдельное распределение безработицы 2024 года; квартиль type 7, без рейтинга результативности проекта.'},
                             {'id': 'same_month', 'status': 'computed', 'description': 'Сравнение одинаковых календарных периодов с учётом планового знаменателя, накопления и квартальных волн.'},
                             {'id': 'target_comparison', 'status': 'computed_when_matching', 'description': 'Самостоятельные годовые факты, методические эквиваленты и оперативные записи показаны раздельно.'},
                             {'id': 'forecast', 'status': 'not_computable', 'description': 'Не хватает независимых годовых наблюдений.'},
                             {'id': 'causal_effect', 'status': 'not_identified', 'description': 'Нужен отдельный дизайн исследования.'}],
                 'reproduction': 'python scripts/build_personnel_analytics.py'}
    atomic(root / DATA / 'statistics.json', statistics)
    atomic(root / DATA / 'analytics.json', analytics)
    atomic(root / DATA / 'indicators.json', {**registry_packet, 'as_of': published_at[:10] if published_at else None,
           'origin_policy': 'verified_current_personnel_sources; explicit periods and units; raw anomalies retained with analytical flags', 'items': current_registry})
    foundation_path = root / DATA / 'foundation.json'
    if foundation_path.exists():
        foundation = load(foundation_path)
        foundation.setdefault('source_release_registry', dict(foundation.get('registry', {})))
        foundation.setdefault('source_release_results', dict(foundation.get('results', {})))
        foundation['registry'].update(n_registry=coverage['indicators_total'], n_with_numeric=coverage['indicators_with_numeric'],
                                     n_unique_cells=coverage['observations'], n_numeric=coverage['numeric_observations'],
                                     n_usable=coverage['usable_observations'], n_domain_violations=sum(r['n_domain_violations'] for r in current_registry),
                                     n_with_national=sum(any(source['national'] for source in sources if source['id'] in r['source_ids']) for r in current_registry),
                                     n_with_regional=coverage['regional_sources'], coverage_pct=100 * coverage['indicators_with_numeric'] / coverage['indicators_total'])
        series_keys = lambda records: {(r['source_id'], r['frequency'], r['name'], json.dumps(r['category'], sort_keys=True)) for r in records}
        scenario_sources = {s['id'] for s in sources if (s['annual'] or s['annual_equivalents']) and any(str(t.get('source_id', t.get('emiss_id'))) == s['id'] and t.get('years', {}).get('2030') is not None and t.get('mapping_status') != 'conditional' for t in targets)}
        foundation['results'].update(n_forecast_indicators=0, n_projected_series=0, n_diagnostic_forecast_series=0,
                                    n_numeric_indicators=coverage['indicators_with_numeric'], n_regional_indicators=coverage['regional_sources'],
                                    n_series=len(series_keys(all_rows)), n_series_with_review_flags=len(series_keys([r for r in all_rows if r['quality_flags']])),
                                    n_reference_scenario_series=len(scenario_sources), n_documented_target_indicators=len(targets),
                                    forecast_status='insufficient_independent_annual_history',
                                    n_annual_facts=coverage['independent_annual_national_facts'],
                                    n_annual_equivalent_references=coverage['annual_equivalent_references'])
        foundation['statistical_as_of'] = published_at[:10] if published_at else None
        foundation['context'] = {'kind': 'pre_project_context', 'year': 2024, 'n_regions': 85, 'source': context['source_url']} if context else None
        if (root / DATA / 'expertise.json').exists():
            foundation['author_expertise_status'] = 'published'
            foundation['research']['author_expertise_text_status'] = 'published'
            for section in foundation.get('sections', []):
                section['publication_status'] = 'published'
                if section['section_id'] == 'map':
                    section['evidence'] = 'Проектные региональные ряды отсутствуют. Представлен самостоятельный контекст безработицы 2024 года для 85 территорий.'
        atomic(foundation_path, foundation)
    methods_path = root / DATA / 'methods.json'
    if methods_path.exists():
        methods_packet = load(methods_path)
        overrides = {
            'theory_of_change': ('author_review_completed', 'Авторская экспертиза раскрывает механизмы четырёх федеральных проектов. Причинный эффект не оценён.'),
            'domain_evidence': ('author_review_completed', 'Предметная проверка связывает меры с потребностью работодателей, обучением и трудовыми переходами; частота слов не является эффектом.'),
            'recommendations': ('author_review_completed', 'Размещены авторские предложения и протоколы дополнительного наблюдения трудовых траекторий.'),
            'expert_domain_scale': ('not_assigned_by_author', 'Сводные экспертные баллы не назначались. Представлены документы, выводы и ограничения.'),
            'activity_indicator_links': ('author_documentary_review_completed', 'Десять прямых связей в полном паспорте управления рынком труда отделены от связей через общую задачу.'),
            'source_quality': ('computed_current_source', f'Первичные значения сохранены. Допустимые аналитические числовые ячейки: {coverage["usable_observations"]}. Для индекса и отношения к плану значения выше 100 допускаются.'),
            'observability': ('computed_current_source', 'Доступность пересчитывается из текущих источников. Методические годовые эквиваленты не добавляют независимых исходных ячеек.'),
            'time_dynamics': ('computed_current_source', 'Накопление внутри года и с начала мероприятия различается. Квартальные волны не интерполируются. Сохранены пропуски и пересмотры.'),
            'target_comparison': ('computed_current_source', 'Цели выбранной редакции сравниваются с отдельными годовыми фактами, методическими годовыми эквивалентами и оперативными записями раздельно.'),
            'forecasting': ('not_computable_independent_annual_history', 'Один наблюдаемый год не обеспечивает ретроспективную проверку прогноза. Доступен условный арифметический расчёт движения к цели.'),
            'geographical_join': ('computed_context_only', 'Контекст безработицы 2024 года соединён с 85 территориями. Проектных региональных рядов нет.'),
            'regional_maps': ('computed_context_only', 'Карта отражает исходные условия до начала нацпроекта. Цвет не обозначает результативность его мероприятий.'),
            'regional_descriptive': ('computed_context_only', 'Невзвешенные квантили и распределение контекста. Общероссийская величина взята из исходной таблицы, не усреднена по регионам.'),
            'correlations': ('not_identified_with_current_data', 'Пересекающиеся совокупности и накопление не позволяют интерпретировать корреляцию пяти коротких рядов как причинную связь.'),
            'pca': ('not_computable_project_regional_data', 'Отсутствует матрица сопоставимых региональных показателей проекта.'),
            'kmeans': ('not_computable_project_regional_data', 'Кластеризация региональной результативности не рассчитана: проектных региональных рядов нет.'),
            'multivariate_stability': ('not_computable_project_regional_data', 'Устойчивость многомерной модели не оценивается без исходной матрицы.'),
            'isolation_forest': ('not_computable_project_regional_data', 'Произвольная доля аномалий не назначается; числовые оговорки основаны на содержании методик.'),
            'moran_global': ('not_in_author_expertise', 'Пространственные коэффициенты не заявляются. Представлен контекст исходных условий рынка труда.'),
            'moran_local': ('not_in_author_expertise', 'Локальные пространственные ассоциации не объявляются эффектом проекта.'),
            'regional_similarity': ('not_computable_project_regional_data', 'Нет многомерных региональных профилей проектных результатов.'),
            'relative_profiles': ('not_computable_project_regional_data', 'Контекст безработицы не превращается в сводный показатель эффективности.'),
            'cohort_projection': ('not_applicable_to_project', 'Представлены целевые группы, возрастная стандартизация и трудовые переходы; демографическая передвижка относится к специализированному модулю Семьи.'),
            'interactive_lab': ('implemented_reproducible', 'Лаборатория повторяет арифметику годовых сопоставлений, условных траекторий и финансовой сверки.'),
        }
        for method in methods_packet['items']:
            if method['method_id'] in overrides:
                method['current_status'], method['current_limitations'] = overrides[method['method_id']]
        methods_packet['current_review_basis'] = 'author_expertise_and_current_platform; original status_1_2 retained for provenance'
        atomic(methods_path, methods_packet)
    downloads = root / DOWNLOADS
    csv_write(downloads / 'observations.csv', all_rows)
    csv_write(downloads / 'source_registry.csv', [{k: s[k] for k in ('id', 'title', 'short_title', 'unit', 'source_url', 'indicator_codes', 'available', 'published_at', 'last_checked_at', 'observation_count', 'numeric_count', 'missing_count', 'note')} for s in sources])
    csv_write(downloads / 'annual_equivalents.csv', [r for s in sources for r in s['annual_equivalents']])
    csv_write(downloads / 'same_month_changes.csv', changes)
    csv_write(downloads / 'quality_flags.csv', quality)
    csv_write(downloads / 'availability.csv', availability)
    csv_write(downloads / 'target_comparisons.csv', comparisons, ['source_id', 'target_year', 'target_value', 'fact_value', 'fact_period', 'fact_frequency', 'difference', 'unit', 'difference_unit', 'comparison_kind', 'annual_comparison_eligible', 'annual_basis', 'methodology_url', 'reference_observation_id', 'original_period', 'formal_attainment_eligible', 'target_source', 'interpretation'])
    downloads_manifest = download_records(downloads, root / 'public', suffixes=('.csv', '.zip', '.json', '.txt', '.html'))
    atomic(root / DATA / 'data-downloads.json', {'schema_version': 1, 'files': downloads_manifest})
    print(json.dumps(coverage))
    return statistics, analytics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    build(args.root)
