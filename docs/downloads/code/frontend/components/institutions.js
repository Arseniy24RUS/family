import {h} from '../core/dom.js';

export const institutions = [
  {id: 'ran', name: 'Российская академия наук', url: 'https://new.ras.ru/', image: './assets/institutions/ran.png'},
  {id: 'fnisc', name: 'ФНИСЦ РАН', url: 'https://www.fnisc.ru/', image: './assets/institutions/fnisc.png'},
  {id: 'isd', name: 'ИСД ФНИСЦ РАН', url: 'https://isd-ras.ru/', image: './assets/institutions/isd.png'}
];

export function institutionalLinks() {
  const links = h('nav', {class: 'institution-links', 'aria-label': 'Научные организации'},
    institutions.map(institution => h('a', {
      class: 'institution-link ' + institution.id, href: institution.url,
      target: '_blank', rel: 'noopener noreferrer', 'aria-label': institution.name
    }, h('img', {src: institution.image, alt: institution.name, decoding: 'async'}))));
  return links;
}
