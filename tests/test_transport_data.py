"""Transport input replay, measurement semantics and atomic refresh contracts."""
import copy,csv,gzip,hashlib,json,shutil,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from transport_data import DATA,DOWNLOADS,MAPPING,load,normalize_record,region_aliases,STAFF
from dataeconomy_formats import parse_excel,parse_grid
from emiss_adapter.client import query_plan
from emiss_adapter.errors import EmissConnectorError
from refresh_transport_emiss import normalized_live,run
from transport_update_summary import summary

class TransportDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.config=load(ROOT/'scripts/transport_emiss_sources.json');cls.contracts={c['indicator_id']:c for c in cls.config['sources']};cls.raw=list(csv.DictReader(gzip.open(ROOT/'inputs/efficient_transport/statistics/observations_snapshot.csv.gz','rt',encoding='utf-8-sig')));cls.baseline={sid:[normalize_record(r,c) for r in cls.raw if r['source_id']==sid] for sid,c in cls.contracts.items()}
 def test_all_22_original_exports_replay_exact_463_cells(self):
  count=0
  for sid,c in self.contracts.items():
   p=ROOT/'inputs/efficient_transport/statistics/originals'/sid;meta=load(p/'metadata.json');roles,selected=query_plan(meta,c,self.config['max_cells']);raw=gzip.decompress((p/'part_00001.json.gz').read_bytes()) if sid=='62832' else (p/'part_00001.xls').read_bytes();parsed,_=(parse_grid if sid=='62832' else parse_excel)(raw,meta,selected);actual=normalized_live(parsed,meta,roles,selected,c,{},'2026-10-15T19:50:00+00:00',{});before={r['id']:r for r in self.baseline[sid]};after={r['id']:r for r in actual};self.assertEqual(set(before),set(after))
   for key in before:
    for field in ('value','unit','source_frequency','source_period_start','source_period_end','period_start','period_end','name','category'):self.assertEqual(before[key][field],after[key][field],(sid,field,key))
   count+=len(actual)
  self.assertEqual(count,463)
 def test_original_evidence_bundles_crc_and_bytes(self):
  for sid in self.contracts:
   with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
    self.assertIsNone(z.testzip())
    for item in json.loads(z.read('provenance.json'))['evidence_files']:
     raw=z.read(item['path']);self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(item['bytes'],item['sha256']))
 def test_valid_zero_capacity_and_missing_are_distinct(self):
  rows=[r for group in self.baseline.values() for r in group];self.assertEqual((len(rows),sum(r['value'] is not None for r in rows),sum(r['excluded'] for r in rows)),(463,442,21));self.assertTrue(all(r['analytical_value']==0 and not r['excluded'] for r in self.baseline['62822'] if r['value']==0));self.assertTrue(all(r['value'] is None for r in rows if r['excluded']))
 def test_percentage_indices_above_100_are_not_invalid_shares(self):
  r=next(x for x in self.baseline['62841'] if x['value']==103);self.assertFalse(r['excluded']);c=self.contracts['62834'];raw=copy.deepcopy(next(r for r in self.raw if r['source_id']=='62834'));raw['value_numeric']='101';self.assertTrue(normalize_record(raw,c)['excluded'])
 def test_ytd_flows_and_multiyear_capacity_stocks_are_distinct(self):
  for sid in ['62820','62832','62851']:
   row=next(r for r in self.baseline[sid] if r['period']=='2025-09');self.assertEqual(row['frequency'],'cumulative_ytd');self.assertEqual(row['period_start'],'2025-01-01')
  row=next(r for r in self.baseline['62819'] if r['period']=='2026-01');self.assertEqual(row['value'],15);self.assertEqual(row['frequency'],'monthly');self.assertEqual(row['period_semantics'],'cumulative_project_capacity_stock')
 def test_staff_december_is_not_current_annual_result(self):
  for sid in STAFF:
   row=next(r for r in self.baseline[sid] if r['period']=='2025-12');self.assertFalse(row['annual_equivalent_eligible']);self.assertEqual(row['period_semantics'],'previous_annual_result_published_monthly')
  rows=load(ROOT/DATA/'analytics.json')['target_comparisons'];self.assertEqual(len(rows),19);self.assertFalse(STAFF.intersection(r['source_id'] for r in rows));zero=next(r for r in rows if r['source_id']=='62823');self.assertEqual((zero['value'],zero['target'],zero['difference'],zero['difference_pct']),(0,0,0,None))
 def test_no_regional_or_forecast_synthesis(self):
  data=load(ROOT/DATA/'analytics.json');self.assertEqual(data['coverage']['regions'],0);self.assertEqual(data['regional_profiles'],[]);self.assertEqual(data['forecasts'],[]);self.assertTrue(all(not f['eligible'] for f in data['forecast_eligibility']));self.assertEqual(data['coverage']['independent_annual_national_facts'],0)
 def test_passport_missing_targets_are_not_zero(self):
  items=load(ROOT/DATA/'targets.json')['items'];self.assertEqual(len(items),22);rail=next(t for t in items if t['source_id']=='62850');self.assertEqual(rail['years']['2028'],135);self.assertIsNone(rail['years']['2029']);self.assertIsNone(rail['years']['2030']);self.assertIsNone(next(t for t in items if t['source_id']=='62822')['years']['2025'])
 def candidate(self,destination):
  root=Path(destination)
  for rel in ['scripts/transport_emiss_sources.json','public/data/catalog.json']:
   p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,p)
  for sub in ['series','provenance']:shutil.copytree(ROOT/DATA/sub,root/DATA/sub)
  shutil.copy2(ROOT/DATA/'refresh-status.json',root/DATA/'refresh-status.json');return root
 def test_failed_refresh_retains_all_published_cells_and_dates(self):
  class Offline:
   def metadata(self,sid):raise EmissConnectorError('simulated outage',category='network_error')
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   root=self.candidate(tmp);paths=list((root/DATA/'series').glob('*.json'))+list((root/DATA/'provenance').glob('*.json'));before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};old=load(root/DATA/'refresh-status.json');result=run(root,client=Offline(),rebuild=False,max_failures=2);self.assertEqual((result['attempted_sources'],result['failed_sources'],result['deferred_sources']),(2,2,20));self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths});self.assertEqual(result['published_at'],old['published_at']);self.assertEqual(result['last_success'],old['last_success']);self.assertIn('Эффективная транспортная система',summary(root))
 def test_successful_mock_revision_has_response_identity_and_raw_evidence(self):
  sid='62832';contract=self.contracts[sid];p=ROOT/'inputs/efficient_transport/statistics/originals'/sid;meta=load(p/'metadata.json');roles,selected=query_plan(meta,contract,self.config['max_cells']);body=json.loads(gzip.decompress((p/'part_00001.json.gz').read_bytes()));key=next(k for r in body['results'] for k,v in r.items() if str(v)=='0,16' and k.startswith('dim'))
  for r in body['results']:
   if key in r:r[key]='0,17'
  raw=json.dumps(body,ensure_ascii=False).encode();digest=hashlib.sha256(raw).hexdigest();parsed,_=parse_grid(raw,meta,selected)
  class LocalSource:
   def metadata(self,s):return copy.deepcopy(meta)
   def export(self,m,sel):return parsed,{},digest,raw
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   root=self.candidate(tmp);result=run(root,only=sid,client=LocalSource(),rebuild=False);self.assertEqual(result['successful_sources'],1);self.assertEqual(result['updated_sources'],1);packet=load(root/DATA/'series'/f'{sid}.json');self.assertTrue(all(r['snapshot_id']=='live:'+digest and r['source_observation_key'].startswith('live:'+digest+':') for r in packet['observations']));receipt=load(root/DATA/'provenance'/f'{sid}.json');self.assertEqual(receipt['response_sha256'],digest)
   with zipfile.ZipFile(root/'public'/receipt['current_raw']) as z:self.assertEqual(z.read('data.json'),raw)
 def test_wrong_unit_and_unknown_source_are_rejected(self):
  raw=copy.deepcopy(next(r for r in self.raw if r['source_id']=='62820'));raw['unit']='процент'
  with self.assertRaisesRegex(ValueError,'Unit mismatch'):normalize_record(raw,self.contracts['62820'])
  with self.assertRaisesRegex(ValueError,'Unknown confirmed'):run(ROOT,only='62900',client=object(),rebuild=False)
if __name__=='__main__':unittest.main()
