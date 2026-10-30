"""Transport source-backed financial and documentary interpretation checks."""
import json,sys,unittest
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from transport_data import load
class TransportDocumentaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d=load(ROOT/'public/data/projects/efficient_transport/documentary.json')
 def test_decimal_plan_reconciles_sources_projects_and_years(self):
  f=self.d['finance'];total=Decimal(f['totalDecimal']);self.assertEqual(total,Decimal('7622134021.13'));self.assertEqual(sum(Decimal(p['totalDecimal']) for p in f['projects']),total);self.assertEqual(sum(Decimal(y['totalDecimal']) for y in f['yearTotals']),total);self.assertEqual(sum(Decimal(s['totalDecimal']) for s in f['sourceTotals']),total);self.assertEqual(len(f['sourceReconciliation']),18);self.assertTrue(all(Decimal(r['differenceDecimal'])==0 for r in f['sourceReconciliation']));self.assertIsNone(f['consolidatedTotalThousandRub'])
 def test_rail_horizon_does_not_create_zero_investments(self):
  rail=next(p for p in self.d['finance']['projects'] if p['code']=='Т1');self.assertEqual(rail['passportHorizon'],[2025,2028]);late=[r for r in rail['years'] if r['year']>2028];self.assertTrue(all(r['amountThousandRub'] is None and r['status']=='outside_passport_horizon' for r in late))
 def test_structural_pairs_are_same_document_same_task_without_causal_weights(self):
  n=self.d['network'];nodes={r['node_id']:r for r in n['nodes']};self.assertEqual(len(nodes),92);self.assertEqual(len(n['structuralPairs']),54);self.assertEqual(len(n['ambiguousClaims']),42)
  for p in n['structuralPairs']:
   result,indicator=nodes[p['result_node_id']],nodes[p['indicator_node_id']];self.assertEqual(result['task_node_id'],indicator['task_node_id']);self.assertEqual(result['document_id'],indicator['document_id']);self.assertIsNone(p['official_weight']);self.assertEqual(p['causal_status'],'not_identified')
 def test_lexical_ties_explain_retained_author_difference(self):
  t=self.d['text'];pairs=self.d['network']['lexicalPairs'];self.assertEqual((len(pairs),len({r['result_node_id'] for r in pairs}),len({r['indicator_node_id'] for r in pairs})),(36,17,15));self.assertEqual(self.d['network']['counts']['authorReportedLexicalIndicators'],16);differences=[r for r in t['replicationAudit'] if not r['equal']];self.assertEqual(len(differences),1);self.assertEqual(differences[0]['metric'],'candidate_unique_indicators');self.assertEqual({r['unique_indicators'] for r in t['tieSensitivity']},{15,16});self.assertTrue(all(r['pairs']==36 and r['results']==17 for r in t['tieSensitivity']));self.assertEqual(len(t['tiedBoundaries']),1);self.assertEqual(len(t['tiedBoundaries'][0]['tied_indicators']),3)
 def test_all_ten_profiles_are_matched_to_source_and_thresholds_match(self):
  t=self.d['text'];self.assertEqual(len(t['documents']),10);self.assertEqual(t['sameGenreTokenCount'],2278);self.assertTrue(all(d['profile_independently_verified'] for d in t['documents']));self.assertEqual(t['profileCount'],137);self.assertEqual([(r['threshold'],r['pairs'],r['results_with_candidate']) for r in t['candidateThresholds']],[(.10,36,17),(.15,23,15),(.20,20,13)])
if __name__=='__main__':unittest.main()
