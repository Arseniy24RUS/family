"""Integrity and independent offline replication of the v3 tourism packet."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'public/data/projects/tourism'
NODE = shutil.which('node')


class TourismResearchIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='tourism-research-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        destination = cls.root / 'public/data/projects/tourism'
        shutil.copytree(DATA / 'series', destination / 'series')
        shutil.copyfile(DATA / 'statistics.json', destination / 'statistics.json')
        shutil.copyfile(ROOT / 'package.json', cls.root / 'package.json')
        spec = importlib.util.spec_from_file_location('tourism_research_generator_test', ROOT / 'scripts/build_tourism_research.py')
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        with contextlib.redirect_stdout(io.StringIO()):
            generator.build(cls.root)
        cls.packet_path = destination / 'research.json'
        cls.packet = json.loads(cls.packet_path.read_text(encoding='utf-8'))
        cls.raw_bytes = (DATA / 'series/62900.json').read_bytes()
        cls.source = json.loads(cls.raw_bytes)
        cls.exports_ready = False

    @classmethod
    def make_exports(cls):
        if cls.exports_ready:
            return
        script = """
import fs from 'node:fs';
import {normalizeTourismRows,buildTourismExport} from './src/core/tourism-research.js';
const packet=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const rows=normalizeTourismRows(packet);
const settings={period:'2025-12-31',regions:['77','24'],view:'territories'};
fs.writeFileSync(process.argv[2],JSON.stringify(buildTourismExport(rows,settings)));
const gap=rows.filter(row=>!(row.regionId==='RU'&&row.periodEnd==='2025-03-31'));
fs.writeFileSync(process.argv[3],JSON.stringify(buildTourismExport(gap,settings)));
"""
        cls.valid_path = cls.root / 'export.json'
        cls.gap_path = cls.root / 'export-gap.json'
        subprocess.run([NODE, '--input-type=module', '-e', script, str(cls.packet_path), str(cls.valid_path), str(cls.gap_path)],
                       cwd=ROOT, capture_output=True, text=True, check=True, timeout=30)
        cls.exports_ready = True

    def replay(self, path, output=None):
        command = [sys.executable, str(ROOT / 'scripts/reproduce_tourism_research.py'), str(path)]
        if output:
            command.extend(['--output', str(output)])
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.stderr, '', result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_generated_packet_expands_all_source_records_and_preserves_byte_hash(self):
        expanded = [{**self.packet['observation_defaults'], **row} for row in self.packet['observations']]
        self.assertEqual(len(expanded), 1806)
        self.assertEqual(expanded, self.source['observations'])
        self.assertEqual(self.packet['source_sha256'], hashlib.sha256(self.raw_bytes).hexdigest())
        self.assertEqual(self.packet['snapshot_id'], self.source['snapshot_id'])
        self.assertEqual(self.packet['comparison_status'], 'requires_edition_review')
        self.assertEqual(self.packet['release_version'], json.loads((ROOT / 'package.json').read_text())['version'])
        self.assertLess(self.packet_path.stat().st_size, len(self.raw_bytes))
        for row in expanded:
            self.assertTrue(row['source_cell_attributes']['source_cell'])
            self.assertTrue(row['source_observation_key'])

    def test_fourteen_exclusions_keep_exact_source_rows_and_cell_references(self):
        expected = {}
        for path in sorted((DATA / 'series').glob('*.json')):
            dataset = json.loads(path.read_text(encoding='utf-8'))
            for row in dataset['observations']:
                if row.get('excluded'):
                    expected[(row['source_id'], row['id'])] = (row, dataset['title'])
        self.assertEqual(len(expected), 14)
        self.assertEqual(len(self.packet['exclusions']), 14)
        self.assertEqual({(row['source_id'], row['id']) for row in self.packet['exclusions']}, set(expected))
        for actual in self.packet['exclusions']:
            original, title = expected[(actual['source_id'], actual['id'])]
            self.assertEqual({key: value for key, value in actual.items() if key != 'source_title'}, original)
            self.assertEqual(actual['source_title'], title)
            self.assertTrue(actual['source_cell_attributes']['source_cell'])
            self.assertIsNone(actual['analytical_value'])
            self.assertTrue(any(flag['exclude_from_analysis'] for flag in actual['quality_flags']))

    @unittest.skipUnless(NODE, 'Node.js is required for the browser-export integration check')
    def test_offline_replay_accepts_the_real_export_and_rejects_changed_top5(self):
        self.make_exports()
        output = self.root / 'verification.json'
        code, result = self.replay(self.valid_path, output)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(json.loads(output.read_text(encoding='utf-8')), result)
        self.assertEqual((result['observations'], result['regions'], result['periods_checked']), (1806, 85, 21))
        self.assertEqual((result['mismatches'], result['trajectory_points_checked']), (8, 63))
        self.assertAlmostEqual(result['top5_share_pct'], 41.79370901363279, places=8)
        self.assertAlmostEqual(result['top10_share_pct'], 52.70591507429152, places=8)
        altered = json.loads(self.valid_path.read_text(encoding='utf-8'))
        altered['slice']['top5Share'] = -1
        altered_path = self.root / 'export-altered.json'
        altered_path.write_text(json.dumps(altered), encoding='utf-8')
        code, result = self.replay(altered_path)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any('slice.top5Share' in message for message in result['errors']))

    @unittest.skipUnless(NODE, 'Node.js is required for the browser-export integration check')
    def test_offline_replay_preserves_missing_month_and_rejects_its_zero_substitution(self):
        self.make_exports()
        code, result = self.replay(self.gap_path)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['observations'], 1805)
        altered = json.loads(self.gap_path.read_text(encoding='utf-8'))
        line = next(item for item in altered['trajectories'] if item['regionId'] == 'RU' and item['year'] == 2025)
        march = next(point for point in line['points'] if point['month'] == 3)
        self.assertIsNone(march['value'])
        march['value'] = 0
        altered_path = self.root / 'export-gap-zero.json'
        altered_path.write_text(json.dumps(altered), encoding='utf-8')
        code, result = self.replay(altered_path)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any('month 3' in message for message in result['errors']))


if __name__ == '__main__':
    unittest.main()
