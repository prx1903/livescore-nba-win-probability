"""Estimate league possession rates per season and period from the cleaned play-by-play.

Usage:
    python -I src/simulation/estimate_rates.py data/processed results/simulation/rates.json

For every file year (2013-2026) and period group (1, 2, 3, 4, 'ot') the script counts, over all valid games:
  actions      = turnovers + field-goal attempts + free-throw trips (an "action" ends with one of these)
  p_to, p_fga, p_trip   share of actions that are a turnover, a field-goal attempt, a free-throw trip
  p_make2, p_make3      share of field-goal attempts that score 2 or 3 points (points from the score change)
  p_and1                share of made field goals followed by a single free throw ("1 of 1")
  p_trip3               share of free-throw trips with three shots
  ft_pct                made / attempted free throws (technical free throws excluded)
  p_oreb_fg, p_oreb_ft  share of missed field goals / missed last free throws followed by an offensive rebound
  poss_per_team         possessions per team in the period group, (FGA - OREB + TO + 0.44 FTA) / (2 games)
  secs                  playing time of the period group in seconds (720; 300 per overtime period)
Period 4 is split: 'q4' excludes the last 60 s of regulation, which the end-game table covers.
'endgame' (one table for all seasons, from the training seasons 2014-2022 only) covers the actions in the last
60 s of the fourth quarter and of overtime. Cells: time left (60-24 s, 24 s or less) x lead of the team in
possession before the action (<=-9, -8..-4, -3..-1, 0, 1..3, 4..8, >=9). Per cell:
  p_to, p_trip, p_make2, p_make3, p_miss   shares of the actions (a trip is the start of a two- or three-shot
                                           free-throw trip, which includes deliberate fouls)
  mean_left                                mean seconds left at the action
  dt_trip, dt_other                        quantiles (0, 5, ..., 100 %) of the seconds between the previous action
                                           of the other team and this action, for trips and for other actions
  by_start (cells with 24 s or less)       for possessions that start with 24 s or less left (start = previous
                                           action of the other team): the action shares by start (0-3, 3-8, 8-16,
                                           16-24 s left); start groups with fewer than 100 actions use the cell shares;
                                           p_none = share of possessions that end the period without any action of
                                           the team (it runs out the clock); a possession starts at an action of the
                                           other team that is followed by an action of this team or by none; starts
                                           with 0.5 s or less left are not counted (the simulator ends the period)
  frac_left (cells with 24 s or less)      for the same possessions, quantiles of (seconds left at the action) /
                                           (seconds left at the start), by start group and by trip or other action;
                                           groups with fewer than 40 actions use the pooled values
All rates come from events only; no model output is used.
"""
import sys, json
import numpy as np, pandas as pd

data_dir, out_path = sys.argv[1], sys.argv[2]
games = pd.read_csv(f'{data_dir}/games.csv')
games = games[games.is_valid]
COLS = ['game_id', 'game_play_number', 'period_number', 'start_game_seconds_remaining', 'type_text',
        'scoring_play', 'shooting_play', 'team_id', 'home_score', 'away_score']


def classify(e):
    t = e.type_text.fillna('')
    is_ft = t.str.startswith('Free Throw')
    tech = t.str.contains('Technical')
    fga = e.shooting_play.astype(bool) & ~is_ft
    made = e.scoring_play.astype(bool)
    pts = (e.home_score + e.away_score).diff().fillna(0)
    pts = pts.where(e.game_id == e.game_id.shift(), 0)
    to = (t.str.contains('Turnover') & ~t.str.contains('No Turnover')) | (t == 'Traveling')
    trip_start = is_ft & ~tech & t.str.contains(r'1 of [23]')
    and1 = is_ft & ~tech & t.str.contains('1 of 1')
    trip3 = is_ft & t.str.contains('1 of 3')
    last_ft = is_ft & ~tech & t.str.contains(r'(?:1 of 1|2 of 2|3 of 3)')
    return dict(is_ft=is_ft, tech=tech, fga=fga, made=made, pts=pts, to=to, trip_start=trip_start, and1=and1,
                trip3=trip3, last_ft=last_ft, oreb=(t == 'Offensive Rebound'), dreb=(t == 'Defensive Rebound'))


def next_rebound(e, base):
    """For rows in `base`, whether the next rebound within 3 rows is offensive. Returns (found, offensive)."""
    found = np.zeros(len(e), bool); off = np.zeros(len(e), bool)
    for k in (1, 2, 3):
        tt = e.type_text.shift(-k); same = e.game_id.shift(-k) == e.game_id
        m = base & ~found & same & tt.isin(['Offensive Rebound', 'Defensive Rebound'])
        off |= m & (tt == 'Offensive Rebound'); found |= m
    return found, off


out = {}
for y in range(2013, 2027):
    e = pd.read_parquet(f'{data_dir}/pbp_clean/pbp_clean_{y}.parquet', columns=COLS)
    gids = set(games[games.file_year == y].game_id)
    e = e[e.game_id.isin(gids)].sort_values(['game_id', 'game_play_number'], kind='stable').reset_index(drop=True)
    c = classify(e)
    f_fg, o_fg = next_rebound(e, c['fga'] & ~c['made'])
    f_ft, o_ft = next_rebound(e, c['last_ft'] & ~c['made'])
    per = e.period_number.clip(upper=5)
    rem = e.start_game_seconds_remaining
    late_q4 = (per == 4) & (rem <= 60)
    n_games = len(gids)
    n_ot = int(games[(games.file_year == y)].n_periods.sub(4).clip(lower=0).sum())
    rates = {}
    for key, mask, secs in (('1', per == 1, 720.0), ('2', per == 2, 720.0), ('3', per == 3, 720.0),
                            ('q4', (per == 4) & ~late_q4, 660.0), ('ot', per == 5, 300.0 * n_ot / n_games)):
        m = mask.values
        TO = int(c['to'][m].sum()); FGA = int(c['fga'][m].sum()); TR = int(c['trip_start'][m].sum())
        FGM = int((c['fga'] & c['made'])[m].sum())
        make2 = int((c['fga'] & c['made'] & (c['pts'] == 2))[m].sum())
        make3 = int((c['fga'] & c['made'] & (c['pts'] == 3))[m].sum())
        FTA = int((c['is_ft'] & ~c['tech'])[m].sum()); FTM = int((c['is_ft'] & ~c['tech'] & c['made'])[m].sum())
        OREB = int(c['oreb'][m].sum())
        act = TO + FGA + TR
        rates[key] = dict(
            actions=act, p_to=TO / act, p_fga=FGA / act, p_trip=TR / act,
            p_make2=make2 / FGA, p_make3=make3 / FGA, p_and1=int(c['and1'][m].sum()) / max(FGM, 1),
            p_trip3=int(c['trip3'][m].sum()) / max(TR, 1), ft_pct=FTM / FTA,
            p_oreb_fg=float(o_fg[m].sum() / max(f_fg[m].sum(), 1)),
            p_oreb_ft=float(o_ft[m].sum() / max(f_ft[m].sum(), 1)),
            poss_per_team=(FGA - OREB + TO + 0.44 * FTA) / (2 * n_games), secs=secs)
    reg = games[games.file_year == y]
    rates['season'] = dict(games=n_games, ot_rate=float(reg.has_ot.mean()), home_win=float(reg.home_win_final.mean()),
                           mean_total=float((reg.home_end_reg + reg.away_end_reg).mean()))
    out[str(y)] = rates
    print(y, {k: round(v['poss_per_team'], 1) for k, v in rates.items() if 'poss_per_team' in v}, flush=True)
# ---- end-game table, pooled over the training seasons
LEAD_BINS = [-99, -9, -4, -1, 0, 3, 8, 99]
LEAD_LABELS = ['<=-9', '-8..-4', '-3..-1', '0', '1..3', '4..8', '>=9']
Q = np.linspace(0, 100, 21)
START_LABELS = ['0-3', '3-8', '8-16', '16-24']
home_of = games.set_index('game_id').home_team_id.astype(float)
parts, starts = [], []
for y in range(2014, 2023):
    e = pd.read_parquet(f'{data_dir}/pbp_clean/pbp_clean_{y}.parquet', columns=COLS)
    gids = set(games[games.file_year == y].game_id)
    e = e[e.game_id.isin(gids)].sort_values(['game_id', 'game_play_number'], kind='stable').reset_index(drop=True)
    c = classify(e)
    same = e.game_id == e.game_id.shift()
    hb = e.home_score.shift().where(same, 0); ab = e.away_score.shift().where(same, 0)
    is_home = e.team_id.astype(float) == e.game_id.map(home_of)
    act = (c['to'] | c['fga'] | c['trip_start']).values
    a = pd.DataFrame(dict(game_id=e.game_id, period=e.period_number, rem=e.start_game_seconds_remaining,
                          home=is_home, lead=np.where(is_home, hb - ab, ab - hb), to=c['to'], trip=c['trip_start'],
                          m2=c['fga'] & c['made'] & (c['pts'] == 2), m3=c['fga'] & c['made'] & (c['pts'] == 3),
                          miss=c['fga'] & ~c['made']))[act]
    a = a[a.period >= 4]
    prev_same = (a.game_id == a.game_id.shift()) & (a.period == a.period.shift())
    a['dt'] = np.where(prev_same & (a.home != a.home.shift()), a.rem.shift() - a.rem, np.nan)
    a['start'] = np.where(prev_same & (a.home != a.home.shift()), a.rem.shift(), np.nan)
    parts.append(a[a.rem <= 60])
    # possessions of the other team that start at this action (last 24 s)
    fin = e.groupby(['game_id', 'period_number']).tail(1)
    fin_m = pd.Series((fin.home_score - fin.away_score).values, index=pd.MultiIndex.from_arrays([fin.game_id, fin.period_number]))
    nxt = (a.game_id.shift(-1) == a.game_id) & (a.period.shift(-1) == a.period)
    change = ~nxt | (a.home.shift(-1) != a.home)
    xm = fin_m.reindex(pd.MultiIndex.from_arrays([a.game_id, a.period])).to_numpy() * np.where(a.home, 1, -1)
    ps = pd.DataFrame(dict(start=a.rem, none=~nxt, y_lead=np.where(nxt, a.lead.shift(-1), -xm)))[change]
    starts.append(ps[(ps.start <= 24) & (ps.start > 0.5)])
a = pd.concat(parts)
ps = pd.concat(starts)
ps['lb'] = pd.cut(ps.y_lead, LEAD_BINS, labels=LEAD_LABELS).astype(str)
ps['sb'] = pd.cut(ps.start, [0, 3, 8, 16, 24.01], labels=START_LABELS).astype(str)
a['tb'] = np.where(a.rem > 24, '60-24', '<=24')
a['lb'] = pd.cut(a.lead, LEAD_BINS, labels=LEAD_LABELS).astype(str)
endgame = {}
for (tb, lb), d in a.groupby(['tb', 'lb']):
    n = len(d)
    dt = d[(d.dt >= 0) & (d.dt <= 24)]
    endgame[f'{tb}|{lb}'] = dict(
        actions=n, p_to=float(d.to.mean()), p_trip=float(d.trip.mean()), p_make2=float(d.m2.mean()),
        p_make3=float(d.m3.mean()), p_miss=float(d.miss.mean()), mean_left=float(d.rem.mean()),
        dt_trip=[float(v) for v in np.percentile(dt[dt.trip].dt, Q)],
        dt_other=[float(v) for v in np.percentile(dt[~dt.trip].dt, Q)])
    if tb == '<=24':
        h = d[(d.start > 0) & (d.start <= 24) & (d.start >= d.rem)].copy()
        h['frac'] = h.rem / h.start
        h['sb'] = pd.cut(h.start, [0, 3, 8, 16, 24.01], labels=START_LABELS).astype(str)
        fl, bs = {}, {}
        for sb in START_LABELS:
            hb_ = h[h.sb == sb]
            src = hb_ if len(hb_) >= 100 else d
            bs[sb] = dict(actions=int(len(src)), p_to=float(src.to.mean()), p_trip=float(src.trip.mean()),
                          p_make2=float(src.m2.mean()), p_make3=float(src.m3.mean()), p_miss=float(src.miss.mean()))
            pn = ps[(ps.lb == lb) & (ps.sb == sb)]
            pn = pn if len(pn) >= 100 else ps[ps.lb == lb]
            bs[sb].update(p_none=float(pn.none.mean()), n_starts=int(len(pn)))
            for g, hg in (('trip', hb_[hb_.trip]), ('other', hb_[~hb_.trip])):
                src = hg if len(hg) >= 40 else (hb_ if len(hb_) >= 40 else h)
                fl[f'{g}|{sb}'] = dict(n=int(len(src)), q=[float(v) for v in np.percentile(src.frac, Q)])
        endgame[f'{tb}|{lb}']['frac_left'] = fl
        endgame[f'{tb}|{lb}']['by_start'] = bs
    print('endgame', tb, lb, n, {k: round(v, 3) for k, v in endgame[f'{tb}|{lb}'].items() if k.startswith('p_')},
          'median dt trip/other', endgame[f'{tb}|{lb}']['dt_trip'][10], endgame[f'{tb}|{lb}']['dt_other'][10],
          'p_none by start' if tb == '<=24' else '',
          {k: round(v['p_none'], 3) for k, v in endgame[f'{tb}|{lb}'].get('by_start', {}).items()})
for y in out:
    out[y]['endgame'] = endgame
json.dump(out, open(out_path, 'w'), indent=1)
