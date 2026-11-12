"""Olcutler: Brier, log loss, kalibrasyon ve kalan sure dilimleri."""
import numpy as np, pandas as pd

BUCKETS = ['36-48 dk', '24-36 dk', '12-24 dk', '5-12 dk', '<5 dk', 'Uzatma']

def brier(p, y): return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))

def logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12); y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

def bucket_of(d):
    """train_baseline.py ile ayni sinirlar."""
    tl = np.where(d.is_ot.values > 0, -1.0, d.tl.values)
    return pd.cut(tl, [-2, 0, 300, 720, 1440, 2160, 2881],
                  labels=['Uzatma', '<5 dk', '5-12 dk', '12-24 dk', '24-36 dk', '36-48 dk'])

def calib_table(p, y, bins=10):
    b = pd.cut(np.asarray(p), np.linspace(0, 1, bins + 1), include_lowest=True)
    t = pd.DataFrame({'p': np.asarray(p), 'y': np.asarray(y, float), 'b': b}) \
          .groupby('b', observed=True).agg(n=('y', 'size'), pred=('p', 'mean'), obs=('y', 'mean'))
    t['gap'] = t.pred - t.obs
    return t

def ece(p, y, bins=10):
    """Beklenen kalibrasyon hatasi: bolme buyuklugune gore agirlikli |tahmin - gercek|."""
    t = calib_table(p, y, bins)
    return float((t.n * t.gap.abs()).sum() / t.n.sum())

def max_gap(p, y, bins=10, min_n=500):
    t = calib_table(p, y, bins)
    t = t[t.n >= min_n]
    return float(t.gap.abs().max()) if len(t) else float('nan')

def summary(p, y, d):
    out = {'n': int(len(y)), 'brier': brier(p, y), 'logloss': logloss(p, y),
           'ece': ece(p, y), 'max_gap': max_gap(p, y)}
    bk = np.asarray(bucket_of(d))
    for b in BUCKETS:
        mm = (bk == b)
        out['brier_' + b] = brier(np.asarray(p)[mm], np.asarray(y)[mm]) if mm.sum() else float('nan')
        out['n_' + b] = int(mm.sum())
    return out

def paired_bootstrap(game_id, pa, pb, y, reps=2000, seed=0):
    """Maclari yeniden ornekleyen eslestirilmis bootstrap: ortalama Brier farki (a - b) ve %95 aralik.
    Once her mac icin an-ortalamasi alinir, sonra maclar yeniden orneklenir."""
    df = pd.DataFrame({'g': np.asarray(game_id),
                       'd': (np.asarray(pa) - np.asarray(y)) ** 2 - (np.asarray(pb) - np.asarray(y)) ** 2})
    v = df.groupby('g').d.mean().values
    rng = np.random.default_rng(seed)
    bs = np.empty(reps)
    for i in range(reps):
        bs[i] = v[rng.integers(0, len(v), len(v))].mean()
    return float(v.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), int(len(v))
