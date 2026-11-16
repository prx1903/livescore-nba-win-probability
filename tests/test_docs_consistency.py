"""Numbers written in the documentation must match the data and result files, and every third-party package
that the code imports must be listed in requirements.txt.
Run: python tests/test_docs_consistency.py"""
import csv, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _js

ROOT = _js.ROOT
read = lambda *p: open(os.path.join(ROOT, *p), encoding='utf-8').read()
PIP_NAME = {'sklearn': 'scikit-learn'}                      # import name -> package name, where they differ


def test_invalid_game_count_in_data_readme():
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'data', 'processed', 'games.csv'), encoding='utf-8')))
    invalid = [r for r in rows if r['is_valid'] != 'True']
    conflict = sum(r['final_conflict'] == 'True' for r in invalid)
    txt = read('data', 'README.md')
    stated = [int(x) for x in re.findall(r'(\d+) invalid games', txt)]
    assert stated and all(x == len(invalid) for x in stated), (stated, len(invalid))
    assert f'{conflict} with a score conflict' in txt and f'{len(invalid) - conflict} incomplete records' in txt


def test_results_table_in_readme():
    rep, met = read('results', 'baseline_report.txt'), json.loads(read('results', 'v2', 'metrics.json'))['win']
    test = rep.split('== TEST')[1]
    ll_s, br_s = re.search(r'pregame_only\(spread\)\s+logloss=([\d.]+) brier=([\d.]+)', test).groups()
    ll_m, br_m = re.search(r'S3 \S+\s+logloss=([\d.]+) brier=([\d.]+)', test).groups()
    diff, lo, hi = re.search(r'ort=(-[\d.]+) %95 aralık=\[(-[\d.]+), (-[\d.]+)\]', rep).groups()
    readme = read('README.md')
    for cell in (f'| {br_s} | {ll_s} |', f'| **{br_m}** | **{ll_m}** |', f"| {met['brier_new']:.4f} | {met['ll_new']:.4f} |"):
        assert cell in readme, cell
    minus = lambda x: x.replace('-', '−')
    assert f'{minus(diff)}, 95% game-clustered bootstrap interval [{minus(lo)}, {minus(hi)}]' in readme


def test_demo_notes_numbers():
    day, notes = json.loads(read('app', 'demo', 'day_data.json')), read('app', 'demo', 'NOTES.md')
    gaps = [b[0] - a[0] for g in day['games'] for a, b in zip(g['ev'], g['ev'][1:])]
    mean, mx = re.search(r'on average (\d+), at most (\d+) game seconds apart', notes).groups()
    assert int(mean) == round(sum(gaps) / len(gaps)) and int(mx) == max(gaps), (mean, mx, max(gaps))
    from test_demo_page import game_brier
    sm = sp = n = 0
    for g in day['games']:
        if not g.get('syn'):
            a, b, c = game_brier(g); sm += a; sp += b; n += c
    m, p = re.search(r'model ([\d.]+), pre-game probability alone ([\d.]+)', notes).groups()
    assert (m, p) == (f'{sm / n:.3f}', f'{sp / n:.3f}'), (m, p, sm / n, sp / n)


def test_imported_packages_are_in_requirements():
    req = {re.split(r'[<>=!~\s#]', line, maxsplit=1)[0].lower() for line in read('requirements.txt').splitlines()
           if line.strip() and not line.startswith('#')}
    local, imported = set(), {}
    for top in ('src', 'app', 'tests'):
        for d, _, files in os.walk(os.path.join(ROOT, top)):
            for f in files:
                if f.endswith('.py'):
                    local.add(f[:-3])
                    for line in open(os.path.join(d, f), encoding='utf-8'):
                        m = re.match(r'\s*(?:import\s+([A-Za-z_]\w*)|from\s+([A-Za-z_]\w*)[\w.]*\s+import\b)', line)
                        if m:
                            imported.setdefault(m.group(1) or m.group(2), os.path.join(top, f))
    std = set(getattr(sys, 'stdlib_module_names', ())) or None
    if std is None:
        return 'skip: needs Python 3.10 or newer'
    missing = {mod: where for mod, where in imported.items()
               if mod not in std and mod not in local and PIP_NAME.get(mod, mod).lower() not in req}
    assert not missing, f'imported but not in requirements.txt: {missing}'


if __name__ == '__main__':
    _js.run_tests(globals())
