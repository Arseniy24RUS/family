#!/usr/bin/env python3
"""Browser smoke and interaction tests. Requires Playwright + Chromium.
Normal use: python tests/browser_check.py --base http://localhost:8080/
In-memory reproducible harness: python tests/browser_check.py --virtual --browser /usr/bin/chromium
--virtual serves repository files through Playwright routes and does NOT test live hosting.
All application modules, calculations, real workers and exports remain unmodified.
"""
import argparse,asyncio,json,mimetypes,sys
from pathlib import Path
from urllib.parse import urlparse,unquote
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
ROUTES=['overview','framework','logic','audit','targets','map','map?source=data_21&r=77&compare=50','regions','regions?tab=spatial','regions?tab=network','regions?tab=outliers','finance','network','network?tab=matrix','network?tab=table','network?tab=metrics','texts','texts?tab=similarity','texts?tab=corpus','texts?tab=narrative','domains','causal','proposals','explorer','library','library?tab=code','library?tab=documents','library?tab=methods','updates','lab','lab?tab=cluster','lab?tab=moran']

async def execute(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[]
    async with async_playwright() as p:
        launch={'headless':True}
        if args.browser:launch['executable_path']=args.browser
        browser=await p.chromium.launch(**launch)
        context=await browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,reduced_motion='reduce')
        async def serve(route):
            name=unquote(urlparse(route.request.url).path.lstrip('/'))
            path=(ROOT/'docs'/name).resolve()
            if (ROOT/'docs').resolve() not in path.parents or not path.is_file():
                await route.fulfill(status=404,body='Missing');return
            await route.fulfill(body=path.read_bytes(),content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream',headers={'Access-Control-Allow-Origin':'*'})
        if args.virtual:await context.route('https://semya.test/**',serve)
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        if args.virtual:
            html=(ROOT/'docs/index.html').read_text().replace('<head>','<head><base href="https://semya.test/">')
            await page.set_content(html,wait_until='networkidle')
        else:await page.goto(args.base,wait_until='networkidle')
        await page.wait_for_selector('#main[data-ready=true]')
        async def go(route):
            await page.evaluate('(route)=>location.hash="#/"+route',route)
            await page.wait_for_timeout(110)
            await page.wait_for_function('(p)=>document.querySelector("#main").dataset.page===p && !document.querySelector("#main").hasAttribute("aria-busy")',arg=route.split('?')[0])
        for route in ROUTES:
            await go(route)
            assert not await page.locator('.error-view').count(),route
            assert await page.locator('h1').count()==1,route
            overflow=await page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
            assert not overflow,route+' horizontal overflow'
            assert 'nullnull' not in await page.locator('#main').inner_text(),route
            checks.append({'check':'desktop_route','route':route,'pass':True})
        await go('map?source=data_21&r=77&compare=50')
        assert await page.locator('[data-region]').count()==89
        await page.locator('[data-region="77"]').focus()
        await page.wait_for_timeout(80)
        assert 'Москва' in await page.locator('#tooltip').inner_text()
        checks.append({'check':'map_keyboard_tooltip_89_polygons','pass':True})
        assert await page.locator('.parity-share').count()==1
        assert 'Вклад, %' in await page.locator('.parity-share').text_content()
        checks.append({'check':'same_period_birth_order_share','pass':True})
        await page.get_by_label('Регион',exact=True).select_option('50')
        await page.wait_for_timeout(150)
        assert 'r=50' in await page.evaluate('location.hash')
        await page.get_by_role('button',name='Плиточная карта',exact=True).click();await page.wait_for_timeout(150)
        assert await page.locator('[data-region]').count()==89
        checks.append({'check':'region_selector_and_tile_map','pass':True})
        await go('map?source=data_21&r=77')
        async with page.expect_download() as info: await page.locator('.figure-tools').first.get_by_role('button',name='SVG',exact=True).click()
        f=await info.value;await f.save_as(out/'map.svg')
        text=(out/'map.svg').read_text();assert 'Нет данных' in text and 'архив' in text
        async with page.expect_download() as info: await page.locator('.figure-tools').first.get_by_role('button',name='PNG',exact=True).click()
        await (await info.value).save_as(out/'map.png')
        assert (out/'map.png').read_bytes().startswith(b'\x89PNG')
        checks.append({'check':'map_svg_png_exports_with_source_and_legend','pass':True})
        await go('network')
        await page.locator('[data-node="A::A01"]').count() # specific visibility depends on selected focus
        await page.get_by_label('Выбранный узел').select_option('A::A01');await page.wait_for_timeout(150)
        assert 'мероприятие' in (await page.locator('.network-inspector').text_content()).lower()
        await page.get_by_label('Только связи выбранного узла').uncheck();await page.wait_for_timeout(150)
        assert await page.locator('.network-node').count()==54
        checks.append({'check':'network_node_focus_and_full_54_nodes','pass':True})
        await go('explorer?source=data_21')
        await page.get_by_label('Поиск по таблице').fill('Москва')
        assert await page.locator('tbody tr').count()>0
        async with page.expect_download() as info:await page.locator('.data-table').get_by_role('button',name='CSV',exact=True).click()
        await (await info.value).save_as(out/'filtered.csv');assert 'Москва' in (out/'filtered.csv').read_text(encoding='utf-8-sig')
        checks.append({'check':'table_search_filtered_csv','pass':True})
        await go('lab')
        async with page.expect_download() as info:await page.get_by_role('button',name='Скачать расчёт и параметры').click()
        await (await info.value).save_as(out/'correlation_result.json')
        await go('lab?tab=cluster')
        await page.get_by_role('button',name='Рассчитать кластеры',exact=True).click()
        await page.get_by_role('button',name='Результат + входы + параметры',exact=True).wait_for(timeout=20000)
        async with page.expect_download() as info:await page.get_by_role('button',name='Результат + входы + параметры',exact=True).click()
        await (await info.value).save_as(out/'new_clusters.json')
        await go('lab?tab=moran')
        await page.get_by_role('button',name='Рассчитать Moran I',exact=True).click()
        await page.get_by_role('button',name='Скачать расчёт и входы',exact=True).wait_for(timeout=20000)
        async with page.expect_download() as info:await page.get_by_role('button',name='Скачать расчёт и входы',exact=True).click()
        await (await info.value).save_as(out/'moran_result.json')
        sys.path.insert(0,str(ROOT/'scripts'));from lab_reproduce import repeat
        for name in ['correlation_result.json','new_clusters.json','moran_result.json']:
            doc=json.loads((out/name).read_text());actual=repeat(doc);ref=doc['result']
            def equal(a,b):
                if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
                if isinstance(a,dict):return all(equal(v,b[k]) for k,v in a.items())
                if isinstance(a,(int,float)) and isinstance(b,(int,float)):return abs(a-b)<1e-9
                return a==b
            assert equal(actual,ref),name
            checks.append({'check':'browser_python_parity','file':name,'pass':True})
        for route in ['overview','map?source=data_21&r=77','network','regions?tab=network','targets','finance','texts','lab?tab=moran']:
            await go(route);await page.screenshot(path=str(out/('desktop_'+route.split('?')[0]+'.png')))
        await page.set_viewport_size({'width':390,'height':844})
        for route in ROUTES:
            await go(route)
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+2'),route+' mobile overflow'
            assert not await page.locator('.error-view').count(),route
            checks.append({'check':'mobile_route','route':route,'pass':True})
        for route in ['map?mode=latest', 'explorer?mode=latest', 'lab?mode=latest']:
            await go(route)
            assert not await page.locator('.error-view').count(), route
            assert await page.locator('.note.warning').count()>0, route
            checks.append({'check':'latest_layer_archive_fallback','route':route,'pass':True})
        await go('overview');await page.get_by_role('button',name='Открыть меню').click()
        assert await page.locator('body').evaluate('(e)=>e.classList.contains("nav-open")')
        await page.keyboard.press('Escape')
        assert not await page.locator('body').evaluate('(e)=>e.classList.contains("nav-open")')
        checks.append({'check':'mobile_menu_escape','pass':True})
        for route in ['overview','map?source=data_21&r=77','network','updates']:
            await go(route);await page.screenshot(path=str(out/('mobile_'+route.split('?')[0]+'.png')))
        assert not errors,errors
        await browser.close()
    report={'mode':'virtual_files_no_hosting_test' if args.virtual else 'http','checks':checks,'page_errors':errors}
    (out/'browser_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(f'PASS: {len(checks)} browser checks; {len(errors)} page errors; {out}')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://localhost:8080/');parser.add_argument('--virtual',action='store_true');parser.add_argument('--browser');parser.add_argument('--output',default=str(ROOT/'qa-artifacts'))
    asyncio.run(execute(parser.parse_args()))
