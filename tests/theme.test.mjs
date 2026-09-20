import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {C,ramp} from '../src/components/charts.js';
import {institutions} from '../src/pages/authors.js';

test('GeoTalent source accents retained exactly',()=>assert.deepEqual(C.slice(0,5),['#2947A0','#539D96','#6280D9','#031E4F','#67AEA7']));
test('map scale light-to-dark with clamped limits',()=>{
 assert.equal(ramp(-5),'#eef3f9');assert.equal(ramp(2),'#031e4f');assert.equal(ramp(.5),'#539d96');
 for(let i=0;i<=100;i++)assert.match(ramp(i/100),/^#[0-9a-f]{6}$/);
});
test('institution order and links not changed by restyling',()=>{
 assert.deepEqual(institutions.map(i=>i.id),['ran','fnisc','isd']);
 assert.deepEqual(institutions.map(i=>i.url),['https://new.ras.ru/','https://www.fnisc.ru/','https://isd-ras.ru/']);
});
test('header image sources bundled locally, not third-party embeds',()=>{
 for(const i of institutions){assert.ok(!i.image.startsWith('http'));assert.ok(fs.existsSync(new URL('../public/'+i.image.replace('./',''),import.meta.url)));}
});
