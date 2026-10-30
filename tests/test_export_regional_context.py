"""Guard the territorial boundary and source arithmetic of the CBR context."""
from decimal import Decimal
from pathlib import Path
import hashlib
import importlib.util
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('export_regional_context', ROOT / 'scripts/build_export_regional_context.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExportRegionalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = json.loads((ROOT / 'public/data/projects/international_export/regional-context.json').read_text(encoding='utf-8'))['services']

    def test_source_legend_keeps_unknown_distinct_from_zero(self):
        self.assertIsNone(MODULE.published_number(''))
        self.assertIsNone(MODULE.published_number('...'))
        self.assertIsNone(MODULE.published_number('…'))
        self.assertEqual(MODULE.published_number('-'), Decimal('0'))
        self.assertEqual(MODULE.published_number('14.5199999999999996'), Decimal('14.52'))

    def test_annual_region_partition_excludes_overlapping_parent_totals(self):
        for year in [2024, 2025]:
            with self.subTest(year=year):
                rows = [row for row in self.context['rows'] if row['year'] == year]
                self.assertEqual(len(rows), 85)
                by_id = {row['map_id']: row for row in rows}
                self.assertEqual(len(by_id), 85)
                self.assertIn('без данных', by_id['29']['source_name'])
                self.assertIn('без данных', by_id['72']['source_name'])
                self.assertTrue({'83', '86', '89'}.issubset(by_id))
                self.assertTrue(all(row['value'] is not None for row in rows))
        self.assertEqual(self.context['missing_map_ids'], ['90', '93', '94', '95'])

    def test_rounding_residual_is_retained_and_bounded(self):
        expected = {2024: Decimal('0.43'), 2025: Decimal('-0.33')}
        for record in self.context['reconciliation']:
            d = lambda key: Decimal(str(record[key]))
            self.assertEqual(d('regional_sum') + d('unallocated') - d('national'), d('residual'))
            self.assertEqual(d('residual'), expected[record['year']])
            self.assertEqual(d('tolerance'), Decimal('0.435'))
            self.assertLessEqual(abs(d('residual')), d('tolerance'))

    def test_concentration_uses_published_regional_denominator(self):
        for concentration in self.context['concentration']:
            rows = [row for row in self.context['rows'] if row['year'] == concentration['year']]
            values = [Decimal(str(row['value'])) for row in rows]
            allocated = sum(values)
            national = Decimal(str(next(row['value'] for row in self.context['national'] if row['year'] == concentration['year'])))
            top10 = sum(sorted(values, reverse=True)[:10])
            self.assertAlmostEqual(concentration['hhi_allocated'], float(sum((v / allocated) ** 2 for v in values)), places=12)
            self.assertAlmostEqual(concentration['top10_share_national_pct'], float(100 * top10 / national), places=10)
            self.assertAlmostEqual(concentration['top10_share_allocated_pct'], float(100 * top10 / allocated), places=10)
        self.assertEqual(self.context['growth_summary'], {'increased': 63, 'decreased': 22, 'unchanged': 0, 'comparable_regions': 85})

    def test_original_workbooks_and_published_cells_agree(self):
        for source in self.context['sources']:
            path = ROOT / 'public' / source['local_file']
            raw = path.read_bytes()
            self.assertEqual(len(raw), source['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source['sha256'])
            cells = MODULE.workbook_cells(path)
            for row in self.context['rows']:
                if row['year'] != source['year']:
                    continue
                self.assertEqual(cells[row['source_cell']], row['raw_value'])
                self.assertEqual(float(MODULE.published_number(row['raw_value'])), row['value'])
                for key, cell in row['component_cells'].items():
                    value = MODULE.published_number(cells.get(cell, ''))
                    self.assertEqual(row['components'][key], None if value is None else float(value))


if __name__ == '__main__':
    unittest.main()
