"""Personnel evidence, annual equivalence, context isolation and refresh safety."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import httpx
from emiss_adapter.errors import EmissConnectorError
from emiss_adapter.metadata import parse_indicator_metadata
from emiss_adapter.client import query_plan
from emiss_adapter.sdmx import parse_sdmx
from personnel_data import ROOT, DATA, DOWNLOADS, load, atomic, normalize_payload, normalize_record, region_aliases, merge_observations, annual_equivalents, series_flags, build_context
from build_personnel_analytics import latest, forecast_eligibility, validate_target_unit, difference_unit, make_source
from refresh_personnel_emiss import PersonnelClient, run, normalized_live


class PersonnelEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aliases = region_aliases(ROOT)
        cls.config = load(ROOT / 'scripts/personnel_emiss_sources.json')
        cls.inputs, cls.packets = {}, {}
        for source in cls.config['sources']:
            sid = source['indicator_id']
            with zipfile.ZipFile(ROOT / DOWNLOADS / 'emiss_inputs' / (sid + '.zip')) as archive:
                payload = json.loads(archive.read('input.json'))
                for entry in json.loads(payload['snapshot']['raw_manifest_json']) if payload['snapshot'] else []:
                    relative = '/'.join(p for p in entry['path'].replace('\\', '/').split('/') if p)
                    body = archive.read('source/' + relative)
                    if relative.endswith('.gz'):
                        body = gzip.decompress(body)
                    assert hashlib.sha256(body).hexdigest() == entry['sha256']
            cls.inputs[sid] = payload
            cls.packets[sid] = normalize_payload(payload, cls.aliases)

    def test_nine_source_packets_replay_all_sixty_values_and_original_periods(self):
        count = 0
        for sid, packet in self.packets.items():
            original = {r['observation_key']: r for r in self.inputs[sid]['observations']}
            for row in packet['observations']:
                evidence = original[row['source_observation_key']]
                self.assertEqual(row['value'], evidence['value_numeric'])
                self.assertEqual(row['unit'], evidence['unit'])
                self.assertEqual(row['source_period_start'], evidence['period_start'])
                self.assertEqual(row['source_period_end'], evidence['period_end'])
                self.assertFalse(row['excluded'])
                count += 1
        self.assertEqual(len(self.packets), 9)
        self.assertEqual(count, 60)

    def test_four_metadata_sources_and_two_unmapped_indicators_have_no_invented_values(self):
        self.assertEqual(sum(not p['observations'] for p in self.packets.values()), 4)
        self.assertEqual(len(self.config['unmapped_indicators']), 2)
        self.assertTrue(all(p['published_at'] is None for p in self.packets.values() if not p['observations']))

    def test_two_independent_annual_facts_and_three_references_do_not_create_cells(self):
        rows = [r for p in self.packets.values() for r in p['observations']]
        annual = [r for r in rows if r['frequency'] == 'annual']
        self.assertEqual(sorted((r['source_id'], r['value']) for r in annual), [('62884', 101.7), ('62907', 81.3)])
        eq = [r for sid, p in self.packets.items() for r in annual_equivalents(sid, p['observations'])]
        self.assertEqual(sorted((r['source_id'], r['value']) for r in eq), [('63038', 112.89), ('63238', 72), ('63363', .1766)])
        self.assertTrue(all(r['id'] in {point['id'] for point in rows} for r in eq))
        self.assertTrue(all(r['independent_observation'] is False for r in eq))
        self.assertEqual(len({r['id'] for r in rows}), 60)

    def test_plan_ratio_and_index_allow_above_one_hundred(self):
        for sid, value in [('63038', 112.89), ('62884', 101.7)]:
            row = next(r for r in self.packets[sid]['observations'] if r['value'] == value)
            self.assertFalse(row['excluded'])
            self.assertEqual(row['analytical_value'], value)
        source = self.inputs['62907']['config']
        row = {**self.inputs['62907']['observations'][0], 'value_numeric': 101}
        self.assertTrue(normalize_record(row, source, self.aliases)['excluded'])

    def test_prior_analytical_exclusion_is_separate_from_unchanged_raw_source(self):
        review = load(ROOT / DATA / 'provenance/analytical-review.json')
        body = (ROOT / 'public' / review['source_file']).read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), review['source_sha256'])
        old = review['original_record']
        self.assertEqual(old, next(r for r in json.loads(body) if r['observation_key'] == old['observation_key']))
        self.assertEqual((old['value'], old['analysis_status'], old['domain_violation']), (112.89, 'domain_violation', 1))
        raw = next(r for r in self.inputs['63038']['observations'] if r['observation_key'] == old['observation_key'])
        self.assertEqual((raw['value_numeric'], raw['value_status']), (112.89, 'ok'))
        current = next(r for r in self.packets['63038']['observations'] if r['source_observation_key'] == old['observation_key'])
        self.assertEqual((current['analytical_value'], current['excluded']), (112.89, False))

    def test_zeros_preserved_with_component_caution_not_turned_into_missing(self):
        zeros = [r for r in self.packets['62907']['observations'] if r['value'] == 0]
        self.assertEqual(len(zeros), 7)
        self.assertTrue(all(r['analytical_value'] == 0 and not r['excluded'] for r in zeros))
        self.assertTrue(all(any(f['code'] == 'zero_denominator_components_unavailable' for f in r['quality_flags']) for r in zeros))

    def test_month_labels_for_survey_become_reviewed_quarters_without_averaging(self):
        rows = self.packets['63238']['observations']
        self.assertEqual([(r['period'], r['value']) for r in rows], [('2025-Q3', 73), ('2025-Q4', 72), ('2026-Q1', 74), ('2026-Q2', 70), ('2026-Q3', 72)])
        self.assertEqual(rows[0]['period_start'], '2025-07-01')
        self.assertEqual(rows[0]['source_period_start'], '2025-09-01')
        self.assertEqual(rows[0]['source_frequency'], 'monthly')
        self.assertEqual(rows[0]['period_transformations'][0]['code'], 'quarter_end_label')

    def test_nonquarter_month_for_survey_is_rejected(self):
        payload = self.inputs['63238']
        row = {**payload['observations'][0], 'period_start': '2025-11-01', 'period_end': '2025-11-30'}
        with self.assertRaisesRegex(ValueError, 'quarter end'):
            normalize_record(row, payload['config'], self.aliases)

    def test_training_annual_value_is_distinct_from_december(self):
        rows = self.packets['62907']['observations']
        annual = next(r for r in rows if r['period'] == '2025')
        december = next(r for r in rows if r['period'] == '2025-12')
        self.assertEqual((annual['value'], december['value']), (81.3, 80.2))
        self.assertNotEqual(annual['id'], december['id'])

    def test_cumulative_decrease_is_flagged_without_inferred_cause_or_exclusion(self):
        rows = self.packets['63363']['observations']
        jan = next(r for r in rows if r['period'] == '2026-01')
        self.assertEqual(jan['value'], .1699)
        self.assertFalse(jan['excluded'])
        flag = next(f for f in jan['quality_flags'] if f['code'] == 'cumulative_decrease_requires_review')
        self.assertIn('Причина снижения не установлена', flag['message'])
        self.assertFalse(self.inputs['63363']['config']['annual_reset'])

    def test_same_period_change_uses_like_calendar_positions(self):
        lookup = {r['period']: r['value'] for r in self.packets['63038']['observations']}
        self.assertAlmostEqual(lookup['2026-09'] - lookup['2025-09'], 50.8)
        self.assertTrue(self.inputs['63038']['config']['annual_reset'])

    def test_actual_sdmx_replays_all_five_sources(self):
        for sid in ('62884', '63038', '62907', '63363', '63238'):
            with zipfile.ZipFile(ROOT / DOWNLOADS / 'emiss_inputs' / (sid + '.zip')) as archive:
                raw_name = next(n for n in archive.namelist() if n.endswith('.xml.gz'))
                metadata_name = next(n for n in archive.namelist() if n.endswith('metadata.html'))
                meta = parse_indicator_metadata(archive.read(metadata_name).decode(), sid)
                parsed, _ = parse_sdmx(gzip.decompress(archive.read(raw_name)))
            contract = self.inputs[sid]['config']
            roles, selected = query_plan(meta, contract)
            actual = normalized_live(parsed, meta, roles, selected, contract, self.aliases, '2026-10-29T00:00:00Z')
            expected = self.packets[sid]['observations']
            self.assertEqual(sorted((r['id'], r['value'], r['unit'], r['excluded']) for r in actual),
                             sorted((r['id'], r['value'], r['unit'], r['excluded']) for r in expected))

    def test_source_and_unit_changes_cannot_be_silent(self):
        payload = self.inputs['62884']
        row = payload['observations'][0]
        with self.assertRaisesRegex(ValueError, 'Unit mismatch'):
            normalize_record({**row, 'unit': 'человек'}, payload['config'], self.aliases)
        with self.assertRaisesRegex(ValueError, 'Source identity mismatch'):
            normalize_record({**row, 'source_id': '62907'}, payload['config'], self.aliases)
        validate_target_unit({'id': '62884', 'unit': 'процент'}, {'unit': '%'})
        with self.assertRaises(ValueError):
            validate_target_unit({'id': '62884', 'unit': 'процент'}, {'unit': 'доля единицы'})
        self.assertEqual(difference_unit({'unit': 'процент', 'cumulative': 'index'}), 'пункты индекса')

    def test_missing_update_preserves_number_but_revision_is_audited(self):
        row = self.packets['62884']['observations'][0]
        unchanged, added, revisions = merge_observations([row], [{**row, 'value': None, 'analytical_value': None}])
        self.assertEqual(unchanged[0]['value'], 101.7)
        self.assertEqual((added, revisions), (0, []))
        changed, added, revisions = merge_observations([row], [{**row, 'value': 101.8, 'analytical_value': 101.8}])
        self.assertEqual(revisions[0]['old_value'], 101.7)
        self.assertEqual(revisions[0]['new_value'], 101.8)
        self.assertEqual(added, 0)

    def test_conflicting_duplicate_is_rejected(self):
        row = self.packets['62884']['observations'][0]
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            merge_observations([], [row, {**row, 'value': 101.8}])

    def test_no_model_from_repeated_single_year(self):
        source = {'id': 'test', 'short_title': 'fixture', 'annual': [{'year': 2025, 'excluded': False, 'category': {}}] * 20}
        result = forecast_eligibility(source)
        self.assertEqual(result['distinct_annual_years'], 1)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['status'], 'insufficient_independent_annual_history')
        source['annual'] = [{'year': y, 'excluded': False, 'category': {}} for y in range(2025, 2029)]
        self.assertEqual(forecast_eligibility(source)['status'], 'model_not_validated')

    def test_context_rows_independently_match_original_table_and_report_distribution(self):
        context = build_context(ROOT)
        self.assertEqual(len(context['regions']), 85)
        self.assertEqual(context['national_value'], 2.5)
        self.assertEqual(context['class_counts'], [22, 42, 10, 9, 2])
        self.assertEqual(context['summary']['median'], 2.4)
        self.assertEqual((context['summary']['below_national'], context['summary']['equal_national'], context['summary']['above_national']), (45, 3, 37))
        self.assertNotAlmostEqual(context['summary']['unweighted_mean'], context['national_value'])
        self.assertEqual(context['missing_codes'], ['90', '93', '94', '95'])
        for code in ('29', '72'):
            self.assertIn('без АО', next(r['name'] for r in context['regions'] if r['code'] == code))
        self.assertTrue(all(not p['observations'] or all(r['geo_level'] == 'national' for r in p['observations']) for p in self.packets.values()))

    def test_target_comparisons_match_five_report_annual_results(self):
        analytics = load(ROOT / DATA / 'analytics.json')
        annual = {r['source_id']: r for r in analytics['target_comparisons'] if r['annual_comparison_eligible']}
        expected = {'62884': (101.7, 100.9, .8), '63038': (112.89, 100, 12.89), '62907': (81.3, 80, 1.3), '63363': (.1766, .27, -.0934), '63238': (72, 62, 10)}
        self.assertEqual(set(annual), set(expected))
        for sid, values in expected.items():
            row = annual[sid]
            self.assertEqual((row['fact_value'], row['target_value']), values[:2])
            self.assertAlmostEqual(row['difference'], values[2])
            self.assertFalse(row['formal_attainment_eligible'])
        self.assertEqual(sum(r['comparison_kind'] == 'annual_equivalent_vs_annual_plan' for r in annual.values()), 3)
        self.assertEqual(analytics['coverage']['observations'], 60)
        self.assertEqual(analytics['coverage']['usable_observations'], 60)


TITLE = 'Синтетический показатель для проверки'
HTML = '''<html><span class="sp_txt">Синтетический показатель для проверки</span><div id="methodologyFull">Проверенная методика.</div><div>Единицы измерения</div><ul><li>процент</li></ul><script>window.fixture={filters:{0:{title:'Показатель',values:{999:{title:'Синтетический показатель для проверки'}}},1:{title:'ОКАТО',values:{77:{title:'Москва'}}},2:{title:'Год',values:{2025:{title:'2025'}}},3:{title:'Период',values:{0:{title:'значение показателя за год'}}},4:{title:'Единица измерения',values:{u:{title:'процент'}}}},left_columns:[1],top_columns:[2,3],groups:[4]};</script></html>'''
META = parse_indicator_metadata(HTML, '999')
SOURCE = {'source_id': '999', 'indicator_id': '999', 'title': TITLE, 'titles': [TITLE], 'unit': 'процент', 'methodology': 'Проверенная методика.', 'source_url': 'https://www.fedstat.ru/indicator/999', 'first_year': 2025, 'min_regional_count': 1, 'dimension_defaults': {}, 'field_overrides': {}, 'expected_period_types': ['год', 'месяц']}
CONFIG = {'base_url': 'https://www.fedstat.ru', 'allowed_hosts': ['www.fedstat.ru', 'fedstat.ru'], 'max_cells': 1000, 'min_interval_seconds': 0, 'timeout_seconds': 1, 'retries': 0, 'failure_circuit_breaker': 3, 'sources': [SOURCE], 'unmapped_indicators': []}


def fixture_xml(value='12.3'):
    return ('<GenericData><DataSet><Series><SeriesKey><Value concept="1" value="77"/><Value concept="2" value="2025"/><Value concept="3" value="0"/><Value concept="4" value="u"/></SeriesKey><Obs><Time>2025</Time><ObsValue value="' + value + '"/></Obs></Series></DataSet></GenericData>').encode()


class RefreshSafety(unittest.TestCase):
    def fixture_root(self, path, n=1):
        config = copy.deepcopy(CONFIG)
        config['sources'] = [{**SOURCE, 'source_id': str(999 + i), 'indicator_id': str(999 + i)} for i in range(n)]
        atomic(path / 'scripts/personnel_emiss_sources.json', config)
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
            self.assertEqual(source['downloads']['current_raw'], 'downloads/projects/personnel/statistical/emiss_current/999.zip')
            self.assertEqual(source['downloads']['source_input'], 'downloads/projects/personnel/statistical/emiss_inputs/999.zip')
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
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
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
        client = PersonnelClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace('Проверенная методика.', 'Новая методика.'))))
        try:
            with self.assertRaises(EmissConnectorError) as result:
                client.metadata('999')
            self.assertEqual(result.exception.category, 'methodology_contract_changed')
        finally:
            client.close()

    def test_metadata_unit_revision_rejected(self):
        client = PersonnelClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace('<li>процент</li>', '<li>единица</li>'))))
        try:
            with self.assertRaises(EmissConnectorError) as result:
                client.metadata('999')
            self.assertEqual(result.exception.category, 'unit_mismatch')
        finally:
            client.close()

    def test_empty_grid_is_distinguished_from_failure(self):
        no_grid = HTML.split('<script>')[0] + '</html>'
        client = PersonnelClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=no_grid)))
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

    def test_real_current_json_and_csv_are_not_fabricated_from_report(self):
        stats = load(ROOT / DATA / 'statistics.json')
        for source in stats['sources']:
            packet = load(ROOT / DATA / 'series' / (source['id'] + '.json'))
            national = [r for r in packet['observations'] if r['geo_level'] == 'national']
            self.assertEqual(source['national'], national)
            self.assertEqual(source['observation_count'], len(packet['observations']))
            self.assertEqual(source['numeric_count'], sum(r['value'] is not None for r in packet['observations']))
            if str(packet.get('snapshot_id') or '').startswith('live:'):
                self.assertIn('current_raw', source['downloads'])
            else:
                self.assertNotIn('current_raw', source['downloads'])


if __name__ == '__main__':
    unittest.main()
