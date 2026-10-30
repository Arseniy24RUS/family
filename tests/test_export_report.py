"""Fidelity checks against the immutable Export source DOCX, not UI snapshots."""
from pathlib import Path
import csv
import hashlib
import json
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT/'public/downloads/projects/international_export/report'
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
SHA = '2af8cbdc122dfbaa1c8896def0d2584b9b128ac019d9f00f7752495ea17b1f63'


def plain(el):
    return ''.join((node.text or '') if node.tag==f"{{{NS['w']}}}t" else '\n' if node.tag==f"{{{NS['w']}}}br" else '\t' if node.tag==f"{{{NS['w']}}}tab" else '' for node in el.iter()).strip()


class ExportReportFidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expertise=json.loads((ROOT/'public/data/projects/international_export/expertise.json').read_text())
        cls.extracted=json.loads((REPORT/'report_extraction.json').read_text())
        cls.coverage=json.loads((REPORT/'coverage_manifest.json').read_text())
        cls.config=json.loads((ROOT/'inputs/international_export/report/editorial_config.json').read_text())
        cls.docx=REPORT/'expertise_export_2026.docx'
        cls.html=(REPORT/'expertise_export_2026.html').read_text()
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
        self.assertEqual(self.coverage['summary']['source_body_blocks'],448)

    def test_complete_unique_route_coverage_and_source_order(self):
        routes=self.expertise['pages']
        self.assertEqual(len(routes),21)
        assigned=[i for page in routes.values()for i in page['source_blocks']]
        self.assertEqual(len(assigned),len(set(assigned)))
        self.assertEqual(set(assigned),set(range(64,448)))
        actual=list(map(int,re.findall(r'data-source-block="(\d+)"',self.html)))
        self.assertEqual(actual,list(range(448)))
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
        self.assertEqual(len(images),15)
        for number,expected in enumerate(images,1):
            self.assertEqual((REPORT/f'figure_{number:02d}.png').read_bytes(),expected)

    def test_all_footnotes_and_inline_math_are_preserved(self):
        source_notes={int(n.attrib[f"{{{NS['w']}}}id"]):'\n'.join(plain(p)for p in n.findall('w:p',NS)).strip()for n in ET.fromstring(self.xml.read('word/footnotes.xml'))if int(n.attrib[f"{{{NS['w']}}}id"])>0}
        self.assertEqual(len(source_notes),115)
        self.assertEqual({n['id']:n['text']for n in self.extracted['footnotes']},source_notes)
        self.assertEqual(set(map(int,re.findall(r'id="fn-(\d+)"',self.html))),set(source_notes))
        self.assertEqual(self.html.count('<math '),11)
        self.assertEqual(self.html.count('display="block"'),11)
        self.assertEqual(self.html.count('display="inline"'),0)
        self.assertIn('<msubsup>',self.html)
        self.assertIn('<munder>',self.html)
        self.assertIn('<mfrac>',self.html)
        authored=[b for page in self.expertise['pages'].values()for b in page['blocks']]
        self.assertEqual(sum(b['type']=='formula'for b in authored),11)
        inline=[b for b in authored if b.get('inline_formulas')]
        self.assertEqual(sum(len(b['inline_formulas'])for b in inline),0)
        for b in inline:
            self.assertIn('<math ',b['rich_html'])
            self.assertIn('_{',b['text'])
        source_ids={s['id']for s in self.expertise['sources']}
        for block in authored:
            self.assertTrue(set(block['sourceIds'])<=source_ids,block['id'])

    def test_every_footnote_reference_retains_its_source_block(self):
        for i, element in enumerate(self.body):
            if i not in self.blocks:
                continue
            expected=[int(n.attrib[f"{{{NS['w']}}}id"]) for n in element.findall('.//w:footnoteReference', NS)]
            self.assertEqual(self.blocks[i]['footnotes'],list(dict.fromkeys(expected)))
        for note in self.extracted['footnotes']:
            expected=[i for i,element in enumerate(self.body) if any(int(n.attrib[f"{{{NS['w']}}}id"])==note['id'] for n in element.findall('.//w:footnoteReference',NS))]
            self.assertEqual(note['referenced_by'],expected)

    def test_equation_structure_and_original_numbering(self):
        authored=[b for page in self.expertise['pages'].values()for b in page['blocks']if b['type']=='formula']
        formulas={b['sourceBlock']:b for b in authored}
        self.assertEqual(set(formulas),{149,152,166,173,274,350,397,400,403,413,422})
        self.assertEqual([formulas[i]['number'] for i in sorted(formulas)],list(range(1,12)))
        total_source=Counter()
        total_html=Counter()
        for i,formula in sorted(formulas.items()):
            source=self.body[i].find('.//m:oMath',NS)
            saved=ET.fromstring(formula['original_equation_xml'])
            self.assertEqual(ET.tostring(saved),ET.tostring(source))
            self.assertEqual(plain(self.body[i]),f'({formula["number"]})')
            source_tags=Counter(n.tag.rsplit('}',1)[-1]for n in source.iter())
            html_tree=ET.fromstring(formula['mathml'])
            html_tags=Counter(n.tag.rsplit('}',1)[-1]for n in html_tree.iter())
            total_source.update(source_tags)
            total_html.update(html_tags)
            self.assertEqual(source_tags['f'],html_tags['mfrac'],f'Fractions B{i}')
            self.assertEqual(source_tags['sSub'],html_tags['msub'],f'Subscripts B{i}')
            self.assertEqual(source_tags['sSubSup'],html_tags['msubsup'],f'Subscript/superscript B{i}')
            self.assertEqual(source_tags['rad'],html_tags['mroot']+html_tags['msqrt'],f'Roots B{i}')
            operators=[n.text for n in html_tree.iter()if n.tag.endswith('}mo')]
            self.assertEqual(source_tags['nary'],operators.count('∑'),f'Sum operators B{i}')
            self.assertEqual(source_tags['d'],operators.count('('),f'Opening parentheses B{i}')
            self.assertEqual(source_tags['d'],operators.count(')'),f'Closing parentheses B{i}')
            self.assertEqual(source_tags['acc'],operators.count('̂'),f'Estimation accents B{i}')
            self.assertEqual(source_tags['bar'],operators.count('¯'),f'Mean accents B{i}')
            self.assertIn(f'<span class="formula-number">({formula["number"]})</span>',self.html)
        self.assertEqual(total_source['nary'],9)
        self.assertEqual(total_source['d'],6)
        self.assertEqual(total_source['sSubSup'],5)
        self.assertEqual(total_html['mroot'],1)
        self.assertEqual(total_html['msqrt'],2)
        self.assertEqual(total_source['acc'],2)
        self.assertEqual(total_source['bar'],4)
        self.assertIn('root[5]',self.blocks[274]['text'])
        self.assertIn('100(',self.blocks[152]['text'])
        self.assertIn('hat(τ)=(bar(Y)',self.blocks[422]['text'])

    def test_source_semantics_and_editorial_boundaries(self):
        self.assertEqual(self.expertise['meta']['edition_date'],'2026-10-29')
        self.assertEqual(self.expertise['meta']['statistical_snapshot'],'2026-10-15')
        self.assertEqual(self.expertise['meta']['documentary_snapshot'],'2026-10-16')
        self.assertIsNone(self.expertise['meta']['source_pages'])
        self.assertEqual(len(self.expertise['sources']),116)
        self.assertEqual([p['code']for p in self.expertise['derived']['federalProjects']],['М1','М2','М3','М4'])
        tables={t['number']:t for t in self.expertise['tables']}
        self.assertEqual(len(tables[15]['rows']),21)
        self.assertEqual(len(tables[16]['rows']),47)
        self.assertEqual(tables[16]['note'],'')
        self.assertIn('2026 год',self.blocks[327]['text'])
        self.assertIn('01.09.2026',self.blocks[327]['text'])
        for page in self.expertise['pages'].values():
            self.assertTrue(page['summary'])
            self.assertTrue(page['blocks'])
            for block in page['blocks']:
                if 'sourceBlock' in block:
                    self.assertIn(block['sourceBlock'],page['source_blocks'])


if __name__=='__main__':
    unittest.main()
