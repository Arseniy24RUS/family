"""Meaningful source-contract, arithmetic and outage tests for ecology statistics."""
from __future__ import annotations
import copy
import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import statistics
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from environment_data import DATA,DOWNLOADS,normalize_record,normalize_payload,region_aliases,merge_observations,load,sha256,category_dimensions
from build_environment_analytics import author_correlations,canonical_unit,national_point
from refresh_environment_emiss import normalized_live,run
from environment_formats import parse_excel,parse_grid
from emiss_adapter.sdmx import parse_sdmx
from emiss_adapter.metadata import infer_field_map
from emiss_adapter.errors import EmissConnectorError


def input_packet(sid):
    with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:return json.loads(z.read('input.json'))


def source_export(sid,contract):
    with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
        p=json.loads(z.read('input.json'));metadata=json.loads(p['snapshot']['metadata_json'])
        meta={'indicator_id':sid,'indicator_title':contract['title'],'filters':metadata['filters']}
        selected=json.loads(z.read(next(n for n in z.namelist() if n.endswith('query.json'))))['selected']
        rawname=next(n for n in z.namelist() if n.endswith(('.xls','.json.gz','.xml.gz')))
        raw=z.read(rawname);raw=gzip.decompress(raw) if rawname.endswith('.gz') else raw
    items,_=parse_excel(raw,meta,selected) if rawname.endswith('.xls') else parse_grid(raw,meta,selected) if rawname.endswith('.json.gz') else parse_sdmx(raw)
    return meta,selected,items,raw


class EnvironmentDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']}
        cls.config=load(ROOT/'scripts/environment_emiss_sources.json');cls.contracts={c['indicator_id']:c for c in cls.config['sources']}
        cls.baseline={sid:normalize_payload(input_packet(sid),cls.aliases,cls.regions) for sid in cls.contracts}
        cls.statistics=load(ROOT/DATA/'statistics.json');cls.analytics=load(ROOT/DATA/'analytics.json')
    def raw(self,sid,year,label,name='Российская Федерация'):
        rows=[r for r in input_packet(sid)['observations'] if r['year']==year and r['territory_name']==name and json.loads(r['dimensions_json']).get('Период')==label]
        self.assertEqual(len(rows),1);return rows[0]
    def norm(self,sid,row):return normalize_record(row,self.contracts[sid],self.aliases,self.regions)
    def test_original_cells_dates_categories_and_missing_are_preserved(self):
        total=numeric=0
        for sid,p in self.baseline.items():
            original={r['observation_key']:r for r in input_packet(sid)['observations']}
            self.assertEqual(len(p['observations']),len(original));self.assertEqual(len({r['id'] for r in p['observations']}),len(original))
            for row in p['observations']:
                r=original[row['source_observation_key']]
                for key,source_key in [('value','value_numeric'),('raw_value','value_raw'),('unit','unit'),('source_frequency','period_kind'),('source_period_start','period_start'),('source_period_end','period_end')]:self.assertEqual(row[key],r[source_key])
                self.assertEqual(row['source_dimensions'],json.loads(r['dimensions_json']));self.assertEqual(row['source_attributes'],json.loads(r['attributes_json']))
                if r['value_numeric'] is None:self.assertEqual(row['status'],'missing');self.assertIsNone(row['analytical_value'])
            total+=len(original);numeric+=sum(r['value_numeric'] is not None for r in original.values())
        self.assertEqual((len(self.contracts),total,numeric),(18,10282,9316))
    def test_retained_evidence_and_query_hashes_are_reproducible(self):
        for sid in self.contracts:
            with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
                self.assertIsNone(z.testzip());p=json.loads(z.read('input.json'))
                for f in p['evidence_files']:self.assertEqual(hashlib.sha256(z.read(f['archive_path'])).hexdigest(),f['sha256'])
                for f in json.loads(p['snapshot']['raw_manifest_json']):
                    if f.get('query_file'):
                        name='source/'+'/'.join(t for t in f['query_file'].replace('\\','/').split('/') if t)
                        selected=json.loads(z.read(name))['selected'];digest=hashlib.sha256(json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                        self.assertEqual(digest,f['query_sha256'])
    def test_waste_annual_is_independent_of_december_and_ytd_label_is_disclosed(self):
        for sid,annual,december in [('62792',56.6,56.2),('62793',81.1,80.6)]:
            a=self.norm(sid,self.raw(sid,2025,'значение показателя за год'));d=self.norm(sid,self.raw(sid,2025,'декабрь'))
            self.assertEqual((a['frequency'],a['value']),('annual',annual));self.assertEqual((d['frequency'],d['source_frequency'],d['value']),('cumulative_ytd','monthly',december))
            self.assertEqual(d['period_start'],'2025-01-01');self.assertEqual(d['source_period_start'],'2025-12-01');self.assertNotEqual(a['id'],d['id'])
    def test_visits_only_match_eight_month_windows(self):
        a=self.norm('62777',self.raw('62777',2025,'август'));b=self.norm('62777',self.raw('62777',2026,'август'))
        self.assertEqual((a['value'],b['value']),(16.2,14.7296));self.assertAlmostEqual((b['value']/a['value']-1)*100,-9.07654320987654)
        self.assertEqual(national_point(self.baseline,'62777',2025)['value'],22.6)
        self.assertTrue(all(x['from_period'][4:]==x['to_period'][4:] for x in self.analytics['national_changes'] if x['source_id']=='62777'))
    def test_annual_forest_ratio_and_program_accumulation_are_different(self):
        ratio=self.norm('62781',self.raw('62781',2025,'значение показателя за год'));area=self.norm('62782',self.raw('62782',2025,'значение показателя за год'))
        self.assertEqual(ratio['value'],149.64);self.assertFalse(ratio['excluded']);self.assertEqual(area['value'],1334.9768)
        self.assertTrue(self.contracts['62781']['annual_reset']);self.assertFalse(self.contracts['62782']['annual_reset']);self.assertEqual(self.contracts['62782']['cumulative_since'],2025)
        newest=self.norm('62782',self.raw('62782',2026,'сентябрь'));self.assertAlmostEqual(newest['value']-area['value'],562.7936,places=8)
        high=[r for r in self.baseline['62781']['observations'] if r['value']>100];self.assertTrue(high);self.assertTrue(all(not r['excluded'] for r in high))
    def test_forest_125_rule_does_not_claim_known_zero_denominator(self):
        r=self.raw('62781',2025,'значение показателя за год');r['value_numeric']=125;r['value_raw']='125';p=self.norm('62781',r)
        self.assertFalse(p['excluded']);self.assertIn('value_125_requires_components',{f['code'] for f in p['quality_flags']});self.assertNotIn('zero_denominator',p)
    def test_only_out_of_domain_waste_cells_are_excluded(self):
        rows=[r for p in self.baseline.values() for r in p['observations']]
        excluded=[r for r in rows if r['value'] is not None and r['excluded']]
        self.assertEqual(len(excluded),36);self.assertEqual({r['source_id'] for r in excluded},{'62792','62793'});self.assertTrue(all(r['value']>100 for r in excluded))
    def test_future_number_and_unit_changes_are_not_accepted_as_facts(self):
        raw=self.raw('62777',2025,'значение показателя за год');raw['year']=2027;raw['period_start']='2027-01-01';raw['period_end']='2027-12-31'
        d=json.loads(raw['dimensions_json']);d['Год']='2027';raw['dimensions_json']=json.dumps(d);r=self.norm('62777',raw);self.assertTrue(r['excluded']);self.assertEqual(r['value'],22.6)
        raw=self.raw('62777',2025,'август');raw['unit']='тысяча человек'
        with self.assertRaises(ValueError):self.norm('62777',raw)
    def test_wrong_original_date_rejected_before_ytd_interpretation(self):
        raw=self.raw('62792',2025,'декабрь');raw['period_end']='2025-12-30'
        with self.assertRaises(ValueError):self.norm('62792',raw)
    def test_geographic_grains_not_mixed(self):
        for sid,n in [('62862',12),('62863',29),('62860',29)]:
            rows=self.baseline[sid]['observations'];cities=[r for r in rows if r['geo_level']=='project_territory']
            self.assertEqual(len({r['name'] for r in cities}),n);self.assertTrue(all(r['code'] is None and r['map_id'] is None for r in cities));self.assertTrue(all(not r['geographic_comparison_eligible'] for r in cities))
        self.assertEqual(len({r['code'] for r in self.baseline['62781']['observations'] if r['geo_level']=='regional'}),81)
        self.assertEqual(len({r['name'] for r in self.baseline['62781']['observations'] if r['geo_level']=='other'}),8)
    def test_air_mean_independently_reproduced_from_raw_territories(self):
        for sid,n in [('62862',12),('62863',29)]:
            p=input_packet(sid);allowed=set(self.contracts[sid]['project_territories']);cities=[r for r in p['observations'] if r['year']==2025 and r['period_kind']=='annual' and r['territory_name'] in allowed]
            national=[r for r in p['observations'] if r['year']==2025 and r['period_kind']=='annual' and r['territory_name']=='Российская Федерация'][0]
            self.assertEqual(len(cities),n);mean=statistics.mean(r['value_numeric'] for r in cities);self.assertLessEqual(abs(mean-national['value_numeric']),.000050001)
            a=next(g for g in self.analytics['air_groups'] if g['source_id']==sid);self.assertAlmostEqual(a['annual']['unweighted_mean'],mean);self.assertEqual(a['annual']['n'],n)
            self.assertEqual(a['latest']['n'],0);self.assertFalse(a['latest']['complete']);self.assertTrue(all(r['value'] is None for r in a['latest']['rows']))
    def test_spearman_independently_recomputed_with_ties_from_raw_values(self):
        lookups={sid:{r['territory_name']:r['value_numeric'] for r in input_packet(sid)['observations'] if r['year']==2025 and r['period_kind']=='annual' and r['territory_name']!='Российская Федерация'} for sid in ['62792','62793']}
        names=sorted(set(lookups['62792'])&set(lookups['62793']));self.assertEqual(len(names),85)
        def ranks(values):
            return [1+sum(x<v for x in values)+(sum(x==v for x in values)-1)/2 for v in values]
        for selected,n,expected in [(names,85,-.5570313968037884),([x for x in names if x!='Еврейская автономная область'],84,-.6055947211592854)]:
            a=ranks([lookups['62792'][x] for x in selected]);b=ranks([lookups['62793'][x] for x in selected]);rho=statistics.correlation(a,b)
            self.assertEqual(len(selected),n);self.assertAlmostEqual(rho,expected,places=13)
        self.assertEqual(self.analytics['correlations']['strict']['excluded_codes'],['79']);self.assertEqual(self.analytics['correlations']['imputed_cells'],0)
        self.assertEqual(lookups['62792']['Еврейская автономная область'],0);self.assertEqual(lookups['62793']['Еврейская автономная область'],0)
    def test_waste_counts_do_not_make_complementary_shares(self):
        a=self.analytics['waste_profiles'];self.assertEqual((a['both_at_least_80'],a['landfill_at_least_90'],a['treatment_below_25']),(10,54,29));self.assertEqual(a['national']['sum_percent'],137.7)
    def test_discontinued_and_methodology_limits_survive_targets(self):
        ids={r['source_id'] for r in self.analytics['target_comparisons']};self.assertFalse(ids&{'62779','62787','62804'});self.assertEqual(len(ids),13)
        self.assertTrue(all(r['fact_frequency']=='annual' and not r['formal_attainment_eligible'] for r in self.analytics['target_comparisons']))
        self.assertEqual(self.contracts['62779']['source_status'],'discontinued');self.assertFalse(self.contracts['62779']['scenario_allowed']);self.assertEqual(len(self.baseline['62779']['observations']),21)
        self.assertTrue(all(not f['eligible'] for f in self.analytics['forecast_eligibility']));self.assertEqual(self.analytics['methodology']['pca'],'not_performed')
    def test_water_and_baikal_not_carried_beyond_february(self):
        for sid in ['62871','62854']:
            source=next(s for s in self.statistics['sources'] if s['id']==sid);self.assertEqual(source['latest_national']['period'],'2026-02')
        self.assertEqual(canonical_unit('млн м³'),self.contracts['62871']['unit'])
    def test_flat_csv_retains_ids_units_categories_and_raw_values(self):
        for sid in self.contracts:
            rows=load(ROOT/DATA/'series'/f'{sid}.json')['observations'];by_id={r['id']:r for r in rows}
            text=gzip.decompress((ROOT/DOWNLOADS/'series'/f'{sid}.csv.gz').read_bytes()).decode('utf-8-sig');csvrows=list(csv.DictReader(io.StringIO(text)))
            self.assertEqual(len(csvrows),len(rows));self.assertEqual({r['id'] for r in csvrows},set(by_id))
            for r in csvrows:
                old=by_id[r['id']];self.assertEqual(r['raw_value'],old['raw_value'] or '');self.assertEqual(r['unit'],old['unit']);self.assertEqual(json.loads(r['category']),old['category'])
    def test_merge_preserves_known_values_and_records_revision(self):
        old=copy.deepcopy(self.baseline['62777']['observations'][0]);missing={**old,'value':None};merged,added,revisions=merge_observations([old],[missing]);self.assertEqual(merged[0]['value'],old['value']);self.assertEqual((added,revisions),(0,[]))
        changed={**old,'value':old['value']+.1};merged,_,revisions=merge_observations([old],[changed]);self.assertEqual(len(revisions),1)
        with self.assertRaises(ValueError):merge_observations([old],[changed,changed])


class EnvironmentRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=load(ROOT/'scripts/environment_emiss_sources.json');cls.contracts={s['indicator_id']:s for s in cls.config['sources']}
        cls.sid='62777';cls.meta,cls.selected,cls.items,cls.raw=source_export(cls.sid,cls.contracts[cls.sid])
        cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']}
    def isolated(self,td):
        root=Path(td)
        for relative in ['scripts/environment_emiss_sources.json','public/data/catalog.json',str(DATA/'refresh-status.json'),str(DATA/'series'/f'{self.sid}.json'),str(DATA/'provenance'/f'{self.sid}.json')]:
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
    def test_all_original_exports_pass_live_parser_without_identity_drift(self):
        for sid,contract in self.contracts.items():
            with self.subTest(source=sid):
                meta,selected,items,raw=source_export(sid,contract);roles=infer_field_map(meta,contract.get('field_overrides'))
                incoming=normalized_live(items,meta,roles,selected,contract,self.aliases,'2026-10-15T23:59:59+00:00',self.regions)
                expected=normalize_payload(input_packet(sid),self.aliases,self.regions)['observations']
                self.assertEqual({r['id']:r['value'] for r in incoming},{r['id']:r['value'] for r in expected})
    def test_city_coverage_drop_fails_even_with_all_regional_aggregates(self):
        sid='62862';contract=self.contracts[sid];meta,selected,items,_=source_export(sid,contract);roles=infer_field_map(meta,contract['field_overrides'])
        kept=[r for r in items if r.dimensions.get('ОКАТО')!='Братск']
        self.assertLess(len(kept),len(items))
        with self.assertRaises(EmissConnectorError) as err:normalized_live(kept,meta,roles,selected,contract,self.aliases,'2026-10-29T00:00:00+00:00',self.regions)
        self.assertEqual(err.exception.category,'geography_coverage_drop')
    def test_source_outage_is_bounded_and_preserves_statistics_and_dates(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);old=load(root/DATA/'refresh-status.json');before=[sha256(root/DATA/k/f'{self.sid}.json') for k in ['series','provenance']]
            result=run(root,client=self.client('network'),timeout=12,retries=0,max_failures=3,rebuild=False)
            self.assertEqual((result['attempted_sources'],result['failed_sources'],result['deferred_sources'],result['published_sources']),(3,3,15,0))
            self.assertEqual(result['published_at'],old['published_at']);self.assertEqual(result['last_success'],old['last_success']);self.assertEqual(before,[sha256(root/DATA/k/f'{self.sid}.json') for k in ['series','provenance']])
    def test_metadata_only_is_not_numeric_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/f'{self.sid}.json');result=run(root,only=self.sid,client=self.client('metadata_only'),rebuild=False)
            self.assertEqual(result['published_sources'],0);self.assertEqual(sha256(root/DATA/'series'/f'{self.sid}.json'),before)
    def test_changed_title_cannot_publish(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/f'{self.sid}.json');result=run(root,only=self.sid,client=self.client('wrong_title'),rebuild=False)
            entry=next(s for s in result['sources'] if s['source_id']==self.sid);self.assertEqual(entry['state'],'title_mismatch');self.assertEqual(sha256(root/DATA/'series'/f'{self.sid}.json'),before)
    def test_valid_ytd_export_preserves_observation_identity_and_raw_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=load(root/DATA/'series'/f'{self.sid}.json');result=run(root,only=self.sid,client=self.client('valid'),rebuild=False)
            self.assertEqual((result['published_sources'],result['failed_sources']),(1,0));after=load(root/DATA/'series'/f'{self.sid}.json')
            self.assertEqual({r['id']:r['value'] for r in after['observations']},{r['id']:r['value'] for r in before['observations']})
            entry=next(s for s in result['sources'] if s['source_id']==self.sid);raw=root/'public'/entry['raw_file'];self.assertTrue(zipfile.is_zipfile(raw));self.assertEqual(sha256(raw),load(root/DATA/'provenance'/f'{self.sid}.json')['current_raw_sha256'])

if __name__=='__main__':unittest.main()
