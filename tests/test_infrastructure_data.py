"""Source-backed regression tests for the Infrastructure for Life data layer."""
from __future__ import annotations
import copy
import csv
import gzip
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from infrastructure_data import DATA,DOWNLOADS,normalize_record,normalize_payload,region_aliases,decode_period,merge_observations,csv_write,load,sha256,source_rules,series_flags
from build_infrastructure_analytics import canonical_regions,national_changes,author_correlations,target_comparisons,target_scale,national_point
from refresh_infrastructure_emiss import normalized_live,run
from infrastructure_formats import parse_excel
from emiss_adapter.errors import EmissConnectorError

class InfrastructureDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']}
        cls.config=load(ROOT/'scripts/infrastructure_emiss_sources.json');cls.contracts={c['indicator_id']:c for c in cls.config['sources']}
        cls.packets={s:load(ROOT/DATA/'series'/f'{s}.json') for s in cls.contracts}
        cls.statistics=load(ROOT/DATA/'statistics.json');cls.analytics=load(ROOT/DATA/'analytics.json')
    def input(self,sid):
        with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:return json.loads(z.read('input.json'))
    def raw(self,sid,year,period,name='Российская Федерация'):
        rows=[r for r in self.input(sid)['observations'] if r['year']==year and r['territory_name']==name and json.loads(r['dimensions_json']).get('Период')==period]
        self.assertEqual(len(rows),1);return rows[0]
    def norm(self,sid,row):return normalize_record(row,self.contracts[sid],self.aliases,self.regions)
    def test_catalog_and_sources_are_distinct_counts(self):
        self.assertEqual(len(self.contracts),34);self.assertEqual(len(load(ROOT/DATA/'indicators.json')['items']),32)
    def test_all_baseline_input_rows_preserved(self):
        total=numeric=0
        for sid in self.contracts:
            payload=self.input(sid);rows=normalize_payload(payload,self.aliases,self.regions)['observations']
            self.assertEqual(len(rows),len(payload['observations']));total+=len(rows);numeric+=sum(r['value'] is not None for r in rows)
            original={r['observation_key']:r for r in payload['observations']}
            for row in rows:
                raw=original[row['source_observation_key']]
                self.assertEqual(row['value'],raw['value_numeric']);self.assertEqual(row['raw_value'],raw['value_raw']);self.assertEqual(row['source_dimensions'],json.loads(raw['dimensions_json']));self.assertEqual(row['source_frequency'],raw['period_kind'])
        self.assertEqual((total,numeric),(93631,91025))
    def test_input_evidence_hashes_and_crc(self):
        for sid in self.contracts:
            with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
                self.assertIsNone(z.testzip());p=json.loads(z.read('input.json'))
                for evidence in p['evidence_files']:self.assertEqual(hashlib.sha256(z.read(evidence['archive_path'])).hexdigest(),evidence['sha256'])
    def test_source_packet_ids_unique(self):
        for p in self.packets.values():self.assertEqual(len(p['observations']),len({r['id'] for r in p['observations']}))
    def test_all_flat_csv_rows_match_current_packets(self):
        for sid,p in self.packets.items():
            data=gzip.decompress((ROOT/DOWNLOADS/'series'/f'{sid}.csv.gz').read_bytes()).decode('utf-8-sig');rows=list(csv.DictReader(io.StringIO(data)))
            self.assertEqual(len(rows),len(p['observations']));lookup={r['id']:r for r in p['observations']}
            for row in rows:
                expected=lookup[row['id']];self.assertEqual(row['raw_value'],str(expected['raw_value'] if expected['raw_value'] is not None else ''));self.assertEqual(row['frequency'],expected['frequency']);self.assertEqual(json.loads(row['category']),expected['category'])
    def test_year_end_is_not_december(self):
        year_end=self.norm('62794',self.raw('62794',2025,'на конец года'));december=self.norm('62794',self.raw('62794',2025,'декабрь'))
        self.assertEqual((year_end['frequency'],year_end['source_frequency'],year_end['value']),('annual','unresolved',56.31))
        self.assertEqual((december['frequency'],december['value']),('monthly',57.41));self.assertNotEqual(year_end['id'],december['id'])
    def test_backbone_year_end_is_separate(self):
        row=self.norm('62801',self.raw('62801',2025,'на конец года'));self.assertEqual(row['value'],74.93);self.assertEqual(row['period_basis'],'explicit_year_end_source_row')
    def test_dated_snapshot_is_not_july_average(self):
        row=self.norm('63460',self.raw('63460',2026,'10 июля'));self.assertEqual(row['period'],'2026-07-10');self.assertEqual(row['frequency'],'dated_snapshot');self.assertEqual(row['source_frequency'],'unresolved');self.assertEqual(row['value'],179883.1283)
    def test_invalid_period_label_rejected(self):
        with self.assertRaises(Exception):decode_period(2026,'какой-то период')
    def test_explicit_period_date_disagreement_rejected(self):
        row=self.raw('62882',2026,'июнь');row['period_end']='2026-06-29'
        with self.assertRaises(ValueError):self.norm('62882',row)
    def test_annual_label_preserves_annual_identity(self):
        row=self.norm('62876',self.raw('62876',2025,'значение показателя за год'));self.assertEqual(row['frequency'],'annual');self.assertTrue(row['annual_comparison_eligible'])
    def test_cumulative_grid_period_preserved(self):
        row=self.norm('62872',self.raw('62872',2026,'июнь'));self.assertEqual(row['frequency'],'cumulative_ytd');self.assertEqual(row['source_period_start'],'2026-01-01');self.assertFalse(row['temporal_comparison_eligible'])
    def test_utility_synchronized_zero_excluded_not_erased(self):
        row=self.norm('62882',self.raw('62882',2026,'сентябрь'));self.assertEqual(row['value'],0);self.assertTrue(row['excluded']);self.assertIsNone(row['analytical_value']);self.assertIn('synchronized_zero_after_positive',{f['code'] for f in row['quality_flags']})
    def test_utility_last_positive_not_carried_forward(self):
        p=self.packets['62882']['observations'];national=[r for r in p if r['geo_level']=='national'];self.assertEqual(next(r['value'] for r in national if r['period']=='2026-09'),0);self.assertGreater(next(r['value'] for r in national if r['period']=='2026-06'),0)
    def test_missing_cells_not_zero(self):
        row=next(r for r in self.packets['59262']['observations'] if r['value'] is None);self.assertIsNone(row['analytical_value']);self.assertEqual(row['status'],'missing')
    def test_future_numeric_excluded(self):
        row=self.raw('62876',2025,'значение показателя за год');row['year']=2027;row['period_start']='2027-01-01';row['period_end']='2027-12-31';dims=json.loads(row['dimensions_json']);dims['Год']='2027';row['dimensions_json']=json.dumps(dims);r=self.norm('62876',row);self.assertTrue(r['excluded']);self.assertEqual(r['value'],13.7)
    def test_positive_index_above_100_allowed(self):
        row=self.norm('62875',self.raw('62875',2025,'значение показателя за год'));self.assertEqual(row['value'],105.17);self.assertFalse(row['excluded'])
    def test_share_above_100_retained_but_excluded(self):
        row=self.raw('62876',2025,'значение показателя за год');row['value_numeric']=101;row['value_raw']='101';r=self.norm('62876',row);self.assertEqual(r['value'],101);self.assertIsNone(r['analytical_value'])
    def test_wrong_source_or_unit_rejected(self):
        for key,value in [('source_id','00000'),('unit','тысяча человек')]:
            row=self.raw('62876',2025,'значение показателя за год');row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.norm('62876',row)
    def test_housing_national_geography_scope(self):
        p=normalize_payload(self.input('59263'),self.aliases,self.regions);r=next(r for r in p['observations'] if r['year']==2025 and r['frequency']=='annual' and r['geo_level']=='national' and r['value'] is not None)
        self.assertEqual(r['value'],108.142);self.assertEqual(r['national_scope'],'rf_without_new_subjects_from_2023');self.assertIn('без учета',r['name'])
    def test_no_housing_change_across_geography_break(self):
        for r in self.analytics['national_changes']:
            if r['source_id'] in {'59262','59263','59993'}:self.assertFalse(r['from_period'].startswith('2022') and r['to_period'].startswith('2023'))
    def test_source_category_currency_duplicates_not_two_variables(self):
        p=normalize_payload(self.input('61608'),self.aliases,self.regions);self.assertEqual({tuple(r['category']) for r in p['observations']},{('Вид валюты',)})
    def test_conflicting_source_categories_rejected(self):
        row=self.input('61608')['observations'][0];dims=json.loads(row['dimensions_json']);dims['Вид валюты']='В рублях';dims['Вид валюты  ']='В иностранной валюте';row['dimensions_json']=json.dumps(dims)
        with self.assertRaises(ValueError):self.norm('61608',row)
    def test_geographical_scope_conflict_not_arbitrarily_selected(self):
        rows=[r for r in self.packets['40466']['observations'] if r['period']=='2013' and r['code']=='29' and r['category']=={'Тип поселения':'Всего'}]
        self.assertGreater(len({r['value'] for r in rows}),1);self.assertEqual(canonical_regions(rows),[])
    def test_merged_police_territory_not_split(self):
        rows=[r for r in self.packets['63457']['observations'] if r['name'].startswith('ГУ МВД России')];self.assertTrue(rows);self.assertTrue(all(r['geo_level']=='other' and r['code'] is None for r in rows))
    def test_author_correlation_scope_and_no_imputation(self):
        a=self.analytics['correlations'];self.assertEqual(a['n'],82);self.assertEqual(a['strict']['n'],80);self.assertEqual(a['imputed_cells'],0);self.assertFalse(a['clustering_performed']);self.assertEqual(a['strict']['excluded_codes'],['29','72'])
    def test_author_correlation_source_baseline_reproduced(self):
        packets={s:normalize_payload(self.input(s),self.aliases,self.regions) for s in ['40466','62876','62794','62801','62887','63457']};a=author_correlations(packets,self.statistics['sources'])
        self.assertAlmostEqual(a['matrix'][2][3],.395420,places=6);self.assertAlmostEqual(a['matrix'][1][2],.337559,places=6);self.assertAlmostEqual(a['matrix'][0][1],-.180998,places=6)
    def test_annual_comparison_favourable_direction(self):
        r=next(r for r in self.analytics['target_comparisons'] if r['source_id']=='63457');self.assertEqual(r['direction'],'lower');self.assertGreater(r['favourable_difference'],0);self.assertFalse(r['formal_attainment_eligible'])
    def test_mortgage_year_end_is_explicit_two_currency_sum(self):
        r=next(r for r in self.analytics['target_comparisons'] if r['source_id']=='61608');self.assertEqual(r['fact_frequency'],'cumulative_ytd');self.assertEqual(r['annual_basis'],'explicit_12_month_sum_two_currencies');self.assertEqual(len(r['reference_observation_ids']),2);self.assertAlmostEqual(r['fact_value'],4.452)
    def test_methodological_or_partial_year_targets_blocked(self):
        ids={r['source_id'] for r in self.analytics['target_comparisons']};self.assertFalse(ids&{'62872','62882','63456','63028','59262','59993'})
    def test_target_scale_has_source_specific_mapping(self):
        self.assertEqual(target_scale({'id':'63460','unit':'гектар'},{'unit':'тыс. га'}),1000)
        self.assertIsNone(target_scale({'id':'123','unit':'гектар'},{'unit':'тыс. га'}))
    def test_no_forecast_claim_from_cumulative_cells(self):
        self.assertTrue(all(not f['eligible'] for f in self.analytics['forecast_eligibility']))
    def test_merge_does_not_erase_known_value_with_missing(self):
        row=copy.deepcopy(self.packets['62876']['observations'][0]);new=copy.deepcopy(row);new['value']=None;new['raw_value']='';result,added,revisions=merge_observations([row],[new]);self.assertEqual(result[0]['value'],row['value']);self.assertEqual(added,0);self.assertEqual(revisions,[])
    def test_merge_tracks_revisions(self):
        row=copy.deepcopy(self.packets['62876']['observations'][0]);new=copy.deepcopy(row);new['value']=row['value']+.1;result,added,revisions=merge_observations([row],[new]);self.assertEqual(len(revisions),1);self.assertEqual(result[0]['value'],new['value'])
    def test_duplicate_merge_rejected(self):
        row=self.packets['62876']['observations'][0]
        with self.assertRaises(ValueError):merge_observations([row],[row,row])
    def test_csv_atomic_failure_retains_previous_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'data.csv';p.write_bytes(b'previous')
            with self.assertRaises(TypeError):csv_write(p,[{'x':{'nested':set([1])}}],['x'])
            self.assertEqual(p.read_bytes(),b'previous')

class InfrastructureRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sid='62876';cls.config=load(ROOT/'scripts/infrastructure_emiss_sources.json');cls.contract=next(c for c in cls.config['sources'] if c['indicator_id']==cls.sid)
        with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{cls.sid}.zip') as z:
            p=json.loads(z.read('input.json'));snapshot=json.loads(p['snapshot']['metadata_json']);cls.meta={'indicator_id':cls.sid,'indicator_title':cls.contract['title'],'filters':snapshot['filters']};cls.selected=json.loads(z.read(next(n for n in z.namelist() if n.endswith('query.json'))))['selected'];cls.raw=z.read(next(n for n in z.namelist() if n.endswith('.xls')))
        cls.items,_=parse_excel(cls.raw,cls.meta,cls.selected)
    def isolated(self,td):
        root=Path(td);(root/'scripts').mkdir();(root/'public/data/projects/life_infrastructure/series').mkdir(parents=True);(root/'public/data/projects/life_infrastructure/provenance').mkdir();
        for relative in ['scripts/infrastructure_emiss_sources.json','public/data/catalog.json',str(DATA/'refresh-status.json'),str(DATA/'series'/'62876.json'),str(DATA/'provenance'/'62876.json')]:
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,target)
        return root
    def client(self,kind):
        outer=self
        class FakeClient:
            def metadata(self,sid):
                if kind=='network':raise EmissConnectorError('Recorded test outage',category='network_error')
                if kind=='metadata_only':return {'no_numeric_grid':True}
                if kind=='wrong_title':return {**outer.meta,'indicator_title':'другая статистика'}
                return outer.meta
            def export(self,meta,selected):return copy.deepcopy(outer.items),{},hashlib.sha256(outer.raw).hexdigest(),outer.raw
            def close(self):pass
        return FakeClient()
    def test_failure_does_not_republish_source_or_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=[sha256(root/DATA/n/'62876.json') for n in ['series','provenance']];old=load(root/DATA/'refresh-status.json')
            report=run(root,only=self.sid,client=self.client('network'),rebuild=False)
            self.assertEqual(report['state'],'failed');self.assertEqual(report['published_sources'],0);self.assertEqual(report['published_at'],old['published_at']);self.assertEqual(before,[sha256(root/DATA/n/'62876.json') for n in ['series','provenance']])
    def test_metadata_only_does_not_claim_numeric_success(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/'62876.json');report=run(root,only=self.sid,client=self.client('metadata_only'),rebuild=False)
            self.assertEqual(report['published_sources'],0);self.assertEqual(sha256(root/DATA/'series'/'62876.json'),before)
    def test_changed_title_does_not_replace_data(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/'62876.json');report=run(root,only=self.sid,client=self.client('wrong_title'),rebuild=False)
            entry=next(s for s in report['sources'] if s['source_id']==self.sid);self.assertEqual(entry['state'],'title_mismatch');self.assertEqual(sha256(root/DATA/'series'/'62876.json'),before)
    def test_real_workbook_passes_refresh_normalizer(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);report=run(root,only=self.sid,client=self.client('valid'),rebuild=False)
            self.assertEqual(report['published_sources'],1);self.assertEqual(report['failed_sources'],0);self.assertEqual(len(load(root/DATA/'series'/'62876.json')['observations']),86)
            source=next(s for s in report['sources'] if s['source_id']==self.sid);raw=root/'public'/source['raw_file'];self.assertTrue(zipfile.is_zipfile(raw));self.assertEqual(sha256(raw),load(root/DATA/'provenance'/'62876.json')['current_raw_sha256'])
    def test_unknown_id_rejected_before_request(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td)
            with self.assertRaises(ValueError):run(root,only='00000000',client=self.client('valid'),rebuild=False)

if __name__=='__main__':unittest.main()
