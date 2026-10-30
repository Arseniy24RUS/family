"""Source-based acceptance checks for the Health Technologies documentary module."""
from pathlib import Path
from decimal import Decimal
import hashlib,json,re,sys,unittest,zipfile
from lxml import html
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from extract_healthtech_passports import parse_passport
PROJECT='health_technologies'

def load(relative):return json.loads((ROOT/relative).read_text(encoding='utf-8'))
def ws(value):return re.sub(r'\s+',' ',value).strip()
def dec(value):return Decimal(ws(value).replace(' ','').replace(',','.'))

class HealthtechDocumentaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.doc=load(f'public/data/projects/{PROJECT}/documentary.json');cls.expert=load(f'public/data/projects/{PROJECT}/expertise.json');cls.manifest=load('inputs/healthtech/documentary/source_manifest.json');cls.source_dir=ROOT/'inputs/healthtech/documentary';cls.sources={}
  with zipfile.ZipFile(cls.source_dir/'passports.zip') as z:
   for source in cls.manifest['documents']:
    if source['project_id']==PROJECT:cls.sources[source['document_id']]=(source,z.read(source['archive_entry']))
 def test_author_docx_bytes_and_coverage(self):
  p=ROOT/f'public/downloads/projects/{PROJECT}/report/expertise_healthtech_2026.docx'
  self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),'49a0b61d96a414e72d22ededb26e6690fd45a5e17424135617b7bb9079fd8913')
  coverage=load(f'public/downloads/projects/{PROJECT}/report/coverage_manifest.json')['summary']
  self.assertEqual((coverage['substantive_blocks'],coverage['assigned_blocks'],coverage['report_pages']),(317,317,105))
  self.assertEqual(coverage['unmapped_substantive_blocks'],[]);self.assertEqual(coverage['duplicate_assignments'],[])
  self.assertEqual((coverage['routes'],coverage['tables'],coverage['figures'],coverage['footnotes'],coverage['formulas']),(21,15,14,142,5))
 def test_formula_pages_match_rendered_source_contract(self):
  fs=[b for page in self.expert['pages'].values() for b in page['blocks'] if b['type']=='formula']
  self.assertEqual(sorted(f['page'] for f in fs),[69,69,69,94,95]);self.assertTrue(all(f['original_equation_text'] and f['latex'] for f in fs))
 def test_original_illustration_hashes(self):
  for fig in self.expert['figures']:self.assertEqual(hashlib.sha256((ROOT/'public'/fig['url']).read_bytes()).hexdigest(),fig['original_sha256'])
 def test_all_original_corpus_bytes_preserved(self):
  with zipfile.ZipFile(self.source_dir/'passports.zip') as z:
   for source in self.manifest['documents']:self.assertEqual(hashlib.sha256(z.read(source['archive_entry'])).hexdigest(),source['sha256'])
  self.assertEqual(len(self.manifest['documents']),98);self.assertEqual(len({x['project_id'] for x in self.manifest['documents']}),12)
 def test_passport_titles_do_not_become_last_indicator(self):
  for docid,(meta,raw) in self.sources.items():
   title=ws(html.fromstring(raw).xpath('//h1')[0].text_content());parsed=parse_passport(raw,meta)
   self.assertEqual(parsed['document']['title'],title);self.assertEqual(next(x['title'] for x in self.doc['sources'] if x['document_id']==docid),title)
  self.assertEqual(next(x['name'] for x in self.doc['finance']['federalShares'] if x['fp']=='С1'),'Управление медицинской наукой')
 def test_target_values_resolve_to_original_dom(self):
  targets=self.doc['targets'];self.assertEqual((targets['target_cells'],targets['numeric_targets'],targets['missing_targets']),(126,118,8));self.assertEqual(len({r['indicator_code'] for r in targets['items']}),21)
  for row in targets['items']:
   meta,raw=self.sources[row['source_document']];tree=html.fromstring(raw).getroottree()
   self.assertEqual(len(tree.xpath(row['source_locator'])),1)
   for year,value in row['years'].items():
    source=row['raw_years'][year];cell=tree.xpath(source['source_locator'])[0];nodes=cell.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-purpose-year-val ")]');text=ws(nodes[0].text_content())
    if value is None:self.assertIn(text,['—','–','-',''])
    else:self.assertEqual(Decimal(str(value)),dec(text))
  absent=next(x for x in targets['items'] if x['indicator_code']=='2.14.С5.3');self.assertIsNone(absent['source_id'])
 def test_finance_exact_original_document_cells(self):
  finance=self.doc['finance'];total=Decimal(0)
  for r in finance['fpYears']:
   if r['amount_decimal'] is None:self.assertIsNone(r['amount_thousand_rub']);self.assertIsNone(r['source_locator']);continue
   meta,raw=self.sources[r['source_id']];tree=html.fromstring(raw).getroottree();cell=tree.xpath(r['source_locator'])[0];nodes=cell.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-passport-year-value ")]');amount=dec(nodes[0].text_content());self.assertEqual(amount,Decimal(r['amount_decimal']));total+=amount
  self.assertEqual(total,Decimal('16213442.40'));self.assertEqual(sum(r['amount_decimal'] is None for r in finance['fpYears']),8)
  for y in [2029,2030]:self.assertEqual([r['fp'] for r in finance['fpYears'] if r['year']==y and r['amount_decimal'] is not None],['С1'])
 def test_finance_result_level_is_not_double_counted(self):
  f=self.doc['finance']
  for share in f['federalShares']:
   total=sum((Decimal(r['amount_decimal']) for r in f['resultYears'] if r['fp']==share['fp']),Decimal(0));self.assertEqual(total,Decimal(share['amount_decimal']))
  for row in f['reconciliation']:self.assertEqual(Decimal(row['difference_decimal']),0)
 def test_budget_bill_original_28_cells_and_status(self):
  f=self.doc['finance'];b=f['budgetBill'];self.assertEqual(b['verification_status'],'independently_verified_legal_republication');self.assertEqual(b['verified_numeric_cells'],28)
  p=self.source_dir/'budget_2027_2029.html';self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),b['source_html_sha256']);tree=html.parse(str(p));frame=next(x for x in f['frames'] if x['id']=='budget_bill')
  self.assertEqual(len(frame['rows']),28)
  for r in frame['rows']:
   self.assertEqual(dec(tree.xpath(r['source_locator'])[0].text_content()),Decimal(r['amount_decimal']))
   self.assertEqual(r['kind'],'budget_allocation' if r['year']==2026 else 'budget_bill')
  r=next(x for x in f['reserveYears'] if x['year']==2027);self.assertAlmostEqual(r['residual_after_reserve_million_rub'],1.6377,places=6)
  r=next(x for x in f['reserveYears'] if x['year']==2028);self.assertAlmostEqual(r['residual_after_reserve_million_rub'],30.9721,places=6)
 def test_ambiguous_weights_cannot_become_direct_edges(self):
  network=self.doc['network'];self.assertEqual(len(network['unresolvedClaims']),69);self.assertEqual(network['reviewedEdges'],[]);self.assertEqual(network['directLinks'],[])
  self.assertTrue(all(r['indicator_node_id'] is None and r['resolution']=='unresolved_target_indicator' for r in network['unresolvedClaims']))
  self.assertEqual(len(network['semanticCandidates']),83);self.assertEqual(len(network['sharedTaskPairs']),83);self.assertTrue(all(x['evidence_class']=='same_federal_project_candidate' for x in network['sharedTaskPairs']))
 def test_contexts_are_verbatim_retained_units(self):
  text=self.doc['text'];count=0
  for docid,path in text['documentFiles'].items():
   payload=load('public/'+path);units={u['unit_id']:u for u in payload['units']}
   for c in payload['contexts']:self.assertEqual(c['context'],units[c['unit_id']]['text']);self.assertEqual(c['source_locator'],units[c['unit_id']]['source_locator']);count+=1
  self.assertEqual(count,text['contextCount']);self.assertEqual(count,sum(r['count'] for r in text['frameScores']))
 def test_text_replication_difference_is_visible(self):
  text=self.doc['text'];audit={x['metric']:x for x in text['replicationAudit']};self.assertFalse(text['authorExactCodeAvailable']);self.assertEqual(audit['healthtech_tokens']['platform_recomputed'],2571);self.assertTrue(audit['healthtech_tokens']['equal']);self.assertFalse(audit['features']['equal']);self.assertEqual(audit['features']['author_report'],46519);self.assertEqual(text['projectSimilarity'][0]['project_id'],'long_active_life');self.assertTrue(all(x['top3'][0]=='Продолжительная и активная жизнь' for x in text['sensitivity']))
 def test_all_table_footnotes_have_exact_cell_and_block_anchors(self):
  notes=[x for x in self.expert['sources'] if x['id']!='report']
  self.assertEqual(len(notes),142);self.assertTrue(all(x['source_blocks'] for x in notes))
  count=0
  for table in self.expert['tables']:
   self.assertEqual(len(table['cellSourceIds']),len(table['rows']))
   for row in [table['headerSourceIds'],*table['cellSourceIds']]:
    for cell in row:
     for ref in cell:
      self.assertIn(ref,table['sourceIds']);self.assertIn(table['sourceBlock'],next(x['source_blocks'] for x in notes if x['id']==ref));count+=1
  self.assertEqual(count,23)
 def test_repeated_source_html_ids_do_not_merge_distinct_cards(self):
  network=self.doc['network'];nodes=network['nodes'];ids=[n['node_id'] for n in nodes]
  self.assertEqual(len(ids),62);self.assertEqual(len(set(ids)),62)
  results=[n for n in nodes if n['kind']=='result'];self.assertEqual(len(results),28)
  duplicates=[n for n in results if n['document_id']=='fp_307' and n['source_card_id']=='passport-result-37'];self.assertEqual(len(duplicates),3);self.assertEqual(len({n['node_id'] for n in duplicates}),3)
  self.assertEqual(len({r['id'] for r in network['semanticCandidates']}),83)
  self.assertEqual(len({r['id'] for r in network['sharedTaskPairs']}),83)
  for r in network['unresolvedClaims']:self.assertIn(r['result_node_id'],ids)
 def test_result_finance_refs_resolve_to_exact_distinct_card(self):
  nodes={n['node_id']:n for n in self.doc['network']['nodes'] if n['kind']=='result'}
  for row in self.doc['finance']['resultYears']:
   node=nodes[row['result_id']];self.assertEqual(row['source_result_locator'],node['source_locator']);self.assertEqual(row['source_result_card_id'],node['source_card_id']);self.assertEqual(row['result_title'],node['title'])
   meta,raw=self.sources[row['document_id']];tree=html.fromstring(raw).getroottree();card=tree.xpath(row['source_result_locator'])[0];cell=tree.xpath(row['source_locator'])[0];self.assertIn(card,list(cell.iterancestors()))
  sums=self.doc['finance']['resultSums'];self.assertEqual(len(sums),len({r['result_id'] for r in sums}))
  for r in sums:self.assertEqual(r['title'],nodes[r['result_id']]['title'])
 def test_official_news_dates_do_not_use_current_footer(self):
  updates=self.doc['officialUpdates'];self.assertEqual([x['publication_date'] for x in updates],['2026-03-27','2026-05-18','2026-07-28'])
  for x in updates:self.assertEqual(hashlib.sha256((ROOT/'public'/x['download_path']).read_bytes()).hexdigest(),x['sha256']);self.assertGreater(len(x['text']),1000)
 def test_declared_documentary_downloads_exist(self):
  for key,value in self.doc['downloads'].items():
   if key=='code':continue
   self.assertTrue((ROOT/'public'/value).is_file(),value)

if __name__=='__main__':unittest.main()
