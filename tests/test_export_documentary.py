"""Independent source locators and financial/textual scope gates for Export."""
from decimal import Decimal
from pathlib import Path
import hashlib,json,re,sys,unittest,zipfile
from lxml import html
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from export_data import load
from extract_export_passports import norm,decimal,ws

class ExportDocumentaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=load(ROOT/'public/data/projects/international_export/documentary.json');cls.parsed=load(ROOT/'inputs/international_export/documentary/parsed_export_passports.json');cls.trees={d['document']['document_id']:html.fromstring((ROOT/'public'/d['document']['download_path']).read_bytes()).getroottree() for d in cls.parsed}
 def test_every_financial_cell_matches_exact_source_xpath(self):
  n=0
  for d in self.parsed:
   tree=self.trees[d['document']['document_id']]
   for row in d['finance_records']:
    elements=tree.xpath(row['source_locator']);self.assertEqual(len(elements),1);values=elements[0].xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-passport-year-value ")]');years=elements[0].xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," db-passport-year-label ")]');self.assertEqual(len(values),1);self.assertEqual(len(years),1);self.assertEqual(decimal(ws(values[0].text_content())),row['amount_decimal']);self.assertEqual(int(ws(years[0].text_content())),row['year']);n+=1
  self.assertEqual(n,214)
 def test_horizon_and_known_transfer_are_independently_reconciled(self):
  f=self.data['finance'];gross=Decimal(f['totalDecimal']);adjusted=Decimal(f['adjustedTotalDecimal']);self.assertEqual(gross,Decimal('723311645.10'));self.assertEqual(gross-adjusted,Decimal('1338356.30'));self.assertEqual(sum(Decimal(p['totalDecimal']) for p in f['projects']),gross);self.assertIsNone(f['consolidatedTotalThousandRub']);self.assertEqual(f['ownRegionalContribution2025ThousandRub'],33282.2)
  apk=next(p for p in f['projects'] if p['code']=='М4');self.assertEqual(apk['totalThousandRub'],289794593.8);self.assertEqual(apk['outsideHorizonThousandRub'],3921704.4);self.assertAlmostEqual(apk['totalIncludingOutsideHorizonThousandRub'],293716298.2)
  check=f['transferReconciliation'];self.assertEqual(Decimal(check['federalTotalDecimal'])-Decimal(check['explicitResultFederalDecimal']),Decimal(check['differenceDecimal']));self.assertTrue(all(r['equal'] and Decimal(r['differenceDecimal'])==0 for r in f['sourceReconciliation']));self.assertEqual([r['year'] for r in f['yearTotals'] if r['regional_origin_unresolved']],[2028,2029])
 def test_budget_proposal_and_cash_keep_their_own_time_and_base(self):
  f=self.data['finance'];self.assertEqual(f['budgetProposal']['baseline_year'],2026);self.assertEqual(f['budgetProposal']['baseline_as_of'],'2026-09-01');self.assertEqual(f['budgetProposal']['proposal_years'],[2027,2028,2029]);self.assertEqual(f['budgetProposal']['baseline_billion_rub'],84.7812);self.assertEqual(f['cashExecution']['percent'],84.7);self.assertIsNone(f['cashExecution']['amountThousandRub'])
 def test_structural_pairs_are_task_membership_not_direct_or_causal_edges(self):
  net=self.data['network'];self.assertEqual(net['counts']['results'],47);self.assertEqual(net['counts']['indicatorCards'],25);self.assertEqual(net['counts']['uniqueIndicators'],21);self.assertEqual(len(net['ambiguousClaims']),101);self.assertEqual(net['counts']['resolvedDirectLinks'],0);self.assertFalse(net['officialDirectWeightsUsed']);counts={code:sum(e['fp']==code for e in net['structuralPairs']) for code in ['М1','М2','М3','М4']};self.assertEqual(counts,{'М1':40,'М2':10,'М3':207,'М4':27});nodes={n['node_id']:n for n in net['nodes']}
  for e in net['structuralPairs']:
   r,i=nodes[e['result_id']],nodes[e['indicator_id']];self.assertEqual(r['task_node_id'],i['task_node_id']);self.assertEqual(r['document_id'],i['document_id']);self.assertIsNone(e['official_weight']);self.assertEqual(e['causal_status'],'not_identified')
 def test_all_target_values_match_original_locator_and_missing_stays_missing(self):
  targets=self.data['targets'];self.assertEqual((targets['source_card_count'],targets['unique_indicator_count'],targets['numeric_targets'],targets['missing_targets']),(25,21,122,4))
  missing=next(t for t in targets['items'] if t['indicator_code']=='2.14.М3.7');self.assertEqual(missing['years'],{'2025':None,'2026':None,'2027':None,'2028':4.0,'2029':4.0,'2030':None});self.assertIsNone(missing['source_id']);standard=next(t for t in targets['items'] if t['source_id']=='62731');self.assertFalse(standard['annual_comparison_eligible']);self.assertEqual(standard['mapping_status'],'historical_standard_version_mismatch')
  for card in targets['allCards']:
   self.assertEqual(len(self.trees[card['document_id']].xpath(card['source_locator'])),1)
 def test_65_text_profiles_remain_separate_from_old_corpus_and_author_coefficients(self):
  t=self.data['text'];self.assertEqual(t['profileCount'],65);self.assertEqual(len(t['profiles']),65);self.assertEqual((t['resultProfiles'],t['indicatorProfiles']),(47,18));self.assertFalse(t['authorExactCodeAvailable']);self.assertEqual([r['pairs'] for r in t['candidateThresholds']],[28,15,8,6]);self.assertEqual([r['author_reported_results'] for r in t['candidateThresholds']],[26,15,8,6]);self.assertFalse(t['candidateThresholds'][0]['matches_author']);self.assertEqual(t['method']['numbers_retained'],True);self.assertFalse(t['method']['stemming'])
  for p in t['profiles']:self.assertEqual(hashlib.sha256(p['text'].encode()).hexdigest(),p['text_sha256']);self.assertEqual(len(self.trees[p['document_id']].xpath(p['source_locator'])),1)
 def test_full_similarity_matrix_and_best_candidates_preserve_project_scope(self):
  t=self.data['text'];m=t['resultIndicatorMatrix'];self.assertEqual((len(m['rows']),len(m['columns'])),(47,18));self.assertEqual(len(m['values']),47);cols={c['id']:j for j,c in enumerate(m['columns'])};rowids={r['id']:i for i,r in enumerate(m['rows'])};self.assertEqual(len(t['bestCandidates']),47)
  for p in t['bestCandidates']:
   i,j=rowids[p['result_id']],cols[p['indicator_id']];r=m['rows'][i];self.assertEqual(r['fp'],m['columns'][j]['fp']);self.assertAlmostEqual(p['cosine'],max(v for k,v in enumerate(m['values'][i]) if m['columns'][k]['fp']==r['fp']));self.assertTrue(all(0<=v<=1.000000000001 for v in m['values'][i]));self.assertEqual(len(m['values'][i]),18)
  self.assertEqual(len(t['documentSimilarity']),16)
  for row in t['documentSimilarity']:
   if row['same_document']:self.assertAlmostEqual(row['cosine'],1)
  for row in t['frameScores']:self.assertEqual(row['denominator'],{'М1':10,'М2':5,'М3':23,'М4':9}[row['code']]);self.assertAlmostEqual(row['percent'],row['count']/row['denominator']*100)
if __name__=='__main__':unittest.main()
