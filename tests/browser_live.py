"""HTTP integrity, published data, and complete interactive calculation checks."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote, urljoin, urlparse
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def execute(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    checks, errors, failed_assets, external_errors = [], [], [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=args.browser)
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        page = await context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('response', lambda r: failed_assets.append([r.status, r.url]) if r.status >= 400 and r.url.startswith(args.base) else None)
        page.on('console', lambda m: external_errors.append(m.text) if m.type == 'error' else None)
        await page.goto(args.base, wait_until='networkidle')
        await page.wait_for_function("document.querySelector('#main[data-ready=true]') || document.querySelector('.error-view')")
        assert not await page.locator('.error-view').count(), await page.locator('body').inner_text()
        assert urlparse(page.url).path == urlparse(args.base).path
        assert 'Экспертиза' in await page.title()

        async def go(route):
            await page.goto(args.base+'#/'+route)
            await page.wait_for_timeout(150)
            await page.wait_for_function('(r)=>document.querySelector("#main").dataset.page===r && !document.querySelector("#main").hasAttribute("aria-busy")', arg=route.split('?')[0])
            assert await page.locator('h1').count() == 1
            assert not await page.locator('.error-view').count(), route
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+2'), route

        async def packet(path):
            r = await context.request.get(urljoin(args.base, path))
            assert r.ok, (path, r.status)
            return await r.json()

        index = await packet('downloads/index.json')
        semaphore = asyncio.Semaphore(4)

        async def verify_file(f):
            async with semaphore:
                response = await context.request.get(urljoin(args.base, 'downloads/'+quote(f['path'])), timeout=60000)
                assert response.ok, (f['path'], response.status)
                body = await response.body()
                assert len(body) == f['bytes'], f['path']
                assert hashlib.sha256(body).hexdigest() == f['sha256'], f['path']
                checks.append({'check': 'http_download_hash', 'file': f['path']})

        await asyncio.gather(*(verify_file(f) for f in index['files']))
        print('HTTP downloads verified:', len(index['files']), flush=True)

        await go('explorer')
        old = await page.locator('tbody tr').first.inner_text()
        await page.get_by_role('button', name='Следующая страница', exact=True).click()
        assert old != await page.locator('tbody tr').first.inner_text()
        await page.get_by_label('Поиск по таблице').fill('НесуществующаяТерритория123')
        assert await page.get_by_text('Совпадений нет. Измените фильтр.', exact=True).is_visible()
        await page.get_by_label('Поиск по таблице').fill('Москва')
        assert await page.locator('tbody tr').count() > 0
        checks.append({'check': 'pagination_search_empty_and_recovery'})

        manifest = await packet('data/latest/manifest.json')
        for source in manifest.get('sources', []):
            if not source.get('published_file'):
                continue
            await go('explorer?mode=latest&source='+source['source_id'])
            assert 'Обновлённый' in await page.locator('#main').inner_text()
            source_packet = await packet(source['published_file'])
            assert len(source_packet['rows']) == source['rows']
            checks.append({'check': 'published_source_in_explorer', 'source': source['source_id']})

        await go('library?tab=code')
        await page.get_by_label('Поиск по таблице').fill('reproduce_projection.py')
        await page.get_by_role('button', name='Просмотр', exact=True).click()
        await page.locator('.code-view').wait_for()
        assert 'def main' in await page.locator('.code-view').inner_text()
        checks.append({'check': 'code_library_preview'})

        await go('texts?tab=corpus')
        await page.get_by_label('Искомое выражение').fill('семь')
        assert await page.locator('.concordance mark').count() > 0
        await page.get_by_role('button', name='Сохранить поиск в ссылке').click()
        await page.wait_for_timeout(150)
        await page.reload()
        await page.locator('#main[data-ready=true]').wait_for()
        assert await page.get_by_label('Искомое выражение').input_value() == 'семь'
        checks.append({'check': 'corpus_search_survives_shared_link_reload'})

        await go('causal')
        await page.get_by_label('Участники · после').fill('15')
        assert await page.locator('.did-result strong').inner_text() == '4'
        await page.get_by_label('Участники · после').fill('')
        assert await page.locator('.did-result strong').count() == 0
        checks.append({'check': 'did_recalculation_and_missing_input'})

        pop = await packet('data/projections/population/manifest.json')
        ready = [r for r in pop['regions'] if r['state'] in ('ready', 'retained')]
        for region in ready:
            await go('population?r='+region['region_id'])
            assert await page.locator('.chart-svg').count() > 0, region['region_id']
            assert 'Расчёт остановлен' not in await page.locator('#main').inner_text(), region['region_id']
            clipped = await page.locator('.axis-y-label').evaluate_all('(xs)=>xs.filter(x=>x.getBBox().x<0).map(x=>x.textContent)')
            assert not clipped, (region['region_id'], clipped)
            checks.append({'check': 'observed_cohort_worker', 'region': region['region_id']})
        print('Observed cohort workers verified:', len(ready), flush=True)
        if ready:
            region = next((r for r in ready if r['region_id'] == '77'), ready[0])
            await go('population?r='+region['region_id']+'&scenario=custom')
            before = await page.locator('.stat strong').nth(1).inner_text()
            await page.get_by_label('СКР к концу 2030: множитель').fill('1.1')
            await page.get_by_role('button', name='Рассчитать сценарий', exact=True).click()
            await page.wait_for_function('(v)=>document.querySelectorAll(".stat strong")[1]?.textContent!==v && !document.querySelector("#main").hasAttribute("aria-busy")', arg=before)
            async with page.expect_download() as download:
                await page.get_by_role('button', name='Скачать воспроизводимый JSON').click()
            saved = out/'observed_cohort.json'
            await (await download.value).save_as(saved)
            subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/'scripts/reproduce_projection.py'), 'cohort', str(saved)], check=True, capture_output=True)
            checks.append({'check': 'observed_custom_scenario_export_python_parity'})
            await page.evaluate('window.scrollTo(0,0)')
            await page.screenshot(path=str(out/'observed_cohort_desktop.png'))
            await page.get_by_text('Загрузить свой расчётный файл', exact=True).click()
            await page.get_by_label('Загрузить входной JSON').set_input_files(saved)
            await page.wait_for_timeout(200)
            await page.wait_for_function('!document.querySelector("#main").hasAttribute("aria-busy") && location.hash.includes("r=uploaded")')
            invalid = out/'invalid-input.json'
            invalid.write_text('{"schema":"invalid"}', encoding='utf-8')
            await page.get_by_text('Загрузить свой расчётный файл', exact=True).click()
            await page.get_by_label('Загрузить входной JSON').set_input_files(invalid)
            await page.locator('[role="status"]').filter(has_text='Ожидается').wait_for()
            await page.get_by_role('tab', name='Возраст и пол', exact=True).click()
            await page.locator('.pyramid-wrap').wait_for()
            assert 'Локальный файл пользователя' in await page.locator('#main').inner_text()
            checks.append({'check': 'invalid_import_preserves_last_valid_input'})

        await go('updates')
        assert await page.locator('tbody tr').count() == 16
        await page.screenshot(path=str(out/'updates_desktop.png'), full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 844})
        await go('projections')
        await page.screenshot(path=str(out/'forecast_mobile.png'))
        assert not errors, errors
        assert not failed_assets, failed_assets
        checks.append({'check': 'no_runtime_errors_or_failed_local_assets'})
        await browser.close()
    (out/'live_checks.json').write_text(json.dumps({'url': args.base, 'mode': 'http', 'checks': checks, 'page_errors': errors, 'failed_local_assets': failed_assets, 'console_errors': external_errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS live:', len(checks), 'checks; console errors:', len(external_errors))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://localhost:8080/')
    parser.add_argument('--browser')
    parser.add_argument('--output', required=True)
    asyncio.run(execute(parser.parse_args()))
