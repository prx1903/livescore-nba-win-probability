"""Generate one synthetic game and write its events.

Usage (from the repository root):
    python -I src/simulation/simulate_game.py --home BOS --away LAL --season 2025 --seed 7
    python -I src/simulation/simulate_game.py --seed 7                      (random season and teams)
    python -I src/simulation/simulate_game.py --teams 2025                  (list the team codes of a season)

--season is the file year (2025 = season 2024-25); team strengths are the ratings after the team's last game of
that season. Writes <out>/sim_<game_id>_events.csv (columns of data/processed/pbp_clean) and
<out>/sim_<game_id>_info.json. The same seed gives the same game.
"""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import game_simulator as gs

ap = argparse.ArgumentParser()
ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(HERE)))
ap.add_argument('--home', default='random'); ap.add_argument('--away', default='random')
ap.add_argument('--season', default='random'); ap.add_argument('--seed', type=int, default=0)
ap.add_argument('--out', default=None); ap.add_argument('--teams', type=int, default=None)
a = ap.parse_args()

inp = gs.Inputs(a.repo)
if a.teams:
    print(a.teams, ' '.join(inp.teams(a.teams)))
    raise SystemExit
year, home, away = gs.pick_matchup(inp, a.season, a.home, a.away, seed=a.seed)
info, ev = gs.simulate_game(inp, year, home, away, seed=a.seed)
out = a.out or os.path.join(a.repo, 'results', 'simulation', 'games')
os.makedirs(out, exist_ok=True)
stem = os.path.join(out, f"sim_{info['game_id']}")
ev.to_csv(stem + '_events.csv', index=False)
json.dump({k: (float(v) if isinstance(v, float) else v) for k, v in info.items()}, open(stem + '_info.json', 'w'), indent=1)
print(f"{away} @ {home}, strengths of season {year - 1}-{str(year)[2:]}, seed {a.seed} (synthetic game)")
print(f"expected margin {info['mu_m']:+.1f}, expected total {info['mu_t']:.1f}, implied line {info['spread_home']:+.1f}")
print(f"final {away} {info['away_final']} - {info['home_final']} {home}"
      + (f" after {info['n_periods'] - 4} overtime(s)" if info['has_ot'] else '') + f", {len(ev)} events")
print('written', stem + '_events.csv')
