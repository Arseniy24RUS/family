"""Meaningful gates for documentary provenance, units and report coverage."""
from pathlib import Path
from decimal import Decimal
import csv, gzip, hashlib, importlib.util, json, tempfile, unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('youth_documentary',ROOT/'scripts/build_youth_documentary.py')
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)

class YouthDocumentaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(ROOT/'public/downloads/projects/youth_children/documentary/documentary_inputs.json.gz','rt',encoding='utf-8') as f:cls.inp=json.load(f)
        cls.doc=json.loads((ROOT/'public/data/projects/youth_children/documentary.json').read_text())
        cls.report=json.loads((ROOT/'public/data/projects/youth_children/expertise.json').read_text())

    def test_one_selected_official_target_edition(self):
        items=MOD.build_targets(self.inp)['items']
        self.assertEqual(len(items),9)
        self.assertTrue(all(set(x['years'])=={str(y) for y in range(2025,2031)} for x in items))
        self.assertTrue(all(x['source_url']==MOD.OFFICIAL for x in items))
        byid={x['emiss_id']:x for x in items}
        self.assertEqual(byid[62935]['years']['2030'],70)
        self.assertEqual(byid[62898]['years']['2028'],14.9)
        self.assertEqual(byid[62898]['years']['2029'],21.1)
        self.assertEqual(byid[62968]['baseline'],{'year':2024,'value':0.0})

    def test_plan_reconciliation_without_transfer_double_count(self):
        result=MOD.build_finance(self.inp)
        self.assertEqual(Decimal(result['totalThousandRub']),Decimal('6181320505.53'))
        self.assertEqual(Decimal(result['differenceThousandRub']),Decimal('3376243.50'))
        self.assertEqual(sum(Decimal(x['differenceThousandRub']) for x in result['reconciliation']),Decimal(result['differenceThousandRub']))
        self.assertEqual(len(result['projects']),9)
        self.assertAlmostEqual(sum(p['sharePercent'] for p in result['projects']),100)
        self.assertAlmostEqual(result['hhi'],0.22357150656842767)
        mutated={**self.inp,'tables':{**self.inp['tables'],'f_cashflows':self.inp['tables']['f_cashflows']+[{'row_type':'document_source','source_name':'nested_transfer','year':'2026','document_level':'federal','amount_thousand_rub':'999999999999'}]}}
        self.assertEqual(MOD.build_finance(mutated)['totalThousandRub'],result['totalThousandRub'])

    def test_documentary_layers_do_not_become_causal_effects(self):
        net=self.doc['network'];ids={x['node_id']for x in net['nodes']}
        self.assertTrue(all(e['source_node_id']in ids and e['target_node_id']in ids for e in net['edges']))
        self.assertEqual(len(net['directReviewed']['edges']),31)
        self.assertTrue(all(e['causal_effect'] is False for e in net['directReviewed']['edges']))
        self.assertTrue(all(e['evidence_class']=='structural_inference' for e in net['sharedTaskLinks']))
        self.assertTrue(all(e['review_status']=='unreviewed' for e in net['semanticCandidates']))
        self.assertEqual(net['coverage']['results_linked_through_documented_task'],116)
        self.assertEqual(net['unresolvedClaimCount'],448)

    def test_same_genre_matrix_and_complete_fixed_corpus(self):
        text=self.doc['text'];federal=set(text['federalDocumentIds'])
        self.assertEqual(len(federal),9);self.assertEqual(len(text['documentSimilarity']),36)
        self.assertTrue(all(r['document_a']in federal and r['document_b']in federal for r in text['documentSimilarity']))
        profiles=self.inp['profiles']['documents'];self.assertEqual(len(profiles),137)
        self.assertTrue(all(hashlib.sha256(d['text'].encode()).hexdigest()==d['profile_text_sha256'] for d in profiles))
        self.assertEqual(len(text['frames']),18)
        self.assertEqual(sum(r['document_id']in federal for r in text['frameScores']),162)

    def test_full_report_coverage_and_citations(self):
        coverage=json.loads((ROOT/'public/downloads/projects/youth_children/report/coverage_manifest.json').read_text())
        self.assertEqual(coverage['summary']['substantive_blocks'],303)
        self.assertEqual(coverage['summary']['unmapped_substantive_blocks'],[])
        self.assertEqual(coverage['summary']['duplicate_assignments'],[])
        relevant=[r for r in coverage['blocks'] if r['sourceBlock']>=54]
        self.assertTrue(all(r['status']in {'rendered_block','embedded_in_rendered_block'}for r in relevant))
        self.assertEqual(len(self.report['tables']),12);self.assertEqual(len(self.report['figures']),17)
        self.assertEqual(len(self.report['sources']),84)
        sources={s['id']for s in self.report['sources']}
        self.assertTrue(all(s in sources for p in self.report['pages'].values() for b in p['blocks'] for s in b.get('sourceIds',[])))
        clarification=next(b for b in self.report['pages']['projections']['blocks']if b['id']=='qualification_targets_precision')
        self.assertIn('14,9%',clarification['text']);self.assertEqual(clarification['source_page'],5)

    def test_core_load_is_small_and_lazy_text_has_all_documents(self):
        self.assertLess((ROOT/'public/data/projects/youth_children/documentary.json').stat().st_size,1_600_000)
        self.assertNotIn('units',self.doc['text']);self.assertNotIn('kwic',self.doc['text'])
        parts=self.doc['text']['documentFiles'];self.assertEqual(len(parts),24)
        self.assertEqual(sum(p['units']for p in parts),11000)
        self.assertEqual(sum(p['kwic']for p in parts),12187)
        self.assertTrue(all((ROOT/'public'/p['path']).is_file()for p in parts))

    def test_downloadable_units_contains_every_original_source_record(self):
        expected=self.inp['tables']['units']
        path=ROOT/'public/downloads/projects/youth_children/documentary/units.csv'
        with path.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);actual=list(reader)
            self.assertEqual(reader.fieldnames,list(expected[0]))
        self.assertEqual(len(expected),11000)
        self.assertEqual(len(actual),len(expected),'The downloadable CSV must retain every original text unit, including its final PDF pages.')
        for i,(got,source) in enumerate(zip(actual,expected),1):
            self.assertEqual(got,{k:'' if v is None else str(v) for k,v in source.items()},f'Source unit row {i}')

    def test_failed_csv_iteration_preserves_previous_target(self):
        class FailingRows(list):
            def __iter__(self):
                yield self[0]
                raise RuntimeError('Simulated interruption after a written source row')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'units.csv';original=b'\xef\xbb\xbfunit_id,text\r\nprevious,verified\r\n';path.write_bytes(original)
            rows=FailingRows([{'unit_id':'one','text':'first'},{'unit_id':'two','text':'second'}])
            with self.assertRaisesRegex(RuntimeError,'Simulated interruption'):MOD.rows_csv(path,rows)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])

    def test_incomplete_csv_iterator_cannot_replace_previous_target(self):
        class IncompleteRows(list):
            def __iter__(self):return iter(self[:1])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'units.csv';original=b'\xef\xbb\xbfunit_id,text\r\nprevious,verified\r\n';path.write_bytes(original)
            rows=IncompleteRows([{'unit_id':'one','text':'first'},{'unit_id':'two','text':'second'}])
            with self.assertRaisesRegex(ValueError,'CSV row count mismatch'):MOD.rows_csv(path,rows)
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])

if __name__=='__main__':unittest.main()
