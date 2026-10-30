"""Youth contracts: immutable release evidence, analytical limits and refresh safety."""
import copy
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
from youth_data import ROOT, DATA, DOWNLOADS, load, atomic, normalize_payload, normalize_record, region_aliases, merge_observations, quantile
from build_youth_analytics import summary, latest, forecast_eligibility, validate_target_unit, difference_unit, make_source
from refresh_youth_emiss import YouthClient, run, normalized_live


class ReleaseEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aliases = region_aliases(ROOT)
        cls.packets = {}
        cls.inputs = {}
        cls.config = load(ROOT / 'scripts/youth_emiss_sources.json')
        for source in cls.config['sources']:
            sid = source['indicator_id']
            with zipfile.ZipFile(ROOT / DOWNLOADS / 'emiss_inputs' / (sid + '.zip')) as archive:
                payload = json.loads(archive.read('input.json'))
                for entry in json.loads(payload['snapshot']['raw_manifest_json']) if payload['snapshot'] else []:
                    import gzip
                    relative = '/'.join(p for p in entry['path'].replace('\\', '/').split('/') if p)
                    body = archive.read('source/' + relative)
                    if relative.endswith('.gz'):
                        body = gzip.decompress(body)
                    assert hashlib.sha256(body).hexdigest() == entry['sha256']
            cls.inputs[sid] = payload
            cls.packets[sid] = normalize_payload(payload, cls.aliases)

    def test_all_source_inputs_replay_with_exact_original_values(self):
        count = numeric = 0
        for sid, packet in self.packets.items():
            original = {r['observation_key']: r for r in self.inputs[sid]['observations']}
            for row in packet['observations']:
                evidence = original[row['source_observation_key']]
                self.assertEqual(row['value'], evidence['value_numeric'])
                self.assertEqual(row['unit'], evidence['unit'])
                self.assertEqual(row['period_end'], evidence['period_end'])
                count += 1
                numeric += row['value'] is not None
        self.assertEqual(len(self.packets), 29)
        self.assertEqual((count, numeric), (3596, 3414))

    def test_metadata_only_contracts_not_invented_values(self):
        empty = [p for p in self.packets.values() if not p['observations']]
        self.assertEqual(len(empty), 19)
        self.assertTrue(all(p['published_at'] is None for p in empty))
        self.assertEqual(len(self.config['unmapped_indicators']), 8)

    def test_two_independent_annual_facts(self):
        annual = [r for packet in self.packets.values() for r in packet['observations'] if r['frequency'] == 'annual' and r['geo_level'] == 'national']
        self.assertEqual(sorted((r['source_id'], r['period'], r['value']) for r in annual), [('62895', '2025', 414.647), ('62898', '2025', 5.6)])
        for sid in ('62895', '62898'):
            ids = [r['id'] for r in self.packets[sid]['observations']]
            self.assertEqual(len(ids), len(set(ids)))

    def test_report_anomalies_preserved_but_excluded(self):
        excluded = [r for p in self.packets.values() for r in p['observations'] if r['value'] is not None and r['excluded']]
        self.assertEqual(len(excluded), 4)
        anomaly = next(r for r in excluded if r['source_id'] == '62968')
        self.assertEqual(anomaly['value'], 6.31)
        self.assertEqual(anomaly['period'], '2025-12')
        self.assertIsNone(anomaly['analytical_value'])
        self.assertTrue(all(r['analytical_value'] is None for r in excluded))

    def test_revised_anomaly_is_reconsidered(self):
        payload = self.inputs['62968']
        row = next(r for r in payload['observations'] if r['territory_name'] == 'Российская Федерация' and r['year'] == 2025 and r['month'] == 12)
        revised = {**row, 'value_numeric': 96.31}
        normalized = normalize_record(revised, payload['config'], self.aliases)
        self.assertFalse(normalized['excluded'])
        self.assertEqual(normalized['analytical_value'], 96.31)

    def test_latest_teacher_distribution_matches_independent_report(self):
        rows = [r for r in self.packets['62969']['observations'] if r['geo_level'] == 'regional' and r['period'] == '2026-07']
        result = summary(rows)
        self.assertEqual([result[k] for k in ('n', 'minimum', 'q1', 'median', 'q3', 'maximum')], [85, 1.68, 5.26, 8.21, 12.63, 35.67])
        national = next(r for r in self.packets['62969']['observations'] if r['geo_level'] == 'national' and r['period'] == '2026-07')
        self.assertEqual(national['value'], 10.35)

    def test_latest_talent_distribution_preserves_89_positions(self):
        rows = [r for r in self.packets['62968']['observations'] if r['geo_level'] == 'regional' and r['period'] == '2026-09']
        result = summary(rows)
        self.assertEqual([result[k] for k in ('n', 'minimum', 'q1', 'median', 'q3', 'maximum', 'at_100', 'below_80')], [89, 67.46, 89.92, 97.58, 100, 100, 27, 8])
        other = [r for r in self.packets['62968']['observations'] if r['geo_level'] == 'other']
        self.assertTrue(all(r['map_id'] is None for r in other))
        self.assertEqual(len(other), 20)
        self.assertEqual(sum(r['value'] is not None for r in other), 18)
        self.assertEqual(latest(other)['value'], 100)

    def test_latest_source_does_not_backdate_to_annual(self):
        rows = self.packets['62895']['observations']
        point = latest(rows)
        self.assertEqual((point['period'], point['value']), ('2026-05', 439.464))

    def test_mean_is_not_used_as_national_total(self):
        rows = [r for r in self.packets['62969']['observations'] if r['geo_level'] == 'regional' and r['period'] == '2026-07']
        self.assertNotAlmostEqual(sum(r['value'] for r in rows) / len(rows), 10.35, places=2)

    def test_same_month_delta_and_january_reset(self):
        for sid, expected in [('62932', .29), ('62931', -.74)]:
            lookup = {r['period']: r['value'] for r in self.packets[sid]['observations'] if r['geo_level'] == 'national'}
            self.assertAlmostEqual(lookup['2026-03'] - lookup['2025-03'], expected)
            self.assertTrue(self.inputs[sid]['config']['annual_reset'])

    def test_unit_and_source_changes_rejected(self):
        payload = self.inputs['62895']
        row = payload['observations'][0]
        with self.assertRaisesRegex(ValueError, 'Unit mismatch'):
            normalize_record({**row, 'unit': 'человек'}, payload['config'], self.aliases)
        with self.assertRaisesRegex(ValueError, 'Source identity mismatch'):
            normalize_record({**row, 'source_id': '62898'}, payload['config'], self.aliases)

    def test_missing_update_does_not_erase_number(self):
        row = next(r for r in self.packets['62895']['observations'] if r['value'] is not None)
        result, added, changes = merge_observations([row], [{**row, 'value': None, 'analytical_value': None}])
        self.assertEqual(result[0]['value'], row['value'])
        self.assertEqual((added, changes), (0, []))

    def test_revision_retains_an_audit_record(self):
        row = self.packets['62895']['observations'][0]
        result, added, changes = merge_observations([row], [{**row, 'value': row['value'] + 1, 'analytical_value': row['value'] + 1}])
        self.assertEqual(changes[0]['old_value'], row['value'])
        self.assertEqual(changes[0]['new_value'], row['value'] + 1)
        self.assertEqual(added, 0)

    def test_actual_archived_sdmx_replays_to_exact_observed_points(self):
        import gzip
        for sid in ('62931', '62936'):
            with zipfile.ZipFile(ROOT / DOWNLOADS / 'emiss_inputs' / (sid + '.zip')) as archive:
                raw_name = next(n for n in archive.namelist() if n.endswith('.xml.gz'))
                metadata_name = next(n for n in archive.namelist() if n.endswith('metadata.html'))
                meta = parse_indicator_metadata(archive.read(metadata_name).decode(), sid)
                parsed, _ = parse_sdmx(gzip.decompress(archive.read(raw_name)))
            contract = self.inputs[sid]['config']
            roles, selected = query_plan(meta, contract)
            replayed = normalized_live(parsed, meta, roles, selected, contract, self.aliases, '2026-10-29T00:00:00Z')
            expected = self.packets[sid]['observations']
            self.assertEqual(sorted((r['id'], r['value'], r['unit'], r['excluded']) for r in replayed), sorted((r['id'], r['value'], r['unit'], r['excluded']) for r in expected))

    def test_target_unit_cannot_silently_change_scale(self):
        source = {'id': '62895', 'unit': 'тысяча человек'}
        validate_target_unit(source, {'unit': 'Тысяча человек'})
        with self.assertRaisesRegex(ValueError, 'Target unit differs'):
            validate_target_unit(source, {'unit': 'человек'})
        self.assertEqual(difference_unit({'unit': 'процент', 'cumulative': 'index'}), 'пункты индекса')
        self.assertEqual(difference_unit({'unit': 'процент', 'cumulative': 'year'}), 'п.п.')
        self.assertEqual(difference_unit(source), 'тысяча человек')

    def test_future_annual_history_requires_model_review_not_false_insufficiency(self):
        source = {'id': '62895', 'short_title': 'Синтетическая история', 'annual': [
            {'year': year, 'excluded': False, 'category': {}} for year in range(2025, 2029)]}
        result = forecast_eligibility(source)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['status'], 'model_not_validated')
        self.assertEqual(result['annual_observations'], 4)
        source['annual'] = source['annual'][:1] * 10
        result = forecast_eligibility(source)
        self.assertEqual(result['status'], 'insufficient_independent_annual_history')
        self.assertEqual(result['annual_observations'], 1)

    def test_conflicting_duplicate_update_is_rejected(self):
        row = self.packets['62895']['observations'][0]
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            merge_observations([], [row, {**row, 'value': row['value'] + 1}])


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
        atomic(path / 'scripts/youth_emiss_sources.json', config)
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
            self.assertEqual(source['downloads']['current_raw'], 'downloads/projects/youth_children/emiss_current/999.zip')
            self.assertEqual(source['downloads']['source_input'], 'downloads/projects/youth_children/emiss_inputs/999.zip')
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
        client = YouthClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace('Проверенная методика.', 'Новая методика.'))))
        try:
            with self.assertRaises(EmissConnectorError) as result:
                client.metadata('999')
            self.assertEqual(result.exception.category, 'methodology_contract_changed')
        finally:
            client.close()

    def test_metadata_unit_revision_rejected(self):
        client = YouthClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace('<li>процент</li>', '<li>единица</li>'))))
        try:
            with self.assertRaises(EmissConnectorError) as result:
                client.metadata('999')
            self.assertEqual(result.exception.category, 'unit_mismatch')
        finally:
            client.close()

    def test_empty_grid_is_distinguished_from_failure(self):
        no_grid = HTML.split('<script>')[0] + '</html>'
        client = YouthClient(CONFIG, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=no_grid)))
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
