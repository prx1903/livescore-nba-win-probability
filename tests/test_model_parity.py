"""The model in the demo page (JavaScript) must give the same numbers as the Python code:
  ScoreModel.state = src/v2/refmodel.py        (score-distribution model, results/v2/sim_params.json)
Random game states, including the first and last second, period boundaries and overtime.
Run: python tests/test_model_parity.py   (needs Node; skipped with a message if Node is not installed)"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src')); sys.path.insert(0, os.path.join(HERE, '..', 'src', 'v2')); sys.path.insert(0, HERE)
import _js

ROOT = _js.ROOT
TOL = 1e-9


def random_state(rng):
    per = rng.choice([1, 2, 3, 4, 4, 5, 6])
    if per <= 4:
        t = rng.choice([(per - 1) * 720.0, per * 720.0, (per - 1) * 720 + rng.uniform(0, 720), per * 720 - rng.uniform(0, 5)])
    else:
        t = 2880 + 300 * (per - 5) + rng.choice([0.0, 300.0, rng.uniform(0, 300)])
    h, a = rng.randint(0, 130), rng.randint(0, 130)
    if rng.random() < 0.3:
        a = h + rng.choice([-2, -1, 0, 1, 2])                       # close games: the tie band matters
    starts = None
    if rng.random() < 0.7:
        starts = {str(j): [rng.randint(-20, 20), rng.randint(0, 200)] for j in range(1, min(per, 4) + 1)}
    return dict(t=t, per=per, h=h, a=a, mu_m=rng.uniform(-15, 15), mu_t=rng.uniform(190, 250), starts=starts)


def differences(x, y, path=''):
    """Largest absolute difference between two results (numbers, lists and dicts with the same shape)."""
    if x is None or y is None:
        assert x is None and y is None, path
        return 0.0
    if isinstance(x, dict):
        return max(differences(x[k], y[k], path + '/' + k) for k in x)
    if isinstance(x, list):
        assert len(x) == len(y), path
        return max([differences(u, v, path) for u, v in zip(x, y)] or [0.0])
    return abs(x - y)


def test_score_model_matches_python():
    if not _js.node():
        return 'skip: Node is not installed'
    from refmodel import Ref
    ref = Ref(json.load(open(os.path.join(ROOT, 'results', 'v2', 'sim_params.json'), encoding='utf-8')))
    rng = random.Random(2)
    states = [random_state(rng) for _ in range(4000)]
    src = _js.page_source()
    module = open(os.path.join(ROOT, 'app', 'demo', 'src', 'js', '25_models.js'), encoding='utf-8').read()
    assert module in src.replace('\r\n', '\n'), 'docs/index.html does not contain js/25_models.js as it is on disk'
    code = _js.js_const(src, 'MODEL') + '\n' + module + '''
    console.log(JSON.stringify(INPUT.map(s=>{
      const ms=s.starts?Object.fromEntries(Object.entries(s.starts).map(([j,v])=>[j,v[0]])):null;
      const ts=s.starts?Object.fromEntries(Object.entries(s.starts).map(([j,v])=>[j,v[1]])):null;
      return ScoreModel.state(s.t,s.per,s.h,s.a,s.mu_m,s.mu_t,ms,ts)})));'''
    js = _js.run_node(code, states)
    worst = 0.0
    for s, out in zip(states, js):
        ms = {int(j): v[0] for j, v in s['starts'].items()} if s['starts'] else None
        ts = {int(j): v[1] for j, v in s['starts'].items()} if s['starts'] else None
        py = ref.state(s['t'], s['per'], s['h'], s['a'], s['mu_m'], s['mu_t'], ms, ts)
        d = differences(py, {k: out[k] for k in py}, str(s))
        assert d < TOL, (d, s)
        assert 0 <= py['pw'] <= 1 and 0 <= py['pot'] <= 1
        worst = max(worst, d)
    return f'{len(states)} states, largest difference {worst:.1e}'


if __name__ == '__main__':
    _js.run_tests(globals())
