"""The feed checks of the demo page (JavaScript, docs/index.html) must behave exactly like src/feed_checks.py:
same decision, same warning texts and same state after every event. Random event streams with injected faults
(missing fields, repeated and skipped sequence numbers, clock going back, score drops, period jumps, long gaps).
Run: python tests/test_feed_parity.py   (needs Node; skipped with a message if Node is not installed)"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src')); sys.path.insert(0, HERE)
from feed_checks import FeedState, check_event
import _js

N_GAMES, N_EVENTS = 200, 80


def random_games(seed=0):
    rng, games = random.Random(seed), []
    for _ in range(N_GAMES):
        h = a = 0; per = 1; el = 0.0; seq = rng.choice([-1, 0, 0, 4]); evs = []   # first number 0, 1, 1 or 5
        for _ in range(N_EVENTS):
            el += rng.choice([0, 0.4, 0.5, 3, 7, 12.5, 20, 35, 119.5, 120.5, 200])
            h += rng.choice([0, 0, 0, 1, 2, 3]); a += rng.choice([0, 0, 0, 1, 2, 3])
            if rng.random() < 0.03:
                per += rng.choice([1, 2, 3])
            seq += 1
            e = dict(home=h, away=a, period=per, elapsed=el, secs_left=max(2880 - el, 0.0), seq=seq)
            u = rng.random()
            if u < 0.04:
                e[rng.choice(['home', 'away', 'period', 'elapsed', 'secs_left'])] = None
            elif u < 0.08:
                e['seq'] = seq - rng.choice([0, 1, 2, 5])
            elif u < 0.12:
                seq += rng.choice([1, 2, 7]); e['seq'] = seq
            elif u < 0.16:
                e['elapsed'] = el - rng.choice([0.4, 0.5, 0.6, 1.5, 2.5, 30])
            elif u < 0.20:
                e[rng.choice(['home', 'away'])] -= rng.choice([1, 2, 3])
            elif u < 0.23:
                e['seq'] = None
            elif u < 0.26:
                e['home'] = h + 0.7
            evs.append(e)
        games.append(evs)
    return games


HARNESS = """
const out=INPUT.map(evs=>{const S=feedNew();return evs.map(e=>{
  const r=feedCheck(S,e.home,e.away,e.period,e.elapsed,e.secs_left,e.seq);
  return {ok:r.ok,w:r.w,home:S.home,away:S.away,period:S.period,elapsed:S.elapsed,acc:S.nAcc,rej:S.nRej,warn:S.nWarn,seq:S.lastSeq}})});
console.log(JSON.stringify(out));
"""


def test_javascript_checks_match_python():
    if not _js.node():
        return 'skip: Node is not installed'
    src, games = _js.page_source(), random_games()
    code = '\n'.join([_js.js_const(src, 'FEED'), _js.js_const(src, 'isMiss'), _js.js_function(src, 'f0'),
                      _js.js_function(src, 'feedNew'), _js.js_function(src, 'feedCheck'), HARNESS])
    js = _js.run_node(code, games)
    n = n_warn = n_rej = 0
    for gi, evs in enumerate(games):
        s = FeedState()
        for ei, e in enumerate(evs):
            ok, w = check_event(s, e['home'], e['away'], e['period'], e['elapsed'], e['secs_left'], seq=e['seq'])
            py = dict(ok=ok, w=w, home=s.home, away=s.away, period=s.period, elapsed=s.elapsed, acc=s.n_accepted,
                      rej=s.n_rejected, warn=s.n_warnings, seq=s.last_seq)
            assert py == js[gi][ei], f'game {gi} event {ei}: {e}\n python {py}\n page   {js[gi][ei]}'
            n += 1; n_warn += len(w); n_rej += not ok
    assert n == N_GAMES * N_EVENTS and n_warn > 1000 and n_rej > 1000, (n, n_warn, n_rej)
    return f'{n} events, {n_warn} warnings, {n_rej} rejected: identical'


if __name__ == '__main__':
    _js.run_tests(globals())
