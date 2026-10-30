#!/usr/bin/env python3
"""Independent checks and robustness of the preserved 1.1 regional analyses.

No network access, no source mutation. New diagnostics are not policy effects.
Python >=3.11; numpy, pandas, scipy, scikit-learn, matplotlib, threadpoolctl.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr, rankdata
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import adjusted_rand_score, silhouette_score
from threadpoolctl import threadpool_limits

VERSION = "1.2.0"
SEEDS = (0, 1, 7, 21, 42, 99, 2026)
FAMILY_SHA = "50ad21c1ad1c94e3cf07857363333df120558617"
FAMILY_URL = f"https://github.com/Arseniy24RUS/family/blob/{FAMILY_SHA}/documentation/METHODS.md"


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path, value):
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def sha256_file(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def json_hash(value):
    return hashlib.sha256(json.dumps(clean(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def independent_bh(values):
    """List implementation, independent of npanalytics.common.bh_adjust."""
    out = [None] * len(values)
    ordered = sorted((float(p), i) for i, p in enumerate(values) if p is not None and np.isfinite(p))
    m, running = len(ordered), 1.0
    for rank in range(m, 0, -1):
        p, i = ordered[rank - 1]
        running = min(running, p * m / rank)
        out[i] = running
    return out


def scaled(matrix):
    x = np.asarray(matrix, dtype=float)
    sd = x.std(axis=0, ddof=0)
    if np.any(sd <= 1e-12):
        raise ValueError("constant feature in robustness input")
    return (x - x.mean(axis=0)) / sd


def select_clusters(z, seed=42):
    candidates, fitted = [], {}
    for k in range(2, min(6, len(z) // 5) + 1):
        model = KMeans(n_clusters=k, n_init=20, random_state=int(seed)).fit(z)
        labels = model.labels_
        minimum = int(np.bincount(labels, minlength=k).min())
        sil = float(silhouette_score(z, labels)) if minimum >= 3 else None
        candidates.append(dict(k=k, silhouette=sil, min_cluster_size=minimum, eligible=sil is not None))
        fitted[k] = model
    eligible = [row for row in candidates if row["eligible"]]
    if eligible:
        selected = max(eligible, key=lambda row: row["silhouette"])
        return selected["k"], fitted[selected["k"]].labels_ + 1, selected["silhouette"], candidates, fitted
    return 0, np.zeros(len(z), dtype=int), None, candidates, fitted


def pca_scores(z):
    pca = PCA(n_components=min(5, z.shape[1], z.shape[0]), svd_solver="full").fit(z)
    return pca, pca.transform(z)


def score_subspace(a, b, dimensions=2):
    """Principal angles of the score subspaces on identical region rows."""
    r = min(dimensions, a.shape[1], b.shape[1])
    qa, _ = np.linalg.qr(a[:, :r] - a[:, :r].mean(axis=0))
    qb, _ = np.linalg.qr(b[:, :r] - b[:, :r].mean(axis=0))
    s = np.clip(np.linalg.svd(qa.T @ qb, compute_uv=False), 0, 1)
    return float(np.degrees(np.arccos(s.min()))), float(np.sum(s * s) / r)


class Output:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "tables").mkdir(exist_ok=True)
        self.db = self.root / "quantitative.sqlite3"
        self.con = sqlite3.connect(self.db)
        self.tables = {}

    def table(self, name, rows, columns=None):
        frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows, columns=columns)
        if not len(frame.columns):
            frame = pd.DataFrame(columns=["status"])
        for col in frame.columns:
            if frame[col].dtype == object:
                frame[col] = frame[col].map(lambda x: json.dumps(clean(x), ensure_ascii=False, sort_keys=True) if isinstance(x, (dict, list, tuple)) else x)
        name = "q_" + name
        frame.to_sql(name, self.con, if_exists="replace", index=False)
        frame.to_csv(self.root / "tables" / (name + ".csv"), index=False, encoding="utf-8-sig")
        self.tables[name] = len(frame)
        return frame


def build(package_root, outdir, make_figures=True):
    root = Path(package_root).resolve()
    db = root / "outputs/national_projects_analytics.sqlite"
    before = sha256_file(db)
    source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = Output(outdir)
    read = lambda name: pd.read_sql_query("SELECT * FROM " + name, source)
    panels = read("a_multivariate_panels")
    inputs = read("a_multivariate_inputs")
    features = read("a_multivariate_features")
    scores = read("a_pca_scores")
    loadings = read("a_pca_loadings")
    variance = read("a_pca_variance")
    corrs = read("a_correlations")
    network = read("a_similarity_edges")
    regions = read("a_regions")
    projects = read("a_project_results")
    names = dict(zip(regions.region_code, regions.region_name))
    project_names = dict(zip(projects.project_id, projects.project_name))
    checks, source_inputs = [], []

    def check(method, case, calculated, stored, tolerance=1e-9, project_id=None, detail=""):
        if calculated is None or stored is None:
            ok, error = calculated is None and stored is None, None
        else:
            aa, bb = np.asarray(calculated, dtype=float), np.asarray(stored, dtype=float)
            ok = aa.shape == bb.shape and bool(np.allclose(aa, bb, rtol=tolerance, atol=tolerance, equal_nan=True))
            error = float(np.nanmax(np.abs(aa - bb))) if aa.shape == bb.shape and aa.size and np.isfinite(aa - bb).any() else None
        checks.append(dict(method=method, case=case, project_id=project_id, status="PASS" if ok else "FAIL", max_abs_error=error, tolerance=tolerance, n_values=int(np.size(calculated)) if calculated is not None else 0, detail=detail))

    seed_runs, seed_candidates, seed_labels = [], [], []
    outlier_runs, outlier_members, outlier_stability = [], [], []
    feature_rows, feature_labels, temporal, temporal_inputs, temporal_candidates = [], [], [], [], []
    summaries, availability = [], []
    matrices = {}
    for panel in panels.to_dict("records"):
        project = panel["project_id"]
        if panel["status"] != "computed":
            availability.append(dict(project_id=project, method="regional_robustness", status="not_applicable_to_available_input", reason=panel["status"], n_regions=0, n_features=0, source_table="a_multivariate_panels"))
            continue
        pid = panel["panel_id"]
        ip = inputs[inputs.panel_id == pid]
        raw = ip.pivot(index="region_code", columns="slice_id", values="raw_value").sort_index().sort_index(axis=1)
        used = ip.pivot(index="region_code", columns="slice_id", values="used_value").reindex(index=raw.index, columns=raw.columns)
        zs = ip.pivot(index="region_code", columns="slice_id", values="z").reindex(index=raw.index, columns=raw.columns)
        z = scaled(used.to_numpy())
        stored_score = scores[scores.panel_id == pid].set_index("region_code").loc[raw.index]
        ref_labels = stored_score.cluster.to_numpy(dtype=int)
        kref = int(panel["k"])
        ff = features[features.panel_id == pid].set_index("slice_id").loc[raw.columns]
        matrix_digest = json_hash({"regions": raw.index.tolist(), "features": raw.columns.tolist(), "raw": raw.to_numpy(), "used": used.to_numpy()})
        matrices[pid] = {"input_sha256": matrix_digest, "regions": raw.index.tolist(), "features": raw.columns.tolist()}
        for r in ip.to_dict("records"):
            source_inputs.append({"project_id": project, **r, "input_sha256": matrix_digest})
        check("standardization", pid, z, zs.to_numpy(), project_id=project)
        check("medians", pid, raw.median().to_numpy(), ff.imputation_median.to_numpy(), project_id=project)
        check("imputation", pid, raw.fillna(raw.median()).to_numpy(), used.to_numpy(), project_id=project)
        check("standardization_mean", pid, used.mean().to_numpy(), ff["mean"].to_numpy(), project_id=project)
        check("standardization_scale", pid, used.std(ddof=0).to_numpy(), ff.scale.to_numpy(), project_id=project)
        pca, pcs = pca_scores(z)
        vv = variance[variance.panel_id == pid].sort_values("component")
        check("pca_variance", pid, pca.explained_variance_ratio_, vv.explained_variance_ratio.to_numpy(), project_id=project)
        ll = loadings[loadings.panel_id == pid].pivot(index="slice_id", columns="component", values="eigenvector_coefficient").loc[raw.columns]
        reconstruction = (z - z.mean(axis=0)) @ ll.to_numpy()
        check("pca_scores_algebra", pid, reconstruction[:, :2], stored_score[["pc1", "pc2"]].to_numpy(), project_id=project)
        # Algebraic eigenvector test is independent of sklearn's PCA refit.
        cov = np.cov(z, rowvar=False, ddof=1)
        eig = np.linalg.eigvalsh(cov)[::-1]
        check("pca_eigenvalues", pid, eig[:len(vv)] / eig.sum(), vv.explained_variance_ratio.to_numpy(), project_id=project)
        pcor = corrs[corrs.panel_id == pid].copy()
        prs, pps, srs, sps, sizes = [], [], [], [], []
        for row in pcor.to_dict("records"):
            pair = raw[[row["slice_id_1"], row["slice_id_2"]]].dropna().to_numpy()
            x, y = pair[:, 0], pair[:, 1]
            xc, yc = x - x.mean(), y - y.mean()
            r = float(np.sum(xc * yc) / np.sqrt(np.sum(xc * xc) * np.sum(yc * yc)))
            xr, yr = rankdata(x), rankdata(y)
            xr, yr = xr - xr.mean(), yr - yr.mean()
            sr = float(np.sum(xr * yr) / np.sqrt(np.sum(xr * xr) * np.sum(yr * yr)))
            prs.append(r); srs.append(sr); sizes.append(len(pair))
            pps.append(float(pearsonr(x, y).pvalue)); sps.append(float(spearmanr(x, y).pvalue))
        for label, got, col in [("pearson_formula", prs, "pearson_r"), ("spearman_rank_formula", srs, "spearman_r"), ("correlation_n", sizes, "n_regions"), ("pearson_p", pps, "pearson_p"), ("spearman_p", sps, "spearman_p"), ("pearson_bh", independent_bh(pps), "pearson_q_bh"), ("spearman_bh", independent_bh(sps), "spearman_q_bh")]:
            check(label, pid, got, pcor[col].to_numpy(), project_id=project)
        # Weight equality for every preserved edge; no re-labelling of communities.
        pn = network[network.panel_id == pid]
        pos = {rid: i for i, rid in enumerate(raw.index)}
        weights = [float(np.exp(-0.5 * np.mean((z[pos[r.region_code_1]] - z[pos[r.region_code_2]]) ** 2))) for r in pn.itertuples()]
        check("similarity_edge_weight", pid, weights, pn.similarity.to_numpy(), project_id=project)
        best_k, labels42, silhouette42, candidates42, _ = select_clusters(z, 42)
        check("cluster_selected_k", pid, best_k, kref, project_id=project)
        check("cluster_labels", pid, adjusted_rand_score(ref_labels, labels42), 1.0, project_id=project)
        check("cluster_silhouette", pid, silhouette42, panel["silhouette"] if pd.notna(panel["silhouette"]) else None, project_id=project)
        flag_arrays = []
        for seed in SEEDS:
            selected_k, labels, sil, candidates, fitted = select_clusters(z, seed)
            fixed = fitted.get(kref)
            fixed_min = int(np.bincount(fixed.labels_, minlength=kref).min()) if fixed is not None else None
            fixed_ari = float(adjusted_rand_score(ref_labels, fixed.labels_ + 1)) if fixed is not None else None
            ari = float(adjusted_rand_score(ref_labels, labels)) if kref >= 2 and selected_k >= 2 else None
            seed_runs.append(dict(project_id=project, panel_id=pid, seed=seed, baseline_k=kref, selected_k=selected_k, silhouette=sil, ari_selected_vs_baseline=ari, ari_fixed_k_vs_baseline=fixed_ari, fixed_k_min_cluster_size=fixed_min, fixed_k_eligible=fixed_min >= 3 if fixed_min is not None else None, status="computed" if selected_k else "no_partition_meets_minimum_size", n_regions=len(z), n_features=z.shape[1], input_sha256=matrix_digest))
            seed_candidates.extend(dict(project_id=project, panel_id=pid, seed=seed, **row) for row in candidates)
            seed_labels.extend(dict(project_id=project, panel_id=pid, seed=seed, region_code=rid, baseline_cluster=int(ref_labels[i]), cluster=int(labels[i]), fixed_k_cluster=int(fixed.labels_[i]) + 1 if fixed is not None else None) for i, rid in enumerate(raw.index))
            forest = IsolationForest(n_estimators=200, contamination=.15, random_state=seed).fit(z)
            out_score = -forest.score_samples(z)
            flag = forest.predict(z) == -1
            flag_arrays.append(flag)
            ref_flag = stored_score.is_outlier.to_numpy(dtype=bool)
            union = int(np.sum(flag | ref_flag))
            jaccard = float(np.sum(flag & ref_flag) / union) if union else 1.0
            rho = float(spearmanr(out_score, stored_score.outlier_score.to_numpy()).statistic)
            outlier_runs.append(dict(project_id=project, panel_id=pid, seed=seed, n_regions=len(z), n_flagged=int(flag.sum()), jaccard_vs_seed42=jaccard, rank_spearman_vs_seed42=rho, contamination=.15, n_estimators=200))
            outlier_members.extend(dict(project_id=project, panel_id=pid, seed=seed, region_code=rid, outlier_score=float(out_score[i]), flagged=int(flag[i])) for i, rid in enumerate(raw.index))
            if seed == 42:
                check("isolation_score_refit", pid, out_score, stored_score.outlier_score.to_numpy(), project_id=project)
                check("isolation_flag_refit", pid, flag.astype(int), ref_flag.astype(int), project_id=project)
        counts = np.sum(np.array(flag_arrays), axis=0)
        outlier_stability.extend(dict(project_id=project, panel_id=pid, region_code=rid, region_name=names.get(rid), n_flagged_runs=int(counts[i]), n_runs=len(SEEDS), algorithmic_flag_fraction=float(counts[i] / len(SEEDS)), baseline_flag=int(stored_score.is_outlier.iloc[i]), interpretation="Доля меток при смене seed; не вероятность ошибки или риска региона") for i, rid in enumerate(raw.index))
        for omit in raw.columns:
            kept = [c for c in raw.columns if c != omit]
            if len(kept) < 2:
                feature_rows.append(dict(project_id=project, panel_id=pid, omitted_slice_id=omit, status="fewer_than_two_remaining_features"))
                continue
            znew = z[:, [list(raw.columns).index(c) for c in kept]]
            k, labels, sil, _, fits = select_clusters(znew, 42)
            pn_new, pc_new = pca_scores(znew)
            angle, overlap = score_subspace(pcs, pc_new)
            fixed = fits.get(kref)
            fixed_min = int(np.bincount(fixed.labels_, minlength=kref).min()) if fixed is not None else None
            feature_rows.append(dict(project_id=project, panel_id=pid, omitted_slice_id=omit, omitted_source_id=ff.loc[omit, "source_id"], omitted_indicator_codes=ff.loc[omit, "indicator_codes"], status="computed", n_regions=len(z), n_features_remaining=len(kept), baseline_k=kref, selected_k=k, silhouette=sil, ari_selected_vs_baseline=float(adjusted_rand_score(ref_labels, labels)) if kref >= 2 and k >= 2 else None, ari_fixed_k_vs_baseline=float(adjusted_rand_score(ref_labels, fixed.labels_ + 1)) if fixed is not None else None, fixed_k_min_cluster_size=fixed_min, fixed_k_eligible=fixed_min >= 3 if fixed_min is not None else None, pc12_variance=float(pn_new.explained_variance_ratio_[:2].sum()), pc12_max_principal_angle_degrees=angle, pc12_subspace_overlap=overlap))
            feature_labels.extend(dict(project_id=project, panel_id=pid, omitted_slice_id=omit, region_code=rid, cluster=int(labels[i]), fixed_k_cluster=int(fixed.labels_[i]) + 1 if fixed is not None else None) for i, rid in enumerate(raw.index))
        # Compare the nearest earlier strictly same-frequency observation period.
        placeholders = ",".join("?" for _ in raw.columns)
        history = pd.read_sql_query(f"SELECT slice_id,region_code,period_end,value,observation_key,source_id FROM a_observations WHERE analysis_status='usable' AND region_code IS NOT NULL AND slice_id IN ({placeholders}) AND period_end<=?", source, params=[*raw.columns, panel["period_end"]])
        if history.duplicated(["slice_id", "region_code", "period_end"]).any():
            raise ValueError("Duplicate regional period in temporal robustness input: " + pid)
        current = raw.dropna()
        matched = False
        earlier_dates = [date for date in sorted(history.period_end.unique(), reverse=True) if date < panel["period_end"]]
        max_common = 0
        for date in earlier_dates:
            if date >= panel["period_end"]:
                continue
            previous = history[history.period_end == date].pivot(index="region_code", columns="slice_id", values="value").reindex(columns=raw.columns).dropna()
            shared = sorted(set(current.index) & set(previous.index))
            max_common = max(max_common, len(shared))
            if len(shared) < 20:
                temporal_candidates.append(dict(project_id=project, panel_id=pid, previous_period=date, n_complete_common_regions=len(shared), status="fewer_than_20_complete_common_regions"))
                continue
            a, b = previous.loc[shared].to_numpy(), current.loc[shared].to_numpy()
            if np.any(np.std(a, axis=0) <= 1e-12) or np.any(np.std(b, axis=0) <= 1e-12):
                temporal_candidates.append(dict(project_id=project, panel_id=pid, previous_period=date, n_complete_common_regions=len(shared), status="constant_feature_in_one_period"))
                continue
            za, zb = scaled(a), scaled(b)
            ka, la, sila, _, fitsa = select_clusters(za, 42)
            kb, lb, silb, _, fitsb = select_clusters(zb, 42)
            pa, ca = pca_scores(za); pb, cb = pca_scores(zb)
            angle, overlap = score_subspace(ca, cb)
            min_a = int(np.bincount(fitsa[kref].labels_, minlength=kref).min()) if kref >= 2 else None
            min_b = int(np.bincount(fitsb[kref].labels_, minlength=kref).min()) if kref >= 2 else None
            temporal.append(dict(project_id=project, panel_id=pid, status="computed", previous_period=date, current_period=panel["period_end"], frequency=panel["frequency"], n_regions=len(shared), n_features=len(raw.columns), n_imputed_cells=0, n_prior_periods=len(earlier_dates), previous_k=ka, current_k=kb, previous_silhouette=sila, current_silhouette=silb, ari_selected=float(adjusted_rand_score(la, lb)) if ka >= 2 and kb >= 2 else None, fixed_k=kref if kref >= 2 else None, ari_fixed_k=float(adjusted_rand_score(fitsa[kref].labels_, fitsb[kref].labels_)) if kref >= 2 else None, fixed_k_previous_min_cluster_size=min_a, fixed_k_current_min_cluster_size=min_b, fixed_k_eligible_both=min_a >= 3 and min_b >= 3 if kref >= 2 else None, pc12_max_principal_angle_degrees=angle, pc12_subspace_overlap=overlap, interpretation="Одинаковые территории и признаки без импутации; различия могут отражать реальную динамику, не только нестабильность метода"))
            temporal_candidates.append(dict(project_id=project, panel_id=pid, previous_period=date, n_complete_common_regions=len(shared), status="selected_nearest_eligible_period"))
            for date2, xx, zz, labels, fits in [(date, a, za, la, fitsa), (panel["period_end"], b, zb, lb, fitsb)]:
                keyrows = history[(history.period_end == date2) & history.region_code.isin(shared)].set_index(["region_code", "slice_id"])
                for i, rid in enumerate(shared):
                    for j, sid in enumerate(raw.columns):
                        row = keyrows.loc[(rid, sid)]
                        temporal_inputs.append(dict(project_id=project, panel_id=pid, period_end=date2, region_code=rid, slice_id=sid, source_id=row.source_id, observation_key=row.observation_key, raw_value=float(xx[i, j]), z=float(zz[i, j]), cluster=int(labels[i]), fixed_k_cluster=int(fits[kref].labels_[i]) + 1 if kref >= 2 else None))
            matched = True
            break
        if not matched:
            temporal.append(dict(project_id=project, panel_id=pid, status="no_earlier_period" if not earlier_dates else "no_eligible_earlier_complete_panel", current_period=panel["period_end"], frequency=panel["frequency"], n_features=len(raw.columns), n_prior_periods=len(earlier_dates), max_prior_common_complete_regions=max_common, reason="Нет более раннего периода для исходных признаков в собранном массиве" if not earlier_dates else "Требуются >=20 общих полных регионов, все исходные признаки и ненулевая дисперсия обоих периодов"))
        availability.append(dict(project_id=project, method="regional_robustness", status="computed", reason="same input matrix; original data preserved", n_regions=len(z), n_features=z.shape[1], source_table="a_multivariate_inputs"))
        summaries.append(dict(project_id=project, project_name=project_names[project], panel_id=pid, frequency=panel["frequency"], period_end=panel["period_end"], n_regions=len(z), n_features=z.shape[1], n_imputed_cells=int(raw.isna().sum().sum()), baseline_k=kref, n_seed_runs=len(SEEDS), n_feature_omissions=len(raw.columns), input_sha256=matrix_digest))
        print(json.dumps({"project": project, "status": "completed", "regions": len(z), "features": z.shape[1]}, ensure_ascii=False), flush=True)

    # Spatial audit of all preserved global statistics and all local algebra/BH.
    snaps = read("a_regional_snapshots")
    gl = read("a_moran_global")
    loc = read("a_moran_local")
    ed = read("a_spatial_weights")
    edge_pairs = list(zip(ed.region_code_1, ed.region_code_2))
    for row in gl.to_dict("records"):
        sid = row["slice_id"]
        s = snaps[snaps.slice_id == sid].sort_values("region_code")
        ids = s.region_code.tolist(); index = {rid: i for i, rid in enumerate(ids)}
        adjacency = np.zeros((len(ids), len(ids)), dtype=float)
        for aa, bb in edge_pairs:
            if aa in index and bb in index:
                adjacency[index[aa], index[bb]] = adjacency[index[bb], index[aa]] = 1
        degree = adjacency.sum(axis=1)
        w = np.divide(adjacency, degree[:, None], out=np.zeros_like(adjacency), where=degree[:, None] > 0)
        x = s.value.to_numpy(); z = x - x.mean(); n = len(x)
        numerator = sum(float(w[i, j] * z[i] * z[j]) for i in range(n) for j in np.flatnonzero(w[i]))
        result = float(n / w.sum() * numerator / np.sum(z * z))
        check("moran_global_formula", sid, result, row["moran_I"])
        check("moran_islands", sid, int(np.sum(degree == 0)), row["n_islands"])
        zstd = z / np.sqrt(np.mean(z * z)); lag = w @ zstd
        local = loc[loc.slice_id == sid].set_index("region_code").loc[ids]
        check("lisa_algebra", sid, np.column_stack([zstd, lag, zstd * lag]), local[["z", "lag", "local_I"]].to_numpy())
        check("lisa_bh", sid, independent_bh(local.p_value.tolist()), local.q_bh.to_numpy())
        expected_class = []
        for i, (_, rr) in enumerate(local.iterrows()):
            quad = ("H" if zstd[i] >= 0 else "L") + ("H" if lag[i] >= 0 else "L")
            expected_class.append(quad if pd.notna(rr.q_bh) and rr.q_bh <= .05 else ("ISLAND" if degree[i] == 0 else "NS"))
        check("lisa_classification", sid, sum(a != b for a, b in zip(expected_class, local.lisa_class)), 0)
    check("moran_global_bh", "all_122_or_current_n", independent_bh(gl.p_permutation.tolist()), gl.q_bh.to_numpy())

    # Store all new diagnostics and their exact input subset.
    tables = {
        "panel_summary": summaries, "availability": availability,
        "baseline_inputs": source_inputs, "baseline_features": features,
        "baseline_panels": panels, "verification": checks,
        "cluster_seed_runs": seed_runs, "cluster_seed_candidates": seed_candidates,
        "cluster_seed_memberships": seed_labels, "outlier_seed_runs": outlier_runs,
        "outlier_seed_memberships": outlier_members, "outlier_stability": outlier_stability,
        "feature_sensitivity": feature_rows, "feature_memberships": feature_labels,
        "temporal_comparison": temporal, "temporal_candidates": temporal_candidates,
        "temporal_inputs": temporal_inputs,
    }
    frames = {name: out.table(name, data) for name, data in tables.items()}
    out.con.commit()
    integrity = out.con.execute("PRAGMA quick_check").fetchone()[0]
    out.con.close(); source.close()
    after = sha256_file(db)
    failures = [r for r in checks if r["status"] != "PASS"]
    summary = {
        "version": VERSION, "module": "quantitative_robustness_and_independent_checks",
        "source_database": "outputs/national_projects_analytics.sqlite", "source_sha256": before,
        "source_unchanged": before == after, "family_reference_commit": FAMILY_SHA,
        "family_method_reference": FAMILY_URL + "#L45-L61",
        "seed_values": SEEDS, "minimum_cluster_size": 3, "k_candidates": [2, 3, 4, 5, 6],
        "kmeans_n_init": 20, "isolation_forest_estimators": 200, "isolation_contamination": .15,
        "panels_computed": len(summaries), "projects_without_input": sum(r["status"] != "computed" for r in availability),
        "regional_profiles": len(outlier_stability), "cluster_seed_runs": len(seed_runs),
        "feature_exclusion_runs": len(feature_rows), "temporal_comparisons": len(temporal),
        "temporal_computed": sum(r["status"] == "computed" for r in temporal),
        "verification_cases": len(checks), "verification_failed": len(failures),
        "checks_scope": "All preserved regional input matrices, 509 correlation pairs, PCA algebra/variance, 1493 edge weights, 122 global Moran and 10243 local values/BH. Stored permutation p-values are not independently re-simulated.",
        "sqlite_quick_check": integrity, "tables": out.tables,
        "environment": {"python": platform.python_version(), **{name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "threadpoolctl"]}},
        "interpretation": "Stability across prescribed computational perturbations. No causal policy effect, probability of success, or ranking of government performance.",
    }
    write_json(out.root / "summary.json", summary)
    write_json(out.root / "input_matrices.json", matrices)
    write_json(out.root / "verification.json", {"passed": not failures and before == after and integrity == "ok", "cases": len(checks), "failures": failures, "source_unchanged": before == after, "sqlite_quick_check": integrity, "permutation_p_values_resimulated": False})
    write_methods(out.root, summary, frames)
    if make_figures:
        figures(out.root, frames, project_names)
    if failures or before != after or integrity != "ok":
        raise RuntimeError(f"Quantitative checks failed: {len(failures)} failures, source_unchanged={before == after}")
    return summary


def write_methods(out, summary, frames):
    rows = []
    for r in frames["panel_summary"].to_dict("records"):
        pid = r["panel_id"]
        seed = frames["cluster_seed_runs"].query("panel_id == @pid")
        feature = frames["feature_sensitivity"].query("panel_id == @pid")
        outlier = frames["outlier_seed_runs"].query("panel_id == @pid")
        seed_valid = seed[seed.fixed_k_eligible == True]
        feature_valid = feature[feature.fixed_k_eligible == True]
        def val(x):
            return "не определено" if pd.isna(x) else f"{x:.3f}"
        seed_count = f"{len(seed_valid)}/{len(seed)}" if r["baseline_k"] else "не применимо"
        feature_count = f"{len(feature_valid)}/{len(feature)}" if r["baseline_k"] else "не применимо"
        rows.append(f"| {r['project_name']} | {r['n_regions']} | {r['n_features']} | {r['baseline_k'] or 'не принято'} | {seed_count} | {val(seed_valid.ari_fixed_k_vs_baseline.min())} | {feature_count} | {val(feature_valid.ari_fixed_k_vs_baseline.min())} | {val(outlier.jaccard_vs_seed42.min())} |")
    text = f"""# Количественная воспроизводимость и устойчивость, выпуск 1.2.0

## Объём выполненной работы

Исходные расчёты 1.1.0 сохранены без изменения. Их база имеет SHA-256 `{summary['source_sha256']}`. Проверено {summary['verification_cases']} групп арифметических и структурных условий, ошибок – {summary['verification_failed']}. Новые диагностические расчёты выполнены для {summary['panels_computed']} сопоставимых панелей и {summary['regional_profiles']} региональных профилей. Для пяти проектов отсутствие допустимого входа зафиксировано в `q_availability`, без подстановки синтетических значений.

Эталон – [методика портала «Семья»]({FAMILY_URL}), commit `{FAMILY_SHA}`. Раздел «Стандартизация и k-means» прямо различает детерминированное повторение и проверку нескольких стартов, признаков и периодов. Основные PCA, k-means, Isolation Forest, корреляции, Moran/LISA и сети сходства уже были рассчитаны в 1.1.0. Новый модуль закрывает проверку устойчивости и независимую арифметическую сверку.

В репозитории «Семьи» различаются архивный и обновляемый расчётные слои. [Обновляемый слой]({FAMILY_URL.replace('documentation/METHODS.md', 'scripts/build_current_analytics.py')}) использует четыре признака последних доступных периодов, полные случаи, фиксированное k=3, 100 деревьев Isolation Forest и положительную косинусную близость в сети аналогов. Общий комплект 1.1.0 использует один период и частоту внутри панели, медианное заполнение с явной маской, выбор k=2–6, 200 деревьев и близость exp(−среднее квадратов различий/2). Новая версия сохраняет эти опубликованные правила общего комплекта. Сопоставимость классов методов не означает тождества настроек и числовых результатов.

## Правила проверки

PCA и типологии используют сохранённые матрицы одного периода и одной частоты. Остаточные пропуски заполняются сохранённой медианой только внутри профильной матрицы. Маска заполнений и исходные значения включены в `q_baseline_inputs`. Корреляции повторно проверены только по наблюдаемым парным значениям. Pearson вычислен также явной формулой, Spearman – через средние ранги. Значения p проверены SciPy, поправка Benjamini–Hochberg – независимой списочной реализацией.

Проверены средние, масштабы, медианы, заполнения, алгебра координат PCA, собственные значения ковариационной матрицы и веса всех рёбер сходства. Для глобального Moran I независимо пересчитана сумма по реальным соседним парам. Для LISA проверены стандартизация, пространственный лаг, локальная статистика, поправка BH и категория. Перестановочные p повторно не моделировались. Такая граница проверки явно сохранена в `verification.json`.

## Новая проверка устойчивости

Для каждого из семи seed `{', '.join(map(str, SEEDS))}` повторно выполнены k-means с 20 инициализациями и выбор k=2–6 по силуэту при минимуме три региона в группе. Сохранены все кандидаты, выбранные разбиения и индекс Rand с поправкой на случайное совпадение (ARI). Отдельно рассчитан ARI при фиксированном исходном k. Номер кластера не интерпретируется как порядок качества. Отсутствие допустимого разбиения сохраняется как результат.

В подробных таблицах сохранены также диагностические ARI фиксированного k для разбиений с группой меньше трёх регионов. Поля `fixed_k_min_cluster_size`, `fixed_k_eligible` и временное `fixed_k_eligible_both` отделяют их от допустимых типологий. Сводная таблица и рисунок ARI используют только допустимые варианты и одновременно показывают их число. Высокий ARI среди немногих прошедших вариантов не означает устойчивость всей процедуры.

Для Isolation Forest повторены 200 деревьев и contamination=0,15 с каждым seed. Сохранены коэффициент Spearman между оценками нетипичности, пересечение меток по Жаккару и частота метки у каждого региона. Частота метки отражает алгоритмическую чувствительность, не вероятность реальной ошибки или риска.

Каждый исходный признак поочерёдно исключён. Для оставшихся признаков пересчитаны PCA и кластеризация. Изменение двухмерного пространства PCA описано наибольшим главным углом и долей перекрытия подпространств координат регионов. Значение перекрытия находится от 0 до 1 и не является вероятностью.

Временная проверка выбирает ближайший более ранний пригодный период той же частоты. Сравниваются строго одинаковые признаки и общий набор не менее 20 регионов с полными реальными значениями в обоих периодах. Импутации нет. Все столбцы должны иметь ненулевую дисперсию. Оба периода стандартизуются отдельно. Такая проверка объединяет чувствительность к дате и действительную динамику, поэтому снижение ARI нельзя автоматически считать ошибкой метода.

## Основные числовые результаты

| Проект | Регионов | Признаков | Исходное k | Допустимых seed при исходном k | Минимум ARI среди допустимых seed | Допустимых исключений признака при исходном k | Минимум ARI среди допустимых исключений | Минимум Жаккара меток Isolation Forest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Воспроизведение

Из корня распакованного комплекта:

```bash
python research/quantitative_analysis.py --output outputs/research/quantitative_rebuilt
```

Все входы читаются локально. Код не обращается к внешним API. Для нового каталога создаются SQLite, CSV, JSON и рисунки SVG/PNG. Исходная SQLite открывается только для чтения, контрольная сумма проверяется до и после расчёта. Версии библиотек записаны в `summary.json`. Временные и вычислительные статусы не подменяют содержательную экспертизу причинных механизмов и качества государственной политики.
"""
    (out / "METHODS_AND_RESULTS_RU.md").write_text(text, encoding="utf-8")


def figures(out, frames, names):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 10, "svg.fonttype": "none"})
    short = {"family": "Семья", "long_active_life": "Продолжительная\nи активная жизнь", "life_infrastructure": "Инфраструктура для жизни", "environment": "Экологическое благополучие", "data_economy": "Экономика данных\nи цифровая трансформация", "competitive_economy": "Эффективная\nи конкурентная экономика"}
    figdir = out / "figures"; figdir.mkdir(exist_ok=True)
    eligible = frames["feature_sensitivity"]
    eligible = eligible[eligible.fixed_k_eligible == True]
    data = eligible.groupby("project_id").agg(min_ari=("ari_fixed_k_vs_baseline", "min"), median_ari=("ari_fixed_k_vs_baseline", "median"))
    data = data.dropna().sort_values("min_ari")
    if len(data):
        fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
        y = np.arange(len(data))
        ax.barh(y - .16, data.min_ari, height=.3, label="Минимум ARI", color="#2b6b8a")
        ax.barh(y + .16, data.median_ari, height=.3, label="Медиана ARI", color="#75a49e")
        all_counts = frames["feature_sensitivity"].groupby("project_id").size()
        valid_counts = eligible.groupby("project_id").size()
        labels = [short.get(p, names[p]) + f"\n(допустимо {valid_counts[p]} из {all_counts[p]})" for p in data.index]
        ax.set_yticks(y, labels); ax.set_xlim(-.1, 1.05)
        ax.set_xlabel("ARI при исключении одного признака, фиксированное k\nТолько разбиения с группами не меньше трёх регионов")
        ax.axvline(0, color="black", lw=.7); ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.02), frameon=False, ncol=2)
        for ext in ["svg", "png"]:
            fig.savefig(figdir / ("cluster_feature_sensitivity." + ext), dpi=180, bbox_inches="tight")
        plt.close(fig)
    data = frames["outlier_seed_runs"].groupby("project_id").jaccard_vs_seed42.agg(["min", "median"]).sort_values("min")
    if len(data):
        fig, ax = plt.subplots(figsize=(10, 5.8), constrained_layout=True)
        y = np.arange(len(data))
        ax.barh(y - .16, data["min"], height=.3, label="Минимум среди семи seed", color="#2b6b8a")
        ax.barh(y + .16, data["median"], height=.3, label="Медиана среди семи seed", color="#75a49e")
        ax.set_yticks(y, [short.get(p, names[p]) for p in data.index]); ax.set_xlim(0, 1.05)
        ax.set_xlabel("Индекс Жаккара меток нетипичности относительно seed=42")
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(loc="lower center", bbox_to_anchor=(.5, 1.02), frameon=False, ncol=2)
        for ext in ["svg", "png"]:
            fig.savefig(figdir / ("isolation_forest_seed_sensitivity." + ext), dpi=180, bbox_inches="tight")
        plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--output", type=Path)
    p.add_argument("--skip-figures", action="store_true")
    args = p.parse_args()
    root = args.package_root.resolve()
    target = args.output or root / "outputs/research/quantitative"
    if not target.is_absolute():
        target = root / target
    with threadpool_limits(limits=1):
        result = build(root, target, make_figures=not args.skip_figures)
    print(json.dumps(clean(result), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
