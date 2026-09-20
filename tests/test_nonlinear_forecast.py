"""Checks of numerical provenance, no-lookahead validation and learned curvature."""
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from demography.indicator import (forecast,path,_model,_errors_to_weights,MODELS,VERSION,PARAMETERS,end_month)
from demography.indicator_v11 import forecast as legacy_forecast


def observations(n=15, start=2025, fn=None):
    fn=fn or (lambda t: 1.4*math.exp(-.0015*t+.012*math.sin(2*math.pi*t/12)))
    return [{'date':end_month(start*12+t),'value':fn(t)} for t in range(n)]


class LearnedCurvature(unittest.TestCase):
    def test_five_models_and_declared_fixed_calendar(self):
        o=forecast(observations())
        self.assertEqual(set(MODELS),set(m['id'] for m in o['models']))
        self.assertFalse(o['curvature']['seasonality_confirmed'])
        self.assertFalse(o['curvature']['period_estimated'])
        self.assertEqual(o['parameters']['calendar_period_months'],12)

    def test_input_is_unchanged(self):
        rows=observations();before=copy.deepcopy(rows);o=forecast(rows)
        self.assertEqual(rows,before);self.assertEqual(o['observations'],before)

    def test_constant_series_has_no_artificial_waves(self):
        o=forecast(observations(fn=lambda t:1.37))
        for r in o['forecast']:
            self.assertAlmostEqual(r['value'],1.37,places=10)
            self.assertAlmostEqual(r['cycle_factor'],1,places=10)
            self.assertAlmostEqual(r['local_factor'],1,places=10)

    def test_log_linear_input_has_zero_calendar_component(self):
        y=np.array([math.log(1.4)-.002*t for t in range(30)])
        for name in MODELS[-2:]:
            m=_model(y,24,name)
            self.assertLess(float(np.abs(m['cycle']).max()),1e-11)

    def test_partial_year_never_estimates_calendar(self):
        y=np.log([r['value'] for r in observations(9)])
        for name in MODELS[-2:]:
            m=_model(y,12,name)
            self.assertFalse(m['meta']['calendar_active'])
            self.assertLess(float(np.abs(m['cycle']).max()),1e-12)

    def test_data_conditioned_curvature_and_phase(self):
        n=48;truth=lambda t:.4-.001*t+.035*np.sin(2*np.pi*t/12)
        y=np.array([truth(t) for t in range(n)]);future=np.array([truth(t) for t in range(n,n+12)])
        for name in MODELS[-2:]:
            result=np.array(path(y,12,name))
            self.assertLess(np.sqrt(np.mean((result-future)**2)),.008)
            residual=result-np.array([.4-.001*t for t in range(n,n+12)])
            self.assertGreater(np.corrcoef(residual,[np.sin(2*np.pi*t/12) for t in range(n,n+12)])[0,1],.9)

    def test_gp_has_nonnegative_conditional_variance(self):
        for n in [6,12,15,36]:
            m=_model(np.log([r['value'] for r in observations(n,start=2020)]),60,'quasiperiodic_gp')
            self.assertTrue(np.all(np.isfinite(m['variance'])))
            self.assertTrue(np.all(m['variance']>=0))

    def test_gp_responds_to_new_local_observation(self):
        y=np.log([r['value'] for r in observations()]);a=_model(y,12,'quasiperiodic_gp')
        z=y.copy();z[-1]+=.01;b=_model(z,12,'quasiperiodic_gp')
        self.assertGreater(abs(a['path'][0]-b['path'][0]),1e-4)
        self.assertFalse(np.allclose(a['local'],b['local']))

    def test_harmonic_coefficients_reproduce_without_model_helper(self):
        y=np.log([r['value'] for r in observations()]);m=_model(y,5,'harmonic_ridge')
        beta=m['meta']['coefficients_log'];n=len(y);center=(n-1)/2
        for i,pred in enumerate(m['path']):
            t=n+i-center
            raw=beta[0]+beta[1]*t+beta[2]*math.sin(2*math.pi*t/12)+beta[3]*math.cos(2*math.pi*t/12)
            tlast=n-1-center
            last_fit=beta[0]+beta[1]*tlast+beta[2]*math.sin(2*math.pi*tlast/12)+beta[3]*math.cos(2*math.pi*tlast/12)
            raw+=(y[-1]-last_fit)*math.exp(-(i+1)/PARAMETERS['harmonic_anchor_decay_months'])
            self.assertAlmostEqual(raw,pred,places=12)

    def test_each_row_decomposes_and_matches_geometric_ensemble(self):
        o=forecast(observations());weights={m['id']:m['weight'] for m in o['models']}
        for r in o['forecast']:
            self.assertAlmostEqual(r['value'],r['trend_value']*r['cycle_factor']*r['local_factor'],places=12)
            independent=math.exp(sum(weights[m]*math.log(r['members'][m]) for m in MODELS))
            self.assertAlmostEqual(r['value'],independent,places=12)
            self.assertAlmostEqual(r['cycle_percent'],100*(r['cycle_factor']-1),places=11)

    def test_prequential_weights_use_only_revealed_targets(self):
        o=forecast(observations())
        for b in o['ensemble_backtest']:
            prev={m:[] for m in MODELS}
            for e in o['backtest']:
                if e['target']<=b['train_end']: prev[e['model']].append(e['log_error'])
            weights,_=_errors_to_weights(prev)
            for m,w in zip(MODELS,weights):self.assertAlmostEqual(w,b['weights'][m],places=12)
            if b['weight_errors_end']: self.assertLessEqual(b['weight_errors_end'],b['train_end'])

    def test_future_change_does_not_change_past_validation(self):
        a=observations();b=copy.deepcopy(a);b[-1]['value']*=1.15
        left=forecast(a);right=forecast(b)
        before=a[-1]['date']
        for name in ['backtest','ensemble_backtest']:
            self.assertEqual([r for r in left[name] if r['target']<before],[r for r in right[name] if r['target']<before])

    def test_validation_metrics_computed_on_same_pairs(self):
        o=forecast(observations());tests=o['ensemble_backtest'];v=o['validation']
        self.assertEqual(v['n_tests'],len(tests))
        self.assertAlmostEqual(v['mae'],sum(abs(b['predicted']-b['observed']) for b in tests)/len(tests))
        self.assertAlmostEqual(v['last_value_mae'],sum(abs(b['last_value_prediction']-b['observed']) for b in tests)/len(tests))
        self.assertFalse(o['intervals']['calibrated'])

    def test_sorted_and_empty_horizon_are_supported(self):
        obs=observations()
        self.assertEqual(forecast(obs),forecast(list(reversed(obs))))
        self.assertEqual(forecast(obs,obs[-1]['date'])['forecast'],[])

    def test_version_is_part_of_fingerprint(self):
        obs=observations();self.assertNotEqual(forecast(obs)['input_sha256'],legacy_forecast(obs)['input_sha256'])

    def test_cli_reproduces_new_and_old_packets(self):
        for maker in [forecast,legacy_forecast]:
            with tempfile.TemporaryDirectory() as td:
                f=Path(td)/'saved.json';f.write_text(json.dumps(maker(observations())))
                p=subprocess.run([sys.executable,str(ROOT/'scripts/reproduce_projection.py'),'indicator',str(f)],capture_output=True,text=True)
                self.assertEqual(p.returncode,0,p.stderr)

    def test_unknown_future_model_is_not_silently_reinterpreted(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'saved.json';o=forecast(observations());o['model_version']='different/9';f.write_text(json.dumps(o))
            p=subprocess.run([sys.executable,str(ROOT/'scripts/reproduce_projection.py'),'indicator',str(f)],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)

    def test_portable_archive_has_all_imports_and_requirement(self):
        z=ROOT/'public/downloads/projections/projections_python.zip'
        with zipfile.ZipFile(z) as f:
            for name in ['demography/indicator.py','demography/indicator_v11.py','demography/cohort.py','requirements.txt']:
                self.assertIn(name,f.namelist())
            self.assertIn(b'numpy',f.read('requirements.txt'))

if __name__=='__main__':unittest.main()
