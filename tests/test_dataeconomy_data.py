"""Source fidelity, digital measurement contracts and safe refresh failures."""
from __future__ import annotations
import copy,csv,gzip,hashlib,io,json,math,shutil,statistics,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from dataeconomy_data import DATA,DOWNLOADS,normalize_record,normalize_payload,region_aliases,merge_observations,load,sha256
from build_dataeconomy_analytics import canonical_unit,national_point
from dataeconomy_multivariate import build_multivariate,SOURCE_IDS
from refresh_dataeconomy_emiss import normalized_live,run
from dataeconomy_formats import parse_excel,parse_grid
from emiss_adapter.sdmx import parse_sdmx
from emiss_adapter.metadata import infer_field_map
from emiss_adapter.errors import EmissConnectorError


def input_packet(sid):
    with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:return json.loads(z.read('input.json'))

def source_export(sid,contract):
    with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
        p=json.loads(z.read('input.json'));metadata=json.loads(p['snapshot']['metadata_json']);meta={'indicator_id':sid,'indicator_title':contract['title'],'filters':metadata['filters']}
        selected=json.loads(z.read(next(n for n in z.namelist() if n.endswith('query.json'))))['selected'];name=next(n for n in z.namelist() if n.endswith(('.xls','.json.gz','.xml.gz')));raw=z.read(name);raw=gzip.decompress(raw) if name.endswith('.gz') else raw
    items,_=parse_excel(raw,meta,selected) if name.endswith('.xls') else parse_grid(raw,meta,selected) if name.endswith('.json.gz') else parse_sdmx(raw)
    return meta,selected,items,raw

class DataeconomyDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']};cls.config=load(ROOT/'scripts/dataeconomy_emiss_sources.json');cls.contracts={c['indicator_id']:c for c in cls.config['sources']};cls.baseline={sid:normalize_payload(input_packet(sid),cls.aliases,cls.regions) for sid in cls.contracts};cls.statistics=load(ROOT/DATA/'statistics.json');cls.analytics=load(ROOT/DATA/'analytics.json')
    def raw(self,sid,year,label,name='Российская Федерация'):
        rows=[r for r in input_packet(sid)['observations'] if r['year']==year and r['territory_name']==name and json.loads(r['dimensions_json']).get('Период')==label];self.assertEqual(len(rows),1);return rows[0]
    def norm(self,sid,row):return normalize_record(row,self.contracts[sid],self.aliases,self.regions)
    def test_all_physical_values_dimensions_dates_and_raw_strings_retained(self):
        total=0
        for sid,p in self.baseline.items():
            original={r['observation_key']:r for r in input_packet(sid)['observations']};self.assertEqual(len(p['observations']),len(original));total+=len(original)
            for row in p['observations']:
                old=original[row['source_observation_key']]
                for field,key in [('value','value_numeric'),('raw_value','value_raw'),('unit','unit'),('source_frequency','period_kind'),('source_period_start','period_start'),('source_period_end','period_end')]:self.assertEqual(row[field],old[key])
                self.assertEqual(row['source_dimensions'],json.loads(old['dimensions_json']));self.assertEqual(row['source_attributes'],json.loads(old['attributes_json']))
        self.assertEqual((len(self.contracts),total),(48,12159))
    def test_source_evidence_query_hashes_and_bundle_crc(self):
        for sid in self.contracts:
            with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
                self.assertIsNone(z.testzip());p=json.loads(z.read('input.json'))
                for f in p['evidence_files']:self.assertEqual(hashlib.sha256(z.read(f['archive_path'])).hexdigest(),f['sha256'])
                for f in json.loads(p['snapshot']['raw_manifest_json']):
                    if f.get('query_file'):
                        name='source/'+'/'.join(x for x in f['query_file'].replace('\\','/').split('/') if x);selected=json.loads(z.read(name))['selected'];self.assertEqual(hashlib.sha256(json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),f['query_sha256'])
    def test_fraud_index_above_one_hundred_is_valid_and_ytd(self):
        rows=self.baseline['62751']['observations'];above=[r for r in rows if r['value']>100];self.assertEqual(len(above),12);self.assertTrue(all(not r['excluded'] for r in above));self.assertTrue(all(r['frequency']=='cumulative_ytd' and r['source_frequency']=='monthly' for r in rows));self.assertEqual(self.contracts['62751']['baseline_year'],2024);self.assertIsNone(self.contracts['62751']['upper_bound'])
        dec=self.norm('62751',self.raw('62751',2025,'декабрь'));self.assertEqual(dec['value'],153.7);self.assertEqual(dec['period_start'],'2025-01-01');self.assertEqual(dec['source_period_start'],'2025-12-01')
    def test_investment_index_does_not_inherit_share_ceiling(self):
        self.assertIsNone(self.contracts['62857']['upper_bound']);self.assertTrue(all(not r['excluded'] for r in self.baseline['62857']['observations']))
        row=self.raw('62765',2025,'декабрь');row['value_numeric']=101;self.assertTrue(self.norm('62765',row)['excluded'])
    def test_quantum_zeros_retained_separately_from_analytical_eligibility(self):
        rows=[r for p in self.baseline.values() for r in p['observations'] if r['excluded']];self.assertEqual(len(rows),8);self.assertEqual({r['source_id'] for r in rows},{'62889','62830'});self.assertTrue(all(r['value']==0 and r['analytical_value'] is None for r in rows))
        for sid in ['62889','62830']:
            source=next(s for s in self.statistics['sources'] if s['id']==sid);self.assertEqual(source['latest_published']['period'],'2026-09');self.assertEqual(source['latest_published']['value'],0);self.assertEqual(source['latest_national']['value'],0)
        self.assertEqual(self.statistics['coverage']['domain_violations'],0)
    def test_teacher_tablet_zeros_are_valid_not_missing(self):
        p=self.baseline['62757'];self.assertTrue(all(r['value']==0 and not r['excluded'] for r in p['observations']));profile=next(r for r in self.analytics['digital']['regional_profiles'] if r['source_id']=='62757');self.assertEqual((profile['n'],profile['zero_count']),(88,88))
    def test_graduate_zeros_do_not_prove_training_ceased(self):
        zero=[r for r in self.baseline['62866']['observations'] if r['value']==0];self.assertTrue(zero);self.assertTrue(all(not r['excluded'] and any(f['code']=='graduate_calendar_requires_review' for f in r['quality_flags']) for r in zero))
    def test_source_months_do_not_become_independent_annual_facts(self):
        self.assertEqual(self.statistics['coverage']['independent_annual_national_facts'],0);self.assertTrue(all(not r['annual_comparison_eligible'] for p in self.baseline.values() for r in p['observations']));self.assertTrue(all(not r['eligible'] for r in self.analytics['forecast_eligibility']))
    def test_reviewed_december_anchors_remain_original_monthly_records(self):
        sources=[s for s in self.statistics['sources'] if s['annual_equivalents']];self.assertEqual({s['id'] for s in sources},{'62765','62767','62815'})
        for s in sources:
            for r in s['annual_equivalents']:self.assertEqual(r['frequency'],'monthly');self.assertFalse(r['is_independent_annual_fact']);self.assertFalse(r['formal_attainment_eligible']);self.assertFalse(r['year_end_rule_verified_from_primary']);self.assertEqual(r['reference_observation_id'],r['id'])
        satisfaction=next(s for s in self.statistics['sources'] if s['id']=='62766');self.assertEqual(satisfaction['annual_equivalents'],[])
    def test_conditional_targets_respect_zero_denominator_and_explicit_units(self):
        comparisons=self.analytics['target_comparisons'];self.assertEqual(len(comparisons),44);self.assertTrue(all(not c['formal_attainment_eligible'] for c in comparisons));self.assertTrue(all(c['fact_frequency']!='annual' for c in comparisons))
        r=next(c for c in comparisons if c['source_id']=='62883');self.assertEqual((r['fact_value'],r['target_value']),(0,0));self.assertIsNone(r['ratio_percent'])
        self.assertEqual({r['source_id'] for r in self.analytics['blocked_target_comparisons']},{'62868','62809'})
        self.assertEqual(canonical_unit('Километр; тысяча метров'),canonical_unit('километр (тысяча метров)'))
    def test_national_scope_excluding_new_subjects_is_explicit_and_not_regional(self):
        for sid in ['63143','63144','63145']:
            self.assertTrue(all(r['geo_level']=='national' and r['national_scope']=='rf_excluding_new_subjects_since_2023' and r['code'] is None for r in self.baseline[sid]['observations']))
        self.assertEqual(self.statistics['coverage']['other_territory_observations'],0)
    def test_ytd_quality_revision_preserves_original_dates_and_avoids_false_yoy(self):
        rows=self.baseline['63144']['observations'];self.assertTrue(all(r['frequency']==('cumulative_ytd' if r['year']>=2026 else 'monthly') for r in rows));self.assertFalse(any(c['source_id']=='63144' for c in self.analytics['national_changes']))
        r=next(r for r in rows if r['period']=='2026-09');self.assertEqual((r['period_start'],r['source_period_start']),('2026-01-01','2026-09-01'))
    def test_repeated_annual_inputs_do_not_create_monthly_change_history(self):
        for sid in ['62814','62816','62883']:self.assertFalse(any(c['source_id']==sid for c in self.analytics['national_changes']));self.assertFalse(self.contracts[sid]['temporal_comparison_allowed'])
    def test_unexplained_software_break_is_not_bridged_by_yoy_comparison(self):
        rows=[r for r in self.analytics['national_changes'] if r['source_id']=='62815'];self.assertTrue(rows);self.assertTrue(all(r['from_period']>='2025-08' for r in rows))
    def test_all_seven_distributions_independently_match_original_values(self):
        expected={'62766':(85,52.85,57.52,65.57,0),'62815':(88,64.69,76.835,88.0675,0),'62767':(85,100,100,100,0),'62760':(85,98.22,98.74,99.17,0),'62763':(89,2,2,3,8),'62752':(63,0,0,0,51),'62757':(88,0,0,0,88)}
        for p in self.analytics['digital']['regional_profiles']:
            sid=p['source_id'];raw=input_packet(sid)['observations'];values=[r['value_numeric'] for r in raw if r['year']==2026 and json.loads(r['dimensions_json']).get('Период')=='сентябрь' and r['territory_name']!='Российская Федерация'];n,q1,med,q3,zeros=expected[sid]
            self.assertEqual(len(values),n);qs=statistics.quantiles(values,n=4,method='inclusive');self.assertAlmostEqual(qs[0],q1);self.assertAlmostEqual(qs[2],q3);self.assertAlmostEqual(statistics.median(values),med);self.assertEqual(sum(v==0 for v in values),zeros);self.assertEqual(len(p['reference_observation_ids']),n);self.assertFalse(p['national_reference_comparable'])
    def test_national_application_share_outside_regional_range_is_visible(self):
        p=next(r for r in self.analytics['digital']['regional_profiles'] if r['source_id']=='62760');self.assertEqual(p['national_value'],77.1);self.assertEqual(p['minimum'],88.05);self.assertLess(p['national_value'],p['minimum'])
    def test_latest_source_dates_keep_august_and_september_distinct(self):
        for sid in ['62814','62816','62857','62817','62818','62813']:self.assertEqual(next(s for s in self.statistics['sources'] if s['id']==sid)['latest_published']['period'],'2026-08')
    def test_source_csv_preserves_all_records_and_raw_strings(self):
        for sid in self.contracts:
            originals={r['id']:r for r in load(ROOT/DATA/'series'/f'{sid}.json')['observations']};rows=list(csv.DictReader(io.StringIO(gzip.decompress((ROOT/DOWNLOADS/'series'/f'{sid}.csv.gz').read_bytes()).decode('utf-8-sig'))));self.assertEqual({r['id'] for r in rows},set(originals))
            for r in rows:self.assertEqual(r['raw_value'],originals[r['id']]['raw_value']);self.assertEqual(r['source_period_start'],originals[r['id']]['source_period_start'])
    def test_future_values_and_changed_units_are_rejected_for_analysis(self):
        r=self.raw('62765',2025,'декабрь');r.update(year=2027,period_start='2027-12-01',period_end='2027-12-31');dims=json.loads(r['dimensions_json']);dims['Год']='2027';r['dimensions_json']=json.dumps(dims);self.assertTrue(self.norm('62765',r)['excluded'])
        r=self.raw('62765',2025,'декабрь');r['unit']='единица'
        with self.assertRaises(ValueError):self.norm('62765',r)
    def test_wrong_original_date_cannot_be_hidden_by_ytd_conversion(self):
        r=self.raw('62760',2025,'декабрь');r['period_end']='2025-12-30'
        with self.assertRaises(ValueError):self.norm('62760',r)
    def test_merge_preserves_verified_values_when_new_export_is_missing(self):
        old=self.baseline['62760']['observations'][0];missing={**old,'value':None};merged,added,revisions=merge_observations([old],[missing]);self.assertEqual(merged[0]['value'],old['value']);self.assertEqual((added,revisions),(0,[]))
        revised={**old,'value':old['value']+.01};_,_,revisions=merge_observations([old],[revised]);self.assertEqual(len(revisions),1)
        with self.assertRaises(ValueError):merge_observations([old],[revised,revised])

class DataeconomyMultivariateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m=load(ROOT/DATA/'analytics.json')['multivariate']
    def test_author_matrix_replay_and_all_sensitivity_references_match(self):
        m=self.m;self.assertTrue(m['replication']['passed']);self.assertEqual(len(m['replication']['checks']),164);self.assertTrue(all(c['passed'] for c in m['replication']['checks']));s=m['summary'];self.assertEqual((s['regions'],s['features'],s['imputed_cells']),(85,5,1));self.assertAlmostEqual(s['pc12_variance'],.5138791052081269)
    def test_single_matrix_imputation_is_moscow_software_and_has_no_source_id(self):
        m=self.m;self.assertEqual(len(m['imputations']),1);r=m['imputations'][0];self.assertEqual((r['code'],r['source_id']),('77','62815'));self.assertIsNone(r['raw_value']);self.assertIsNone(r['observation_id']);self.assertAlmostEqual(r['used_value'],76.835);self.assertFalse(m['methods']['source_series_imputed'])
    def test_cluster_starts_and_feature_omissions_are_not_misreported_as_stable(self):
        m=self.m;self.assertEqual((m['summary']['eligible_seed_runs'],m['summary']['eligible_feature_omissions']),(1,1));self.assertEqual(sorted(m['baseline']['clusters']['labels'].count(k) for k in [1,2]),[36,49]);self.assertAlmostEqual(m['summary']['silhouette'],.2437408110804886);self.assertEqual(next(x['omitted_source_id'] for x in m['feature_sensitivity'] if x['selected_k']>=2),'62767');self.assertFalse(m['summary']['ranking_validated'])
    def test_temporal_comparison_has_84_observed_regions_and_no_imputation(self):
        t=self.m['temporal'];self.assertEqual((t['n_regions'],t['imputed_cells'],t['previous_k'],t['current_k']),(84,0,0,2));self.assertAlmostEqual(t['pc12_subspace_overlap'],.6871548700328443);self.assertTrue(38<t['pc12_max_principal_angle_degrees']<40)
    def test_isolation_forest_seed_frequency_is_not_risk_probability(self):
        f=self.m['outlier_sensitivity'];self.assertEqual((f['n_estimators'],f['contamination'],len(f['runs'])),(200,.15,7));self.assertEqual(len(f['rows']),85);self.assertTrue(all(abs(r['algorithmic_flag_fraction']-r['flagged_runs']/7)<1e-12 for r in f['rows']))
    def test_previous_month_revision_does_not_become_numerical_replication_failure(self):
        packets={sid:load(ROOT/DATA/'series'/f'{sid}.json') for sid in SOURCE_IDS}
        row=next(r for r in packets['62766']['observations'] if r['code']=='22' and r['period_end']=='2026-08-31')
        self.assertEqual(row['value'],55.66)
        row.update(value=55.76,analytical_value=55.76,raw_value='55.76')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);reference=Path('inputs/dataeconomy/statistics/multivariate_reference.json');(root/reference).parent.mkdir(parents=True)
            shutil.copy2(ROOT/reference,root/reference)
            m=build_multivariate(root,packets,load(ROOT/DATA/'statistics.json')['sources'])
        r=m['replication'];self.assertTrue(r['baseline_reference_input_identical']);self.assertFalse(r['temporal_reference_input_identical']);self.assertFalse(r['reference_input_identical'])
        self.assertEqual((r['status'],r['checked_scopes'],r['skipped_scopes']),('current_input_differs_from_reference',['baseline'],['temporal']))
        self.assertTrue(r['passed']);self.assertEqual(len(r['checks']),159);self.assertTrue(all(c['passed'] and not c['metric'].startswith('temporal_') for c in r['checks']))
        self.assertEqual(m['baseline']['raw_matrix'],self.m['baseline']['raw_matrix']);self.assertNotAlmostEqual(m['temporal']['pc12_subspace_overlap'],self.m['temporal']['pc12_subspace_overlap'])
    def test_unavailable_matrix_replaces_previous_computed_downloads(self):
        packets={sid:load(ROOT/DATA/'series'/f'{sid}.json') for sid in SOURCE_IDS};packets['62760']['observations']=[]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);reference=Path('inputs/dataeconomy/statistics/multivariate_reference.json');(root/reference).parent.mkdir(parents=True)
            shutil.copy2(ROOT/reference,root/reference);destination=root/DOWNLOADS;destination.mkdir(parents=True)
            files=list((ROOT/DOWNLOADS).glob('multivariate*.csv'))+[ROOT/DOWNLOADS/'multivariate.json']
            for path in files:shutil.copy2(path,destination/path.name)
            self.assertEqual(load(destination/'multivariate.json')['status'],'computed')
            m=build_multivariate(root,packets,load(ROOT/DATA/'statistics.json')['sources'])
            self.assertEqual(m['status'],'no_common_publication_period');self.assertEqual(load(destination/'multivariate.json'),m)
            for path in destination.glob('multivariate*.csv'):
                with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
                self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],m['status']);self.assertEqual(rows[0]['data_rows_available'],'False')

class DataeconomyRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=load(ROOT/'scripts/dataeconomy_emiss_sources.json');cls.contracts={s['indicator_id']:s for s in cls.config['sources']};cls.sid='62760';cls.meta,cls.selected,cls.items,cls.raw=source_export(cls.sid,cls.contracts[cls.sid]);cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']}
    def isolated(self,td):
        root=Path(td)
        for relative in ['scripts/dataeconomy_emiss_sources.json','public/data/catalog.json',str(DATA/'refresh-status.json'),str(DATA/'series'/f'{self.sid}.json'),str(DATA/'provenance'/f'{self.sid}.json')]:
            dest=root/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,dest)
        return root
    def client(self,kind):
        outer=self
        class Fake:
            def metadata(self,sid):
                if kind=='network':raise EmissConnectorError('Recorded outage',category='network_error')
                if kind=='metadata_only':return {'no_numeric_grid':True}
                if kind=='wrong_title':return {**outer.meta,'indicator_title':'Другой показатель'}
                return outer.meta
            def export(self,meta,selected):return copy.deepcopy(outer.items),{},hashlib.sha256(outer.raw).hexdigest(),outer.raw
            def close(self):pass
        return Fake()
    def test_all_48_original_formats_pass_live_parser_without_identity_drift(self):
        for sid,contract in self.contracts.items():
            with self.subTest(source=sid):
                meta,selected,items,raw=source_export(sid,contract);roles=infer_field_map(meta,contract.get('field_overrides'));incoming=normalized_live(items,meta,roles,selected,contract,self.aliases,'2026-10-15T23:59:59+00:00',self.regions);expected=normalize_payload(input_packet(sid),self.aliases,self.regions)['observations'];self.assertEqual({r['id']:r['value'] for r in incoming},{r['id']:r['value'] for r in expected})
    def test_missing_single_region_is_rejected_even_above_minimum_coverage(self):
        sid='62766';contract=self.contracts[sid];meta,selected,items,_=source_export(sid,contract);roles=infer_field_map(meta,contract['field_overrides']);victim=next(r.dimensions.get('ОКАТО') for r in items if r.dimensions.get('ОКАТО') not in {None,'Российская Федерация'});kept=[r for r in items if r.dimensions.get('ОКАТО')!=victim]
        with self.assertRaises(EmissConnectorError) as err:normalized_live(kept,meta,roles,selected,contract,self.aliases,'2026-10-29T00:00:00+00:00',self.regions)
        self.assertEqual(err.exception.category,'geography_coverage_drop')
    def test_bounded_outage_keeps_dates_and_both_source_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);old=load(root/DATA/'refresh-status.json');before=[sha256(root/DATA/k/f'{self.sid}.json') for k in ['series','provenance']];report=run(root,client=self.client('network'),retries=0,max_failures=3,rebuild=False);self.assertEqual((report['attempted_sources'],report['failed_sources'],report['deferred_sources'],report['published_sources']),(3,3,45,0));self.assertEqual(report['published_at'],old['published_at']);self.assertEqual(report['last_success'],old['last_success']);self.assertEqual(before,[sha256(root/DATA/k/f'{self.sid}.json') for k in ['series','provenance']])
    def test_metadata_only_response_does_not_erase_numeric_publication(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/f'{self.sid}.json');report=run(root,only=self.sid,client=self.client('metadata_only'),rebuild=False);self.assertEqual(report['published_sources'],0);self.assertEqual(sha256(root/DATA/'series'/f'{self.sid}.json'),before)
    def test_changed_source_title_cannot_publish(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/f'{self.sid}.json');report=run(root,only=self.sid,client=self.client('wrong_title'),rebuild=False);self.assertEqual(next(s for s in report['sources'] if s['source_id']==self.sid)['state'],'title_mismatch');self.assertEqual(sha256(root/DATA/'series'/f'{self.sid}.json'),before)
    def test_successful_ytd_refresh_preserves_keys_and_raw_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=load(root/DATA/'series'/f'{self.sid}.json');report=run(root,only=self.sid,client=self.client('valid'),rebuild=False);self.assertEqual((report['published_sources'],report['failed_sources']),(1,0));after=load(root/DATA/'series'/f'{self.sid}.json');self.assertEqual({r['id']:r['value'] for r in before['observations']},{r['id']:r['value'] for r in after['observations']});status=next(s for s in report['sources'] if s['source_id']==self.sid);self.assertEqual(sha256(root/'public'/status['raw_file']),load(root/DATA/'provenance'/f'{self.sid}.json')['current_raw_sha256'])

if __name__=='__main__':unittest.main()
