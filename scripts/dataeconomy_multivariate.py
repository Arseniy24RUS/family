"""Source-linked regional PCA and sensitivity of Data Economy descriptions.

Raw EMISS series remain unchanged. The sole allowed imputation is explicitly
recorded inside a retained multivariate matrix. Region groups are descriptive,
not an ordinal ranking or evidence of a policy effect.
"""
from __future__ import annotations
import hashlib,json,math,importlib.metadata
from pathlib import Path
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import adjusted_rand_score,silhouette_score
from threadpoolctl import threadpool_limits
from dataeconomy_data import load,atomic,csv_write,DOWNLOADS

SEEDS=(0,1,7,21,42,99,2026)
SOURCE_IDS=('62760','62767','62766','62815','62763')

def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple,np.ndarray)):return [clean(x) for x in v]
    if isinstance(v,(np.integer,)):return int(v)
    if isinstance(v,(np.bool_,)):return bool(v)
    if isinstance(v,(float,np.floating)):return float(v) if math.isfinite(v) else None
    return v

def scaled(x):
    sd=x.std(axis=0,ddof=0)
    if np.any(sd<=1e-12):raise ValueError('Constant feature in current multivariate matrix')
    return (x-x.mean(axis=0))/sd

def select_clusters(z,seed=42):
    candidates=[];fits={}
    for k in range(2,min(6,len(z)//5)+1):
        fit=KMeans(n_clusters=k,n_init=20,random_state=int(seed)).fit(z)
        minimum=int(np.bincount(fit.labels_,minlength=k).min());sil=float(silhouette_score(z,fit.labels_)) if minimum>=3 else None
        candidates.append({'k':k,'min_cluster_size':minimum,'silhouette':sil,'eligible':sil is not None});fits[k]=fit
    eligible=[r for r in candidates if r['eligible']]
    if eligible:
        chosen=max(eligible,key=lambda r:r['silhouette']);k=chosen['k']
        return k,fits[k].labels_+1,chosen['silhouette'],candidates,fits
    return 0,np.zeros(len(z),dtype=int),None,candidates,fits

def pca(z):
    fit=PCA(n_components=min(5,z.shape[1],z.shape[0]),svd_solver='full').fit(z)
    return fit,fit.transform(z)

def score_subspace(a,b):
    r=min(2,a.shape[1],b.shape[1]);qa,_=np.linalg.qr(a[:,:r]-a[:,:r].mean(axis=0));qb,_=np.linalg.qr(b[:,:r]-b[:,:r].mean(axis=0))
    sv=np.clip(np.linalg.svd(qa.T@qb,compute_uv=False),0,1)
    return float(np.degrees(np.arccos(sv.min()))),float(np.sum(sv*sv)/r)

def build_multivariate(root,packets,sources):
    root=Path(root)
    with threadpool_limits(limits=1):result=clean(_build(root,packets,sources))
    destination=root/DOWNLOADS
    atomic(destination/'multivariate.json',result,compact=True)
    tables={'multivariate_inputs':result.get('inputs',[]),
        'multivariate_pca_scores':result.get('baseline',{}).get('rows',[]),
        'multivariate_features':result.get('features',[]),
        'multivariate_replication':result.get('replication',{}).get('checks',[]),
        'multivariate_temporal_inputs':result.get('temporal_inputs',[]),
        'multivariate_imputations':result.get('imputations',[])}
    for name,rows in tables.items():
        if result['status']!='computed':rows=[{'status':result['status'],'period_end':result.get('period_end'),'data_rows_available':False}]
        csv_write(destination/(name+'.csv'),rows)
    return result

def _build(root,packets,sources):
    refs=load(root/'inputs/dataeconomy/statistics/multivariate_reference.json');ref=refs['tables'];by={s['id']:s for s in sources}
    historical_features=sorted(ref['q_baseline_features'],key=lambda r:r['slice_id'])
    ids=[r['source_id'] for r in historical_features]
    assert tuple(ids)==SOURCE_IDS
    lookups={};periods=[];names={}
    for sid in ids:
        usable=[r for r in packets[sid]['observations'] if r['geo_level']=='regional' and r['geographic_comparison_eligible'] and r['category']=={} and r['analytical_value'] is not None]
        lookup={}
        for r in usable:
            key=(r['period_end'],r['code'])
            if key in lookup and lookup[key]['value']!=r['value']:raise ValueError('Ambiguous multivariate source cell')
            lookup[key]=r;names[r['code']]=r['name']
        lookups[sid]=lookup;periods.append({k[0] for k in lookup})
    common_periods=set.intersection(*periods)
    if not common_periods:return {'status':'no_common_publication_period','source_ids':ids,'summary':{'ranking_validated':False}}
    end=max(common_periods);all_regions=sorted({code for sid in ids for date,code in lookups[sid] if date==end})
    regions=[code for code in all_regions if sum((end,code) in lookups[s] for s in ids)>=4]
    raw=np.array([[lookups[sid].get((end,code),{}).get('value',np.nan) for sid in ids] for code in regions],float)
    if len(regions)<20 or np.any(np.sum(~np.isnan(raw),axis=0)<20):return {'status':'insufficient_observed_matrix','period_end':end,'source_ids':ids,'summary':{'regions':len(regions),'features':len(ids),'ranking_validated':False},'raw_matrix':raw,'row_order':regions}
    medians=np.nanmedian(raw,axis=0);mask=np.isnan(raw);used=np.where(mask,medians,raw);means=used.mean(axis=0);scales=used.std(axis=0,ddof=0)
    if np.any(scales<=1e-12):return {'status':'constant_feature','period_end':end,'summary':{'regions':len(regions),'features':len(ids),'ranking_validated':False},'raw_matrix':clean(raw),'row_order':regions,'source_ids':ids}
    z=scaled(used);pc,scores=pca(z);k,labels,sil,candidates,fits=select_clusters(z,42)
    features=[{'source_id':sid,'title':by[sid]['short_title'],'slice_id':historical_features[j]['slice_id'],'mean':means[j],'scale':scales[j],'median':medians[j],'source_period_semantics':by[sid]['period_semantics']} for j,sid in enumerate(ids)]
    inputs=[];imputations=[]
    for i,code in enumerate(regions):
        for j,sid in enumerate(ids):
            obs=lookups[sid].get((end,code));record={'period_end':end,'code':code,'name':names[code],'source_id':sid,'raw_value':None if mask[i,j] else raw[i,j],'used_value':used[i,j],'z':z[i,j],'imputed':bool(mask[i,j]),'observation_id':obs['id'] if obs else None,'imputation_rule':'within_panel_observed_median' if mask[i,j] else None,'imputation_median':medians[j] if mask[i,j] else None}
            inputs.append(record)
            if mask[i,j]:imputations.append(record)
    starts=[];forest_flags=[];outlier_runs=[]
    for seed in SEEDS:
        sk,sl,ss,sc,sf=select_clusters(z,seed);fixed=sf.get(k)
        minimum=int(np.bincount(fixed.labels_,minlength=k).min()) if fixed is not None else None
        starts.append({'seed':seed,'selected_k':sk,'silhouette':ss,'ari_selected_vs_baseline':float(adjusted_rand_score(labels,sl)) if k>=2 and sk>=2 else None,'ari_fixed_k_vs_baseline':float(adjusted_rand_score(labels,fixed.labels_)) if fixed is not None else None,'fixed_k_min_cluster_size':minimum,'fixed_k_eligible':minimum>=3 if minimum is not None else None,'candidates':sc,'labels':sl})
        forest=IsolationForest(n_estimators=200,contamination=.15,random_state=seed).fit(z);flags=forest.predict(z)==-1;forest_flags.append(flags)
        outlier_runs.append({'seed':seed,'flagged_regions':[regions[i] for i,x in enumerate(flags) if x]})
    omissions=[]
    for j,sid in enumerate(ids):
        newer=np.delete(z,j,axis=1);fk,fl,fs,fc,ff=select_clusters(newer,42);fp,fp_scores=pca(newer);angle,overlap=score_subspace(scores,fp_scores);fixed=ff.get(k)
        minimum=int(np.bincount(fixed.labels_,minlength=k).min()) if fixed is not None else None
        omissions.append({'omitted_source_id':sid,'omitted_title':by[sid]['short_title'],'selected_k':fk,'silhouette':fs,'ari_selected_vs_baseline':float(adjusted_rand_score(labels,fl)) if k>=2 and fk>=2 else None,'ari_fixed_k_vs_baseline':float(adjusted_rand_score(labels,fixed.labels_)) if fixed is not None else None,'fixed_k_min_cluster_size':minimum,'fixed_k_eligible':minimum>=3 if minimum is not None else None,'pc12_variance':float(fp.explained_variance_ratio_[:2].sum()),'pc12_max_principal_angle_degrees':angle,'pc12_subspace_overlap':overlap,'candidates':fc,'labels':fl})
    complete=[regions[i] for i in range(len(regions)) if not mask[i].any()];cc_index=[regions.index(c) for c in complete]
    ck,cl,cs,ccandidates,_=select_clusters(scaled(raw[cc_index]),42)
    complete_case={'n_regions':len(complete),'selected_k':ck,'silhouette':cs,'ari_vs_baseline':float(adjusted_rand_score(labels[cc_index],cl)) if k>=2 and ck>=2 else None,'imputed_cells':0,'candidates':ccandidates,'region_order':complete}
    temporal={'status':'no_earlier_complete_panel','current_period':end};temporal_inputs=[]
    for previous in sorted((p for p in common_periods if p<end),reverse=True):
        shared=[code for code in complete if all((previous,code) in lookups[s] for s in ids)]
        if len(shared)<20:continue
        a=np.array([[lookups[s][(previous,code)]['value'] for s in ids] for code in shared],float);b=np.array([[lookups[s][(end,code)]['value'] for s in ids] for code in shared],float)
        if np.any(a.std(axis=0)<=1e-12) or np.any(b.std(axis=0)<=1e-12):continue
        za,zb=scaled(a),scaled(b);ka,la,sa,ca,fa=select_clusters(za,42);kb,lb,sb,cb,fb=select_clusters(zb,42);pa,ap=pca(za);pb,bp=pca(zb);angle,overlap=score_subspace(ap,bp)
        mina=int(np.bincount(fa[k].labels_,minlength=k).min()) if k>=2 else None;minb=int(np.bincount(fb[k].labels_,minlength=k).min()) if k>=2 else None
        temporal={'status':'computed','previous_period':previous,'current_period':end,'n_regions':len(shared),'n_features':len(ids),'imputed_cells':0,'previous_k':ka,'current_k':kb,'previous_silhouette':sa,'current_silhouette':sb,'ari_selected':float(adjusted_rand_score(la,lb)) if ka>=2 and kb>=2 else None,'ari_fixed_k':float(adjusted_rand_score(fa[k].labels_,fb[k].labels_)) if k>=2 else None,'fixed_k_previous_min_cluster_size':mina,'fixed_k_current_min_cluster_size':minb,'fixed_k_eligible_both':mina>=3 and minb>=3 if k>=2 else None,'pc12_max_principal_angle_degrees':angle,'pc12_subspace_overlap':overlap,'region_order':shared,'raw_matrices':{'previous':a,'current':b},'z_matrices':{'previous':za,'current':zb},'candidates':{'previous':ca,'current':cb},'labels':{'previous':la,'current':lb}}
        for period,matrix,std in [(previous,a,za),(end,b,zb)]:
            for i,code in enumerate(shared):
                for j,sid in enumerate(ids):temporal_inputs.append({'period_end':period,'code':code,'source_id':sid,'value':matrix[i,j],'z':std[i,j],'observation_id':lookups[sid][(period,code)]['id']})
        break
    counts=np.sum(np.array(forest_flags),axis=0)
    rows=[{'code':code,'name':names[code],'pc1':scores[i,0],'pc2':scores[i,1],'cluster':int(labels[i]) if k else None,'imputed':bool(mask[i].any()),'n_imputed_cells':int(mask[i].sum()),'flagged_runs':int(counts[i]),'n_runs':len(SEEDS),'algorithmic_flag_fraction':float(counts[i]/len(SEEDS))} for i,code in enumerate(regions)]
    checks=[]
    def check(name,actual,expected,tol=1e-9):
        same=(actual is None and expected in {None,''}) if actual is None else isinstance(actual,bool) and actual==expected or isinstance(actual,(int,float,np.integer,np.floating)) and expected not in {None,''} and abs(float(actual)-float(expected))<=tol*max(1,abs(float(expected)))
        checks.append({'metric':name,'actual':clean(actual),'reference':expected,'passed':bool(same)})
    reference_period=ref['q_baseline_panels'][0]['period_end']
    reference_baseline={(r['region_code'],r['slice_id']):None if r['raw_value']=='' else float(r['raw_value']) for r in ref['q_baseline_inputs']}
    current_baseline={(code,f['slice_id']):None if mask[i,j] else float(raw[i,j]) for i,code in enumerate(regions) for j,f in enumerate(features)}
    baseline_input_same=end==reference_period and current_baseline==reference_baseline
    old_time=ref['q_temporal_comparison'][0]
    reference_temporal={(r['period_end'],r['region_code'],r['source_id']):float(r['raw_value']) for r in ref['q_temporal_inputs']}
    current_temporal={(r['period_end'],r['code'],r['source_id']):float(r['value']) for r in temporal_inputs}
    temporal_input_same=(temporal['status']==old_time['status']=='computed'
        and temporal['previous_period']==old_time['previous_period']
        and temporal['current_period']==old_time['current_period']
        and current_temporal==reference_temporal)
    if baseline_input_same:
        rp=ref['q_baseline_panels'][0]
        for key,actual in [('k',k),('silhouette',sil),('pc12_variance',float(pc.explained_variance_ratio_[:2].sum())),('n_imputed_cells',int(mask.sum())),('n_regions',len(regions)),('n_features',len(ids))]:check('baseline_'+key,actual,rp[key])
        for j,f in enumerate(historical_features):
            for key,actual in [('mean',means[j]),('scale',scales[j]),('imputation_median',medians[j])]:check(f['source_id']+'_'+key,actual,f[key])
        for row,old in zip(starts,ref['q_cluster_seed_runs']):
            assert int(old['seed'])==row['seed']
            for key in ['selected_k','silhouette','ari_selected_vs_baseline','fixed_k_min_cluster_size']:check('seed_'+str(row['seed'])+'_'+key,row[key],old[key])
        old_features={r['omitted_source_id']:r for r in ref['q_feature_sensitivity']}
        for row in omissions:
            old=old_features[row['omitted_source_id']]
            for key in ['selected_k','silhouette','ari_selected_vs_baseline','pc12_subspace_overlap','pc12_max_principal_angle_degrees']:check('omit_'+row['omitted_source_id']+'_'+key,row[key],old[key],1e-7)
        old_out={r['region_code']:r for r in ref['q_outlier_stability']}
        for row in rows:check('outlier_seeds_'+row['code'],row['flagged_runs'],old_out[row['code']]['n_flagged_runs'])
    if temporal_input_same:
        for key in ['n_regions','previous_k','current_k','pc12_subspace_overlap','pc12_max_principal_angle_degrees']:check('temporal_'+key,temporal.get(key),old_time[key],1e-7)
    input_same=baseline_input_same and temporal_input_same
    checks_passed=bool(checks) and all(c['passed'] for c in checks)
    replication_status=('numerical_environment_or_method_difference' if any(not c['passed'] for c in checks)
        else 'matched' if input_same and checks_passed else 'current_input_differs_from_reference')
    reference_scopes={'baseline':baseline_input_same,'temporal':temporal_input_same}
    result={'status':'computed','period_end':end,'publication_frequency':'monthly','source_period_semantics_are_heterogeneous':True,
      'summary':{'regions':len(regions),'features':len(ids),'raw_cells':int(raw.size),'imputed_cells':int(mask.sum()),'baseline_k':k,'silhouette':sil,'pc1_variance':float(pc.explained_variance_ratio_[0]),'pc2_variance':float(pc.explained_variance_ratio_[1]),'pc12_variance':float(pc.explained_variance_ratio_[:2].sum()),'seed_runs':len(starts),'eligible_seed_runs':sum(r['selected_k']>=2 for r in starts),'feature_omissions':len(omissions),'eligible_feature_omissions':sum(r['selected_k']>=2 for r in omissions),'ranking_validated':False},
      'features':features,'source_ids':ids,'baseline':{'row_order':regions,'raw_matrix':raw,'used_matrix':used,'imputation_mask':mask,'z_matrix':z,'pca':{'explained_variance_ratio':pc.explained_variance_ratio_,'components':pc.components_,'scores':scores},'clusters':{'selected_k':k,'labels':labels,'silhouette':sil,'candidates':candidates},'rows':rows},
      'seed_sensitivity':starts,'feature_sensitivity':omissions,'temporal':temporal,'complete_case':complete_case,'outlier_sensitivity':{'algorithm':'IsolationForest','n_estimators':200,'contamination':.15,'seeds':list(SEEDS),'runs':outlier_runs,'rows':[{k:v for k,v in row.items() if k in {'code','name','flagged_runs','n_runs','algorithmic_flag_fraction'}} for row in rows],'interpretation':'Частота алгоритмической отметки при смене начального состояния. Она не является вероятностью ошибки, риска или неблагополучия.'},
      'imputations':imputations,'inputs':inputs,'temporal_inputs':temporal_inputs,'input_sha256':hashlib.sha256(json.dumps(clean({'regions':regions,'source_ids':ids,'raw':raw}),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
      'replication':{'reference_period':reference_period,'reference_input_identical':bool(input_same),'baseline_reference_input_identical':bool(baseline_input_same),'temporal_reference_input_identical':bool(temporal_input_same),'checked_scopes':[scope for scope,same in reference_scopes.items() if same],'skipped_scopes':[scope for scope,same in reference_scopes.items() if not same],'passed':checks_passed,'status':replication_status,'checks':checks,'reference_download':'downloads/projects/data_economy/statistics/reference/multivariate_reference.json'},
      'methods':{'standard_deviation_ddof':0,'pca_solver':'full','k_candidates':[2,3,4,5,6],'kmeans_n_init':20,'minimum_cluster_size':3,'baseline_seed':42,'seeds':list(SEEDS),'selection':'maximum_silhouette_among_eligible','matrix_region_minimum_observed_features':4,'imputation':'observed_median_only_inside_profile_matrix','source_series_imputed':False,'temporal_imputation':'none','dependencies':{name:importlib.metadata.version(name) for name in ['numpy','scipy','scikit-learn']},'causal_effect_identified':False},
      'interpretation':'Пять административных признаков имеют общий месяц публикации и разные содержательные периоды измерения. PCA и группы описывают сочетания этих признаков. Проверки начальных состояний, состава признаков и соседнего периода не подтверждают устойчивый интегральный рейтинг. Заполнение пропуска ограничено профильной матрицей; исходные ряды и карты не заполняются.'}
    return result
