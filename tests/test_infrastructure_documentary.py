"""Source-oriented acceptance checks for Infrastructure for Life.

The expected source cells are read from the original DOCX / HTML bytes.
They are not reconstructed with the publishing builder under test.
"""
from pathlib import Path
from decimal import Decimal
import collections, hashlib, json, re, sys, unittest, zipfile
import xml.etree.ElementTree as ET
from lxml import html

ROOT=Path(__file__).resolve().parents[1]
PROJECT='life_infrastructure'
sys.path.insert(0,str(ROOT/'scripts'))
from build_infrastructure_documentary import build_budget


def load(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def ws(value):
    return re.sub(r'\s+',' ',str(value)).strip()


def dec(value):
    return Decimal(ws(value).replace(' ','').replace(',','.'))


class InfrastructureDocumentaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=load(f'public/data/projects/{PROJECT}/documentary.json')
        cls.full=load(f'public/downloads/projects/{PROJECT}/documentary/documentary_full.json')
        cls.expert=load(f'public/data/projects/{PROJECT}/expertise.json')
        cls.report=load(f'public/downloads/projects/{PROJECT}/report/report_extraction.json')
        cls.manifest=load('inputs/infrastructure/documentary/source_manifest.json')
        cls.sources={};cls.trees={}
        with zipfile.ZipFile(ROOT/cls.manifest['archive_path']) as z:
            for source in cls.manifest['documents']:
                if source['project_id']==PROJECT:
                    raw=z.read(source['archive_entry'])
                    cls.sources[source['document_id']]=(source,raw)
                    cls.trees[source['document_id']]=html.fromstring(raw).getroottree()

    def test_original_docx_and_every_substantive_block_are_preserved(self):
        p=ROOT/f'public/downloads/projects/{PROJECT}/report/expertise_infrastructure_2026.docx'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'2098f0b0b25b2539f693d80ddc1e7f76a3502f1d5c9dac4994109a4f930938c4')
        coverage=load(f'public/downloads/projects/{PROJECT}/report/coverage_manifest.json')
        summary=coverage['summary']
        self.assertEqual((summary['substantive_blocks'],summary['assigned_blocks'],summary['report_pages']),(271,271,76))
        self.assertEqual(summary['unmapped_substantive_blocks'],[])
        self.assertEqual(summary['duplicate_assignments'],[])
        self.assertEqual((summary['routes'],summary['tables'],summary['figures'],summary['footnotes'],summary['formulas']),(21,11,12,91,5))
        rendered=[b for page in self.expert['pages'].values() for b in page['blocks']]
        source_texts={b['text'] for b in rendered if b.get('text')}
        source_texts|={v for b in rendered for key in ['title','note'] if (v:=b.get(key))}
        for b in self.report['blocks']:
            if b['index']<45 or b['type']!='paragraph' or not b['text'] or b['equations']:
                continue
            self.assertIn(b['text'],source_texts,f"Lost original paragraph {b['index']}")

    def test_all_five_formulas_retain_verified_source_and_latex(self):
        formulas=[b for p in self.expert['pages'].values() for b in p['blocks'] if b['type']=='formula']
        self.assertEqual(sorted(f['page'] for f in formulas),[45,45,62,66,68])
        self.assertEqual({f['number'] for f in formulas},{1,2,3,4,5})
        self.assertTrue(all(f['latex'] and f['original_equation_text'] for f in formulas))
        self.assertIn('V_T',next(f['latex'] for f in formulas if f['number']==5))

    def test_original_figures_are_exact_bytes(self):
        for fig in self.expert['figures']:
            p=ROOT/'public'/fig['url']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),fig['original_sha256'])

    def test_tables_preserve_every_original_cell(self):
        self.assertEqual(len(self.expert['tables']),11)
        for raw,published in zip(self.report['tables'],self.expert['tables']):
            actual=[[c['label'] for c in published['columns']]]
            actual.extend([[row[c['key']] for c in published['columns']] for row in published['rows']])
            self.assertEqual(actual,raw['rows'])
            self.assertEqual(len(published['cellSourceIds']),len(published['rows']))
            for refs in [published['headerSourceIds'],*published['cellSourceIds']]:
                for cell in refs:
                    for note in cell:self.assertIn(note,published['sourceIds'])

    def test_every_footnote_has_source_block_and_usable_url(self):
        notes={s['note_number']:s for s in self.expert['sources'] if s.get('note_number')}
        self.assertEqual(len(notes),91)
        for note in self.report['footnotes']:
            out=notes[note['id']]
            self.assertEqual(out['text'],note['text'])
            self.assertEqual(out['source_blocks'],[f'b{i}' for i in note['referenced_by']])
            self.assertTrue(out['source_blocks'])
            for url in out['urls']:
                self.assertRegex(url,r'^https?://')
                self.assertNotRegex(url,'[\u200b\u2060\ufeff]')
        self.assertTrue(all(c['route'] in self.expert['pages'] and c['title'] for c in self.expert['meta']['source_clarifications']))

    def test_shared_corpus_bytes_and_project_source_downloads_match(self):
        archive=ROOT/self.manifest['archive_path']
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),self.manifest['archive_sha256'])
        shared_download=ROOT/'public'/self.manifest['shared_archive_download']
        self.assertEqual(shared_download.read_bytes(),archive.read_bytes())
        self.assertEqual(self.doc['downloads']['sources'],self.manifest['shared_archive_download'])
        with zipfile.ZipFile(archive) as z:
            for meta in self.manifest['documents']:
                self.assertEqual(hashlib.sha256(z.read(meta['archive_entry'])).hexdigest(),meta['sha256'])
        self.assertEqual(len(self.manifest['documents']),98)
        self.assertEqual(len(self.sources),13)
        for meta,raw in self.sources.values():
            self.assertEqual((ROOT/'public'/meta['download_path']).read_bytes(),raw)

    def test_source_titles_resolve_to_h1(self):
        for meta in self.doc['sources']:
            self.assertEqual(meta['title'],ws(self.trees[meta['document_id']].xpath('//h1')[0].text_content()))

    def test_all_969_passport_target_cells_resolve_to_original_html(self):
        cards=self.full['targets']['allCards'];self.assertEqual(len(cards),51)
        count=0
        for card in cards:
            tree=self.trees[card['source_document']]
            self.assertEqual(len(tree.xpath(card['source_locator'])),1)
            for year,raw in card['raw_years'].items():
                cell=tree.xpath(raw['source_locator'])[0]
                labels=cell.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-purpose-year ")]')
                values=cell.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-purpose-year-val ")]')
                self.assertEqual(ws(labels[0].text_content()),year)
                txt=ws(values[0].text_content())
                self.assertEqual(txt,raw['value_raw'])
                if raw['value_decimal'] is None:self.assertIn(txt,['—','–','-',''])
                else:self.assertEqual(dec(txt),Decimal(raw['value_decimal']))
                count+=1
        self.assertEqual(count,969)

    def test_target_selection_preserves_scope_and_unmapped_military_card(self):
        t=self.full['targets'];self.assertEqual((t['target_cells'],t['numeric_targets'],t['missing_targets']),(192,188,4))
        self.assertEqual(len({x['indicator_code'] for x in t['items']}),32)
        housing=next(x for x in t['items'] if x['indicator_code']=='2.14.И.4')
        self.assertEqual(housing['source_id'],'59263')
        self.assertEqual(housing['document_level'],'national')
        military=[x for x in t['allCards'] if x['indicator_code'] is None]
        self.assertEqual(len(military),1)
        self.assertIn('Минобороны',military[0]['title'])
        self.assertIsNone(military[0]['source_id'])
        self.assertEqual(military[0]['mapping_status'],'outside_inherited_registry')

    def test_all_524_financial_source_cells_resolve_to_original_html(self):
        rows=self.full['finance']['sourceRows'];self.assertEqual(len(rows),524)
        for row in rows:
            cell=self.trees[row['document_id']].xpath(row['source_locator'])[0]
            value=cell.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-passport-year-value ")]')[0]
            self.assertEqual(ws(value.text_content()),row['value_raw'])
            self.assertEqual(dec(value.text_content()),Decimal(row['amount_decimal']))

    def test_finance_horizon_and_reconciliation_use_exact_decimal_values(self):
        f=self.full['finance'];rows=[r for r in f['sourceRows'] if r['scope']=='document' and 2025<=r['year']<=2030]
        np=sum((Decimal(r['amount_decimal']) for r in rows if r['fp']=='И'),Decimal(0))
        fp=sum((Decimal(r['amount_decimal']) for r in rows if r['fp']!='И'),Decimal(0))
        self.assertEqual(np,Decimal('15094430617.02'));self.assertEqual(fp,Decimal('15098801767.71'))
        self.assertEqual(fp-np,Decimal('4371150.69'))
        self.assertEqual([r['difference_decimal'] for r in f['reconciliation']],['1075233.19','1552183.40','1743734.10','0.00','0.00','0.00'])
        extended=[r for r in f['horizonSummaries'] if r['first_year']==2031 and r['amount_decimal'] is not None]
        self.assertEqual({r['code'] for r in extended},{'И2','И4'})
        self.assertEqual(sum((Decimal(r['amount_decimal']) for r in extended),Decimal(0)),Decimal('801130068'))
        self.assertTrue(all(not r['included_in_national_reconciliation'] for r in extended))

    def test_subcomponents_and_result_totals_do_not_double_count(self):
        f=self.full['finance'];sub=[r for r in f['sourceRows'] if r['is_subcomponent']]
        self.assertEqual(len(sub),61)
        self.assertTrue(all(not r['included_in_additive_total'] for r in sub))
        for total in f['resultSums']:
            rows=[r for r in f['resultYears'] if r['result_id']==total['result_id'] and r['year']<=2030 and r['included_in_additive_total']]
            self.assertEqual(sum((Decimal(r['amount_decimal']) for r in rows),Decimal(0)),Decimal(total['amount_decimal']))
        mortgage=[r for r in f['fpYears'] if r['code']=='ИБ']
        self.assertEqual(len(mortgage),6)
        self.assertTrue(all(r['amount_thousand_rub'] is None and r['missing_reason'] for r in mortgage))

    def test_every_result_finance_cell_belongs_to_exact_unique_card(self):
        nodes={n['node_id']:n for n in self.doc['network']['nodes'] if n['kind']=='result'}
        for row in self.full['finance']['resultYears']:
            node=nodes[row['result_id']]
            self.assertEqual(node['source_locator'],row['source_result_locator'])
            self.assertEqual(node['source_card_id'],row['source_result_card_id'])
            self.assertEqual(node['title'],row['result_title'])
            tree=self.trees[row['document_id']]
            card=tree.xpath(node['source_locator'])[0];cell=tree.xpath(row['source_locator'])[0]
            self.assertIn(card,list(cell.iterancestors()))

    def test_budget_header_is_never_a_numeric_observation(self):
        b=build_budget(ROOT,ROOT/'inputs/infrastructure/documentary')
        self.assertEqual(b['published_numeric_cells'],268)
        self.assertTrue(all(not re.fullmatch(r'\d+',r['name']) for r in b['rows']))
        self.assertTrue(all('/tr[3]/' not in r['source_locator'] for r in b['rows']))
        self.assertEqual(len(b['projectRows']),44)
        self.assertEqual(len(b['totals']),4)

    def test_all_268_budget_cells_and_period_status_resolve_to_original_html(self):
        b=self.full['finance']['budgetBill'];p=ROOT/b['source_input_path']
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),b['source_html_sha256'])
        tree=html.parse(str(p));self.assertEqual(len(b['rows']),268)
        for row in b['rows']:
            self.assertEqual(dec(tree.xpath(row['source_locator'])[0].text_content()),Decimal(row['amount_decimal']))
            self.assertEqual(row['kind'],'budget_allocation' if row['year']==2026 else 'budget_bill')
        self.assertEqual([r['amount_decimal'] for r in b['totals']],['1304889.3','1413125.1','1759332.5','1439537.7'])
        self.assertAlmostEqual(next(r['share_percent'] for r in b['roadShares'] if r['year']==2027),83.888192206,places=8)

    def test_complete_node_census_preserves_repeated_task_scope_and_goals(self):
        network=self.doc['network'];nodes=network['nodes']
        self.assertEqual(len(nodes),191);self.assertEqual(len({r['node_id'] for r in nodes}),191)
        self.assertEqual(collections.Counter(n['kind'] for n in nodes),{'result':85,'indicator':51,'task':42,'goal':13})
        tasks=[n for n in nodes if n['kind']=='task']
        self.assertEqual(collections.Counter(n['record_scope'] for n in tasks),{'standalone_task_card':26,'national_structure_federal_task_restatement':16})
        for n in nodes:
            tree=self.trees[n['document_id']];self.assertEqual(len(tree.xpath(n['source_locator'])),1)
            if n.get('record_scope') in ['document_goal','national_structure_federal_task_restatement']:
                self.assertEqual(n['title'],ws(tree.xpath(n['source_value_locator'])[0].text_content()))
        duplicates=[n for n in nodes if n['document_id']=='fp_262' and n['source_card_id']=='passport-result-37']
        self.assertEqual(len(duplicates),4)
        self.assertEqual(len({n['node_id'] for n in duplicates}),4)

    def test_shared_task_pairs_do_not_become_direct_causal_edges(self):
        network=self.doc['network'];nodes={n['node_id']:n for n in network['nodes']}
        self.assertEqual((len(network['sharedTaskPairs']),len(network['sameProjectPairs']),len(network['semanticCandidates'])),(266,300,300))
        self.assertEqual(network['reviewedEdges'],[]);self.assertEqual(network['directLinks'],[])
        for pair in network['sharedTaskPairs']:
            a,b=nodes[pair['result_node_id']],nodes[pair['indicator_node_id']]
            self.assertEqual(a['document_id'],b['document_id'])
            self.assertEqual(a['task_node_id'],b['task_node_id'])
            self.assertEqual(a['task_node_id'],pair['task_node_id'])
            self.assertTrue(nodes[pair['task_node_id']]['membership_eligible'])
            self.assertEqual(pair['evidence_class'],'same_document_task_membership')
        for pair in network['semanticCandidates']:
            self.assertIsNone(pair['official_weight']);self.assertEqual(pair['evidence_class'],'semantic_candidate')
        self.assertEqual(len(network['unresolvedClaims']),160)
        self.assertTrue(all(r['indicator_node_id'] is None for r in network['unresolvedClaims']))

    def test_contexts_are_verbatim_and_counts_match_all_13_documents(self):
        t=self.doc['text'];count=0
        self.assertEqual(len(t['documentFiles']),13)
        for docid,path in t['documentFiles'].items():
            payload=load('public/'+path);units={u['unit_id']:u for u in payload['units']}
            for context in payload['contexts']:
                unit=units[context['unit_id']]
                self.assertEqual(context['context'],unit['text'])
                self.assertEqual(context['source_locator'],unit['source_locator'])
                cell=self.trees[docid].xpath(context['source_locator'])[0]
                self.assertIn(unit['text'],ws(cell.text_content()))
                count+=1
        self.assertEqual(count,605);self.assertEqual(count,t['contextCount'])
        self.assertEqual(count,sum(r['count'] for r in t['frameScores']))

    def test_independent_text_results_are_not_labelled_exact_replication(self):
        text=self.doc['text'];audit={r['metric']:r for r in text['replicationAudit']}
        self.assertFalse(text['authorExactCodeAvailable'])
        self.assertEqual((audit['infrastructure_tokens']['author_report'],audit['infrastructure_tokens']['platform_recomputed']),(5889,5886))
        self.assertFalse(audit['features']['equal'])
        self.assertEqual(audit['features']['author_report'],46519)
        self.assertTrue(all(r['top3'][0]=='Эффективная транспортная система' for r in text['sensitivity']))
        self.assertAlmostEqual(next(r['spearman'] for r in text['sensitivity'] if r['variant']=='equal_levels'),0.690909090909091)
        self.assertIn('no extra within-level normalization',text['method']['equal_levels_formula'])

    def test_light_runtime_omissions_are_available_in_full_export(self):
        for key in ['sourceRows','resultYears']:
            self.assertNotIn(key,self.doc['finance']);self.assertIn(key,self.full['finance'])
        self.assertNotIn('allCards',self.doc['targets']);self.assertEqual(len(self.full['targets']['allCards']),51)
        self.assertNotIn('rows',self.doc['finance']['budgetBill'])
        self.assertEqual(self.doc['meta']['full_export_url'],f'downloads/projects/{PROJECT}/documentary/documentary_full.json')
        for key,path in self.doc['downloads'].items():
            if key=='code':continue
            self.assertTrue((ROOT/'public'/path).is_file(),path)


if __name__=='__main__':
    unittest.main()
