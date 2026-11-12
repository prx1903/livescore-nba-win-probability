"""SON DEGERLENDIRME: secilen aday ve baseline, test sezonlarinda (2023-2026) BIR KEZ olculur.
Secim run_validation.py'de bitti; bu betik secim yapmaz.

Kullanim: python3 -I run_test.py <config.json>
Cikti: <out_dir>/final_test.txt, final_test.json, secilen modelin surumlu dosyasi (models/ altina)
"""
import sys, os, json, time, platform, re
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import candidates as C
import metrics as M

cfg = json.load(open(sys.argv[1], encoding='utf-8'))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
p = lambda x: x if os.path.isabs(x) else os.path.join(ROOT, x)
OUT = p(cfg['out_dir'])
SEL = json.load(open(os.path.join(OUT, 'selection.json'), encoding='utf-8'))
F = cfg['final']

S = pd.read_parquet(p(cfg['snapshots']))
lines = []
def log(t=''):
    print(t, flush=True); lines.append(t)

def make(tag):
    """Etiketten aday nesnesi ve egitim penceresi."""
    G = cfg['grids']
    if tag == 'a_logit_base': return C.LogitBase(), None, False
    if tag.startswith('g_logit_base_win'):
        return C.LogitBase(), int(tag.replace('g_logit_base_win', '')), False
    if tag.startswith('b_hgb') or tag.startswith('b2_hgb_eng'):
        lr = float(re.search(r'lr=([\d.]+)', tag).group(1)); lf = int(re.search(r'leaf=(\d+)', tag).group(1))
        cols = 'engineered' if 'eng' in tag else C.RAW_COLS
        return C.HGB(cols=cols, mono='mono' in tag, learning_rate=lr, max_leaf_nodes=lf,
                     max_iter=G['hgb']['max_iter'][0], seed=cfg['seed']), None, False
    if tag.startswith('b_lgbm'):
        lf = int(re.search(r'leaf=(\d+)', tag).group(1))
        return C.LGBM(cols=C.RAW_COLS, mono='mono' in tag, num_leaves=lf,
                      learning_rate=G['lgbm']['learning_rate'][0],
                      n_estimators=G['lgbm']['n_estimators'][0], seed=cfg['seed']), None, False
    if tag.startswith('c_spline'):
        Cv = float(re.search(r'C=([\d.]+)', tag).group(1)); kn = int(re.search(r'knots=(\d+)', tag).group(1))
        return C.LogitSpline(C=Cv, n_knots=kn), None, False
    if tag.startswith('d_hgb_rating'):
        lr = float(re.search(r'lr=([\d.]+)', tag).group(1)); lf = int(re.search(r'leaf=(\d+)', tag).group(1))
        return C.HGB(cols=C.RATING_COLS, mono=True, learning_rate=lr, max_leaf_nodes=lf,
                     max_iter=G['hgb']['max_iter'][0], seed=cfg['seed']), None, False
    if tag.startswith('e_cal_'):
        meth = 'isotonic' if 'isotonic' in tag else 'platt'
        inner = tag[tag.index('(') + 1:-1]
        base, _, _ = make(inner)
        return C.Calibrated(base, method=meth), None, True
    if tag.startswith('f_ens'):
        members = [C.LogitBase()]
        if 'spline' in tag: members.append(make(SEL['best_spline'])[0])
        members.append(make(SEL['best_gbm'])[0])
        return C.Ensemble(members), None, False
    raise ValueError(tag)

win_tag = SEL['winner']
log('=== SON DEGERLENDIRME (test: dosya yili %d-2026) ===' % F['test_min'])
log(f"Dogrulamada secilen aday : {win_tag}  (3 sezon ortalama Brier {SEL['mean_brier'][win_tag]:.5f})")
log(f"Baseline                : a_logit_base  (3 sezon ortalama Brier {SEL['baseline_mean_brier']:.5f})")
log('Secim yalnizca 2020-2022 dogrulama sezonlariyla yapildi; test sezonlari bu asamaya kadar hic kullanilmadi.')
log('')

te = S[S.year >= F['test_min']]
y = te.y.values
res, fitted = {}, {}
for tag in dict.fromkeys(['a_logit_base', win_tag]):
    cand, window, needs_cal = make(tag)
    tmin = cfg['train_min'] if window is None else max(cfg['train_min'], F['train_max'] - window + 1)
    tmax = F['train_max_inner'] if needs_cal else F['train_max']
    tr = S[(S.year >= tmin) & (S.year <= tmax)]
    cal = S[S.year == F['calib']] if needs_cal else None
    t0 = time.time(); obj = cand.fit(tr, cal); fit_s = time.time() - t0
    t0 = time.time(); pt = cand.predict(obj, te); pred_s = time.time() - t0
    res[tag] = M.summary(pt, y, te)
    res[tag].update(train_min=int(tmin), train_max=int(tmax), n_train=int(len(tr)),
                    fit_sec=round(fit_s, 1), predict_sec_254k=round(pred_s, 2))
    fitted[tag] = (cand, obj, pt)
    log(f"{tag:26s} egitim {tmin}-{tmax} ({len(tr)} an)  Brier={res[tag]['brier']:.5f}  "
        f"log loss={res[tag]['logloss']:.4f}  ECE={res[tag]['ece']:.4f}  en buyuk bolme sapmasi={res[tag]['max_gap']:+.3f}")

pb, pw = fitted['a_logit_base'][2], fitted[win_tag][2]
log('\n--- Kalan sure dilimlerine gore Brier ---')
log(f"{'dilim':10s} {'n':>7s} {'baseline':>10s} {'aday':>10s} {'fark':>9s}")
for b in M.BUCKETS:
    log(f"{b:10s} {res['a_logit_base']['n_'+b]:7d} {res['a_logit_base']['brier_'+b]:10.4f} "
        f"{res[win_tag]['brier_'+b]:10.4f} {res[win_tag]['brier_'+b]-res['a_logit_base']['brier_'+b]:+9.4f}")

log('\n--- Kalibrasyon (10 bolme) ---')
for tag, pp in (('baseline', pb), ('aday', pw)):
    t = M.calib_table(pp, y)
    log(f'  {tag}:')
    for r in t.itertuples():
        log(f'    {str(r.Index):14s} n={int(r.n):6d} tahmin={r.pred:.3f} gercek={r.obs:.3f} fark={r.gap:+.3f}')

md, lo, hi, ng = M.paired_bootstrap(te.game_id.values, pw, pb, y, reps=cfg['bootstrap_reps'], seed=cfg['seed'])
log(f"\n--- Brier farki (aday - baseline), mac bazli eslestirilmis bootstrap ---")
log(f"  ortalama={md:+.5f}  %95 aralik=[{lo:+.5f}, {hi:+.5f}]  ({ng} mac, {cfg['bootstrap_reps']} tekrar)")
zero_in = lo <= 0 <= hi
log(f"  aralik sifiri iceriyor mu: {'EVET' if zero_in else 'HAYIR'}")

# tek tahmin suresi (replay icin)
sys.path.insert(0, os.path.join(ROOT, 'src'))
import winprob
base_model = winprob.load(os.path.join(ROOT, 'models', 'model_coefficients.json'))
t0 = time.time()
for _ in range(2000): winprob.predict(base_model, 5, 600.0, False, -3.5)
us_base = (time.time() - t0) / 2000 * 1e6
log(f"\n--- Tek tahmin suresi (replay icin) ---")
log(f"  baseline (winprob.predict, saf Python): {us_base:.1f} mikrosaniye/tahmin")

cand, obj, _ = fitted[win_tag]
if isinstance(cand, C.LogitBase):
    lr = obj
    mdl = {'kind': 'logistic_coeffs', 'features': C.BASE_COLS,
           'intercept': float(lr.intercept_[0]), 'coef': [float(c) for c in lr.coef_[0]],
           'feature_set': win_tag, 'train': f"dosya yili {res[win_tag]['train_min']}-{res[win_tag]['train_max']}",
           'note': 'm=ev sahibi - deplasman; tl=kalan sn (uzatmada uzatma periyodunda kalan)',
           'selection': 'ileri yonlu dogrulama 2020/2021/2022, secim olcutu ortalama Brier',
           'experiment': cfg['run_name']}
    fn = os.path.join(ROOT, 'models', f"model_{win_tag.replace('(', '_').replace(')', '').replace('=', '').replace(',', '_')}_v1.json")
    json.dump(mdl, open(fn, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    t0 = time.time()
    m2 = winprob.load(fn)
    for _ in range(2000): winprob.predict(m2, 5, 600.0, False, -3.5)
    log(f"  aday    (winprob.predict, saf Python): {(time.time()-t0)/2000*1e6:.1f} mikrosaniye/tahmin")
else:
    import joblib
    fn = os.path.join(ROOT, 'models', f"model_{win_tag.split('(')[0]}_v1.joblib")
    joblib.dump({'kind': 'sklearn', 'estimator': obj,
                 'input_features': cand.cols if isinstance(getattr(cand, 'cols', None), list) else C.RAW_COLS,
                 'train': f"dosya yili {res[win_tag]['train_min']}-{res[win_tag]['train_max']}",
                 'experiment': cfg['run_name']}, fn)
    m2 = winprob.load(fn)
    t0 = time.time()
    for _ in range(2000): winprob.predict(m2, 5, 600.0, False, -3.5)
    log(f"  aday    (winprob.predict, sklearn):    {(time.time()-t0)/2000*1e6:.1f} mikrosaniye/tahmin")
log(f"  model dosyasi: {os.path.relpath(fn, ROOT)}")

log('\n--- KARAR ---')
ok_int = not zero_in and md < 0
ok_cal = res[win_tag]['ece'] <= res['a_logit_base']['ece'] + 1e-9
log(f"  1) Brier farkinin %95 araligi sifiri disliyor ve aday daha iyi: {'EVET' if ok_int else 'HAYIR'}")
log(f"  2) Kalibrasyon baseline'dan kotu degil (ECE {res[win_tag]['ece']:.4f} <= {res['a_logit_base']['ece']:.4f}): {'EVET' if ok_cal else 'HAYIR'}")
log(f"  3) Tek tahmin suresi replay icin kabul edilebilir: EVET ({us_base:.1f} mikrosaniye duzeyinde)")
log(f"  SONUC: aday baseline'in yerini {'ALIR' if (ok_int and ok_cal) else 'ALMAZ'}.")
if not (ok_int and ok_cal):
    log("  Baseline teslim edilen model olarak kalir; aday modeli results/experiments altinda kayitli kalir.")

json.dump({'winner': win_tag, 'test': res, 'diff_mean': md, 'diff_lo': lo, 'diff_hi': hi,
           'n_games': ng, 'zero_in_interval': bool(zero_in), 'replaces_baseline': bool(ok_int and ok_cal)},
          open(os.path.join(OUT, 'final_test.json'), 'w'), indent=1)
open(os.path.join(OUT, 'final_test.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('\nyazildi:', os.path.join(OUT, 'final_test.txt'))
