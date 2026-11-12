"""Maç içi skor dağılımı modeli: kalan sürede iki takımın atacağı sayı normal dağılımla modellenir.
Kullanım: python3 -I model.py <calisma_klasoru> <baseline_model_json>
Seçimler eğitim (2014-2021) + doğrulama (2022) ile yapılır; son parametreler 2014-2022 ile yeniden kestirilir;
test (2023-2026) en sonda bir kez değerlendirilir.
Çıktılar: model_report.txt, sim_params.json, test_preds.parquet (örnek maçlar için)
"""
import sys, os, json
import numpy as np, pandas as pd
from scipy.stats import norm
from sklearn.isotonic import IsotonicRegression

work, base_json = sys.argv[1], sys.argv[2]
BASE = json.load(open(base_json))
PG = pd.read_parquet(os.path.join(work, 'pregame.parquet'))
S = pd.read_parquet(os.path.join(work, 'snaps.parquet'))
PER = pd.read_parquet(os.path.join(work, 'periods.parquet'))
PG = PG[PG.sp.notna()]
S = S.merge(PG[['game_id', 'file_year', 'mu_m', 'mu_t', 'sp', 'mreg', 'treg', 'home_win_final', 'has_ot', 'n_periods',
                'home_final', 'away_final']], on='game_id')
S = S.rename(columns={'home_score': 'h', 'away_score': 'a', 'period_number': 'per'})
S['tot'] = S.h + S.a
REP = []
MET = {}
def log(t=''):
    print(t, flush=True); REP.append(t)

TR = lambda y: (y >= 2014) & (y <= 2021)
VA = lambda y: y == 2022
TV = lambda y: (y >= 2014) & (y <= 2022)
TE = lambda y: y >= 2023
reg = S.k < 2880

# ---------------------------------------------------------------- 1) puan yoğunluğu ve kalan pay s(k)
def intensity(mask):
    d = S[mask & reg][['game_id', 'k', 'tot', 'treg']].sort_values(['game_id', 'k'])
    nxt = d.groupby('game_id').tot.shift(-1)
    d['inc'] = np.where(nxt.notna(), nxt - d.tot, d.treg - d.tot)   # son dakika: normal süre sonu toplamı
    I = d.groupby((d.k // 60).astype(int)).inc.mean().reindex(range(48)).values
    return I

def share_table(I):
    c = np.r_[np.cumsum(I[::-1])[::-1], 0.0]          # c[i] = i. dakikadan sona kalan beklenen sayı
    return c / c[0]                                   # 49 değer: k = 0, 60, ..., 2880

def s_of(k, SH):
    k = np.clip(np.asarray(k, float), 0, 2880)
    return np.interp(k, np.arange(49) * 60.0, SH)

# ---------------------------------------------------------------- 2) ortalama modeli (tempo/güç güncellemesi + ek özellikler)
def means(d, SH, kt, km, beta):
    s = s_of(d.k.values, SH); e = 1 - s
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.where(e > 1e-9, s / e, 0.0)
    wt = 0.0 if kt is None else e / (e + kt)
    wm = 0.0 if km is None else e / (e + km)
    rem_t = d.mu_t.values * s + wt * (d.tot.values - d.mu_t.values * e) * ratio
    rem_m = d.mu_m.values * s + wm * (d.m.values - d.mu_m.values * e) * ratio
    for c, b in beta.items():
        rem_m = rem_m + b * feat(d, c, s)
    return s, rem_m, rem_t

def feat(d, c, s):
    if c == 'ms':
        return d.m.values * s
    return d[c].values

SCALED = set()   # (yer tutucu: ölçekli özellik kullanılırsa)

def fit_kappa(mask, SH, which):
    d = S[mask & reg]
    best = None
    for kap in [None, 0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2]:
        if which == 't':
            _, _, rt = means(d, SH, kap, None, {})
            err = np.mean((d.treg.values - d.tot.values - rt) ** 2)
        else:
            _, rm, _ = means(d, SH, None, kap, {})
            err = np.mean((d.mreg.values - d.m.values - rm) ** 2)
        if best is None or err < best[0] - 1e-9:
            best = (err, kap)
    return best

# ---------------------------------------------------------------- 3) belirsizlik eğrileri V(tau)
def var_curves(mask, SH, kt, km, beta):
    d = S[mask & reg].copy()
    s, rm, rt = means(d, SH, kt, km, beta)
    d['Rm'] = d.mreg - d.m - rm; d['Rt'] = d.treg - d.tot - rt
    d['tau'] = ((2880 - d.k) // 60).astype(int)       # 1..48 (dakika)
    g = d.groupby('tau')
    Vm = g.Rm.apply(lambda x: np.mean(x ** 2)).reindex(range(1, 49)).values
    Vt = g.Rt.apply(lambda x: np.mean(x ** 2)).reindex(range(1, 49)).values
    Cmt = g.apply(lambda x: np.mean(x.Rm * x.Rt)).reindex(range(1, 49)).values
    bias_m = g.Rm.mean().reindex(range(1, 49)).values
    iso = IsotonicRegression(increasing=True)
    taus = np.arange(1, 49)
    Vm_s = np.r_[0.0, iso.fit_transform(taus, Vm)]; Vt_s = np.r_[0.0, iso.fit_transform(taus, Vt)]
    Cmt_s = np.r_[0.0, pd.Series(Cmt).rolling(5, center=True, min_periods=1).mean().values]
    # korelasyon sınırı
    lim = np.sqrt(Vm_s * Vt_s) * 0.95
    Cmt_s = np.clip(Cmt_s, -lim, lim)
    return Vm_s, Vt_s, Cmt_s, bias_m

def V_of(tau, V):
    return np.interp(np.clip(np.asarray(tau, float), 0, 2880), np.arange(49) * 60.0, V)

# ---------------------------------------------------------------- 4) uzatma modeli
def ot_params(mask_games):
    gids = PG[mask_games(PG.file_year)].game_id
    o = PER[PER.game_id.isin(gids) & (PER.period_number >= 5)].merge(PG[['game_id', 'mu_m']], on='game_id')
    pm = (o.ph - o.pa).values; x = o.mu_m.values * 300 / 2880
    c = float(np.sum(pm * x) / np.sum(x * x)) if np.sum(x * x) > 0 else 1.0
    v = float(np.mean((pm - c * x) ** 2))
    tie_rate = float(np.mean(pm == 0))
    return {'c': c, 'v': v, 'n': int(len(o)), 'emp_tie': tie_rate,
            'pts_mean': float((o.ph + o.pa).mean()), 'pts_var': float((o.ph + o.pa).var())}

def ot_q(mu_m, OT):
    mu = OT['c'] * mu_m * 300 / 2880; sd = np.sqrt(OT['v']); h = OT.get('h', 0.5)
    pw = 1 - norm.cdf((h - mu) / sd); pl = norm.cdf((-h - mu) / sd)
    return pw / (pw + pl), 1 - pw - pl

H_EDGES = [0, 1, 2, 3, 5, 8, 12, 24, 48]          # kalan dakika grupları
def h_of(tau, P):
    g = np.searchsorted(H_EDGES, np.clip(np.asarray(tau, float) / 60.0, 1e-9, 48), side='left') - 1
    return np.array(P['h'])[np.clip(g, 0, len(P['h']) - 1)]

def fit_h(mask, P):
    d = S[mask & reg]
    _, rm, _ = means(d, np.array(P['share']), P['kt'], P['km'], P['beta'])
    mu = d.m.values + rm; sd = np.sqrt(V_of(2880 - d.k.values, np.array(P['Vm'])))
    tie = (d.mreg.values == 0)
    tau = (2880 - d.k.values) / 60.0
    out = []
    for lo, hi in zip(H_EDGES[:-1], H_EDGES[1:]):
        mm = (tau > lo) & (tau <= hi)
        best = None
        for h in np.arange(0.5, 2.51, 0.02):
            p = norm.cdf((h - mu[mm]) / sd[mm]) - norm.cdf((-h - mu[mm]) / sd[mm])
            p = np.clip(p, 1e-9, 1 - 1e-9)
            ll = np.sum(np.where(tie[mm], np.log(p), np.log(1 - p)))
            if best is None or ll > best[0]:
                best = (ll, h)
        out.append(float(best[1]))
    return out

def fit_h_ot(mask_fn, OT):
    gids = PG[mask_fn(PG.file_year)].game_id
    o = PER[PER.game_id.isin(gids) & (PER.period_number >= 5)].merge(PG[['game_id', 'mu_m']], on='game_id')
    mu = OT['c'] * o.mu_m.values * 300 / 2880; sd = np.sqrt(OT['v']); tie = (o.ph - o.pa).values == 0
    best = None
    for h in np.arange(0.5, 3.01, 0.02):
        p = np.clip(norm.cdf((h - mu) / sd) - norm.cdf((-h - mu) / sd), 1e-9, 1 - 1e-9)
        ll = np.sum(np.where(tie, np.log(p), np.log(1 - p)))
        if best is None or ll > best[0]:
            best = (ll, h)
    return float(best[1])

# ---------------------------------------------------------------- 5) olasılıklar
def win_probs(d, P):
    """Normal süre ve uzatma için P(ev kazanır), P(uzatma). d: k, m, mu_m, tot, mu_t + özellikler."""
    SH, Vm = np.array(P['share']), np.array(P['Vm'])
    s, rm, rt = means(d, SH, P['kt'], P['km'], P['beta'])
    q, tie1 = ot_q(d.mu_m.values, P['OT'])
    k = d.k.values; m = d.m.values
    regm = k < 2880
    mu = m + rm; sd = np.sqrt(np.maximum(V_of(2880 - k, Vm), 1e-9))
    h = h_of(2880 - k, P) if 'h' in P else 0.5
    p_hi = 1 - norm.cdf((h - mu) / sd); p_tie = norm.cdf((h - mu) / sd) - norm.cdf((-h - mu) / sd)
    p_reg = p_hi + p_tie * q
    # uzatmada: içinde bulunulan uzatmanın kalan saniyesi
    tl_ot = 300 - ((k - 2880) % 300)
    mu_o = m + P['OT']['c'] * d.mu_m.values * tl_ot / 2880
    sd_o = np.sqrt(np.maximum(P['OT']['v'] * tl_ot / 300, 1e-9))
    ho = P['OT'].get('h', 0.5)
    po_hi = 1 - norm.cdf((ho - mu_o) / sd_o); po_tie = norm.cdf((ho - mu_o) / sd_o) - norm.cdf((-ho - mu_o) / sd_o)
    p_ot_state = po_hi + po_tie * q
    pw = np.where(regm, p_reg, p_ot_state)
    pot = np.where(regm, p_tie, 1.0)
    return np.clip(pw, 1e-6, 1 - 1e-6), pot, mu, sd, rt, s

def baseline_p(d):
    ot = d.k.values >= 2880
    tl = np.where(ot, 300 - ((d.k.values - 2880) % 300), 2880 - d.k.values)
    f = {'m_over_sqrt_tl': d.m.values / np.sqrt(tl + 1.0), 'is_ot': ot.astype(float),
         'spread_x_tl': d.sp.values * (tl / 2880.0), 'spread_x_sqrt_tl': d.sp.values * np.sqrt(tl / 2880.0)}
    z = BASE['intercept'] + sum(c * f[n] for n, c in zip(BASE['features'], BASE['coef']))
    return 1 / (1 + np.exp(-z))

def logit_feats(d):
    ot = d.k.values >= 2880
    tl = np.where(ot, 300 - ((d.k.values - 2880) % 300), 2880 - d.k.values)
    return np.c_[d.m.values / np.sqrt(tl + 1.0), ot.astype(float), d.sp.values * (tl / 2880.0), d.sp.values * np.sqrt(tl / 2880.0)]

def fit_logit(mask):
    from sklearn.linear_model import LogisticRegression
    d = S[mask]
    lr = LogisticRegression(C=1e4, max_iter=100000, tol=1e-10).fit(logit_feats(d), d.home_win_final.values)
    return lr

def brier(p, y): return float(np.mean((p - y) ** 2))
def logloss(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

def boot_diff(d, a, b, y, reps=500, seed=0):
    df = pd.DataFrame({'g': d.game_id.values, 'x': (a - y) ** 2 - (b - y) ** 2}).groupby('g').x.mean()
    rng = np.random.default_rng(seed); v = df.values
    bs = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(reps)]
    return float(v.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))

def build(mask_fn, kt, km, beta_cols, var_fn=None):
    """Verilen yıllarla tüm parametreleri kestir. var_fn: belirsizlik eğrileri için yıllar (yoksa mask_fn)."""
    m = mask_fn(S.file_year)
    vm_mask = (var_fn or mask_fn)(S.file_year)
    SH = share_table(intensity(m))
    beta = {}
    if beta_cols:
        d = S[m & reg]
        s, rm, _ = means(d, SH, kt, km, {})
        R = d.mreg.values - d.m.values - rm
        X = np.c_[[feat(d, c, s) for c in beta_cols]].T
        b, *_ = np.linalg.lstsq(X, R, rcond=None)
        beta = dict(zip(beta_cols, map(float, b)))
    Vm, Vt, Cmt, bias = var_curves(vm_mask, SH, kt, km, beta)
    OT = ot_params(mask_fn)
    P = {'share': list(SH), 'Vm': list(Vm), 'Vt': list(Vt), 'Cmt': list(Cmt), 'kt': kt, 'km': km, 'beta': beta, 'OT': OT}
    P['h'] = fit_h(vm_mask, P)
    P['OT']['h'] = fit_h_ot(mask_fn, P['OT'])
    # periyot varyansları (maç öncesi bilgiyle tam periyot farkı)
    gids = PG[(var_fn or mask_fn)(PG.file_year)].game_id
    pp = PER[PER.game_id.isin(gids) & (PER.period_number <= 4)].merge(PG[['game_id', 'mu_m', 'mu_t']], on='game_id')
    j = pp.period_number.values
    shj = SH[(j - 1) * 12] - SH[j * 12]
    vj = pd.Series((pp.ph - pp.pa - pp.mu_m * shj) ** 2).groupby(j).mean()
    vtj = pd.Series((pp.ph + pp.pa - pp.mu_t * shj) ** 2).groupby(j).mean()
    P['v_per'] = [float(vj[i]) for i in (1, 2, 3, 4)]
    P['vt_per'] = [float(vtj[i]) for i in (1, 2, 3, 4)]
    return P, bias

# ======================================================================== SEÇİMLER (eğitim -> doğrulama)
log('=== 1) TEMPO VE GÜÇ GÜNCELLEMESİ (eğitim 2014-2021 ile seçim) ===')
SH_tr = share_table(intensity(TR(S.file_year)))
et, kt = fit_kappa(TR(S.file_year), SH_tr, 't')
em, km = fit_kappa(TR(S.file_year), SH_tr, 'm')
d0 = S[TR(S.file_year) & reg]
_, _, rt0 = means(d0, SH_tr, None, None, {}); _, rm0, _ = means(d0, SH_tr, None, None, {})
log(f'Toplam sayı: güncellemesiz MSE={np.mean((d0.treg - d0.tot - rt0) ** 2):.2f}  en iyi kappa={kt}  MSE={et:.2f}')
log(f'Fark: güncellemesiz MSE={np.mean((d0.mreg - d0.m - rm0) ** 2):.2f}  en iyi kappa={km}  MSE={em:.2f}')
dv = S[VA(S.file_year) & reg]
for name, kk in (('toplam', kt),):
    _, _, a = means(dv, SH_tr, None, None, {}); _, _, b = means(dv, SH_tr, kk, None, {})
    log(f'  doğrulama 2022, toplam MSE: güncellemesiz={np.mean((dv.treg - dv.tot - a) ** 2):.2f}  güncellemeli={np.mean((dv.treg - dv.tot - b) ** 2):.2f}')
_, a, _ = means(dv, SH_tr, None, None, {}); _, b, _ = means(dv, SH_tr, None, km, {})
log(f'  doğrulama 2022, fark MSE: güncellemesiz={np.mean((dv.mreg - dv.m - a) ** 2):.2f}  güncellemeli={np.mean((dv.mreg - dv.m - b) ** 2):.2f}')

log('\n=== 2) MOMENTUM VE FAUL SIKINTISI (eğitimde kestirim, doğrulamada karar) ===')
BASEF = ['ms']
P_noms, _ = build(TR, kt, km, [])
P0, _ = build(TR, kt, km, BASEF)
dvv = S[VA(S.file_year)]
yv = dvv.home_win_final.values
p0, *_ = win_probs(dvv, P0)
p_noms, *_ = win_probs(dvv, P_noms)
log(f'Doğrulama Brier: lojistik (mevcut)={brier(baseline_p(dvv), yv):.5f}  dağılım modeli (fark erimesi ve beraberlik düzeltmesi yok)={brier(p_noms, yv):.5f}')
log(f"Doğrulama Brier, fark erimesi eklendi (katsayı={P0['beta']['ms']:+.3f}): {brier(p0, yv):.5f}")
cands = {'momentum (son 5 dk fark değişimi)': ['run5'], 'momentum (son 3 dk)': ['run3'],
         'faul sıkıntısı (önem ağırlıklı)': ['fd'], 'faulle oyundan çıkma (önem ağırlıklı)': ['fd_out']}
keep = []
dtr = S[TR(S.file_year) & reg]
for name, cols in cands.items():
    Pc, _ = build(TR, kt, km, BASEF + cols)
    pc, *_ = win_probs(dvv, Pc)
    # katsayı için maç kümeli bootstrap (eğitim)
    s, rm, _ = means(dtr, np.array(Pc['share']), kt, km, {'ms': P0['beta']['ms']})
    R = dtr.mreg.values - dtr.m.values - rm
    X = dtr[cols[0]].values
    g = dtr.game_id.values
    sxy = pd.Series(X * R).groupby(g).sum(); sxx = pd.Series(X * X).groupby(g).sum()
    rng = np.random.default_rng(1); idx = np.arange(len(sxy))
    bs = []
    for _ in range(300):
        ii = rng.integers(0, len(idx), len(idx)); bs.append(sxy.values[ii].sum() / sxx.values[ii].sum())
    _, _, _, _, _, _ = (None,) * 6
    mse_v0 = np.mean((dvv[dvv.k < 2880].mreg - dvv[dvv.k < 2880].m - means(dvv[dvv.k < 2880], np.array(P0['share']), kt, km, P0['beta'])[1]) ** 2)
    mse_v1 = np.mean((dvv[dvv.k < 2880].mreg - dvv[dvv.k < 2880].m - means(dvv[dvv.k < 2880], np.array(Pc['share']), kt, km, Pc['beta'])[1]) ** 2)
    b = Pc['beta'][cols[0]]
    log(f'{name:42s} katsayı={b:+.3f} [%95: {np.percentile(bs, 2.5):+.3f}, {np.percentile(bs, 97.5):+.3f}]  '
        f'doğrulama fark MSE {mse_v0:.3f}->{mse_v1:.3f}  Brier {brier(p0, yv):.5f}->{brier(pc, yv):.5f}')
    if brier(pc, yv) < brier(p0, yv) - 0.0001 and mse_v1 < mse_v0:
        keep.append(cols[0])
log(f'Doğrulamaya göre tutulanlar (Brier en az 0,0001 düşmeli): {keep if keep else "yok"}')

# ======================================================================== SON MODEL (2014-2022) VE TEST
VARY = lambda y: (y >= 2020) & (y <= 2022)     # belirsizlik: son üç sezon (doğrulamada seçildi)
P, bias = build(TV, kt, km, BASEF + keep, VARY)
log('\n=== 3) SON MODEL (2014-2022 ile kestirildi) ===')
log(f"Uzatma: c={P['OT']['c']:.3f} varyans={P['OT']['v']:.2f} n={P['OT']['n']} gözlenen uzatma beraberliği={P['OT']['emp_tie']:.3f}")
q_, tie1 = ot_q(np.array([0.0]), P['OT'])
log(f'  model: tek uzatmada beraberlik={tie1[0]:.3f} (yarı genişlik h={P["OT"]["h"]:.2f})')
log(f"Normal süre sonu beraberlik yarı genişliği h (kalan dk grupları {H_EDGES}): {P['h']}")
log(f"Fark erimesi katsayısı (mevcut fark x kalan pay): {P['beta']}")
log(f"Periyot fark varyansları (sd): {[round(np.sqrt(v), 2) for v in P['v_per']]}")
log(f"Kalan süre belirsizliği sd (fark): 48dk={np.sqrt(P['Vm'][48]):.2f} 24dk={np.sqrt(P['Vm'][24]):.2f} 12dk={np.sqrt(P['Vm'][12]):.2f} 2dk={np.sqrt(P['Vm'][2]):.2f}")
log(f"  (toplam):                  48dk={np.sqrt(P['Vt'][48]):.2f} 24dk={np.sqrt(P['Vt'][24]):.2f} 12dk={np.sqrt(P['Vt'][12]):.2f}")
log(f'  fark ortalamasında en büyük sapma (eğitim, dakika bazında): {np.nanmax(np.abs(bias)):.2f} sayı')

T = S[TE(S.file_year)].copy()
y = T.home_win_final.values.astype(float)
pw, pot, mu, sd, rt, s = win_probs(T, P)
pb = baseline_p(T)
lr_f = fit_logit((S.file_year >= 2013) & (S.file_year <= 2022))
pc = lr_f.predict_proba(logit_feats(T))[:, 1]
log('\n=== 4) TEST 2023-2026: KAZANMA OLASILIĞI (aynı anlık görüntüler) ===')
log(f'Lojistik, teslim edilen (zamanı kaymış veriyle eğitilmiş): Brier={brier(pb, y):.4f} log loss={logloss(pb, y):.4f}  n={len(T)}')
log(f'Lojistik, düzeltilmiş veriyle yeniden eğitildi:           Brier={brier(pc, y):.4f} log loss={logloss(pc, y):.4f}')
log(f'  yeni katsayılar: sabit={lr_f.intercept_[0]:.4f} {np.round(lr_f.coef_[0], 4).tolist()}')
log(f'Yeni model (skor dağılımı):                             Brier={brier(pw, y):.4f} log loss={logloss(pw, y):.4f}')
MET['win'] = {'n': int(len(T)), 'brier_delivered': brier(pb, y), 'brier_fixed': brier(pc, y), 'brier_new': brier(pw, y),
              'll_delivered': logloss(pb, y), 'll_new': logloss(pw, y), 'brier_const': brier(np.full(len(y), y.mean()), y)}
md, lo, hi = boot_diff(T, pw, pb, y)
MET['win']['diff_new_delivered'] = [md, lo, hi]
log(f'Fark (yeni - teslim edilen lojistik), maç kümeli bootstrap: {md:+.4f} [%95: {lo:+.4f}, {hi:+.4f}]')
md, lo, hi = boot_diff(T, pw, pc, y)
log(f'Fark (yeni - düzeltilmiş lojistik): {md:+.4f} [%95: {lo:+.4f}, {hi:+.4f}]')
md, lo, hi = boot_diff(T, pc, pb, y)
log(f'Fark (düzeltilmiş - teslim edilen lojistik): {md:+.4f} [%95: {lo:+.4f}, {hi:+.4f}]')
tl = np.where(T.k >= 2880, -1, 2880 - T.k)
bk = pd.cut(tl, [-2, 0, 300, 720, 1440, 2160, 2881], labels=['Uzatma', 'Son 5 dk', '5-12 dk', '12-24 dk', '24-36 dk', '36-48 dk'])
MET['buckets'] = []
for b in ['36-48 dk', '24-36 dk', '12-24 dk', '5-12 dk', 'Son 5 dk', 'Uzatma']:
    mm = (bk == b)
    MET['buckets'].append({'label': b, 'n': int(mm.sum()), 'delivered': brier(pb[mm], y[mm]), 'new': brier(pw[mm], y[mm]),
                           'const': brier(np.full(mm.sum(), 0.5), y[mm])})
    log(f'  {b:9s} n={mm.sum():6d} teslim edilen={brier(pb[mm], y[mm]):.4f} düzeltilmiş={brier(pc[mm], y[mm]):.4f} yeni={brier(pw[mm], y[mm]):.4f}')
log('Kalibrasyon (yeni model, 10 bölme): ')
cb = pd.cut(pw, np.linspace(0, 1, 11), include_lowest=True)
cal = pd.DataFrame({'p': pw, 'y': y, 'b': cb}).groupby('b', observed=True).agg(n=('y', 'size'), tahmin=('p', 'mean'), gercek=('y', 'mean'))
log(cal.round(3).to_string())
MET['calib'] = [{'n': int(r.n), 'pred': float(r.tahmin), 'obs': float(r.gercek)} for r in cal.itertuples()]

# ---- uzatma olasılığı
regT = T.k.values < 2880
yo = T.has_ot.values.astype(float)
base_ot = float(PG[TV(PG.file_year)].has_ot.mean())
log('\n=== 5) TEST: UZATMAYA GİTME OLASILIĞI (normal süre anları) ===')
log(f'Sabit oran ({base_ot:.4f}): Brier={brier(np.full(regT.sum(), base_ot), yo[regT]):.5f}   Model: Brier={brier(pot[regT], yo[regT]):.5f}')
for b in ['36-48 dk', '24-36 dk', '12-24 dk', '5-12 dk', 'Son 5 dk']:
    mm = (bk == b) & regT
    log(f'  {b:9s} sabit={brier(np.full(mm.sum(), base_ot), yo[mm]):.5f} model={brier(pot[mm], yo[mm]):.5f}  ort. tahmin={pot[mm].mean():.4f} gerçek={yo[mm].mean():.4f}')
cbo = pd.cut(pot[regT], [0, 0.02, 0.05, 0.1, 0.2, 0.4, 1.0], include_lowest=True)
oc = pd.DataFrame({'p': pot[regT], 'y': yo[regT], 'b': cbo}).groupby('b', observed=True).agg(n=('y', 'size'), tahmin=('p', 'mean'), gercek=('y', 'mean'))
log(oc.round(4).to_string())
MET['ot'] = {'brier_model': brier(pot[regT], yo[regT]), 'brier_const': brier(np.full(regT.sum(), base_ot), yo[regT]), 'base': base_ot,
             'calib': [{'n': int(r.n), 'pred': float(r.tahmin), 'obs': float(r.gercek)} for r in oc.itertuples()]}

# ---- skor tahmini: kontrol noktaları
log('\n=== 6) TEST: SKOR TAHMİNİ (normal süre sonu) ===')
naive_rate = float(PG[TV(PG.file_year)].treg.mean())
MET['score'] = []
for kk, lab in ((0, 'Maç öncesi'), (720, '1. çeyrek sonu'), (1440, 'Devre arası'), (2160, '3. çeyrek sonu'), (2520, 'Son 6 dk')):
    mm = (T.k.values == kk)
    d = T[mm]
    et_ = d.tot.values + rt[mm]; em_ = d.m.values + (mu[mm] - d.m.values)
    naive_t = d.tot.values + naive_rate * s[mm]
    sdm = sd[mm]; sdt = np.sqrt(V_of(2880 - kk, np.array(P['Vt'])))
    cov_m = np.mean(np.abs(d.mreg.values - em_) <= 1.2816 * sdm)
    cov_t = np.mean(np.abs(d.treg.values - et_) <= 1.2816 * sdt)
    MET['score'].append({'label': lab, 'n': int(mm.sum()), 'mae_t': float(np.mean(np.abs(d.treg - et_))), 'mae_t_naive': float(np.mean(np.abs(d.treg - naive_t))),
                         'mae_m': float(np.mean(np.abs(d.mreg - em_))), 'cov_m': float(cov_m), 'cov_t': float(cov_t)})
    log(f'  {lab:15s} n={mm.sum():5d}  toplam MAE: model={np.mean(np.abs(d.treg - et_)):5.2f} (bilgisiz={np.mean(np.abs(d.treg - naive_t)):5.2f})  '
        f'fark MAE={np.mean(np.abs(d.mreg - em_)):5.2f}  %80 aralık kapsaması: fark={cov_m:.3f} toplam={cov_t:.3f}')

# ---- periyot sonuçları
log('\n=== 7) TEST: PERİYOT SONUÇLARI (ev kazanır / berabere / dep kazanır) ===')
def period_probs(d, P, j):
    """d anlık görüntüleri için j. periyodun sonuç olasılıkları."""
    SH = np.array(P['share']); Vm = np.array(P['Vm'])
    k = d.k.values; st, en = 720 * (j - 1), 720 * j
    s, rm, _ = means(d, SH, P['kt'], P['km'], P['beta'])
    base_rem = d.mu_m.values * s
    adj = rm - base_rem                                   # güncellemelerin kalan maça eklediği
    a0 = np.clip(k, st, en)
    share_rem = s_of(a0, SH) - s_of(en, SH)
    with np.errstate(divide='ignore', invalid='ignore'):
        frac = np.where(s > 1e-9, share_rem / s, 0.0)
    mean_inc = d.mu_m.values * share_rem + adj * frac
    full = V_of(2880 - st, Vm) - V_of(2880 - en, Vm)
    part = V_of(2880 - a0, Vm) - V_of(2880 - en, Vm)
    var = P['v_per'][j - 1] * np.where(full > 0, part / full, 0)
    return mean_inc, var

gper = PER[PER.period_number <= 4].assign(pm=lambda x: x.ph - x.pa)
pm_t = gper.pivot(index='game_id', columns='period_number', values='pm')
st_t = gper.assign(ms=lambda x: x.h_start - x.a_start).pivot(index='game_id', columns='period_number', values='ms')
base_cls = {}
trv = gper[gper.game_id.isin(PG[TV(PG.file_year)].game_id)]
for j in (1, 2, 3, 4):
    x = trv[trv.period_number == j].pm
    base_cls[j] = np.array([(x > 0).mean(), (x == 0).mean(), (x < 0).mean()])
def cls_probs(d, P, j):
    mi, var = period_probs(d, P, j)
    sdv = np.sqrt(np.maximum(var, 1e-9))
    st_m = st_t.reindex(d.game_id.values)[j].values
    so_far = np.where(d.k.values >= 720 * (j - 1), d.m.values - st_m, 0.0)
    so_far = np.where(np.isnan(so_far), 0.0, so_far)
    mu_ = so_far + mi
    ph_ = 1 - norm.cdf((0.5 - mu_) / sdv); pt_ = norm.cdf((0.5 - mu_) / sdv) - norm.cdf((-0.5 - mu_) / sdv)
    return np.c_[ph_, pt_, 1 - ph_ - pt_]
for j in (1, 2, 3, 4):
    for kk, lab in ((0, 'maç öncesi'), (720 * (j - 1), 'periyot başında'), (720 * (j - 1) + 360, 'periyot ortasında')):
        if lab == 'periyot başında' and j == 1:
            continue
        d = T[T.k.values == kk]
        pmv = pm_t.reindex(d.game_id.values)[j].values
        Y = np.c_[pmv > 0, pmv == 0, pmv < 0].astype(float)
        Pp = cls_probs(d, P, j)
        b3 = np.mean(np.sum((Pp - Y) ** 2, 1)); bb = np.mean(np.sum((base_cls[j] - Y) ** 2, 1))
        MET.setdefault('periods', []).append({'j': j, 'when': lab, 'n': int(len(d)), 'brier_const': float(bb), 'brier_model': float(b3),
                                              'tie_pred': float(Pp[:, 1].mean()), 'tie_obs': float(Y[:, 1].mean())})
        log(f'  {j}. periyot, {lab:18s} n={len(d):5d}  3 sınıf Brier: sabit oran={bb:.4f} model={b3:.4f}  '
            f'(berabere tahmini ort={Pp[:, 1].mean():.3f}, gerçek={Y[:, 1].mean():.3f})')

# ---- parametreleri yaz
P['naive_treg'] = naive_rate
P['logit_fixed'] = {'intercept': float(lr_f.intercept_[0]), 'coef': list(map(float, lr_f.coef_[0]))}
P['H_EDGES'] = H_EDGES
P['base_ot_rate'] = base_ot
P['base_cls'] = {j: list(map(float, v)) for j, v in base_cls.items()}
json.dump(P, open(os.path.join(work, 'sim_params.json'), 'w'), indent=1)
json.dump(MET, open(os.path.join(work, 'metrics.json'), 'w'), indent=1, ensure_ascii=False)
open(os.path.join(work, 'model_report.txt'), 'w').write('\n'.join(REP) + '\n')
