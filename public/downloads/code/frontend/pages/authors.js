import { h, para } from '../core/dom.js';
import { heading, panel } from '../components/ui.js';
import { json } from '../core/data.js';
export const institutions=[
 {id:'ran',name:'Российская академия наук',url:'https://new.ras.ru/',image:'./assets/institutions/ran.png'},
 {id:'fnisc',name:'ФНИСЦ РАН',url:'https://www.fnisc.ru/',image:'./assets/institutions/fnisc.png'},
 {id:'isd',name:'ИСД ФНИСЦ РАН',url:'https://isd-ras.ru/',image:'./assets/institutions/isd.png'}
];
export function institutionalLinks(){
 return h('nav',{class:'institution-links','aria-label':'Научные организации'},institutions.map(i=>
  h('a',{class:'institution-link '+i.id,href:i.url,target:'_blank',rel:'noopener noreferrer','aria-label':i.name},
   h('img',{src:i.image,alt:i.name,decoding:'async'}))));
}
export async function authors(){
 const config=await json('data/authors.json');const root=h('div',{},heading('Об авторах','Научный коллектив комплексной экспертизы национального проекта «Семья»'));
 root.append(h('div',{class:'author-grid'},config.authors.map(a=>{
  const photo=h('div',{class:'author-photo'},h('span',{class:'initials','aria-hidden':'true'},a.initials));
  const url=a.local_photo?'./'+a.local_photo:a.photo_url;
  if(url)photo.append(h('img',{src:url,alt:a.name,loading:'lazy',referrerpolicy:'no-referrer',onError:e=>{e.target.remove();photo.setAttribute('aria-label','Фотография временно недоступна');}}));
  return h('article',{class:'author-card'},photo,h('div',{},h('h2',{},a.surname,h('span',{},a.given)),para(a.role,'role'),a.degree?para(a.degree):null,para('Институт социальной демографии ФНИСЦ РАН'),h('a',{href:a.profile_url,target:'_blank',rel:'noopener noreferrer'},'Профиль исследователя ↗')));
 })));
 root.append(panel('О работе коллектива',null,h('div',{},para('Экспертиза объединяет двенадцать взаимосвязанных исследований: от проверки документов и статистики до территориального, финансового, сетевого и текстового анализа. Руководитель исследования — Тамара Керимовна Ростовская.'),para('Должности и роли участников приведены по материалам экспертизы и уточнениям авторского коллектива. Новые прогнозные модули платформы описаны отдельно от архивных результатов исследования.','small'),h('a',{href:'./downloads/expertise_2026-05-14.docx',class:'text-link'},'Полный текст экспертизы'))));
 root.append(h('div',{class:'source-ledger'},'Фотографии: ',h('a',{href:'https://isd-ras.ru/administration/',target:'_blank',rel:'noopener'},'дирекция'), ' и ',h('a',{href:'https://isd-ras.ru/profiles/',target:'_blank',rel:'noopener'},'каталог научных сотрудников ИСД ФНИСЦ РАН'),'. При недоступности внешнего изображения показаны инициалы. Логотипы принадлежат соответствующим организациям.'));
 return root;
}
