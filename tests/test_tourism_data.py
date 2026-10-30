"""Tourism source replay, measurement-unit and failed-refresh retention contracts."""
import copy, csv, gzip, hashlib, json, shutil, sys, tempfile, unittest, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from tourism_data import DATA, DOWNLOADS, MAPPING, load, normalize_record, region_aliases
from dataeconomy_formats import parse_excel
from emiss_adapter.client import query_plan
from emiss_adapter.errors import EmissConnectorError
from refresh_tourism_emiss import normalized_live, run
from tourism_update_summary import summary

class TourismDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.config=load(ROOT/'scripts/tourism_emiss_sources.json');cls.contracts={c['indicator_id']:c for c in cls.config['sources']}
  cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']}
  cls.raw=list(csv.DictReader(gzip.open(ROOT/'inputs/tourism/statistics/observations_snapshot.csv.gz','rt',encoding='utf-8-sig')))
  cls.baseline={sid:[normalize_record(r,cls.contracts[sid],cls.aliases,cls.regions) for r in cls.raw if r['source_id']==sid] for sid in cls.contracts}

 def test_all_six_original_xls_exports_replay_exact_values_periods_and_units(self):
  total=0
  for sid,contract in self.contracts.items():
   folder=ROOT/'inputs/tourism/statistics/originals'/sid;meta=load(folder/'metadata.json');roles,selected=query_plan(meta,contract,self.config['max_cells'])
   parsed,_=parse_excel((folder/'part_00001.xls').read_bytes(),meta,selected)
   actual=normalized_live(parsed,meta,roles,selected,contract,self.aliases,'2026-10-15T19:45:47+00:00',self.regions)
   before={r['id']:r for r in self.baseline[sid]};after={r['id']:r for r in actual};self.assertEqual(set(before),set(after))
   for key in before:
    for field in ('value','unit','source_frequency','source_period_start','source_period_end','period_start','period_end','name','map_id'):
     self.assertEqual(before[key][field],after[key][field],(sid,field,key))
   total+=len(actual)
  self.assertEqual((len(self.contracts),total),(6,1924))

 def test_raw_sources_have_verified_byte_hashes(self):
  for sid in self.contracts:
   with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
    self.assertIsNone(z.testzip());provenance=json.loads(z.read('provenance.json'))
    for item in provenance['evidence_files']:
     self.assertEqual(hashlib.sha256(z.read(item['path'])).hexdigest(),item['sha256'])
     self.assertEqual(len(z.read(item['path'])),item['bytes'])

 def test_ytd_flow_retains_source_month_and_never_becomes_monthly_flow(self):
  row=next(r for r in self.baseline['62900'] if r['geo_level']=='national' and r['period']=='2026-09')
  self.assertEqual((row['value'],row['frequency'],row['source_frequency']),(74.4464,'cumulative_ytd','monthly'))
  self.assertEqual((row['period_start'],row['source_period_start']),('2026-01-01','2026-09-01'))
  self.assertFalse(row['annual_comparison_eligible'])

 def test_foreign_guests_and_export_have_distinct_contracts_and_units(self):
  self.assertEqual(MAPPING['62902'],'2.14.П.1');self.assertEqual(MAPPING['63347'],'2.14.П3.1')
  self.assertEqual(self.contracts['62902']['unit'],'миллиард долларов США')
  self.assertEqual(self.contracts['63347']['unit'],'миллион человек')
  wrong=copy.deepcopy(next(r for r in self.raw if r['source_id']=='62902'));wrong['unit']='миллион человек'
  with self.assertRaisesRegex(ValueError,'Unit mismatch'):normalize_record(wrong,self.contracts['62902'],self.aliases,self.regions)

 def test_unresolved_zeros_are_retained_and_not_used_as_missing_activity(self):
  rows=[r for group in self.baseline.values() for r in group];excluded=[r for r in rows if r['excluded']]
  self.assertEqual(len(excluded),14);self.assertEqual(len(rows)-len(excluded),1910)
  self.assertEqual({r['source_id'] for r in excluded},{'62902','62903','62780'})
  self.assertTrue(all(r['value']==0 and r['analytical_value'] is None for r in excluded))
  self.assertTrue(all(r['source_frequency']=='monthly' for r in excluded))

 def test_2025_regional_sum_and_national_target_gap_match_source_cells(self):
  rows=[r for r in self.baseline['62900'] if r['period']=='2025-12'];regional=[r for r in rows if r['geo_level']=='regional'];national=next(r for r in rows if r['geo_level']=='national')
  self.assertEqual(len(regional),85);self.assertAlmostEqual(sum(r['value'] for r in regional),92.0428,7);self.assertEqual(national['value'],92.0428)
  target=next(t for t in load(ROOT/DATA/'targets.json')['items'] if t['source_id']=='62900')
  self.assertEqual(target['years']['2025'],98.2);self.assertAlmostEqual(national['value']-target['years']['2025'],-6.1572,7)
  p2=next(t for t in load(ROOT/DATA/'targets.json')['items'] if t['indicator_code']=='2.14.П2.1')
  self.assertIsNone(p2['years']['2025']);self.assertIsNone(p2['years']['2026']);self.assertEqual(p2['years']['2028'],1.2)

 def candidate(self,destination):
  root=Path(destination)
  for relative in ['scripts/tourism_emiss_sources.json','public/data/catalog.json']:
   target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
  shutil.copytree(ROOT/DATA,root/DATA)
  return root

 def test_failed_refresh_preserves_series_provenance_and_publication_date(self):
  class Unavailable:
   def metadata(self,sid):raise EmissConnectorError('offline simulated outage',category='network_error')
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   root=self.candidate(tmp);paths=sorted((root/DATA/'series').glob('*.json'))+sorted((root/DATA/'provenance').glob('*.json'))
   before={p.name+str(p.parent):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};previous=load(root/DATA/'refresh-status.json')
   result=run(root,client=Unavailable(),rebuild=False,max_failures=2)
   after={p.name+str(p.parent):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
   self.assertEqual(before,after);self.assertEqual((result['attempted_sources'],result['failed_sources'],result['deferred_sources']),(2,2,4))
   self.assertEqual(result['published_at'],previous['published_at']);self.assertEqual(result['last_success'],previous['last_success'])
   self.assertEqual(load(root/'monitoring/tourism_last_refresh.json'),result)
   output=summary(root);self.assertIn('Туризм и гостеприимство',output);self.assertIn(previous['published_at'],output)

 def test_unknown_source_is_rejected_before_any_client_request(self):
  class Never:
   def metadata(self,sid):raise AssertionError('A request must not be made')
   def close(self):raise AssertionError('Client was not opened')
  with self.assertRaisesRegex(ValueError,'Unknown confirmed'):run(ROOT,only='123456789',client=Never(),rebuild=False)

if __name__=='__main__':unittest.main()
