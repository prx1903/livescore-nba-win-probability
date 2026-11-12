"""Ileri yonlu dogrulama: aday modelleri ayni an goruntuleri ve ayni bolmelerle olcer.
TEST SEZONLARINA (2023-2026) BU BETIK HIC DOKUNMAZ.

Kullanim: python3 -I run_validation.py <config.json>
Cikti: <out_dir>/validation_table.csv, validation_report.txt, selection.json, versions.json, config.json
"""
import sys, os, json, time, platform, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import candidates as C
import metrics as M

cfg = json.load(open(sys.argv[1], encoding='utf-8'))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
p = lambda x: x if os.path.isabs(x) else os.path.join(ROOT, x)
OUT = p(cfg['out_dir']); os.makedirs(OUT, exist_ok=True)

S = pd.read_parquet(p(cfg['snapshots']))
TEST_MIN = cfg['final']['test_min']
S = S[S.year < TEST_MIN].copy()          # guvenlik: test sezonlari bu betige hic girmez
print('dogrulama icin an goruntusu:', len(S), '| yillar:', sorted(S.year.unique()))

rows, log_lines = [], []
def log(t=''):
    print(t, flush=True); log_lines.append(t)

def grid(d):
    keys = list(d)
    return [dict(zip(keys, v)) for v in itertools.product(*[d[k] for k in keys])]

def evaluate(name, make, use_calib=False, window=None):
    """make() -> aday nesnesi. Her fold icin egit, dogrulama sezonunda olc.
    window=N ise egitim yalnizca fold'dan onceki son N sezonla yapilir."""
    per = []
    for f in cfg['folds']:
        tmax = f['train_max_inner'] if use_calib else f['train_max']
        tmin = cfg['train_min'] if window is None else max(cfg['train_min'], tmax - window + 1)
        tr = S[(S.year >= tmin) & (S.year <= tmax)]
        cal = S[S.year == f['calib']] if use_calib else None
        va = S[S.year == f['val']]
        t0 = time.time()
        cand = make()
        obj = cand.fit(tr, cal)
        pv = cand.predict(obj, va)
        dt = time.time() - t0
        s = M.summary(pv, va.y.values, va)
        s.update(model=name, val_year=int(f['val']), train_min=int(tmin), train_max=int(tmax),
                 calib_year=int(f['calib']) if use_calib else None, n_train=int(len(tr)), fit_sec=round(dt, 1))
        per.append(s); rows.append(s)
        log(f"  {name:34s} val {f['val']}  brier={s['brier']:.5f}  logloss={s['logloss']:.4f}  "
            f"ece={s['ece']:.4f}  maxgap={s['max_gap']:+.3f}  ({dt:.0f} sn)")
    mb = float(np.mean([x['brier'] for x in per])); ml = float(np.mean([x['logloss'] for x in per]))
    me = float(np.mean([x['ece'] for x in per]))
    log(f"  {name:34s} ORTALAMA brier={mb:.5f} logloss={ml:.4f} ece={me:.4f}")
    return {'model': name, 'mean_brier': mb, 'mean_logloss': ml, 'mean_ece': me, 'folds': per}

means = {}
G = cfg['grids']

log('=== (a) BASELINE LOJISTIK (kontrol) ===')
means['a_logit_base'] = evaluate('a_logit_base', lambda: C.LogitBase())

log('\n=== (b) GRADIENT BOOSTING, HAM GIRDILER (m, tl, is_ot, spread) ===')
for hp in grid(G['hgb']):
    tag = f"b_hgb(lr={hp['learning_rate']},leaf={hp['max_leaf_nodes']})"
    means[tag] = evaluate(tag, lambda hp=hp: C.HGB(cols=C.RAW_COLS, mono=False, seed=cfg['seed'], **hp))
for hp in grid(G['hgb']):
    tag = f"b_hgb_mono(lr={hp['learning_rate']},leaf={hp['max_leaf_nodes']})"
    means[tag] = evaluate(tag, lambda hp=hp: C.HGB(cols=C.RAW_COLS, mono=True, seed=cfg['seed'], **hp))
try:
    import lightgbm  # noqa
    for hp in grid(G['lgbm']):
        tag = f"b_lgbm(leaf={hp['num_leaves']})"
        means[tag] = evaluate(tag, lambda hp=hp: C.LGBM(cols=C.RAW_COLS, mono=False, seed=cfg['seed'], **hp))
        tag = f"b_lgbm_mono(leaf={hp['num_leaves']})"
        means[tag] = evaluate(tag, lambda hp=hp: C.LGBM(cols=C.RAW_COLS, mono=True, seed=cfg['seed'], **hp))
except ImportError:
    log('  lightgbm kurulu degil, atlandi')

log('\n=== (b2) GRADIENT BOOSTING, MUHENDISLIK OZELLIKLERIYLE ===')
for hp in grid(G['hgb']):
    if hp['learning_rate'] != 0.05: continue
    tag = f"b2_hgb_eng(lr={hp['learning_rate']},leaf={hp['max_leaf_nodes']})"
    means[tag] = evaluate(tag, lambda hp=hp: C.HGB(cols='engineered', mono=False, seed=cfg['seed'], **hp))
    tag = f"b2_hgb_eng_mono(lr={hp['learning_rate']},leaf={hp['max_leaf_nodes']})"
    means[tag] = evaluate(tag, lambda hp=hp: C.HGB(cols='engineered', mono=True, seed=cfg['seed'], **hp))

log('\n=== (g) KAYAN EGITIM PENCERESI (sezon kaymasi icin) ===')
for n in cfg.get('windows', [4, 6]):
    tag = f'g_logit_base_win{n}'
    means[tag] = evaluate(tag, lambda: C.LogitBase(), window=n)

log('\n=== (c) LOJISTIK + SPLINE/ETKILESIM ===')
for hp in grid(G['spline']):
    tag = f"c_spline(C={hp['C']},knots={hp['n_knots']})"
    means[tag] = evaluate(tag, lambda hp=hp: C.LogitSpline(**hp))

# --- aile kazananlari
def best(prefix):
    c = {k: v for k, v in means.items() if k.startswith(prefix)}
    return min(c, key=lambda k: c[k]['mean_brier']) if c else None

best_gbm = min([k for k in means if k.startswith('b_')], key=lambda k: means[k]['mean_brier'])
best_spline = best('c_spline')
log(f"\nAile kazananlari: gradient boosting -> {best_gbm} ({means[best_gbm]['mean_brier']:.5f}), "
    f"spline -> {best_spline} ({means[best_spline]['mean_brier']:.5f})")

def rebuild(tag):
    """Etiketten aday nesnesi uret (ikinci asama icin)."""
    import re
    if tag.startswith('b_hgb'):
        lr = float(re.search(r'lr=([\d.]+)', tag).group(1)); lf = int(re.search(r'leaf=(\d+)', tag).group(1))
        return lambda: C.HGB(cols=C.RAW_COLS, mono='mono' in tag, learning_rate=lr, max_leaf_nodes=lf,
                             max_iter=G['hgb']['max_iter'][0], l2_regularization=G['hgb']['l2_regularization'][0],
                             min_samples_leaf=G['hgb']['min_samples_leaf'][0], seed=cfg['seed'])
    if tag.startswith('b_lgbm'):
        lf = int(re.search(r'leaf=(\d+)', tag).group(1))
        return lambda: C.LGBM(cols=C.RAW_COLS, mono='mono' in tag, num_leaves=lf,
                              learning_rate=G['lgbm']['learning_rate'][0],
                              n_estimators=G['lgbm']['n_estimators'][0], seed=cfg['seed'])
    if tag.startswith('c_spline'):
        Cv = float(re.search(r'C=([\d.]+)', tag).group(1)); kn = int(re.search(r'knots=(\d+)', tag).group(1))
        return lambda: C.LogitSpline(C=Cv, n_knots=kn)
    raise ValueError(tag)

log('\n=== (d) TAKIM GUCU PUANI OZELLIKLERIYLE GRADIENT BOOSTING ===')
import re
lr = float(re.search(r'lr=([\d.]+)', best_gbm).group(1)) if 'hgb' in best_gbm else G['hgb']['learning_rate'][0]
lf = int(re.search(r'leaf=(\d+)', best_gbm).group(1))
tag = f'd_hgb_rating(lr={lr},leaf={lf})'
means[tag] = evaluate(tag, lambda: C.HGB(cols=C.RATING_COLS, mono=True, learning_rate=lr, max_leaf_nodes=lf,
                                         max_iter=G['hgb']['max_iter'][0], seed=cfg['seed']))

log('\n=== (e) KALIBRASYON DUZELTMESI (taban model son egitim sezonu haric egitilir) ===')
for base_tag in dict.fromkeys([best_gbm, best_spline]):
    for meth in ('isotonic', 'platt'):
        t = f'e_cal_{meth}({base_tag})'
        means[t] = evaluate(t, lambda b=base_tag, m=meth: C.Calibrated(rebuild(b)(), method=m), use_calib=True)

log('\n=== (f) TOPLULUK: lojistik + gradient boosting ortalamasi ===')
means['f_ens_logit_gbm'] = evaluate('f_ens_logit_gbm',
                                   lambda: C.Ensemble([C.LogitBase(), rebuild(best_gbm)()]))
means['f_ens_logit_spline_gbm'] = evaluate('f_ens_logit_spline_gbm',
                                           lambda: C.Ensemble([C.LogitBase(), rebuild(best_spline)(), rebuild(best_gbm)()]))

# --- ozet
tab = pd.DataFrame(rows)
tab.to_csv(os.path.join(OUT, 'validation_table.csv'), index=False)
summ = pd.DataFrame([{'model': k, 'mean_brier': v['mean_brier'], 'mean_logloss': v['mean_logloss'],
                      'mean_ece': v['mean_ece']} for k, v in means.items()]).sort_values('mean_brier')
log('\n=== UC DOGRULAMA SEZONUNUN ORTALAMASI (secim olcutu: mean_brier) ===')
log(summ.to_string(index=False, float_format=lambda x: f'{x:.5f}'))
base_b = means['a_logit_base']['mean_brier']
log(f"\nBaseline ortalama Brier = {base_b:.5f}")
log('Adaylarin baseline'"'"'a gore farki (eksi = daha iyi):')
for r in summ.itertuples():
    if r.model != 'a_logit_base':
        log(f"  {r.model:34s} {r.mean_brier - base_b:+.5f}")
win = summ.iloc[0].model
log(f"\nDogrulamada en iyi aday: {win}")
json.dump({'winner': win, 'best_gbm': best_gbm, 'best_spline': best_spline,
           'mean_brier': {k: v['mean_brier'] for k, v in means.items()},
           'baseline_mean_brier': base_b}, open(os.path.join(OUT, 'selection.json'), 'w'), indent=1)
mods = {}
for m in ('numpy', 'pandas', 'sklearn', 'scipy'):
    try: mods[m] = __import__(m).__version__
    except Exception as e: mods[m] = str(e)
try: import lightgbm; mods['lightgbm'] = lightgbm.__version__
except Exception: mods['lightgbm'] = 'yok'
json.dump({'python': platform.python_version(), 'platform': platform.platform(), 'packages': mods,
           'seed': cfg['seed']}, open(os.path.join(OUT, 'versions.json'), 'w'), indent=1)
json.dump(cfg, open(os.path.join(OUT, 'config.json'), 'w'), indent=1, ensure_ascii=False)
open(os.path.join(OUT, 'validation_report.txt'), 'w', encoding='utf-8').write('\n'.join(log_lines) + '\n')
print('\nyazildi:', OUT)
