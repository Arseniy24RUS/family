import test from 'node:test';
import assert from 'node:assert/strict';
import {contextParams,readResearchContext,sourcePeriodWindow,resolveContextPeriod,periodContextParams,updateContextFromLocalControl} from '../src/core/research-context.js';

test('a cumulative December estimate never becomes an annual fact or a monthly observation',()=>{
  const ytd = sourcePeriodWindow({period_end:'2025-12-31',frequency:'cumulative_ytd',source_frequency:'monthly'});
  const annual = sourcePeriodWindow({period_start:'2025-01-01',period_end:'2025-12-31',frequency:'annual'});
  const monthly = sourcePeriodWindow({period_start:'2025-12-01',period_end:'2025-12-31',frequency:'monthly'});
  assert.deepEqual(ytd,{start:'2025-01-01',end:'2025-12-31',kind:'cumulative_ytd',frequency:'monthly'});
  const state = periodContextParams(ytd);
  assert.equal(resolveContextPeriod(state,[{...annual,nativeKey:'annual'},{...monthly,nativeKey:'monthly'}]).status,'unavailable');
});

test('an unavailable period never silently selects a newer or nearest record',()=>{
  const periods = [{...sourcePeriodWindow({end:'2026-09-30',type:'месяц'}),nativeKey:'месяц|2026-09-30'}];
  const request = {...periods[0],end:'2026-08-31',start:'2026-08-01'};
  assert.equal(resolveContextPeriod(periodContextParams(request),periods).selected,null);
  assert.equal(resolveContextPeriod({period:'месяц|2030-01-31'},periods).status,'unavailable');
});

test('stock and rolling intervals retain their distinct semantics and reporting frequency',()=>{
  assert.deepEqual(sourcePeriodWindow({frequency:'monthly',period_end:'2026-07-31'},{period_semantics:'stock_at_period_end'}),{start:'2026-07-31',end:'2026-07-31',kind:'stock_at_period_end',frequency:'monthly'});
  assert.deepEqual(sourcePeriodWindow({frequency:'monthly',period_end:'2026-02-28'},{period_semantics:'rolling_12_months'}),{start:'2025-03-01',end:'2026-02-28',kind:'rolling_12_months',frequency:'monthly'});
  assert.deepEqual(sourcePeriodWindow({frequency:'monthly',period_end:'2026-03-31'},{period_semantics:'cumulative_ytd'}),{start:'2026-01-01',end:'2026-03-31',kind:'cumulative_ytd',frequency:'monthly'});
});

test('invalid context remains a visible invalid request, rather than a default period',()=>{
  const state = {ctx_region:'unknown',ctx_start:'2026-02-30',ctx_end:'2026-03-31',ctx_kind:'monthly',ctx_frequency:'monthly'};
  const request = readResearchContext(state);
  assert.equal(request.invalidRegion,true);assert.equal(request.invalidPeriod,true);
  assert.equal(resolveContextPeriod(state,[{start:'2026-03-01',end:'2026-03-31',kind:'monthly',frequency:'monthly',nativeKey:'March'}]).status,'invalid');
  assert.deepEqual(contextParams({...state,source:'data_21',scenario:'forecast'}),state);
});

test('local period and region choices update shared context; changing source preserves the request',()=>{
  const period = {...sourcePeriodWindow({end:'2026-07-31',type:'месяц'}),nativeKey:'месяц|2026-07-31'};
  const state = {ctx_region:'77',...periodContextParams({...period,start:'2026-06-01',end:'2026-06-30'})};
  const next = updateContextFromLocalControl(state,{period:period.nativeKey,r:'23'},[period]);
  assert.equal(next.ctx_region,'23');assert.equal(next.ctx_end,'2026-07-31');
  const source = updateContextFromLocalControl(next,{source:'new_source',period:null},[]);
  assert.equal(source.ctx_end,'2026-07-31');
});
