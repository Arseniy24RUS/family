"""Meaningful source-contract, arithmetic and outage tests for economic statistics."""
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
from competitive_data import DATA,DOWNLOADS,normalize_record,normalize_payload,region_aliases,merge_observations,load,sha256,category_dimensions
from build_competitive_analytics import canonical_unit,national_point,canonical_regions
from refresh_competitive_emiss import normalized_live,run
from competitive_formats import parse_excel,parse_grid
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


class CompetitiveDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']}
        cls.config=load(ROOT/'scripts/competitive_emiss_sources.json');cls.contracts={c['indicator_id']:c for c in cls.config['sources']}
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
        self.assertEqual((len(self.contracts),total,numeric),(37,9329,7502))
    def test_retained_evidence_and_query_hashes_are_reproducible(self):
        for sid in self.contracts:
            with zipfile.ZipFile(ROOT/DOWNLOADS/'emiss_inputs'/f'{sid}.zip') as z:
                self.assertIsNone(z.testzip());p=json.loads(z.read('input.json'))
                for f in p['evidence_files']:self.assertEqual(hashlib.sha256(z.read(f['archive_path'])).hexdigest(),f['sha256'])
                for f in json.loads(p['snapshot']['raw_manifest_json']) if p['snapshot'] else []:
                    if f.get('query_file'):
                        name='source/'+'/'.join(t for t in f['query_file'].replace('\\','/').split('/') if t)
                        selected=json.loads(z.read(name))['selected'];digest=hashlib.sha256(json.dumps(selected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                        self.assertEqual(digest,f['query_sha256'])
    def test_explicit_annual_label_resolves_climate_without_manufacturing_december_fact(self):
        p=self.norm('63089',self.raw('63089',2025,'ежегодно'));self.assertEqual((p['frequency'],p['source_frequency'],p['value']),('annual','unresolved',0))
        self.assertTrue(p['annual_comparison_eligible']);self.assertEqual(p['source_period_label'],'ежегодно')
        s=self.norm('63094',self.raw('63094',2025,'декабрь'));self.assertFalse(s['annual_comparison_eligible']);self.assertEqual(s['value'],36.7)
        self.assertIsNone(national_point(self.baseline,'63094',2025))
    def test_quarterly_revenue_has_ytd_start_without_summing_quarters(self):
        p=self.norm('63088',self.raw('63088',2026,'III квартал'))
        self.assertEqual((p['frequency'],p['period'],p['period_start'],p['period_end']),('quarterly','2026-Q3','2026-01-01','2026-09-30'))
        self.assertEqual(p['source_frequency'],'unresolved');self.assertIsNone(p['source_period_start']);self.assertEqual(p['value'],1444772.16)
        self.assertFalse(p['annual_comparison_eligible']);self.assertTrue(self.contracts['63088']['annual_reset'])
        q=self.norm('63222',self.raw('63222',2026,'II квартал'));self.assertEqual(q['period_start'],'2026-04-01');self.assertEqual(q['value'],3)
    def test_macro_index_zeros_are_visible_but_not_analytic(self):
        rows=self.baseline['62709']['observations'];zero=[r for r in rows if r['value']==0];self.assertEqual(len(zero),17)
        self.assertTrue(all(r['raw_value'] in {'0','0.0'} and r['excluded'] and r['analytical_value'] is None for r in zero))
        s=next(s for s in self.statistics['sources'] if s['id']=='62709');self.assertEqual(s['latest_published']['period'],'2026-09');self.assertEqual(s['latest_published']['value'],0)
        self.assertEqual(s['latest_analytically_usable']['period'],'2025-12');self.assertEqual(s['latest_analytically_usable']['value'],105.7)
        self.assertFalse(s['scenario_allowed']);self.assertFalse(s['temporal_comparison_allowed'])
    def test_income_monthly_repetition_does_not_inflate_annual_history(self):
        a=self.norm('62979',self.raw('62979',2025,'значение показателя за год'));m=self.norm('62979',self.raw('62979',2025,'июль'))
        self.assertEqual((a['value'],m['value']),(106.8,100));self.assertTrue(a['annual_comparison_eligible']);self.assertFalse(m['annual_comparison_eligible']);self.assertFalse(m['temporal_comparison_eligible'])
        f=next(x for x in self.analytics['forecast_eligibility'] if x['source_id']=='62979');self.assertEqual(f['annual_observations'],1);self.assertFalse(f['eligible'])
    def test_nominal_growth_and_tax_proxy_cannot_become_real_annual_effects(self):
        s=self.contracts['62712'];self.assertTrue(s['nominal_growth_criterion']);self.assertFalse(s['real_growth']);self.assertFalse(s['scenario_allowed'])
        proxy=self.contracts['63165'];self.assertTrue(proxy['proxy_only']);self.assertEqual(proxy['reference_lag_months'],1);self.assertEqual(proxy['proxy_for_source_id'],'62979');self.assertFalse(proxy['target_comparison_allowed']);self.assertFalse(proxy['scenario_allowed'])
        self.assertNotIn('63165',{x['source_id'] for x in self.analytics['target_comparisons']})
    def test_health_ytd_keeps_original_month_and_does_not_mask_zero(self):
        p=self.norm('62960',self.raw('62960',2026,'сентябрь'));self.assertEqual((p['frequency'],p['source_frequency']),('cumulative_ytd','monthly'))
        self.assertEqual((p['period_start'],p['source_period_start']),('2026-01-01','2026-09-01'))
        for sid in ['62960','62961']:
            r=self.norm(sid,self.raw(sid,2026,'январь','Московская область'));self.assertEqual(r['value'],0);self.assertTrue(r['excluded'])
        zeros=[r for r in self.baseline['62991']['observations'] if r['value']==0];self.assertTrue(zeros);self.assertTrue(all(not r['excluded'] for r in zeros))
    def test_only_nineteen_documented_zero_indices_excluded(self):
        out=[r for p in self.baseline.values() for r in p['observations'] if r['value'] is not None and r['excluded']]
        self.assertEqual(self.statistics['coverage']['domain_violations'],0);self.assertEqual(self.statistics['coverage']['review_exclusions'],19);self.assertEqual(len(out),19);self.assertEqual({r['source_id'] for r in out},{'62709','62960','62961'});self.assertTrue(all(r['value']==0 for r in out))
    def test_regional_sme_statistics_independently_match_source_and_report(self):
        raw=input_packet('62979')['observations'];values=[r['value_numeric'] for r in raw if r['year']==2025 and r['period_kind']=='annual' and r['territory_name'] not in {'Российская Федерация','Районы Кабардино-Балкарской Республики/'} and r['value_numeric'] is not None]
        self.assertEqual(len(values),84);self.assertEqual(statistics.median(values),105.4);self.assertEqual(sum(x<100 for x in values),7)
        q=statistics.quantiles(values,n=4,method='inclusive');self.assertAlmostEqual(q[0],102.775);self.assertAlmostEqual(q[2],108.5)
        block=self.analytics['economics']['sme_income_2025'];self.assertEqual(block['n'],84);self.assertEqual(block['median'],statistics.median(values))
    def test_six_separate_regional_distributions_keep_different_windows(self):
        blocks=self.analytics['economics']['regional_profiles'];self.assertEqual([b['n'] for b in blocks],[84,84,88,88,88,85]);self.assertEqual(blocks[0]['period'],'2025');self.assertEqual(blocks[2]['period'],'2026-09')
        self.assertEqual(blocks[2]['median'],25.345);self.assertEqual(blocks[-1]['median'],1.1765);self.assertEqual(blocks[-1]['zero_count'],21)
        self.assertFalse(self.analytics['correlations']['computed']);self.assertFalse(self.analytics['economics']['composite_ranking_computed'])
        self.assertEqual(self.analytics['methodology']['pca'],'not_performed')
    def test_annual_target_summary_is_ten_arithmetic_comparisons(self):
        c=self.analytics['target_comparisons'];self.assertEqual(len(c),10);self.assertEqual((sum(r['difference']>0 for r in c),sum(r['difference']==0 for r in c),sum(r['difference']<0 for r in c)),(7,2,1))
        self.assertTrue(all(r['fact_frequency']=='annual' and not r['formal_attainment_eligible'] for r in c))
        climate=next(r for r in c if r['source_id']=='63089');self.assertEqual((climate['fact_value'],climate['target_value']),(0,0));self.assertIsNone(climate['ratio_percent'])
        income=next(r for r in c if r['source_id']=='62979');self.assertEqual(income['difference'],-1.1);self.assertEqual(income['target_value'],107.9)
    def test_metadata_only_does_not_mean_zero(self):
        empty=[s for s in self.statistics['sources'] if not s['available']];self.assertEqual(len(empty),7)
        self.assertTrue(all(s['latest_national'] is None and s['numeric_count']==0 and not s['national'] for s in empty))
        self.assertEqual(self.statistics['coverage']['unmapped_indicators'],12)
        self.assertTrue(all(not r['direct_emiss_verified'] for r in self.baseline.values() if r['origin_kind']=='metadata_only'))
    def test_regional_map_excludes_other_territorial_grains(self):
        rows=[r for p in self.baseline.values() for r in p['observations']];other=[r for r in rows if r['geo_level']=='other']
        self.assertEqual(len(other),29);self.assertEqual({r['name'] for r in other},{'Районы Кабардино-Балкарской Республики/'});self.assertTrue(all(r['code'] is None and not r['geographic_comparison_eligible'] for r in other))
    def test_domains_distinguish_shares_ratios_and_growth(self):
        ratio=self.raw('63093',2025,'декабрь');ratio['value_numeric']=120;ratio['value_raw']='120';self.assertFalse(self.norm('63093',ratio)['excluded'])
        share=self.raw('63094',2025,'декабрь');share['value_numeric']=120;share['value_raw']='120';self.assertTrue(self.norm('63094',share)['excluded'])
        growth=self.raw('62978',2025,'декабрь');growth['value_numeric']=-20;growth['value_raw']='-20';self.assertFalse(self.norm('62978',growth)['excluded'])
    def test_binary_systems_cannot_generate_fractional_trajectories(self):
        for sid in ['63089','63176']:
            self.assertEqual(self.contracts[sid]['domain'],'binary_status');self.assertFalse(self.contracts[sid]['scenario_allowed'])
        raw=self.raw('63089',2025,'ежегодно');raw['value_numeric']=.5;raw['value_raw']='0.5';self.assertTrue(self.norm('63089',raw)['excluded'])
        self.assertTrue(self.contracts['62979']['scenario_allowed'])
        self.assertFalse(self.norm('62979',self.raw('62979',2025,'июль'))['temporal_comparison_eligible'])
    def test_future_number_and_unit_changes_are_not_accepted_as_facts(self):
        raw=self.raw('62979',2025,'значение показателя за год');raw['year']=2027;raw['period_start']='2027-01-01';raw['period_end']='2027-12-31';d=json.loads(raw['dimensions_json']);d['Год']='2027';raw['dimensions_json']=json.dumps(d)
        r=self.norm('62979',raw);self.assertTrue(r['excluded']);self.assertEqual(r['value'],106.8)
        raw=self.raw('63088',2025,'I квартал');raw['unit']='триллион рублей'
        with self.assertRaises(ValueError):self.norm('63088',raw)
    def test_wrong_original_date_rejected_before_ytd_interpretation(self):
        raw=self.raw('62960',2025,'декабрь');raw['period_end']='2025-12-30'
        with self.assertRaises(ValueError):self.norm('62960',raw)
    def test_flat_csv_retains_ids_units_categories_and_raw_values(self):
        for sid in self.contracts:
            rows=load(ROOT/DATA/'series'/f'{sid}.json')['observations'];by_id={r['id']:r for r in rows};csvrows=list(csv.DictReader(io.StringIO(gzip.decompress((ROOT/DOWNLOADS/'series'/f'{sid}.csv.gz').read_bytes()).decode('utf-8-sig'))))
            self.assertEqual(len(csvrows),len(rows));self.assertEqual({r['id'] for r in csvrows},set(by_id))
            for r in csvrows:
                old=by_id[r['id']];self.assertEqual(r['raw_value'],old['raw_value'] or '');self.assertEqual(r['unit'],old['unit']);self.assertEqual(json.loads(r['category']),old['category'])
    def test_merge_preserves_known_values_and_records_revision(self):
        old=copy.deepcopy(self.baseline['63088']['observations'][0]);missing={**old,'value':None};merged,added,revisions=merge_observations([old],[missing]);self.assertEqual(merged[0]['value'],old['value']);self.assertEqual((added,revisions),(0,[]))
        changed={**old,'value':old['value']+.1};merged,_,revisions=merge_observations([old],[changed]);self.assertEqual(len(revisions),1)
        with self.assertRaises(ValueError):merge_observations([old],[changed,changed])

class CompetitiveRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=load(ROOT/'scripts/competitive_emiss_sources.json');cls.contracts={s['indicator_id']:s for s in cls.config['sources']}
        cls.sid='63088';cls.meta,cls.selected,cls.items,cls.raw=source_export(cls.sid,cls.contracts[cls.sid])
        cls.aliases=region_aliases(ROOT);cls.regions={str(r['id']):r for r in load(ROOT/'public/data/catalog.json')['regions']}
    def isolated(self,td):
        root=Path(td)
        for relative in ['scripts/competitive_emiss_sources.json','public/data/catalog.json',str(DATA/'refresh-status.json'),str(DATA/'series'/f'{self.sid}.json'),str(DATA/'provenance'/f'{self.sid}.json')]:
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
                if input_packet(sid)['snapshot'] is None:continue
                meta,selected,items,raw=source_export(sid,contract);roles=infer_field_map(meta,contract.get('field_overrides'))
                incoming=normalized_live(items,meta,roles,selected,contract,self.aliases,'2026-10-15T23:59:59+00:00',self.regions)
                expected=normalize_payload(input_packet(sid),self.aliases,self.regions)['observations']
                self.assertEqual({r['id']:r['value'] for r in incoming},{r['id']:r['value'] for r in expected})
    def test_single_missing_region_fails_even_above_minimum_count(self):
        sid='62979';contract=self.contracts[sid];meta,selected,items,_=source_export(sid,contract);roles=infer_field_map(meta,contract['field_overrides'])
        kept=[r for r in items if r.dimensions.get('ОКАТО')!='Республика Адыгея (Адыгея)']
        if len(kept)==len(items):
            victim=next(r.dimensions.get('ОКАТО') for r in items if r.dimensions.get('ОКАТО') not in {None,'Российская Федерация'})
            kept=[r for r in items if r.dimensions.get('ОКАТО')!=victim]
        self.assertLess(len(kept),len(items))
        with self.assertRaises(EmissConnectorError) as err:normalized_live(kept,meta,roles,selected,contract,self.aliases,'2026-10-29T00:00:00+00:00',self.regions)
        self.assertEqual(err.exception.category,'geography_coverage_drop')
    def test_source_outage_is_bounded_and_preserves_statistics_and_dates(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);old=load(root/DATA/'refresh-status.json');before=[sha256(root/DATA/k/f'{self.sid}.json') for k in ['series','provenance']]
            result=run(root,client=self.client('network'),timeout=12,retries=0,max_failures=3,rebuild=False)
            self.assertEqual((result['attempted_sources'],result['failed_sources'],result['deferred_sources'],result['published_sources']),(3,3,34,0))
            self.assertEqual(result['published_at'],old['published_at']);self.assertEqual(result['last_success'],old['last_success']);self.assertEqual(before,[sha256(root/DATA/k/f'{self.sid}.json') for k in ['series','provenance']])
    def test_metadata_only_is_not_numeric_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/f'{self.sid}.json');result=run(root,only=self.sid,client=self.client('metadata_only'),rebuild=False)
            self.assertEqual(result['published_sources'],0);self.assertEqual(sha256(root/DATA/'series'/f'{self.sid}.json'),before)
    def test_changed_title_cannot_publish(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=sha256(root/DATA/'series'/f'{self.sid}.json');result=run(root,only=self.sid,client=self.client('wrong_title'),rebuild=False)
            entry=next(s for s in result['sources'] if s['source_id']==self.sid);self.assertEqual(entry['state'],'title_mismatch');self.assertEqual(sha256(root/DATA/'series'/f'{self.sid}.json'),before)
    def test_valid_quarterly_ytd_export_preserves_observation_identity_and_raw_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root=self.isolated(td);before=load(root/DATA/'series'/f'{self.sid}.json');result=run(root,only=self.sid,client=self.client('valid'),rebuild=False)
            self.assertEqual((result['published_sources'],result['failed_sources']),(1,0));after=load(root/DATA/'series'/f'{self.sid}.json')
            self.assertEqual({r['id']:r['value'] for r in after['observations']},{r['id']:r['value'] for r in before['observations']})
            entry=next(s for s in result['sources'] if s['source_id']==self.sid);raw=root/'public'/entry['raw_file'];self.assertTrue(zipfile.is_zipfile(raw));self.assertEqual(sha256(raw),load(root/DATA/'provenance'/f'{self.sid}.json')['current_raw_sha256'])

if __name__=='__main__':unittest.main()
