/** Monthly cohort component engine, matching scripts/demography/cohort.py.
 * Annual ages are split uniformly into 12 birth-month cells. Missing data and
 * impossible outflows fail loudly; no fabricated cohorts or silent clipping.
 */
export const COHORT_VERSION='cohort-monthly/1.1.1';
const SEXES=['male','female'];
const sum=a=>a.reduce((s,v)=>s+v,0);
const finite=v=>typeof v==='number'&&Number.isFinite(v);
function normalized(a){if(!Array.isArray(a)||!a.every(v=>finite(v)&&v>=0)||!Number.isFinite(sum(a))||sum(a)<=0)throw Error('Некорректный возрастной профиль.');const s=sum(a);return a.map(v=>v/s);}
export function fertilityProfile(mean=28,sd=6){return normalized(Array.from({length:101},(_,a)=>a>=15&&a<=49?Math.exp(-.5*((a+.5-mean)/sd)**2):0));}
export function migrationProfile(){return normalized(Array.from({length:101},(_,a)=>Math.exp(-.5*((a-27)/9)**2)+.20*Math.exp(-.5*((a-7)/5)**2)+.08*Math.exp(-.5*((a-62)/8)**2)));}
export function lifeE0(hazards){let l=1,E=0;for(const m of hazards.slice(0,100)){E+=l*(m?-Math.expm1(-m)/m:1);l*=Math.exp(-m);}return hazards[100]>0?E+l/hazards[100]:Infinity;}
export function mortalityFromE0(e0,sex){if(!finite(e0)||e0<30||e0>100||!SEXES.includes(sex))throw Error('ОПЖ должна находиться в интервале 30–100 лет.');const c=sex==='male'?1.25:.85,template=Array.from({length:101},(_,a)=>a===0?(sex==='male'?.004:.0032):.00013+c*.000035*Math.exp(.092*a)+(sex==='male'?.0003:.00008)*Math.exp(-.5*((a-23)/7)**2));let lo=.005,hi=20;for(let i=0;i<80;i++){const mid=(lo+hi)/2;if(lifeE0(template.map(v=>v*mid))>e0)lo=mid;else hi=mid;}const hz=template.map(v=>v*(lo+hi)/2);return{qx:hz.map(v=>-Math.expm1(-v)),e0:lifeE0(hz)};}
export function annualValue(values,year){if(!values)throw Error('Не задан годовой компонент.');const years=Object.keys(values).map(Number).filter(v=>Number.isInteger(v)&&v<=year).sort((a,b)=>a-b);if(!years.length)throw Error('Нет значения компоненты на базовый год или ранее.');const val=values[years.at(-1)];if(!finite(val))throw Error('Нечисловой компонент.');return val;}
export function validateCohortInput(d){if(d?.schema!=='semya.cohort-input/1')throw Error('Ожидается файл semya.cohort-input/1.');if(!/^20\d{2}-(0[1-9]|1[0-2])-01$/.test(d.base_date)||d.base_date>='2031-01-01')throw Error('Базовая дата должна быть первым числом месяца до 2031 года.');const scen=d.scenario_start??d.base_date;if(!/^20\d{2}-(0[1-9]|1[0-2])-01$/.test(scen)||scen<d.base_date||scen>='2031-01-01')throw Error('Некорректная сценарная дата.');const year=Number(d.base_date.slice(0,4));for(const s of SEXES){const p=d.population?.[s];if(!p||p.length!==101||!p.every(v=>finite(v)&&v>=0)||!Number.isFinite(sum(p))||sum(p)<=0)throw Error(`${s}: нужны 101 непустая возрастная ячейка 0–99 и 100+.`);const spec=d.mortality?.[s];if(spec?.qx){if(spec.qx.length!==101||!spec.qx.every(v=>finite(v)&&v>=0&&v<=1))throw Error('qx: ожидается 101 вероятность от 0 до 1.');}else mortalityFromE0(annualValue(spec?.annual_e0,year),s);annualValue(d.migration?.[s]?.annual_net,year);if(normalized(d.migration?.[s]?.weights).length!==101)throw Error('Ожидается 101 миграционный вес.');}for(const sex of SEXES){for(const [y,v] of Object.entries(d.migration[sex].annual_net))if(!/^\d+$/.test(y)||!finite(v))throw Error('Некорректная годовая миграционная траектория.');for(const [y,v] of Object.entries(d.mortality[sex].annual_e0||{}))if(!/^\d+$/.test(y)||!finite(v)||v<30||v>100)throw Error('Некорректная годовая траектория ОПЖ.');}const f=d.fertility,w=normalized(f?.weights);for(const [y,v] of Object.entries(f.annual_tfr))if(!/^\d+$/.test(y)||!finite(v)||v<0)throw Error('Некорректная годовая траектория СКР.');if(w.length!==101||w.some((v,i)=>v>0&&(i<15||i>49)))throw Error('Рождаемость задаётся в возрастах 15–49.');if(annualValue(f.annual_tfr,year)<0)throw Error('СКР не может быть отрицательным.');for(const [k,v]of Object.entries(f.monthly_tfr||{}))if(!/^20\d{2}-(0[1-9]|1[0-2])$/.test(k)||!finite(v)||v<0)throw Error('Некорректная месячная траектория СКР.');const ratio=d.sex_ratio??105.6;if(!finite(ratio)||ratio<90||ratio>120)throw Error('Соотношение полов вне диапазона 90–120.');return true;}
export function aggregateAge(a){return Array.from({length:101},(_,i)=>i===100?a[1200]:sum(a.slice(i*12,i*12+12)));}
export function simulateCohort(d,options={}){
 validateCohortInput(d);const opt={migration_scale:1,fertility_scale_end:1,e0_delta_end:0,...options};
 for(const[k,[lo,hi]]of Object.entries({migration_scale:[0,3],fertility_scale_end:[.25,3],e0_delta_end:[-15,15]}))if(!finite(opt[k])||opt[k]<lo||opt[k]>hi)throw Error(`Параметр ${k} вне допустимого диапазона.`);
 const scen=d.scenario_start??d.base_date,scenarioN=Number(scen.slice(0,4))*12+Number(scen.slice(5,7))-1;
 const start=Number(d.base_date.slice(0,4))*12+Number(d.base_date.slice(5,7))-1,end=2030*12+11;
 let stocks=Object.fromEntries(SEXES.map(s=>[s,[...d.population[s].slice(0,100).flatMap(v=>Array(12).fill(v/12)),d.population[s][100]]])),maxResidual=0;
 const fw=normalized(d.fertility.weights),mw=Object.fromEntries(SEXES.map(s=>[s,normalized(d.migration[s].weights)])),share=(d.sex_ratio??105.6)/(100+(d.sex_ratio??105.6)),months=[],cache=new Map();
 for(let n=start;n<=end;n++){
  const year=Math.floor(n/12),month=n%12+1,key=`${year}-${String(month).padStart(2,'0')}`,progress=Math.max(0,(n-scenarioN)/Math.max(1,end-scenarioN));
  let tfr=d.fertility.monthly_tfr?.[key]??annualValue(d.fertility.annual_tfr,year);tfr*=1+(opt.fertility_scale_end-1)*progress;
  const before=Object.fromEntries(SEXES.map(s=>[s,sum(stocks[s])])),startF=aggregateAge(stocks.female),next={},survival={},e0Used={};
  for(const s of SEXES){const spec=d.mortality[s];let qx;
   if(spec.qx){if(opt.e0_delta_end!==0)throw Error('Сдвиг ОПЖ недоступен для заданных напрямую qx.');qx=spec.qx;e0Used[s]=null;}
   else{const e0=annualValue(spec.annual_e0,year)+opt.e0_delta_end*progress,ck=s+':'+e0.toFixed(9);if(!cache.has(ck))cache.set(ck,mortalityFromE0(e0,s));qx=cache.get(ck).qx;e0Used[s]=e0;}
   const pm=qx.map(v=>(1-v)**(1/12));survival[s]=pm;const survivors=stocks[s].map((v,i)=>v*pm[Math.min(Math.floor(i/12),100)]);
   next[s]=[0,...survivors.slice(0,1199),survivors[1199]+survivors[1200]];
  }
  const endF=aggregateAge(next.female),exposure=startF.map((v,i)=>(v+endF[i])/2),births=sum(exposure.map((v,a)=>v*fw[a]*tfr/12));
  const deaths=Object.fromEntries(SEXES.map(s=>[s,before[s]-sum(next[s])])),net={};
  for(const[s,sexShare]of[['male',share],['female',1-share]]){
   const born=births*sexShare,alive=born*Math.sqrt(survival[s][0]);next[s][0]+=alive;deaths[s]+=born-alive;
   net[s]=annualValue(d.migration[s].annual_net,year)/12*(n>=scenarioN?opt.migration_scale:1);
   for(let a=0;a<100;a++){const added=net[s]*mw[s][a]/12;for(let j=a*12;j<a*12+12;j++){next[s][j]+=added;if(next[s][j]<-1e-8)throw Error(`${key}, ${s}, возраст ${a}: отток превышает численность. Отрицательные ячейки не обрезаются.`);}}
   next[s][1200]+=net[s]*mw[s][100];if(next[s][1200]<-1e-8)throw Error('Отток превышает численность группы 100+.');
  }
  stocks=next;const age=Object.fromEntries(SEXES.map(s=>[s,aggregateAge(stocks[s])])),male=sum(age.male),female=sum(age.female),total=male+female,natural=births-sum(Object.values(deaths)),migration=sum(Object.values(net));
  const residual=total-sum(Object.values(before))-natural-migration;if(![total,births,natural,migration,residual,...Object.values(deaths)].every(Number.isFinite))throw Error('Переполнение вычислений: проверьте масштабы входных данных и коэффициентов.');maxResidual=Math.max(maxResidual,Math.abs(residual));if(Math.abs(residual)>Math.max(1e-6,total*1e-10))throw Error('Нарушен демографический баланс.');
  months.push({month:key,stock_date:`${Math.floor((n+1)/12)}-${String((n+1)%12+1).padStart(2,'0')}-01`,population:total,male,female,births,deaths:sum(Object.values(deaths)),natural_change:natural,net_migration:migration,tfr,e0_male:e0Used.male,e0_female:e0Used.female,children_0_14:sum(age.male.slice(0,15))+sum(age.female.slice(0,15)),age_65_plus:sum(age.male.slice(65))+sum(age.female.slice(65)),women_15_49:sum(age.female.slice(15,50)),balance_residual:residual,age});
 }
 return{schema:'semya.cohort-result/1',model_version:COHORT_VERSION,region_id:d.region_id,region_name:d.region_name,base_date:d.base_date,scenario_start:d.scenario_start??d.base_date,end_date:'2030-12-31',baseline:d.population,options:opt,months,max_balance_residual:maxResidual,provenance:d.provenance||[],assumptions:d.assumptions||[],interpretation:'Условная сценарная передвижка, не официальный и не причинный прогноз. Месяц — вычислительный шаг, а не частота наблюдения всех компонент.'};
}
