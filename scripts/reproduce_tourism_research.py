#!/usr/bin/env python3
"""Recalculate a downloaded tourism research JSON without network or dependencies.

Usage: python3 reproduce_tourism_research.py research.json [--output check.json]
Checks internal arithmetic against source_observations. The original source-file
SHA remains a provenance reference; reconstructing its original bytes is outside
this check. Exit 0 = PASS, 1 = disagreement, 2 = unreadable/invalid input.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys

TOLERANCE = Decimal('1e-8')
RECONCILIATION_TOLERANCE = Decimal('1e-6')
ZERO, HUNDRED = Decimal(0), Decimal(100)


def number(value):
    if value is None or isinstance(value, bool) or str(value).strip() == '':
        return None
    try:
        result = Decimal(''.join(str(value).split()).replace(',', '.'))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def region_id(value):
    text = str(value or '').strip()
    return 'RU' if text.upper() == 'RU' else text.zfill(2) if text.isdigit() and len(text) <= 2 else text


def normalize(row):
    national = row.get('geo_level') in ('national', 'russia', 'country') or row.get('is_national') is True or row.get('name', '').startswith('Российская Федерация')
    code = 'RU' if national else region_id(next((row[key] for key in ('map_id', 'region_id', 'code', 'territory_code') if row.get(key) is not None), ''))
    try:
        period = date.fromisoformat(row.get('period_end', ''))
    except (ValueError, TypeError):
        period = None
    excluded = row.get('excluded') is True or any(flag.get('exclude_from_analysis') is True for flag in row.get('quality_flags', []))
    value = number(row.get('analytical_value') if 'analytical_value' in row else row.get('value'))
    if excluded or str(row.get('source_id', '62900')) != '62900' or row.get('frequency') not in (None, '', 'cumulative_ytd') or row.get('category') or (value is not None and value < 0):
        value = None
    regional = row.get('geo_level') == 'regional' and len(code) == 2 and code.isdigit()
    eligible = value is not None and period is not None and (national or (regional and row.get('geographic_comparison_eligible') is not False))
    return {'id': code, 'period': period, 'value': value, 'national': national, 'regional': regional, 'eligible': eligible, 'excluded': excluded}


def calculate(rows, known_regions):
    duplicates = {key for key, count in Counter(row['id'] for row in rows).items() if count > 1}
    admitted = [row for row in rows if row['eligible'] and row['id'] not in duplicates]
    regions = sorted((row for row in admitted if not row['national']), key=lambda row: (-row['value'], row['id']))
    national = next((row['value'] for row in admitted if row['national']), None)
    total = sum((row['value'] for row in regions), ZERO) if regions else None
    residual = national - total if national is not None and total is not None else None
    observed = {row['id'] for row in regions}
    complete = observed == known_regions and not duplicates and national is not None
    status = 'incomplete' if not complete or residual is None else 'matched' if abs(residual) <= RECONCILIATION_TOLERANCE else 'mismatch'
    def share(count):
        return HUNDRED * sum((row['value'] for row in regions[:count]), ZERO) / total if total is not None and total > 0 else None
    return {'total': total, 'nationalValue': national, 'residual': residual,
            'nationalMinusRegions': residual, 'difference': -residual if residual is not None else None,
            'top5Share': share(5), 'top10Share': share(10),
            'hhi': sum(((row['value'] / total) ** 2 for row in regions), ZERO) if total is not None and total > 0 else None,
            'status': status, 'regions': regions}


def verify(bundle):
    errors = []
    def check(label, actual, expected):
        if isinstance(expected, (Decimal, int)) and not isinstance(expected, bool):
            parsed = number(actual)
            equal = parsed is not None and abs(parsed - Decimal(expected)) <= TOLERANCE
        else:
            equal = actual == expected
        if not equal:
            errors.append(f'{label}: found {actual!r}; expected {expected!r}')
    def fields(prefix, actual, expected):
        for key, value in expected.items():
            if key not in actual:
                errors.append(f'{prefix}.{key}: missing field')
            else:
                check(f'{prefix}.{key}', actual[key], value)

    fields('root', bundle, {'schema': 'national-projects.tourism-research/1', 'valid': True, 'indicator': '62900', 'causal_status': 'not_identified'})
    raw = bundle['source_observations']
    if not isinstance(raw, list) or not raw:
        raise ValueError('source_observations must contain the complete nonempty input array')
    rows = [normalize(row) for row in raw]
    periods = defaultdict(list)
    for row in rows:
        if row['period'] is not None:
            periods[row['period'].isoformat()].append(row)
    known_regions = {row['id'] for row in rows if row['regional'] and not row['national']}
    calculated = {period: calculate(group, known_regions) for period, group in sorted(periods.items())}
    settings = bundle['settings']
    period = settings['requestedPeriod']
    check('settings.appliedPeriod', settings.get('appliedPeriod'), period)
    if period not in calculated:
        raise ValueError(f'Requested period {period!r} is unavailable in source observations')
    current = calculated[period]
    selected = bundle['slice']
    fields('slice', selected, {key: current[key] for key in ('total', 'nationalValue', 'residual', 'nationalMinusRegions', 'difference', 'top5Share', 'top10Share', 'hhi')})
    fields('slice', selected, {'available': True, 'period': period, 'requestedPeriod': period})
    check('slice.reconciliation.status', selected.get('reconciliation', {}).get('status'), current['status'])
    expected_regions = {row['id']: row['value'] for row in current['regions']}
    for field in ('regions', 'ranked'):
        actual_rows = selected[field]
        check(f'slice.{field}.count', len(actual_rows), len(expected_regions))
        check(f'slice.{field}.territories', sorted(row['regionId'] for row in actual_rows), sorted(expected_regions))
        for row in actual_rows:
            check(f'slice.{field}.{row["regionId"]}.value', row.get('value'), expected_regions.get(row['regionId']))
    check('slice.coverage.observed', selected.get('coverage', {}).get('observed'), len(expected_regions))
    check('slice.coverage.expected', selected.get('coverage', {}).get('expected'), len(known_regions))

    quality = bundle['quality']
    expected_counts = {'observationCount': len(rows), 'regionCount': len(known_regions),
                       'eligibleCount': sum(row['eligible'] for row in rows), 'nationalCount': sum(row['national'] for row in rows),
                       'excludedCount': sum(row['excluded'] for row in rows), 'missingCount': sum(row['value'] is None and not row['excluded'] for row in rows),
                       'mismatchCount': sum(item['status'] == 'mismatch' for item in calculated.values()),
                       'matchingCount': sum(item['status'] == 'matched' for item in calculated.values()),
                       'incompleteCount': sum(item['status'] == 'incomplete' for item in calculated.values())}
    fields('quality', quality, expected_counts)
    check('quality.periods', [item['period'] for item in quality['periods']], list(calculated))
    for item in quality['periods']:
        expected = calculated.get(item['period'])
        if expected is None:
            continue
        fields(f'quality.{item["period"]}', item,
               {'regionalSum': expected['total'], 'regional_sum': expected['total'], 'nationalValue': expected['nationalValue'],
                'national_value': expected['nationalValue'], 'residual': expected['residual'], 'difference': expected['difference'],
                'regions': len(expected['regions']), 'equal': expected['status'] == 'matched', 'status': expected['status']})

    selected_ids = {'RU', *(region_id(item) for item in settings['regions'])}
    groups = defaultdict(list)
    for row in rows:
        if row['id'] in selected_ids and row['period'] is not None:
            groups[(row['id'], row['period'].year)].append(row)
    lines = bundle['trajectories']
    actual_keys = [(line['regionId'], int(line['year'])) for line in lines]
    check('trajectory keys', sorted(actual_keys), sorted(groups))
    point_count = 0
    for line, key in zip(lines, actual_keys):
        group = groups.get(key)
        if not group:
            continue
        months = defaultdict(list)
        for row in group:
            months[row['period'].month].append(row)
        last = max(months)
        expected = [months[month][0]['value'] if len(months[month]) == 1 and months[month][0]['eligible'] else None for month in range(1, last + 1)]
        check(f'trajectory {key} months', [point['month'] for point in line['points']], list(range(1, last + 1)))
        for index, point in enumerate(line['points'][:last]):
            check(f'trajectory {key} month {index + 1}', point.get('value'), expected[index])
            point_count += 1
        fields(f'trajectory {key}', line, {'complete': len([value for value in expected if value is not None]) == 12,
                                         'calendarYearComplete': len([value for value in expected if value is not None]) == 12,
                                         'comparisonStatus': 'requires_edition_review', 'frequency': 'cumulative_ytd'})

    return {'status': 'FAIL' if errors else 'PASS', 'period': period, 'observations': len(rows),
            'regions': len(expected_regions), 'periods_checked': len(calculated), 'trajectory_points_checked': point_count,
            'regional_sum': current['total'], 'national_value': current['nationalValue'], 'residual': current['residual'],
            'top5_share_pct': current['top5Share'], 'top10_share_pct': current['top10Share'],
            'mismatches': expected_counts['mismatchCount'], 'tolerance': TOLERANCE, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('research_json', type=Path)
    parser.add_argument('--output', type=Path, help='Write the verification summary as JSON')
    args = parser.parse_args()
    try:
        with args.research_json.open(encoding='utf-8-sig') as stream:
            bundle = json.load(stream, parse_float=Decimal)
        summary = verify(bundle)
        exit_code = 0 if summary['status'] == 'PASS' else 1
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        summary = {'status': 'FAIL', 'errors': [str(error)]}
        exit_code = 2
    text = json.dumps(summary, ensure_ascii=False, indent=2, default=lambda value: float(value) if isinstance(value, Decimal) else str(value))
    if args.output:
        try:
            args.output.write_text(text + '\n', encoding='utf-8')
        except OSError as error:
            print(f'FAIL: cannot write {args.output}: {error}', file=sys.stderr)
            return 2
    print(text)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
