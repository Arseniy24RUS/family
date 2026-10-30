"""Independent source and interpretation checks for the Longlife publication.

These checks read the immutable DOCX and compact source inputs directly; they do
not import the builders. The expensive TF-IDF replication has its own saved
protocol and is repeated explicitly with --verify-text when its inputs change.
"""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import csv
import gzip
import hashlib
import json
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'public/data/projects/long_active_life'
DOWNLOAD = ROOT / 'public/downloads/projects/long_active_life'
REPORT_SHA256 = '5685d539722553bd90da5f3db190e663e5640129bc4bd8443258e9907d5de72b'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def decimal_cell(value):
    return Decimal(str(value).replace(' ', '').replace('\u00a0', '').replace(',', '.'))


def csv_read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


class LonglifeDocumentaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = read(DATA / 'documentary.json')
        cls.targets = read(DATA / 'targets.json')
        cls.expertise = read(DATA / 'expertise.json')
        cls.extract = read(DOWNLOAD / 'report/report_extraction.json')
        cls.coverage = read(DOWNLOAD / 'report/coverage_manifest.json')
        cls.inputs = json.loads(gzip.decompress((ROOT / 'inputs/longlife/documentary_inputs.json.gz').read_bytes()))

    def test_original_bytes_and_source_manifest(self):
        sources = read(DOWNLOAD / 'documentary/source_manifest.json')['documents']
        self.assertEqual(len(sources), 15)
        self.assertEqual(Counter(Path(s['download_path']).suffix for s in sources), {'.html': 12, '.pdf': 3})
        for source in sources:
            with self.subTest(source=source['title']):
                path = ROOT / 'public' / source['download_path']
                self.assertEqual(path.stat().st_size, source['size_bytes'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source['source_sha256'])
        original = DOWNLOAD / 'report/expertise_longlife_2026.docx'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), REPORT_SHA256)
        self.assertEqual(self.expertise['meta']['source_docx_sha256'], REPORT_SHA256)
        self.assertEqual(self.extract['sha256'], REPORT_SHA256)

    def test_author_words_footnotes_tables_and_figures_are_preserved(self):
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        plain = lambda value: re.sub(r'\s+', '', value)
        with zipfile.ZipFile(DOWNLOAD / 'report/expertise_longlife_2026.docx') as source:
            body = ET.fromstring(source.read('word/document.xml')).find('w:body', ns)
            paragraphs = [''.join(n.text or '' for n in p.findall('.//w:t', ns)) for p in body.findall('w:p', ns)]
            parsed = [b['text'] for b in self.extract['blocks'] if b['type'] == 'paragraph']
            self.assertEqual([plain(s) for s in paragraphs], [plain(s) for s in parsed])
            notes = ET.fromstring(source.read('word/footnotes.xml'))
            originals = {int(n.attrib['{' + ns['w'] + '}id']): plain(''.join(t.text or '' for t in n.findall('.//w:t', ns))) for n in notes if int(n.attrib['{' + ns['w'] + '}id']) > 0}
            self.assertEqual(originals, {f['id']: plain(f['text']) for f in self.extract['footnotes']})
            raw_tables = [[[''.join(t.text or '' for t in cell.findall('.//w:t', ns)) for cell in row.findall('w:tc', ns)] for row in table.findall('w:tr', ns)] for table in body.findall('w:tbl', ns)]
            self.assertEqual([[[plain(c) for c in row] for row in table] for table in raw_tables], [[[plain(c) for c in row] for row in table['rows']] for table in self.extract['tables']])
        self.assertEqual((len(self.expertise['pages']), len(self.expertise['tables']), len(self.expertise['figures']), len(self.expertise['sources'])), (21, 14, 18, 138))
        self.assertEqual(self.coverage['summary']['substantive_blocks'], 387)
        self.assertEqual(self.coverage['summary']['assigned_blocks'], 387)
        self.assertEqual(self.coverage['summary']['unmapped_substantive_blocks'], [])
        self.assertEqual(self.coverage['summary']['duplicate_assignments'], [])
        source_blocks = {b['index']: b for b in self.extract['blocks']}
        for page in self.expertise['pages'].values():
            for block in page['blocks']:
                if block['type'] in {'paragraph', 'heading'} and 'sourceBlock' in block:
                    self.assertEqual(block['text'], source_blocks[block['sourceBlock']]['text'])
        for table, raw in zip(self.expertise['tables'], self.extract['tables']):
            actual = [[col['label'] for col in table['columns']]] + [[row[col['key']] for col in table['columns']] for row in table['rows']]
            self.assertEqual(actual, raw['rows'])
        for figure in self.expertise['figures']:
            self.assertEqual(hashlib.sha256((ROOT / 'public' / figure['url']).read_bytes()).hexdigest(), figure['original_sha256'])

    def test_eight_equations_and_local_seed_clarification(self):
        formula = [b for p in self.expertise['pages'].values() for b in p['blocks'] if b['type'] == 'formula']
        self.assertEqual(sorted(b['number'] for b in formula), list(range(1, 9)))
        expected_pages = {1: 9, 2: 10, 3: 74, 4: 101, 5: 101, 6: 102, 7: 113, 8: 114}
        for item in formula:
            self.assertEqual(item['page'], expected_pages[item['number']])
            self.assertEqual(item['page_verification'], 'rendered_source_formula_visually_checked')
            self.assertTrue(item['latex'])
        by_number = {f['number']: f for f in formula}
        self.assertIn(r'\frac{\sum_{a=x}^{\omega}L_a}{l_x}', by_number[1]['latex'])
        self.assertIn(r'\frac{\sum_{a=x}^{\omega}L_a p_a}{l_x}', by_number[2]['latex'])
        markdown = (DOWNLOAD / 'report/expertise_longlife_2026.md').read_text(encoding='utf-8')
        self.assertNotIn('[FORMULA]', markdown)
        self.assertTrue(all(item['latex'] in markdown for item in formula))
        self.assertTrue(all(Path(item['url']).name in markdown for item in self.expertise['figures']))
        clarification = next(c for c in self.expertise['meta']['source_clarifications'] if c.get('author_paragraph') == 263)
        self.assertEqual((clarification['route'], clarification['author_page']), ('methods', 69))
        self.assertEqual(clarification['parameters']['seeds'], list(range(10)))
        self.assertEqual(clarification['ari_min'], -0.0016820150540347335)
        self.assertTrue(any('от 0,905 до 1,000' in b.get('text', '') for b in self.expertise['pages']['methods']['blocks']))

    def test_all_finance_cells_and_different_published_horizons(self):
        rows = self.inputs['tables']['f_cashflows']
        headers = [r for r in rows if r['row_type'] == 'document_header' and r['source_name'] == 'all_sources_declared']
        federal = {r['record_id']: r for r in headers if r['document_level'] == 'federal'}
        self.assertEqual(len(federal), 120)
        published = csv_read(DOWNLOAD / 'documentary/finance_fp_years.csv')
        self.assertEqual(len(published), 120)
        self.assertEqual({r['record_id'] for r in published}, set(federal))
        for row in published:
            original = federal[row['record_id']]
            self.assertEqual(Decimal(row['amountThousandRub']), Decimal(original['amount_thousand_rub']))
            self.assertEqual(int(row['year']), int(original['year']))
            self.assertEqual(row['source_xpath'], original['source_xpath'])
        finance = self.doc['finance']
        self.assertEqual(sum(len(p['years']) for p in finance['projects']), 66)
        common_total = Decimal(0)
        full_total = Decimal(0)
        for project in finance['projects']:
            expected = [r for r in federal.values() if r['document_title'].startswith('[' + project['code'] + ']')]
            actual = project['fullYears']
            self.assertEqual({r['record_id']: Decimal(r['amountThousandRub']) for r in actual}, {r['record_id']: Decimal(r['amount_thousand_rub']) for r in expected})
            common = sum(Decimal(r['amount_thousand_rub']) for r in expected if 2025 <= int(r['year']) <= 2030)
            full = sum(Decimal(r['amount_thousand_rub']) for r in expected)
            self.assertEqual(common, Decimal(project['totalThousandRub']))
            self.assertEqual(full, Decimal(project['fullHorizonThousandRub']))
            common_total += common
            full_total += full
            expected_end = 2030 if project['code'] in {'Д9', 'ДА'} else 2036
            self.assertEqual([r['year'] for r in actual], list(range(2025, expected_end + 1)))
            if expected_end == 2030:
                self.assertFalse(project['laterPublished'])
                self.assertIsNone(project['laterThousandRub'])
                self.assertIsNone(project['laterBillionRub'])
        self.assertEqual(common_total, Decimal('4066231073.60'))
        self.assertEqual(full_total, Decimal(finance['fullHorizonThousandRub']))
        national = sum(Decimal(r['amount_thousand_rub']) for r in headers if r['document_level'] == 'national' and 2025 <= int(r['year']) <= 2030)
        self.assertEqual(national, Decimal('4136479588.77'))
        self.assertEqual(national - common_total, Decimal('70248515.17'))
        self.assertEqual(Decimal(finance['differenceThousandRub']), common_total - national)
        self.assertEqual(Decimal(finance['nationalMinusFederalThousandRub']), national - common_total)
        self.assertEqual(finance['differenceConvention'], 'federal_minus_national')
        # Each document reconciles its visible sources; result-level rows are
        # intentionally absent from this sum to prevent repeated transfers.
        source_rows = [r for r in rows if r['row_type'] == 'document_source']
        checked = 0
        for header in headers:
            if 2025 <= int(header['year']) <= 2030:
                source_sum = sum((Decimal(r['amount_thousand_rub']) for r in source_rows if r['source_sha256'] == header['source_sha256'] and r['year'] == header['year']), Decimal(0))
                self.assertEqual(source_sum, Decimal(header['amount_thousand_rub']))
                checked += 1
        self.assertEqual(checked, 72)

    def test_independently_rounded_manuscript_finance_tables(self):
        finance = self.doc['finance']
        projects = {p['code']: p for p in finance['projects']}
        manuscript_codes = ['Д3', 'Д1', 'Д6', 'Д7', 'Д9', 'Д4', 'Д2', 'Д5', 'Д8', 'ДА', 'ДБ']
        for code, row in zip(manuscript_codes, self.extract['tables'][5]['rows'][1:12]):
            self.assertLessEqual(abs(Decimal(projects[code]['totalThousandRub']) / 1000000 - decimal_cell(row[2])), Decimal('.0005'))
            self.assertLessEqual(abs(Decimal(str(projects[code]['sharePercent'])) - decimal_cell(row[3])), Decimal('.005'))
            self.assertIn(row[1], projects[code]['edition'])
        for source, row in zip(finance['sourceSummaries'], self.extract['tables'][6]['rows'][1:]):
            self.assertLessEqual(abs(Decimal(source['nationalThousandRub']) / 1000000 - decimal_cell(row[1])), Decimal('.0005'))
            self.assertLessEqual(abs(Decimal(str(source['nationalSharePercent'])) - decimal_cell(row[2])), Decimal('.005'))
            self.assertLessEqual(abs(Decimal(source['nationalMinusFederalThousandRub']) / 1000000 - decimal_cell(row[3])), Decimal('.0005'))
        for actual, row in zip(finance['reconciliation'], self.extract['tables'][7]['rows'][1:7]):
            self.assertEqual(actual['year'], int(row[0]))
            for field, value in zip(['nationalThousandRub', 'federalThousandRub', 'nationalMinusFederalThousandRub'], row[1:]):
                self.assertLessEqual(abs(Decimal(actual[field]) / 1000000 - decimal_cell(value)), Decimal('.0005'))
        self.assertAlmostEqual(finance['hhi'], 0.3161542555161044, places=14)

    def test_targets_match_author_plans_and_preserve_source_series(self):
        by_code = {item['code'].replace('2.14.', ''): item for item in self.targets['items']}
        codes = ['Д2.1', 'Д2.2', 'Д2.3', 'Д2.4', 'Д2.5', 'Д4.1', 'Д4.2', 'Д4.3', 'Д7.2', 'ДА.6']
        for code, row in zip(codes, self.extract['tables'][1]['rows'][1:]):
            for year, cell in zip(['2025', '2030'], row[3:]):
                self.assertEqual(Decimal(str(by_code[code]['years'][year])), decimal_cell(cell), (code, year))
        self.assertEqual((len(by_code), self.targets['target_cells'], self.targets['numeric_targets']), (65, 390, 378))
        registry = {r['indicator_code']: r for r in read(DATA / 'indicators.json')['items']}
        for item in self.targets['items']:
            self.assertEqual(item['source_ids'], registry[item['code']].get('source_ids', []))
            if item['code'].startswith('2.14.Д.'):
                self.assertIsNone(item['emiss_id'])
                self.assertFalse(item['formal_comparison_eligible'])
            selected = [v for v in item['versions'] if v['selected']]
            self.assertEqual(len(selected), 1)
            self.assertEqual(item['source_sha256'], selected[0]['source_sha256'])
            for year, value in item['years'].items():
                self.assertEqual(value, selected[0]['years'].get(year))
        self.assertEqual(len(csv_read(DOWNLOAD / 'documentary/targets_all_editions.csv')), 961)
        self.assertEqual(by_code['Д.16']['yearStatus']['2030'], 'not_published_in_selected_source_series')
        self.assertIsNone(by_code['Д.16']['years']['2030'])
        self.assertTrue(any('2030' in v['years'] for v in by_code['Д.16']['versions']))
        proxy = by_code['Д8.3']
        self.assertTrue(proxy['proxy_only'])
        self.assertTrue(proxy['target_is_proxy'])
        self.assertEqual(proxy['emiss_id'], 63151)
        self.assertEqual(proxy['years'], {'2025': 27190769, '2026': None, '2027': None, '2028': None, '2029': None, '2030': None})
        self.assertEqual(proxy['unit'].lower(), 'человек')
        for code in ['Д.19', 'ДБ.1', 'ДБ.3']:
            self.assertEqual(by_code[code]['display_unit'], 'человек на 10 тыс. населения')
        for code in ['ДА.2', 'ДА.3']:
            self.assertEqual(by_code[code]['years']['2025'], 0)
            self.assertEqual(by_code[code]['yearStatus']['2025'], 'documented_target')

    def test_reviewed_links_keep_source_weights_separate_from_causality(self):
        network = self.doc['network']
        direct = network['directReviewed']
        self.assertEqual((len(network['nodes']), len(network['edges']), len(network['sharedTaskLinks']), len(network['semanticCandidates'])), (184, 313, 282, 160))
        self.assertEqual((len(direct['nodes']), len(direct['edges'])), (10, 24))
        expected = [[25, 70, 25, 5, 25, 5], [25, 5, 25, 5, 25, 5], [25, 5, 25, 55, 25, 55], [25, 20, 25, 35, 25, 35]]
        for r, values in enumerate(expected, 1):
            for c, value in enumerate(values, 1):
                edge = next(e for e in direct['edges'] if e['source_node_id'] == f'reviewed_Д2_r{r}' and e['target_node_id'] == f'reviewed_Д2_i{c}')
                self.assertEqual(edge['documentary_weight_percent'], value)
                self.assertEqual(edge['weight'], 1)
                self.assertEqual(edge['pdf_page'], 181 + edge['printed_page'])
                self.assertIn(edge['pdf_page'], [182, 183])
                self.assertFalse(edge['causal_effect'])
                self.assertEqual(edge['source_sha256'], 'f7843029406f2b8587746b2bd11d2c0af8dd84cc0100cbd5f85536c4808f9aa5')
        self.assertEqual(list(direct['columnSums'].values()), [100] * 6)
        self.assertEqual(list(direct['rowSums'].values()), [155, 90, 190, 165])
        self.assertFalse(direct['causal_effect'])
        self.assertEqual(direct['bipartiteDensity'], 1)

    def test_demographic_context_keeps_year_and_source_scope(self):
        context = self.doc['demographicContext']
        self.assertEqual(context, self.expertise['derived']['demographicContext'])
        rows = csv_read(DOWNLOAD / 'documentary/rosstat_life_expectancy_2023.csv')
        self.assertEqual(len(rows), 17)
        self.assertEqual([p['age'] for p in context['ageSex']], list(range(0, 81, 5)))
        for profile, original in zip(context['ageSex'], rows):
            for field, source_field in [('all', 'both_sexes'), ('male', 'male'), ('female', 'female')]:
                self.assertEqual(Decimal(str(profile[field])), Decimal(original[source_field]))
            self.assertEqual(Decimal(str(profile['gap'])), Decimal(original['female']) - Decimal(original['male']))
        self.assertEqual([Decimal(str(p['value'])) for p in context['sexGaps']], [Decimal('10.70'), Decimal('10.60'), Decimal('8.53'), Decimal('5.13'), Decimal('.57')])
        self.assertEqual(context['role'], 'pre_project_context')
        self.assertFalse(context['downloaded_original_pdf'])
        self.assertEqual(context['retrieval_kind'], 'indexed_pdf_text_selected_rows')
        preliminary = next(p for p in context['atBirth'] if p['year'] == 2024)
        source_2024 = read(ROOT / 'public' / preliminary['source_metadata'])
        self.assertTrue(preliminary['preliminary'])
        self.assertEqual(preliminary['geography'], 'Российская Федерация')
        self.assertEqual(preliminary['all'], source_2024['value'])
        self.assertEqual(preliminary['retrieval_kind'], 'indexed_pdf_text_excerpt')
        self.assertFalse(preliminary['downloaded_original_pdf'])
        self.assertEqual(hashlib.sha256((DOWNLOAD / 'documentary' / source_2024['source_excerpt']).read_bytes()).hexdigest(), source_2024['excerpt_sha256'])
        self.assertFalse(next(p for p in context['atBirth'] if p['year'] == 2022)['independently_verified'])

    def test_lazy_text_retains_full_corpus_and_same_genre_boundaries(self):
        text = self.doc['text']
        self.assertEqual(text['units'], [])
        self.assertEqual(text['kwic'], [])
        self.assertEqual(len(text['documentFiles']), 15)
        units = []
        contexts = []
        for entry in text['documentFiles']:
            payload = read(ROOT / 'public' / entry['path'])
            self.assertEqual(payload['document_id'], entry['document_id'])
            self.assertTrue(all(r['document_id'] == entry['document_id'] for r in payload['units']))
            self.assertTrue(all(r['document_id'] == entry['document_id'] for r in payload['kwic']))
            units.extend(payload['units'])
            contexts.extend(payload['kwic'])
        self.assertEqual((len(units), len(contexts)), (4339, 1565))
        self.assertEqual((len(text['sameGenreDocumentIds']), len(text['federalDocumentIds']), len(text['documentSimilarity'])), (12, 11, 66))
        self.assertEqual(text['sameGenreTokenCount'], 9094)
        for row in text['documentSimilarity']:
            self.assertIn(row['document_a'], text['sameGenreDocumentIds'])
            self.assertIn(row['document_b'], text['sameGenreDocumentIds'])
        self.assertEqual(len(text['projectSimilarity']), 9)
        self.assertTrue(all('family' not in [p['project_a'], p['project_b']] for p in text['projectSimilarity']))
        self.assertEqual(len(text['crossGenreProjectSimilarity']), 1)
        self.assertLess((DATA / 'documentary.json').stat().st_size, 6_000_000)
        for frame in text['frameTotals']:
            expected = sum(int(r['count']) for r in self.inputs['tables']['frame_scores'] if r['document_id'] in text['sameGenreDocumentIds'] and r['frame_id'] == frame['frame_id'])
            self.assertEqual(frame['count'], expected)
            self.assertAlmostEqual(frame['per_1000_tokens'], expected / 9094 * 1000, places=12)
        replication = read(DOWNLOAD / 'documentary/text_replication_validation.json')
        self.assertTrue(replication['passed'])
        self.assertEqual((replication['profile_hashes_checked'], replication['numeric_comparisons'], replication['frame_cells_checked']), (137, 825, 270))
        self.assertLess(replication['tfidf_max_abs_error'], 1e-12)
        self.assertEqual(replication['frame_max_abs_error'], 0)
        self.assertEqual(replication['stemming'], 'recomputed')
        self.assertLess(replication['stemming_max_abs_error'], 1e-12)


if __name__ == '__main__':
    unittest.main()
