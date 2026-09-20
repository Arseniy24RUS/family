"""Monthly diagnostic TFR ensemble with data-conditioned, regularised curvature.

Five model specifications, including harmonic regression and a quasi-periodic GP.
The 12-month kernel period is a declared calendar hypothesis, NOT a detected cycle.
Observed cells are never smoothed, fabricated, interpolated, or mixed with annual rows.
New model of the platform; the original May 2026 report remains a separate artefact.

Kernel construction: Rasmussen & Williams (2006), Gaussian Processes for Machine Learning,
chapters 2 and 4; https://gaussianprocess.org/gpml/chapters/.
Fourier terms: Hyndman & Athanasopoulos, Forecasting: Principles and Practice, ch. 10.
"""
from __future__ import annotations
import calendar
import hashlib
import json
import math
from datetime import date
import numpy as np
from .indicator_v11 import path as baseline_path

VERSION = 'monthly-nonlinear-ensemble/1.2.0'
MODELS = ('last', 'local_damped', 'holt_damped', 'harmonic_ridge', 'quasiperiodic_gp')
NAMES = {
    'last': 'Последнее значение',
    'local_damped': 'Локальный затухающий тренд',
    'holt_damped': 'Затухающий тренд Холта',
    'harmonic_ridge': 'Тренд + регуляризованная гармоника',
    'quasiperiodic_gp': 'Тренд + квазипериодический гауссовский процесс',
}
PARAMETERS = {
    'minimum_training': 6, 'validation_horizons': [1, 3],
    'maximum_training_months': 120, 'maximum_validation_origins': 24,
    'calendar_period_months': 12, 'minimum_calendar_training': 12,
    'harmonic_ridge_penalty': 2.0, 'harmonic_anchor_decay_months': 3.0,
    'gp_periodic_length_scale': 0.9, 'gp_cycle_coherence_months': 48.0,
    'gp_local_length_months': 2.5, 'gp_local_variance_ratio': 0.4,
    'gp_noise_variance_ratio': 0.2, 'gp_nugget_variance': 1e-8,
    'gp_mean_estimation': 'generalized_least_squares',
    'gp_mean_uncertainty': True,
    'minimum_residual_scale': 1e-4, 'weight_floor_share': 0.05,
    'baseline_specification': 'monthly-log-ensemble/1.1.1',
}


def month_id(value):
    d = date.fromisoformat(str(value)[:10])
    return d.year * 12 + d.month - 1


def end_month(n):
    y, m = divmod(n, 12)
    m += 1
    return f'{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def _linear(y):
    t = np.arange(len(y), dtype=float) - (len(y) - 1) / 2
    slope = float(t @ (y - y.mean()) / (t @ t)) if len(y) > 1 else 0.0
    return float(y.mean()), slope, t


def _model(y, horizon, method):
    """Return the conditional log path and its additive components; no future data."""
    y = np.asarray(y[-PARAMETERS['maximum_training_months']:], dtype=float)
    n = len(y)
    future = np.arange(n, n + horizon, dtype=float) - (n - 1) / 2
    steps = np.arange(1, horizon + 1, dtype=float)
    zero = np.zeros(horizon)
    active = n >= PARAMETERS['minimum_calendar_training']
    if method in MODELS[:3]:
        p = np.asarray(baseline_path(y.tolist(), horizon, method))
        return dict(path=p, trend=p, cycle=zero, local=zero, variance=zero,
                    fit=None, meta={'calendar_active': False, 'training_months': n})
    level, slope, t = _linear(y)
    trend = level + slope * future
    if method == 'harmonic_ridge':
        if not active:
            # A fully specified fallback: no harmonic is estimated on a partial year.
            p = y[-1] + slope * steps
            return dict(path=p, trend=p, cycle=zero, local=zero, variance=zero,
                        fit=level + slope * t,
                        meta={'calendar_active': False, 'training_months': n,
                              'fallback': 'log-linear path anchored at last observation'})
        def design(x):
            phase = 2 * np.pi * x / PARAMETERS['calendar_period_months']
            return np.column_stack([np.ones(len(x)), x, np.sin(phase), np.cos(phase)])
        X = design(t)
        penalty = np.diag([0., 0., PARAMETERS['harmonic_ridge_penalty'],
                           PARAMETERS['harmonic_ridge_penalty']])
        beta = np.linalg.solve(X.T @ X + penalty, X.T @ y)
        fit = X @ beta
        A = design(future)
        trend = A[:, :2] @ beta[:2]
        cycle = A[:, 2:] @ beta[2:]
        local = (y[-1] - fit[-1]) * np.exp(-steps / PARAMETERS['harmonic_anchor_decay_months'])
        return dict(path=trend + cycle + local, trend=trend, cycle=cycle, local=local,
                    variance=zero, fit=fit,
                    meta={'calendar_active': True, 'training_months': n,
                          'coefficients_log': beta.tolist(),
                          'amplitude_log': float(np.hypot(beta[2], beta[3])),
                          'period_months': PARAMETERS['calendar_period_months'],
                          'period_status': 'assumed, not estimated'})
    if method != 'quasiperiodic_gp':
        raise ValueError('Неизвестная модель: ' + method)
    residual = y - (level + slope * t)
    scale = max(float(np.std(residual)), PARAMETERS['minimum_residual_scale'])

    def kernels(x, z):
        delta = np.subtract.outer(x, z)
        period = PARAMETERS['calendar_period_months']
        cyc = np.exp(-2 * np.sin(np.pi * delta / period) ** 2 /
                     PARAMETERS['gp_periodic_length_scale'] ** 2)
        cyc *= np.exp(-0.5 * (delta / PARAMETERS['gp_cycle_coherence_months']) ** 2)
        if not active:
            cyc[:] = 0
        local = PARAMETERS['gp_local_variance_ratio'] * np.exp(
            -0.5 * (delta / PARAMETERS['gp_local_length_months']) ** 2)
        return scale ** 2 * cyc, scale ** 2 * local

    Kc, Kl = kernels(t, t)
    noise = scale ** 2 * PARAMETERS['gp_noise_variance_ratio'] + PARAMETERS['gp_nugget_variance']
    L = np.linalg.cholesky(Kc + Kl + np.eye(n) * noise)
    # Jointly estimate the linear mean with the covariance, so a calendar pattern
    # is not mechanically absorbed into the slope of the extrapolated trend.
    A = np.column_stack([np.ones(n), t])
    Af = np.column_stack([np.ones(horizon), future])
    invA = np.linalg.solve(L.T, np.linalg.solve(L, A))
    invY = np.linalg.solve(L.T, np.linalg.solve(L, y))
    precision_beta = A.T @ invA
    beta = np.linalg.solve(precision_beta, A.T @ invY)
    level, slope = map(float, beta)
    trend = Af @ beta
    residual = y - A @ beta
    alpha = np.linalg.solve(L.T, np.linalg.solve(L, residual))
    Fc, Fl = kernels(future, t)
    cycle = Fc @ alpha
    local = Fl @ alpha
    fit = level + slope * t + (Kc + Kl) @ alpha
    # Smooth endpoint correction is estimated from the final residual, never drawn by hand.
    local += (y[-1] - fit[-1]) * np.exp(-steps / PARAMETERS['gp_local_length_months'])
    solved = np.linalg.solve(L, (Fc + Fl).T)
    prior_diag = scale ** 2 * (int(active) + PARAMETERS['gp_local_variance_ratio'])
    mean_design_residual = Af - (Fc + Fl) @ invA
    mean_variance = np.einsum('ij,ji->i', mean_design_residual,
                             np.linalg.solve(precision_beta, mean_design_residual.T))
    variance = np.maximum(0., prior_diag - (solved ** 2).sum(axis=0) + mean_variance)
    return dict(path=trend + cycle + local, trend=trend, cycle=cycle, local=local,
                variance=variance, fit=fit,
                meta={'calendar_active': active, 'training_months': n, 'level_log': level,
                      'trend_per_month_log': slope, 'residual_scale_log': scale,
                      'period_months': PARAMETERS['calendar_period_months'],
                      'period_status': 'assumed, not estimated',
                      'cycle_coherence_months': PARAMETERS['gp_cycle_coherence_months'],
                      'mean_estimation': PARAMETERS['gp_mean_estimation']})


def path(y, horizon, method):
    """Compatibility helper for tests and isolated model inspection."""
    return _model(y, horizon, method)['path'].tolist()


def _errors_to_weights(errors):
    mse = np.array([np.mean(np.square(errors[m])) if errors[m] else np.nan for m in MODELS])
    finite = mse[np.isfinite(mse)]
    floor = max(1e-8, float(finite.mean()) * PARAMETERS['weight_floor_share']) if len(finite) else 1e-8
    raw = np.array([1 / (v + floor) if math.isfinite(v) else 1. for v in mse])
    return raw / raw.sum(), mse


def _validation(y, dates):
    """Rolling-origin validation of fixed model algorithms and prequential ensemble.

    At an ensemble origin only errors whose target was observed strictly earlier may
    enter its weights. Endpoint normalisation, regression and kernels are refit inside
    each origin. No full-series residuals or future targets enter these fits.
    """
    backtests = []
    outer = []
    first = max(PARAMETERS['minimum_training'], len(y) - PARAMETERS['maximum_validation_origins'])
    for origin in range(first, len(y)):
        H = min(max(PARAMETERS['validation_horizons']), len(y) - origin)
        before = {m: [] for m in MODELS}
        for b in backtests:
            if b['target_index'] < origin:
                before[b['model']].append(b['log_error'])
        pre_weights, _ = _errors_to_weights(before)
        predictions = {m: _model(y[:origin], H, m) for m in MODELS}
        for horizon in PARAMETERS['validation_horizons']:
            target = origin + horizon - 1
            if target >= len(y):
                continue
            logs = np.array([predictions[m]['path'][horizon - 1] for m in MODELS])
            for i, m in enumerate(MODELS):
                predicted = float(np.exp(logs[i]))
                if not math.isfinite(predicted):
                    raise ValueError('Модель нестабильна при временной проверке.')
                backtests.append({'model': m, 'train_end': dates[origin - 1],
                                  'target': dates[target], 'target_index': target,
                                  'horizon': horizon, 'observed': float(np.exp(y[target])),
                                  'predicted': predicted, 'log_error': float(logs[i] - y[target]),
                                  'calendar_active': predictions[m]['meta']['calendar_active']})
            if origin > first:
                pred = float(np.exp(pre_weights @ logs))
                outer.append({'train_end': dates[origin - 1], 'target': dates[target],
                              'horizon': horizon, 'observed': float(np.exp(y[target])),
                              'predicted': pred, 'last_value_prediction': float(np.exp(y[origin - 1])),
                              'weight_errors_end': max((b['target'] for b in backtests if b['target_index'] < origin), default=None),
                              'weights': {m: float(v) for m, v in zip(MODELS, pre_weights)}})
    return backtests, outer


def forecast(observations, end='2030-12-31'):
    obs = sorted(observations, key=lambda x: x['date'])
    if len(obs) < 6:
        raise ValueError('Для прогнозирования нужны хотя бы 6 последовательных месячных наблюдений.')
    ids = [month_id(o['date']) for o in obs]
    if len(set(ids)) != len(ids):
        raise ValueError('Дубли месячных наблюдений.')
    if any(b - a != 1 for a, b in zip(ids, ids[1:])):
        raise ValueError('Разрыв месячной сетки: заполнение или сжатие времени запрещено.')
    if any(not isinstance(o['value'], (int, float)) or isinstance(o['value'], bool) or
           not math.isfinite(o['value']) or o['value'] <= 0 for o in obs):
        raise ValueError('Нужны положительные конечные значения СКР без пропусков.')
    H = max(0, month_id(end) - ids[-1])
    y = np.log([o['value'] for o in obs])
    backtests, outer = _validation(y, [o['date'] for o in obs])
    errors = {m: [b['log_error'] for b in backtests if b['model'] == m] for m in MODELS}
    weights, mse = _errors_to_weights(errors)
    fitted = {m: _model(y, H, m) for m in MODELS}
    one_step = [math.log(b['predicted'] / b['observed']) for b in outer if b['horizon'] == 1]
    if not one_step:
        one_step = [b['log_error'] for b in backtests if b['horizon'] == 1]
    sigma = float(np.sqrt(np.mean(np.square(one_step)))) if one_step else float(np.std(np.diff(y)))
    rows = []
    for i in range(H):
        vals = np.array([fitted[m]['path'][i] for m in MODELS])
        mu = float(weights @ vals)
        spread = float(weights @ ((vals - mu) ** 2))
        gp_var = float(sum(weights[j] ** 2 * fitted[m]['variance'][i] for j, m in enumerate(MODELS)))
        se = math.sqrt((i + 1) * sigma ** 2 + spread + gp_var)
        if max(abs(mu), abs(mu + 1.96 * se), abs(mu - 1.96 * se)) > 25:
            raise ValueError('Модель вышла за численно устойчивый диапазон; результат не публикуется.')
        trend, cycle, local = [float(sum(weights[j] * fitted[m][key][i] for j, m in enumerate(MODELS)))
                               for key in ['trend', 'cycle', 'local']]
        rows.append({'date': end_month(ids[-1] + i + 1), 'value': math.exp(mu),
                     'lo80': math.exp(mu - 1.2815515655 * se), 'hi80': math.exp(mu + 1.2815515655 * se),
                     'lo95': math.exp(mu - 1.9599639845 * se), 'hi95': math.exp(mu + 1.9599639845 * se),
                     'model_min': float(np.exp(vals).min()), 'model_max': float(np.exp(vals).max()),
                     'members': {m: float(math.exp(vals[j])) for j, m in enumerate(MODELS)},
                     'trend_value': math.exp(trend), 'cycle_factor': math.exp(cycle),
                     'local_factor': math.exp(local), 'cycle_percent': math.expm1(cycle) * 100,
                     'prediction_log_sd': se})
    parameters = dict(PARAMETERS)
    fingerprint = hashlib.sha256(json.dumps({'obs': obs, 'end': end, 'version': VERSION,
                                           'parameters': parameters}, ensure_ascii=False,
                                           sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    models = []
    for j, m in enumerate(MODELS):
        b = [b for b in backtests if b['model'] == m]
        models.append({'id': m, 'name': NAMES[m], 'weight': float(weights[j]), 'n_tests': len(b),
                       'log_rmse': math.sqrt(mse[j]) if math.isfinite(mse[j]) else None,
                       'mae': float(np.mean([abs(bi['predicted'] - bi['observed']) for bi in b])) if b else None,
                       'calendar_tests': sum(bi['calendar_active'] for bi in b),
                       'fit': fitted[m]['meta']})
    mae = lambda field: float(np.mean([abs(b[field] - b['observed']) for b in outer])) if outer else None
    return {'schema': 'semya.indicator-projection/1', 'model_version': VERSION,
            'input_sha256': fingerprint, 'source_as_of': obs[-1]['date'], 'end_date': end,
            'n_observations': len(obs), 'observations': obs, 'forecast': rows, 'models': models,
            'backtest': [{k: v for k, v in b.items() if k != 'target_index'} for b in backtests],
            'ensemble_backtest': outer,
            'validation': {'kind': 'prequential, expanding origin; weights use past targets only',
                           'n_tests': len(outer), 'mae': mae('predicted'),
                           'last_value_mae': mae('last_value_prediction'), 'max_test_horizon': 3,
                           'historical_vintages_available': False},
            'parameters': parameters,
            'intervals': {'type': 'conditional_log_normal_heuristic',
                          'innovation_log_rmse': sigma, 'calibrated': False},
            'curvature': {'kind': 'estimated Fourier/GP residuals, not chart smoothing',
                          'calendar_hypothesis_months': 12,
                          'calendar_estimated': len(obs) >= 12,
                          'period_estimated': False, 'seasonality_confirmed': False,
                          'training_cycles': len(obs) / 12},
            'caveats': [
                'Новая модель платформы; не заменяет сохранённый прогноз исходной экспертизы.',
                'Помесячно опубликованный СКР — годовой по размерности коэффициент, не число детей за месяц.',
                'Годовые и накопительные строки не входят в месячное обучение. Пропуски не интерполируются.',
                'Период 12 месяцев задан как проверяемая календарная гипотеза. Один цикл не доказывает сезонность. Соседние оперативные оценки могут быть зависимы.',
                'Параметры гармоники и гауссовского процесса оцениваются по исходному ряду; наблюдения не сглаживаются. На ровном ряду искусственные колебания не создаются.',
                'Временные проверки охватывают 1 и 3 месяца. Надёжность прогноза до 2030 года ими не подтверждена; используются текущие версии прошлых значений, не архивы публикаций.',
                '80/95%-полосы — условная оценка: ошибки краткосрочной проверки, расхождение моделей и остаточная неопределённость GP. Фактическое покрытие и структурные шоки не проверены.',
                'Национальный ряд рассчитан независимо; региональные коэффициенты не усредняются в СКР России.',
            ]}
