"""Builds the demo page: docs/index.html, one self-contained file.

Sources (edit these, never docs/index.html itself):
  app/demo/src/page.html     page structure; the lines /*@style*/, /*@data*/ and /*@script*/ are filled in here
  app/demo/src/style.css     styles
  app/demo/src/js/*.js       page code, joined in file-name order
  app/demo/day_data.json     the games of the day (built by build_day_data.py)
  results/baseline_report.txt, results/season_type_report.txt   accuracy numbers shown in the Model view
  models/model_coefficients.json, results/v2/sim_params.json    parameters of the two models used in the page

Usage (from the repository root): python -I app/demo/build_page.py [output file]   -> docs/index.html
tests/test_demo_page.py checks that docs/index.html is exactly what this script builds."""
import json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
SRC = os.path.join(ROOT, 'app', 'demo', 'src')


def read(*parts):
    return open(os.path.join(*parts), encoding='utf-8', newline='').read()


def find(pattern, text, what):
    m = re.search(pattern, text, flags=re.M)
    if not m:
        raise SystemExit(f'build_page: could not read {what}; has the report format changed?')
    return m.groups()


def accuracy():
    """Accuracy numbers of the delivered model on the test seasons, read from the text reports in results/."""
    rep = read(ROOT, 'results', 'baseline_report.txt')
    test = rep.split('== TEST')[1]
    best, = find(r'Seçilen özellik kümesi \(doğrulama Brier\): (.+)$', rep, 'the selected feature set')
    ll, br = find(r'^' + re.escape(best.strip()) + r'\s+logloss=([\d.]+) brier=([\d.]+)$', test, 'the test scores of the model')
    _, br_spread = find(r'^pregame_only\(spread\)\s+logloss=([\d.]+) brier=([\d.]+)$', test, 'the test scores of the line alone')
    cal = [dict(n=int(n), p=float(p), o=float(o))
           for n, p, o in re.findall(r'n=\s*(\d+) tahmin=([\d.]+) gerçek=([\d.]+)', rep)]
    by_time = {lab: dict(n=int(n), m=float(m), s=float(s))
               for lab, n, m, s in re.findall(r'^\s+(\S+)\s+n=\s*(\d+) model=([\d.]+) spread=([\d.]+)$', rep, re.M)}
    order = ['36-48dk', '24-36dk', '12-24dk', '5-12dk', '<5dk', 'OT']      # first quarter ... last 5 minutes, overtime
    if len(cal) != 10 or set(by_time) != set(order):
        raise SystemExit('build_page: calibration or time table of baseline_report.txt has an unexpected shape')
    st = read(ROOT, 'results', 'season_type_report.txt')
    rows = []
    for lab, key in (('normal sezon', 'regular'), ('playoff', 'playoff'), ('play-in', 'playin')):
        n, snaps, _, b, lo, hi, l = find(rf'^{lab}\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+\[([\d.]+),\s*([\d.]+)\]\s+([\d.]+)\s*$',
                                         st, 'the row "' + lab + '" of season_type_report.txt')
        rows.append(dict(key=key, n=int(n), snaps=int(snaps), brier=float(b), lo=float(lo), hi=float(hi), ll=float(l)))
    diff = [float(x) for x in find(r'Playoff - normal sezon Brier farkı: ([+-][\d.]+)\s+%95 aralık \[([+-][\d.]+), ([+-][\d.]+)\]',
                                   st, 'the playoff difference')]
    return {'cal': cal, 'time': [by_time[b] for b in order],
            'overall': {'m': float(br), 's': float(br_spread), 'll': float(ll), 'n': sum(c['n'] for c in cal),
                        'games': sum(r['n'] for r in rows)},
            'season': {'rows': rows, 'diff': diff}}


def models():
    """Parameters of the logistic model (LOGIT) and of the score-distribution model (MODEL) for the page code."""
    wp = json.loads(read(ROOT, 'models', 'model_coefficients.json'))
    sim = json.loads(read(ROOT, 'results', 'v2', 'sim_params.json'))
    if sim['kt'] is not None or sim['km'] is not None or set(sim['beta']) != {'ms'}:
        raise SystemExit('build_page: sim_params.json has terms that the page code (js/25_models.js) does not implement')
    model = {k: sim[k] for k in ('share', 'Vm', 'Vt', 'Cmt', 'h', 'H_EDGES', 'v_per', 'OT')}
    model['b'] = sim['beta']['ms']
    return {k: wp[k] for k in ('features', 'intercept', 'coef')}, model


def data_block():
    """The generated JavaScript constants (one line each)."""
    day = json.load(open(os.path.join(ROOT, 'app', 'demo', 'day_data.json'), encoding='utf-8'))
    dumps = lambda x: json.dumps(x, ensure_ascii=False, separators=(',', ':'))
    wp, model = models()
    return ('const DAY=' + dumps(day) + ';\nconst ACC=' + dumps(accuracy()) + ';\nconst LOGIT=' + dumps(wp)
            + ';\nconst MODEL=' + dumps(model) + ';\n')


def build():
    js_dir = os.path.join(SRC, 'js')
    script = ''.join(read(js_dir, f) for f in sorted(os.listdir(js_dir)) if f.endswith('.js'))
    page = read(SRC, 'page.html')
    for marker, content in (('/*@style*/\n', read(SRC, 'style.css')), ('/*@data*/\n', data_block()), ('/*@script*/\n', script)):
        assert page.count(marker) == 1, 'marker must appear exactly once in page.html: ' + marker.strip()
        page = page.replace(marker, content)
    return page


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'docs', 'index.html')
    html = build()
    open(out, 'w', encoding='utf-8', newline='').write(html)
    print('built', out, '|', len(html.encode('utf-8')), 'bytes')
