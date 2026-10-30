/** Validate the published Dataeconomy study and its source-linked arithmetic. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {dataeconomyPages,getProject} from '../src/platform/projects.js';
import {median,quantile} from '../src/core/stats.js';
import {validateDataeconomyContent} from './build_dataeconomy.mjs';

const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const close=(actual,expected,label)=>assert.ok(Number.isFinite(actual)&&Number.isFinite(expected)&&Math.abs(actual-expected)<=1e-8*Math.max(1,Math.abs(expected)),label);
const cents=value=>{
  assert.match(value,/^-?\d+(?:\.\d{1,2})?$/,'Financial source amounts retain exact hundredths.');
  const negative=value.startsWith('-'),[integer,fraction='']=value.replace('-','').split('.');
  return (BigInt(integer)*100n+BigInt(fraction.padEnd(2,'0')))*(negative?-1n:1n);
};

const average=values=>values.reduce((sum,value)=>sum+value,0)/values.length;
const dot=(a,b)=>a.reduce((sum,value,i)=>sum+value*b[i],0);
const distance=(a,b)=>Math.sqrt(a.reduce((sum,value,i)=>sum+(value-b[i])**2,0));
function adjustedRand(a,b){
  assert.equal(a.length,b.length);
  const counts=values=>values.reduce((out,value)=>(out.set(value,(out.get(value)||0)+1),out),new Map());
  const choose2=n=>n*(n-1)/2,sumPairs=map=>[...map.values()].reduce((sum,n)=>sum+choose2(n),0);
  const cells=sumPairs(counts(a.map((value,i)=>value+'|'+b[i]))),left=sumPairs(counts(a)),right=sumPairs(counts(b));
  const expected=left*right/choose2(a.length),maximum=(left+right)/2;
  return maximum===expected?1:(cells-expected)/(maximum-expected);
}
function silhouette(matrix,labels){
  const groups=[...new Set(labels)];
  assert.ok(groups.length>1&&groups.length<matrix.length);
  return average(matrix.map((row,i)=>{
    const own=matrix.filter((_,j)=>j!==i&&labels[j]===labels[i]);
    if(!own.length)return 0;
    const a=average(own.map(value=>distance(row,value)));
    const b=Math.min(...groups.filter(g=>g!==labels[i]).map(g=>average(matrix.filter((_,j)=>labels[j]===g).map(value=>distance(row,value)))));
    return (b-a)/Math.max(a,b);
  }));
}
function standardized(matrix){
  const columns=matrix[0].map((_,j)=>matrix.map(row=>row[j]));
  const means=columns.map(average),scales=columns.map((values,j)=>Math.sqrt(average(values.map(v=>(v-means[j])**2)))||1);
  return {means,scales,z:matrix.map(row=>row.map((value,j)=>(value-means[j])/scales[j]))};
}
function covariance(matrix){
  const p=matrix[0].length,n=matrix.length;
  return Array.from({length:p},(_,i)=>Array.from({length:p},(_,j)=>matrix.reduce((sum,row)=>sum+row[i]*row[j],0)/(n-1)));
}
// A separate symmetric Jacobi eigensolver checks the geometry without sklearn.
function eigenvectors(matrix){
  const a=matrix.map(row=>[...row]),n=a.length,v=Array.from({length:n},(_,i)=>Array.from({length:n},(_,j)=>Number(i===j)));
  for(let iteration=0;iteration<1000;iteration++){
    let p=0,q=1;
    for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)if(Math.abs(a[i][j])>Math.abs(a[p][q]))[p,q]=[i,j];
    if(Math.abs(a[p][q])<1e-13)break;
    const angle=.5*Math.atan2(2*a[p][q],a[q][q]-a[p][p]),c=Math.cos(angle),s=Math.sin(angle);
    const app=a[p][p],aqq=a[q][q],apq=a[p][q];
    for(let k=0;k<n;k++)if(k!==p&&k!==q){
      const akp=a[k][p],akq=a[k][q];
      a[k][p]=a[p][k]=c*akp-s*akq;a[k][q]=a[q][k]=s*akp+c*akq;
    }
    a[p][p]=c*c*app-2*c*s*apq+s*s*aqq;
    a[q][q]=s*s*app+2*c*s*apq+c*c*aqq;a[p][q]=a[q][p]=0;
    for(let k=0;k<n;k++){const vkp=v[k][p],vkq=v[k][q];v[k][p]=c*vkp-s*vkq;v[k][q]=s*vkp+c*vkq;}
  }
  return a.map((row,i)=>({value:row[i],vector:v.map(row=>row[i])})).sort((a,b)=>b.value-a.value);
}
function checkCandidates(candidates,selected){
  assert.deepEqual(candidates.map(row=>row.k),[2,3,4,5,6]);
  for(const row of candidates){
    assert.equal(row.eligible,row.min_cluster_size>=3);
    assert.equal(Number.isFinite(row.silhouette),row.eligible);
  }
  const best=candidates.filter(row=>row.eligible).sort((a,b)=>b.silhouette-a.silhouette)[0];
  assert.equal(selected,best?.k||0,'Select only an eligible candidate with maximal silhouette.');
}
export function validateDataeconomyMultivariate(mv,observations){
  assert.ok(['computed','no_common_publication_period','insufficient_observed_matrix','constant_feature'].includes(mv.status));
  assert.equal(mv.summary.ranking_validated,false);
  if(mv.status!=='computed'){
    assert.ok(!mv.baseline&&!mv.replication,'An unavailable model cannot retain former computed results.');
    return;
  }
  const base=mv.baseline,n=base.row_order.length,p=mv.features.length;
  assert.equal(n,mv.summary.regions);assert.equal(p,mv.summary.features);assert.equal(n*p,mv.summary.raw_cells);
  assert.equal(new Set(base.row_order).size,n);
  const sourceIndex=new Map();
  for(const row of observations.values())if(row.geo_level==='regional'){
    const key=[row.source_id,row.map_id||row.code,row.period_end].join('|');
    if(!sourceIndex.has(key))sourceIndex.set(key,[]);sourceIndex.get(key).push(row);
  }
  let imputed=0;
  for(let i=0;i<n;i++){
    for(const field of ['raw_matrix','used_matrix','imputation_mask','z_matrix'])assert.equal(base[field][i].length,p);
    for(let j=0;j<p;j++){
      const raw=base.raw_matrix[i][j],used=base.used_matrix[i][j],mask=base.imputation_mask[i][j];
      const source=sourceIndex.get([mv.features[j].source_id,base.row_order[i],mv.period_end].join('|'))||[];
      assert.equal(Boolean(mask),raw===null,'Only a missing source cell may be imputed.');
      if(raw===null){
        imputed++;assert.ok(!source.some(row=>Number.isFinite(row.analytical_value)),'Missing matrix cell agrees with source absence.');
        close(used,median(base.raw_matrix.map(row=>row[j]).filter(Number.isFinite)),'Median imputation from available original values.');
      }else{
        assert.ok(source.some(row=>row.analytical_value===raw),'Every matrix cell refers to a same-period source observation.');
        assert.equal(used,raw,'Observed matrix values remain unchanged.');
      }
    }
  }
  assert.equal(imputed,mv.summary.imputed_cells);
  const std=standardized(base.used_matrix),cov=covariance(std.z),trace=cov.reduce((sum,row,i)=>sum+row[i],0);
  for(let j=0;j<p;j++){
    close(mv.features[j].mean,std.means[j],'Independent feature mean.');
    close(mv.features[j].scale,std.scales[j],'Independent population standard deviation.');
    for(let i=0;i<n;i++)close(base.z_matrix[i][j],std.z[i][j],'Independent standardized cell.');
  }
  const components=base.pca.components,ratios=base.pca.explained_variance_ratio;
  close(ratios.reduce((sum,v)=>sum+v,0),1,'All PCA variance ratios sum to one.');
  for(let component=0;component<components.length;component++){
    const vector=components[component],eigenvalue=ratios[component]*trace;
    for(let other=0;other<components.length;other++)close(dot(vector,components[other]),Number(component===other),'PCA orthonormality.');
    for(let j=0;j<p;j++)close(dot(cov[j],vector),eigenvalue*vector[j],'PCA covariance eigenvector equation.');
    for(let i=0;i<n;i++)close(base.pca.scores[i][component],dot(std.z[i],vector),'PCA score projected from original matrix.');
  }
  close(mv.summary.pc12_variance,ratios[0]+ratios[1],'First two component variance.');
  checkCandidates(base.clusters.candidates,base.clusters.selected_k);
  if(base.clusters.selected_k){
    close(base.clusters.silhouette,silhouette(std.z,base.clusters.labels),'Independent baseline silhouette.');
    close(mv.summary.silhouette,base.clusters.silhouette,'Summary baseline silhouette.');
  }else{
    assert.equal(base.clusters.silhouette,null);assert.equal(mv.summary.silhouette,null);
    assert.ok(base.clusters.labels.every(label=>label===0),'No eligible baseline partition retains zero labels.');
  }
  assert.equal(mv.summary.baseline_k,base.clusters.selected_k);
  for(let i=0;i<n;i++){
    assert.equal(base.rows[i].code,base.row_order[i]);assert.equal(base.rows[i].cluster,base.clusters.selected_k?base.clusters.labels[i]:null);
    close(base.rows[i].pc1,base.pca.scores[i][0],'First displayed coordinate.');close(base.rows[i].pc2,base.pca.scores[i][1],'Second displayed coordinate.');
  }
  for(const run of [...mv.seed_sensitivity,...mv.feature_sensitivity]){
    checkCandidates(run.candidates,run.selected_k);
    if(run.selected_k){
      if(base.clusters.selected_k)close(run.ari_selected_vs_baseline,adjustedRand(base.clusters.labels,run.labels),'Independent adjusted Rand index.');
      else assert.equal(run.ari_selected_vs_baseline,null,'ARI requires both partitions.');
      const matrix=run.omitted_source_id?std.z.map(row=>row.filter((_,j)=>mv.features[j].source_id!==run.omitted_source_id)):std.z;
      close(run.silhouette,silhouette(matrix,run.labels),'Independent sensitivity silhouette.');
    }else{
      assert.equal(run.ari_selected_vs_baseline,null);assert.equal(run.silhouette,null);
      assert.ok(run.labels.every(label=>label===0),'Absent partition cannot masquerade as a ranked cluster.');
    }
  }
  assert.equal(mv.summary.seed_runs,mv.seed_sensitivity.length);
  assert.equal(mv.summary.eligible_seed_runs,mv.seed_sensitivity.filter(run=>run.selected_k>0).length);
  assert.equal(mv.summary.feature_omissions,mv.feature_sensitivity.length);
  assert.equal(mv.summary.eligible_feature_omissions,mv.feature_sensitivity.filter(run=>run.selected_k>0).length);
  const temporal=mv.temporal,bases={};
  assert.ok(['computed','no_earlier_complete_panel'].includes(temporal.status));
  if(temporal.status==='computed'){
  assert.equal(temporal.imputed_cells,0);
  for(const which of ['previous','current']){
    const matrix=temporal.raw_matrices[which];assert.equal(matrix.length,temporal.n_regions);
    for(let i=0;i<matrix.length;i++)for(let j=0;j<p;j++){
      assert.ok(Number.isFinite(matrix[i][j]));
      const original=sourceIndex.get([mv.features[j].source_id,temporal.region_order[i],temporal[which+'_period']].join('|'))||[];
      assert.ok(original.some(row=>row.analytical_value===matrix[i][j]),'Temporal comparison uses observed matching cells.');
    }
    const z=standardized(matrix).z;
    bases[which]=eigenvectors(covariance(z)).slice(0,2).map(component=>{
      const scores=z.map(row=>dot(row,component.vector)),norm=Math.sqrt(dot(scores,scores));
      return scores.map(score=>score/norm);
    });
    for(let i=0;i<z.length;i++)for(let j=0;j<p;j++)close(temporal.z_matrices[which][i][j],z[i][j],'Independent temporal standardization.');
    checkCandidates(temporal.candidates[which],temporal[which+'_k']);
    if(temporal[which+'_k'])close(temporal[which+'_silhouette'],silhouette(z,temporal.labels[which]),'Independent temporal silhouette.');
    else{assert.equal(temporal[which+'_silhouette'],null);assert.ok(temporal.labels[which].every(label=>label===0));}
  }
  if(temporal.previous_k&&temporal.current_k)close(temporal.ari_selected,adjustedRand(temporal.labels.previous,temporal.labels.current),'Independent temporal ARI.');
  else assert.equal(temporal.ari_selected,null,'Temporal ARI requires both eligible partitions.');
  if(!base.clusters.selected_k){assert.equal(temporal.ari_fixed_k,null);assert.equal(temporal.fixed_k_eligible_both,null);}
  const overlap=bases.previous.map(a=>bases.current.map(b=>dot(a,b))),a=overlap[0][0]**2+overlap[1][0]**2,b=overlap[0][0]*overlap[0][1]+overlap[1][0]*overlap[1][1],d=overlap[0][1]**2+overlap[1][1]**2;
  const minimum=Math.max(0,Math.min(1,((a+d)-Math.sqrt((a-d)**2+4*b*b))/2));
  close(temporal.pc12_subspace_overlap,(a+d)/2,'Independent squared-cosine overlap of regional score subspaces.');
  close(temporal.pc12_max_principal_angle_degrees,Math.acos(Math.sqrt(minimum))*180/Math.PI,'Independent maximal principal angle.');
  }
  const outliers=mv.outlier_sensitivity;
  assert.equal(outliers.runs.length,outliers.seeds.length);
  for(const row of outliers.rows){
    const count=outliers.runs.filter(run=>run.flagged_regions.includes(row.code)).length;
    assert.equal(row.flagged_runs,count);assert.equal(row.n_runs,outliers.runs.length);
    close(row.algorithmic_flag_fraction,count/row.n_runs,'Flag fraction is a count of algorithmic runs.');
  }
  const replication=mv.replication;
  assert.equal(typeof replication.baseline_reference_input_identical,'boolean');
  assert.equal(typeof replication.temporal_reference_input_identical,'boolean');
  assert.equal(replication.reference_input_identical,replication.baseline_reference_input_identical&&replication.temporal_reference_input_identical);
  assert.equal(replication.passed,replication.checks.length>0&&replication.checks.every(check=>check.passed));
  for(const check of replication.checks)assert.equal(check.passed,true,check.metric);
  assert.equal(replication.status,replication.reference_input_identical?'matched':'current_input_differs_from_reference');
  assert.equal(replication.checks.filter(check=>check.metric.startsWith('temporal_')).length,replication.temporal_reference_input_identical?5:0);
  assert.equal(replication.checks.filter(check=>!check.metric.startsWith('temporal_')).length,replication.baseline_reference_input_identical?6+3*p+4*mv.seed_sensitivity.length+5*mv.feature_sensitivity.length+n:0);
}

export async function validateDataeconomy(root){
  const docs=path.join(root,'docs'),prefix='data/projects/data_economy/';
  const bytes=relative=>fs.readFile(path.join(docs,relative.replace(/^\.\//,'')));
  const read=async relative=>JSON.parse(await bytes(relative));
  const [statistics,analytics,report,runtime,status,methods]=await Promise.all(
    ['statistics','analytics','expertise','documentary','refresh-status','methods'].map(name=>read(prefix+name+'.json')));
  const documentary=await read(runtime.downloads.full_documentary);
  const config=JSON.parse(await fs.readFile(path.join(root,'scripts/dataeconomy_emiss_sources.json'),'utf8'));
  for(const packet of [statistics,analytics,status,methods])assert.equal(packet.project_id,'data_economy');
  for(const packet of [runtime,documentary])assert.equal(packet.meta.project_id,'data_economy');
  assert.equal(getProject('data_economy').color,'#4224FD');
  assert.equal(getProject('data_economy').hasAuthors,false);
  assert.equal(methods.items.length,39);
  for(const method of methods.items){
    assert.ok(method.current_status&&method.current_status_label&&method.current_limitations,
      'Every inherited method has an explicit current evidence status: '+method.method_id);
  }

  const reportCheck=validateDataeconomyContent(report);
  assert.equal(sha(await bytes(report.meta.report_url)),report.meta.source_docx_sha256,'Original report bytes.');
  const coverage=await read(report.meta.coverage_url);
  assert.equal(coverage.summary.substantive_blocks,coverage.summary.assigned_blocks);
  assert.deepEqual(coverage.summary.unmapped_substantive_blocks,[]);
  assert.deepEqual(coverage.summary.duplicate_assignments,[]);
  assert.equal(coverage.summary.tables,report.tables.length);
  assert.equal(coverage.summary.figures,report.figures.length);
  const sourceIds=new Set(report.sources.map(source=>source.id));
  for(const source of report.sources.filter(source=>source.kind==='source_note')){
    assert.ok(source.source_blocks?.length,'Every footnote retains its original body/table reference: '+source.id);
    assert.ok(Object.values(report.pages).some(page=>page.blocks.some(block=>(block.sourceIds||[]).includes(source.id))),source.id);
  }
  for(const table of report.tables)for(const id of [...(table.headerSourceIds||[]).flat(),...(table.cellSourceIds||[]).flat(2)]){
    assert.ok(sourceIds.has(id)&&table.sourceIds.includes(id),'Cell citation belongs to its original table.');
  }
  for(const figure of report.figures)await bytes(figure.url);
  for(const page of dataeconomyPages){
    const html=(await bytes('research/projects/data_economy/'+(page.id==='overview'?'index':page.id)+'.html')).toString();
    assert.ok(html.includes('--brand:#4224FD;'));
    assert.ok(html.includes('#/projects/data_economy/'+page.id));
  }

  assert.deepEqual(new Set(statistics.sources.map(source=>source.id)),new Set(config.sources.map(source=>String(source.indicator_id))));
  assert.deepEqual(statistics.coverage,analytics.coverage);
  assert.equal(statistics.registry.length,statistics.coverage.registry_indicators);
  const observations=new Map(),sourceMap=new Map(statistics.sources.map(source=>[source.id,source]));
  let cells=0,numeric=0,usable=0,excluded=0,annual=0;
  for(const source of statistics.sources){
    const raw=await bytes(prefix+'series/'+source.id+'.json'),packet=JSON.parse(raw);
    const provenance=await read(prefix+'provenance/'+source.id+'.json');
    assert.equal(packet.project_id,'data_economy');
    assert.equal(packet.source_id,source.id);assert.equal(packet.unit,source.unit);
    assert.equal(sha(raw),provenance.published_sha256,'Published source SHA: '+source.id);
    assert.equal(sha(await bytes(provenance.input_bundle)),provenance.input_sha256,'Included source bundle: '+source.id);
    assert.equal(packet.observations.length,source.observation_count);
    let sourceNumeric=0,sourceUsable=0,sourceExcluded=0;
    for(const row of packet.observations){
      assert.equal(row.source_id,source.id);
      assert.ok(!observations.has(row.id),'Unique source observation: '+row.id);
      assert.ok(row.source_observation_key&&typeof row.raw_value==='string');
      assert.match(row.period_start,/^\d{4}-\d{2}-\d{2}$/);
      assert.match(row.period_end,/^\d{4}-\d{2}-\d{2}$/);
      assert.ok(row.value===null||Number.isFinite(row.value));
      assert.equal(row.analytical_value,row.excluded?null:row.value);
      assert.ok(Array.isArray(row.quality_flags));
      if(row.value!==null){numeric++;sourceNumeric++;}
      if(row.analytical_value!==null){usable++;sourceUsable++;}
      if(row.value!==null&&row.excluded){excluded++;sourceExcluded++;}
      if(row.geo_level==='national'&&row.frequency==='annual'&&row.analytical_value!==null)annual++;
      if(row.geo_level==='regional')assert.match(row.map_id||row.code,/^\d{2}$/);
      if(row.annual_comparison_eligible)assert.equal(row.frequency,'annual');
      // Keep only fields required by cross-file checks; raw dimensions remain in each source file.
      const {id,source_id,geo_level,map_id,code,period,period_end,frequency,year,category,value,analytical_value,geographic_comparison_eligible,national_scope}=row;
      observations.set(id,{id,source_id,geo_level,map_id,code,period,period_end,frequency,year,category,value,analytical_value,geographic_comparison_eligible,national_scope});
    }
    cells+=packet.observations.length;
    assert.equal(sourceNumeric,source.numeric_count);assert.equal(sourceUsable,source.usable_count);
    assert.equal(sourceExcluded,source.excluded_numeric_count);
    assert.equal(packet.observations.length-sourceNumeric,source.missing_count);
    for(const row of [...source.national,...source.regional_latest]){
      const original=observations.get(row.id);assert.ok(original);
      assert.equal(row.value,original.value);assert.equal(row.analytical_value,original.analytical_value);
      assert.equal(row.period,original.period);assert.equal(row.frequency,original.frequency);
    }
    if(provenance.current_raw)assert.equal(sha(await bytes(provenance.current_raw)),provenance.current_raw_sha256);
  }
  for(const [key,count] of Object.entries({observations:cells,numeric_observations:numeric,missing_observations:cells-numeric,
    usable_observations:usable,excluded_numeric_observations:excluded,independent_annual_national_facts:annual}))assert.equal(statistics.coverage[key],count,key);
  for(const comparison of analytics.target_comparisons){
    const row=observations.get(comparison.reference_observation_id);assert.ok(row);
    const ids=comparison.reference_observation_ids||[comparison.reference_observation_id];
    assert.equal(new Set(ids).size,ids.length);
    assert.ok(ids.includes(comparison.reference_observation_id));
    const references=ids.map(id=>observations.get(id));
    for(const reference of references){
      assert.ok(reference);
      assert.equal(reference.geo_level,'national');assert.equal(reference.source_id,row.source_id);
      assert.equal(reference.period,row.period);assert.equal(reference.frequency,row.frequency);
      assert.ok(Number.isFinite(reference.analytical_value));
    }
    close(references.reduce((sum,reference)=>sum+reference.analytical_value,0),comparison.fact_value,
      'A comparison preserves every explicitly referenced observation, without changing its period or denominator.');
    assert.equal(row.period,comparison.fact_period);assert.equal(row.frequency,comparison.fact_frequency);
    assert.ok(sourceMap.get(row.source_id).target_comparison_allowed);
    close(comparison.difference,comparison.fact_value-comparison.target_value,'Target difference.');
    if(comparison.target_value)close(comparison.ratio_percent,100*comparison.fact_value/comparison.target_value,'Target ratio.');
    assert.equal(comparison.formal_attainment_eligible,false,'Late published plan comparison is not certification of original plan attainment.');
  }
  validateDataeconomyMultivariate(analytics.multivariate,observations);
  assert.equal(analytics.correlations.computed,false,'No separate correlation model is claimed in the current report.');
  assert.equal(analytics.digital.composite_ranking_computed,false);
  assert.equal(analytics.digital.source_series_imputed_cells,0);
  for(const profile of analytics.digital.regional_profiles){
    assert.equal(profile.rows.length,profile.n);
    assert.equal(new Set(profile.rows.map(row=>row.map_id||row.code)).size,profile.n);
    const values=[];
    for(const row of profile.rows){
      const original=observations.get(row.id);assert.ok(original);
      assert.equal(original.source_id,profile.source_id);
      assert.equal(original.geo_level,'regional');
      assert.equal(original.period,profile.period);assert.equal(original.frequency,profile.frequency);
      assert.equal(original.analytical_value,row.analytical_value);
      assert.ok(Number.isFinite(row.analytical_value));values.push(row.analytical_value);
    }
    if(values.length){
      close(profile.median,median(values),'Independent median: '+profile.id);
      close(profile.q1,quantile(values,.25),'Independent first quartile: '+profile.id);
      close(profile.q3,quantile(values,.75),'Independent third quartile: '+profile.id);
      close(profile.mean,values.reduce((sum,value)=>sum+value,0)/values.length,'Independent unweighted mean: '+profile.id);
    }
  }
  for(const source of statistics.sources){
    if(source.proxy_only)assert.ok(!analytics.target_comparisons.some(row=>row.source_id===source.id),
      'A proxy must retain its documented comparison scope.');
    if(source.scenario_allowed===false){
      assert.ok(source.period_note||source.note,'A disabled scenario retains its source-specific reason.');
    }
  }

  const foundation=await read(prefix+'foundation.json');
  assert.ok(foundation.legacy_release_metadata?.original,'Earlier metadata is preserved explicitly.');
  assert.equal(foundation.author_expertise_status,'published');
  assert.equal(foundation.registry.n_unique_cells,cells);
  assert.equal(foundation.registry.n_domain_violations,statistics.coverage.domain_violations);
  assert.equal(foundation.registry.n_review_exclusions,statistics.coverage.review_exclusions);
  assert.equal(foundation.panel.clustering_performed,analytics.multivariate.status==='computed');
  assert.equal(foundation.panel.pca_performed,analytics.multivariate.status==='computed');
  assert.equal(foundation.panel.ranking_validated,false);
  assert.equal(foundation.results.n_projected_series,0);
  assert.equal(foundation.results.forecast_status,'model_not_validated');

  const finance=documentary.finance;
  assert.equal(finance.unit,'тыс. руб.');
  let national=0n,federal=0n;
  for(const year of finance.yearTotals){
    const fp=finance.fpYears.filter(row=>row.year===year.year&&row.amount_decimal!==null);
    const np=finance.nationalSourceYears.filter(row=>row.year===year.year&&row.amount_decimal!==null);
    const f=fp.reduce((sum,row)=>sum+cents(row.amount_decimal),0n),n=np.reduce((sum,row)=>sum+cents(row.amount_decimal),0n);
    assert.equal(f,cents(year.federal_decimal));assert.equal(n,cents(year.national_decimal));
    assert.equal(f-n,cents(year.difference_decimal),'FP minus NP, one year and the same funding scope.');
    national+=n;federal+=f;
  }
  assert.equal(national,cents(finance.nationalDecimal));assert.equal(federal,cents(finance.federalDecimal));
  assert.equal(national,cents(finance.totalDecimal));
  for(const row of finance.sourceYears.filter(row=>row.amount_decimal===null))assert.equal(row.amount_thousand_rub,null);
  close(finance.hhi,finance.federalShares.reduce((sum,row)=>sum+row.share**2,0),'FP financing concentration.');
  const budget=finance.budgetBill;
  assert.equal(sha(await bytes(budget.source_html_download)),budget.source_html_sha256);
  assert.equal(budget.unit,'млн руб.');
  assert.equal(budget.rows.length,budget.published_numeric_cells);
  for(const row of budget.rows){
    assert.ok(row.source_locator&&row.source_sha256);
    assert.ok(!/^\d+$/.test(row.name),'Column number is not a budget expenditure row.');
  }

  const nodeMap=new Map(documentary.network.nodes.map(row=>[row.id||row.node_id,row]));
  assert.equal(nodeMap.size,documentary.network.nodes.length);
  for(const edge of documentary.network.reviewedEdges)assert.ok(edge.evidence_class&&edge.source_locator,
    'A reviewed link must retain the review basis and source address.');
  for(const pair of documentary.network.sharedTaskPairs){
    const result=nodeMap.get(pair.result_node_id),indicator=nodeMap.get(pair.indicator_node_id),task=nodeMap.get(pair.task_node_id);
    assert.equal(result?.kind,'result');assert.equal(indicator?.kind,'indicator');assert.equal(task?.kind,'task');
    assert.equal(result.document_id,pair.document_id);assert.equal(indicator.document_id,pair.document_id);assert.equal(task.document_id,pair.document_id);
    assert.notEqual(task.scope,'national_structure_federal_task_restatement');
    assert.equal(pair.official_weight??null,null);
    assert.equal(pair.causal_status,'not_identified');
    assert.equal(pair.evidence_class,'same_document_task_membership');
  }
  for(const claim of documentary.network.unresolvedClaims)assert.equal(claim.indicator_node_id,null);
  for(const row of finance.resultYears){
    const result=nodeMap.get(row.result_id);assert.equal(result?.kind,'result');
    assert.equal(result.document_id,row.document_id);assert.equal(result.source_locator,row.source_result_locator);
    assert.ok(row.source_locator.startsWith(row.source_result_locator+'/'));
    if(row.is_subcomponent)assert.equal(row.included_in_additive_total,false);
  }
  for(const source of documentary.sources){
    assert.equal(sha(await bytes(source.download_path)),source.source_sha256||source.sha256);
    assert.equal(source.source_kind,'secondary_epbs_rendering');
  }
  assert.deepEqual(runtime.network.summary,documentary.network.summary);
  assert.equal(runtime.targets.items.length,statistics.registry.length);
  let targetCells=0,targetNumbers=0;
  for(const target of documentary.targets.items){
    assert.ok(target.source_sha256&&target.source_locator&&target.source_document);
    assert.deepEqual(Object.keys(target.years),['2025','2026','2027','2028','2029','2030']);
    for(const value of Object.values(target.years)){assert.ok(value===null||Number.isFinite(value));targetCells++;if(value!==null)targetNumbers++;}
  }
  assert.equal(documentary.targets.target_cells,targetCells);assert.equal(documentary.targets.numeric_targets,targetNumbers);
  assert.equal(documentary.targets.missing_targets,targetCells-targetNumbers);
  assert.equal(typeof documentary.text.authorExactCodeAvailable,'boolean');
  assert.ok(documentary.text.sensitivity.length>=2,'Textual sensitivity must retain the actual alternative specifications.');
  const author=documentary.text.authorAnalysis;
  assert.equal(author.documents,documentary.meta.corpus_documents);
  assert.equal(author.digital_documents,documentary.sources.length);
  assert.equal(sha(await bytes(author.source_code_url)),author.source_code_sha256,'Included author analysis code.');
  assert.equal(sha(await bytes(author.shared_profiles_url)),author.shared_profiles_sha256,'Pinned shared text corpus.');
  if(documentary.text.authorExactCodeAvailable){
    assert.equal(author.baseline_and_stemming_match_reference,true);
    assert.equal(author.all_digital_source_profiles_verified,true);
    for(const item of documentary.text.replicationAudit)assert.equal(item.equal,true,'Exact reference replay: '+item.metric);
  }
  for(const file of Object.values(documentary.text.documentFiles))await bytes(file);
  for(const item of documentary.text.replicationAudit)assert.equal(item.difference,item.platform_recomputed-item.author_report);
  for(const url of Object.values(runtime.downloads))await bytes(url);
  assert.equal(status.project_id,'data_economy');
  assert.ok(status.checked_at&&status.published_at);
  console.log(`Validated Dataeconomy: ${statistics.sources.length} sources, ${cells} cells, ${numeric} numeric values, ${reportCheck.routes} pages, ${nodeMap.size} documentary nodes and source-linked financial arithmetic.`);
  return {sources:statistics.sources.length,cells,numeric,routes:reportCheck.routes,nodes:nodeMap.size};
}
