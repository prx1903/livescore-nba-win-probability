"""Synthetic NBA games: score-flow targets from team strengths, played out possession by possession.

Two layers:
  1. Score flow. The expected regulation points of each team come from the team ratings of src/v2/ratings.py
     (Equations 2-4 of the report): mu_m from the ratings difference, mu_t from the ratings sum. A game-level
     random shock can be added to both targets (calibration.json; the calibrated margin shock is zero, the
     total shock fills the spread of final totals that the possessions do not produce).
  2. Possessions. Each possession is a sequence of actions (turnover, field-goal attempt, free-throw trip) drawn
     from league rates of the chosen season and period (results/simulation/rates.json). The make probabilities of
     each team are scaled by one efficiency factor, solved so that its expected points equal its target. Overtime
     periods are played until the game is decided. The make probabilities of the team in possession are
     multiplied by exp(-gamma * lead + form): leads shrink on average as they do in real games (the lead-shrink
     coefficient of the score-distribution model), and form is a mean-reverting difference between the teams
     (runs, lineups) that widens the spread of margins without making leads persist; gamma and the standard
     deviation of form are calibrated (calibrate.py).
  3. End game. In the last 60 s of the fourth quarter and of overtime, actions follow the end-game table of
     rates.json (time left x lead of the team in possession, training seasons): action shares, including
     deliberate fouls by the trailing team, and the time between possessions. For a possession that starts with
     24 s or less left, the action shares depend on the time left at the start, the time of the action is drawn
     as a share of the remaining time (a tied team holds the ball for the last shot, a leading team is fouled), and
     with the measured probability the team runs out the clock without an action.

The events have the columns of data/processed/pbp_clean, so the replay, the feed checks and the models read them
unchanged. Event texts are generic ("Made 3-pt shot", "Defensive rebound") and contain no source text.
Synthetic games are for demonstration and system tests only; they must not be used to measure model accuracy,
because they are generated from the same expectations that the models use.
"""
import bisect, json, math, os, random
import numpy as np, pandas as pd

REG_PERIOD, OT_PERIOD, LATE_SECS, CLUTCH_SECS = 720.0, 300.0, 60.0, 24.0
LEAD_BUCKETS = ((-9, '<=-9'), (-4, '-8..-4'), (-1, '-3..-1'), (0, '0'), (3, '1..3'), (8, '4..8'))
SIM_GAME_ID_BASE = 9_000_000_000
DEFAULT_CAL = {'gamma': 0.0, 'form_sd': 0.0, 'shock_sd_margin': 0.0, 'shock_sd_total': 0.0, 'points_scale': 1.0,
               'margin_scale': 1.0}
FORM_TAU = 360.0               # time constant of in-game form (game seconds, half a quarter); assumed, not estimated


# ------------------------------------------------------------------ inputs
class Inputs:
    """Everything the simulator reads from the repository."""

    def __init__(self, repo):
        self.repo = repo
        self.pregame = pd.read_parquet(os.path.join(repo, 'results/v2/pregame.parquet'))
        self.rparams = json.load(open(os.path.join(repo, 'results/v2/ratings_params.json')))
        self.sim = json.load(open(os.path.join(repo, 'results/v2/sim_params.json')))
        self.rates = json.load(open(os.path.join(repo, 'results/simulation/rates.json')))
        cal = os.path.join(repo, 'results/simulation/calibration.json')
        self.cal = json.load(open(cal)) if os.path.exists(cal) else dict(DEFAULT_CAL)
        loc = os.path.join(repo, 'results/simulation/shot_locations.json')
        self.locs = None
        if os.path.exists(loc):                       # shot locations (estimate_shot_locations.py); optional
            self.locs = {}
            for c, cells in json.load(open(loc))['categories'].items():
                self.locs[c] = ([(x, y) for x, y, _ in cells], list(np.cumsum([n for _, _, n in cells])))

    def seasons(self):
        return sorted(int(y) for y in self.rates)

    def teams(self, year):
        p = self.pregame[self.pregame.file_year == year]
        return sorted(set(p.home_abbrev) | set(p.away_abbrev))

    def ratings(self, year, abbrev):
        """Offensive and defensive rating of a team before its last game of the season, with L and H."""
        p = self.pregame[(self.pregame.file_year == year) &
                         ((self.pregame.home_abbrev == abbrev) | (self.pregame.away_abbrev == abbrev))]
        if p.empty:
            raise ValueError(f'no games for {abbrev} in file year {year}')
        r = p.sort_values(['game_date', 'game_id']).iloc[-1]
        if r.home_abbrev == abbrev:
            return float(r.O_h), float(r.D_h), float(r.L), float(r.H)
        return float(r.O_a), float(r.D_a), float(r.L), float(r.H)

    def expectations(self, year, home, away):
        """Expected regulation points (mu_h, mu_a), mu_m, mu_t and the implied pre-game line for a matchup."""
        Oh, Dh, L, H = self.ratings(year, home)
        Oa, Da, _, _ = self.ratings(year, away)
        eh = L + H / 2 + Oh + Da
        ea = L - H / 2 + Oa + Dh
        b_rm, b_tot, b_sp = self.rparams['b_rm'], self.rparams['b_tot'], self.rparams['b_sp']
        mu_m = b_rm[0] + b_rm[1] * (eh - ea)
        mu_t = b_tot[0] + b_tot[1] * (eh + ea)
        spread = (mu_m - b_sp[0]) / b_sp[1]          # line that the spread model would turn into mu_m
        return dict(mu_h=(mu_t + mu_m) / 2, mu_a=(mu_t - mu_m) / 2, mu_m=mu_m, mu_t=mu_t, spread=spread)


# ------------------------------------------------------------------ expected points per possession
def _period_key(period):
    return {1: '1', 2: '2', 3: '3', 4: 'q4'}.get(period, 'ot')


def _lead_bucket(lead):
    for hi, name in LEAD_BUCKETS:
        if lead <= hi:
            return name
    return '>=9'


def _from_quantiles(q, u):
    """Draw from a distribution given by equally spaced quantiles (linear interpolation)."""
    x = u * (len(q) - 1)
    i = min(int(x), len(q) - 2)
    return q[i] + (q[i + 1] - q[i]) * (x - i)


def _scaled(r, eff):
    m2, m3 = r['p_make2'] * eff, r['p_make3'] * eff
    s = m2 + m3
    if s > 0.92:                                    # keep a miss probability
        m2, m3 = m2 * 0.92 / s, m3 * 0.92 / s
    return m2, m3


def expected_ppp(r, eff):
    """Expected points per possession for period rates r and efficiency eff (actions repeat on offensive rebounds)."""
    m2, m3 = _scaled(r, eff)
    ft = r['ft_pct']; made = m2 + m3
    n_ft = 2 * (1 - r['p_trip3']) + 3 * r['p_trip3']
    a = r['p_fga'] * (2 * m2 + 3 * m3 + made * r['p_and1'] * ft) + r['p_trip'] * n_ft * ft
    b = (r['p_fga'] * (1 - made) * r['p_oreb_fg'] + r['p_trip'] * (1 - ft) * r['p_oreb_ft']
         + r['p_fga'] * made * r['p_and1'] * (1 - ft) * r['p_oreb_ft'])
    return a / (1 - b)


def expected_points(rates_y, eff):
    """Expected regulation points of one team: possessions per period times points per possession."""
    tot = 0.0
    for key, secs in (('1', 720), ('2', 720), ('3', 720), ('q4', 720)):
        r = rates_y[key]
        poss = r['poss_per_team'] * (720.0 / r['secs'])
        tot += poss * expected_ppp(r, eff)
    return tot


def solve_efficiency(rates_y, target):
    lo, hi = 0.3, 2.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if expected_points(rates_y, mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ------------------------------------------------------------------ simulation
class _Game:
    def __init__(self, rates_y, eff_home, eff_away, rng, game_id, home_id, away_id, gamma=0.0, form_sd=0.0,
                 form_tau=FORM_TAU):
        self.r, self.eff, self.rng, self.gamma = rates_y, {1: eff_home, 0: eff_away}, rng, gamma
        self.form_sd, self.form_tau, self.form, self.form_t = form_sd, form_tau, 0.0, 0.0
        self.game_id, self.team_id = game_id, {1: home_id, 0: away_id}
        self.score = {1: 0, 0: 0}
        self.events = []
        self.play = 0
        self.last_t = 0.0
        self.locs, self.loc_rng = None, None          # set by simulate_from_expectations when locations exist

    # ---- clock helpers
    def _loc(self, cat):
        """Shot location (x, y in ft, as coordinate_x_raw / coordinate_y_raw) drawn from the training-season counts,
        with a separate random stream, so that the game itself does not depend on whether locations are drawn."""
        if not self.locs:
            return None
        cells, cum = self.locs[cat]
        i = min(bisect.bisect_right(cum, self.loc_rng.random() * cum[-1]), len(cells) - 1)
        x, y = cells[i]
        return round(x + self.loc_rng.random(), 1), round(y + self.loc_rng.random(), 1)

    def _emit(self, period, t_in_period, plen, text, team, scoring=False, shooting=False, loc=None):
        t_in_period = min(max(t_in_period, 0.0), plen)
        self.last_t = t_in_period                      # time of the latest event in the period
        left = plen - t_in_period
        if period <= 4:
            rem = (4 - period) * REG_PERIOD + left
            elapsed = (period - 1) * REG_PERIOD + t_in_period
        else:
            rem = left
            elapsed = 4 * REG_PERIOD + (period - 5) * OT_PERIOD + t_in_period
        if left >= 60:
            clock = f'{int(left // 60)}:{int(left % 60):02d}'
        else:
            clock = f'{left:.1f}' if left % 1 else f'{int(left)}.0'
        self.play += 1
        self.events.append(dict(game_id=self.game_id, game_play_number=self.play, period_number=period,
                                clock_display_value=clock, start_game_seconds_remaining=round(rem, 1),
                                game_seconds_elapsed=round(elapsed, 1), is_overtime_period=period > 4,
                                type_text=text, scoring_play=scoring, shooting_play=shooting,
                                team_id=None if team is None else self.team_id[team],
                                sequence_number=self.play, home_score=self.score[1], away_score=self.score[0],
                                shot_x=None if loc is None else loc[0], shot_y=None if loc is None else loc[1]))

    def _form_now(self, period, t):
        """In-game form of the home team relative to the away team (log factor on make probabilities): a
        mean-reverting process with standard deviation form_sd and time constant form_tau (game seconds)."""
        if self.form_sd <= 0:
            return 0.0
        now = (period - 1) * REG_PERIOD + t if period <= 4 else 4 * REG_PERIOD + (period - 5) * OT_PERIOD + t
        dt = max(now - self.form_t, 0.0)
        a = math.exp(-dt / self.form_tau)
        self.form = self.form * a + self.form_sd * math.sqrt(1 - a * a) * self.rng.gauss(0, 1)
        self.form_t = now
        return self.form

    def _duration(self, mean, lo, hi, shape=3.0):
        return min(max(self.rng.gammavariate(shape, mean / shape), lo), hi)

    # ---- one free-throw trip; returns True if the shooting team keeps the ball (offensive rebound)
    def _free_throws(self, period, t, plen, off, n, r, label):
        made_last = False
        for i in range(1, n + 1):
            made = self.rng.random() < r['ft_pct']
            if made:
                self.score[off] += 1
            self._emit(period, t, plen, f'Free throw {i} of {n}{label}' + (' made' if made else ' missed'), off,
                       scoring=made, shooting=True)
            made_last = made
        if made_last or t + 1 >= plen:
            return False
        oreb = self.rng.random() < r['p_oreb_ft']
        self._emit(period, t + 1, plen, 'Offensive rebound' if oreb else 'Defensive rebound', off if oreb else 1 - off)
        return oreb

    def play_period(self, period, first_off, jump=False):
        plen = REG_PERIOD if period <= 4 else OT_PERIOD
        key = _period_key(period)
        r = self.r[key]
        mean_poss = r['secs'] / (2 * r['poss_per_team'])          # data: seconds per possession in this period
        cont_mean = 6.0
        q_cont = r['p_fga'] * (1 - r['p_make2'] - r['p_make3']) * r['p_oreb_fg']
        base_mean = max(mean_poss - cont_mean * q_cont / (1 - q_cont), 4.0)
        t, off, cont = 0.0, first_off, False
        self._emit(period, 0.0, plen, 'Start of period', None)
        if jump:
            self._emit(period, 0.0, plen, 'Jump ball', first_off)
        while True:
            t = max(t, self.last_t)                    # a rebound is written 1 s after the shot
            left = plen - t
            if left <= 0.5:
                break
            if period >= 4 and left <= LATE_SECS:
                keep, t, over = self._late_action(period, t, plen, off, r, cont)
                if over:
                    break
                cont = keep
                if not keep:
                    off = 1 - off
                continue
            dur = self._duration(base_mean, 3.0, 24.0)
            buzzer = dur >= left
            if buzzer:
                dur = max(left - 0.3, 0.1)
            keep_ball, first, handed_over = True, True, False
            while keep_ball:
                if not first:
                    if period >= 4 and plen - t <= LATE_SECS:
                        handed_over = True                         # the end-game rules take over the possession
                        break
                    extra = self._duration(cont_mean, 1.0, 14.0, shape=2.0)
                    if t + extra >= plen:
                        t = plen
                        break
                    t += extra
                else:
                    t += dur
                    first = False
                if t >= plen:
                    break
                keep_ball = self._action(period, t, plen, off, r, heave=buzzer)
                buzzer = False
            if handed_over:
                cont = True
                continue
            off, cont = 1 - off, False
            if t >= plen:
                break
        self._emit(period, plen, plen, 'End of period', None)

    def _late_action(self, period, t, plen, off, r, cont):
        """One action in the last 60 s of the fourth quarter or of overtime, from the end-game table.
        Returns (keep_ball, t, period_over)."""
        left = plen - t
        lead = self.score[off] - self.score[1 - off]
        c = self.r['endgame'][('<=24' if left <= CLUTCH_SECS else '60-24') + '|' + _lead_bucket(lead)]
        fresh = not cont and left <= CLUTCH_SECS                   # possession starts with 24 s or less left
        sb = ('0-3' if left <= 3 else '3-8' if left <= 8 else '8-16' if left <= 16 else '16-24') if fresh else None
        src = c['by_start'][sb] if fresh else c
        if fresh and self.rng.random() < src['p_none']:          # the team runs out the clock
            return False, plen, True
        shares = (('to', src['p_to']), ('trip', src['p_trip']), ('m2', src['p_make2']), ('m3', src['p_make3']),
                  ('miss', src['p_miss']))
        u = self.rng.random() * sum(p for _, p in shares)
        for kind, p in shares:
            if u < p:
                break
            u -= p
        foul = kind == 'trip' and lead >= 1                       # deliberate foul by the trailing team
        group = 'trip' if kind == 'trip' else 'other'
        if cont:
            dt = self._duration(6.0, 1.0, 14.0, shape=2.0)        # after an offensive rebound
            if t + dt >= plen - 0.3:
                if lead <= 0:                                      # out of time: heave at the buzzer
                    self._action(period, plen - 0.3, plen, off, r, heave=True)
                return False, plen, True
        elif fresh:                                                # share of the remaining time used
            dt = left * (1.0 - _from_quantiles(c['frac_left'][f'{group}|{sb}']['q'], self.rng.random()))
            dt = min(dt, left - 0.1)
        else:
            dt = _from_quantiles(c['dt_' + group], self.rng.random())
        t += dt
        if kind == 'to':
            self._emit(period, t, plen, 'Turnover', off)
            return False, t, False
        if kind == 'trip':
            self._emit(period, t, plen, 'Personal foul' if foul else 'Shooting foul', 1 - off)
            n = 2 if foul or self.rng.random() >= r['p_trip3'] else 3
            return self._free_throws(period, t, plen, off, n, r, ''), t, False
        if kind in ('m2', 'm3'):
            pts = 2 if kind == 'm2' else 3
            self.score[off] += pts
            self._emit(period, t, plen, f'Made {pts}-pt shot', off, scoring=True, shooting=True, loc=self._loc(f'made{pts}'))
            if self.rng.random() < r['p_and1']:
                self._emit(period, t, plen, 'Shooting foul', 1 - off)
                return self._free_throws(period, t, plen, off, 1, r, ' (and-one)'), t, False
            return False, t, False
        self._emit(period, t, plen, 'Missed shot', off, shooting=True, loc=self._loc('miss'))
        if t + 1 >= plen:
            return False, t, False
        oreb = self.rng.random() < r['p_oreb_fg']
        self._emit(period, t + 1, plen, 'Offensive rebound' if oreb else 'Defensive rebound', off if oreb else 1 - off)
        return oreb, t + 1, False

    def _action(self, period, t, plen, off, r, heave=False):
        """One action of the team in possession at time t. Returns True if it keeps the ball."""
        u = self.rng.random()
        if u < r['p_to'] and not heave:
            self._emit(period, t, plen, 'Turnover', off)
            return False
        if u < r['p_to'] + r['p_trip'] and not heave:
            self._emit(period, t, plen, 'Shooting foul', 1 - off)
            n = 3 if self.rng.random() < r['p_trip3'] else 2
            return self._free_throws(period, t, plen, off, n, r, '')
        lead = self.score[off] - self.score[1 - off]
        f = self._form_now(period, t) * (0.5 if off == 1 else -0.5)
        m2, m3 = _scaled(r, self.eff[off] * math.exp(-self.gamma * lead + f))
        if heave:
            m2, m3 = m2 * 0.5, m3 * 0.5
        v = self.rng.random()
        if v < m3 or v < m2 + m3:
            pts = 3 if v < m3 else 2
            self.score[off] += pts
            self._emit(period, t, plen, f'Made {pts}-pt shot', off, scoring=True, shooting=True, loc=self._loc(f'made{pts}'))
            if self.rng.random() < r['p_and1'] and not heave:
                self._emit(period, t, plen, 'Shooting foul', 1 - off)
                return self._free_throws(period, t, plen, off, 1, r, ' (and-one)')
            return False
        self._emit(period, t, plen, 'Missed shot', off, shooting=True, loc=self._loc('miss'))
        if t + 1 >= plen:
            return False
        oreb = self.rng.random() < r['p_oreb_fg']
        self._emit(period, t + 1, plen, 'Offensive rebound' if oreb else 'Defensive rebound', off if oreb else 1 - off)
        return oreb


def simulate_game(inputs, year, home, away, seed=0, shocks=True):
    """Simulate one game. Returns (game_info dict, events DataFrame)."""
    rates_y = inputs.rates[str(year)]
    exp = inputs.expectations(year, home, away)
    return simulate_from_expectations(inputs, year, exp, seed=seed, shocks=shocks, home=home, away=away)


def simulate_from_expectations(inputs, year, exp, seed=0, shocks=True, home='HOME', away='AWAY'):
    rng = random.Random(seed)
    rates_y = inputs.rates[str(year)]
    cal = {**DEFAULT_CAL, **inputs.cal}
    em = rng.gauss(0, cal['shock_sd_margin']) if shocks else 0.0
    et = rng.gauss(0, cal['shock_sd_total']) if shocks else 0.0
    mu_m = exp['mu_m'] * cal['margin_scale'] + em          # calibrated targets: see calibrate.py
    mu_t = exp['mu_t'] * cal.get('points_scale_by_season', {}).get(str(year), cal['points_scale']) + et
    tgt_h, tgt_a = (mu_t + mu_m) / 2, (mu_t - mu_m) / 2
    eff_h, eff_a = solve_efficiency(rates_y, tgt_h), solve_efficiency(rates_y, tgt_a)
    gid = SIM_GAME_ID_BASE + int(seed)
    g = _Game(rates_y, eff_h, eff_a, rng, gid, 1, 2, gamma=cal['gamma'], form_sd=cal['form_sd'])
    if getattr(inputs, 'locs', None):
        g.locs, g.loc_rng = inputs.locs, random.Random(int(seed) * 1_000_003 + 17)
    tip = 1 if rng.random() < 0.5 else 0           # 1: home team wins the opening tip
    for period, first in ((1, tip), (2, 1 - tip), (3, 1 - tip), (4, tip)):
        g.play_period(period, first, jump=period == 1)
    reg_h, reg_a = g.score[1], g.score[0]
    period = 4
    while g.score[1] == g.score[0]:
        period += 1
        g.play_period(period, 1 if rng.random() < 0.5 else 0, jump=True)
    g._emit(period, OT_PERIOD if period > 4 else REG_PERIOD, OT_PERIOD if period > 4 else REG_PERIOD, 'End of game', None)
    ev = pd.DataFrame(g.events)
    info = dict(game_id=gid, file_year=year, home_abbrev=home, away_abbrev=away, spread_home=exp['spread'],
                mu_h=exp['mu_h'], mu_a=exp['mu_a'], mu_m=exp['mu_m'], mu_t=exp['mu_t'],
                home_end_reg=reg_h, away_end_reg=reg_a, home_final=g.score[1], away_final=g.score[0],
                n_periods=period, has_ot=period > 4, home_win_final=int(g.score[1] > g.score[0]),
                eff_home=eff_h, eff_away=eff_a, seed=seed, synthetic=True)
    return info, ev


def pick_matchup(inputs, year=None, home=None, away=None, seed=0):
    """Fill in a random season and/or random teams when they are not given."""
    rng = random.Random(seed + 7919)
    if year in (None, 'random'):
        year = rng.choice(inputs.seasons())
    year = int(year)
    teams = inputs.teams(year)
    if home in (None, 'random'):
        home = rng.choice([t for t in teams if t != away])
    if away in (None, 'random'):
        away = rng.choice([t for t in teams if t != home])
    if home == away:
        raise ValueError('home and away team must differ')
    return year, home, away
