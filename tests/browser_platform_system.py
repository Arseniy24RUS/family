#!/usr/bin/env python3
"""Shared-shell, on-demand loading and current-report checks over real HTTP.

This suite runs with the existing optional Playwright CI dependencies. It does
not add browser or runtime dependencies to the static platform.
"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def execute(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    reports = json.loads((ROOT/'public/data/current-reports.json').read_text(encoding='utf-8'))['reports']
    checks, errors, requests = [], [], []
    base = args.base.rstrip('/') + '/'
    async with async_playwright() as playwright:
        options = {'headless': True}
        if args.browser:
            options['executable_path'] = args.browser
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(urlparse(request.url).path))

        async def ready(project, route='overview'):
            await page.wait_for_function(
                '([project,route])=>{const m=document.querySelector("#main");return m?.dataset.ready==="true" && m.dataset.project===project && m.dataset.page===route}',
                arg=[project, route], timeout=60000)
            assert not await page.locator('.error-view').count()

        async def go(project, route='overview'):
            fragment = '#/' + route if project == 'family' else '#/projects/' + project + '/' + route
            await page.evaluate('(fragment)=>location.hash=fragment', fragment)
            await ready(project, route)

        await page.goto(base+'#/projects/tourism/overview', wait_until='domcontentloaded')
        await ready('tourism')
        assert not any(path.endswith(('/data/research.json', '/data/current/research.json', '/data/current/catalog.json', '/data/latest/manifest.json')) for path in requests)
        loaded_project_css = await page.locator('link[data-project-style]').evaluate_all('(links)=>links.map(link=>link.getAttribute("href"))')
        assert loaded_project_css == ['./src/tourism.css'], loaded_project_css
        loaded_page_modules = [path.rsplit('/', 1)[-1] for path in requests if '/src/pages/' in path]
        assert loaded_page_modules == ['tourism.js'], loaded_page_modules
        checks.append({'check': 'direct_tourism_loads_only_its_renderer_and_css_without_family_data'})

        for report in reports:
            project = report['project_id']
            await go(project)
            assert await page.locator('.site-brand strong').inner_text() == 'Национальные проекты России'
            assert not await page.locator('.site-header .project-brand-link,.site-header .project-brand-logo').count()
            logo = page.locator('#main img[src$="/'+project+'.svg"]')
            assert await logo.count() == 1
            await logo.evaluate('(image)=>image.decode()')
            assert await logo.evaluate('(image)=>image.complete&&image.naturalWidth>0')
            assert await page.locator('.institution-link').count() == 3
            assert await page.locator('.sidebar [data-route="authors"]').count() == (1 if project == 'family' else 0)
            assert (await page.locator('.current-report-button').get_attribute('href')).endswith(report['pdf']['url'])
            assert await page.locator('.current-report-card').count() == 1
            assert 'Все 12 экспертиз' in await page.locator('.current-report-card').inner_text()
            await go(project, 'library')
            assert await page.locator('.current-report-card').count() == 1
            assert await page.locator('.sidebar [aria-current="page"]').count() == 1
            checks.append({'check': 'project_header_reports_authors', 'project': project})

        for width, height in [(1440, 1000), (1024, 768), (768, 1024), (390, 844), (320, 740)]:
            await page.set_viewport_size({'width': width, 'height': height})
            for project in ['family', 'international_export', 'data_economy']:
                await go(project)
                boxes = await page.locator('.institution-links > a').evaluate_all('(nodes)=>nodes.map(node=>node.getBoundingClientRect().toJSON())')
                assert len(boxes) == 3
                assert all(box['left'] >= 0 and box['right'] <= width+1 for box in boxes), boxes
                assert all(boxes[index]['right'] <= boxes[index+1]['left']+1 for index in range(2)), boxes
                rail_box = await page.locator('.project-rail').bounding_box()
                assert all(box['bottom'] <= rail_box['y']+1 for box in boxes), (boxes, rail_box)
                brand = await page.locator('.site-brand').bounding_box()
                institutions = await page.locator('.institution-links').bounding_box()
                assert brand['x'] >= 0 and brand['x']+brand['width'] <= width+1, brand
                assert brand['y']+brand['height'] <= institutions['y']+1 or brand['x']+brand['width'] <= institutions['x']+1, (brand, institutions)
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
                checks.append({'check': 'three_institution_logos_fit_without_page_overflow', 'width': width, 'project': project})
            await page.screenshot(path=str(output/f'platform-{width}.png'))
            if width <= 760:
                rail = page.locator('.project-nav')
                assert await rail.evaluate('(node)=>node.scrollWidth>node.clientWidth')
                await page.get_by_role('button', name='Открыть меню', exact=True).click()
                assert await page.locator('.institution-links').evaluate('(node)=>node.inert')
                await page.locator('.sidebar [data-route="library"]').click()
                await ready('data_economy', 'library')
                assert not await page.locator('body').evaluate('(node)=>node.classList.contains("nav-open")')
                checks.append({'check': 'mobile_scrollable_projects_and_menu_navigation', 'width': width})
                await page.go_back()
                await ready('data_economy')
                await page.get_by_role('button', name='Открыть меню', exact=True).click()
                await page.go_forward()
                await ready('data_economy', 'library')
                assert not await page.locator('body').evaluate('(node)=>node.classList.contains("nav-open")')
                checks.append({'check': 'mobile_history_closes_navigation', 'width': width})

        await page.set_viewport_size({'width': 1440, 'height': 1000})
        await go('international_export')
        runtime_requests = lambda: [value for value in requests if value.endswith(('.json', '.json.gz', '.js', '.css'))]
        before = list(runtime_requests())
        await go('international_export', 'library')
        assert runtime_requests() == before
        await page.evaluate('()=>{location.hash="#/projects/tourism/overview";location.hash="#/projects/data_economy/overview";location.hash="#/projects/international_export/overview";}')
        await ready('international_export')
        assert await page.locator('.site-brand strong').inner_text() == 'Национальные проекты России'
        assert not await page.locator('.site-header .project-brand-logo').count()
        assert await page.locator('#main img[src$="/international_export.svg"]').count() == 1
        checks.append({'check': 'cached_navigation_and_rapid_project_switch'})
        assert not errors, errors
        await context.close()
        await browser.close()
    result = {'checks': checks, 'page_errors': errors, 'request_count': len(requests)}
    (output/'platform-system.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'suite': 'platform_system', 'checks': len(checks), 'page_errors': len(errors)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--browser')
    parser.add_argument('--output', required=True)
    asyncio.run(execute(parser.parse_args()))


if __name__ == '__main__':
    main()
