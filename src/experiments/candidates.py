"""Aday modeller. Hepsi ayni arayuzu kullanir:
      obj = cand.fit(train_df, calib_df)      # calib_df yalnizca kalibrasyon sarmallayicilari icin
      p   = cand.predict(obj, df)             # 0-1 arasi olasilik dizisi

Ozellik kolonlari an goruntusu tablosundan okunur; hicbir aday y'yi girdi olarak gormez.
"""
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import SplineTransformer, StandardScaler
from sklearn.isotonic import IsotonicRegression

BASE_COLS = ['m_over_sqrt_tl', 'is_ot', 'spread_x_tl', 'spread_x_sqrt_tl']
RAW_COLS = ['m', 'tl', 'is_ot', 'spread']
RATING_COLS = ['m', 'tl', 'is_ot', 'spread', 'rm', 'rt', 'O_h', 'D_h', 'O_a', 'D_a']


def base_features(d):
    """winprob.features ile ayni dort ozellik."""
    tl = d.tl.values
    return pd.DataFrame({
        'm_over_sqrt_tl': d.m.values / np.sqrt(tl + 1.0),
        'is_ot': d.is_ot.values,
        'spread_x_tl': d.spread.values * (tl / 2880.0),
        'spread_x_sqrt_tl': d.spread.values * np.sqrt(tl / 2880.0),
    })


class LogitBase:
    """(a) Mevcut baseline: dort ozellikli lojistik regresyon. Kontrol."""
    kind = 'logit_base'
    def __init__(self, C=1e4): self.C = C
    def fit(self, tr, calib=None):
        X = base_features(tr)
        lr = LogisticRegression(C=self.C, max_iter=100000, tol=1e-10).fit(X, tr.y.values)
        return lr
    def predict(self, obj, d): return obj.predict_proba(base_features(d))[:, 1]


class HGB:
    """(b)/(d) Gradient boosting. mono=True ise skor farki ve spread'de artan kisit."""
    kind = 'hgb'
    def __init__(self, cols=RAW_COLS, mono=False, learning_rate=0.1, max_leaf_nodes=31,
                 max_iter=300, l2_regularization=1.0, min_samples_leaf=200, seed=0):
        self.cols = cols if isinstance(cols, str) else list(cols)
        self.mono = mono
        self.kw = dict(learning_rate=learning_rate, max_leaf_nodes=max_leaf_nodes, max_iter=max_iter,
                       l2_regularization=l2_regularization, min_samples_leaf=min_samples_leaf,
                       early_stopping=False, random_state=seed)
    def _cst(self):
        if not self.mono: return None
        # +1: ozellik artarken ev sahibi olasiligi azalmasin
        if self.cols == 'engineered':
            return [1, 0, 0, 0, 1, 0]      # m_over_sqrt_tl, is_ot, spread_x_tl, spread_x_sqrt_tl, m, tl
        return [1 if c in ('m', 'spread') else 0 for c in self.cols]
    def _X(self, d):
        if self.cols == 'engineered':
            # baseline'in dort ozelligi + ham m ve tl (agaclar icin ayni bilgi, farkli temsil)
            B = base_features(d)
            B['m'] = d.m.values; B['tl'] = d.tl.values
            return B.values
        return d[self.cols].values
    def fit(self, tr, calib=None):
        g = HistGradientBoostingClassifier(monotonic_cst=self._cst(), **self.kw)
        return g.fit(self._X(tr), tr.y.values)
    def predict(self, obj, d): return obj.predict_proba(self._X(d))[:, 1]


class LGBM:
    """(b) LightGBM (kuruluysa). Monoton kisit secenegi ayni."""
    kind = 'lgbm'
    def __init__(self, cols=RAW_COLS, mono=False, learning_rate=0.05, num_leaves=31, n_estimators=400, seed=0):
        self.cols, self.mono = list(cols), mono
        self.kw = dict(learning_rate=learning_rate, num_leaves=num_leaves, n_estimators=n_estimators,
                       random_state=seed, n_jobs=-1, verbose=-1, min_child_samples=200)
    def fit(self, tr, calib=None):
        import lightgbm as lgb
        cst = [1 if c in ('m', 'spread') else 0 for c in self.cols] if self.mono else None
        kw = dict(self.kw)
        if cst: kw['monotone_constraints'] = cst
        return lgb.LGBMClassifier(**kw).fit(tr[self.cols].values, tr.y.values)
    def predict(self, obj, d): return obj.predict_proba(d[self.cols].values)[:, 1]


class LogitSpline:
    """(c) Lojistik + spline/etkilesim: kalan sureye gore degisen katsayilar.
    u = sqrt(kalan sure / 2880) uzerinde dogal kubik spline tabani; taban [1, z, spread] ile carpilir
    (z = fark / sqrt(kalan sure + 1)). Baseline bu ailenin ozel bir halidir."""
    kind = 'logit_spline'
    def __init__(self, n_knots=6, C=1.0, degree=3):
        self.n_knots, self.C, self.degree = n_knots, C, degree
    def _design(self, d, fit=False):
        tl = d.tl.values
        u = np.sqrt(tl / 2880.0).reshape(-1, 1)
        z = (d.m.values / np.sqrt(tl + 1.0)).reshape(-1, 1)
        sp = d.spread.values.reshape(-1, 1)
        if fit:
            self.st_ = SplineTransformer(n_knots=self.n_knots, degree=self.degree, include_bias=True,
                                         extrapolation='constant').fit(u)
        B = self.st_.transform(u)                      # (n, n_knots+degree-1)
        X = np.hstack([B, B * z, B * sp, d.is_ot.values.reshape(-1, 1)])
        if fit:
            self.sc_ = StandardScaler().fit(X)
        return self.sc_.transform(X)
    def fit(self, tr, calib=None):
        X = self._design(tr, fit=True)
        lr = LogisticRegression(C=self.C, max_iter=20000, tol=1e-9).fit(X, tr.y.values)
        return (lr, self.st_, self.sc_)
    def predict(self, obj, d):
        lr, self.st_, self.sc_ = obj
        return lr.predict_proba(self._design(d))[:, 1]


class Calibrated:
    """(e) Taban modelin ciktisina kalibrasyon duzeltmesi.
    Taban model egitim yillarinin SON sezonu haric kismiyla egitilir, duzeltme o son sezonda ogrenilir.
    Dogrulama/test sezonu hicbir asamada gorulmez."""
    kind = 'calibrated'
    def __init__(self, base, method='isotonic'):
        self.base, self.method = base, method
    def fit(self, tr, calib=None):
        assert calib is not None and len(calib), 'kalibrasyon bolmesi gerekli'
        b = self.base.fit(tr)
        q = np.clip(self.base.predict(b, calib), 1e-6, 1 - 1e-6)
        yv = calib.y.values
        if self.method == 'isotonic':
            cal = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(q, yv)
        else:
            cal = LogisticRegression(C=1e6, max_iter=10000).fit(np.log(q / (1 - q)).reshape(-1, 1), yv)
        return (b, cal)
    def predict(self, obj, d):
        b, cal = obj
        q = np.clip(self.base.predict(b, d), 1e-6, 1 - 1e-6)
        if self.method == 'isotonic':
            return np.clip(cal.predict(q), 1e-6, 1 - 1e-6)
        return cal.predict_proba(np.log(q / (1 - q)).reshape(-1, 1))[:, 1]


class Ensemble:
    """(f) Basit topluluk: uye olasiliklarinin duz ortalamasi."""
    kind = 'ensemble'
    def __init__(self, members): self.members = members
    def fit(self, tr, calib=None): return [m.fit(tr) for m in self.members]
    def predict(self, objs, d):
        return np.mean([m.predict(o, d) for m, o in zip(self.members, objs)], axis=0)
