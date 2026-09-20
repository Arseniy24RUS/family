import { h, button, icon, select, copyLink, hideTip, announce } from './core/dom.js';
import { bootstrap } from './core/data.js';
import { sections } from './content/sections.js';
import { overview, framework, logic, audit, targets, finance, measures, domainPage, causal, proposalPage } from './pages/research.js';
import { atlas } from './pages/atlas.js';
import { regionsPage } from './pages/regions.js';
import { textsPage } from './pages/texts.js';
import { lab } from './pages/lab.js';
import { explorer, library, updates } from './pages/tools.js';
import { indicatorProjections } from './pages/projections.js';
import { populationProjection } from './pages/population.js';
import { authors, institutionalLinks } from './pages/authors.js';
const pages = { overview, framework, logic, audit, targets, map: atlas, regions: regionsPage, finance, network: measures, texts: textsPage, domains: domainPage, causal, proposals: proposalPage, lab, explorer, library, updates, projections: indicatorProjections, population: populationProjection, authors };
let data, main, sidebar, top, masthead, sequence = 0, currentPage = '', preserveScroll = null;
function parse() { const hash = location.hash.slice(1) || '/overview', [route, query = ''] = hash.split('?'), p = route.replace(/^\//, ''); return { ...Object.fromEntries(new URLSearchParams(query)), page: pages[p] ? p : 'overview' }; }
function route(page, patch = {}, preserve = false) { const old = parse(); const params = { mode: old.mode || 'baseline', ...patch }; delete params.page; const query = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([k, v]) => v !== null && v !== undefined && v !== ''))); const dest = '#/' + page + (query.size ? '?' + query.toString() : ''); if (preserve)
    preserveScroll = scrollY; if (location.hash === dest)
    render();
else
    location.hash = dest; }
function set(patch) { const state = parse(); route(state.page, { ...state, ...patch }, true); }
const mobileViewport = matchMedia('(max-width:760px)');
function syncNavigation() {
    if (!sidebar) return;
    const opened = mobileViewport.matches && document.body.classList.contains('nav-open');
    sidebar.inert = mobileViewport.matches && !opened;
    document.querySelector('.workspace').inert = opened;
    masthead.querySelector('.institution-links').inert = opened;
    masthead.querySelector('.site-brand').inert = opened;
    document.querySelector('.mobile-menu')?.setAttribute('aria-expanded', String(opened));
}
function setNavigation(opened, restoreFocus = false) {
    document.body.classList.toggle('nav-open', Boolean(opened) && mobileViewport.matches);
    syncNavigation();
    if (opened && mobileViewport.matches) sidebar.querySelector('.nav-link.active, a')?.focus();
    else if (restoreFocus) document.querySelector('.mobile-menu')?.focus();
}
mobileViewport.addEventListener('change', () => { document.body.classList.remove('nav-open'); syncNavigation(); });
function navLink(id, title, number = '') { return h('a', { href: '#/' + id, class: 'nav-link', dataset: { route: id }, onClick: () => { setNavigation(false); } }, h('span', { class: 'nav-number' }, number), h('span', {}, title)); }
function shell() {
    masthead = h('header', {class:'site-header'}, h('div', {class:'site-header-inner'},
        h('button', {class:'mobile-menu icon-button', 'aria-label':'Открыть меню', 'aria-controls':'sidebar', 'aria-expanded':'false', onClick:()=>setNavigation(!document.body.classList.contains('nav-open'))}, icon('menu', 21)),
        h('a', {href:'#/overview',class:'site-brand','aria-label':'Экспертиза национального проекта «Семья» — главная'},
            h('span',{},'Экспертиза национального проекта'),h('strong',{},'«Семья»')),
        institutionalLinks()));
    sidebar = h('aside', {class:'sidebar',id:'sidebar'},
        h('nav', {'aria-label':'Основная навигация'},
            navLink('overview','Обзор исследования',icon('grid',16)),
            h('div',{class:'nav-label'},'Разделы экспертизы'),
            sections.map(s=>navLink(s.id,s.short,s.n)),
            h('div',{class:'nav-label'},'Прогнозирование'),
            navLink('projections','СКР и СКР3+',icon('trend',16)),
            navLink('population','Передвижка возрастов',icon('population',16)),
            h('div',{class:'nav-label'},'Инструменты'),
            navLink('lab','Вычислительная лаборатория',icon('code',16)),
            navLink('explorer','Исследователь данных',icon('table',16)),
            navLink('library','Данные, документы и код',icon('download',16)),
            navLink('updates','Обновление ЕМИСС',icon('reset',16)),
            navLink('authors','Об авторах',icon('users',16))));
    top = h('div', {class:'topbar'});
    main = h('main', {id:'main',tabindex:'-1'});
    const scrim=h('button',{class:'nav-scrim','aria-label':'Закрыть меню',onClick:()=>setNavigation(false,true)});
    document.getElementById('app').replaceChildren(masthead,sidebar,
        h('div',{class:'workspace'},top,main,h('footer',{class:'site-footer'},
            h('span',{},'Экспертиза национального проекта «Семья»'),
            h('a',{href:'#/authors'},'Авторский коллектив'),
            h('a',{href:'#/library'},'Источники и воспроизведение'))),scrim);
    document.querySelector('.skip').onclick=e=>{e.preventDefault();main.focus();};
}
async function render() { if (!data)
    return; const token = ++sequence, state = parse(), same = currentPage === state.page; hideTip(); document.querySelectorAll('[data-route]').forEach(a => { const active = a.dataset.route === state.page; a.classList.toggle('active', active); if (active)
    a.setAttribute('aria-current', 'page');
else
    a.removeAttribute('aria-current'); }); let name = sections.find(s => s.id === state.page)?.short || ({ overview: 'Обзор', lab: 'Лаборатория', explorer: 'Данные', library: 'Библиотека', updates: 'Обновление', projections:'Прогнозы показателей', population:'Передвижка возрастов', authors:'Об авторах' })[state.page]; top.replaceChildren(
 h('div',{class:'breadcrumb'},h('a',{href:'#/overview'},'Исследование'),icon('chevron',13),h('span',{},name)),
 h('div',{class:'topbar-controls'},
  ['map','lab','explorer'].includes(state.page)?select('Версия статистики',[['baseline','Архив экспертизы'],['latest','Проверенный слой ЕМИСС']],state.mode||'baseline',v=>set({mode:v})):null,
  button('Ссылка',copyLink,'button subtle','link'),button('Источники',()=>route('library'),'button subtle','download')));
 main.setAttribute('aria-busy', 'true'); main.classList.add('loading'); try {
    const content = await pages[state.page]({ ...data, state, go: route, set });
    if (token !== sequence)
        return;
    main.replaceChildren(content);
    document.title = name + ' · Экспертиза национального проекта «Семья»';
    main.dataset.page = state.page;
    main.dataset.ready = 'true';
    if (!same) {
        window.scrollTo(0, 0);
        main.focus({ preventScroll: true });
    }
    else if (preserveScroll !== null) {
        window.scrollTo(0, preserveScroll);
    }
    preserveScroll = null;
    currentPage = state.page;
    document.getElementById('announcer').textContent = 'Открыто: ' + name;
    syncNavigation();
}
catch (e) {
    if (token !== sequence)
        return;
    console.error(e);
    main.replaceChildren(h('div', { class: 'error-view' }, h('h1', {}, 'Не удалось открыть данные'), h('p', {}, e.message), h('p', {}, 'Проверьте, что сайт открыт через HTTP, а файлы data и downloads опубликованы вместе с приложением.'), button('Повторить', render, 'button primary')));
}
finally {
    if (token === sequence) {
        main.removeAttribute('aria-busy');
        main.classList.remove('loading');
    }
} }
window.addEventListener('hashchange', render);
window.addEventListener('keydown', e => { if (e.key === 'Escape') {
    hideTip();
    if (document.body.classList.contains('nav-open')) setNavigation(false, true);
} if (e.key === 'Tab' && mobileViewport.matches && document.body.classList.contains('nav-open')) {
    const focusable = [document.querySelector('.mobile-menu'), ...sidebar.querySelectorAll('a[href], button:not([disabled])')];
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
} if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
    e.preventDefault();
    route('explorer');
} });
(async () => { try {
    data = await bootstrap();
    shell();
    await render();
}
catch (e) {
    document.getElementById('app').replaceChildren(h('div', { class: 'error-view' }, h('h1', {}, 'Файлы платформы не загружены'), h('p', {}, e.message), h('p', {}, 'Откройте готовый каталог docs через HTTP-сервер или GitHub Pages.')));
} })();
