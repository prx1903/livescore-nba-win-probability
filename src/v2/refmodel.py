"""Skor dağılımı modelinin tek durum için Python karşılığı (sayfadaki JavaScript bununla birebir aynı olmalı).
Durum: t (geçen sn, düzeltilmiş), per (periyot), h, a (skor), mstart[j] (j. periyot başındaki fark), tstart[j] (toplam).
Oyun: mu_m (maç öncesi beklenen normal süre farkı, ev - dep), mu_t (beklenen normal süre toplamı).
"""
import numpy as np
from scipy.stats import norm

GRID = np.arange(49) * 60.0


class Ref:
    def __init__(self, P):
        self.P = P
        self.SH = np.array(P['share']); self.Vm = np.array(P['Vm']); self.Vt = np.array(P['Vt']); self.C = np.array(P['Cmt'])
        self.b = P['beta'].get('ms', 0.0); self.OT = P['OT']; self.E = P['H_EDGES']; self.hh = P['h']

    def s(self, k): return float(np.interp(min(max(k, 0.0), 2880.0), GRID, self.SH))
    def V(self, tau, arr): return float(np.interp(min(max(tau, 0.0), 2880.0), GRID, arr))

    def h_of(self, tau):
        x = min(max(tau / 60.0, 1e-9), 48.0)
        g = int(np.searchsorted(self.E, x, side='left')) - 1
        return self.hh[min(max(g, 0), len(self.hh) - 1)]

    def q_ot(self, mu_m):
        O = self.OT; mu = O['c'] * mu_m * 300 / 2880; sd = np.sqrt(O['v']); h = O['h']
        pw = 1 - norm.cdf((h - mu) / sd); pl = norm.cdf((-h - mu) / sd)
        return pw / (pw + pl), 1 - pw - pl

    def state(self, t, per, h, a, mu_m, mu_t, mstart=None, tstart=None):
        m = h - a; out = {}
        q, tie1 = self.q_ot(mu_m)
        O = self.OT
        if per <= 4:
            k = min(t, 2880.0); s = self.s(k); tau = 2880 - k
            rm = mu_m * s + self.b * m * s; rt = mu_t * s
            mu = m + rm; sd = np.sqrt(max(self.V(tau, self.Vm), 1e-9)); hb = self.h_of(tau)
            p_hi = 1 - norm.cdf((hb - mu) / sd); p_tie = norm.cdf((hb - mu) / sd) - norm.cdf((-hb - mu) / sd)
            out.update(pw=float(np.clip(p_hi + p_tie * q, 1e-6, 1 - 1e-6)), pot=float(p_tie), mu=float(mu), sd=float(sd), band=float(hb),
                       mu_t=float(h + a + rt), sd_t=float(np.sqrt(max(self.V(tau, self.Vt), 1e-9))), cov=float(self.V(tau, self.C)),
                       p_reg_win=float(p_hi), p_reg_loss=float(1 - p_hi - p_tie))
            n_ot = 1 / (1 - tie1)
            out['exp_h'] = float(h + (rt + rm) / 2 + p_tie * n_ot * (O['pts_mean'] + O['c'] * mu_m * 300 / 2880) / 2)
            out['exp_a'] = float(a + (rt - rm) / 2 + p_tie * n_ot * (O['pts_mean'] - O['c'] * mu_m * 300 / 2880) / 2)
            # periyotlar
            pers = []
            for j in (1, 2, 3, 4):
                st, en = 720 * (j - 1), 720 * j
                if k >= en or per > j:
                    pers.append(None); continue
                a0 = min(max(k, st), en)
                sr = self.s(a0) - self.s(en)
                adj = self.b * m * s
                frac = sr / s if s > 1e-9 else 0.0
                mean_inc = mu_m * sr + adj * frac
                full = self.V(2880 - st, self.Vm) - self.V(2880 - en, self.Vm)
                part = self.V(2880 - a0, self.Vm) - self.V(2880 - en, self.Vm)
                var = self.P['v_per'][j - 1] * (part / full if full > 0 else 0.0)
                started = k >= st and mstart is not None and j in mstart
                so_m = (m - mstart[j]) if started else 0.0
                so_t = ((h + a) - tstart[j]) if started else 0.0
                mu_j = so_m + mean_inc; sd_j = np.sqrt(max(var, 1e-9))
                ph = 1 - norm.cdf((0.5 - mu_j) / sd_j); pt = norm.cdf((0.5 - mu_j) / sd_j) - norm.cdf((-0.5 - mu_j) / sd_j)
                tot_j = so_t + mu_t * sr
                pers.append({'ph': float(ph), 'pt': float(pt), 'pa': float(1 - ph - pt), 'eh': float((tot_j + mu_j) / 2),
                             'ea': float((tot_j - mu_j) / 2)})
            out['periods'] = pers
        else:
            end = 2880 + 300 * (per - 4); tl = max(end - t, 0.0)
            mu = m + O['c'] * mu_m * tl / 2880; sd = np.sqrt(max(O['v'] * tl / 300, 1e-9)); hb = O['h']
            p_hi = 1 - norm.cdf((hb - mu) / sd); p_tie = norm.cdf((hb - mu) / sd) - norm.cdf((-hb - mu) / sd)
            out.update(pw=float(np.clip(p_hi + p_tie * q, 1e-6, 1 - 1e-6)), pot=1.0, mu=float(mu), sd=float(sd), band=float(hb),
                       p_reg_win=float(p_hi), p_reg_loss=float(1 - p_hi - p_tie), periods=[None] * 4)
            n_more = p_tie / (1 - tie1)
            out['exp_h'] = float(h + (O['pts_mean'] * tl / 300 + (mu - m)) / 2 + n_more * O['pts_mean'] / 2)
            out['exp_a'] = float(a + (O['pts_mean'] * tl / 300 - (mu - m)) / 2 + n_more * O['pts_mean'] / 2)
            out['mu_t'] = float(out['exp_h'] + out['exp_a']); out['sd_t'] = float(np.sqrt(O['pts_var'] * tl / 300 + 1e-9)); out['cov'] = 0.0
        return out
