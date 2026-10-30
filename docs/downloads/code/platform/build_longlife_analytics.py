#!/usr/bin/env python3
"""Build compact Long and Active Life views from published source packets.

The complete observations remain in per-source files and downloadable CSVs.
Author diagnostic imputation never modifies a factual observation.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

from download_manifest import download_records
from longlife_data import ROOT, DATA, DOWNLOADS, load, atomic, sha256, csv_write, quantile


def latest(rows):
    values = [r for r in rows if r['value'] is not None]
    return max(values, key=lambda r: (r['period_end'], r['frequency'] == 'annual')) if values else None


def slice_key(row):
    return row['period_end'], row['frequency'], json.dumps(row['category'], ensure_ascii=False, sort_keys=True)


def compact(row):
    if row is None:
        return None
    keep = {'id', 'source_id', 'name', 'code', 'map_id', 'fd', 'geo_level', 'period', 'period_end', 'year', 'frequency',
            'value', 'analytical_value', 'excluded', 'status', 'category', 'unit', 'geographic_comparison_eligible',
            'author_comparison_eligible', 'quality_flags'}
    return {k: v for k, v in row.items() if k in keep}


def summary(rows):
    usable = [r for r in rows if r.get('analytical_value') is not None]
    values = [r['analytical_value'] for r in usable]
    return {'n': len(values), 'minimum': min(values) if values else None,
            'q1': quantile(values, .25), 'median': quantile(values, .5), 'q3': quantile(values, .75),
            'maximum': max(values) if values else None,
            'mean': sum(values) / len(values) if values else None,
            'weighting': 'unweighted_territories', 'quartile_method': 'Hyndman_Fan_type_7'}


def current_raw_download(root, sid, status):
    raw = status.get('raw_file')
    if not raw:
        return None
    expected = f'downloads/projects/long_active_life/statistical/emiss_current/{sid}.zip'
    if raw != expected:
        raise ValueError('Unexpected current source response path: ' + sid)
    provenance = load(root / DATA / 'provenance' / (sid + '.json'))
    if provenance.get('current_raw') != raw or sha256(root / 'public' / raw) != provenance.get('current_raw_sha256'):
        raise ValueError('Current response provenance mismatch: ' + sid)
    return raw


def make_source(config, packet, status, root=ROOT):
    rows = packet['observations']
    national = [r for r in rows if r['geo_level'] == 'national']
    regional = [r for r in rows if r['geo_level'] == 'regional']
    slices = collections.defaultdict(list)
    for row in regional:
        slices[slice_key(row)].append(row)
    eligible_slices = [key for key, points in slices.items() if any(r['analytical_value'] is not None for r in points)]
    latest_key = max(eligible_slices, key=lambda key: (key[0], key[1] == 'annual', key[2] == '{}')) if eligible_slices else None
    regional_latest = slices.get(latest_key, [])
    downloads = {'observations': f'data/projects/long_active_life/series/{config["indicator_id"]}.json',
                 'provenance': f'data/projects/long_active_life/provenance/{config["indicator_id"]}.json',
                 'source_input': f'downloads/projects/long_active_life/statistical/emiss_inputs/{config["indicator_id"]}.zip'}
    raw = current_raw_download(Path(root), config['indicator_id'], status)
    if raw:
        downloads['current_raw'] = raw
    source = {key: config.get(key) for key in ('title', 'short_title', 'indicator_codes', 'indicator_level', 'federal_project_name', 'unit',
              'display_unit', 'source_url', 'cumulative', 'annual_reset', 'note', 'direction', 'domain', 'lower_bound', 'upper_bound',
              'period_semantics', 'period_note', 'methodology', 'periodicity', 'target_comparison_allowed', 'target_comparison_note', 'proxy_only')}
    source.update(id=config['indicator_id'], available=any(r['value'] is not None for r in rows),
                  published_at=packet['published_at'], last_success=status.get('last_success') or packet['published_at'],
                  last_checked_at=status.get('checked_at'), refresh_state=status.get('state'), snapshot_id=packet.get('snapshot_id'),
                  observation_count=len(rows), numeric_count=sum(r['value'] is not None for r in rows),
                  missing_count=sum(r['value'] is None for r in rows),
                  excluded_numeric_count=sum(r['value'] is not None and r['excluded'] for r in rows),
                  usable_count=sum(r['analytical_value'] is not None for r in rows),
                  latest_national=compact(latest(national)), national=[compact(r) for r in national],
                  annual=[compact(r) for r in national if r['frequency'] == 'annual'], annual_equivalents=[],
                  regional_latest=[compact(r) for r in regional_latest], regional_history=[], regional_history_deferred=True,
                  regional_periods=sorted({r['period_end'] for r in regional}),
                  regional_slices=[{'period': points[0]['period'], 'period_end': key[0], 'frequency': key[1], 'category': points[0]['category'],
                                    'count': len(points), 'numeric_count': sum(r['value'] is not None for r in points),
                                    'usable_count': sum(r['analytical_value'] is not None for r in points)} for key, points in sorted(slices.items())],
                  regional_period_end=latest_key[0] if latest_key else None,
                  regional_frequency=latest_key[1] if latest_key else None,
                  regional_category=json.loads(latest_key[2]) if latest_key else None,
                  other_territories=[compact(r) for r in rows if r['geo_level'] == 'other'],
                  quality_flags=[{'code': 'source_methodology', 'message': config['note'], 'severity': 'info', 'exclude_from_analysis': False}],
                  downloads=downloads)
    return source


def difference_unit(source):
    if source['domain'] in {'bounded_index', 'nonnegative_ratio'} and source['id'] != '62926':
        return 'пункты индекса'
    return 'п.п.' if source['unit'].casefold() in {'%', 'процент'} else source.get('display_unit', source['unit'])


def validate_target_unit(source, target):
    def canonical(value):
        value = str(value or '').strip().casefold()
        if value in {'%', 'процент', 'проценты', 'процентов'}:
            return 'процент'
        if value in {'человек', 'чел.', 'чел'}:
            return 'человек'
        if value in {'литр чистого (100 %) спирта', 'литр чистого (100%) спирта', 'литр'}:
            return 'литр чистого спирта'
        return value
    allowed = {canonical(source['unit']), canonical(source.get('display_unit'))}
    if canonical(target.get('unit')) not in allowed:
        raise ValueError('Target unit differs from confirmed source unit: ' + source['id'])


def forecast_eligibility(source):
    years = {r['year'] for r in source['annual'] if r['analytical_value'] is not None and not r['category']}
    return {'source_id': source['id'], 'title': source['short_title'], 'annual_observations': len(years),
            'distinct_annual_years': len(years), 'eligible': False,
            'status': 'insufficient_independent_annual_history' if len(years) < 4 else 'model_not_validated',
            'reason': 'Накопительные, административные и пересекающиеся месячные оценки не заменяют несколько независимых годовых наблюдений. Проверенная прогнозная модель отсутствует.'}


def target_rows(root):
    path = root / DATA / 'targets.json'
    if not path.exists():
        return []
    data = load(path)
    return data if isinstance(data, list) else data.get('items', [])


def target_comparisons(sources, targets):
    by_id, comparisons = {s['id']: s for s in sources}, []
    for target in targets:
        sid = str(target.get('source_id', target.get('emiss_id', '')))
        source = by_id.get(sid)
        if source is None or not source.get('target_comparison_allowed', True) or target.get('mapping_status') == 'conditional':
            continue
        validate_target_unit(source, target)
        for raw_year, goal in target.get('years', {}).items():
            if goal is None:
                continue
            year = int(raw_year)
            annual = [r for r in source['annual'] if r['year'] == year and r['analytical_value'] is not None and not r['category']]
            fact = annual[-1] if annual else latest([r for r in source['national'] if r['year'] == year and r['frequency'] != 'annual' and r['analytical_value'] is not None and not r['category']])
            if fact is None:
                continue
            difference = round(fact['value'] - float(goal), 10)
            favourable = difference if source['direction'] == 'higher' else -difference
            comparisons.append({'source_id': sid, 'indicator_code': target.get('indicator_code', target.get('code')),
                                'target_year': year, 'target_value': goal, 'fact_value': fact['value'],
                                'fact_period': fact['period'], 'fact_frequency': fact['frequency'], 'difference': difference,
                                'unit': source['unit'], 'display_unit': source['display_unit'], 'difference_unit': difference_unit(source),
                                'direction': source['direction'], 'favourable_difference': favourable, 'on_favourable_side': favourable >= 0,
                                'proxy_only': source.get('proxy_only', False),
                                'comparison_kind': 'annual_fact_vs_annual_plan' if annual else 'operational_point_vs_annual_plan',
                                'annual_comparison_eligible': bool(annual), 'formal_attainment_eligible': False,
                                'annual_basis': 'Самостоятельная годовая запись ЕМИСС.' if annual else None,
                                'reference_observation_id': fact['id'], 'original_period': fact['period'],
                                'target_source': target,
                                'interpretation': 'Сопоставление с выбранной опубликованной редакцией цели не подтверждает исполнение первоначального обязательства или причинный эффект. Оперативная запись не заменяет годовой факт.'})
    return comparisons


def author_staffing(packets, sources):
    from scipy.stats import spearmanr, pearsonr
    period, doctors_id, nurses_id = '2026-07', '62971', '62970'
    by_id = {s['id']: s for s in sources}
    if not all(sid in packets for sid in (doctors_id, nurses_id)):
        return None
    scopes, national = {}, {}
    for sid in (doctors_id, nurses_id):
        exact = [r for r in packets[sid]['observations'] if r['period'] == period and r['frequency'] == 'monthly' and not r['category']]
        national[sid] = next((r['analytical_value'] for r in exact if r['geo_level'] == 'national'), None)
        scopes[sid] = {r['code']: r for r in exact if r['geo_level'] == 'regional' and r['analytical_value'] is not None and r['code'] not in {'29', '72'}}
    if any(value is None for value in national.values()):
        return None
    rows = []
    for code in sorted(scopes[doctors_id].keys() & scopes[nurses_id].keys()):
        doctor, nurse = scopes[doctors_id][code], scopes[nurses_id][code]
        dv, nv = doctor['analytical_value'], nurse['analytical_value']
        group = 'both_below' if dv < national[doctors_id] and nv < national[nurses_id] else 'doctors_below_only' if dv < national[doctors_id] else 'nurses_below_only' if nv < national[nurses_id] else 'both_at_or_above'
        rows.append({'code': code, 'map_id': code, 'name': doctor['name'], 'fd': doctor.get('fd'), 'period': period,
                     'doctors': dv, 'nurses': nv, 'doctors_index_rf100': 100 * dv / national[doctors_id],
                     'nurses_index_rf100': 100 * nv / national[nurses_id], 'group': group,
                     'doctor_observation_id': doctor['id'], 'nurse_observation_id': nurse['id']})
    stats = {}
    for label, sid in [('doctors', doctors_id), ('nurses', nurses_id)]:
        values = [{'analytical_value': row[label]} for row in rows]
        low, high = min(rows, key=lambda r: r[label]), max(rows, key=lambda r: r[label])
        stats[label] = {**summary(values), 'source_id': sid, 'national_value': national[sid],
                        'minimum_region': low['name'], 'maximum_region': high['name'],
                        'max_min_ratio': high[label] / low[label] if low[label] else None,
                        'below_national': sum(row[label] < national[sid] for row in rows)}
    dv, nv = [r['doctors'] for r in rows], [r['nurses'] for r in rows]
    return {'computed': True, 'period': period, 'period_end': '2026-07-31', 'frequency': 'monthly', 'n': len(rows),
            'role': 'author_comparable_staffing_snapshot', 'source_ids': [doctors_id, nurses_id],
            'unit': 'человек на 10 тыс. населения', 'regions': rows, 'summary': stats,
            'national': {'doctors': national[doctors_id], 'nurses': national[nurses_id]},
            'group_counts': dict(collections.Counter(r['group'] for r in rows)),
            'spearman': float(spearmanr(dv, nv).statistic), 'pearson': float(pearsonr(dv, nv).statistic),
            'excluded_codes': ['29', '72'], 'missing_codes': ['90', '93', '94', '95'],
            'scope_note': 'Областные строки 29 и 72 исключены из-за неуточнённого охвата автономных округов. Округа сохранены отдельно. Четыре другие позиции не имеют кадровых значений. Исходные строки доступны в полных рядах.',
            'interpretation': 'РФ — опубликованный описательный ориентир, не норматив достаточности. Физические лица не равны ставкам; корреляция не доказывает взаимозаменяемость персонала.',
            'weighting': 'unweighted_territories', 'national_value_origin': 'published_national_not_regional_average',
            'downloads': {'observations': 'downloads/projects/long_active_life/statistical/author_staffing_2026_07.csv'}}


def author_multivariate(packets, sources, root):
    import numpy as np
    import scipy
    import sklearn
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score, adjusted_rand_score
    catalog = {str(r['id']): r for r in load(root / 'public/data/catalog.json')['regions']}
    codes = sorted(code for code in catalog if code not in {'29', '72', '90', '93', '94', '95'})
    period = '2026-09'
    selected = {}
    by_id = {s['id']: s for s in sources}
    for sid, packet in packets.items():
        lookup = {r['code']: r for r in packet['observations'] if r['geo_level'] == 'regional' and r['period'] == period and r['frequency'] == 'monthly' and not r['category'] and r['code'] in codes}
        if sum(r['analytical_value'] is not None for r in lookup.values()) >= 75:
            selected[sid] = lookup
    sids = sorted(selected)
    if len(codes) < 10 or len(sids) < 2:
        return {'computed': False, 'reason': 'Недостаточно сопоставимых признаков в фиксированном авторском срезе.'}
    x = np.array([[selected[sid].get(code, {}).get('analytical_value', np.nan) for sid in sids] for code in codes], dtype=float)
    medians = np.nanmedian(x, axis=0)
    filled = np.where(np.isnan(x), medians, x)
    scaler = StandardScaler()
    z = scaler.fit_transform(filled)
    pca = PCA(svd_solver='full').fit(z)
    scores = pca.transform(z)
    labels = KMeans(n_clusters=2, n_init=30, random_state=42).fit_predict(z)
    experiments = []
    for k in range(2, 7):
        run = labels if k == 2 else KMeans(n_clusters=k, n_init=30, random_state=42).fit_predict(z)
        counts = sorted(collections.Counter(int(n) for n in run).values(), reverse=True)
        experiments.append({'k': k, 'cluster_sizes': counts, 'minimum_cluster_size': min(counts),
                            'silhouette': float(silhouette_score(z, run)), 'minimum_size_5_passed': min(counts) >= 5})
    seeds = [{'seed': seed, 'adjusted_rand_index': float(adjusted_rand_score(labels, KMeans(n_clusters=2, n_init=30, random_state=seed).fit_predict(z)))} for seed in range(10)]
    complete_mask = ~np.isnan(x).any(axis=1)
    complete = StandardScaler().fit_transform(x[complete_mask])
    complete_checks = []
    for n_init in (30, 200):
        run = KMeans(n_clusters=2, n_init=n_init, random_state=42).fit_predict(complete)
        sizes = collections.Counter(int(n) for n in run)
        singletons = [codes[index] for index, label in zip(np.where(complete_mask)[0], run) if sizes[int(label)] == 1]
        complete_checks.append({'n': int(complete_mask.sum()), 'n_init': n_init, 'cluster_sizes': sorted(sizes.values(), reverse=True),
                                'silhouette': float(silhouette_score(complete, run)), 'singleton_codes': singletons})
    without_rehab = None
    if '62955' in sids:
        reduced = np.delete(z, sids.index('62955'), axis=1)
        run = KMeans(n_clusters=2, n_init=30, random_state=42).fit_predict(reduced)
        without_rehab = {'excluded_source_id': '62955', 'silhouette': float(silhouette_score(reduced, run)),
                         'adjusted_rand_index': float(adjusted_rand_score(labels, run)),
                         'cluster_sizes': sorted(collections.Counter(int(n) for n in run).values(), reverse=True)}
    missing = [{'code': codes[i], 'name': catalog[codes[i]]['name'], 'source_id': sids[j], 'imputed_median': float(medians[j])}
               for i, j in zip(*np.where(np.isnan(x)))]
    diagnostics = [{'code': code, 'name': catalog[code]['name'], 'pc1': float(scores[i, 0]), 'pc2': float(scores[i, 1]), 'cluster': int(labels[i]) + 1,
                    'imputed_count': int(np.isnan(x[i]).sum())} for i, code in enumerate(codes)]
    features = [{'source_id': sid, 'title': by_id[sid]['short_title'], 'unit': by_id[sid]['display_unit'],
                 'median': float(medians[j]), 'mean_after_imputation': float(scaler.mean_[j]), 'scale_population_sd': float(scaler.scale_[j]),
                 'pc1_loading': float(pca.components_[0, j]), 'pc2_loading': float(pca.components_[1, j])} for j, sid in enumerate(sids)]
    raw_matrix = [{'code': code, 'name': catalog[code]['name'], **{sid: None if np.isnan(x[i, j]) else float(x[i, j]) for j, sid in enumerate(sids)}} for i, code in enumerate(codes)]
    diagnostic_matrix = [{'code': code, 'name': catalog[code]['name'], **{sid: float(filled[i, j]) for j, sid in enumerate(sids)}} for i, code in enumerate(codes)]
    csv_write(root / DOWNLOADS / 'multivariate_observed_2026_09.csv', raw_matrix)
    csv_write(root / DOWNLOADS / 'multivariate_diagnostic_imputed_2026_09.csv', diagnostic_matrix)
    csv_write(root / DOWNLOADS / 'multivariate_scores_2026_09.csv', diagnostics)
    csv_write(root / DOWNLOADS / 'multivariate_loadings_2026_09.csv', features)
    csv_write(root / DOWNLOADS / 'multivariate_imputed_cells.csv', missing)
    csv_write(root / DOWNLOADS / 'multivariate_seed_audit_2026_09.csv', seeds)
    return {'computed': True, 'role': 'research_diagnostic_not_performance_ranking', 'period': period, 'period_end': '2026-09-30',
            'frequency': 'monthly', 'n_regions': len(codes), 'n_features': len(sids), 'source_ids': sids, 'region_codes': codes,
            'observed_matrix_sha256': sha256(root / DOWNLOADS / 'multivariate_observed_2026_09.csv'),
            'diagnostic_matrix_sha256': sha256(root / DOWNLOADS / 'multivariate_diagnostic_imputed_2026_09.csv'),
            'source_snapshots': {sid: packets[sid].get('snapshot_id') for sid in sids},
            'implementation_sha256': sha256(Path(__file__)),
            'software': {'numpy': np.__version__, 'scipy': scipy.__version__, 'scikit_learn': sklearn.__version__},
            'excluded_codes': ['29', '72', '90', '93', '94', '95'], 'missing_cells': missing, 'imputed_count': len(missing),
            'imputed_fraction': len(missing) / x.size, 'imputation_policy': 'feature_median_diagnostic_copy_only',
            'standardization': 'StandardScaler; population standard deviation ddof=0',
            'explained_variance_ratio': [float(v) for v in pca.explained_variance_ratio_],
            'pc1_pc2_explained': float(sum(pca.explained_variance_ratio_[:2])),
            'scores': diagnostics, 'features': features,
            'kmeans': {'random_state': 42, 'n_init': 30, 'space': 'all_standardized_features', 'experiments': experiments,
                       'baseline_k': 2, 'silhouette': experiments[0]['silhouette'], 'cluster_sizes': experiments[0]['cluster_sizes'],
                       'seed_stability': seeds, 'complete_cases': complete_checks, 'without_rehabilitation': without_rehab},
            'seed_stability_provenance': {'role': 'independent_explicit_seed_audit', 'seeds': list(range(10)),
                'author_report_range': [0.905, 1.0], 'author_seed_list_available': False,
                'observed_range': [min(r['adjusted_rand_index'] for r in seeds), max(r['adjusted_rand_index'] for r in seeds)],
                'audit_download': 'downloads/projects/long_active_life/statistical/multivariate_seed_audit_2026_09.csv',
                'legacy_scope_check': 'data/projects/long_active_life/provenance/seed-audit-origin.json',
                'note': 'В авторском отчёте указан диапазон ARI 0,905–1,000, но не перечислены десять начальных состояний. Здесь отдельно выполнен воспроизводимый аудит seed 0–9 при n_init=30. Его диапазон шире; начальные состояния не подбирались ради совпадения. Исходный авторский текст сохранён.'},
            'interpretation': 'Две компоненты сохраняют менее четверти вариации, силуэт близок к нулю. Устойчивая управленческая типология и интегральный рейтинг не подтверждены. Медианные замены существуют только в диагностической копии, исходные пропуски сохранены.',
            'feature_selection': 'Фиксированный сентябрьский срез: не менее 75 пригодных территориальных значений среди 83 авторских территорий; один период, без дополнительных категорий.',
            'reproduction': 'python scripts/build_longlife_analytics.py'}


def build(root=ROOT):
    root = Path(root)
    config = load(root / 'scripts/longlife_emiss_sources.json')
    registry_packet = load(root / DATA / 'indicators.json')
    refresh = load(root / DATA / 'refresh-status.json')
    status = {str(r['source_id']): r for r in refresh.get('sources', [])}
    packets = {s['indicator_id']: load(root / DATA / 'series' / (s['indicator_id'] + '.json')) for s in config['sources']}
    sources = [make_source(contract, packets[contract['indicator_id']], status.get(contract['indicator_id'], {}), root) for contract in config['sources']]
    by_id = {s['id']: s for s in sources}
    rows = [row for packet in packets.values() for row in packet['observations']]
    published_at = max((s['published_at'] for s in sources if s['published_at']), default=None)
    registry = []
    region_count = len(load(root / 'public/data/catalog.json')['regions'])
    for old in registry_packet['items']:
        linked = [by_id[sid] for sid in old['source_ids']]
        evidence = [r for sid in old['source_ids'] for r in packets[sid]['observations']]
        numeric = [r for r in evidence if r['value'] is not None]
        regions = {r['code'] for r in numeric if r['geo_level'] == 'regional'}
        latest_points = []
        for source in linked:
            groups = collections.defaultdict(list)
            for point in source['national']:
                if point['value'] is not None:
                    groups[(point['frequency'], json.dumps(point['category'], sort_keys=True))].append(point)
            for values in groups.values():
                point = latest(values)
                latest_points.append({**point, 'source_title': source['title'], 'source_url': source['source_url'],
                                      'territory_name': point['name'], 'acquired_at': source['published_at'], 'snapshot_id': source['snapshot_id'],
                                      'origin_kind': 'live_emiss', 'observation_key': point.get('source_observation_key') or point['id'],
                                      'analysis_status': 'excluded' if point['excluded'] else 'usable'})
        registry.append({**old, 'source_release_counts': old.get('source_release_counts') or {key: old.get(key) for key in ('n_cells', 'n_numeric', 'n_usable', 'n_domain_violations')},
                         'n_linked_sources': len(linked), 'n_loaded_sources': sum(s['available'] for s in linked), 'n_cells': len(evidence),
                         'n_numeric': len(numeric), 'n_usable': sum(not r['excluded'] for r in numeric),
                         'n_regions': len(regions), 'region_coverage_pct': 100 * len(regions) / region_count,
                         'n_national': sum(r['geo_level'] == 'national' for r in numeric),
                         'n_domain_violations': sum(r['excluded'] for r in numeric),
                         'first_end': min((r['period_end'] for r in numeric), default=''), 'last_end': max((r['period_end'] for r in numeric), default=''),
                         'status': 'numeric_data' if numeric else 'linked_no_numeric' if linked else 'no_table_link', 'latest_national': latest_points})
    coverage = {'indicators_total': len(registry), 'national_indicators': sum(r['indicator_level'] == 'national_project' for r in registry),
                'federal_indicators': sum(r['indicator_level'] != 'national_project' for r in registry), 'known_sources': len(sources),
                'numeric_sources': sum(s['available'] for s in sources), 'indicators_with_numeric': sum(r['n_numeric'] > 0 for r in registry),
                'metadata_only_sources': sum(not s['available'] for s in sources), 'unmapped_indicators': len(config['unmapped_indicators']),
                'observations': len(rows), 'numeric_observations': sum(r['value'] is not None for r in rows),
                'missing_observations': sum(r['value'] is None for r in rows), 'usable_observations': sum(r['analytical_value'] is not None for r in rows),
                'excluded_numeric_observations': sum(r['value'] is not None and r['excluded'] for r in rows),
                'independent_annual_national_facts': sum(r['analytical_value'] is not None for s in sources for r in s['annual']),
                'annual_equivalent_references': 0, 'regional_sources': sum(bool(s['regional_latest']) for s in sources),
                'other_territory_observations': sum(r['geo_level'] == 'other' for r in rows)}
    targets = target_rows(root)
    comparisons = target_comparisons(sources, targets)
    staffing = author_staffing(packets, sources)
    multivariate = author_multivariate(packets, sources, root)
    changes, annual_december, distributions, availability = [], [], [], []
    for source in sources:
        monthly = {r['period']: r for r in source['national'] if r['frequency'] == 'monthly' and r['analytical_value'] is not None and not r['category']}
        for period, point in sorted(monthly.items()):
            previous = monthly.get(str(int(period[:4]) - 1) + period[4:])
            if previous:
                changes.append({'source_id': source['id'], 'title': source['short_title'], 'period': period, 'prior_period': previous['period'],
                                'value': point['value'], 'prior_value': previous['value'], 'change': round(point['value'] - previous['value'], 10),
                                'unit': source['unit'], 'change_unit': difference_unit(source), 'direction': source['direction'],
                                'period_semantics': source['period_semantics'], 'interpretation': 'Разность сопоставимых календарных позиций; не причинный эффект и не доказательство независимости наблюдений.'})
        for annual in source['annual']:
            december = monthly.get(str(annual['year']) + '-12')
            if annual['analytical_value'] is not None and december:
                annual_december.append({'source_id': source['id'], 'title': source['short_title'], 'year': annual['year'],
                                        'annual_value': annual['value'], 'december_value': december['value'],
                                        'difference': round(annual['value'] - december['value'], 10), 'difference_unit': difference_unit(source),
                                        'annual_observation_id': annual['id'], 'december_observation_id': december['id'],
                                        'interpretation': 'Две опубликованные формы периода сохранены самостоятельно; расхождение не объявляется ошибкой одной из них.'})
        if source['regional_latest']:
            exact = source['regional_latest']
            matching = next((r for r in source['national'] if r['period_end'] == source['regional_period_end'] and r['frequency'] == source['regional_frequency'] and r['category'] == source['regional_category']), None)
            distributions.append({'source_id': source['id'], 'title': source['short_title'], 'period_end': source['regional_period_end'],
                                  'frequency': source['regional_frequency'], 'category': source['regional_category'], 'unit': source['display_unit'],
                                  **summary([r for r in exact if r['geographic_comparison_eligible']]),
                                  'national_value': matching['analytical_value'] if matching else None,
                                  'national_value_origin': 'published_national_not_regional_average',
                                  'excluded_geography_count': sum(not r['geographic_comparison_eligible'] for r in exact)})
        groups = collections.defaultdict(list)
        for row in packets[source['id']]['observations']:
            groups[(row['period'], row['frequency'])].append(row)
        for (period, frequency), cells in sorted(groups.items()):
            availability.append({'source_id': source['id'], 'period': period, 'frequency': frequency,
                                 'cells': len(cells), 'numeric': sum(r['value'] is not None for r in cells),
                                 'missing': sum(r['value'] is None for r in cells), 'usable': sum(r['analytical_value'] is not None for r in cells),
                                 'excluded_numeric': sum(r['value'] is not None and r['excluded'] for r in cells)})
    quality_all = [{**{k: r[k] for k in ('id', 'source_id', 'name', 'code', 'period', 'frequency', 'value', 'unit')}, **flag} for r in rows for flag in r['quality_flags']]
    quality_summary = []
    for source in sources:
        flags = [f for f in quality_all if f['source_id'] == source['id']]
        counts = collections.Counter((f['code'], f['severity'], f['exclude_from_analysis']) for f in flags)
        for (code, severity, excluded), count in sorted(counts.items()):
            example = next(f for f in flags if f['code'] == code)
            quality_summary.append({'source_id': source['id'], 'code': code, 'severity': severity, 'exclude_from_analysis': excluded,
                                    'count': count, 'message': example['message']})
    download_names = [('observations', 'Все исходные наблюдения'), ('source_registry', 'Реестр источников'),
                      ('target_comparisons', 'Сопоставления с целями'), ('annual_december_comparisons', 'Годовой и декабрьский факты'),
                      ('same_month_changes', 'Изменения одинаковых месяцев'), ('quality_flags', 'Все оговорки и исключения'),
                      ('availability', 'Календарь доступности'), ('regional_latest', 'Согласованные последние срезы источников'),
                      ('regional_summaries', 'Распределения сопоставимых территорий'), ('author_staffing_2026_07', 'Кадровый срез: июль 2026'),
                      ('multivariate_observed_2026_09', 'Исходная матрица диагностики: сентябрь 2026'),
                      ('multivariate_diagnostic_imputed_2026_09', 'Диагностическая копия с медианными заменами'),
                      ('multivariate_scores_2026_09', 'Координаты исследовательской проекции'), ('multivariate_loadings_2026_09', 'Нагрузки и стандартизация'),
                      ('multivariate_imputed_cells', 'Реестр диагностических замен'),
                      ('multivariate_seed_audit_2026_09', 'Независимая проверка начальных состояний 0–9')]
    statistics = {'schema_version': 1, 'project_id': 'long_active_life', 'published_at': published_at,
                  'statistical_as_of': published_at[:10] if published_at else None, 'last_checked_at': refresh.get('checked_at'),
                  'sources': sources, 'unmapped_indicators': config['unmapped_indicators'],
                  'geography_note': 'Территориальные позиции воспроизводят статистический источник. Охват автономных округов проверяется отдельно; авторские сравнительные совокупности имеют явные исключения.',
                  'history_loading': 'Per-source source.downloads.observations; each packet has source_id and observations[].',
                  'downloads': [{'label': label, 'path': f'downloads/projects/long_active_life/statistical/{name}.csv'} for name, label in download_names]}
    analytics = {'schema_version': 1, 'project_id': 'long_active_life', 'published_at': published_at, 'coverage': coverage,
                 'regional_summaries': distributions, 'regions': [], 'regional_history_deferred': True, 'context': None,
                 'author_staffing': staffing, 'multivariate': multivariate,
                 'same_month_changes': changes, 'annual_december_comparisons': annual_december, 'availability': availability,
                 'quality_flags': quality_summary, 'quality_flags_are_aggregated': True,
                 'excluded_observations': [f for f in quality_all if f['exclude_from_analysis'] and f['value'] is not None],
                 'forecast_eligibility': [forecast_eligibility(s) for s in sources], 'targets': targets, 'target_comparisons': comparisons,
                 'causal': {'identified': False, 'reason': 'Одновременное изменение показателя и реализация мероприятий не идентифицируют эффект; нужны контрфактический дизайн, состав пациентов и предыстория.'},
                 'reproduction': 'python scripts/build_longlife_analytics.py'}
    atomic(root / DATA / 'statistics.json', statistics, compact=True)
    atomic(root / DATA / 'analytics.json', analytics, compact=True)
    atomic(root / DATA / 'context.json', {'schema_version': 1, 'project_id': 'long_active_life', 'kind': 'project_regional_data',
           'external_context': None, 'note': 'Карта и кадровые сопоставления используют собственные ряды проекта. Безработица Кадров и другие внешние наборы не подставляются.',
           'author_staffing': staffing})
    atomic(root / DATA / 'indicators.json', {**registry_packet, 'as_of': published_at[:10] if published_at else None,
           'origin_policy': 'verified_current_longlife_sources; source_specific_domains; original_periods_and_missing_cells_retained', 'items': registry})
    foundation_path = root / DATA / 'foundation.json'
    if foundation_path.exists():
        foundation = load(foundation_path)
        foundation.setdefault('source_release_registry', dict(foundation.get('registry', {})))
        foundation.setdefault('source_release_results', dict(foundation.get('results', {})))
        foundation['registry'].update(n_registry=len(registry), n_with_numeric=coverage['indicators_with_numeric'],
                                     n_with_regional=coverage['regional_sources'], n_unique_cells=len(rows),
                                     n_numeric=coverage['numeric_observations'], n_usable=coverage['usable_observations'],
                                     n_with_national=sum(bool(s['national']) for s in sources),
                                     n_domain_violations=coverage['excluded_numeric_observations'],
                                     coverage_pct=100 * coverage['indicators_with_numeric'] / len(registry))
        series_key = lambda r: (r['source_id'], r['name'], r['frequency'], json.dumps(r['category'], sort_keys=True))
        scenario_ids = {s['id'] for s in sources if not s.get('proxy_only') and any(r['analytical_value'] is not None for r in s['annual'])
                        and any(str(t.get('emiss_id')) == s['id'] and t.get('years', {}).get('2030') is not None for t in targets)}
        foundation['results'].update(n_numeric_indicators=coverage['indicators_with_numeric'], n_regional_indicators=coverage['regional_sources'],
                                    n_forecast_indicators=0, n_projected_series=0, n_diagnostic_forecast_series=0,
                                    n_series=len({series_key(r) for r in rows}), n_reference_scenario_series=len(scenario_ids),
                                    n_series_with_review_flags=len({series_key(r) for r in rows if r['quality_flags']}),
                                    n_annual_facts=coverage['independent_annual_national_facts'], n_annual_equivalent_references=0,
                                    n_documented_target_indicators=len(targets), forecast_status='insufficient_independent_annual_history',
                                    multivariate_status='diagnostic_not_performance_typology')
        foundation['statistical_as_of'] = published_at[:10] if published_at else None
        atomic(foundation_path, foundation)
    methods_path = root / DATA / 'methods.json'
    if methods_path.exists():
        methods = load(methods_path)
        overrides = {
            'source_quality': ('source_specific_domains_verified', 'Все исходные ячейки сохранены. Индексы и приросты проверяются по предметным диапазонам; исключения обычных долей явно отделены от нулей и пропусков.'),
            'observability': ('computed_from_current_source_packets', 'Независимые источники и повторяющиеся позиции каталога различаются. Национальные и региональные охваты пересчитываются из фактических ячеек.'),
            'time_dynamics': ('computed_with_period_contracts', 'Самостоятельные годовые значения, административные месяцы, накопление и перекрывающиеся 12-месячные окна не смешиваются.'),
            'target_comparison': ('computed_with_documented_target_versions', 'Годовой факт сопоставляется с выбранной редакцией плана; отдельные оперативные сравнения не удостоверяют годовое исполнение.'),
            'forecasting': ('insufficient_independent_annual_history', 'Вероятностный прогноз не рассчитан. Условные сценарии имеют самостоятельную годовую базу и явно не являются прогнозом.'),
            'geographical_join': ('verified_source_geography_with_explicit_scopes', 'Официальные обозначения территорий сохранены. Авторские совокупности исключают две областные строки с неоднозначным охватом автономных округов.'),
            'regional_maps': ('computed_matching_source_periods', 'Каждая карта использует один источник, частоту, дату и категорию. Отсутствующие или исключённые значения не подменяются нулями.'),
            'regional_descriptive': ('computed_unweighted_territories', 'Квантили type 7 описывают регионы с одинаковым весом; национальное значение взято из источника и не пересчитано простым средним.'),
            'correlations': ('computed_with_explicit_matching_scope', 'Кадровая корреляция относится к 83 сопоставимым территориям июля 2026 года. Описательная связь не устанавливает взаимозаменяемость ресурсов.'),
            'pca': ('author_matrix_reproduced', 'Матрица 83×29 и пять диагностических медианных замен отделены от фактов. Две компоненты объясняют менее четверти вариации.'),
            'kmeans': ('diagnostic_no_validated_typology', 'Двухгрупповое разбиение имеет низкий силуэт. Группы при k=3…6 нарушают ограничение минимального размера; рейтинг не построен.'),
            'multivariate_stability': ('reproduced_with_independent_explicit_seed_audit', 'Авторские проверки полного наблюдения и исключения реабилитации воспроизведены. Дополнительные seed 0…9 имеют явный список и более широкий ARI; исходный авторский диапазон не заменён.'),
            'isolation_forest': ('not_claimed_in_current_author_analysis', 'Экстремальные наблюдения не объявляются ошибками или искусственной фиксированной долей аномалий.'),
            'moran_global': ('not_claimed_in_current_author_analysis', 'Новая пространственная автокорреляция не заявляется без отдельного выбора и проверки матрицы соседства.'),
            'moran_local': ('not_claimed_in_current_author_analysis', 'Локальные пространственные тесты не подменяют предметный региональный разбор.'),
            'regional_similarity': ('descriptive_profiles_not_integral_ranking', 'Разные болезни, ресурсы и совокупности показаны отдельными профилями; универсальная типология не подтверждена.'),
            'relative_profiles': ('computed_staffing_rf100', 'Для кадрового среза РФ=100 служит общим описательным ориентиром, не нормативом достаточности.'),
            'cohort_projection': ('not_implemented_without_population_inputs', 'Показатели регистра и административного охвата не используются как таблица когортной выживаемости.'),
            'interactive_lab': ('implemented_reproducible_source_calculations', 'Лаборатория повторяет расчёты согласованных срезов, разностей, распределений, описательных корреляций и условных годовых сценариев.'),
        }
        for method in methods['items']:
            if method['method_id'] in overrides:
                method['current_status'], method['current_limitations'] = overrides[method['method_id']]
        documentary_review = root / 'scripts/longlife_documentary_method_status.json'
        if documentary_review.exists():
            reviewed = load(documentary_review)
            for method in methods['items']:
                if method['method_id'] in reviewed:
                    method.update(reviewed[method['method_id']])
        methods['current_review_basis'] = 'source_specific_longlife_statistics_and_author_expertise; source_release status_1_2 retained'
        atomic(methods_path, methods)
    downloads = root / DOWNLOADS
    csv_write(downloads / 'observations.csv', rows)
    csv_write(downloads / 'source_registry.csv', [{k: s.get(k) for k in ('id', 'title', 'short_title', 'unit', 'display_unit', 'source_url', 'indicator_codes', 'direction', 'domain', 'lower_bound', 'upper_bound', 'period_semantics', 'available', 'published_at', 'last_checked_at', 'observation_count', 'numeric_count', 'missing_count', 'usable_count', 'note')} for s in sources])
    csv_write(downloads / 'target_comparisons.csv', comparisons, ['source_id', 'indicator_code', 'target_year', 'target_value', 'fact_value', 'fact_period', 'fact_frequency', 'difference', 'difference_unit', 'direction', 'proxy_only', 'comparison_kind', 'annual_comparison_eligible', 'formal_attainment_eligible', 'target_source', 'interpretation'])
    csv_write(downloads / 'annual_december_comparisons.csv', annual_december)
    csv_write(downloads / 'same_month_changes.csv', changes)
    csv_write(downloads / 'quality_flags.csv', quality_all)
    csv_write(downloads / 'availability.csv', availability)
    csv_write(downloads / 'regional_latest.csv', [r for s in sources for r in s['regional_latest']])
    csv_write(downloads / 'regional_summaries.csv', distributions)
    csv_write(downloads / 'author_staffing_2026_07.csv', staffing['regions'] if staffing else [])
    atomic(root / DATA / 'data-downloads.json', {'schema_version': 1, 'files': download_records(downloads, root / 'public')})
    print(json.dumps(coverage))
    return statistics, analytics


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    build(args.root)
