import { h, button, icon, copyLink, hideTip } from './core/dom.js';
import { bootstrap, json } from './core/data.js';
import { sections } from './content/sections.js';
import { institutionalLinks } from './components/institutions.js';
import { currentReportButton, currentReportCard } from './components/current-report.js';
import { projects, getProject, foundationPages, projectHref, completeProjectPages } from './platform/projects.js';
import { parseRoute, switchProject } from './platform/routes.js';
import { applyTheme } from './platform/theme.js';
import { projectData, publications, reviewedPage, completeProjectData, currentReports } from './platform/data.js';
import { runtime, projectRuntimes } from './platform/runtime.js';
import { installSeriesTransport } from './core/series-transport.js';
let main, sidebar, top, masthead, footer, rail, publicationIndex={projects:{}}, sequence=0, currentKey='', sidebarProject='', preserveScroll=null;
const parse=()=>parseRoute(location.hash);
function route(page,patch={},preserve=false){
 const old=parse();const params={...patch};delete params.nationalProject;
 const dest=projectHref(old.nationalProject,page,params);
 if(preserve)preserveScroll=scrollY;
 if(location.hash===dest)render();else location.hash=dest;
}
function set(patch){const state=parse();route(state.page,{...state,...patch},true);}
const mobileViewport=matchMedia('(max-width:760px)');
function syncNavigation(){
 if(!sidebar)return;
 const opened=mobileViewport.matches&&document.body.classList.contains('nav-open');
 sidebar.inert=mobileViewport.matches&&!opened;
 document.querySelector('.workspace').inert=opened;
 for(const selector of ['.institution-links','.site-brand','.project-rail'])masthead.querySelector(selector).inert=opened;
 document.querySelector('.mobile-menu')?.setAttribute('aria-expanded',String(opened));
}
function setNavigation(opened,restoreFocus=false){
 document.body.classList.toggle('nav-open',Boolean(opened)&&mobileViewport.matches);syncNavigation();
 if(opened&&mobileViewport.matches)sidebar.querySelector('.nav-link.active,a')?.focus();
 else if(restoreFocus)document.querySelector('.mobile-menu')?.focus();
}
mobileViewport.addEventListener('change',()=>{document.body.classList.remove('nav-open');syncNavigation();});
function navLink(project,id,title,number=''){
 return h('a',{href:projectHref(project,id),class:'nav-link',dataset:{route:id},onClick:()=>setNavigation(false)},h('span',{class:'nav-number'},number),h('span',{},title));
}
function updateSidebar(p){
 if(sidebarProject===p.id)return;
 let content;
 if(p.id==='family')content=[navLink(p.id,'overview','Обзор исследования',icon('grid',16)),h('div',{class:'nav-label'},'Разделы экспертизы'),...sections.map(s=>navLink(p.id,s.id,s.short,s.n)),h('div',{class:'nav-label'},'Прогнозирование'),navLink(p.id,'projections','СКР и СКР3+',icon('trend',16)),navLink(p.id,'population','Передвижка возрастов',icon('population',16)),h('div',{class:'nav-label'},'Инструменты'),navLink(p.id,'lab','Вычислительная лаборатория',icon('code',16)),navLink(p.id,'explorer','Исследователь данных',icon('table',16)),navLink(p.id,'library','Данные, документы и код',icon('download',16)),navLink(p.id,'updates','Обновление ЕМИСС',icon('reset',16)),navLink(p.id,'authors','Об авторах',icon('users',16))];
 else if(completeProjectPages[p.id]){
  const projectPages=completeProjectPages[p.id];
  content=[h('div',{class:'sidebar-project'},p.name)];
  let group='';
  for(const item of projectPages){
   if(item.group!==group&&item.group!=='overview')content.push(h('div',{class:'nav-label'},({research:'Разделы экспертизы',scenarios:'Цели и целевые группы',tools:'Инструменты'})[item.group]));
   group=item.group;
   const number=item.group==='research'?String(projectPages.filter(s=>s.group==='research').findIndex(s=>s.id===item.id)+1).padStart(2,'0'):icon(item.icon,16);
   content.push(navLink(p.id,item.id,item.title,number));
  }
 }
 else {
  content=[h('div',{class:'sidebar-project'},p.name),...foundationPages.map(s=>navLink(p.id,s.id,s.title,icon(s.icon,16)))];
  const reviewed=publicationIndex.projects[p.id]||[];
  if(reviewed.length)content.push(h('div',{class:'nav-label'},'Разделы экспертизы'),...reviewed.map((s,i)=>navLink(p.id,s.id,s.title,String(i+1).padStart(2,'0'))));
  content.push(h('p',{class:'sidebar-note'},'Разделы исследования добавляются последовательно. Источники и ограничения доступны на каждой странице.'));
 }
 sidebar.replaceChildren(h('nav',{'aria-label':'Разделы проекта «'+p.name+'»'},content));
 sidebarProject=p.id;
}
function shell(){
 rail=h('nav',{class:'project-nav','aria-label':'Национальные проекты России'},projects.map(p=>h('a',{href:projectHref(p.id),class:'project-tab',title:p.name,dataset:{project:p.id},style:`--tab-color:${p.color}`,onClick:event=>{event.preventDefault();setNavigation(false);location.hash=switchProject(parse(),p.id);}},h('span',{class:'project-dot','aria-hidden':'true'}),p.short)));
 const previous=button('‹',()=>rail.scrollBy({left:-260,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}),'project-scroll');previous.setAttribute('aria-label','Предыдущие нацпроекты');
 const next=button('›',()=>rail.scrollBy({left:260,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'}),'project-scroll');next.setAttribute('aria-label','Следующие нацпроекты');
 masthead=h('header',{class:'site-header'},h('div',{class:'site-header-inner'},h('button',{class:'mobile-menu icon-button','aria-label':'Открыть меню','aria-controls':'sidebar','aria-expanded':'false',onClick:()=>setNavigation(!document.body.classList.contains('nav-open'))},icon('menu',21)),h('a',{href:'#/overview',class:'site-brand','aria-label':'Исследовательская платформа: Национальные проекты России'},h('span',{},'Исследовательская платформа'),h('strong',{},'Национальные проекты России')),institutionalLinks()),h('div',{class:'project-rail'},previous,rail,next));
 sidebar=h('aside',{class:'sidebar',id:'sidebar'});top=h('div',{class:'topbar'});main=h('main',{id:'main',tabindex:'-1'});footer=h('footer',{class:'site-footer'});
 document.getElementById('app').replaceChildren(masthead,sidebar,h('div',{class:'workspace'},top,main,footer),h('button',{class:'nav-scrim','aria-label':'Закрыть меню',onClick:()=>setNavigation(false,true)}));
 document.querySelector('.skip').onclick=e=>{e.preventDefault();main.focus();};
}
async function render(){
 if(!main)return;
 const token=++sequence,state=parse(),p=getProject(state.nationalProject),key=p.id+'/'+state.page,same=currentKey===key;
 if(p.id!=='family'&&!completeProjectPages[p.id]){publicationIndex=await publications();if(token!==sequence)return;}
 const reviewed=publicationIndex.projects[p.id]||[];
 if(p.id!=='family'&&!completeProjectPages[p.id]&&!foundationPages.some(x=>x.id===state.page)&&!reviewed.some(x=>x.id===state.page)){location.replace(projectHref(p.id));return;}
 hideTip();applyTheme(p.id);updateSidebar(p);
 for(const a of rail.querySelectorAll('[data-project]')){
  const active=a.dataset.project===p.id;a.classList.toggle('active',active);a.setAttribute('href',switchProject(state,a.dataset.project));
  if(active)a.setAttribute('aria-current','true');else a.removeAttribute('aria-current');
 }
 const activeTab=rail.querySelector('.active');
 if(activeTab){const left=activeTab.offsetLeft-rail.offsetLeft,right=left+activeTab.offsetWidth;if(left<rail.scrollLeft||right>rail.scrollLeft+rail.clientWidth)rail.scrollLeft=left-24;}
 for(const a of sidebar.querySelectorAll('[data-route]')){const active=a.dataset.route===state.page;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');}
 const name=p.id==='family'?(sections.find(s=>s.id===state.page)?.short||({overview:'Обзор',lab:'Лаборатория',explorer:'Данные',library:'Библиотека',updates:'Обновление',projections:'Прогнозы показателей',population:'Передвижка возрастов',authors:'Об авторах'})[state.page]):completeProjectPages[p.id]?.find(s=>s.id===state.page)?.title||foundationPages.find(s=>s.id===state.page)?.title||reviewed.find(s=>s.id===state.page)?.title;
 top.replaceChildren(h('div',{class:'breadcrumb'},h('a',{href:projectHref(p.id)},p.short),icon('chevron',13),h('span',{},name)),h('div',{class:'topbar-controls'},button('Ссылка',copyLink,'button subtle','link'),button('Источники',()=>route('library'),'button subtle','download')));
 footer.replaceChildren(...[h('span',{},'Экспертиза национального проекта «'+p.name+'»'),p.hasAuthors?h('a',{href:'#/authors'},'Авторский коллектив'):null,h('a',{href:projectHref(p.id,'library')},'Источники и воспроизведение'),h('a',{href:p.id==='family'?'./research/index.html':`./research/projects/${p.id}/index.html`},p.id==='family'?'Тексты исследований':'О проекте')].filter(Boolean));
 main.setAttribute('aria-busy','true');main.dataset.ready='false';main.classList.add('loading');
 if(!same)main.replaceChildren(h('div',{class:'page-loading',role:'status'},'Загрузка: '+p.name+' · '+name+'…'));
 try{
  await installSeriesTransport();
  const reportIndex=await currentReports();
  if(token!==sequence)return;
  const report=reportIndex.reports?.find(item=>item.project_id===p.id);
  if(!report?.pdf?.url||!report?.docx?.url)throw Error('Не найдены актуальные файлы экспертизы проекта «'+p.name+'».');
  top.querySelector('.topbar-controls').prepend(currentReportButton(report));
  let content;
  if(p.id==='family'){
   const [data,pageRenderer]=await Promise.all([bootstrap(),runtime.family(state.page)]);
   if(token!==sequence)return;
   content=await pageRenderer({...data,state,go:route,set});
  }
  else if(projectRuntimes[p.id]){
   const regional=['map','regions'].includes(state.page);
   const [study,bundle,research,geo,catalog]=await Promise.all([
    runtime.study(p.id),projectData(p.id),completeProjectData(p.id),
    regional?json('data/map.json'):null,
    json('data/regions.json')
   ]);
   if(token!==sequence)return;
   applyTheme(p.id);content=await study.render({...bundle,project:p,[study.key]:research,geo,catalog,state,go:route,set});
  }
  else if(foundationPages.some(x=>x.id===state.page)){
   const [bundle,{projectPage}]=await Promise.all([projectData(p.id),runtime.foundation()]);
   if(token!==sequence)return;applyTheme(p.id);content=projectPage({...bundle,project:p,state,go:route,set});
  }
  else {
   const [reviewed,{renderReviewedPage}]=await Promise.all([reviewedPage(p.id,state.page),runtime.foundation()]);
   if(token!==sequence)return;content=renderReviewedPage(p,reviewed);
  }
  if(token!==sequence)return;
  if(p.id==='family'&&['logic','finance','network','texts','domains','causal','proposals'].includes(state.page))content.insertBefore(h('div',{class:'note'},'Документальная часть экспертизы от 14.05.2026. Статистические ряды, документы и авторские выводы имеют собственные даты источников.'),content.children[1]||null);
  if(p.id==='family'&&state.page==='overview')content.querySelector('.page-heading')?.append(h('img',{src:p.logo,alt:'Логотип национального проекта «Семья»',class:'family-project-logo',width:112,height:98}));
  if(['overview','library'].includes(state.page)){const card=currentReportCard(report),heading=content.querySelector('.page-heading,.project-hero');if(heading)heading.after(card);else content.prepend(card);}
  main.replaceChildren(content);document.title=name+' · Экспертиза национального проекта «'+p.name+'»';main.dataset.page=state.page;main.dataset.project=p.id;main.dataset.ready='true';
  if(!same){window.scrollTo(0,0);main.focus({preventScroll:true});}else if(preserveScroll!==null)window.scrollTo(0,preserveScroll);
  preserveScroll=null;currentKey=key;document.getElementById('announcer').textContent='Открыто: '+p.name+', '+name;syncNavigation();
 }catch(error){
  if(token!==sequence)return;console.error(error);main.replaceChildren(h('div',{class:'error-view'},h('h1',{},'Не удалось открыть данные'),h('p',{},error.message),h('p',{},'Откройте сайт через HTTP. Каталоги data и downloads должны быть опубликованы вместе с приложением.'),button('Повторить',render,'button primary')));
 }finally{if(token===sequence){main.removeAttribute('aria-busy');main.classList.remove('loading');}}
}
window.addEventListener('hashchange',()=>{setNavigation(false);render();});
window.addEventListener('keydown',event=>{
 if(event.key==='Escape'){hideTip();if(document.body.classList.contains('nav-open'))setNavigation(false,true);}
 if(event.key==='Tab'&&mobileViewport.matches&&document.body.classList.contains('nav-open')){
  const items=[document.querySelector('.mobile-menu'),...sidebar.querySelectorAll('a[href],button:not([disabled])')],first=items[0],last=items[items.length-1];
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
 }
 if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){event.preventDefault();route('explorer');}
});
(async()=>{try{shell();await render();}catch(error){document.getElementById('app').replaceChildren(h('div',{class:'error-view'},h('h1',{},'Файлы платформы не загружены'),h('p',{},error.message),h('p',{},'Откройте готовый каталог docs через HTTP-сервер или GitHub Pages.')));}})();
