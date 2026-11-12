"""winprob tahmin arayuzunun testleri (28 Ekim 2026).
Calistirma: python tests/test_models.py        (python -I kullanmayin: yerel src/ ice aktarilir)
"""
import os, sys, math, json, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import winprob
from feed_checks import spread_or_default

MODELS = [os.path.join(ROOT, 'models', f) for f in sorted(os.listdir(os.path.join(ROOT, 'models')))
          if f.endswith('.json') or f.endswith('.joblib')]
assert MODELS, 'models/ icinde model dosyasi yok'

# models/ icinde .joblib yoksa sklearn ve topluluk yolunu gecici dosyalarla sinar (depoya dosya eklenmez).
# Veri yapaydir (yalnizca arayuzu sinar, model kalitesini degil). sklearn/joblib yoksa bu kisim atlanir.
TMP = tempfile.TemporaryDirectory()
TOL = {}          # model etiketine gore 0-0 beraberlik toleransi
SKIPPED = None
try:
    import numpy as np, joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    rng = np.random.default_rng(0)
    n = 20000
    X = np.column_stack([rng.integers(-25, 26, n).astype(float), rng.uniform(0, 2880, n),
                         (rng.random(n) < 0.05).astype(float), rng.normal(0, 6, n)])  # m, tl, is_ot, spread
    z = X[:, 0] / np.sqrt(X[:, 1] + 1.0) * 1.2 + 0.08 * X[:, 3] * (X[:, 1] / 2880.0)
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    feats = ['m', 'tl', 'is_ot', 'spread']
    lr = LogisticRegression(max_iter=1000).fit(X, y)
    hgb = HistGradientBoostingClassifier(max_iter=60, monotonic_cst=[1, 0, 0, 0], random_state=0).fit(X, y)
    for name, est, tol in (('tmp_sklearn_lr.joblib', lr, 0.05), ('tmp_sklearn_hgb_mono.joblib', hgb, 0.15)):
        pth = os.path.join(TMP.name, name)
        joblib.dump({'estimator': est, 'input_features': feats, 'kind': 'sklearn'}, pth)
        MODELS.append(pth); TOL[os.path.basename(pth)] = tol
    ens = os.path.join(TMP.name, 'tmp_ensemble.json')
    json.dump({'kind': 'ensemble', 'members': [os.path.join(ROOT, 'models', 'model_coefficients.json'),
                                               'tmp_sklearn_lr.joblib']}, open(ens, 'w'))
    MODELS.append(ens); TOL['tmp_ensemble.json'] = 0.05
except ImportError as e:
    SKIPPED = str(e)
    print('ATLANDI: sklearn/joblib yok, sklearn ve topluluk testleri calismadi (' + SKIPPED + ')')

ok = 0
def check(cond, name):
    global ok
    assert cond, 'BASARISIZ: ' + name
    ok += 1
    print('ok  -', name)

for path in MODELS:
    tag = os.path.basename(path)
    m = winprob.load(path)

    # 1) olasilik her zaman 0-1 arasinda
    bad = []
    for margin in (-60, -10, -1, 0, 1, 10, 60):
        for tl in (0.0, 0.5, 1.0, 60.0, 300.0, 1440.0, 2880.0):
            for ot in (False, True):
                for sp in (-20.0, -3.5, 0.0, 3.5, 20.0):
                    pr = winprob.predict(m, margin, tl, ot, sp)
                    if not (0.0 <= pr <= 1.0) or math.isnan(pr):
                        bad.append((margin, tl, ot, sp, pr))
    check(not bad, f'{tag}: olasilik 0-1 araliginda (490 durum)')

    # 2) uzatma: is_ot bayragi sonucu degistirebilir ama gecerli olasilik verir
    p_reg = winprob.predict(m, 0, 300.0, False, 0.0)
    p_ot = winprob.predict(m, 0, 300.0, True, 0.0)
    check(0 < p_reg < 1 and 0 < p_ot < 1, f'{tag}: uzatma ve normal sure gecerli olasilik veriyor')

    # 3) beraberlikte ve denk takimlarda olasilik 0,5 civarinda
    p_tie = winprob.predict(m, 0, 2880.0, False, 0.0)
    tol = TOL.get(tag, 0.05)
    check(abs(p_tie - 0.5) < tol, f'{tag}: 0-0, mac basi, denk takim -> {p_tie:.3f} (0,5 civari, tolerans {tol})')

    # 4) skor farki arttikca olasilik azalmamali (ayni an icin)
    seq = [winprob.predict(m, mm, 600.0, False, 0.0) for mm in range(-20, 21)]
    check(all(b >= a - 1e-12 for a, b in zip(seq, seq[1:])), f'{tag}: olasilik skor farkinda azalmiyor')

    # 5) predict_state ve predict ayni sonucu veriyor
    st = {'margin': 7, 'secs_left': 420.0, 'is_ot': False, 'spread': -2.5}
    check(abs(winprob.predict_state(m, st) - winprob.predict(m, 7, 420.0, False, -2.5)) < 1e-15,
          f'{tag}: predict_state ile predict ayni')

    # 6) bos girdi
    check(winprob.predict_many(m, []) == [], f'{tag}: bos girdi listesi -> bos liste')
    check(len(winprob.predict_many(m, [st, st])) == 2, f'{tag}: iki durum -> iki olasilik')

    # 7) spread eksikse: feed_checks 0 (denk) kullanip uyarir, tahmin calisir
    sp, warn = spread_or_default(None)
    check(sp == 0.0 and warn, f'{tag}: spread yoksa 0 kullanilir ve uyari verilir')
    check(0 < winprob.predict(m, 3, 900.0, False, sp) < 1, f'{tag}: spread yokken tahmin calisiyor')

    # 8) son saniye: kalan sure 0 iken bolme hatasi olmamali
    check(0 < winprob.predict(m, 1, 0.0, False, 0.0) < 1, f'{tag}: kalan sure 0 saniyede tahmin calisiyor')

# 9) eski cagri bicimi (load_model) hala ayni sonucu veriyor
old = winprob.load_model(os.path.join(ROOT, 'models', 'model_coefficients.json'))
new = winprob.load(os.path.join(ROOT, 'models', 'model_coefficients.json'))
check(winprob.predict(old, 5, 600.0, False, -3.5) == winprob.predict(new, 5, 600.0, False, -3.5),
      'load_model ve load ayni sonucu veriyor (geriye donuk uyumluluk)')

# 10) bilinmeyen tur: eski katsayi modeli varsayilir
check(abs(winprob.predict(dict(old, kind='logistic_coeffs'), 5, 600.0, False, -3.5)
          - winprob.predict(old, 5, 600.0, False, -3.5)) < 1e-15, 'kind alani eklenince sonuc degismiyor')

# 11) topluluk: uye olasiliklarinin ortalamasi
if SKIPPED is None:
    e = winprob.load(os.path.join(TMP.name, 'tmp_ensemble.json'))
    a = winprob.predict(winprob.load(os.path.join(ROOT, 'models', 'model_coefficients.json')), 4, 700.0, False, 2.0)
    b = winprob.predict(winprob.load(os.path.join(TMP.name, 'tmp_sklearn_lr.joblib')), 4, 700.0, False, 2.0)
    check(abs(winprob.predict(e, 4, 700.0, False, 2.0) - (a + b) / 2) < 1e-12, 'topluluk = uye olasiliklarinin ortalamasi')
    # 12) joblib dosyasi diskten yuklenince 'kind' sklearn olarak okunuyor
    check(winprob.load(os.path.join(TMP.name, 'tmp_sklearn_lr.joblib'))['kind'] == 'sklearn', '.joblib dosyasi kind=sklearn yukleniyor')

TMP.cleanup()
print(f'\n{ok} test gecti ({len(MODELS)} model dosyasi: ' + ', '.join(os.path.basename(x) for x in MODELS) + ')')
