"""Source-oriented acceptance checks for Ecological Well-being.

The expected source cells are read from the original DOCX / HTML bytes.
They are not reconstructed with the publishing builder under test.
"""
from pathlib import Path
from decimal import Decimal
import collections, hashlib, json, re, sys, unittest, zipfile
import xml.etree.ElementTree as ET
from lxml import html

ROOT=Path(__file__).resolve().parents[1]
PROJECT='environment'
sys.path.insert(0,str(ROOT/'scripts'))
from build_environment_documentary import build_budget


def load(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def ws(value):
    return re.sub(r'\s+',' ',str(value)).strip()


def dec(value):
    return Decimal(ws(value).replace(' ','').replace(',','.'))


class EnvironmentDocumentaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc=load(f'public/data/projects/{PROJECT}/documentary.json')
        cls.full=load(f'public/downloads/projects/{PROJECT}/documentary/documentary_full.json')
        cls.expert=load(f'public/data/projects/{PROJECT}/expertise.json')
        cls.report=load(f'public/downloads/projects/{PROJECT}/report/report_extraction.json')
        cls.manifest=load('inputs/environment/documentary/source_manifest.json')
        cls.sources={};cls.trees={}
        with zipfile.ZipFile(ROOT/cls.manifest['archive_path']) as z:
            for source in cls.manifest['documents']:
                if source['project_id']==PROJECT:
                    raw=z.read(source['archive_entry'])
                    cls.sources[source['document_id']]=(source,raw)
                    cls.trees[source['document_id']]=html.fromstring(raw).getroottree()

    def test_original_docx_and_every_substantive_block_are_preserved(self):
        p=ROOT/f'public/downloads/projects/{PROJECT}/report/expertise_environment_2026.docx'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'d5adb758afb0d75b8d599a563711e0c6ee42f3e7e5fcf5d754a4ed705b2ccabb')
        coverage=load(f'public/downloads/projects/{PROJECT}/report/coverage_manifest.json')
        summary=coverage['summary']
        self.assertEqual((summary['substantive_blocks'],summary['assigned_blocks'],summary['report_pages']),(285,285,84))
        self.assertEqual(summary['unmapped_substantive_blocks'],[])
        self.assertEqual(summary['duplicate_assignments'],[])
        self.assertEqual((summary['routes'],summary['tables'],summary['figures'],summary['footnotes'],summary['formulas']),(21,10,12,112,3))
        rendered=[b for page in self.expert['pages'].values() for b in page['blocks']]
        source_texts={b['text'] for b in rendered if b.get('text')}
        source_texts|={v for b in rendered for key in ['title','note'] if (v:=b.get(key))}
        for b in self.report['blocks']:
            if b['index']<44 or b['type']!='paragraph' or not b['text'] or b['equations']:
                continue
            self.assertIn(b['text'],source_texts,f"Lost original paragraph {b['index']}")

    def test_all_three_formulas_retain_verified_source_and_latex(self):
        formulas=[b for page in self.expert['pages'].values() for b in page['blocks'] if b['type']=='formula']
        self.assertEqual(sorted(f['page'] for f in formulas),[55,56,72])
        self.assertEqual({f['number'] for f in formulas},{1,2,3})
        self.assertTrue(all(f['latex'] and f['original_equation_text'] for f in formulas))
        exposure=next(f for f in formulas if f['number']==3)
        self.assertIn(r'\overline{C}_p',exposure['latex'])
        self.assertIn(r'\sum_i N_i C_{ip}',exposure['latex'])
        self.assertIn(r'{\sum_i N_i}',exposure['latex'])

    def test_original_figures_are_exact_bytes(self):
        for fig in self.expert['figures']:
            p=ROOT/'public'/fig['url']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),fig['original_sha256'])

    def test_tables_preserve_every_original_cell(self):
        self.assertEqual(len(self.expert['tables']),10)
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
        self.assertEqual(len(notes),112)
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
        self.assertEqual(len(self.sources),7)
        for meta,raw in self.sources.values():
            self.assertEqual((ROOT/'public'/meta['download_path']).read_bytes(),raw)

    def test_source_titles_resolve_to_h1(self):
        for meta in self.doc['sources']:
            self.assertEqual(meta['title'],ws(self.trees[meta['document_id']].xpath('//h1')[0].text_content()))

    def test_all_475_passport_target_cells_resolve_to_original_html(self):
        cards=self.full['targets']['allCards'];self.assertEqual(len(cards),25)
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
        self.assertEqual(count,475)

    def test_target_selection_preserves_scope_and_discontinued_fire_card(self):
        t=self.full['targets']
        self.assertEqual((t['target_cells'],t['numeric_targets'],t['missing_targets']),(108,100,8))
        self.assertEqual(len({x['indicator_code'] for x in t['items']}),18)
        for c in t['items']:
            alternatives=[a for a in t['allCards'] if a['indicator_code']==c['indicator_code']]
            if any(a['document_level']=='national' for a in alternatives):self.assertEqual(c['document_level'],'national')
        fire=next(x for x in t['items'] if x['source_id']=='62779')
        self.assertEqual(fire['years']['2025'],46.2)
        self.assertTrue(all(fire['years'][str(y)] is None for y in range(2026,2031)))
        self.assertEqual(fire['execution_status'],'discontinued_in_source_card')
        self.assertEqual(fire['cessation_date'],'21.05.2026')
        self.assertEqual(fire['cessation_date_basis'],'passport_metadata_not_legal_order_date')
        self.assertEqual(fire['target_comparison_status'],'historical_card_no_current_target_conclusion')

    def test_all_507_financial_source_cells_resolve_to_original_html(self):
        rows=self.full['finance']['sourceRows'];self.assertEqual(len(rows),507)
        for row in rows:
            cell=self.trees[row['document_id']].xpath(row['source_locator'])[0]
            value=cell.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-passport-year-value ")]')[0]
            self.assertEqual(ws(value.text_content()),row['value_raw'])
            self.assertEqual(dec(value.text_content()),Decimal(row['amount_decimal']))

    def test_finance_horizon_and_reconciliation_use_exact_decimal_values(self):
        f=self.full['finance'];rows=[r for r in f['sourceRows'] if r['scope']=='document' and r['included_in_additive_total'] and 2025<=r['year']<=2030]
        national=sum((Decimal(r['amount_decimal']) for r in rows if r['fp']=='Ч'),Decimal(0))
        federal=sum((Decimal(r['amount_decimal']) for r in rows if r['fp']!='Ч'),Decimal(0))
        self.assertEqual(national,Decimal('1519365026.42'))
        self.assertEqual(federal,Decimal('1519117214.38'))
        self.assertEqual(federal-national,Decimal('-247812.04'))
        self.assertEqual([r['difference_decimal'] for r in f['reconciliation']],['-247812.04','0.00','0.00','0.00','0.00','0.00'])
        extended=[r for r in f['horizonSummaries'] if r['first_year']==2031]
        self.assertEqual(len(extended),7)
        self.assertTrue(all(r['amount_decimal'] is None and not r['included_in_national_reconciliation'] for r in extended))
        self.assertEqual(len(f['fpYears']),36)
        self.assertEqual(len(f['sourceYears']),108)
        self.assertEqual(sum((Decimal(r['amount_decimal']) for r in f['sourceSummaries']),Decimal(0)),national)

    def test_subcomponents_and_result_totals_do_not_double_count(self):
        f=self.full['finance'];sub=[r for r in f['sourceRows'] if r['is_subcomponent']]
        self.assertEqual(len(sub),70)
        self.assertTrue(all(not r['included_in_additive_total'] for r in sub))
        for total in f['resultSums']:
            rows=[r for r in f['resultYears'] if r['result_id']==total['result_id'] and r['year']<=2030 and r['included_in_additive_total']]
            self.assertEqual(sum((Decimal(r['amount_decimal']) for r in rows),Decimal(0)),Decimal(total['amount_decimal']))
        missing=[r for r in f['sourceYears'] if r['amount_decimal'] is None]
        self.assertTrue(missing)
        self.assertTrue(all(r['amount_thousand_rub'] is None and r['missing_reason'] for r in missing))

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
        b=build_budget(ROOT,ROOT/'inputs/environment/documentary')
        self.assertEqual(b['published_numeric_cells'],288)
        self.assertTrue(all(not re.fullmatch(r'\d+',r['name']) for r in b['rows']))
        self.assertTrue(all('/tr[3]/' not in r['source_locator'] for r in b['rows']))
        self.assertEqual(len(b['projectRows']),24)
        self.assertEqual(len(b['totals']),4)

    def test_all_288_budget_cells_and_period_status_resolve_to_original_html(self):
        b=self.full['finance']['budgetBill'];p=ROOT/b['source_input_path']
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),b['source_html_sha256'])
        tree=html.parse(str(p));self.assertEqual(len(b['rows']),288)
        for row in b['rows']:
            self.assertEqual(dec(tree.xpath(row['source_locator'])[0].text_content()),Decimal(row['amount_decimal']))
            self.assertEqual(row['kind'],'budget_allocation' if row['year']==2026 else 'budget_bill')
        self.assertEqual([r['amount_decimal'] for r in b['totals']],['75013.1','84801.5','147022.6','126446.0'])
        for r in b['directionShares']:
            value=dec(tree.xpath(r['source_locator'])[0].text_content())
            denominator=dec(tree.xpath(r['denominator_locator'])[0].text_content())
            self.assertAlmostEqual(float(value/denominator*100),r['share_percent'],places=10)
        reserve=next(r for r in b['directionShares'] if r['id']=='remediation_reserve' and r['year']==2029)
        self.assertEqual(reserve['amount_decimal'],'19184.9')
        self.assertAlmostEqual(reserve['share_percent'],89.48932279762293)
        for r in b['reconciliation']:
            total=dec(tree.xpath(r['total_locator'])[0].text_content())
            children=sum((dec(tree.xpath(x)[0].text_content()) for x in r['child_locators']),Decimal(0))
            self.assertEqual(str(children-total),r['child_minus_published_decimal'])
            self.assertLessEqual(abs(children-total),Decimal('0.2'))

    def test_complete_node_census_preserves_repeated_task_scope_and_goals(self):
        nodes=self.doc['network']['nodes']
        self.assertEqual(len(nodes),149);self.assertEqual(len({r['node_id'] for r in nodes}),149)
        self.assertEqual(collections.Counter(n['kind'] for n in nodes),{'result':89,'indicator':25,'task':28,'goal':7})
        tasks=[n for n in nodes if n['kind']=='task']
        self.assertEqual(collections.Counter(n['record_scope'] for n in tasks),{'standalone_task_card':17,'national_structure_federal_task_restatement':11})
        for n in nodes:
            tree=self.trees[n['document_id']];self.assertEqual(len(tree.xpath(n['source_locator'])),1)
            if n.get('record_scope') in ['document_goal','national_structure_federal_task_restatement']:
                self.assertEqual(n['title'],ws(tree.xpath(n['source_value_locator'])[0].text_content()))
        duplicates=[n for n in nodes if n['document_id']=='fp_247' and n['source_card_id']=='passport-result-37']
        self.assertEqual(len(duplicates),4)
        self.assertEqual(len({n['node_id'] for n in duplicates}),4)

    def test_shared_task_pairs_do_not_become_direct_causal_edges(self):
        network=self.doc['network'];nodes={n['node_id']:n for n in network['nodes']}
        self.assertEqual((len(network['sharedTaskPairs']),len(network['sameProjectPairs']),len(network['semanticCandidates'])),(157,287,287))
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
        self.assertEqual(len(network['unresolvedClaims']),151)
        self.assertTrue(all(r['indicator_node_id'] is None for r in network['unresolvedClaims']))

    def test_contexts_are_verbatim_and_counts_match_all_7_documents(self):
        t=self.doc['text'];count=0
        self.assertEqual(len(t['documentFiles']),7)
        for docid,path in t['documentFiles'].items():
            payload=load('public/'+path);units={u['unit_id']:u for u in payload['units']}
            for context in payload['contexts']:
                unit=units[context['unit_id']]
                self.assertEqual(context['context'],unit['text'])
                self.assertEqual(context['source_locator'],unit['source_locator'])
                cell=self.trees[docid].xpath(context['source_locator'])[0]
                self.assertIn(unit['text'],ws(cell.text_content()))
                count+=1
        self.assertEqual(count,690);self.assertEqual(count,t['contextCount'])
        self.assertEqual(count,sum(r['count'] for r in t['frameScores']))

    def test_independent_text_results_are_not_labelled_exact_replication(self):
        text=self.doc['text'];audit={r['metric']:r for r in text['replicationAudit']}
        self.assertFalse(text['authorExactCodeAvailable'])
        self.assertEqual((audit['environment_tokens']['author_report'],audit['environment_tokens']['platform_recomputed']),(6110,6085))
        self.assertEqual((audit['corpus_tokens']['author_report'],audit['corpus_tokens']['platform_recomputed']),(75539,75367))
        self.assertEqual((audit['features']['author_report'],audit['features']['platform_recomputed']),(46519,45885))
        self.assertFalse(audit['features']['equal'])
        self.assertTrue(all(r['top3'][0]=='Инфраструктура для жизни' for r in text['sensitivity']))
        expected={'base':1.,'stemming':.982,'unigrams':1.,'equal_levels':.636,'federal_only':.991,'national_only':.300}
        self.assertEqual({r['variant']:round(r['spearman'],3) for r in text['sensitivity']},expected)
        self.assertTrue(all(r['matches_author_rounded_rho'] and r['nearest_matches_author'] for r in text['sensitivity']))
        self.assertIn('no extra within-level normalization',text['method']['equal_levels_formula'])

    def test_light_runtime_omissions_are_available_in_full_export(self):
        for key in ['sourceRows','resultYears']:
            self.assertNotIn(key,self.doc['finance']);self.assertIn(key,self.full['finance'])
        self.assertNotIn('allCards',self.doc['targets']);self.assertEqual(len(self.full['targets']['allCards']),25)
        self.assertNotIn('rows',self.doc['finance']['budgetBill'])
        self.assertEqual(self.doc['meta']['full_export_url'],f'downloads/projects/{PROJECT}/documentary/documentary_full.json')
        for key,path in self.doc['downloads'].items():
            if key=='code':continue
            self.assertTrue((ROOT/'public'/path).is_file(),path)


    def test_docx_xml_paragraphs_and_cells_match_published_extraction(self):
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        def text(el):
            return ''.join((n.text or '') if n.tag.endswith('}t') else '\n' if n.tag.endswith('}br') else '\t' if n.tag.endswith('}tab') else '' for n in el.iter() if n.tag.startswith('{'+ns['w']+'}')).strip()
        docx=ROOT/f'public/downloads/projects/{PROJECT}/report/expertise_environment_2026.docx'
        with zipfile.ZipFile(docx) as z:
            body=ET.fromstring(z.read('word/document.xml')).find('w:body',ns)
            raw={b['index']:b for b in self.report['blocks']}
            for i,el in enumerate(body):
                if el.tag.endswith('}p'):
                    self.assertEqual(text(el),raw[i]['text'])
                elif el.tag.endswith('}tbl'):
                    rows=[['\n'.join(text(p) for p in c.findall('w:p',ns)) for c in r.findall('w:tc',ns)] for r in el.findall('w:tr',ns)]
                    self.assertEqual(rows,raw[i]['rows'])

    def test_federal_sources_are_exactly_the_declared_mechanism_blocks(self):
        blocks={f"b{b['index']}":b for b in self.report['blocks']}
        for fp in self.expert['derived']['federalProjects']:
            expected={'report'}|{f'fn_{n:03d}' for ident in fp['mechanismBlocks'] for n in blocks[ident]['footnotes']}
            self.assertEqual(set(fp['sourceIds']),expected)

    def test_air_collision_does_not_merge_different_territory_definitions(self):
        collision=self.doc['text']['lexicalCollisions'][0]
        self.assertTrue(collision['feature_sequence_equal'])
        self.assertAlmostEqual(collision['cosine'],1.)
        self.assertFalse(collision['scope_equivalence'])
        self.assertEqual(collision['base_dates'],['01.01.2017','01.01.2020'])
        self.assertNotEqual(collision['source_locators'][0],collision['source_locators'][1])
        pairs=[r for r in self.doc['network']['semanticCandidates'] if r['fp']=='Ч4']
        self.assertEqual(len(pairs),60)
        nodes={n['node_id']:n for n in self.doc['network']['nodes']}
        for result in {r['result_node_id'] for r in pairs}:
            selected=[r for r in pairs if r['result_node_id']==result and nodes[r['indicator_node_id']]['source_card_id'] in collision['indicator_card_ids']]
            self.assertEqual(len(selected),2)
            self.assertAlmostEqual(selected[0]['cosine'],selected[1]['cosine'])

    def test_retrieval_dates_and_archive_scope_do_not_invent_fresh_sources(self):
        original=load('inputs/healthtech/documentary/source_manifest.json')
        byid={d['document_id']:d for d in original['documents']}
        for doc in self.doc['sources']:
            self.assertEqual(doc['retrieved_at'],byid[doc['document_id']]['retrieved_at'])
            self.assertEqual(doc['sha256'],byid[doc['document_id']]['sha256'])
        original_budget=load('inputs/healthtech/documentary/budget_source_verification.json')
        self.assertEqual(self.doc['finance']['budgetBill']['retrieved_at'],original_budget['retrieved_at'])
        self.assertFalse((ROOT/f'inputs/environment/documentary/passports.zip').exists())
        self.assertFalse((ROOT/f'public/downloads/projects/environment/documentary/documentary_sources.zip').exists())


if __name__=='__main__':
    unittest.main()
