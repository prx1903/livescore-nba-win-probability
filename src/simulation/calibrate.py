"""Calibrate the game simulator on training seasons only (file years 2014-2022).

Usage:
    python -I src/simulation/calibrate.py .            (run from the repository root)

Targets come from the score-distribution model (results/v2/sim_params.json), which was estimated on the same
training seasons:
  - lead shrink beta: regression of the remaining-margin residual on margin x remaining share (Equation 5);
  - standard deviation of the final regulation margin and total with 48 minutes left (Vm, Vt).
Margin parameters. A persistent game-level margin shock makes a lead persist and moves the simulated beta towards
zero; on a grid of gamma and shock no point reached both the target beta and the target spread of margins. The
extra spread therefore comes from in-game form (game_simulator.py: mean-reverting, time constant 6 minutes), and
there is no persistent margin shock. Steps:
  1. for every gamma of the grid, margin_scale = 1 / (slope of the final margin on mu_m without form);
  2. with that scale, the simulator is run for each form standard deviation of the grid;
  3. for every gamma, the form value that gives the target standard deviation of the final margin is
     interpolated, and the beta at that value; gamma is the value at which that beta equals the target;
  4. two correction rounds at the selected point: margin_scale and points_scale correct the mean final margin and
     total, the form value is moved along the grid slope to the target spread of margins, and the total shock
     fills the missing spread of totals;
  5. per-season points scale: for every file year (2013-2026), points_scale is multiplied by the ratio of the
     mean expected total to the mean simulated total (600 games of the season with their own pre-game
     expectations). Only expectations are used, no real results, so test seasons can be included.
     `python -I src/simulation/calibrate.py . --seasons-only` runs this step on an existing calibration.json.
The overtime rate is reported but is not a target.
In steps 1-4 the real game pairings and pre-game expectations of 2014-2022 are used as inputs; real results are
not used anywhere.
Writes results/simulation/calibration.json.
"""
import sys, os, json, random
import numpy as np, pandas as pd

repo = sys.argv[1]
sys.path.insert(0, os.path.join(repo, 'src', 'simulation'))
import game_simulator as gs

N_GAMES, SEED = 1500, 11
inp = gs.Inputs(repo)
P = inp.sim
SH = np.array(P['share'])
beta_target = P['beta']['ms']
sd_m_target, sd_t_target = float(np.sqrt(P['Vm'][48])), float(np.sqrt(P['Vt'][48]))
pg = inp.pregame
pg = pg[(pg.file_year >= 2014) & (pg.file_year <= 2022) & pg.sp.notna()]
games = pg.sample(N_GAMES, random_state=SEED).reset_index(drop=True)
K = np.arange(0, 2880, 60.0)
rho = np.interp(K, np.arange(49) * 60.0, SH)


def run(cal, shocks):
    inp.cal = {**gs.DEFAULT_CAL, **cal}
    rows = []
    for i, g in games.iterrows():
        exp = dict(mu_h=g.mu_h, mu_a=g.mu_a, mu_m=g.mu_m, mu_t=g.mu_t, spread=g.sp)
        info, ev = gs.simulate_from_expectations(inp, int(g.file_year), exp, seed=1000 + i, shocks=shocks)
        reg = ev[ev.period_number <= 4]
        t = reg.game_seconds_elapsed.values
        m = (reg.home_score - reg.away_score).values
        idx = np.searchsorted(t, K, side='right') - 1
        rows.append(dict(mu_m=g.mu_m, mu_t=g.mu_t, M=info['home_end_reg'] - info['away_end_reg'],
                         T=info['home_end_reg'] + info['away_end_reg'], ot=info['has_ot'], m_k=m[idx]))
    return rows


def summarise(rows):
    mu_m = np.array([r['mu_m'] for r in rows]); mu_t = np.array([r['mu_t'] for r in rows])
    M = np.array([r['M'] for r in rows]); T = np.array([r['T'] for r in rows])
    mk = np.vstack([r['m_k'] for r in rows])                       # games x 48
    R = (M[:, None] - mk - mu_m[:, None] * rho[None, :])
    X = mk * rho[None, :]
    beta = float((X * R).sum() / (X * X).sum())
    slope = float((M * mu_m).sum() / (mu_m * mu_m).sum())
    return dict(beta=beta, slope_margin=slope, mean_total_ratio=float(T.mean() / mu_t.mean()),
                sd_margin=float(np.std(M - mu_m)), sd_total=float(np.std(T - mu_t)),
                ot_rate=float(np.mean([r['ot'] for r in rows])))


out = os.path.join(repo, 'results', 'simulation')
SEASON_GAMES = 600


def season_scales(cal):
    """Step 5: points scale per file year from simulated totals versus expected totals."""
    allpg = inp.pregame[inp.pregame.sp.notna()]
    res = {}
    for y in sorted(allpg.file_year.unique()):
        g = allpg[allpg.file_year == y]
        g = g.sample(min(SEASON_GAMES, len(g)), random_state=SEED).reset_index(drop=True)
        inp.cal = {**gs.DEFAULT_CAL, **cal, 'points_scale_by_season': {}}
        T, mt = [], []
        for i, r in g.iterrows():
            info, _ = gs.simulate_from_expectations(inp, int(y), dict(mu_h=r.mu_h, mu_a=r.mu_a, mu_m=r.mu_m, mu_t=r.mu_t,
                                                                      spread=r.sp), seed=7000 + i, shocks=True)
            T.append(info['home_end_reg'] + info['away_end_reg']); mt.append(r.mu_t)
        ratio = float(np.mean(T) / np.mean(mt))
        res[str(int(y))] = cal['points_scale'] / ratio
        print('season', int(y), 'simulated / expected total', round(ratio, 4), flush=True)
    return res


if len(sys.argv) > 2 and sys.argv[2] == '--seasons-only':
    cal = json.load(open(os.path.join(out, 'calibration.json')))
    cal['points_scale_by_season'] = season_scales(cal)
    json.dump(cal, open(os.path.join(out, 'calibration.json'), 'w'), indent=1)
    lp = os.path.join(out, 'calibration_log.json')
    if os.path.exists(lp):
        log = json.load(open(lp))
        log['selected'] = cal
        json.dump(log, open(lp, 'w'), indent=1)
    print('written', cal)
    raise SystemExit
log = {'targets': dict(beta=beta_target, sd_margin=sd_m_target, sd_total=sd_t_target), 'grid': []}
GAMMAS = (0.003, 0.004, 0.005, 0.006)
FORMS = (0.1, 0.2, 0.3, 0.4)
rows = []
for gamma in GAMMAS:
    s0 = summarise(run({'gamma': gamma}, shocks=False))
    scale = 1.0 / s0['slope_margin']
    for fs in FORMS:
        sm = summarise(run({'gamma': gamma, 'margin_scale': scale, 'form_sd': fs}, shocks=False))
        rows.append(dict(gamma=gamma, margin_scale=scale, form_sd=fs, **sm))
        print('gamma', gamma, 'form', fs, {k: round(v, 4) for k, v in sm.items()}, flush=True)
grid = pd.DataFrame(rows)
log['grid'] = rows
cand = []
for gamma, g in grid.groupby('gamma'):
    g = g.sort_values('form_sd')
    if g.sd_margin.max() < sd_m_target or g.sd_margin.min() > sd_m_target:
        continue
    fs = float(np.interp(sd_m_target, g.sd_margin, g.form_sd))
    cand.append((gamma, fs, float(np.interp(fs, g.form_sd, g.beta)), float(g.margin_scale.iloc[0]),
                 float(np.polyfit(g.form_sd, g.sd_margin, 1)[0])))
cand = pd.DataFrame(cand, columns=['gamma', 'form_sd', 'beta', 'margin_scale', 'dsd_dform'])
print(cand.round(4).to_string(), flush=True)
c = cand.sort_values('gamma')
if c.beta.min() <= beta_target <= c.beta.max():
    gamma = float(np.interp(-beta_target, -c.beta, c.gamma))
else:
    gamma = float(c.iloc[(c.beta - beta_target).abs().argmin()].gamma)
cal = dict(gs.DEFAULT_CAL, gamma=gamma, form_sd=float(np.interp(gamma, c.gamma, c.form_sd)),
           margin_scale=float(np.interp(gamma, c.gamma, c.margin_scale)))
slope_sd = float(np.interp(gamma, c.gamma, c.dsd_dform))
log['corrections'] = []
for rnd in range(2):
    s1 = summarise(run(cal, shocks=True))
    cal['margin_scale'] /= s1['slope_margin']
    cal['points_scale'] /= s1['mean_total_ratio']
    cal['form_sd'] = float(max(cal['form_sd'] + (sd_m_target - s1['sd_margin']) / slope_sd, 0.0))
    cal['shock_sd_total'] = float(np.sqrt(max(cal['shock_sd_total'] ** 2 + sd_t_target ** 2 - s1['sd_total'] ** 2, 0.0)))
    log['corrections'].append(dict(before=s1, cal=dict(cal)))
    print('correction', rnd, {k: round(v, 4) for k, v in s1.items()}, '->', {k: round(v, 4) for k, v in cal.items()}, flush=True)
s3 = summarise(run(cal, shocks=True))
print('final', {k: round(v, 4) for k, v in s3.items()}, flush=True)
cal['points_scale_by_season'] = season_scales(cal)
log.update(candidates=cand.to_dict('records'), selected=cal, final=s3, n_games=N_GAMES, seasons='2014-2022', seed=SEED,
           form_tau=gs.FORM_TAU)
json.dump(cal, open(os.path.join(out, 'calibration.json'), 'w'), indent=1)
json.dump(log, open(os.path.join(out, 'calibration_log.json'), 'w'), indent=1)
print('written', cal)
