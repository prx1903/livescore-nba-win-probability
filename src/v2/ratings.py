"""Takım gücü puanları (hücum / savunma) ve maç öncesi beklenen skor.
Kullanım: python3 -I ratings.py <veri_klasoru> <calisma_klasoru>
Her maç için yalnızca o maçtan ÖNCEKİ maçlar kullanılır (sızıntı yok).
  beklenen ev sayısı  = L + H/2 + O[ev] + D[dep]
  beklenen dep sayısı = L - H/2 + O[dep] + D[ev]
  O: lig ortalamasına göre attığı fazla sayı, D: lig ortalamasına göre yediği fazla sayı (normal süre, 48 dk).
Maçtan sonra hata ile güncellenir (K), yeni sezonda puanlar ortalamaya doğru çekilir (r).
Parametre seçimi: eğitim dosya yılları 2014-2021 hata kareler ortalaması; 2022 doğrulama; 2023-2026 test (bir kez).
"""
import sys, os, json, itertools
import numpy as np, pandas as pd

data, work = sys.argv[1], sys.argv[2]
BAD = {400975164}   # ATL-DET 2017-12-14: skor 262-105, bozuk kayıt
G = pd.read_csv(os.path.join(data, 'games.csv'))
G = G[G.is_valid & ~G.game_id.isin(BAD)].copy()
G['game_date'] = pd.to_datetime(G.game_date)
G = G.sort_values(['game_date', 'game_id']).reset_index(drop=True)
hid, aid = G.home_team_id.values, G.away_team_id.values
ph, pa = G.home_end_reg.values.astype(float), G.away_end_reg.values.astype(float)
season = G.season.values; year = G.file_year.values
L0 = (ph[year == 2013].mean() + pa[year == 2013].mean()) / 2
H0 = (ph[year == 2013] - pa[year == 2013]).mean()


def run(K, r, KL, KH, keep=False):
    O = np.zeros(31); D = np.zeros(31); L, H = L0, H0
    eh = np.empty(len(G)); ea = np.empty(len(G))
    snap = np.empty((len(G), 6)) if keep else None
    cur = season[0]
    for i in range(len(G)):
        if season[i] != cur:
            O *= (1 - r); D *= (1 - r); cur = season[i]
        h, a = hid[i], aid[i]
        eh[i] = L + H / 2 + O[h] + D[a]; ea[i] = L - H / 2 + O[a] + D[h]
        if keep:
            snap[i] = (O[h], D[h], O[a], D[a], L, H)
        rh, ra = ph[i] - eh[i], pa[i] - ea[i]
        O[h] += K * rh; D[a] += K * rh; O[a] += K * ra; D[h] += K * ra
        L += KL * (rh + ra) / 2; H += KH * (rh - ra)
    return eh, ea, snap


tr = (year >= 2014) & (year <= 2021); va = year == 2022; te = year >= 2023
best = None
for K, r, KL, KH in itertools.product([0.02, 0.03, 0.045, 0.06, 0.08, 0.1, 0.13], [0.0, 0.25, 0.4, 0.6],
                                      [0.0005, 0.002, 0.005], [0.0005, 0.002]):
    eh, ea, _ = run(K, r, KL, KH)
    mse = np.mean(((ph - eh) ** 2 + (pa - ea) ** 2)[tr]) / 2
    if best is None or mse < best[0]:
        best = (mse, K, r, KL, KH)
mse, K, r, KL, KH = best
eh, ea, snap = run(K, r, KL, KH, keep=True)
G['exp_h'], G['exp_a'] = eh, ea
G[['O_h', 'D_h', 'O_a', 'D_a', 'L', 'H']] = snap

# --- maç öncesi fark ve toplam: spread + puan farkı birleşimi (eğitimde doğrusal regresyon)
G['rm'] = G.exp_h - G.exp_a; G['rt'] = G.exp_h + G.exp_a
G['mreg'] = ph - pa; G['treg'] = ph + pa
G['sp'] = G.spread_home
hasp = G.sp.notna().values


def ols(X, y):
    X1 = np.c_[np.ones(len(X)), X]
    b, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return b


m_tr = tr & hasp
b_sp = ols(G.loc[m_tr, ['sp']].values, G.mreg[m_tr].values)
b_both = ols(G.loc[m_tr, ['sp', 'rm']].values, G.mreg[m_tr].values)
b_rm = ols(G.loc[tr, ['rm']].values, G.mreg[tr].values)
b_tot = ols(G.loc[tr, ['rt']].values, G.treg[tr].values)


def pred(b, cols, df):
    return b[0] + df[cols].values @ b[1:]


lines = [f'Seçilen parametreler: K={K} r={r} KL={KL} KH={KH}  (eğitim 2014-2021 MSE/takım={mse:.2f})', '']
lines.append('Maç öncesi NORMAL SÜRE FARKI (ev - dep) için hata (RMSE, sayı):')
for name, m in (('doğrulama 2022', va & hasp), ('test 2023-2026', te & hasp)):
    d = G[m]
    r0 = np.sqrt(np.mean((d.mreg - d.mreg[tr].mean() if False else d.mreg - G.mreg[tr].mean()) ** 2))
    r1 = np.sqrt(np.mean((d.mreg - pred(b_sp, ['sp'], d)) ** 2))
    r2 = np.sqrt(np.mean((d.mreg - pred(b_rm, ['rm'], d)) ** 2))
    r3 = np.sqrt(np.mean((d.mreg - pred(b_both, ['sp', 'rm'], d)) ** 2))
    lines.append(f'  {name:15s} n={len(d):5d}  sabit={r0:.2f}  sadece spread={r1:.2f}  sadece güç puanı={r2:.2f}  ikisi={r3:.2f}')
lines.append(f'  katsayılar (ikisi): sabit={b_both[0]:.3f} spread={b_both[1]:.3f} güç farkı={b_both[2]:.3f}')
lines.append(f'  katsayılar (sadece spread): sabit={b_sp[0]:.3f} spread={b_sp[1]:.3f}')
lines.append('')
lines.append('Maç öncesi NORMAL SÜRE TOPLAM SAYI için hata (RMSE, sayı):')
for name, m in (('doğrulama 2022', va), ('test 2023-2026', te)):
    d = G[m]
    r0 = np.sqrt(np.mean((d.treg - G.treg[tr].mean()) ** 2))
    rs = np.sqrt(np.mean((d.treg - d.groupby('season').treg.transform('mean')) ** 2))
    r1 = np.sqrt(np.mean((d.treg - pred(b_tot, ['rt'], d)) ** 2))
    lines.append(f'  {name:15s} sabit (eğitim ort.)={r0:.2f}  [hile: o sezonun gerçek ortalaması={rs:.2f}]  güç puanı={r1:.2f}')
lines.append(f'  katsayılar: sabit={b_tot[0]:.3f} güç toplamı={b_tot[1]:.3f}')
choose = 'both'
# doğrulamada ikisi spread'den iyi değilse sadece spread
d = G[va & hasp]
if np.mean((d.mreg - pred(b_both, ['sp', 'rm'], d)) ** 2) >= np.mean((d.mreg - pred(b_sp, ['sp'], d)) ** 2):
    choose = 'spread'
lines.append(f'\nDoğrulamaya göre seçilen fark modeli: {choose}')
G['mu_m'] = np.where(hasp, pred(b_both, ['sp', 'rm'], G) if choose == 'both' else pred(b_sp, ['sp'], G), pred(b_rm, ['rm'], G))
G['mu_t'] = pred(b_tot, ['rt'], G)
G['mu_h'] = (G.mu_t + G.mu_m) / 2; G['mu_a'] = (G.mu_t - G.mu_m) / 2
G[['game_id', 'file_year', 'season', 'game_date', 'home_team_id', 'away_team_id', 'home_abbrev', 'away_abbrev', 'sp',
   'exp_h', 'exp_a', 'O_h', 'D_h', 'O_a', 'D_a', 'L', 'H', 'mu_m', 'mu_t', 'mu_h', 'mu_a', 'mreg', 'treg', 'has_ot',
   'home_win_final', 'home_final', 'away_final', 'n_periods']].to_parquet(os.path.join(work, 'pregame.parquet'), index=False)
json.dump({'K': K, 'r': r, 'KL': KL, 'KH': KH, 'margin_model': choose,
           'b_both': list(b_both), 'b_sp': list(b_sp), 'b_rm': list(b_rm), 'b_tot': list(b_tot)},
          open(os.path.join(work, 'ratings_params.json'), 'w'), indent=1)
open(os.path.join(work, 'ratings_report.txt'), 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
