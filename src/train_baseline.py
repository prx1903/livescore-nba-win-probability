"""
Baseline canlı kazanma olasılığı modeli.
Kullanım: python3 -I train_baseline.py <veri_klasoru> <model_klasoru> [<rapor_klasoru>]
  model_coefficients.json <model_klasoru>'ne, baseline_report.txt <rapor_klasoru>'ne yazılır (verilmezse <model_klasoru>).
  <veri_klasoru> içinde games.csv ve pbp_clean/pbp_clean_<yıl>.parquet bulunmalı.

Tasarım:
  - Her maç için 60 sn aralıkla anlık görüntü (snapshot): o ana kadarki son olayın temiz skoru.
  - Özellikler yalnızca o ana kadarki bilgiyi kullanır (skor farkı, kalan süre, maç öncesi spread).
  - Aynı saniyede birden fazla olay varsa, olay sırasına (game_play_number) göre en sondaki alınır
    (22 Ekim 2026 düzeltmesi; önceki sürümde bu seçim sıralama algoritmasına bağlıydı).
  - Lojistik regresyon tam yakınsayana kadar çözülür (tol=1e-10); önceki sürüm varsayılan durma ölçütüyle
    erken duruyordu ve uzatma katsayısı ortamdan ortama değişiyordu.
  - Model seçimi doğrulama sezonu (dosya yılı 2022) ile; test (2023-2026) yalnızca bir kez, en sonda.
"""
import sys, os, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss

data_dir, out_dir = sys.argv[1], sys.argv[2]
report_dir = sys.argv[3] if len(sys.argv) > 3 else out_dir
os.makedirs(out_dir, exist_ok=True); os.makedirs(report_dir, exist_ok=True)
games = pd.read_csv(os.path.join(data_dir, 'games.csv'))
games = games[games.is_valid & games.spread_home.notna()].set_index('game_id')

def snapshots(year):
    d = pd.read_parquet(os.path.join(data_dir, 'pbp_clean', f'pbp_clean_{year}.parquet'),
                        columns=['game_id', 'game_play_number', 'game_seconds_elapsed', 'home_score', 'away_score'])
    d['game_id'] = d.game_id.astype('int64'); d['game_seconds_elapsed'] = d.game_seconds_elapsed.astype('float64')
    d = d[d.game_id.isin(games.index)].sort_values(['game_seconds_elapsed', 'game_play_number'], kind='stable')
    length = d.groupby('game_id').game_seconds_elapsed.max()
    grid = []
    for gid, L in length.items():
        ks = np.arange(0, int(L), 60)
        ks = ks[ks != 2880]
        grid.append(pd.DataFrame({'game_id': gid, 'k': ks.astype(float)}))
    grid = pd.concat(grid); grid['game_id'] = grid.game_id.astype('int64'); grid = grid.sort_values('k')
    s = pd.merge_asof(grid, d, left_on='k', right_on='game_seconds_elapsed', by='game_id', direction='backward')
    s['year'] = year
    return s.dropna(subset=['home_score'])

def feats(s, spread):
    k = s.k.values
    ot = k >= 2880
    tl = np.where(ot, 300 - ((k - 2880) % 300), 2880 - k)
    m = (s.home_score - s.away_score).values.astype(float)
    X = pd.DataFrame({
        'm_over_sqrt_tl': m / np.sqrt(tl + 1.0),
        'is_ot': ot.astype(float),
        'spread_x_tl': spread * (tl / 2880.0),
        'spread_x_sqrt_tl': spread * np.sqrt(tl / 2880.0),
        'm': m,
    })
    return X, tl, m

parts = [snapshots(y) for y in range(2013, 2027)]
S = pd.concat(parts, ignore_index=True)
S['y'] = games.home_win_final.reindex(S.game_id).values
S['spread'] = games.spread_home.reindex(S.game_id).values
X, S['tl'], S['m'] = feats(S, S.spread.values)
print('snapshot satırı:', len(S), ' maç:', S.game_id.nunique())

sets = {
    'pregame_only(spread)':    ['spread_only'],
    'S1 skor+süre':            ['m_over_sqrt_tl', 'is_ot'],
    'S2 S1+spread*tl':         ['m_over_sqrt_tl', 'is_ot', 'spread_x_tl'],
    'S3 S2+spread*sqrt(tl)':   ['m_over_sqrt_tl', 'is_ot', 'spread_x_tl', 'spread_x_sqrt_tl'],
}
X['spread_only'] = S.spread.values
tr = S.year <= 2021; va = S.year == 2022; trva = S.year <= 2022; te = S.year >= 2023

def fit(cols, mask):
    return LogisticRegression(C=1e4, max_iter=100000, tol=1e-10).fit(X.loc[mask, cols], S.y[mask])
def score(model, cols, mask):
    p = model.predict_proba(X.loc[mask, cols])[:, 1]
    return log_loss(S.y[mask], p), brier_score_loss(S.y[mask], p), p

lines = []
def log(t): print(t); lines.append(t)
log('== DOĞRULAMA (eğitim 2013-2021, doğrulama dosya yılı 2022) ==')
val = {}
for name, cols in sets.items():
    m_ = fit(cols, tr); ll, br, _ = score(m_, cols, va); val[name] = br
    log(f'{name:26s} logloss={ll:.4f} brier={br:.4f}')
best = min((n for n in sets if n != 'pregame_only(spread)'), key=lambda n: val[n])
log(f'Seçilen özellik kümesi (doğrulama Brier): {best}')

log('\n== TEST (eğitim 2013-2022, test dosya yılı 2023-2026) ==')
res = {}
for name, cols in sets.items():
    m_ = fit(cols, trva); ll, br, p = score(m_, cols, te); res[name] = (m_, cols, ll, br, p)
    log(f'{name:26s} logloss={ll:.4f} brier={br:.4f}')
model, cols, ll, br, p = res[best]
cl = pd.Series(cols)
log('\nSeçilen model katsayıları: intercept=%.4f  %s' % (model.intercept_[0], dict(zip(cols, np.round(model.coef_[0], 4)))))

T = S[te].copy(); T['p'] = p
T['bucket'] = pd.cut(T.tl.where(T.k < 2880, -1), [-2, 0, 300, 720, 1440, 2160, 2881], labels=['OT', '<5dk', '5-12dk', '12-24dk', '24-36dk', '36-48dk'])
log('\nKalan süreye göre test Brier (model | sadece spread):')
pg = res['pregame_only(spread)'][4]; T['pg'] = pg
for b, g in T.groupby('bucket', observed=True):
    log(f'  {b:8s} n={len(g):6d} model={brier_score_loss(g.y, g.p):.4f} spread={brier_score_loss(g.y, g.pg):.4f}')

log('\nKalibrasyon (test, tüm anlar; 10 eşit genişlikli bölme):')
T['bin'] = pd.cut(T.p, np.linspace(0, 1, 11), include_lowest=True)
for b, g in T.groupby('bin', observed=True):
    log(f'  {str(b):14s} n={len(g):6d} tahmin={g.p.mean():.3f} gerçek={g.y.mean():.3f}')

# Oyun-kümeli bootstrap: model - spread Brier farkı (maç bazında toplanmış)
rng = np.random.default_rng(0)
gdf = T.assign(d=(T.p - T.y) ** 2 - (T.pg - T.y) ** 2).groupby('game_id').d.mean()
bs = [gdf.sample(len(gdf), replace=True, random_state=int(rng.integers(1e9))).mean() for _ in range(500)]
log(f'\nBrier farkı (model - sadece spread), maç-kümeli bootstrap: ort={gdf.mean():.4f} %95 aralık=[{np.percentile(bs, 2.5):.4f}, {np.percentile(bs, 97.5):.4f}]')

coef = {'features': cols, 'intercept': float(model.intercept_[0]), 'coef': [float(c) for c in model.coef_[0]],
        'feature_set': best, 'train': 'dosya yılı 2013-2022', 'note': 'm=ev sahibi - deplasman; tl=kalan sn (uzatmada uzatma periyodunda kalan)'}
json.dump(coef, open(os.path.join(out_dir, 'model_coefficients.json'), 'w'), indent=2, ensure_ascii=False)
open(os.path.join(report_dir, 'baseline_report.txt'), 'w').write('\n'.join(lines) + '\n')
