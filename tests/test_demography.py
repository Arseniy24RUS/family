import unittest,json,sys,math,copy,subprocess,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from demography.cohort import simulate,validate_input,mortality_from_e0
from demography.indicator import forecast
from demography.repository_inputs import observed_stocks,annual_components,fetch_repository,norm
from reproduce_projection import same

def fixture():return json.loads((ROOT/'tests/fixtures/cohort_input.json').read_text())
def months(n=15):return [{'date':f'{2025+i//12}-{i%12+1:02d}-01','value':1.5-i*.001} for i in range(n)]
def xlsx(path,sheets):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    def col(n):
        out=''
        while n:n,v=divmod(n-1,26);out=chr(65+v)+out
        return out
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>'+''.join(f'<sheet name="{k}" sheetId="{i}" r:id="r{i}"/>' for i,k in enumerate(sheets,1))+'</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="r{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
        for i,rows in enumerate(sheets.values(),1):
            text=f'<worksheet xmlns="{ns}"><sheetData>'
            for j,row in enumerate(rows,1):
                text+=f'<row r="{j}">'
                for c,v in enumerate(row,1):
                    if v is None:continue
                    ref=col(c)+str(j)
                    text+=(f'<c r="{ref}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' if isinstance(v,str) else f'<c r="{ref}"><v>{v}</v></c>')
                text+='</row>'
            z.writestr(f'xl/worksheets/sheet{i}.xml',text+'</sheetData></worksheet>')

class IndicatorTests(unittest.TestCase):
    def test_reproducible(self):self.assertEqual(forecast(months()),forecast(months()))
    def test_end_and_weights(self):
        d=forecast(months());self.assertEqual(d['forecast'][-1]['date'],'2030-12-31');self.assertAlmostEqual(sum(m['weight'] for m in d['models']),1);self.assertEqual(len(d['forecast']),57)
    def test_intervals_and_members(self):
        for r in forecast(months())['forecast']:
            self.assertTrue(0<r['lo95']<=r['lo80']<=r['value']<=r['hi80']<=r['hi95']);self.assertTrue(r['model_min']<=r['value']+1e-10<=r['model_max']+1e-10)
    def test_time_validation_never_leaks(self):
        for b in forecast(months())['backtest']:self.assertLess(b['train_end'],b['target'])
    def test_constant(self):
        o=months()
        for r in o:r['value']=1.4
        for r in forecast(o)['forecast']:self.assertAlmostEqual(r['value'],1.4)
    def test_short_gap_duplicates_rejected(self):
        for o in [months(5),months()[:7]+months()[8:],months()+[months()[0]]]:
            with self.assertRaises(ValueError):forecast(o)
    def test_bad_values_rejected(self):
        for v in [None,True,float('nan'),0,-1]:
            o=months();o[0]['value']=v
            with self.assertRaises(ValueError):forecast(o)
    def test_archive_packet_reproduces(self):
        o=json.loads((ROOT/'public/data/projections/indicators/data_21/RU.json').read_text());fresh=forecast(o['observations'],o['end_date']);same(fresh['forecast'],o['forecast']);self.assertEqual(fresh['input_sha256'],o['input_sha256'])

class CohortTests(unittest.TestCase):
    def test_all_balances(self):
        d=simulate(fixture());self.assertEqual(len(d['months']),72)
        for r in d['months']:self.assertLess(abs(r['balance_residual']),1e-6);self.assertAlmostEqual(sum(r['age']['male'])+sum(r['age']['female']),r['population'])
    def test_e0(self):
        for s in ['male','female']:
            for e in [45,65,80,95]:self.assertAlmostEqual(mortality_from_e0(e,s)['e0'],e,places=7)
    def test_js_parity(self):
        script="import fs from 'node:fs'; import {simulateCohort} from './src/core/cohort.js';const d=JSON.parse(fs.readFileSync('./tests/fixtures/cohort_input.json','utf8'));console.log(JSON.stringify(simulateCohort(d,{fertility_scale_end:1.2,e0_delta_end:2,migration_scale:0.6})));"
        value=json.loads(subprocess.check_output(['node','--input-type=module','-e',script],cwd=ROOT,text=True));fresh=simulate(fixture(),{'fertility_scale_end':1.2,'e0_delta_end':2,'migration_scale':.6});same(fresh['months'],value['months'])
    def test_historical_scenario_invariance(self):
        a,b=simulate(fixture()),simulate(fixture(),{'migration_scale':0});self.assertEqual(a['months'][:15],b['months'][:15]);self.assertEqual(b['months'][15]['net_migration'],0)
    def test_invalid_input(self):
        for transform in [lambda d:d['population']['female'].pop(),lambda d:d['population']['male'].__setitem__(3,None),lambda d:d['fertility']['annual_tfr'].__setitem__('2029',-1),lambda d:d.__setitem__('scenario_start','2024-01-01')]:
            d=fixture();transform(d)
            with self.assertRaises((ValueError,TypeError)):validate_input(d)
    def test_overflow_rejected(self):
        d=fixture();d['fertility']['annual_tfr']={'2025':1e308};d['fertility']['monthly_tfr']={}
        with self.assertRaisesRegex(ValueError,'Переполнение'):simulate(d)
    def test_no_silent_clip(self):
        d=fixture();d['migration']['male']['annual_net']={'2025':-1e9}
        with self.assertRaisesRegex(ValueError,'отток'):simulate(d)

class InputReaderTests(unittest.TestCase):
    def book(self,path,long=False,missing=False):
        headers=['Территория','Год',*range(100),'100+'];rows=[headers,['Россия',2025,*([100]*101)],['Россия',2026,*([999]*101)]]
        if missing:rows[1][4]=None
        status=[['Территория','Год','Статус'],['Россия',2025,'наблюдение'],['Россия',2026,'прогноз']] if long else [['Год','Россия'],[2025,'наблюдение'],[2026,'прогноз']]
        xlsx(path,{'by_age':rows,'status':status})
    def test_wide_status_keeps_only_observed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.xlsx';self.book(p);r=observed_stocks(p);self.assertEqual(list(r),[('россия',2025)]);self.assertEqual(sum(r['россия',2025]['population']),10100)
    def test_long_status_keeps_only_observed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.xlsx';self.book(p,True);self.assertEqual(list(observed_stocks(p)),[('россия',2025)])
    def test_missing_base_cell_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.xlsx';self.book(p,missing=True)
            with self.assertRaises(ValueError):observed_stocks(p)
    def test_wrong_schema_is_not_invented(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.xlsx';xlsx(p,{'by_age':[['x'],[1]]})
            with self.assertRaises(ValueError):observed_stocks(p)
    def test_annual_scope_sex_and_status(self):
        rows=[{'Территория':'Россия','Год':'2025','Пол':'Мужчины','e0':'70,2','Статус':'наблюдение'},{'Территория':'Россия','Год':'2026','Пол':'Мужчины','e0':'70.4','Статус':'прогноз'}]
        r=annual_components(rows,{'россия':'RU'},{'e0'});self.assertEqual(r['RU','male']['2025']['value'],70.2);self.assertEqual(r['RU','male']['2026']['status'],'прогноз')
    def test_ambiguous_component_rejected(self):
        rows=[{'Территория':'Россия','Год':'2025','Пол':'Мужчины','e0':x} for x in [70,71]]
        with self.assertRaises(ValueError):annual_components(rows,{'россия':'RU'},{'e0'})
    def test_failed_fetch_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as td,patch('demography.repository_inputs.get_bytes',side_effect=RuntimeError('offline')):
            r=fetch_repository(Path(td));self.assertEqual(r['state'],'unavailable');self.assertFalse((Path(td)/'POP_wide_female_noMIG.xlsx').exists())


class BatchIntegrationTests(unittest.TestCase):
    def scaffold(self,root):
        from build_indicator_forecasts import write
        write(root/'public/data/catalog.json',{'regions':[{'id':'77','name':'Москва'}]})
        write(root/'public/data/latest/manifest.json',{'sources':[]})
        for sid in ['data_21','data_22']:write(root/f'public/data/baseline/{sid}.json',{'columns':['r','territory','type','year','value','end'],'rows':[]})
        cache=root/'inputs/upstream';cache.mkdir(parents=True)
        for sex in ['male','female']:
            age=[['Территория','Год',*range(100),'100+']]
            for name in ['Россия','Москва']:
                age.extend([[name,2025,*([1000]*101)],[name,2026,*([9999]*101)]])
            xlsx(cache/f'POP_wide_{sex}_noMIG.xlsx',{'by_age':age,'status':[['Год','Россия','Москва'],[2025,'наблюдение','наблюдение'],[2026,'прогноз','прогноз']]})
        (cache/'LE_Russia_subjects_forecast_2100_long.csv').write_text('Территория,Пол,Год,e0,Статус\n'+''.join(f'{r},{s},2025,{v},прогноз\n' for r in ['Россия','Москва'] for s,v in [('Мужчины',70),('Женщины',79)]))
        (cache/'MIG_cyclic_tidy.csv').write_text('Территория,Пол,Год,Сальдо,Статус\n'+''.join(f'{r},{s},2025,120,прогноз\n' for r in ['Россия','Москва'] for s in ['Мужчины','Женщины']))
        (cache/'TFR_Russia_subjects_ML_GP_UCM_tidy.csv').write_text('Территория,Год,median,Статус\nРоссия,2025,1.4,прогноз\nМосква,2025,1.3,прогноз\n')
        return cache
    def test_book_to_inputs_to_monthly_projection(self):
        from refresh_demography import run
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);self.scaffold(r);m=run(r);self.assertEqual(m['ready'],2)
            out=json.loads((r/'public/data/projections/population/RU/with_migration.json').read_text());self.assertEqual(out['base_date'],'2025-01-01');self.assertEqual(len(out['months']),72);self.assertEqual(sum(out['baseline']['male']),101000)
            # The following year is a projection and must not be used as a newer observed base.
            self.assertNotEqual(sum(out['baseline']['male']),9999*101)
    def test_invalid_local_override_retains_last_valid_output(self):
        from refresh_demography import run
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);self.scaffold(r);run(r);path=r/'public/data/projections/population/RU/with_migration.json';old=path.read_bytes();(r/'inputs/cohort').mkdir();(r/'inputs/cohort/RU.json').write_text('{"schema":"wrong", "region_id":"RU"}')
            m=run(r);self.assertEqual(m['retained'],1);self.assertEqual(path.read_bytes(),old);self.assertEqual(len(m['local_input_errors']),1)

if __name__=='__main__':unittest.main()
