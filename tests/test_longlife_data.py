"""Real-source replay, measurement semantics and safe Longlife refresh."""
import copy
import csv
import gzip
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from emiss_adapter.errors import EmissConnectorError
from emiss_adapter.metadata import parse_indicator_metadata
from emiss_adapter.client import query_plan
from emiss_adapter.sdmx import parse_sdmx
from longlife_formats import parse_excel, parse_grid, axis_mapping
from longlife_data import ROOT, DATA, DOWNLOADS, load, atomic, source_rules, normalize_payload, normalize_record, region_aliases, merge_observations
from build_longlife_analytics import latest, forecast_eligibility, validate_target_unit, difference_unit, make_source, author_staffing, author_multivariate
from refresh_longlife_emiss import LonglifeClient, run, normalized_live


class LonglifeEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load(ROOT / 'scripts/longlife_emiss_sources.json')
        cls.aliases = region_aliases(ROOT)
        cls.regions = {str(r['id']): r for r in load(ROOT / 'public/data/catalog.json')['regions']}
        cls.inputs, cls.packets = {}, {}
        for contract in cls.config['sources']:
            sid = contract['indicator_id']
            with zipfile.ZipFile(ROOT / DOWNLOADS / 'emiss_inputs' / (sid + '.zip')) as archive:
                payload = json.loads(archive.read('input.json'))
                for entry in payload['evidence_files']:
                    body = archive.read(entry['archive_path'])
                    assert len(body) == entry['bytes'] and hashlib.sha256(body).hexdigest() == entry['sha256']
                for entry in json.loads(payload['snapshot']['raw_manifest_json']):
                    relative = '/'.join(p for p in entry['path'].replace('\\', '/').split('/') if p)
                    body = archive.read('source/' + relative)
                    if relative.endswith('.gz'):
                        body = gzip.decompress(body)
                    assert hashlib.sha256(body).hexdigest() == entry['sha256']
            cls.inputs[sid] = payload
            cls.packets[sid] = normalize_payload(payload, cls.aliases, cls.regions)
        cls.rows = [r for p in cls.packets.values() for r in p['observations']]

    def test_all_input_cells_numbers_missing_and_source_identity_survive(self):
        self.assertEqual((len(self.packets), len(self.rows)), (42, 61029))
        self.assertEqual(sum(r['value'] is not None for r in self.rows), 57391)
        self.assertEqual(sum(r['value'] is None for r in self.rows), 3638)
        self.assertEqual(sum(r['analytical_value'] is not None for r in self.rows), 57337)
        for sid, packet in self.packets.items():
            original = {r['observation_key']: r for r in self.inputs[sid]['observations']}
            for row in packet['observations']:
                evidence = original[row['source_observation_key']]
                self.assertEqual((row['value'], row['unit'], row['source_period_start'], row['source_period_end']),
                                 (evidence['value_numeric'], evidence['unit'], evidence['period_start'], evidence['period_end']))

    def test_all_42_real_official_exports_replay_the_same_61029_cells(self):
        count = 0
        formats = set()
        for sid, payload in self.inputs.items():
            with self.subTest(source=sid), zipfile.ZipFile(ROOT / DOWNLOADS / 'emiss_inputs' / (sid + '.zip')) as archive:
                contract = payload['config']
                formats.add(contract['export_format'])
                meta = parse_indicator_metadata(archive.read('source/' + payload['metadata_source']).decode(), sid)
                roles, _ = query_plan(meta, contract)
                actual = []
                for entry in json.loads(payload['snapshot']['raw_manifest_json']):
                    if not entry.get('query_file'):
                        continue
                    name = '/'.join(p for p in entry['path'].replace('\\', '/').split('/') if p)
                    qname = '/'.join(p for p in entry['query_file'].replace('\\', '/').split('/') if p)
                    selected = json.loads(archive.read('source/' + qname))['selected']
                    body = archive.read('source/' + name)
                    if name.endswith('.gz'):
                        body = gzip.decompress(body)
                    parsed, _ = parse_excel(body, meta, selected) if name.endswith('.xls') else parse_grid(body, meta, selected) if name.endswith('.json.gz') else parse_sdmx(body)
                    actual.extend(normalized_live(parsed, meta, roles, selected, contract, self.aliases, '2026-10-29T00:00:00Z', self.regions))
                expected = self.packets[sid]['observations']
                key = lambda r: (r['id'], r['value'], r['unit'], r['excluded'])
                self.assertEqual({key(r) for r in actual}, {key(r) for r in expected})
                self.assertEqual(len(actual), len(expected))
                count += len(actual)
        self.assertEqual(count, 61029)
        self.assertEqual(formats, {'sdmx', 'excel', 'grid'})

    def test_geography_is_not_an_extra_measure_category(self):
        self.assertTrue(all(r['category'] == {} for r in self.rows))
        row = next(r for r in self.packets['62926']['observations'] if r['geo_level'] == 'regional')
        self.assertIn('ОКАТО (межведомственный)', row['source_geography_dimensions'])
        self.assertIn(row['code'], self.regions)
        self.assertEqual(row['fd'], self.regions[row['code']]['federal_district'])

    def test_index_capacity_and_growth_are_not_clipped_to_0_100(self):
        for sid in ('63006', '62926', '62950', '62955'):
            outlying = [r for r in self.packets[sid]['observations'] if r['value'] is not None and (r['value'] < 0 or r['value'] > 100)]
            self.assertTrue(outlying)
            self.assertTrue(all(not r['excluded'] and r['analytical_value'] == r['value'] for r in outlying))
        eao = next(r for r in self.packets['62955']['observations'] if r['code'] == '79' and r['period'] == '2026-09')
        self.assertEqual(eao['analytical_value'], 1084.5)

    def test_bounded_share_violations_preserve_original_numbers(self):
        excluded = [r for r in self.rows if r['value'] is not None and r['excluded']]
        self.assertEqual(len(excluded), 54)
        self.assertTrue(all(r['analytical_value'] is None and r['value'] > 100 for r in excluded))
        self.assertEqual({r['source_id'] for r in excluded}, {'62941', '62940', '62930', '62943', '62965', '62914'})

    def test_zero_and_missing_are_distinct(self):
        zero = next(r for r in self.rows if r['value'] == 0)
        missing = next(r for r in self.rows if r['value'] is None)
        self.assertEqual(zero['analytical_value'], 0)
        self.assertFalse(zero['excluded'])
        self.assertEqual(missing['status'], 'missing')
        self.assertIsNone(missing['analytical_value'])

    def test_ten_independent_national_annual_numbers_no_december_substitution(self):
        annual = [r for r in self.rows if r['geo_level'] == 'national' and r['frequency'] == 'annual']
        self.assertEqual((len(annual), sum(r['value'] is not None for r in annual)), (11, 10))
        self.assertIsNone(next(r['value'] for r in annual if r['source_id'] == '62950'))
        self.assertTrue(all(s.get('annual_equivalence') is None for s in self.config['sources']))

    def test_diabetes_annual_and_december_have_distinct_published_values(self):
        for sid, yearly, december in [('62957', 70.8, 40.4), ('62959', 81.0, 97.8)]:
            rows = [r for r in self.packets[sid]['observations'] if r['geo_level'] == 'national']
            annual = next(r for r in rows if r['period'] == '2025')
            monthly = next(r for r in rows if r['period'] == '2025-12')
            self.assertEqual((annual['value'], monthly['value']), (yearly, december))
            self.assertNotEqual(annual['id'], monthly['id'])

    def test_late_oncology_missing_values_do_not_extend_march_fact(self):
        rows = [r for r in self.packets['62945']['observations'] if r['geo_level'] == 'national']
        point = latest(rows)
        self.assertEqual((point['period'], point['value']), ('2026-03', 67.6))
        self.assertTrue(all(r['value'] is None for r in rows if r['period_end'] > point['period_end']))

    def test_alcohol_window_overlaps_twelve_months_and_original_month_is_retained(self):
        point = next(r for r in self.packets['63005']['observations'] if r['geo_level'] == 'national' and r['period'] == '2026-09')
        self.assertEqual((point['value'], point['period_start'], point['measurement_window_start'], point['measurement_window_end']),
                         (7.47, '2026-09-01', '2025-10-01', '2026-09-30'))
        self.assertEqual(point['period_semantics'], 'rolling_12_months')

    def test_ytd_index_and_staff_stock_have_distinct_windows_and_units(self):
        point = next(r for r in self.packets['63006']['observations'] if r['geo_level'] == 'national' and r['period'] == '2026-09')
        self.assertEqual((point['value'], point['measurement_window_start']), (85.1, '2026-01-01'))
        source = next(s for s in self.config['sources'] if s['indicator_id'] == '62971')
        self.assertEqual(source['unit'], 'человек')
        self.assertEqual(source['display_unit'], 'человек на 10 тыс. населения')
        self.assertIsNone(source['upper_bound'])

    def test_proxy_count_never_compares_to_a_percent_target(self):
        config = next(s for s in self.config['sources'] if s['indicator_id'] == '63151')
        self.assertTrue(config['proxy_only'])
        validate_target_unit({'id': '63151', **config}, {'unit': 'Человек'})
        with self.assertRaises(ValueError):
            validate_target_unit({'id': '63151', **config}, {'unit': '%'})

    def test_staffing_scope_reproduces_author_groups_and_independent_statistics(self):
        sources = [make_source(s, self.packets[s['indicator_id']], {}, ROOT) for s in self.config['sources']]
        staffing = author_staffing(self.packets, sources)
        self.assertEqual(staffing['n'], 83)
        self.assertEqual(staffing['group_counts'], {'both_below': 23, 'doctors_below_only': 23, 'nurses_below_only': 5, 'both_at_or_above': 32})
        self.assertAlmostEqual(staffing['spearman'], .5555526402863961)
        doctors = sorted(r['doctors'] for r in staffing['regions'])
        self.assertEqual(staffing['summary']['doctors']['median'], doctors[41])
        self.assertAlmostEqual(staffing['summary']['doctors']['q1'], (doctors[20] + doctors[21]) / 2)
        self.assertNotAlmostEqual(sum(doctors) / len(doctors), staffing['national']['doctors'])
        self.assertEqual(staffing['national'], {'doctors': 43.54, 'nurses': 86.1})

    def test_diagnostic_matrix_reproduces_pca_without_modifying_missing_facts(self):
        sources = [make_source(s, self.packets[s['indicator_id']], {}, ROOT) for s in self.config['sources']]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            atomic(root / 'public/data/catalog.json', load(ROOT / 'public/data/catalog.json'))
            result = author_multivariate(self.packets, sources, root)
            self.assertEqual((result['n_regions'], result['n_features'], result['imputed_count']), (83, 29, 5))
            self.assertAlmostEqual(result['explained_variance_ratio'][0], .15454722, places=7)
            self.assertAlmostEqual(result['explained_variance_ratio'][1], .08834015, places=7)
            self.assertEqual(result['kmeans']['cluster_sizes'], [43, 40])
            self.assertAlmostEqual(result['kmeans']['silhouette'], .06671967330356121)
            self.assertEqual(result['kmeans']['complete_cases'][0]['cluster_sizes'], [81, 1])
            self.assertEqual(result['kmeans']['complete_cases'][0]['singleton_codes'], ['79'])
            with (root / DOWNLOADS / 'multivariate_diagnostic_imputed_2026_09.csv').open(encoding='utf-8-sig', newline='') as file:
                rows = list(csv.DictReader(file))
            values = np.array([[float(r[sid]) for sid in result['source_ids']] for r in rows])
            standardized = (values - values.mean(axis=0)) / values.std(axis=0, ddof=0)
            eigenvalues = np.linalg.eigvalsh(standardized.T @ standardized)[::-1]
            ratio = eigenvalues / eigenvalues.sum()
            self.assertTrue(np.allclose(result['explained_variance_ratio'], ratio, atol=1e-12))
            for missing in result['missing_cells']:
                original = next(r for r in self.packets[missing['source_id']]['observations'] if r['code'] == missing['code'] and r['period'] == '2026-09')
                self.assertIsNone(original['value'])
                self.assertIsNone(original['analytical_value'])
            seed = result['seed_stability_provenance']
            self.assertEqual(seed['seeds'], list(range(10)))
            self.assertAlmostEqual(seed['observed_range'][0], -.0016820150540347335)
            self.assertFalse(seed['author_seed_list_available'])

    def test_multiple_months_do_not_become_independent_annual_years(self):
        source = {'id': 'fixture', 'short_title': 'fixture', 'annual': [{'year': 2025, 'analytical_value': 1, 'category': {}}] * 30}
        self.assertEqual(forecast_eligibility(source)['distinct_annual_years'], 1)
        self.assertFalse(forecast_eligibility(source)['eligible'])

    def test_conflicting_duplicate_and_unit_change_are_rejected(self):
        row = self.packets['62971']['observations'][0]
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            merge_observations([], [row, {**row, 'value': 999}])
        with self.assertRaisesRegex(ValueError, 'Historical unit'):
            merge_observations([row], [{**row, 'unit': '%'}])

    def test_missing_update_keeps_number_and_real_revision_records_before_after(self):
        row = next(r for r in self.packets['62971']['observations'] if r['value'] is not None)
        values, count, revisions = merge_observations([row], [{**row, 'value': None, 'analytical_value': None}])
        self.assertEqual(values[0]['value'], row['value'])
        self.assertEqual((count, revisions), (0, []))
        values, count, revisions = merge_observations([row], [{**row, 'value': row['value'] + 1}])
        self.assertEqual(revisions[0]['new_value'] - revisions[0]['old_value'], 1)

    def test_truncated_grid_and_ambiguous_excel_axes_fail(self):
        with self.assertRaises(EmissConnectorError) as error:
            parse_grid(json.dumps({'__count': 2, 'results': [{}]}).encode(), {}, {})
        self.assertEqual(error.exception.category, 'grid_truncated')
        fields = [{'field_id': '1', 'title': 'one'}, {'field_id': '2', 'title': 'two'}]
        selected = {key: [{'id': 'a', 'title': 'A'}, {'id': 'b', 'title': 'B'}] for key in ('1', '2')}
        with self.assertRaises(EmissConnectorError) as error:
            axis_mapping([{'a', 'b'}, {'a', 'b'}], fields, selected)
        self.assertEqual(error.exception.category, 'excel_axis_ambiguous')

    def test_published_summary_and_exports_are_derived_from_current_packets(self):
        stats = load(ROOT / DATA / 'statistics.json')
        total = 0
        for source in stats['sources']:
            packet = load(ROOT / DATA / 'series' / (source['id'] + '.json'))
            by_key = {r['id']: r for r in packet['observations']}
            self.assertEqual(source['observation_count'], len(by_key))
            self.assertEqual(source['numeric_count'], sum(r['value'] is not None for r in by_key.values()))
            total += len(by_key)
            for point in source['national'] + source['regional_latest']:
                for key in ('source_id', 'name', 'period', 'frequency', 'category', 'value', 'analytical_value', 'excluded'):
                    self.assertEqual(point[key], by_key[point['id']][key])
            self.assertEqual(source['regional_history'], [])
            self.assertTrue(source['regional_history_deferred'])
            if source['regional_latest']:
                self.assertEqual(len({(r['frequency'], r['period_end'], json.dumps(r['category'])) for r in source['regional_latest']}), 1)
        with (ROOT / DOWNLOADS / 'observations.csv').open(encoding='utf-8-sig', newline='') as file:
            self.assertEqual(sum(1 for _ in csv.DictReader(file)), total)
        self.assertLess((ROOT / DATA / 'statistics.json').stat().st_size, 3 * 1024 * 1024)

    def test_target_comparison_preserves_period_direction_and_proxy(self):
        analytics = load(ROOT / DATA / 'analytics.json')
        facts = {r['id']: r for s in load(ROOT / DATA / 'statistics.json')['sources'] for r in s['national']}
        for item in analytics['target_comparisons']:
            fact = facts[item['reference_observation_id']]
            self.assertEqual(item['fact_value'], fact['value'])
            self.assertEqual(item['annual_comparison_eligible'], fact['frequency'] == 'annual')
            self.assertFalse(item['formal_attainment_eligible'])
            self.assertAlmostEqual(item['difference'], fact['value'] - item['target_value'])
            if item['source_id'] == '63151':
                self.assertTrue(item['proxy_only'])
                self.assertEqual(item['target_value'], 27190769)



TITLE = 'Синтетический показатель для проверки'
HTML = '''<html><span class="sp_txt">Синтетический показатель для проверки</span><div id="methodologyFull">Проверенная методика.</div><div>Единицы измерения</div><ul><li>процент</li></ul><script>window.fixture={filters:{0:{title:'Показатель',values:{999:{title:'Синтетический показатель для проверки'}}},1:{title:'ОКАТО',values:{77:{title:'Москва'}}},2:{title:'Год',values:{2025:{title:'2025'}}},3:{title:'Период',values:{0:{title:'значение показателя за год'}}},4:{title:'Единица измерения',values:{u:{title:'процент'}}}},left_columns:[1],top_columns:[2,3],groups:[4]};</script></html>'''
META = parse_indicator_metadata(HTML, '999')
SOURCE = {'source_id': '999', 'indicator_id': '999', 'title': TITLE, 'titles': [TITLE], 'unit': 'процент', 'methodology': 'Проверенная методика.', 'source_url': 'https://www.fedstat.ru/indicator/999', 'first_year': 2025, 'min_regional_count': 1, 'dimension_defaults': {}, 'field_overrides': {}, 'expected_period_types': ['год', 'месяц']}
SOURCE.update(source_rules('999', TITLE, 'процент'))
CONFIG = {'base_url': 'https://www.fedstat.ru', 'allowed_hosts': ['www.fedstat.ru', 'fedstat.ru'], 'max_cells': 1000, 'min_interval_seconds': 0, 'timeout_seconds': 1, 'retries': 0, 'failure_circuit_breaker': 3, 'sources': [SOURCE], 'unmapped_indicators': []}


def fixture_xml(value='12.3'):
    return ('<GenericData><DataSet><Series><SeriesKey><Value concept="1" value="77"/><Value concept="2" value="2025"/><Value concept="3" value="0"/><Value concept="4" value="u"/></SeriesKey><Obs><Time>2025</Time><ObsValue value="' + value + '"/></Obs></Series></DataSet></GenericData>').encode()


class RefreshSafety(unittest.TestCase):
    def fixture_root(self, path, n=1):
        config = copy.deepcopy(CONFIG)
        config['sources'] = [{**SOURCE, 'source_id': str(999 + i), 'indicator_id': str(999 + i)} for i in range(n)]
        atomic(path / 'scripts/longlife_emiss_sources.json', config)
        atomic(path / 'public/data/catalog.json', {'regions': [{'id': '77', 'name': 'Москва'}], 'datasets': []})
        statuses = []
        for source in config['sources']:
            sid = source['indicator_id']
            row = normalize_record({'source_id': sid, 'unit': 'процент', 'period_kind': 'annual', 'period_start': '2025-01-01', 'period_end': '2025-12-31', 'year': 2025, 'territory_name': 'Москва', 'value_numeric': 10, 'value_raw': '10', 'dimensions_json': '{}'}, source, {'москва': '77'})
            atomic(path / DATA / 'series' / (sid + '.json'), {'source_id': sid, 'unit': 'процент', 'published_at': '2026-01-15T00:00:00Z', 'observations': [row]})
            atomic(path / DATA / 'provenance' / (sid + '.json'), {'source_id': sid})
            statuses.append({'source_id': sid, 'state': 'updated', 'published_at': '2026-01-15T00:00:00Z', 'last_success': '2026-01-15T00:00:00Z', 'checked_at': '2026-01-15T00:00:00Z'})
        atomic(path / DATA / 'refresh-status.json', {'published_at': '2026-01-15T00:00:00Z', 'last_success': '2026-01-15T00:00:00Z', 'statistical_as_of': '2026-01-15', 'sources': statuses})
        return config

    def test_good_refresh_then_outage_preserves_published_data(self):
        class Fake:
            failed = False
            def metadata(self, sid):
                if self.failed:
                    raise EmissConnectorError('Synthetic outage', category='network_error')
                return META
            def export(self, m, s):
                body = fixture_xml()
                parsed, structure = parse_sdmx(body)
                return parsed, structure, hashlib.sha256(body).hexdigest(), body
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture_root(root)
            client = Fake()
            good = run(root, client=client, rebuild=False)
            self.assertEqual(good['state'], 'updated')
            self.assertEqual(good['sources'][0]['revisions'], 1)
            path = root / DATA / 'series/999.json'
            data = path.read_bytes()
            contract = {**SOURCE, 'short_title': TITLE, 'indicator_codes': ['fixture'], 'indicator_level': 'national_project',
                        'federal_project_name': '', 'cumulative': 'stock', 'annual_reset': False, 'note': '', 'periodicity': 'Годовая'}
            source = make_source(contract, load(path), good['sources'][0], root)
            self.assertEqual(source['downloads']['current_raw'], 'downloads/projects/long_active_life/statistical/emiss_current/999.zip')
            self.assertEqual(source['downloads']['source_input'], 'downloads/projects/long_active_life/statistical/emiss_inputs/999.zip')
            client.failed = True
            bad = run(root, client=client, rebuild=False)
            self.assertEqual(bad['state'], 'failed')
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(bad['last_success'], good['last_success'])
            self.assertEqual(bad['published_at'], good['published_at'])
            retained = make_source(contract, load(path), bad['sources'][0], root)
            self.assertEqual(retained['downloads'], source['downloads'])
            raw = root / 'public' / retained['downloads']['current_raw']
            raw.write_bytes(raw.read_bytes() + b'corrupt')
            with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
                make_source(contract, load(path), bad['sources'][0], root)

    def test_circuit_breaker_records_unchecked_sources_truthfully(self):
        class Offline:
            calls = 0
            def metadata(self, sid):
                self.calls += 1
                raise EmissConnectorError('Synthetic outage', category='network_error')
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture_root(root, 4)
            before = {p: p.read_bytes() for p in (root / DATA / 'series').glob('*.json')}
            client = Offline()
            result = run(root, client=client, rebuild=False)
            self.assertEqual((client.calls, result['attempted_sources'], result['deferred_sources']), (3, 3, 1))
            self.assertEqual(result['sources'][-1]['checked_at'], '2026-01-15T00:00:00Z')
            self.assertEqual(result['sources'][-1]['state'], 'deferred_after_source_outage')
            self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))

    def test_unknown_source_does_not_start_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture_root(root)
            with self.assertRaisesRegex(ValueError, 'Unknown confirmed'):
                run(root, only='12345', rebuild=False)

    def test_metadata_method_revision_rejected(self):
        client = LonglifeClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace('Проверенная методика.', 'Новая методика.'))))
        try:
            with self.assertRaises(EmissConnectorError) as result:
                client.metadata('999')
            self.assertEqual(result.exception.category, 'methodology_contract_changed')
        finally:
            client.close()

    def test_metadata_unit_revision_rejected(self):
        client = LonglifeClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace('<li>процент</li>', '<li>единица</li>'))))
        try:
            with self.assertRaises(EmissConnectorError) as result:
                client.metadata('999')
            self.assertEqual(result.exception.category, 'unit_mismatch')
        finally:
            client.close()

    def test_empty_grid_is_distinguished_from_failure(self):
        no_grid = HTML.split('<script>')[0] + '</html>'
        client = LonglifeClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=no_grid)))
        try:
            meta = client.metadata('999')
            self.assertTrue(meta['no_numeric_grid'])
            self.assertEqual(meta['unit'], 'процент')
        finally:
            client.close()

    def test_metadata_only_check_does_not_advance_data_date(self):
        class Empty:
            def metadata(self, sid):
                return {'indicator_id': sid, 'no_numeric_grid': True}
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture_root(root)
            path = root / DATA / 'series/999.json'
            before = path.read_bytes()
            result = run(root, client=Empty(), rebuild=False)
            self.assertEqual(result['sources'][0]['state'], 'metadata_only')
            self.assertEqual(result['published_sources'], 0)
            self.assertEqual(result['published_at'], '2026-01-15T00:00:00Z')
            self.assertEqual(path.read_bytes(), before)

    def test_unknown_period_label_does_not_guess_month(self):
        meta = copy.deepcopy(META)
        next(f for f in meta['filters'] if f['field_id'] == '3')['values'][0]['title'] = 'неизвестный период'
        roles, selected = query_plan(meta, SOURCE)
        parsed, _ = parse_sdmx(fixture_xml())
        with self.assertRaises(EmissConnectorError) as result:
            normalized_live(parsed, meta, roles, selected, SOURCE, {'москва': '77'}, '2026-10-29T00:00:00Z')
        self.assertEqual(result.exception.category, 'ambiguous_period')

    def test_future_numerical_period_is_rejected(self):
        meta = copy.deepcopy(META)
        next(f for f in meta['filters'] if f['field_id'] == '2')['values'][0] = {'id': '2027', 'title': '2027'}
        roles, selected = query_plan(meta, SOURCE)
        parsed, _ = parse_sdmx(fixture_xml().replace(b'value="2025"', b'value="2027"').replace(b'>2025<', b'>2027<'))
        with self.assertRaises(EmissConnectorError) as result:
            normalized_live(parsed, meta, roles, selected, SOURCE, {'москва': '77'}, '2026-10-29T00:00:00Z')
        self.assertEqual(result.exception.category, 'future_observation')



if __name__ == '__main__':
    unittest.main()
