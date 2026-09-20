"""Offline contract tests. Fixtures are deliberately synthetic, never statistical data."""
import copy, json, tempfile, unittest, hashlib, sys
from pathlib import Path
from urllib.parse import parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import httpx
from emiss_adapter.metadata import parse_indicator_metadata,infer_field_map
from emiss_adapter.catalog import parse_organizations_catalog,EmissCatalogItem
from emiss_adapter.client import Client,query_plan,resolve_indicator,redact
from emiss_adapter.sdmx import parse_sdmx,ParsedSdmxObservation,SdmxParseError
from emiss_adapter.normalize import convert,decode_period,merge,COLS,territory_key
from emiss_adapter.errors import EmissConnectorError
from refresh_emiss import run

TITLE='Тестовый показатель'
HTML='''<html><title>Тест</title><script>window.test={filters:{
0:{title:'Показатель',values:{999:{title:'Тестовый показатель'}}},
1:{title:'Территория',values:{77:{title:'г. Москва'},78:{title:'Санкт-Петербург'}}},
2:{title:'Год',values:{2025:{title:'2025'}}},
3:{title:'Период',values:{0:{title:'значение показателя за год'},1:{title:'январь'},2:{title:'февраль'}}},
4:{title:'Единица измерения',values:{u:{title:'единица'}}}},
left_columns:[1],top_columns:[2,3],groups:[4]};</script></html>'''
META=parse_indicator_metadata(HTML,'999')
SOURCE={'source_id':'data_21','indicator_code':'2.14.Я.2','indicator_id':'999','titles':[TITLE], 'unit':'единица','first_year':2025,'dimension_defaults':{},'field_overrides':{},'min_regional_count':2,'expected_period_types':['год','месяц']}
CONFIG={'base_url':'https://www.fedstat.ru','allowed_hosts':['www.fedstat.ru','fedstat.ru'],'timeout_seconds':2,'retries':0,'min_interval_seconds':0,'max_cells':10000,'sources':[SOURCE]}
ALIASES={territory_key('Москва'):'77',territory_key('Санкт-Петербург'):'78'}

def xml(month='0', v1='1,4',v2='1.2'):
    parts=[]
    for r,v in [('77',v1),('78',v2)]:
        parts.append(f'<Series><SeriesKey><Value concept="1" value="{r}"/><Value concept="2" value="2025"/><Value concept="3" value="{month}"/><Value concept="4" value="u"/></SeriesKey><Obs><Time>2025</Time><ObsValue value="{v}"/></Obs></Series>')
    return ('<?xml version="1.0"?><GenericData><DataSet>'+''.join(parts)+'</DataSet></GenericData>').encode()

class Contract(unittest.TestCase):
    def setUp(self): self.roles,self.selected=query_plan(META,SOURCE)
    def assertCategory(self,cat,fn):
        with self.assertRaises(EmissConnectorError) as c: fn()
        self.assertEqual(c.exception.category,cat)
    def convert(self,raw=None,meta=META,source=SOURCE):
        rows,_=parse_sdmx(raw or xml()); roles,selected=query_plan(meta,source)
        return convert(rows,meta,roles,selected,source,ALIASES,'2026-09-20T00:00:00Z')
    def test_metadata_js_not_evaluated(self):
        self.assertEqual(META['indicator_title'],TITLE)
        self.assertEqual(self.roles,{'territory':'1','year':'2','month':'3'})
        self.assertEqual(next(f for f in META['filters'] if f['field_id']=='2')['object_parameter'],'columnObjectIds')
    def test_metadata_missing_filters(self):
        self.assertCategory('metadata_contract_changed',lambda:parse_indicator_metadata('<html>error</html>','999'))
    def test_ambiguous_role_rejected(self):
        m=copy.deepcopy(META);m['filters'].append({**m['filters'][1],'field_id':'9'})
        self.assertCategory('ambiguous_field_mapping',lambda:infer_field_map(m))
    def test_explicit_role_can_resolve(self):
        m=copy.deepcopy(META);m['filters'].append({**m['filters'][1],'field_id':'9'})
        self.assertEqual(infer_field_map(m,{'territory':'1'})['territory'],'1')
    def test_unselected_dimension_never_uses_first(self):
        m=copy.deepcopy(META);m['filters'].append({'field_id':'5','title':'Пол','values':[{'id':'m','title':'Мужчины'},{'id':'f','title':'Женщины'}]})
        self.assertCategory('dimension_requires_confirmation',lambda:query_plan(m,SOURCE))
    def test_title_must_match(self):
        self.assertCategory('title_mismatch',lambda:query_plan({**META,'indicator_title':'Чужой показатель'},SOURCE))
    def test_query_limit(self): self.assertCategory('query_too_large',lambda:query_plan(META,SOURCE,max_cells=1))
    def test_catalog_status_and_exact_match(self):
        rows=parse_organizations_catalog(f'<ul><li class="i_excluded"><a href="/indicator/998">{TITLE}</a></li><li class="i_actual"><a href="/indicator/999">{TITLE}</a></li></ul>')
        self.assertEqual(resolve_indicator(rows,[TITLE]).indicator_id,'999')
    def test_catalog_ambiguity(self):
        rows=[EmissCatalogItem(str(i),TITLE,'','actual') for i in (998,999)]
        self.assertCategory('ambiguous_mapping',lambda:resolve_indicator(rows,[TITLE]))
    def test_catalog_no_fuzzy_guess(self):
        rows=[EmissCatalogItem('999',TITLE+' другой','','actual')]
        self.assertCategory('unresolved_mapping',lambda:resolve_indicator(rows,[TITLE]))
    def test_annual_and_monthly_different(self):
        a=self.convert();m=self.convert(xml('1'))
        self.assertEqual(a[0]['type'],'год');self.assertEqual(m[0]['type'],'месяц')
        merged,new,rev=merge(a,m);self.assertEqual(new,2);self.assertEqual(len(merged),4)
    def test_cumulative_and_annual_not_mixed(self):
        self.assertEqual(decode_period(2025,'январь-декабрь')[0],'накопительно с января')
        self.assertEqual(decode_period(2025,'значение показателя за год')[0],'год')
    def test_no_positional_month_guess(self): self.assertCategory('ambiguous_period',lambda:decode_period(2025,None,'2025',False))
    def test_leap_month(self): self.assertEqual(decode_period(2024,'февраль')[2],'2024-02-29')
    def test_new_period_type_rejected(self):
        self.assertCategory('period_schema_changed',lambda:self.convert(xml('1'),source={**SOURCE,'expected_period_types':['год']}))
    def test_decimal_comma(self): self.assertEqual(self.convert()[0]['value'],1.4)
    def test_missing_and_zero_are_different(self):
        s={**SOURCE,'min_regional_count':0}
        result=self.convert(xml(v1='-',v2='0'),source=s)
        self.assertIsNone(result[0]['value']);self.assertEqual(result[1]['value'],0)
    def test_nonfinite_rejected(self): self.assertCategory('invalid_numeric',lambda:self.convert(xml(v1='inf')))
    def test_html_not_data(self):
        with self.assertRaises(SdmxParseError):parse_sdmx(b'<html>error</html>')
    def test_unknown_territory_rejected(self):
        raw=xml().replace(b'value="77"',b'value="12345"')
        self.assertCategory('territory_requires_mapping',lambda:self.convert(raw))
    def test_coverage_loss(self):
        raw=xml(v1='-',v2='1.2')
        self.assertCategory('coverage_drop',lambda:self.convert(raw))
    def test_wrong_unit(self):
        m=copy.deepcopy(META);m['filters'][4]['values'][0]['title']='миллион рублей'
        self.assertCategory('unit_mismatch',lambda:self.convert(meta=m))
    def test_conflicting_duplicates(self):
        obs,_=parse_sdmx(xml());obs.append(copy.deepcopy(obs[0]));obs[-1].value=9
        self.assertCategory('conflicting_duplicates',lambda:convert(obs,META,self.roles,self.selected,SOURCE,ALIASES,'now'))
    def test_missing_does_not_delete_good_value(self):
        old=self.convert();new=copy.deepcopy(old);new[0]['value']=None
        merged,added,changes=merge(old,new)
        self.assertEqual(merged[0]['value'],old[0]['value']);self.assertEqual(changes,[])
    def test_revision_is_recorded(self):
        old=self.convert();new=self.convert(xml(v1='1.5'));merged,added,changes=merge(old,new)
        self.assertEqual(len(changes),1);self.assertEqual(changes[0]['old_value'],1.4)
    def test_historical_dimension_change_rejected(self):
        old=self.convert(); new=copy.deepcopy(old)
        new[0]['dimensions']={**new[0]['dimensions'], 'Условие': 'Новая категория'}
        self.assertCategory('historical_dimension_changed',lambda:merge(old,new))
    def test_transport_keeps_repeated_keys(self):
        seen={}
        def handle(req):
            seen.update(parse_qs(req.content.decode()));return httpx.Response(200,content=xml())
        c=Client(CONFIG,transport=httpx.MockTransport(handle))
        try: c.export(META,self.selected)
        finally:c.close()
        self.assertEqual(seen['format'],['sdmx']);self.assertIn('0_999',seen['selectedFilterIds'])
        self.assertIn('1_77',seen['selectedFilterIds']);self.assertIn('1_78',seen['selectedFilterIds'])
        self.assertEqual(seen['columnObjectIds'],['2','3'])
    def test_transport_cookie_session(self):
        calls=[]
        def handle(req):
            calls.append(req.headers.get('cookie',''))
            return httpx.Response(200,text=HTML,headers={'set-cookie':'JSESSIONID=fixture; Path=/; Secure'})
        c=Client(CONFIG,transport=httpx.MockTransport(handle))
        try:c.metadata('999');c.metadata('999')
        finally:c.close()
        self.assertIn('JSESSIONID=fixture',calls[1])
    def test_untrusted_redirect(self):
        c=Client(CONFIG,transport=httpx.MockTransport(lambda req:httpx.Response(302,headers={'location':'https://example.org/'})))
        try:self.assertCategory('unsafe_url',lambda:c.request('GET','/indicator/999'))
        finally:c.close()
    def test_challenge_not_bypassed(self):
        c=Client(CONFIG,transport=httpx.MockTransport(lambda req:httpx.Response(200,text='<html>CAPTCHA</html>')))
        try:self.assertCategory('access_challenge',lambda:c.request('GET','/indicator/999'))
        finally:c.close()
    def test_redaction(self):self.assertNotIn('user:pass',redact('http://user:pass@proxy.test:80 failed'))
    def test_fixture_pipeline_publish_and_retain(self):
        outer=self
        class Fake:
            failed=False
            def catalog(self):return [EmissCatalogItem('999',TITLE,'/indicator/999','actual')]
            def metadata(self,i):
                if self.failed:raise EmissConnectorError('fixture outage',category='network_error')
                return META
            def export(self,m,s):
                body=xml(v1='1.5');items,meta=parse_sdmx(body)
                return items,meta,hashlib.sha256(body).hexdigest(),body
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for p in ['scripts','public/data/baseline','public/data/latest']:(root/p).mkdir(parents=True)
            (root/'scripts/emiss_sources.json').write_text(json.dumps(CONFIG))
            (root/'public/data/catalog.json').write_text(json.dumps({'regions':[{'id':'77','name':'Москва'},{'id':'78','name':'Санкт-Петербург'}]}))
            base={'columns':COLS,'rows':[[r.get(k) for k in COLS] for r in self.convert()]}
            (root/'public/data/baseline/data_21.json').write_text(json.dumps(base))
            client=Fake();one=run(root,client=client)
            self.assertEqual(one['state'],'success');self.assertEqual(one['sources'][0]['revisions'],1)
            data_path=root/'public/data/latest/data_21.json';before=data_path.read_bytes()
            self.assertTrue((root/'public/data/latest/data_21_raw_sdmx.zip').exists())
            client.failed=True;two=run(root,client=client)
            self.assertEqual(two['state'],'failed');self.assertEqual(data_path.read_bytes(),before)
            self.assertEqual(two['last_success'],one['last_success'])
            self.assertEqual(two['sources'][0]['published_file'],one['sources'][0]['published_file'])

if __name__=='__main__':unittest.main()
