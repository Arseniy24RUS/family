import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from build_current_analytics import period_rows, valid, spatial


class CurrentAnalyticsTests(unittest.TestCase):
    def test_latest_month_beats_prior_annual_but_same_date_prefers_annual(self):
        def row(end, typ):
            return dict(r='77', territory='Москва', end=end, type=typ, value=1)
        rows = [row('2025-12-31', 'год'), row('2025-12-31', 'месяц')]
        self.assertEqual(period_rows(rows)[0], 'год|2025-12-31')
        rows.append(row('2026-08-31', 'месяц'))
        self.assertEqual(period_rows(rows)[0], 'месяц|2026-08-31')

    def test_nested_districts_and_conflicts(self):
        rows = [dict(r='72', territory=t, end='2026-08-31', type='месяц', value=v)
                for t, v in [('Тюменская область', 2), ('Тюменская область без автономных округов', 1)]]
        self.assertEqual(period_rows(rows)[1]['72']['value'], 1)
        rows[1]['territory'] = 'Другая запись'
        self.assertNotIn('72', period_rows(rows)[1])

    def test_quality_flags_excluded_without_clipping(self):
        r = dict(value=414.35, flag='outside_0_100')
        self.assertFalse(valid(r))
        self.assertEqual(r['value'], 414.35)
        self.assertTrue(valid(dict(value=0)))
        self.assertFalse(valid(dict(value=None)))

    def test_spatial_deterministic_normalization_and_bh(self):
        values = dict(a=1, b=2, c=4, d=8, e=9, f=10)
        edges = [('a', 'b'), ('b', 'c'), ('c', 'd'), ('d', 'e'), ('e', 'f'), ('f', 'missing')]
        a = spatial(values, edges, 99)
        b = spatial(values, edges, 99)
        self.assertEqual(a['I'], b['I'])
        self.assertEqual(a['p'], b['p'])
        np.testing.assert_array_equal(a['q'], b['q'])
        self.assertTrue(np.all(a['q'] >= a['p_local']))
        self.assertTrue(np.all(a['q'] <= 1))
        self.assertEqual(a['islands'], 0)
        z = (np.array(list(values.values()))-np.mean(list(values.values())))/np.std(list(values.values()))
        lag = np.array([z[1], (z[0]+z[2])/2, (z[1]+z[3])/2, (z[2]+z[4])/2, (z[3]+z[5])/2, z[4]])
        self.assertAlmostEqual(a['I'], np.dot(z, lag)/np.dot(z, z))


if __name__ == '__main__':
    unittest.main()
