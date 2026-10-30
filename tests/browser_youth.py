"""HTTP acceptance tests for the completed Youth project and shared navigation.

Uses ordinary Playwright: Browser plugin not available in the implementation session.
Screenshots and exported QA files are written outside the repository.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
PAGES=['overview','framework','logic','audit','targets','map','regions','finance','network','texts','domains','causal','proposals','lab','explorer','library','updates','projections','population','structure','methods']

async def run(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    results=[];errors=[];http_errors=[];downloads=[];requests=[]
    def check(name,condition,detail=None):
        results.append({'name':name,'passed':bool(condition),'detail':detail})
        if not condition:print('FAIL:',name,detail,flush=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,executable_path=args.browser or None,args=['--no-sandbox'])
        context=await browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,locale='ru-RU',timezone_id='Europe/Moscow')
        page=await context.new_page()
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' else None)
        page.on('response',lambda resp:http_errors.append({'url':resp.url,'status':resp.status}) if resp.status>=400 else None)
        page.on('request',lambda req:requests.append(req.url))
        async def ready():
            await page.wait_for_function("document.querySelector('#main')?.dataset.ready==='true'||!!document.querySelector('.error-view')",timeout=30000)
            if await page.locator('.error-view').count():raise AssertionError(await page.locator('.error-view').inner_text())
        async def route(name,query='',project='youth_children'):
            target='#/'+name if project=='family' else '#/projects/'+project+'/'+name
            await page.goto(args.base+target+query,wait_until='domcontentloaded')
            await ready()
            await page.wait_for_function('([p,s])=>document.querySelector("#main")?.dataset.project===p&&document.querySelector("#main")?.dataset.page===s',arg=[project,name])
        async def select(label,val):
            await page.get_by_label(label,exact=True).select_option(val)
            await ready()
            await page.wait_for_function('([label,value])=>document.querySelector(`select[aria-label="${label}"]`)?.value===value',arg=[label,val])
        for name in PAGES:
            try:
                await route(name)
                content=await page.locator('#main').inner_text()
                check('desktop_route_'+name,len(content)>350,{'characters':len(content),'title':await page.title()})
                check('desktop_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                check('no_authors_'+name,await page.locator('#sidebar a[href$="/authors"]').count()==0)
                if name in ['overview','map','finance','network','texts','projections']:
                    await page.screenshot(path=str(output/(name+'-desktop.png')),full_page=False)
            except Exception as exc:
                check('desktop_route_'+name,False,str(exc))
        # Ordinary route loading must not fetch the full text corpus.
        check('corpus_is_lazy',not any('/text/' in u or 'documentary_full.json' in u for u in requests))
        if not args.smoke_only:
            await route('explorer','?source=62969')
            await select('Территориальный уровень','regional')
            await select('Территория','77')
            check('explorer_region_filter','geography=regional' in page.url and 'r=77' in page.url)
            check('explorer_region_rows','Москва' in await page.locator('#main').inner_text())
            bookmark=page.url
            await page.reload();await ready()
            check('filters_survive_reload',await page.get_by_label('Территория',exact=True).input_value()=='77' and page.url==bookmark)
            await route('map','?source=62968')
            await select('Регион','77')
            await select('Сравнить с регионом','78')
            check('regional_comparison','compare=78' in page.url and 'Разность' in await page.locator('#main').inner_text())
            periods=await page.get_by_label('Период регионального среза',exact=True).locator('option').evaluate_all('(els)=>els.map(e=>e.value)')
            if len(periods)>1:
                await select('Период регионального среза',periods[-1])
                check('historical_regional_period',periods[-1] in page.url)
            await page.get_by_role('button',name='Плиточная карта',exact=True).click();await ready()
            check('tile_map','view=tile' in page.url)
            await route('finance')
            before=await page.locator('.figure svg').first.text_content()
            year_label=await page.locator('select').evaluate_all("els=>els.find(e=>Array.from(e.options).some(o=>o.value==='2030'))?.getAttribute('aria-label')")
            await select(year_label,'2030')
            after=await page.locator('.figure svg').first.text_content()
            check('finance_year_changes_chart',before!=after and 'finyear=2030' in page.url)
            await select('Единица суммы','million')
            check('finance_units','money=million' in page.url and 'млн' in await page.locator('.figure svg').first.text_content())
            for ext in ['SVG','PNG','CSV']:
                async with page.expect_download() as waiting:
                    await page.locator('.figure').first.get_by_role('button',name=ext,exact=True).click()
                download=await waiting.value;dest=output/download.suggested_filename;await download.save_as(dest)
                body=dest.read_bytes();downloads.append({'name':dest.name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
                check('export_'+ext,len(body)>100)
                if ext=='SVG':
                    text=body.decode('utf-8');check('svg_has_embedded_fonts',text.count('data:font/woff;base64,')==3)
                    check('svg_youth_identity','Молодёжь и дети' in text and '#8265CB'.lower() in text.lower())
                if ext=='CSV':check('csv_cyrillic', 'name' in body.decode('utf-8-sig') and 'Ю' in body.decode('utf-8-sig'))
            await route('projections','?source=62898')
            step=page.get_by_label('Ежегодное абсолютное изменение',exact=True)
            previous_step=await step.element_handle()
            await step.fill('2');await step.press('Tab')
            # A hash update can precede hashchange/render while ready still
            # belongs to the previous DOM. Wait for that DOM to be replaced.
            await page.wait_for_function('(element)=>!element.isConnected',arg=previous_step)
            await ready()
            await page.wait_for_function("new URLSearchParams(location.hash.split('?')[1]).get('step')==='2'")
            text=await page.locator('#main').inner_text()
            check('scenario_parameter_changes_result','15,6' in text and 'step=2' in page.url)
            await page.reload();await ready();check('scenario_parameter_bookmark',await step.input_value()=='2')
            await route('lab','?calc=distribution&source=62969')
            check('lab_quartile_matches_source','8,21' in await page.locator('#main').inner_text())
            await route('network')
            await select('Основание связи','shared')
            check('network_layer_filter','layer=shared' in page.url)
            await route('texts')
            await select('Представление','contexts')
            await page.wait_for_function("document.querySelector('#main')?.dataset.ready==='true'")
            check('text_context_lazy_request',any('/text/' in u for u in requests))
            check('text_context_rows',await page.locator('#main tbody tr').count()>0)
            check('no_full_corpus_request',not any('documentary_full.json' in u for u in requests))
            await route('audit')
            filter_locator=page.get_by_label('Статус данных',exact=True)
            if await filter_locator.count():
                await select('Статус данных','no_table_link')
                check('audit_missing_is_not_zero','Источник не установлен' in await page.locator('#main').inner_text())
            await route('map','?source=62969&r=77')
            await page.locator('.project-tab[data-project="family"]').click();await ready()
            check('project_switch_clears_foreign_filters',page.url.endswith('#/map'))
            await page.go_back();await ready();check('browser_back_restores_youth','youth_children/map' in page.url and 'r=77' in page.url)
        await page.set_viewport_size({'width':390,'height':844})
        for name in PAGES:
            try:
                await route(name)
                check('mobile_route_'+name,len(await page.locator('#main').inner_text())>350)
                check('mobile_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
                if name in ['overview','map','finance','network','texts']:
                    await page.screenshot(path=str(output/(name+'-mobile.png')),full_page=False)
            except Exception as exc:check('mobile_route_'+name,False,str(exc))
        await route('overview')
        await page.get_by_role('button',name='Открыть меню',exact=True).click()
        check('mobile_navigation_open',await page.locator('.workspace').evaluate('(e)=>e.inert'))
        check('mobile_menu_focused',await page.evaluate('document.querySelector("#sidebar").contains(document.activeElement)'))
        await page.keyboard.press('Escape')
        check('mobile_navigation_escape',await page.get_by_role('button',name='Открыть меню',exact=True).evaluate('(e)=>e===document.activeElement') and not await page.locator('.workspace').evaluate('(e)=>e.inert'))
        await page.get_by_role('button',name='Следующие нацпроекты',exact=True).click()
        await page.wait_for_function('document.querySelector(".project-nav").scrollLeft>0')
        check('mobile_project_scroll',True)
        await page.set_viewport_size({'width':320,'height':740})
        for name in ['overview','network','finance','projections']:
            await route(name);check('small_mobile_width_'+name,await page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'))
        await page.screenshot(path=str(output/'projections-320.png'))
        # All generated text pages load independently without JavaScript modules.
        for name in PAGES:
            filename='index.html' if name=='overview' else name+'.html'
            response=await context.request.get(args.base+'research/projects/youth_children/'+filename)
            text=await response.text()
            check('static_'+name,response.status==200 and '<h1>' in text and 'Молодёжь' in text)
        for project in ['long_active_life','tourism','personnel','life_infrastructure','efficient_transport','environment','international_export','data_economy','competitive_economy']:
            await route('overview',project=project);check('other_project_'+project,await page.locator('#main h1').count()==1)
        # Sources offered by the Youth library must exist under a project subpath.
        manifest=json.loads((ROOT/'docs/downloads/index.json').read_text(encoding='utf-8'))
        for item in manifest['files']:
            if not item['path'].startswith('projects/youth_children/'):continue
            response=await context.request.get(args.base+'downloads/'+item['path'])
            body=await response.body()
            check('download_'+item['path'],response.status==200 and hashlib.sha256(body).hexdigest()==item['sha256'])
        check('no_javascript_errors',not errors,errors)
        check('no_http_errors',not http_errors,http_errors)
        await browser.close()
    report={'base':args.base,'browser_path':'Playwright; Browser plugin not available','checks':results,'errors':errors,'http_errors':http_errors,'downloads':downloads,'passed':all(r['passed'] for r in results)}
    (output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(results),'failed':sum(not r['passed'] for r in results)},ensure_ascii=False),flush=True)
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True)
    parser.add_argument('--browser')
    parser.add_argument('--output',type=Path,default=Path('/tmp/youth-browser-qa'))
    parser.add_argument('--smoke-only',action='store_true')
    asyncio.run(run(parser.parse_args()))
