"""Checks of the demo page (docs/index.html).
  1. The numbers written on the page are the numbers in results/ (accuracy tiles, calibration, error by time, season types).
  2. The embedded day data is app/demo/day_data.json.
  3. Small page functions run in Node: state of a finished game, order of the game list, per-game Brier score.
Run: python tests/test_demo_page.py   (part 3 needs Node; skipped with a message if Node is not installed)"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _js

ROOT = _js.ROOT
SRC = _js.page_source()
DAY = json.load(open(os.path.join(ROOT, 'app', 'demo', 'day_data.json'), encoding='utf-8'))
REPORT = open(os.path.join(ROOT, 'results', 'baseline_report.txt'), encoding='utf-8').read()
tr = lambda x, d: f'{x:.{d}f}'.replace('.', ',')                 # 0.1519 -> '0,1519'
tr_int = lambda n: f'{n:,}'.replace(',', '.')                      # 254328 -> '254.328'


def report_numbers():
    test = REPORT.split('== TEST')[1]
    brier = {m.group(1).strip(): (float(m.group(2)), float(m.group(3)))
             for m in re.finditer(r'^(\S.*?)\s+logloss=([\d.]+) brier=([\d.]+)$', test, re.M)}
    best = re.search(r'Seçilen özellik kümesi \(doğrulama Brier\): (.+)', REPORT).group(1).strip()
    cal = [dict(n=int(n), p=float(p), o=float(o))
           for n, p, o in re.findall(r'n=\s*(\d+) tahmin=([\d.]+) gerçek=([\d.]+)', REPORT)]
    time = {lab: dict(n=int(n), m=float(m), s=float(s))
            for lab, n, m, s in re.findall(r'^\s+(\S+)\s+n=\s*(\d+) model=([\d.]+) spread=([\d.]+)$', REPORT, re.M)}
    return brier[best], brier['pregame_only(spread)'], cal, time


def tiles():
    return {k: v for v, k in re.findall(r'<div class="tile"><div class="v">([^<]+)</div><div class="k">([^<]+)</div></div>', SRC)}


def test_embedded_day_data_is_day_data_json():
    assert _js.json_const(SRC, 'DAY') == DAY


def test_page_is_what_build_page_builds():
    # docs/index.html must never be edited by hand: it is the output of app/demo/build_page.py
    import importlib.util
    spec = importlib.util.spec_from_file_location('build_page', os.path.join(ROOT, 'app', 'demo', 'build_page.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.build() == open(_js.PAGE, encoding='utf-8', newline='').read(), 'run: python -I app/demo/build_page.py'


def test_page_structure_is_balanced():
    # a missing or extra </div> silently moves a whole column of the page
    html = open(os.path.join(ROOT, 'app', 'demo', 'src', 'page.html'), encoding='utf-8').read()
    assert len(re.findall(r'<div\b', html)) == len(re.findall(r'</div>', html))


def test_page_script_parses():
    # the page is one script: a name declared twice (in two source files) would stop the whole page
    if not _js.node():
        return 'skip: Node is not installed'
    import subprocess, tempfile
    script = SRC[SRC.index('<script>') + 8:SRC.rindex('</script>')]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'page.js')
        open(path, 'w', encoding='utf-8').write(script)
        r = subprocess.run([_js.node(), '--check', path], capture_output=True, text=True, encoding='utf-8')
    assert r.returncode == 0, r.stderr[:600]


def test_accuracy_numbers_match_result_files():
    # the page shows the score-distribution model (results/v2/metrics.json); the line alone and the logistic model
    # (comparison) come from results/baseline_report.txt
    (ll, br), (_, br_spread), cal, time = report_numbers()
    met = json.load(open(os.path.join(ROOT, 'results', 'v2', 'metrics.json'), encoding='utf-8'))
    acc = _js.json_const(SRC, 'ACC')
    assert acc['cal'] == [dict(n=c['n'], p=round(c['pred'], 3), o=round(c['obs'], 3)) for c in met['calib']]
    order = ['36-48dk', '24-36dk', '12-24dk', '5-12dk', '<5dk', 'OT']            # page order: first quarter ... overtime
    assert acc['time'] == [dict(n=b['n'], m=round(b['new'], 4), s=time[o]['s']) for b, o in zip(met['buckets'], order)]
    assert [b['n'] for b in met['buckets']] == [time[o]['n'] for o in order]     # both files describe the same snapshots
    o, w = acc['overall'], met['win']
    assert (o['m'], o['ll'], o['n'], o['s']) == (round(w['brier_new'], 4), round(w['ll_new'], 4), w['n'], br_spread)
    assert o['logit'] == {'m': br, 'll': ll} and o['diff'] == [round(x, 4) for x in w['diff_new_delivered']]
    # the tiles and notes are written by the page from ACC; no accuracy number may be typed into the sources
    for typed in (tr(o['m'], 4), tr(br, 4), tr(ll, 4), tr_int(o['n']), tr_int(o['games'])):
        assert typed not in SRC, typed


def test_probability_text_is_never_certain_before_the_end():
    if not _js.node():
        return 'skip: Node is not installed'
    code = '\n'.join(_js.js_const(SRC, k) for k in ('pct', 'pcr', 'pcs', 'pcsA')) + '\nconsole.log(JSON.stringify(INPUT.map(([p,f])=>[pcs(p,f),pcsA(p,f)])));'
    out = _js.run_node(code, [[1, False], [0.996, False], [0.994, False], [0.004, False], [0, False], [0.5, False], [1, True], [0, True]])
    assert [x[0] for x in out] == ['>%99', '>%99', '%99', '<%1', '<%1', '%50', '%100', '%0'], out
    assert [x[1] for x in out] == ['<%1', '<%1', '%1', '>%99', '>%99', '%50', '%0', '%100'], out      # the two teams add up to 100
    # every probability of the match screen goes through pcs
    for old in ("'%'+(ph>=50?ph:100-ph)", '%${100-ph}</span>', '%${ph}</span>'):
        assert old not in SRC, old


def test_score_range_panel_adds_up():
    if not _js.node():
        return 'skip: Node is not installed'
    module = open(os.path.join(ROOT, 'app', 'demo', 'src', 'js', '25_models.js'), encoding='utf-8').read()
    code = '\n'.join([_js.js_const(SRC, 'MODEL'), module, _js.js_function(SRC, 'distCells'), '''
    console.log(JSON.stringify(INPUT.map(s=>{const sm=ScoreModel.state(s[0],s[1],s[2],s[3],s[4],s[5],null,null);
      return {c:distCells(sm),pot:sm.pot,pw:sm.pw,ot:sm.ot,q:sm.q}})));'''])
    states = [[0, 1, 0, 0, 6.2, 228.0], [1500, 3, 60, 71, -3.0, 231.0], [2870, 4, 101, 100, 1.0, 225.0], [2880, 4, 99, 99, 0.0, 220.0],
              [3000, 5, 110, 108, 4.0, 230.0]]
    for s, r in zip(states, _js.run_node(code, states)):
        c = r['c']
        assert len(c) == 7 and abs(sum(c) - 1) < 1e-9 and all(x >= 0 for x in c), (s, c)
        if not r['ot']:
            # the middle range is the overtime probability; home ranges + its share of overtime = win probability
            assert abs(c[3] - r['pot']) < 1e-9 and abs(sum(c[4:]) + c[3] * r['q'] - r['pw']) < 1e-6, (s, r)


def test_always_fifty_tile_is_one_quarter():
    # a forecast of 50% for both teams has a Brier score of exactly 0.25, whatever the results are
    assert tiles()['Hep %50 deseydik Brier'] == '0,2500'


def test_season_type_table_matches_report():
    txt = open(os.path.join(ROOT, 'results', 'season_type_report.txt'), encoding='utf-8').read()
    season = _js.json_const(SRC, 'ACC')['season']
    for (lab, key), row in zip((('normal sezon', 'regular'), ('playoff', 'playoff'), ('play-in', 'playin')), season['rows']):
        n, snaps, _, br, lo, hi, ll = re.search(
            rf'^{lab}\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+\[([\d.]+),\s*([\d.]+)\]\s+([\d.]+)\s*$', txt, re.M).groups()
        assert row == dict(key=key, n=int(n), snaps=int(snaps), brier=float(br), lo=float(lo), hi=float(hi), ll=float(ll))
    diff = re.search(r'Brier farkı: ([+-][\d.]+)\s+%95 aralık \[([+-][\d.]+), ([+-][\d.]+)\]', txt).groups()
    assert season['diff'] == [float(x) for x in diff]
    assert _js.json_const(SRC, 'ACC')['overall']['games'] == sum(r['n'] for r in season['rows'])


def test_finished_game_shows_the_result_not_a_forecast():
    if not _js.node():
        return 'skip: Node is not installed'
    code = 'let T=INPUT.T;\n' + _js.js_function(SRC, 'stateOf') + '''
    console.log(JSON.stringify(INPUT.games.map(g=>{const st=stateOf(g);return [st.s,st.p,st.h,st.a]})));'''
    out = _js.run_node(code, {'T': DAY['dayEnd'], 'games': DAY['games']})
    one_point = 0
    for g, (s, p, h, a) in zip(DAY['games'], out):
        assert s == 'final' and p == (1 if h > a else 0), (g['away'], g['home'], s, p, h, a)
        one_point += abs(h - a) == 1
    assert one_point >= 3                    # the cases that used to show 99% / 1%
    # a live game still shows the model probability of the last event that arrived
    g = DAY['games'][0]
    code = 'let T=INPUT.T;\n' + _js.js_function(SRC, 'stateOf') + 'console.log(JSON.stringify(stateOf(INPUT.g)));'
    st = _js.run_node(code, {'T': g['tip'] + 1000.5, 'g': g})
    last = [e for e in g['ev'] if e[0] <= 1000.5][-1]
    assert st['s'] == 'live' and st['p'] == last[1] and (st['h'], st['a']) == (last[2], last[3])


def test_arrow_keys_follow_the_order_shown_in_the_list():
    if not _js.node():
        return 'skip: Node is not installed'
    code = _js.js_function(SRC, 'listOrder') + '''
    console.log(JSON.stringify(INPUT.map(([st,f])=>listOrder(st.map(s=>({s})),f).map(g=>[g.k,g.ix]))));'''
    st = ['final', 'final', 'live', 'live', 'pre', 'live', 'pre', 'live']
    out = _js.run_node(code, [[st, 'all'], [st, 'pre'], [['pre'] * 3, 'live']])
    assert out[0] == [['live', [2, 3, 5, 7]], ['pre', [4, 6]], ['final', [0, 1]]]
    assert out[1] == [['pre', [4, 6]]] and out[2] == []
    # the key handler and the list must both be built from listOrder
    assert SRC.count('listOrder(ST,filt)') >= 3


def game_brier(g):
    """Per-game Brier score with the snapshot rule of the test (every 60 s, k = 2880 excluded)."""
    ev, dur = g['ev'], g['ev'][-1][0]
    y = 1 if ev[-1][2] > ev[-1][3] else 0
    k = sm = n = 0
    for t in range(0, dur, 60):
        while k < len(ev) and ev[k][0] <= t:
            k += 1
        if t == 2880:
            continue
        p = ev[k - 1][1] if k else g['pre']
        sm += (p - y) ** 2; n += 1
    return sm, n * (g['pre'] - y) ** 2, n


def test_per_game_brier_uses_the_snapshot_rule_of_the_test():
    if not _js.node():
        return 'skip: Node is not installed'
    code = _js.js_function(SRC, 'gameBrier') + 'console.log(JSON.stringify(INPUT.map(g=>{const b=gameBrier(g);return [b.m,b.p0,b.n]})));'
    out = _js.run_node(code, DAY['games'])
    assert any(g['ot'] for g in DAY['games'])
    for g, (m, p0, n) in zip(DAY['games'], out):
        em, ep, en = game_brier(g)
        assert n == en and abs(m - em) < 1e-9 and abs(p0 - ep) < 1e-9, (g['away'], g['home'], n, en)
    # the page must measure on the original events, not on the events left by a feed test
    assert 'gameBrier(G[' not in SRC and 'gameBrier(g)' not in SRC.replace('function gameBrier(g)', '')


if __name__ == '__main__':
    _js.run_tests(globals())
