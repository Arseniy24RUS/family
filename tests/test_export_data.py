"""Original Export cells, period identity and lossless offline refresh contracts."""
import copy,csv,gzip,hashlib,json,shutil,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from export_data import DATA,DOWNLOADS,FORMATS,MAPPING,STALE,load,normalize_record
from dataeconomy_formats import parse_excel,parse_grid
from emiss_adapter.sdmx import parse_sdmx
from emiss_adapter.client import query_plan
from emiss_adapter.errors import EmissConnectorError
from refresh_export_emiss import normalized_live,run
from export_update_summary import summary

class ExportDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.config=load(ROOT/'scripts/export_emiss_sources.json');cls.contracts={c['indicator_id']:c for c in cls.config['sources']};cls.raw=list(csv.DictReader(gzip.open(ROOT/'inputs/international_export/statistics/observations_snapshot.csv.gz','rt',encoding='utf-8-sig')));cls.baseline={sid:[normalize_record(r,c) for r in cls.raw if r['source_id']==sid] for sid,c in cls.contracts.items()}
 def source(self,sid):
  c=self.contracts[sid];p=ROOT/'inputs/international_export/statistics/originals'/sid;meta=load(p/'metadata.json');roles,selected=query_plan(meta,c,self.config['max_cells']);fmt=FORMATS[sid];raw=gzip.decompress((p/('part_00001.xml.gz' if fmt=='sdmx' else 'part_00001.json.gz')).read_bytes()) if fmt!='excel' else (p/'part_00001.xls').read_bytes();parsed,_=parse_sdmx(raw) if fmt=='sdmx' else (parse_grid if fmt=='grid' else parse_excel)(raw,meta,selected);return c,meta,roles,selected,raw,parsed
 def test_18_original_exports_replay_all_181_cells_exactly(self):
  count=0
  for sid in self.contracts:
   c,meta,roles,selected,raw,parsed=self.source(sid);actual=normalized_live(parsed,meta,roles,selected,c,{},'2026-10-15T20:00:00+00:00',{});a={r['id']:r for r in actual};b={r['id']:r for r in self.baseline[sid]};self.assertEqual(set(a),set(b),sid)
   for key in a:
    for field in ('value','unit','source_frequency','source_period_start','source_period_end','period_start','period_end','name','category'):self.assertEqual(a[key][field],b[key][field],(sid,field,key))
   count+=len(actual)
  self.assertEqual(count,181);self.assertEqual([list(FORMATS.values()).count(k) for k in ['excel','sdmx','grid']],[13,4,1])
 def test_original_archive_sha_and_bundle_roundtrip(self):
  folder=ROOT/'inputs/international_export/statistics'
  for entry in load(folder/'archive_entries.json'):
   raw=(folder/entry['relative_path']).read_bytes();self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(entry['bytes'],entry['sha256']))
  for sid in self.contracts:
   with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
    self.assertIsNone(z.testzip())
    for item in json.loads(z.read('provenance.json'))['evidence_files']:
     raw=z.read(item['path']);self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(item['bytes'],item['sha256']))
 def test_annual_and_december_conflicts_are_independent_source_cells(self):
  expected={'62713':(10.2,.5),'62716':(141.59,141.8),'62719':(0,0)}
  for sid,(a,m) in expected.items():
   annual=next(r for r in self.baseline[sid] if r['period']=='2025');monthly=next(r for r in self.baseline[sid] if r['period']=='2025-12');self.assertEqual((annual['value'],monthly['value']),(a,m));self.assertNotEqual(annual['id'],monthly['id']);self.assertEqual(annual['period_end'],monthly['period_end'])
  comparisons=load(ROOT/DATA/'statistics.json')['target_comparisons'];self.assertEqual(next(r for r in comparisons if r['source_id']=='62713')['value'],10.2);self.assertEqual(next(r for r in comparisons if r['source_id']=='62716')['value'],141.59)
 def test_negative_growth_and_large_growth_are_not_invalid_shares(self):
  raw=copy.deepcopy(next(r for r in self.raw if r['source_id']=='62713'))
  for value in [-50,150]:raw['value_numeric']=value;self.assertFalse(normalize_record(raw,self.contracts['62713'])['excluded'])
  raw['value_numeric']=-101;self.assertTrue(normalize_record(raw,self.contracts['62713'])['excluded']);raw=copy.deepcopy(next(r for r in self.raw if r['source_id']=='63154'));raw['value_numeric']=101;self.assertTrue(normalize_record(raw,self.contracts['63154'])['excluded'])
 def test_calendar_ytd_resets_do_not_mean_asset_loss(self):
  for sid in ['62715','62717','62718','62736','62742','63154']:
   row=next(r for r in self.baseline[sid] if r['period']=='2026-08');self.assertEqual(row['frequency'],'cumulative_ytd');self.assertEqual(row['period_start'],'2026-01-01')
  zero=next(r for r in self.baseline['63154'] if r['period']=='2026-01');self.assertEqual(zero['value'],0);self.assertFalse(zero['excluded']);self.assertEqual(zero['period_semantics'],'annual_program_cumulative_progress')
 def test_stale_partial_years_and_standard_mismatch_never_become_annual_results(self):
  data=load(ROOT/DATA/'statistics.json');comparison={r['source_id'] for r in data['target_comparisons']};self.assertEqual(len(comparison),11);self.assertFalse(comparison.intersection(STALE));self.assertNotIn('62721',comparison);old=next(r for r in data['registry'] if r['indicator_code']=='2.14.М3.6');self.assertFalse(old['current_passport_comparable']);self.assertEqual(old['n_numeric'],2);self.assertEqual(data['coverage']['independent_annual_national_facts'],4)
 def test_conditional_nominal_scenarios_are_not_forecasts_or_regional_values(self):
  data=load(ROOT/DATA/'analytics.json');self.assertEqual(data['forecasts'],[]);self.assertTrue(all(not s['eligible'] for s in data['forecast_eligibility']));self.assertEqual(data['coverage']['regions'],0);self.assertEqual(data['regional_profiles'],[])
  for row in data['scenario_trajectories']:self.assertAlmostEqual(row['points'][-1]['value'],row['target_value']);self.assertIn('not_forecast',row['status'])
  check=next(r for r in data['export_accounting_checks'] if r['period']=='2025-12');self.assertEqual((check['nne'],check['industrial'],check['agriculture'],check['difference']),(163.65,122.09,41.56,0))
 def candidate(self,destination):
  root=Path(destination)
  for rel in ['scripts/export_emiss_sources.json','public/data/catalog.json']:
   p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,p)
  for sub in ['series','provenance']:shutil.copytree(ROOT/DATA/sub,root/DATA/sub)
  shutil.copy2(ROOT/DATA/'refresh-status.json',root/DATA/'refresh-status.json');return root
 def test_failed_refresh_preserves_all_cells_provenance_and_success_dates(self):
  class Offline:
   def metadata(self,sid):raise EmissConnectorError('simulated source outage',category='network_error')
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   root=self.candidate(tmp);paths=list((root/DATA/'series').glob('*.json'))+list((root/DATA/'provenance').glob('*.json'));before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths};old=load(root/DATA/'refresh-status.json');result=run(root,client=Offline(),rebuild=False,max_failures=2);self.assertEqual((result['attempted_sources'],result['failed_sources'],result['deferred_sources']),(2,2,16));self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths});self.assertEqual(result['published_at'],old['published_at']);self.assertEqual(result['last_success'],old['last_success']);self.assertIn('Международная кооперация и экспорт',summary(root))
 def test_successful_sdmx_revision_retains_both_frequencies_and_exact_raw(self):
  sid='62713';c,meta,roles,selected,raw,parsed=self.source(sid);raw=raw.replace(b'value="10,2"',b'value="10,3"');parsed,_=parse_sdmx(raw);digest=hashlib.sha256(raw).hexdigest()
  class LocalSource:
   def metadata(self,s):return copy.deepcopy(meta)
   def export(self,m,sel):return parsed,{},digest,raw
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   root=self.candidate(tmp);result=run(root,only=sid,client=LocalSource(),rebuild=False);self.assertEqual(result['successful_sources'],1);self.assertEqual(result['updated_sources'],1);packet=load(root/DATA/'series'/f'{sid}.json');self.assertEqual(len(packet['observations']),2);self.assertEqual({r['period']:r['value'] for r in packet['observations']},{'2025':10.3,'2025-12':.5});self.assertTrue(all(r['snapshot_id']=='live:'+digest and r['source_observation_key']=='live:'+digest+':'+r['id'] for r in packet['observations']));receipt=load(root/DATA/'provenance'/f'{sid}.json');self.assertEqual(receipt['response_sha256'],digest)
   with zipfile.ZipFile(root/'public'/receipt['current_raw']) as z:self.assertEqual(z.read('data.xml'),raw)
 def test_missing_incoming_value_never_erases_retained_number(self):
  from personnel_data import merge_observations
  old=self.baseline['62713'];incoming=copy.deepcopy(old[:1]);incoming[0]['value']=None;incoming[0]['analytical_value']=None;incoming[0]['excluded']=True;merged,added,revisions=merge_observations(old,incoming);self.assertEqual({r['id']:r['value'] for r in merged},{r['id']:r['value'] for r in old});self.assertEqual(len(merged),2)
 def test_second_partial_response_retains_prior_live_cell_and_its_raw_archive(self):
  from lxml import etree
  sid='62713';c,meta,roles,selected,raw,parsed=self.source(sid);first=raw.replace(b'value="10,2"',b'value="10,3"');tree=etree.fromstring(first);series=tree.xpath('//*[local-name()="Series"]');self.assertEqual(len(series),2);series[1].getparent().remove(series[1]);second=etree.tostring(tree).replace(b'value="0,5"',b'value="0,6"')
  class LocalSource:
   def __init__(self,body):self.raw=body
   def metadata(self,s):return copy.deepcopy(meta)
   def export(self,m,sel):return parse_sdmx(self.raw)[0],{},hashlib.sha256(self.raw).hexdigest(),self.raw
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   root=self.candidate(tmp)
   for body in [first,second]:self.assertEqual(run(root,only=sid,client=LocalSource(body),rebuild=False)['successful_sources'],1)
   packet=load(root/DATA/'series'/f'{sid}.json');self.assertEqual({r['period']:r['value'] for r in packet['observations']},{'2025':10.3,'2025-12':.6});receipt=load(root/DATA/'provenance'/f'{sid}.json');self.assertEqual(len(receipt['retained_responses']),2)
   for item in receipt['retained_responses']:
    p=root/'public'/item['path'];self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),item['archive_sha256'])
    with zipfile.ZipFile(p) as z:self.assertEqual(hashlib.sha256(z.read('data.xml')).hexdigest(),item['response_sha256'])
 def test_new_annual_cell_grows_live_coverage_and_passes_published_source_validator(self):
  import subprocess
  from lxml import etree
  sid='62728';c,meta,roles,selected,raw,parsed=self.source(sid);meta=copy.deepcopy(meta);period=next(f for f in meta['filters'] if f['title']=='Период');period['values'].append({'id':'1558883','title':'значение показателя за год'});tree=etree.fromstring(raw);first=tree.xpath('//*[local-name()="Series"]')[0];extra=copy.deepcopy(first);extra.xpath('./*[local-name()="Attributes"]/*[@concept="PERIOD"]')[0].set('value','значение показателя за год');extra.xpath('./*[local-name()="Obs"]/*[local-name()="ObsValue"]')[0].set('value','8,90');first.getparent().append(extra);raw=etree.tostring(tree);parsed,_=parse_sdmx(raw);digest=hashlib.sha256(raw).hexdigest()
  class LocalSource:
   def metadata(self,s):return copy.deepcopy(meta)
   def export(self,m,sel):return parsed,{},digest,raw
   def close(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   root=self.candidate(tmp)
   for rel in ['inputs/international_export/statistics/catalog_original.json','inputs/international_export/statistics/observations_snapshot.csv.gz']:
    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,p)
   for name in ['targets.json','metadata-sources.json','regional-context.json']:shutil.copy2(ROOT/DATA/name,root/DATA/name)
   result=run(root,only=sid,client=LocalSource(),rebuild=True);self.assertEqual(result['successful_sources'],1);stats=load(root/DATA/'statistics.json');self.assertEqual((stats['coverage']['observations'],stats['coverage']['independent_annual_national_facts'],len(stats['target_comparisons'])),(182,5,12))
   bundles=[]
   for source_id,contract in self.contracts.items():
    p=load(root/DATA/'provenance'/f'{source_id}.json');bundles.append({'path':str(ROOT/'public'/p['input_bundle']),'published':str(root/DATA/'series'/f'{source_id}.json'),'evidence_files':p['evidence_files'],'contract':contract,'responses':[{**r,'absolute_path':str(root/'public'/r['path'])} for r in p.get('retained_responses',[])]})
   services=load(ROOT/DATA/'regional-context.json')['services'];cbr=[{'absolute_path':str(ROOT/'public'/r['local_file']),'rows':[x for x in services['rows']+services['national']+services['unallocated'] if x['year']==r['year']]} for r in services['sources']];payload=root/'source_check.json';payload.write_text(json.dumps({'scripts':str(ROOT/'scripts'),'bundles':bundles,'cbr_sources':cbr}));code=(ROOT/'scripts/validate_export.mjs').read_text().split('const SOURCE_CHECK=String.raw`',1)[1].split('`;',1)[0];checked=json.loads(subprocess.check_output([sys.executable,'-c',code,str(payload)],text=True));self.assertEqual(checked['original_snapshot_cells'],181);self.assertEqual(checked['published_cells_checked'],182);self.assertEqual(checked['live_rows_checked'],3);self.assertEqual(checked['retained_responses_checked'],1)
 def test_wrong_units_unknown_source_and_future_period_rejected(self):
  raw=copy.deepcopy(next(r for r in self.raw if r['source_id']=='62715'));raw['unit']='процент'
  with self.assertRaisesRegex(ValueError,'Unit mismatch'):normalize_record(raw,self.contracts['62715'])
  with self.assertRaisesRegex(ValueError,'Unknown confirmed'):run(ROOT,only='62900',client=object(),rebuild=False)
  c,meta,roles,selected,raw,parsed=self.source('62713')
  with self.assertRaises(EmissConnectorError):normalized_live(parsed,meta,roles,selected,c,{},'2025-01-01T00:00:00+00:00',{})
if __name__=='__main__':unittest.main()
