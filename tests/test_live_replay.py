"""Command-line behaviour of src/live_replay.py: clear messages for wrong arguments, a generated game from start
to end, and a feed in which no event can be accepted.
Run: python tests/test_live_replay.py"""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _js

ROOT = _js.ROOT
MODEL = os.path.join(ROOT, 'models', 'model_coefficients.json')
DATA = os.path.join(ROOT, 'data', 'processed')


def replay(*args, cwd=None):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([sys.executable, os.path.join(ROOT, 'src', 'live_replay.py'), *args], capture_output=True,
                          text=True, encoding='utf-8', env=env, cwd=cwd or tempfile.gettempdir())


def test_list_needs_no_model():
    r = replay('--data', DATA, '--list')
    assert r.returncode == 0 and 'home_abbrev' in r.stdout, r.stderr[-500:]


def test_missing_game_id_is_explained():
    r = replay('--data', DATA, '--model', MODEL)
    assert r.returncode == 2 and '--game' in r.stderr and 'Traceback' not in r.stderr, r.stderr[-500:]


def test_unknown_game_id_is_explained():
    r = replay('--data', DATA, '--model', MODEL, '--game', '123')
    assert r.returncode == 2 and '123' in r.stderr and 'Traceback' not in r.stderr, r.stderr[-500:]


def test_generated_game_runs_to_the_end():
    with tempfile.TemporaryDirectory() as d:
        r = replay('--model', MODEL, '--sim', '--home', 'BOS', '--away', 'LAL', '--season', '2025', '--sim-seed', '7',
                   '--speed', '0', '--out', os.path.join(d, 'state.json'), cwd=d)
        assert r.returncode == 0 and 'Bitti.' in r.stdout and 'atlanan: 0' in r.stdout, r.stderr[-500:]


def test_feed_without_any_valid_event_does_not_crash():
    import pandas as pd
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'pbp_clean'))
        pd.DataFrame([dict(game_id=1, file_year=2026, game_date='2026-01-01', home_abbrev='AAA', away_abbrev='BBB',
                           spread_home=2.5, home_final=100, away_final=90, home_win_final=1, is_valid=True,
                           has_ot=False)]).to_csv(os.path.join(d, 'games.csv'), index=False)
        pd.DataFrame([dict(game_id=1, game_play_number=i + 1, period_number=1, clock_display_value='12:00',
                           start_game_seconds_remaining=2880.0, game_seconds_elapsed=float(i), type_text='x',
                           home_score=float('nan'), away_score=float('nan')) for i in range(3)]
                     ).to_parquet(os.path.join(d, 'pbp_clean', 'pbp_clean_2026.parquet'), index=False)
        r = replay('--data', d, '--model', MODEL, '--game', '1', '--speed', '0', '--out', os.path.join(d, 's.json'), cwd=d)
        assert r.returncode == 0 and 'Kabul edilen olay yok' in r.stdout and 'atlanan: 3' in r.stdout, r.stderr[-800:]


if __name__ == '__main__':
    _js.run_tests(globals())
