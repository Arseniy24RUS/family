import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {C,ramp,fieldColors} from '../src/components/charts.js';
import {applyTheme,forecastFill} from '../src/platform/theme.js';
import {institutions} from '../src/pages/authors.js';

test('Family source accents retained exactly',()=>{applyTheme('family',null);assert.deepEqual(C,['#2947A0','#539D96','#6280D9','#031E4F','#67AEA7','#7F92BB','#315C83','#A7DBD6']);});
test('map scale light-to-dark with clamped limits',()=>{
 applyTheme('family',null);
 assert.equal(ramp(-5).toLowerCase(),'#eef3f9');assert.equal(ramp(2).toLowerCase(),'#031e4f');assert.equal(ramp(.5).toLowerCase(),'#539d96');
 for(let i=0;i<=100;i++)assert.match(ramp(i/100),/^#[0-9a-f]{6}$/i);
});
test('switching project updates shared chart colors and restores Family',()=>{
 applyTheme('family',null);const original=[...C],paletteReference=C,fieldsReference=fieldColors;
 try{
  applyTheme('long_active_life',null);assert.equal(C,paletteReference);assert.equal(fieldColors,fieldsReference);assert.equal(C[0],'#D9124A');assert.equal(fieldColors.HH,C[0]);assert.equal(fieldColors.LL,C[7]);assert.notEqual(forecastFill(),'#DCE7F6');
  applyTheme('data_economy',null);assert.equal(C[0],'#4224FD');assert.equal(fieldColors.HL,C[2]);assert.equal(fieldColors.LH,C[1]);
 }finally{applyTheme('family',null);}
 assert.deepEqual(C,original);assert.equal(forecastFill(),'#DCE7F6');
});
test('institution order and links not changed by restyling',()=>{
 assert.deepEqual(institutions.map(i=>i.id),['ran','fnisc','isd']);
 assert.deepEqual(institutions.map(i=>i.url),['https://new.ras.ru/','https://www.fnisc.ru/','https://isd-ras.ru/']);
});
test('header image sources bundled locally, not third-party embeds',()=>{
 for(const i of institutions){assert.ok(!i.image.startsWith('http'));assert.ok(fs.existsSync(new URL('../public/'+i.image.replace('./',''),import.meta.url)));}
});
