"""Statistical meaning, source fidelity and non-destructive refresh acceptance."""
from __future__ import annotations

import copy
import functools
import gzip
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from healthtech_data import DATA, DOWNLOADS, PROJECT, load, observation, period, number, merge_observations, canonical_key
from healthtech_formats import parse_export
from longlife_formats import parse_excel
from import_healthtech_release import run as replay
from build_healthtech_analytics import build, target_comparisons, make_source, changes
from refresh_healthtech_emiss import run as refresh, live_rows, validate_coverage
from emiss_adapter.sdmx import ParsedSdmxObservation
from emiss_adapter.errors import EmissConnectorError


def contract(sid):
    return next(s for s in load(ROOT/'scripts/healthtech_emiss_sources.json')['sources'] if s['indicator_id']==sid)


@functools.lru_cache(maxsize=None)
def frozen_packet(sid):
    """Immutable release fixture; future legitimate refreshes may change live data."""
    source=contract(sid);path=ROOT/DOWNLOADS/'inputs'/(sid+'.zip')
    if not path.exists():
        return {'project_id':PROJECT,'source_id':sid,'title':source['title'],'unit':source['unit'],'observations':[],
                'origin_kind':'no_numeric_publication_recovered','published_at':None,'acquired_at':None,'snapshot_id':None}
    with zipfile.ZipFile(path) as archive:
        meta,rows,_=parse_export(archive.read(sid+'.csv.gz'),archive.read(sid+'.xls.zip'),sid)
        retrieved=json.loads(archive.read('retrieval.json'))
        digest=hashlib.sha256(archive.read(sid+'.xls.zip')).hexdigest()
    observations=sorted([observation(sid,r,source) for r in rows],key=lambda r:(r['period_end'],r['frequency'],r['id']))
    return {'project_id':PROJECT,'source_id':sid,'title':source['title'],'unit':source['unit'],'observations':observations,
            'origin_kind':'secondary_emiss_republication','published_at':meta['published_at'],
            'acquired_at':max(r['retrieved_at'] for r in retrieved if r.get('status')==200),'snapshot_id':'nsedc:'+digest}


def packet(sid):
    return copy.deepcopy(frozen_packet(sid))


def frozen_sources():
    return [make_source(c,packet(c['indicator_id']),{}) for c in load(ROOT/'scripts/healthtech_emiss_sources.json')['sources']]


def fact(sid, label, frequency='monthly'):
    return next(r for r in packet(sid)['observations'] if r['period']==label and r['frequency']==frequency)


def raw(sid,value='10',year=2025,period_label='62 декабрь',unit=None):
    c=contract(sid)
    return observation(sid,{'year':year,'period_label':period_label,'value_raw':value,
                           'territory_label':'643 Российская Федерация','unit_label':unit or c['unit']},c)


def candidate():
    temp=tempfile.TemporaryDirectory()
    path=Path(temp.name)
    (path/'scripts').mkdir()
    shutil.copy2(ROOT/'scripts/healthtech_emiss_sources.json',path/'scripts/healthtech_emiss_sources.json')
    shutil.copytree(ROOT/DATA,path/DATA)
    shutil.copytree(ROOT/DOWNLOADS,path/DOWNLOADS)
    # Network tests begin from the immutable, reproducible source fixture.
    replay(path,from_bundles=True)
    build(path)
    return temp,path


def metadata(sid):
    c=contract(sid);rows=packet(sid)['observations']
    vals=lambda seq:[{'id':str(x),'title':str(x)} for x in sorted(set(seq))]
    return {'indicator_id':sid,'indicator_title':c['title'],'source_updated_at':'2026-09-10',
            'filters':[{'field_id':'0','title':'Показатель','values':[{'id':sid,'title':c['title']}]},
                       {'field_id':'1','title':'Год','object_parameter':'columnObjectIds','values':vals(r['year'] for r in rows)},
                       {'field_id':'2','title':'Период','object_parameter':'lineObjectIds','values':vals(r['original_period_label'] for r in rows)},
                       {'field_id':'3','title':'Единица измерения','object_parameter':'lineObjectIds','values':vals([c['unit']])},
                       {'field_id':'4','title':'ОКАТО','object_parameter':'lineObjectIds','values':vals(['Российская Федерация'])}]}


def live_items(sid):
    c=contract(sid)
    return [ParsedSdmxObservation(value=r['value'],period=str(r['year']),raw_value=r['raw_value'],
             dimensions={'Показатель':c['title'],'Год':str(r['year']),'Период':r['original_period_label'],
                         'Единица измерения':c['unit'],'ОКАТО':'Российская Федерация'},
             dimension_codes={},attributes={'source_cell':r['source_locator']}) for r in packet(sid)['observations']]


class FakeClient:
    def __init__(self,sid=None,values=None,error=None):self.sid=sid;self.values=values;self.error=error;self.calls=[]
    def metadata(self,sid):
        self.calls.append(sid)
        if self.error:raise self.error
        return metadata(sid)
    def export(self,meta,selected):
        values=self.values if self.values is not None else live_items(meta['indicator_id'])
        b=b'validated-test-source'
        return values,{},hashlib.sha256(b).hexdigest(),b


class HealthtechSourceTests(unittest.TestCase):
    def test_exact_raw_counts(self):
        rows=[r for c in load(ROOT/'scripts/healthtech_emiss_sources.json')['sources'] for r in packet(c['indicator_id'])['observations']]
        self.assertEqual((len(rows),sum(r['value'] is not None for r in rows),sum(r['value'] is None for r in rows)),(233,191,42))

    def test_every_csv_cell_matches_preserved_xls(self):
        total=0
        for source in load(ROOT/'scripts/healthtech_emiss_sources.json')['sources']:
            sid=source['indicator_id'];p=ROOT/DOWNLOADS/'inputs'/(sid+'.zip')
            if not p.exists():continue
            with zipfile.ZipFile(p) as archive:
                meta,rows,check=parse_export(archive.read(sid+'.csv.gz'),archive.read(sid+'.xls.zip'),sid)
            expected={r['source_observation_key']:r for r in packet(sid)['observations']}
            for r in rows:
                value=observation(sid,r,source)
                self.assertEqual(value,expected[value['source_observation_key']])
            total+=check['cross_checked_cells']
        self.assertEqual(total,233)

    def test_registry_is_twenty_one_cards_and_twenty_sources(self):
        cards=load(ROOT/DATA/'indicators.json')['items']
        self.assertEqual(len(cards),21)
        self.assertEqual(sum(len(c['source_ids']) for c in cards),20)
        c5=next(c for c in cards if c['indicator_code']=='2.14.С5.3')
        self.assertEqual(c5['source_ids'],[])
        self.assertEqual(c5['mapping_status'],'no_confirmed_source_id')

    def test_shared_official_excel_parser_accepts_fourteen_actual_workbooks(self):
        checked=0
        for source in load(ROOT/'scripts/healthtech_emiss_sources.json')['sources']:
            sid=source['indicator_id'];path=ROOT/DOWNLOADS/'inputs'/(sid+'.zip')
            if not path.exists():continue
            with zipfile.ZipFile(path) as archive:
                nested=archive.read(sid+'.xls.zip')
            import io
            with zipfile.ZipFile(io.BytesIO(nested)) as archive:body=archive.read(sid+'.xls')
            meta=metadata(sid);selected={f['field_id']:f['values'] for f in meta['filters']}
            parsed,_=parse_excel(body,meta,selected)
            current=live_rows(parsed,source,'2026-10-29')
            expected={canonical_key(r):r['value'] for r in packet(sid)['observations']}
            self.assertEqual({canonical_key(r):r['value'] for r in current},expected)
            checked+=1
        self.assertEqual(checked,14)

    def test_no_regional_values(self):
        stats=load(ROOT/DATA/'statistics.json')
        self.assertEqual(stats['summary']['regional_sources'],0)
        for source in stats['sources']:
            self.assertEqual(source['regional_latest'],[])
            self.assertEqual({r['geo_level'] for r in source['national']} - {'national'},set())

    def test_annual_value_not_december(self):
        annual=fact('62986','2025','annual');dec=fact('62986','2025-12')
        self.assertEqual(annual['value'],4.55)
        self.assertEqual(dec['value'],0)
        self.assertEqual(annual['analytical_value'],4.55)
        self.assertIsNone(dec['analytical_value'])
        self.assertNotEqual(annual['id'],dec['id'])

    def test_future_annual_missing_not_zero(self):
        row=fact('62986','2026','annual')
        self.assertIsNone(row['value']);self.assertEqual(row['raw_value'],'')

    def test_only_one_independent_annual_fact(self):
        sources=frozen_sources()
        self.assertEqual(sum(r['analytical_value'] is not None for s in sources for r in s['annual']),1)
        self.assertTrue(all(s['annual_equivalents']==[] for s in sources))

    def test_annual_placeholder_zero_preserved(self):
        for sid in ['62928','62929','62984','62985','62986','62987']:
            row=fact(sid,'2026-08')
            self.assertEqual(row['value'],0);self.assertIsNone(row['analytical_value'])

    def test_december_not_relabelled(self):
        for sid in ['62928','62929','62984','62985','62987']:
            row=fact(sid,'2025-12');self.assertEqual(row['frequency'],'monthly');self.assertFalse(row['annual_comparison_eligible'])

    def test_unit_conflict_preserved(self):
        row=fact('62985','2025-12')
        self.assertEqual(row['unit'],'процент');self.assertEqual(row['value'],0.73);self.assertIsNone(row['analytical_value'])
        self.assertFalse(contract('62985')['target_comparison_allowed'])

    def test_gva_is_quarantined_from_derived_analytics(self):
        rows=packet('63059')['observations']
        self.assertEqual([r['value'] for r in rows],[17.7,12.6,None,16.6])
        self.assertTrue(all(r['analytical_value'] is None for r in rows))
        self.assertFalse(contract('63059')['target_comparison_allowed'])

    def test_growth_above_hundred_is_valid(self):
        row=fact('62987','2025-12')
        self.assertEqual(row['analytical_value'],249.59)
        self.assertFalse(any(f['code']=='outside_domain' for f in row['quality_flags']))

    def test_missing_june_not_invented(self):
        self.assertNotIn('2026-06',{r['period'] for r in packet('62988')['observations']})
        source=next(s for s in frozen_sources() if s['id']=='62988')
        self.assertEqual(source['gaps'][0]['kind'],'absent_source_row')

    def test_rolling_proxies_not_annual(self):
        for sid,value in [('63446',105),('63447',21)]:
            self.assertEqual(contract(sid)['period_semantics'],'rolling_five_calendar_years')
            self.assertEqual(fact(sid,'2026-08')['value'],value)
            self.assertEqual({r['frequency'] for r in packet(sid)['observations']},{'monthly'})

    def test_cumulative_windows_distinct(self):
        self.assertEqual(contract('63130')['period_semantics'],'cumulative_since_2025')
        self.assertEqual(contract('63132')['period_semantics'],'cumulative_calendar_year')
        self.assertEqual(contract('62988')['period_semantics'],'cumulative_calendar_year_ratio')

    def test_pre_inception_zero_not_evidence_of_absence(self):
        for sid in ['63130','63132']:
            row=fact(sid,'2025-04');self.assertEqual(row['value'],0);self.assertIsNone(row['analytical_value'])
            self.assertIsNotNone(fact(sid,'2025-05')['analytical_value'])

    def test_source_date_differs_from_repository_metadata(self):
        p=packet('62986')
        with zipfile.ZipFile(ROOT/DOWNLOADS/'inputs/62986.zip') as archive:repository=json.loads(archive.read('package.json'))['result']
        self.assertEqual(p['published_at'],'2026-09-08')
        self.assertNotEqual(repository['dataset_update'][:10],p['published_at'])
        self.assertTrue(p['acquired_at'].startswith('2026-10-29'))

    def test_same_month_change_is_exact(self):
        rows=changes(frozen_sources())[0]
        change=next(r for r in rows if r['source_id']=='63132' and r['to_period']=='2026-08')
        self.assertEqual((change['from_value'],change['to_value'],change['difference']),(272.8,51.32,-221.48))
        self.assertAlmostEqual(change['relative_change_percent'],-81.18768328445748)

    def test_annual_target_ratio_only(self):
        sources=frozen_sources()
        targets=[{'source_id':'62986','indicator_code':'2.14.С.1','unit':'процент','years':{'2025':1.5,'2026':5}},
                 {'source_id':'62928','unit':'процент','years':{'2025':50}},
                 {'source_id':'63059','unit':'процент','years':{'2025':10}}]
        result=target_comparisons(sources,targets)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['difference'],3.05);self.assertAlmostEqual(result[0]['ratio_percent'],303.3333333333333)

    def test_wrong_target_unit_not_compared(self):
        sources=frozen_sources()
        self.assertEqual(target_comparisons(sources,[{'source_id':'62986','unit':'единица','years':{'2025':1.5}}]),[])

    def test_fractional_normalized_count_valid(self):
        self.assertEqual(fact('62984','2025-12')['analytical_value'],0.96)

    def test_number_rejects_invalid_and_infinite(self):
        for value in ['banana','inf','nan','1e9999']:
            with self.assertRaises(ValueError):number(value)
        self.assertIsNone(number('–'));self.assertEqual(number('0'),0)

    def test_unknown_period_and_country_rejected(self):
        with self.assertRaises(ValueError):period(2026,'полугодие')
        c=contract('63130')
        with self.assertRaises(ValueError):observation('63130',{'year':2026,'period_label':'август','unit_label':'единица','value_raw':'1','territory_label':'Москва'},c)

    def test_out_of_range_percent_retained_flagged(self):
        row=raw('62988','102.3',2026,'август')
        self.assertEqual(row['value'],102.3);self.assertIsNone(row['analytical_value'])

    def test_current_packets_match_provenance_and_preserve_reviewed_contracts(self):
        for source in load(ROOT/'scripts/healthtech_emiss_sources.json')['sources']:
            sid=source['indicator_id'];path=ROOT/DATA/'series'/(sid+'.json');current=load(path)
            provenance=load(ROOT/DATA/'provenance'/(sid+'.json'))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),provenance['published_sha256'])
            self.assertEqual(current['unit'],source['unit'])
            self.assertEqual(current['project_id'],PROJECT)
            self.assertEqual(len({canonical_key(r) for r in current['observations']}),len(current['observations']))
            if current['origin_kind']=='secondary_emiss_republication':
                self.assertEqual(current['observations'],packet(sid)['observations'])
            else:
                self.assertTrue(all(r['geo_level']=='national' for r in current['observations']))


class HealthtechRefreshTests(unittest.TestCase):
    def test_failed_refresh_preserves_all_packet_bytes_and_dates(self):
        temp,path=candidate()
        with temp:
            before={p.name:p.read_bytes() for p in (path/DATA/'series').glob('*.json')}
            old=load(path/DATA/'refresh-status.json')['published_at']
            client=FakeClient(error=EmissConnectorError('HTTP 403',category='http_error'))
            result=refresh(path,client=client,max_failures=3,rebuild=False)
            self.assertEqual((result['attempted'],result['failed'],result['deferred']),(3,3,17))
            self.assertEqual(result['published_at'],old)
            self.assertEqual({p.name:p.read_bytes() for p in (path/DATA/'series').glob('*.json')},before)
            self.assertTrue(all(s.get('checked_at')!=result['checked_at'] for s in result['sources'][3:]))

    def test_only_selection_does_not_probe_other_sources(self):
        temp,path=candidate()
        with temp:
            client=FakeClient(error=EmissConnectorError('network unavailable',category='network_error'))
            result=refresh(path,only='63130',client=client,rebuild=False)
            self.assertEqual(client.calls,['63130']);self.assertEqual(result['attempted'],1)

    def test_empty_response_cannot_erase_snapshot(self):
        temp,path=candidate()
        with temp:
            p=path/DATA/'series/63130.json';before=p.read_bytes()
            result=refresh(path,only='63130',client=FakeClient(values=[]),rebuild=False)
            self.assertEqual(result['failed'],1);self.assertEqual(p.read_bytes(),before)

    def test_successful_revised_source_is_published(self):
        temp,path=candidate()
        with temp:
            values=live_items('63130')
            selected=next(r for r in values if r.dimensions['Год']=='2026' and r.dimensions['Период']=='60 август')
            selected.value=8;selected.raw_value='8'
            result=refresh(path,only='63130',client=FakeClient(values=values),rebuild=True)
            self.assertEqual((result['failed'],result['published'],result['updated']),(0,1,1))
            current=load(path/DATA/'series/63130.json');self.assertEqual(current['origin_kind'],'live_emiss')
            self.assertEqual(next(r['value'] for r in current['observations'] if r['period']=='2026-08'),8)
            self.assertEqual(load(path/DATA/'provenance/63130.json')['revisions'][0]['previous_value'],7)

    def test_missing_existing_period_rejected(self):
        rows=packet('63130')['observations']
        with self.assertRaises(EmissConnectorError):validate_coverage(rows,[r for r in rows if r['period']!='2025-12'])

    def test_annual_fact_cannot_disappear(self):
        rows=packet('62986')['observations'];new=copy.deepcopy(rows)
        next(r for r in new if r['period']=='2025' and r['frequency']=='annual')['value']=None
        with self.assertRaises(EmissConnectorError):validate_coverage(rows,new)

    def test_live_country_unit_and_future_guards(self):
        for field,value in [('ОКАТО','Москва'),('Единица измерения','процент'),('Год','2030')]:
            row=copy.deepcopy(live_items('63130')[0]);row.dimensions[field]=value
            with self.assertRaises(EmissConnectorError):live_rows([row],contract('63130'),'2026-10-29')

    def test_merge_tracks_revisions_without_relabelling_frequency(self):
        old=packet('62986')['observations'];new=copy.deepcopy(old)
        next(r for r in new if r['frequency']=='annual' and r['year']==2025)['value']=4.6
        merged,added,revisions=merge_observations(old,new)
        self.assertEqual(added,0);self.assertEqual(len(revisions),1)
        self.assertEqual(revisions[0]['frequency'],'annual')

    def test_offline_replay_without_inputs(self):
        temp,path=candidate()
        with temp:
            before={p.name:p.read_bytes() for p in (path/DATA/'series').glob('*.json')}
            result=replay(path,from_bundles=True)
            self.assertEqual(result['numeric_observations'],191)
            self.assertEqual({p.name:p.read_bytes() for p in (path/DATA/'series').glob('*.json')},before)
            self.assertFalse((path/'inputs').exists())

    def test_analytics_build_needs_no_inputs(self):
        temp,path=candidate()
        with temp:
            result=build(path)
            self.assertEqual(result['annual_facts'],1)
            self.assertFalse((path/'inputs').exists())


if __name__=='__main__':unittest.main()
