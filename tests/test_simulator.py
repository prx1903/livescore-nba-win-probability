"""Tests of the game simulator (src/simulation). Run: python -m pytest tests  (without pytest: python tests/test_simulator.py)
Needs results/v2/pregame.parquet, ratings_params.json, sim_params.json and results/simulation/rates.json,
calibration.json, shot_locations.json."""
import os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'src', 'simulation'))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import game_simulator as gs
from feed_checks import FeedState, check_event

INP = gs.Inputs(ROOT)
COLS = ['game_id', 'game_play_number', 'period_number', 'clock_display_value', 'start_game_seconds_remaining',
        'game_seconds_elapsed', 'is_overtime_period', 'type_text', 'scoring_play', 'shooting_play', 'team_id',
        'sequence_number', 'home_score', 'away_score', 'shot_x', 'shot_y']


def _game(seed=3):
    year, home, away = gs.pick_matchup(INP, 2025, 'BOS', 'LAL', seed=seed)
    return gs.simulate_game(INP, year, home, away, seed=seed)


def test_same_seed_same_game():
    a, ea = _game(5)
    b, eb = _game(5)
    assert a['home_final'] == b['home_final'] and a['away_final'] == b['away_final'] and ea.equals(eb)


def test_columns_and_order():
    info, ev = _game()
    assert list(ev.columns) == COLS
    assert ev.game_play_number.is_monotonic_increasing
    assert ev.game_seconds_elapsed.is_monotonic_increasing
    assert ev.home_score.is_monotonic_increasing and ev.away_score.is_monotonic_increasing
    assert (ev.start_game_seconds_remaining >= 0).all()


def test_final_score_and_winner():
    for seed in range(20):
        info, ev = _game(seed)
        last = ev.iloc[-1]
        assert (last.home_score, last.away_score) == (info['home_final'], info['away_final'])
        assert info['home_final'] != info['away_final']
        assert info['has_ot'] == (info['home_end_reg'] == info['away_end_reg'])
        assert info['n_periods'] == ev.period_number.max()


def test_points_match_scoring_events():
    info, ev = _game(8)
    d = (ev.home_score + ev.away_score).diff().fillna(ev.home_score.iloc[0] + ev.away_score.iloc[0])
    assert ((d > 0) == ev.scoring_play.astype(bool)).all()


def test_feed_checks_accept_every_event():
    for seed in range(10):
        info, ev = _game(seed)
        st = FeedState()
        for e in ev.itertuples():
            ok, w = check_event(st, e.home_score, e.away_score, e.period_number, e.game_seconds_elapsed,
                                e.start_game_seconds_remaining, seq=e.game_play_number)
            assert ok and w == []


def test_shot_locations():
    info, ev = _game(4)
    fga = ev[ev.shooting_play & ~ev.type_text.str.startswith('Free')]
    other = ev.drop(fga.index)
    assert fga.shot_x.notna().all() and other.shot_x.isna().all()
    assert fga.shot_x.between(0, 50).all() and fga.shot_y.between(-5, 47).all()
    m3 = fga[fga.type_text == 'Made 3-pt shot']
    assert (((m3.shot_x - 25) ** 2 + m3.shot_y ** 2) ** 0.5 > 20.5).all()


def test_random_matchup_is_valid():
    year, home, away = gs.pick_matchup(INP, seed=11)
    assert year in INP.seasons() and home != away and home in INP.teams(year) and away in INP.teams(year)


if __name__ == '__main__':
    for name, f in list(globals().items()):
        if name.startswith('test_'):
            f(); print('ok', name)
