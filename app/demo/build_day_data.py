"""All games of one day for the demo page: score, clock and win probability at every event.
One day clock: the games advance together according to their assigned start times.
One generated game is added to the real games ('syn': 1); the interface says that it is not real.
Event row: [elapsed s, probability, home score, away score, period, clock, event type, team, event class]
  team: 1 home, 0 away, -1 none; class (for the court animation): 0 other, 1 shot, 2 free throw,
  3 offensive rebound, 4 defensive rebound, 5 turnover, 6 start of period / jump ball, 7 end of period / game.
Shot locations ('sh'): for real games from the raw file, for the generated game from the simulator's location table
(shot distribution of the training season 2022; results/simulation/shot_locations.json).
Usage (from the repository root): python -I app/demo/build_day_data.py   -> app/demo/day_data.json
Needs data/processed/pbp_clean/pbp_clean_2026.parquet and data/raw/play_by_play_2026.parquet (not in git)."""
import json, math, os, sys
import pandas as pd

U = os.environ.get("LIVESCORE_REPO", os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')))
OUT = os.path.join(U, 'app', 'demo', 'day_data.json')
# Generated game (not real): two of the six teams that did not play that night, 2025-26 strengths, fixed seed.
SIM_SEASON, SIM_SEED, SIM_TIP_MIN = 2026, 1, 30
# Shot locations from the raw file (data/raw, coordinate_x_raw / coordinate_y_raw): x 0-50 ft (sideline to sideline),
# y in ft from the rim centre towards half court (free-throw line 13.75). Always relative to the attacked basket.
RAW = os.environ.get("LIVESCORE_RAW", U + "/data/raw/play_by_play_2026.parquet")
DATE = "2025-12-18"
# Day clock and game clock run 1:1 so that the game clock runs at real speed at 1x: a game lasts 48 minutes
# (longer with overtime). Start times were assigned for the presentation: on a real NBA night games spread over about
# 3.5 hours and a game lasts 2.5 hours (ratio 1.4). The 12 games were spread over 90 minutes with the same ratio.
TIP_MIN = [0, 0, 10, 20, 30, 30, 40, 50, 60, 70, 80, 90]   # minutes after 02:00
mdl = json.load(open(U + "/models/model_coefficients.json", encoding="utf-8"))


def predict(m, tl, ot, sp):
    f = {'m_over_sqrt_tl': m / math.sqrt(tl + 1.0), 'is_ot': 1.0 if ot else 0.0,
         'spread_x_tl': sp * (tl / 2880.0), 'spread_x_sqrt_tl': sp * math.sqrt(tl / 2880.0)}
    z = mdl['intercept'] + sum(c * f[n] for n, c in zip(mdl['features'], mdl['coef']))
    return 1.0 / (1.0 + math.exp(-z))


g = pd.read_csv(U + "/data/processed/games.csv")
d = g[(g.game_date == DATE) & g.is_valid & (g.season_type == 2)].sort_values('game_id').reset_index(drop=True)
pbp = pd.read_parquet(U + "/data/processed/pbp_clean/pbp_clean_2026.parquet")
pbp = pbp[pbp.game_id.isin(set(d.game_id))]
raw = pd.read_parquet(RAW, columns=['game_id', 'game_play_number', 'type_text', 'team_id', 'home_team_id',
                                    'score_value', 'coordinate_x_raw', 'coordinate_y_raw'])
raw = raw[raw.game_id.isin(set(d.game_id))]
pbp = pbp.merge(raw.rename(columns={'type_text': 'type_raw', 'team_id': 'team_raw'}), on=['game_id', 'game_play_number'],
                how='left', validate='one_to_one')
assert (pbp.type_text == pbp.type_raw).all(), 'raw file and clean data do not match'

types, tidx = [], {}


def kind(t, shooting):
    """Event class (list above). For source and generated texts."""
    tl = t.lower()
    if tl.startswith('free throw'):
        return 2
    if shooting:
        return 1
    if 'rebound' in tl:
        return 3 if 'offensive' in tl else (4 if 'defensive' in tl else 0)
    if ('turnover' in tl and 'no turnover' not in tl) or tl == 'traveling':
        return 5
    if tl.startswith('end'):
        return 7
    if ('jump' in tl and 'ball' in tl) or tl.startswith('start of period'):
        return 6
    return 0


def side(team, home_id):
    return -1 if pd.isna(team) else int(float(team) == float(home_id))


def ti(t):
    if t not in tidx:
        tidx[t] = len(types); types.append(t)
    return tidx[t]


out = []
for i, r in d.iterrows():
    ev = pbp[pbp.game_id == r.game_id].sort_values('game_play_number').reset_index(drop=True)
    sp = float(r.spread_home)
    rows = [[int(e.game_seconds_elapsed), round(predict(e.home_score - e.away_score, e.start_game_seconds_remaining,
             e.period_number > 4, sp), 3), int(e.home_score), int(e.away_score), int(e.period_number),
             str(e.clock_display_value), ti(str(e.type_text)), side(e.team_id, e.home_team_id),
             kind(str(e.type_text), bool(e.shooting_play))] for e in ev.itertuples()]
    # shots drawn on the court (free throws excluded): [event index, x, y, home, made, points]
    shots = []
    for k, e in enumerate(ev.itertuples()):
        if e.shooting_play and not str(e.type_text).startswith('Free Throw') and pd.notna(e.coordinate_x_raw):
            made = bool(e.scoring_play)
            shots.append([k, round(float(e.coordinate_x_raw), 1), round(float(e.coordinate_y_raw), 1),
                          int(float(e.team_id) == float(e.home_team_id)), int(made), int(e.score_value) if made else 0])
    out.append({'id': int(r.game_id), 'home': r.home_abbrev, 'away': r.away_abbrev, 'sh': shots,
                'tip': 7200 + TIP_MIN[i % len(TIP_MIN)] * 60, 'dur': rows[-1][0], 'sp': sp,
                'pre': round(predict(0.0, 2880.0, False, sp), 3),
                'np': int(r.n_periods), 'ot': int(r.has_ot), 'ev': rows})
# ---- generated game: src/simulation/game_simulator.py (generic event texts, no source text)
sys.path.insert(0, U + "/src/simulation")
import game_simulator as gs
inp = gs.Inputs(U)
busy = set(d.home_abbrev) | set(d.away_abbrev)
free = [t for t in inp.teams(SIM_SEASON) if t not in busy]
import random
rng = random.Random(SIM_SEED)
home, away = rng.sample(free, 2)
info, sev = gs.simulate_game(inp, SIM_SEASON, home, away, seed=SIM_SEED)
sp = float(info['spread_home'])
rows = [[int(e.game_seconds_elapsed), round(predict(e.home_score - e.away_score, e.start_game_seconds_remaining,
         e.period_number > 4, sp), 3), int(e.home_score), int(e.away_score), int(e.period_number),
         str(e.clock_display_value), ti(str(e.type_text)), side(e.team_id, 1),
         kind(str(e.type_text), bool(e.shooting_play))] for e in sev.itertuples()]
sshots = [[k, float(e.shot_x), float(e.shot_y), int(e.team_id == 1), int(bool(e.scoring_play)),
           (3 if '3-pt' in e.type_text else 2) if e.scoring_play else 0]
          for k, e in enumerate(sev.itertuples()) if pd.notna(e.shot_x)]
# synNote is shown in the (Turkish) interface
out.append({'id': int(info['game_id']), 'home': home, 'away': away, 'tip': 7200 + SIM_TIP_MIN * 60, 'dur': rows[-1][0],
            'sp': round(sp, 1), 'pre': round(predict(0.0, 2880.0, False, sp), 3), 'np': int(info['n_periods']),
            'ot': int(info['has_ot']), 'syn': 1, 'seed': SIM_SEED, 'sh': sshots,
            'synNote': f"{SIM_SEASON - 1}-{str(SIM_SEASON)[2:]} takım güçlerinden üretildi (tohum {SIM_SEED})", 'ev': rows})
print('generated game', away, '@', home, '| expected margin', round(info['mu_m'], 1), '| line', round(sp, 1),
      '| result', info['away_final'], '-', info['home_final'], '| overtime' if info['has_ot'] else '')

# ---- home advantage (demo panel): rating-model home edge H and expected margin mu_m of every game,
# and season averages of regular-season games played before DATE (no later games are used)
pre = pd.read_parquet(U + "/results/v2/pregame.parquet").set_index('game_id')
rat = json.load(open(U + "/results/v2/ratings_params.json", encoding="utf-8"))
for o in out:
    if o.get('syn'):
        # the simulator uses team strengths after each team's last game of the season; same for H
        o['H'] = round(float(pre[pre.file_year == SIM_SEASON].H.iloc[-1]), 3)
        o['mu'] = round(float(info['mu_m']), 3)
    else:
        p = pre.loc[o['id']]
        assert abs(float(p.sp) - o['sp']) < 1e-9, o['id']
        o['H'], o['mu'] = round(float(p.H), 3), round(float(p.mu_m), 3)
v = g[g.is_valid & (g.game_date < DATE)].copy()
v['mreg'] = v.home_end_reg - v.away_end_reg
summ = lambda x: {'n': int(len(x)), 'margin': round(float(x.mreg.mean()), 3), 'spread': round(float(x.spread_home.mean()), 3),
                  'home_win': round(float(x.home_win_final.mean()), 4)}
seasons = [dict(season=s, **summ(x)) for s, x in v[(v.season_type == 2) & (v.file_year >= 2013)].groupby('season_label')]
seasons[-1]['partial'] = 1          # the season of DATE, games before DATE only
home = {'b': rat['b_sp'], 'seasons': seasons, 'playoff': summ(v[(v.season_type == 3) & (v.file_year >= 2013)])}

D = {'date': DATE, 'types': types, 'dayStart': min(o['tip'] for o in out),
     'dayEnd': max(o['tip'] + o['dur'] for o in out), 'games': out, 'home': home}
# opening moment: most games live while at least 2 finished and 2 not started
best, bestT = -1, D['dayStart']
for t in range(D['dayStart'], D['dayEnd'], 60):
    liv = sum(1 for o in out if o['tip'] < t < o['tip'] + o['dur'])
    fin = sum(1 for o in out if t >= o['tip'] + o['dur'])
    pre = sum(1 for o in out if t <= o['tip'])
    if fin >= 2 and pre >= 2 and liv > best: best, bestT = liv, t
D['startAt'] = bestT
json.dump(D, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print('games', len(out), '| events', sum(len(o['ev']) for o in out), '| event types', len(types),
      '| file', os.path.getsize(OUT), 'bytes')
h = lambda s: f"{s//3600:02d}:{s%3600//60:02d}"
print('day', h(D['dayStart']), '->', h(D['dayEnd']), '| at 1x', round((D['dayEnd']-D['dayStart'])/60), 'min,',
      'at 20x', round((D['dayEnd']-D['dayStart'])/60/20, 1), 'min')
print('opening moment', h(bestT), '-', best, 'games live')
for o in out:
    st = 'live' if o['tip'] < bestT < o['tip']+o['dur'] else ('finished' if bestT >= o['tip']+o['dur'] else 'not started')
    print(f"  {o['away']:>4} @ {o['home']:<4} {h(o['tip'])} -> {h(o['tip']+o['dur'])}  {st}")
