"""Compare simulated games with real games of the test seasons (file years 2023-2026).

Usage:
    python -I src/simulation/validate.py .            (run from the repository root)

Every real test game with a pre-game line is simulated once with its own pre-game expectations (the same inputs
the models use); real results are not used by the simulator. Both sets of games are summarised with the same code:
  - final regulation margin and total minus their expectations (mean and standard deviation), overtime rate,
    home-win rate by expected margin;
  - lead shrink beta (Equation 5 of the score-distribution model) on the test games;
  - game flow: share of points per quarter, lead changes, largest lead, longest scoring run, free-throw attempts,
    standard deviation of the margin after 12, 24 and 36 minutes, share of games tied or within 3 points with
    24 s left and at the end of regulation;
  - feed checks (src/feed_checks.py) on every simulated event.
For a mean, the 95 % interval of the difference (simulated - real) uses the standard errors of both sets.
Writes results/simulation/validation.json and results/simulation/validation_report.txt.
"""
import sys, os, json, re
import numpy as np, pandas as pd

repo = sys.argv[1]
sys.path.insert(0, os.path.join(repo, 'src', 'simulation'))
sys.path.insert(0, os.path.join(repo, 'src'))
import game_simulator as gs
from feed_checks import FeedState, check_event

SEED0 = 200_000
inp = gs.Inputs(repo)
P = inp.sim
rho = np.interp(np.arange(0, 2880, 60.0), np.arange(49) * 60.0, np.array(P['share']))
K = np.arange(0, 2880, 60.0)
data = os.path.join(repo, 'data', 'processed')
games = pd.read_csv(os.path.join(data, 'games.csv'))
games = games[games.is_valid & (games.file_year >= 2023)]
pg = inp.pregame
pg = pg[(pg.file_year >= 2023) & pg.sp.notna() & pg.game_id.isin(games.game_id)].reset_index(drop=True)
COLS = ['game_id', 'game_play_number', 'period_number', 'start_game_seconds_remaining', 'game_seconds_elapsed',
        'type_text', 'home_score', 'away_score']
FT = re.compile('free throw', re.I)


def flow(ev):
    """Flow statistics of one game (events sorted by play number)."""
    reg = ev[ev.period_number <= 4]
    h, a = reg.home_score.to_numpy(float), reg.away_score.to_numpy(float)
    m = h - a
    t = reg.game_seconds_elapsed.to_numpy(float)
    idx = np.searchsorted(t, K, side='right') - 1
    m_k = np.where(idx >= 0, m[np.clip(idx, 0, None)], 0.0)
    q_tot = []
    for q in (1, 2, 3, 4):
        r = reg[reg.period_number <= q]
        q_tot.append(float(r.home_score.iloc[-1] + r.away_score.iloc[-1]) if len(r) else 0.0)
    q_pts = np.diff([0.0] + q_tot)
    s = np.sign(m[m != 0])
    lead_changes = int((s[1:] != s[:-1]).sum()) if len(s) > 1 else 0
    dh, da = np.diff(np.r_[0, h]), np.diff(np.r_[0, a])
    run, best, side = 0.0, 0.0, 0
    for x, y in zip(dh, da):
        if x > 0 and y == 0:
            run = run + x if side == 1 else x; side = 1
        elif y > 0 and x == 0:
            run = run + y if side == -1 else y; side = -1
        elif x > 0 and y > 0:
            run, side = 0.0, 0
        best = max(best, run)
    tt = ev.type_text.fillna('')
    fta = int((tt.str.contains(FT) & ~tt.str.contains('echnical')).sum())
    idx24 = np.searchsorted(t, 2880 - 24, side='right') - 1
    m24 = m[idx24] if idx24 >= 0 else 0.0
    return dict(m_k=m_k, q_share=q_pts / max(q_pts.sum(), 1.0), lead_changes=lead_changes,
                largest_lead=float(np.abs(m).max()), longest_run=best, fta=fta, m24=float(m24))


def summary(rows, info):
    mu_m = info.mu_m.to_numpy(); mu_t = info.mu_t.to_numpy()
    M = info['M'].to_numpy(float); T = info['T'].to_numpy(float)
    mk = np.vstack([r['m_k'] for r in rows])
    R = M[:, None] - mk - mu_m[:, None] * rho[None, :]
    X = mk * rho[None, :]
    out = dict(
        n=len(rows),
        resid_margin_mean=(M - mu_m), resid_margin_sd=None, resid_total_mean=(T - mu_t), resid_total_sd=None,
        ot=info.ot.to_numpy(float), home_win=info.home_win.to_numpy(float),
        beta=float((X * R).sum() / (X * X).sum()), slope_margin=float((M * mu_m).sum() / (mu_m * mu_m).sum()),
        lead_changes=np.array([r['lead_changes'] for r in rows], float),
        largest_lead=np.array([r['largest_lead'] for r in rows]),
        longest_run=np.array([r['longest_run'] for r in rows]),
        fta=np.array([r['fta'] for r in rows], float),
        tie_24=np.array([r['m24'] == 0 for r in rows], float),
        close_24=np.array([abs(r['m24']) <= 3 for r in rows], float),
        tie_end=(M == 0).astype(float), close_end=(np.abs(M) <= 3).astype(float),
    )
    out['resid_margin_sd'] = float(np.std(M - mu_m)); out['resid_total_sd'] = float(np.std(T - mu_t))
    q = np.vstack([r['q_share'] for r in rows])
    for i in range(4):
        out[f'q{i + 1}_share'] = q[:, i]
    for k in (12, 24, 36):
        out[f'sd_margin_{k}min'] = float(np.std(mk[:, k]))
    return out


# ---- real games
real_ev = {}
for y in range(2023, 2027):
    e = pd.read_parquet(os.path.join(data, 'pbp_clean', f'pbp_clean_{y}.parquet'), columns=COLS)
    e = e[e.game_id.isin(set(pg.game_id))].sort_values(['game_id', 'game_play_number'], kind='stable')
    for gid, d in e.groupby('game_id', sort=False):
        real_ev[gid] = d
g = games.set_index('game_id')
pg = pg[pg.game_id.isin(real_ev)].reset_index(drop=True)
real_rows = [flow(real_ev[gid]) for gid in pg.game_id]
real_info = pd.DataFrame(dict(
    mu_m=pg.mu_m, mu_t=pg.mu_t,
    M=pg.game_id.map(g.home_end_reg - g.away_end_reg).to_numpy(), T=pg.game_id.map(g.home_end_reg + g.away_end_reg).to_numpy(),
    ot=pg.game_id.map(g.has_ot).astype(float).to_numpy(), home_win=pg.game_id.map(g.home_win_final).astype(float).to_numpy()))

# ---- simulated games and feed checks
sim_rows, sim_info, fc = [], [], dict(games=0, events=0, rejected=0, warnings=0)
for i, r in pg.iterrows():
    exp = dict(mu_h=r.mu_h, mu_a=r.mu_a, mu_m=r.mu_m, mu_t=r.mu_t, spread=r.sp)
    info, ev = gs.simulate_from_expectations(inp, int(r.file_year), exp, seed=SEED0 + i, shocks=True)
    sim_rows.append(flow(ev))
    sim_info.append(dict(mu_m=r.mu_m, mu_t=r.mu_t, M=info['home_end_reg'] - info['away_end_reg'],
                         T=info['home_end_reg'] + info['away_end_reg'], ot=float(info['has_ot']),
                         home_win=float(info['home_win_final'])))
    st = FeedState(); fc['games'] += 1
    for e in ev.itertuples():
        ok, w = check_event(st, e.home_score, e.away_score, e.period_number, e.game_seconds_elapsed,
                            e.start_game_seconds_remaining, seq=e.game_play_number)
        fc['events'] += 1; fc['rejected'] += int(not ok); fc['warnings'] += len(w)
sim_info = pd.DataFrame(sim_info)

RS, SS = summary(real_rows, real_info), summary(sim_rows, sim_info)
res = dict(n_games=len(pg), seasons='2023-2026', seed0=SEED0, feed_checks=fc, metrics={})
lines = [f'Simulated vs real games, test seasons 2023-2026, {len(pg)} games (each real game simulated once)', '',
         f'{"metric":34s} {"real":>9s} {"simulated":>10s} {"difference [95% interval]":>30s}']
for key in ('resid_margin_mean', 'resid_total_mean', 'ot', 'home_win', 'tie_end', 'close_end', 'tie_24', 'close_24',
            'q1_share', 'q2_share', 'q3_share', 'q4_share', 'lead_changes', 'largest_lead', 'longest_run', 'fta'):
    a, b = RS[key], SS[key]
    d = b.mean() - a.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    res['metrics'][key] = dict(real=float(a.mean()), sim=float(b.mean()), diff=float(d), lo=float(d - 1.96 * se), hi=float(d + 1.96 * se))
    lines.append(f'{key:34s} {a.mean():9.4f} {b.mean():10.4f} {d:+10.4f} [{d - 1.96 * se:+.4f}, {d + 1.96 * se:+.4f}]')
for key in ('resid_margin_sd', 'resid_total_sd', 'beta', 'slope_margin', 'sd_margin_12min', 'sd_margin_24min',
            'sd_margin_36min'):
    res['metrics'][key] = dict(real=RS[key], sim=SS[key], diff=SS[key] - RS[key])
    lines.append(f'{key:34s} {RS[key]:9.4f} {SS[key]:10.4f} {SS[key] - RS[key]:+10.4f}')
lines += ['', 'Home-win rate by expected margin mu_m (home - away):']
bins = [-99, -6, -2, 2, 6, 99]
for lo, hi in zip(bins[:-1], bins[1:]):
    mr = (real_info.mu_m > lo) & (real_info.mu_m <= hi)
    ms = (sim_info.mu_m > lo) & (sim_info.mu_m <= hi)
    key = f'home_win_mu_{lo}_{hi}'
    res['metrics'][key] = dict(n=int(mr.sum()), real=float(real_info.home_win[mr].mean()), sim=float(sim_info.home_win[ms].mean()))
    lines.append(f'  mu_m in ({lo:>3d}, {hi:>3d}]  n={int(mr.sum()):5d}  real {real_info.home_win[mr].mean():.3f}  simulated {sim_info.home_win[ms].mean():.3f}')
lines += ['', f'Feed checks on simulated events: {fc["games"]} games, {fc["events"]} events, '
              f'{fc["rejected"]} rejected, {fc["warnings"]} warnings']
out = os.path.join(repo, 'results', 'simulation')
json.dump(res, open(os.path.join(out, 'validation.json'), 'w'), indent=1)
open(os.path.join(out, 'validation_report.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
