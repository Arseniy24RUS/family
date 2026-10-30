"""HTTP acceptance for Longlife pages, lazy data, calculations and mobile use.

Browser plugin not available; the project uses the pinned Playwright fallback.
The flow under test is: a research page opens -> a source, period or method is
selected -> the URL, displayed evidence and exported data agree with that choice.
Numeric expectations come from the published files, so refreshes do not require
replacing hard-coded current observations in this browser suite.
"""
import argparse
import asyncio
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlencode, urljoin

from playwright.async_api import async_playwright
from browser_json import get_json as published_json

ROOT=Path(__file__).resolve().parents[1]
PROJECT='long_active_life'
PAGES=['overview','framework','logic','audit','targets','map','regions','finance',
       'network','texts','domains','causal','proposals','lab','explorer','library',
       'updates','projections','population','structure','methods']

def number(value):
    if value is None or value=='':return None
    try:return float(value)
    except (TypeError,ValueError):return None

def analytical(row):
    if 'analytical_value' in row:return number(row['analytical_value'])
    return None if row.get('excluded') else number(row.get('value'))

def category(row):
    c=row.get('category') or {}
    return ';'.join(k+':'+str(c[k]) for k in sorted(c)) if isinstance(c,dict) else str(c)

def slice_key(row):
    return '|'.join([row.get('frequency',''),row.get('period_end',''),category(row)])

def territory_values(rows):
    """One territory per map code, with confirmed scope before a parent aggregate."""
    groups={}
    for row in rows:
        code=str(row.get('map_id') or row.get('code') or '')
        if code:groups.setdefault(code,[]).append(row)
    selected={}
    for code,candidates in groups.items():
        eligible=[r for r in candidates if r.get('geographic_comparison_eligible') is not False]
        pool=eligible or candidates
        values={analytical(r) for r in pool if analytical(r) is not None}
        selected[code]={'value':next(iter(values)) if len(values)==1 else None,
                        'comparable':bool(eligible)}
    return selected

async def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    results=[];errors=[];http_errors=[];requests=[];downloads=[];expected_faults=[]
    def check(name,passed,detail=None):
        results.append({'name':name,'passed':bool(passed),'detail':detail})
        if not passed:print('FAIL:',name,detail,flush=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=args.browser or None,args=['--no-sandbox'])
        context=await browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,locale='ru-RU',timezone_id='Europe/Moscow')
        page=await context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)
        page.on('response',lambda response:http_errors.append({'url':response.url,'status':response.status}) if response.status>=400 else None)
        page.on('request',lambda request:requests.append(request.url))
        async def get_json(path):
            return await published_json(context, args.base, path)
        statistics=await get_json('data/projects/'+PROJECT+'/statistics.json')
        analytics=await get_json('data/projects/'+PROJECT+'/analytics.json')
        documentary=await get_json('data/projects/'+PROJECT+'/documentary.json')
        expertise=await get_json('data/projects/'+PROJECT+'/expertise.json')
        geometry=await get_json('data/map.json')
        geometry_ids={str(feature['id']) for feature in geometry['features']}
        sources=statistics['sources'];source_lookup={str(s['id']):s for s in sources}
        async def ready(project=PROJECT,name=None,state=None):
            await page.wait_for_function("document.querySelector('#main')?.dataset.ready==='true'||!!document.querySelector('.error-view')",timeout=30000)
            if await page.locator('.error-view').count():raise AssertionError(await page.locator('.error-view').inner_text())
            await page.wait_for_function('''([project,name,state])=>{
                const main=document.querySelector('#main');
                if(main?.dataset.project!==project||(name&&main.dataset.page!==name)||main.dataset.ready!=='true')return false;
                if(!state)return true;
                const actual=JSON.parse(document.querySelector('.longlife-page')?.dataset.routeState||'{}');
                return Object.entries(state).every(([key,value])=>String(actual[key]??'')===String(value));
            }''',arg=[project,name,state])
        async def route(name,params=None,project=PROJECT):
            fragment='#/'+name if project=='family' else '#/projects/'+project+'/'+name
            query='?'+urlencode(params) if params else ''
            await page.goto(args.base+fragment+query,wait_until='domcontentloaded')
            await ready(project,name,params if project==PROJECT else None)
        async def select(label,value,key):
            await page.get_by_label(label,exact=True).select_option(str(value))
            await ready(state={key:value})
        def panel(title):
            return page.locator('section.panel').filter(has=page.get_by_role('heading',name=title,exact=True))
        async def download(locator,ext):
            async with page.expect_download() as waiting:
                await locator.get_by_role('button',name=ext,exact=True).first.click()
            artifact=await waiting.value;dest=output/artifact.suggested_filename;await artifact.save_as(dest)
            content=dest.read_bytes();downloads.append({'name':dest.name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
            return content
        async def settled_mobile(width):
            await page.wait_for_function('''() => {
                const sidebar=document.querySelector('#sidebar');
                return !document.body.classList.contains('nav-open')&&sidebar?.inert
                    &&sidebar.getBoundingClientRect().right<=0
                    &&sidebar.getAnimations().every(a=>a.playState!=='running');
            }''')
            state=await page.locator('#sidebar').evaluate('e=>({right:e.getBoundingClientRect().right,inert:e.inert})')
            check('mobile_navigation_closed_'+str(width),state['right']<=0 and state['inert'],state)

        for name in PAGES:
            try:
                await route(name)
                text=await page.locator('#main').inner_text()
                check('desktop_route_'+name,len(text)>350,{'characters':len(text),'title':await page.title()})
                check('desktop_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                check('no_authors_'+name,await page.locator('#sidebar a[href$="/authors"]').count()==0)
                check('no_lazy_error_'+name,await page.locator('.longlife-load-error').count()==0)
                if name in ['overview','map','regions','finance','network','texts','projections','population']:
                    await page.screenshot(path=str(output/(name+'-desktop.png')))
            except Exception as error:check('desktop_route_'+name,False,str(error))
        check('full_corpus_not_preloaded',not any('/text/' in url or 'documentary_full.json' in url for url in requests))

        if not args.smoke_only:
            try:
                # Every regional source uses its own lazy file and a single exact slice.
                for source in [s for s in sources if s.get('regional_latest')]:
                    sid=str(source['id']);await route('map',{'source':sid})
                    packet=await get_json(source['downloads']['observations'])
                    chosen=await page.get_by_label('Срез наблюдений',exact=True).input_value()
                    rows=[r for r in packet['observations'] if r.get('geo_level')=='regional' and slice_key(r)==chosen]
                    territories=territory_values(rows)
                    expected=sum(number(r.get('value')) is not None for r in rows)
                    shown=await page.locator('.longlife-page>.stats .stat').first.locator('strong').inner_text()
                    check('map_source_'+sid,int(''.join(shown.split()))==expected,{'slice':chosen,'expected':expected,'shown':shown})
                    expected_comparable=sum(r['value'] is not None and r['comparable'] and code in geometry_ids for code,r in territories.items())
                    shown_comparable=await page.locator('.longlife-page>.stats .stat').nth(1).locator('strong').inner_text()
                    check('map_comparable_coverage_'+sid,int(''.join(shown_comparable.split()))==expected_comparable,
                          {'expected':expected_comparable,'shown':shown_comparable})
                    ambiguous=[code for code,r in territories.items() if not r['comparable'] and code in geometry_ids]
                    fills=await page.locator('.map-surface .region').evaluate_all('(nodes)=>Object.fromEntries(nodes.map(n=>[n.dataset.region,n.getAttribute("fill")]))')
                    check('map_ambiguous_not_filled_'+sid,all(fills.get(code)=='url(#missing)' for code in ambiguous),{'codes':ambiguous})
                    check('map_lazy_request_'+sid,any('/series/'+sid+'.json' in url for url in requests))
                    check('map_source_unit_'+sid,(source.get('display_unit') or source['unit']) in await page.locator('#main').inner_text())

                # The explicit Arkhangelsk-without-NAO row must survive its
                # missing ambiguous parent. Expectations remain source-backed.
                exclusive_source=source_lookup.get('62930')
                if exclusive_source:
                    packet=await get_json(exclusive_source['downloads']['observations'])
                    candidates=[r for r in packet['observations'] if r.get('geo_level')=='regional'
                                and str(r.get('map_id') or r.get('code'))=='29'
                                and r.get('geographic_comparison_eligible') is True and analytical(r) is not None]
                    if candidates:
                        exclusive=max(candidates,key=lambda r:r['period_end']);chosen=slice_key(exclusive)
                        await route('map',{'source':'62930','period':chosen,'r':'29'})
                        reading=await page.locator('.region-reading strong').first.inner_text()
                        parsed=float(''.join(reading.split()).replace(',','.'))
                        fill=await page.locator('.map-surface .region[data-region="29"]').get_attribute('fill')
                        check('map_explicit_exclusive_29',abs(parsed-analytical(exclusive))<=.00051 and fill!='url(#missing)',
                              {'period':exclusive['period'],'expected':analytical(exclusive),'shown':parsed,'fill':fill})
                        exported=await download(panel('Наблюдения выбранных регионов'),'CSV')
                        original_rows=[r for r in packet['observations'] if r.get('geo_level')=='regional' and slice_key(r)==chosen]
                        csv_rows=list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')),delimiter=';'))
                        check('map_retains_original_geographic_variants',len(csv_rows)==len(original_rows),
                              {'source_rows':len(original_rows),'exported_rows':len(csv_rows)})

                doctor=source_lookup.get('62971') or next(s for s in sources if s.get('regional_latest'))
                sid=str(doctor['id']);await route('map',{'source':sid})
                packet=await get_json(doctor['downloads']['observations'])
                chosen=await page.get_by_label('Срез наблюдений',exact=True).input_value()
                rows=[r for r in packet['observations'] if r.get('geo_level')=='regional' and slice_key(r)==chosen and analytical(r) is not None]
                district=next(r['fd'] for r in rows if r.get('fd'))
                await select('Федеральный округ',district,'fd')
                exported=await download(panel('Наблюдения выбранных регионов'),'CSV')
                csv_rows=list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')),delimiter=';'))
                expected_count=sum(r.get('geo_level')=='regional' and slice_key(r)==chosen and r.get('fd')==district for r in packet['observations'])
                check('map_fd_csv',len(csv_rows)==expected_count,{'expected':expected_count,'actual':len(csv_rows)})
                first=next(r for r in rows if r.get('fd')==district and r.get('geographic_comparison_eligible') is not False)
                await select('Регион',first['map_id'],'r')
                reading=await page.locator('.region-reading strong').first.inner_text()
                parsed=float(''.join(reading.split()).replace(',','.'))
                check('map_region_reading',abs(parsed-analytical(first))<=.00051)
                await page.get_by_role('button',name='Плиточная карта',exact=True).click();await ready(state={'view':'tile'})
                check('map_tile_and_region_retained',await page.locator('.map-surface g.region').count()>0 and 'r=' in page.url)
                await page.reload();await ready(name='map',state={'source':sid,'fd':district,'r':first['map_id'],'view':'tile'})
                check('map_url_filters_restore',await page.get_by_label('Федеральный округ',exact=True).input_value()==district)

                # The observations export includes selected geography, period and denominators.
                await route('explorer',{'source':sid,'geography':'regional','r':first['map_id']})
                full=[r for r in packet['observations'] if r.get('geo_level')=='regional' and r.get('map_id')==first['map_id']]
                year=max(str(r['period_end'])[:4] for r in full)
                await select('Год',year,'year')
                exported=await download(panel('Наблюдения и исходные значения'),'CSV')
                csv_rows=list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')),delimiter=';'))
                check('explorer_filter_export',len(csv_rows)==sum(str(r['period_end']).startswith(year) for r in full))
                check('explorer_denominator_export',(doctor.get('display_unit') or doctor['unit']) in exported.decode('utf-8-sig'))

                await route('lab',{'calc':'correlation','source':'62971','source2':'62970'})
                check('lab_pair_calculated',await panel('Парные наблюдения').locator('tbody tr').count()>0)
                check('lab_correlation_not_causal','не устанавливает причинность' in await page.locator('#main').inner_text())
                await route('lab',{'calc':'distribution','source':sid})
                check('lab_quantiles_available',await panel('Значения расчёта').locator('tbody tr').count()>0)

                await route('finance',{'money':'million','finyear':'2028'})
                fin=documentary['finance'];year_row=next(r for r in fin['reconciliation'] if str(r['year'])=='2028')
                expected=(float(year_row['nationalThousandRub'])-float(year_row['federalThousandRub']))/1000
                reading=await page.locator('.longlife-page>.stats .stat').nth(2).locator('strong').inner_text()
                check('finance_sign_and_unit',abs(float(''.join(reading.split()).replace(',','.'))-expected)<.00011 and 'млн руб.' in await page.locator('#main').inner_text())
                bar_labels=await panel('Финансирование федеральных проектов').locator('svg text').evaluate_all('''nodes=>nodes.filter(n=>/^Д[1-9АБ] ·/.test(n.textContent)).map(n=>({label:n.textContent,x:n.getBBox().x}))''')
                check('finance_bar_labels_fit',len(bar_labels)==len(fin['projects']) and all(r['x']>=0 for r in bar_labels),bar_labels)
                for ext in ['SVG','PNG','CSV']:
                    content=await download(panel('Финансирование федеральных проектов'),ext)
                    check('finance_export_'+ext,len(content)>100 and (ext!='SVG' or 'млн руб.' in content.decode('utf-8')))
                check('finance_missing_future_not_null', 'null–null' not in await page.locator('#main').inner_text())

                await route('network',{'layer':'reviewed'})
                exported=await download(panel('Все связи выбранного слоя'),'CSV')
                check('network_reviewed_count',len(list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')),delimiter=';')))==len(documentary['network']['directReviewed']['edges']))
                await select('Федеральный проект','ДА','fp')
                await select('Основание связи','shared','layer')
                await select('Федеральный проект','ДА','fp')
                check('network_letter_project_filter',await page.get_by_label('Карточка для просмотра',exact=True).locator('option').count()>0)

                await route('texts',{'textview':'similarity'})
                same_genre=set(documentary['text']['sameGenreDocumentIds'])
                expected=sum(r['document_a'] in same_genre and r['document_b'] in same_genre for r in documentary['text']['documentSimilarity'])
                check('text_same_genre_pairs',await page.get_by_role('heading',name=str(expected)+' пар документов',exact=True).count()==1)
                await route('texts',{'textview':'contexts'})
                check('text_context_lazy_loaded',any('/text/' in url for url in requests))
                check('text_contexts_nonempty',await panel('Ключевое слово в контексте').locator('tbody tr').count()>0)
                check('full_corpus_still_not_requested',not any('documentary_full.json' in url for url in requests))

                await route('population')
                ages=expertise['derived']['demographicContext']['ageSex']
                age=ages[len(ages)//2]
                await select('Возраст',str(age['age']),'age')
                await select('Демографическое представление','gap','lifeview')
                check('demography_age_changes',await panel('Предстоящая жизнь по возрасту и полу').locator('.stat').first.locator('strong').inner_text()==str(age['age']))
                exported=await download(panel('Предстоящая жизнь по возрасту и полу'),'CSV')
                check('demography_full_age_grid',len(list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')),delimiter=';')))==len(ages))

                await route('projections')
                options=await page.get_by_label('Годовой показатель',exact=True).locator('option').evaluate_all('(els)=>els.map(e=>e.value)')
                bounded=next((sid for sid in options if source_lookup[sid].get('upper_bound') is not None),options[0])
                await select('Годовой показатель',bounded,'source')
                selected_source=await page.get_by_label('Годовой показатель',exact=True).input_value()
                check('scenario_not_proxy',not source_lookup[selected_source].get('proxy_only'))
                await page.get_by_label('Ежегодное абсолютное изменение',exact=True).fill('1000')
                await page.get_by_label('Ежегодное абсолютное изменение',exact=True).blur();await ready(state={'step':'1000'})
                check('scenario_changed_in_url','step=1000' in page.url)
                check('scenario_bounds_explained','за область допустимых значений' in await page.locator('#main').inner_text())

                await route('audit',{'status':'no_table_link'})
                exported=await download(panel('Реестр показателей'),'CSV')
                check('audit_unmapped_filter',len(list(csv.DictReader(io.StringIO(exported.decode('utf-8-sig')),delimiter=';')))==analytics['coverage']['unmapped_indicators'])
                await route('library')
                local_links=await page.locator('#main a[download]').evaluate_all('(els)=>els.map(e=>e.href)')
                for url in local_links:
                    response=await context.request.get(url);check('library_'+url.rsplit('/',1)[-1],response.status==200)

                # A controlled 503 must remain local to the chosen data source and retry.
                retry_page=await context.new_page();retry_requests=[];fault_path=source_lookup['62926']['downloads']['observations'];fault_url=urljoin(args.base,fault_path)
                async def serve_fault(route):
                    retry_requests.append(route.request.url)
                    if len(retry_requests)==1:await route.fulfill(status=503,content_type='application/json',body='{"error":"QA simulated outage"}')
                    else:await route.continue_()
                await retry_page.route('**/'+fault_path+'*',serve_fault)
                retry_page.on('pageerror',lambda error:errors.append('retry: '+str(error)))
                await retry_page.goto(args.base+'#/projects/'+PROJECT+'/map?source=62926',wait_until='domcontentloaded')
                await retry_page.locator('.longlife-load-error').wait_for()
                check('lazy_503_has_retry','HTTP 503' in await retry_page.locator('.longlife-load-error').inner_text())
                await retry_page.get_by_role('button',name='Повторить загрузку',exact=True).click()
                await retry_page.locator('.longlife-load-error').wait_for(state='detached')
                check('lazy_retry_success',len(retry_requests)==2 and await retry_page.get_by_label('Показатель',exact=True).input_value()=='62926')
                expected_faults.append({'url':fault_url,'status':503,'retry_requests':len(retry_requests)})
                await retry_page.close()

                await route('map',{'source':sid,'r':first['map_id']})
                await page.locator('.project-tab[data-project="personnel"]').click();await ready('personnel','map')
                check('switch_project_preserves_route_clears_filters',page.url.endswith('#/projects/personnel/map'))
                await page.go_back();await ready(PROJECT,'map')
                check('back_restores_longlife_filters','source='+sid in page.url)
            except Exception as error:check('interactive_flow',False,str(error))

        await page.set_viewport_size({'width':390,'height':844});await settled_mobile(390)
        for name in PAGES:
            try:
                await route(name)
                check('mobile_route_'+name,len(await page.locator('#main').inner_text())>350)
                check('mobile_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                if name in ['overview','map','regions','finance','network','population']:
                    await page.screenshot(path=str(output/(name+'-mobile.png')))
            except Exception as error:check('mobile_route_'+name,False,str(error))
        await route('overview');await page.get_by_role('button',name='Открыть меню',exact=True).click()
        check('mobile_focus_trapped',await page.locator('.workspace').evaluate('(e)=>e.inert') and await page.evaluate('document.querySelector("#sidebar").contains(document.activeElement)'))
        await page.keyboard.press('Escape')
        check('mobile_escape_restores_focus',await page.get_by_role('button',name='Открыть меню',exact=True).evaluate('(e)=>e===document.activeElement'))
        await page.get_by_role('button',name='Следующие нацпроекты',exact=True).click()
        await page.wait_for_function('document.querySelector(".project-nav").scrollLeft>0')
        check('mobile_project_rail_scroll',True)
        await page.set_viewport_size({'width':320,'height':740});await settled_mobile(320)
        for name in ['overview','finance','network','population','projections']:
            await route(name);check('small_mobile_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
        await page.screenshot(path=str(output/'projections-320.png'))
        for name in PAGES:
            filename='index.html' if name=='overview' else name+'.html'
            response=await context.request.get(args.base+'research/projects/'+PROJECT+'/'+filename)
            body=await response.text();check('static_'+name,response.status==200 and '<h1>' in body and 'Продолжительная' in body)
        check('no_javascript_errors',not errors,errors);check('no_unexpected_http_errors',not http_errors,http_errors)
        await browser.close()
    report={'base':args.base,'browser_path':'Playwright; Browser plugin not available','checks':results,
            'errors':errors,'http_errors':http_errors,'expected_faults':expected_faults,'downloads':downloads,
            'passed':all(r['passed'] for r in results)}
    (output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(results),'output':str(output)},ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True)
    parser.add_argument('--browser')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--smoke-only',action='store_true')
    args=parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))
