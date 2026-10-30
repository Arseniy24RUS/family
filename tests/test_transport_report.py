"""Fidelity checks against the immutable Transport source DOCX, not UI snapshots."""
from pathlib import Path
import csv
import hashlib
import json
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT/'public/downloads/projects/efficient_transport/report'
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
SHA = 'fcbf95e7aba2d8c647a1852e8b1241b8af0a542a5056504fe6132b013591e079'


def plain(el):
    return ''.join((node.text or '') if node.tag==f"{{{NS['w']}}}t" else '\n' if node.tag==f"{{{NS['w']}}}br" else '\t' if node.tag==f"{{{NS['w']}}}tab" else '' for node in el.iter()).strip()


class TransportReportFidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expertise=json.loads((ROOT/'public/data/projects/efficient_transport/expertise.json').read_text())
        cls.extracted=json.loads((REPORT/'report_extraction.json').read_text())
        cls.coverage=json.loads((REPORT/'coverage_manifest.json').read_text())
        cls.config=json.loads((ROOT/'inputs/efficient_transport/report/editorial_config.json').read_text())
        cls.docx=REPORT/'expertise_transport_2026.docx'
        cls.html=(REPORT/'expertise_transport_2026.html').read_text()
        cls.xml=zipfile.ZipFile(cls.docx)
        cls.body=ET.fromstring(cls.xml.read('word/document.xml')).find('w:body',NS)
        cls.blocks={b['index']:b for b in cls.extracted['blocks']}

    @classmethod
    def tearDownClass(cls):
        cls.xml.close()

    def test_original_docx_and_every_body_text(self):
        self.assertEqual(hashlib.sha256(self.docx.read_bytes()).hexdigest(),SHA)
        self.assertEqual(self.expertise['meta']['source_docx_sha256'],SHA)
        for i,el in enumerate(self.body):
            if el.tag.endswith('}p'):
                self.assertEqual(self.blocks[i]['text_without_math'],plain(el),f'Original paragraph B{i}')
        self.assertEqual(self.coverage['summary']['source_body_blocks'],440)

    def test_complete_unique_route_coverage_and_source_order(self):
        routes=self.expertise['pages']
        self.assertEqual(len(routes),21)
        assigned=[i for page in routes.values()for i in page['source_blocks']]
        self.assertEqual(len(assigned),len(set(assigned)))
        self.assertEqual(set(assigned),set(range(58,440)))
        actual=list(map(int,re.findall(r'data-source-block="(\d+)"',self.html)))
        self.assertEqual(actual,[i for i in range(440)if i!=10])
        self.assertEqual(self.coverage['summary']['unmapped_substantive_blocks'],[])
        for block in [b for p in routes.values()for b in p['blocks']]:
            if 'sourceBlock' not in block:
                self.assertEqual(block['origin'],'platform_explanation_based_on_report')

    def test_all_table_cells_and_csvs_are_exact(self):
        table_indices=[i for i,el in enumerate(self.body)if el.tag.endswith('}tbl')]
        self.assertEqual(len(table_indices),16)
        for number,i in enumerate(table_indices,1):
            expected=[['\n'.join(plain(p)for p in cell.findall('w:p',NS))for cell in row.findall('w:tc',NS)]for row in self.body[i].findall('w:tr',NS)]
            self.assertEqual(self.blocks[i]['rows'],expected)
            with(REPORT/f'table_{number:02d}.csv').open(encoding='utf-8-sig',newline='')as f:
                self.assertEqual(list(csv.reader(f)),expected)

    def test_all_figures_preserve_original_bytes(self):
        relations={n.attrib['Id']:n.attrib['Target']for n in ET.fromstring(self.xml.read('word/_rels/document.xml.rels'))}
        images=[]
        for el in self.body:
            for img in el.findall('.//a:blip',NS):
                target=relations[img.attrib[f"{{{NS['r']}}}embed"]]
                images.append(self.xml.read('word/'+target if not target.startswith('/')else target[1:]))
        self.assertEqual(len(images),9)
        for number,expected in enumerate(images,1):
            self.assertEqual((REPORT/f'figure_{number:02d}.png').read_bytes(),expected)

    def test_all_footnotes_and_inline_math_are_preserved(self):
        source_notes={int(n.attrib[f"{{{NS['w']}}}id"]):'\n'.join(plain(p)for p in n.findall('w:p',NS)).strip()for n in ET.fromstring(self.xml.read('word/footnotes.xml'))if int(n.attrib[f"{{{NS['w']}}}id"])>0}
        self.assertEqual(len(source_notes),171)
        self.assertEqual({n['id']:n['text']for n in self.extracted['footnotes']},source_notes)
        self.assertEqual(set(map(int,re.findall(r'id="fn-(\d+)"',self.html))),set(source_notes))
        self.assertEqual(self.html.count('<math '),20)
        self.assertEqual(self.html.count('display="block"'),7)
        self.assertEqual(self.html.count('display="inline"'),13)
        self.assertIn('<msup>',self.html)
        self.assertIn('<munder>',self.html)
        self.assertIn('<mfrac>',self.html)
        authored=[b for page in self.expertise['pages'].values()for b in page['blocks']]
        self.assertEqual(sum(b['type']=='formula'for b in authored),7)
        inline=[b for b in authored if b.get('inline_formulas')]
        self.assertEqual(sum(len(b['inline_formulas'])for b in inline),13)
        for b in inline:
            self.assertIn('<math ',b['rich_html'])
            self.assertIn('_{',b['text'])
        source_ids={s['id']for s in self.expertise['sources']}
        for block in authored:
            self.assertTrue(set(block['sourceIds'])<=source_ids,block['id'])


if __name__=='__main__':
    unittest.main()
