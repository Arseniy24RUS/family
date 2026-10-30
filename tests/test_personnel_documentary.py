"""Independent source consistency checks for the Personnel publication."""
from pathlib import Path
from decimal import Decimal
import hashlib,json,re,unittest,zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'public/data/projects/personnel'
DOWNLOAD=ROOT/'public/downloads/projects/personnel'

class PersonnelDocumentaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=json.loads((DATA/'documentary.json').read_text())
        cls.targets=json.loads((DATA/'targets.json').read_text())
        cls.extract=json.loads((DOWNLOAD/'report/report_extraction.json').read_text())
        cls.coverage=json.loads((DOWNLOAD/'report/coverage_manifest.json').read_text())

    def test_source_bytes_match_original_manifest(self):
        manifest=json.loads((DOWNLOAD/'documentary/source_manifest.json').read_text())
        for source in manifest['documents']:
            with self.subTest(source=source['title']):
                p=ROOT/'public'/source['download_path']
                self.assertEqual(p.stat().st_size,source['size_bytes'])
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),source['source_sha256'])
        p=DOWNLOAD/'report/expertise_personnel_2026.docx'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'d459f1011cf3525100bc800e2d71f473bf49ec7c5cf34f85a552c428c762299b')

    def test_report_words_notes_and_coverage_are_preserved(self):
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        plain=lambda s:re.sub(r'\s+','',s)
        with zipfile.ZipFile(DOWNLOAD/'report/expertise_personnel_2026.docx') as z:
            body=ET.fromstring(z.read('word/document.xml')).find('w:body',ns)
            original=[''.join(n.text or '' for n in p.findall('.//w:t',ns)) for p in body.findall('w:p',ns)]
            parsed=[b['text'] for b in self.extract['blocks'] if b['type']=='paragraph']
            self.assertEqual([plain(s) for s in original],[plain(s) for s in parsed])
            notes=ET.fromstring(z.read('word/footnotes.xml'))
            originals={int(n.attrib['{'+ns['w']+'}id']):''.join(t.text or '' for t in n.findall('.//w:t',ns)) for n in notes if int(n.attrib['{'+ns['w']+'}id'])>0}
            self.assertEqual({k:plain(v) for k,v in originals.items()},{x['id']:plain(x['text']) for x in self.extract['footnotes']})
        included=[b for b in self.coverage['blocks'] if b['sourceBlock']>=53]
        self.assertEqual(len(included),352)
        self.assertTrue(all(b['route'] for b in included))
        self.assertEqual(self.coverage['summary']['unmapped_substantive_blocks'],[])
        self.assertEqual(self.coverage['summary']['duplicate_assignments'],[])

    def test_selected_targets_match_author_table_and_keep_uncertainty(self):
        table=self.extract['tables'][2]['rows'][1:]
        by_code={x['code'].replace('2.14.',''):x for x in self.targets['items']}
        for row in table:
            item=by_code[row[0]]
            for year,raw in zip(['2025','2026','2030'],row[2:]):
                expected=None if raw=='–' else float(raw.replace(',','.').replace('*',''))
                self.assertEqual(item['years'][year],expected,(item['code'],year))
        self.assertEqual(by_code['Л1.1']['yearStatus']['2030'],'ambiguous_zero_target_requires_interpretation')
        self.assertFalse(by_code['Л1.1']['formal_comparison_eligible'])
        self.assertEqual(by_code['Л1.2']['mapping_status'],'conditional')
        self.assertFalse(by_code['Л1.2']['formal_comparison_eligible'])
        early=[v for v in by_code['Л3.2']['versions'] if not v['selected']]
        self.assertTrue(any(v['years'].get('2025')==0.6 for v in early))
        self.assertEqual(by_code['Л3.2']['years']['2025'],0.27)

    def test_finance_independently_reconciles_common_and_full_horizons(self):
        f=self.doc['finance'];common=Decimal(0);full=Decimal(0)
        for p in f['projects']:
            cells=p['fullYears'];self.assertEqual([r['year'] for r in cells],list(range(2025,2037)))
            common+=sum(Decimal(r['amountThousandRub']) for r in cells if r['year']<=2030)
            full+=sum(Decimal(r['amountThousandRub']) for r in cells)
        self.assertEqual(common,Decimal('178800951.31'))
        self.assertEqual(full,Decimal('298194619.61'))
        self.assertEqual(full-common,Decimal('119393668.30'))
        self.assertEqual(common-Decimal(f['nationalThousandRub']),Decimal('1469341.60'))
        self.assertEqual([Decimal(r['differenceThousandRub']) for r in f['reconciliation']],[Decimal('1469341.60')]+[Decimal(0)]*5)
        # Compare independently rounded manuscript table, not copied builder output.
        for row in self.extract['tables'][11]['rows'][1:5]:
            p=next(x for x in f['projects'] if x['code']==row[0])
            for cell,raw in zip(p['years'],row[1:7]):
                self.assertLessEqual(abs(Decimal(cell['amountThousandRub'])/Decimal(10**6)-Decimal(raw.replace(',','.'))),Decimal('.0005'))

    def test_direct_links_match_author_review_and_remain_documentary(self):
        links=self.doc['network']['directReviewed'];rows=self.extract['tables'][6]['rows'][1:]
        self.assertEqual(len(links['edges']),len(rows))
        for edge,row in zip(links['edges'],rows):
            self.assertEqual(edge['documentary_weight_percent'],int(row[1]))
            self.assertEqual(edge['printed_page'],int(row[2]))
            self.assertEqual(edge['pdf_page'],154+int(row[2]))
            self.assertFalse(edge['causal_effect'])
        self.assertEqual(sum(x['documentary_weight_percent'] for x in links['edges']),100)
        self.assertEqual(len({x['target_node_id'] for x in links['edges']}),1)
        self.assertFalse(links['causal_effect'])

    def test_lazy_text_is_complete_without_automatic_full_corpus(self):
        t=self.doc['text'];self.assertEqual(t['units'],[]);self.assertEqual(t['kwic'],[])
        units=kwic=0
        for item in t['documentFiles']:
            payload=json.loads((ROOT/'public'/item['path']).read_text())
            self.assertEqual(payload['document_id'],item['document_id'])
            self.assertTrue(all(x['document_id']==item['document_id'] for x in payload['units']))
            self.assertTrue(all(x['document_id']==item['document_id'] for x in payload['kwic']))
            units+=len(payload['units']);kwic+=len(payload['kwic'])
        self.assertEqual(units,1769);self.assertEqual(kwic,1018)
        self.assertLess((DATA/'documentary.json').stat().st_size,2_000_000)
        self.assertEqual(len(t['federalDocumentIds']),4)
        self.assertEqual(len(t['documentSimilarity']),6)

if __name__=='__main__':unittest.main()
