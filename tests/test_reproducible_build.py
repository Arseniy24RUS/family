"""Regression checks for editorial ownership, exact ties and archive metadata."""
import copy
import gzip
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from infrastructure_method_review import apply_method_review
from reproducible_output import gzip_bytes, write_zip_entry, descending_term_indices
from build_projection_downloads import run as build_projection_downloads


class EditorialReviewTests(unittest.TestCase):
    def setUp(self):
        self.review = json.loads((ROOT/'scripts/infrastructure_method_review.json').read_text(encoding='utf-8'))
        self.published = json.loads((ROOT/'public/data/projects/life_infrastructure/methods.json').read_text(encoding='utf-8'))

    def test_analytics_preserves_the_complete_published_review(self):
        methods = copy.deepcopy(self.published)
        self.assertEqual(apply_method_review(methods, self.review), self.published)

    def test_new_revision_does_not_replace_calculated_or_historical_fields(self):
        methods = copy.deepcopy(self.published)
        methods['items'][0]['numeric_indicators'] = 41
        self.review['items'][0]['current_limitations'] = 'Новая редакторская оговорка с указанием основания.'
        expected = copy.deepcopy(methods)
        expected['items'][0]['current_limitations'] = self.review['items'][0]['current_limitations']
        self.assertEqual(apply_method_review(methods, self.review), expected)

    def test_missing_duplicate_or_extra_review_fields_fail_without_mutation(self):
        cases = []
        value = copy.deepcopy(self.review);value['items'].pop();cases.append(value)
        value = copy.deepcopy(self.review);value['items'].append(value['items'][0]);cases.append(value)
        value = copy.deepcopy(self.review);value['items'][0]['current_limitations'] = '';cases.append(value)
        value = copy.deepcopy(self.review);value['items'][0]['numeric_indicators'] = 123;cases.append(value)
        value = copy.deepcopy(self.review);value['project_id'] = 'tourism';cases.append(value)
        for broken in cases:
            methods = copy.deepcopy(self.published)
            with self.assertRaises(ValueError):
                apply_method_review(methods, broken)
            self.assertEqual(methods, self.published)


class ReproducibleOutputTests(unittest.TestCase):
    def test_gzip_has_fixed_metadata_and_preserves_every_input_byte(self):
        payload = ('Источник\r\n123.45000000000000001\n' * 100).encode('utf-8')
        packed = gzip_bytes(payload)
        self.assertEqual(packed[:10], bytes.fromhex('1f8b08000000000002ff'))
        self.assertEqual(gzip.decompress(packed), payload)
        self.assertEqual(gzip_bytes(payload), packed)

    def test_exact_ties_use_terms_and_adjacent_floats_are_not_rounded(self):
        rows = [('я', .5), ('б', .5), ('а', math.nextafter(.5, 0)), ('в', math.nextafter(.5, 1))]
        expected = ['в', 'б', 'я', 'а']
        for ordered in [rows, rows[::-1], rows[1:]+rows[:1]]:
            terms, weights = zip(*ordered)
            ranking = descending_term_indices(weights, terms)
            self.assertEqual([terms[i] for i in ranking], expected)
            self.assertEqual(weights[terms.index('а')], math.nextafter(.5, 0))

    def test_zip_container_is_independent_of_clock_and_keeps_content(self):
        content = b'\x00source\r\nbytes\xff'
        outputs = []
        for year in [2001, 2035]:
            output = io.BytesIO()
            with patch('zipfile.time.localtime', return_value=(year, 7, 2, 12, 34, 56, 0, 1, 0)):
                with zipfile.ZipFile(output, 'w') as archive:
                    write_zip_entry(archive, 'evidence.bin', content)
            outputs.append(output.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        with zipfile.ZipFile(io.BytesIO(outputs[0])) as archive:
            self.assertEqual(archive.read('evidence.bin'), content)
            self.assertEqual(archive.getinfo('evidence.bin').date_time, (1980, 1, 1, 0, 0, 0))

    def test_projection_builder_repeats_identically_after_source_timestamp_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relative, content in {
                'public/data/projections/indicators/manifest.json': '{"series":[]}',
                'public/data/projections/population/manifest.json': '{"fixtures":true}',
                'public/data/projections/demo_input.json': '{"synthetic":true}\r\n',
                'scripts/demography/cohort.py': '# cohort fixture\n',
                'scripts/demography/indicator.py': '# indicator fixture\n',
                'scripts/demography/indicator_v11.py': '# historical fixture\n',
                'scripts/reproduce_projection.py': '# reproduction fixture\n',
            }.items():
                target = root/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content.encode('utf-8'))
            outputs = []
            for timestamp, year in [(1_000_000_000, 2001), (2_000_000_000, 2033)]:
                os.utime(root/'public/data/projections/demo_input.json', (timestamp, timestamp))
                with patch('zipfile.time.localtime', return_value=(year, 7, 2, 12, 34, 56, 0, 1, 0)):
                    build_projection_downloads(root)
                outputs.append({p.name: p.read_bytes() for p in (root/'public/downloads/projections').iterdir()})
            self.assertEqual(outputs[0], outputs[1])
            with zipfile.ZipFile(io.BytesIO(outputs[0]['projections_python.zip'])) as archive:
                self.assertEqual(archive.read('example_synthetic.json'), b'{"synthetic":true}\r\n')


if __name__ == '__main__':
    unittest.main()
