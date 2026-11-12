"""Model geliştirme için ara tablolar.
Kullanım: python3 -I prep.py <veri_klasoru> <cikti_klasoru>
Çıktılar:
  periods.parquet  : maç x periyot, ev/deplasman periyot sayısı
  snaps.parquet    : 60 sn aralıklı anlık görüntüler (+ son 3/5 dk fark değişimi, faul sıkıntısı)
  fouls_check.txt  : faul sayımı kontrolü
"""
import sys, os
import numpy as np, pandas as pd

data, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
G = pd.read_csv(os.path.join(data, 'games.csv'))
G = G[G.is_valid].copy()
G['game_date'] = pd.to_datetime(G.game_date)
side = pd.concat([G[['game_id', 'home_team_id']].rename(columns={'home_team_id': 'team_id'}).assign(is_home=1),
                  G[['game_id', 'away_team_id']].rename(columns={'away_team_id': 'team_id'}).assign(is_home=0)])

PF = {'Shooting Foul', 'Personal Foul', 'Loose Ball Foul', 'Offensive Foul', 'Offensive Charge', 'Personal Take Foul',
      'Transition Take Foul', 'Flagrant Foul Type 1', 'Flagrant Foul Type 2', 'Clear Path Foul', 'Inbound Foul',
      'Away from Play Foul', 'Double Personal Foul'}
THR = {1: 2, 2: 3, 3: 4, 4: 5}          # periyoda göre "faul sıkıntısı" eşiği; uzatmada 5

def elapsed_from_clock(e):
    c = e.clock_display_value.astype(str)
    sp = c.str.split(':', expand=True)
    sec = np.where(c.str.contains(':'), pd.to_numeric(sp[0], errors='coerce') * 60 + pd.to_numeric(sp[1], errors='coerce'),
                   pd.to_numeric(c, errors='coerce'))
    p = e.period_number.values
    t = np.where(p <= 4, (p - 1) * 720 + (720 - sec), 2880 + (p - 5) * 300 + (300 - sec))
    assert not np.isnan(t).any(), 'saat okunamadı'
    return t.astype(float)

TCHK = []
periods, snaps, ppts, fouls = [], [], [], []
for y in range(2013, 2027):
    e = pd.read_parquet(os.path.join(data, 'pbp_clean', f'pbp_clean_{y}.parquet'),
                        columns=['game_id', 'game_play_number', 'period_number', 'clock_display_value', 'game_seconds_elapsed', 'type_text',
                                 'scoring_play', 'team_id', 'athlete_id_1', 'home_score', 'away_score'])
    e['game_id'] = e.game_id.astype('int64')
    e = e[e.game_id.isin(G.game_id)].sort_values(['game_id', 'game_play_number']).reset_index(drop=True)
    e = e[e.game_id != 400975164]
    # 2013-2019 dosyalarında game_seconds_elapsed kaymış (1.-3. çeyrekte +360/+240/+120 sn).
    # Zaman periyot ve maç saatinden yeniden hesaplanır; 2020+ dosyalarında eski sütunla birebir aynıdır.
    e['t'] = elapsed_from_clock(e)
    TCHK.append((y, len(e), float(np.mean(np.abs(e.t - e.game_seconds_elapsed) > 1.5))))
    # olay sırası zamanla tutarlı mı (geri giden zaman)
    TCHK[-1] += (float(np.mean(e.groupby('game_id').t.diff().fillna(0) < -1.5)),)
    # periyot skorları
    last = e.groupby(['game_id', 'period_number']).agg(h=('home_score', 'last'), a=('away_score', 'last')).reset_index()
    last = last.sort_values(['game_id', 'period_number'])
    last['ph'] = last.groupby('game_id').h.diff().fillna(last.h)
    last['pa'] = last.groupby('game_id').a.diff().fillna(last.a)
    last['h_start'] = last.h - last.ph; last['a_start'] = last.a - last.pa
    last['year'] = y
    periods.append(last)
    # oyuncu sayıları (sayı satırındaki skor artışı)
    e['dh'] = e.groupby('game_id').home_score.diff().fillna(e.home_score)
    e['da'] = e.groupby('game_id').away_score.diff().fillna(e.away_score)
    s = e[(e.scoring_play == True) & e.athlete_id_1.notna()].copy()
    s['pts'] = s.dh + s.da
    ppts.append(s.groupby(['game_id', 'team_id', 'athlete_id_1']).pts.sum().reset_index())
    f = e[e.type_text.isin(PF) & e.athlete_id_1.notna()][['game_id', 'team_id', 'athlete_id_1', 't', 'period_number']].copy()
    f['n'] = f.groupby(['game_id', 'athlete_id_1']).cumcount() + 1
    fouls.append(f)
    # 60 sn anlık görüntüler
    L = e.groupby('game_id').t.max()
    grid = pd.concat([pd.DataFrame({'game_id': gid, 'k': np.arange(0, int(Lg), 60, dtype=float)}) for gid, Lg in L.items()])
    grid = grid[grid.k != 2880].sort_values('k')
    ee = e[['game_id', 't', 'period_number', 'home_score', 'away_score']].sort_values('t', kind='stable')  # e olay sırasında; aynı saniyede son olay
    sn = pd.merge_asof(grid, ee, left_on='k', right_on='t', by='game_id', direction='backward').dropna(subset=['home_score'])
    sn['m'] = sn.home_score - sn.away_score
    for lag in (180, 300):
        g2 = grid.assign(kl=np.maximum(grid.k - lag, 0.0)).sort_values('kl')
        b = pd.merge_asof(g2, ee[['game_id', 't', 'home_score', 'away_score']], left_on='kl', right_on='t', by='game_id',
                          direction='backward')
        b['ml'] = (b.home_score - b.away_score).fillna(0)
        sn = sn.merge(b[['game_id', 'k', 'ml']], on=['game_id', 'k'], how='left')
        sn[f'run{lag // 60}'] = sn.m - sn.ml
        sn = sn.drop(columns='ml')
    sn['year'] = y
    snaps.append(sn.drop(columns=['t']))
    print(y, len(sn), flush=True)

P = pd.concat(periods); S = pd.concat(snaps); PP = pd.concat(ppts); F = pd.concat(fouls)
tl = ['Zaman düzeltmesi: yıl, satır, eski sütundan farklı oran, olay sırasında geri giden zaman oranı']
tl += [str(r) for r in TCHK]
open(os.path.join(out, 'time_check.txt'), 'w').write('\n'.join(tl) + '\n'); print('\n'.join(tl))

# --- faul sayımı kontrolü
pg = F.groupby(['game_id', 'athlete_id_1']).n.max()
chk = [f'oyuncu-maç sayısı (en az 1 faul): {len(pg)}',
       f'6 faul (faulle oyundan çıkma): {(pg == 6).sum()}  ({(pg == 6).mean():.4f})',
       f'6 dan fazla: {(pg > 6).sum()}  ({(pg > 6).mean():.5f})',
       'faul sayısı dağılımı: ' + pg.value_counts().sort_index().to_dict().__repr__()]
open(os.path.join(out, 'fouls_check.txt'), 'w').write('\n'.join(chk) + '\n'); print('\n'.join(chk))

# --- oyuncu önemi: takımın son 20 maçındaki sayılarının payı (bu maç hariç)
PP = PP.merge(G[['game_id', 'game_date']], on='game_id')
tg = PP.groupby(['team_id', 'game_id', 'game_date']).pts.sum().reset_index().sort_values(['team_id', 'game_date', 'game_id'])
tg['tidx'] = tg.groupby('team_id').cumcount()
PP = PP.merge(tg[['team_id', 'game_id', 'tidx']], on=['team_id', 'game_id'])
# her oyuncu için her takım maçında (oynamasa 0) sayı -> son 20 maç toplamı
full = []
for tid, grp in PP.groupby('team_id'):
    piv = grp.pivot_table(index='tidx', columns='athlete_id_1', values='pts', aggfunc='sum')
    idx = np.arange(tg[tg.team_id == tid].tidx.max() + 1)
    piv = piv.reindex(idx).fillna(0.0)
    roll = piv.rolling(20, min_periods=5).sum().shift(1)
    tot = roll.sum(axis=1)
    share = roll.div(tot.replace(0, np.nan), axis=0)
    st = share.stack().rename('w').reset_index().rename(columns={'level_1': 'athlete_id_1'})
    st['team_id'] = tid
    full.append(st)
W = pd.concat(full)
W = W.merge(tg[['team_id', 'tidx', 'game_id']], on=['team_id', 'tidx'])[['game_id', 'team_id', 'athlete_id_1', 'w']]

# --- faul sıkıntısı: eşik th'e ulaşma anı -> önem ağırlıklı birikimli toplam
F = F.merge(W, on=['game_id', 'team_id', 'athlete_id_1'], how='left').fillna({'w': 0.0})
F = F.merge(side, on=['game_id', 'team_id'], how='left')
F['sgn'] = np.where(F.is_home == 1, 1.0, -1.0)
S = S.sort_values('k')
for th in (2, 3, 4, 5, 6):
    r = F[F.n == th][['game_id', 't', 'w', 'sgn']].copy()
    r['v'] = r.w * r.sgn
    r['vh'] = np.where(r.sgn > 0, r.w, 0.0); r['va'] = np.where(r.sgn < 0, r.w, 0.0)
    r = r.sort_values(['game_id', 't'], kind='stable')
    for c in ('v', 'vh', 'va'):
        r[c] = r.groupby('game_id')[c].cumsum()
    r = r.sort_values('t', kind='stable')
    S = pd.merge_asof(S, r[['game_id', 't', 'v', 'vh', 'va']].rename(columns={'v': f'fd{th}', 'vh': f'fh{th}', 'va': f'fa{th}'}),
                      left_on='k', right_on='t', by='game_id', direction='backward').drop(columns='t')
    S[[f'fd{th}', f'fh{th}', f'fa{th}']] = S[[f'fd{th}', f'fh{th}', f'fa{th}']].fillna(0.0)
per = S.period_number.astype(int)
thr = per.map(THR).fillna(5).astype(int)
for c in ('fd', 'fh', 'fa'):
    S[c] = np.select([thr == t for t in (2, 3, 4, 5)], [S[f'{c}{t}'] for t in (2, 3, 4, 5)])
S['fd_out'] = S.fd6
S = S.drop(columns=[f'{c}{t}' for c in ('fd', 'fh', 'fa') for t in (2, 3, 4, 5)] + ['fh6', 'fa6'])
S = S.sort_values(['game_id', 'k']).reset_index(drop=True)
P.to_parquet(os.path.join(out, 'periods.parquet'), index=False)
S.to_parquet(os.path.join(out, 'snaps.parquet'), index=False)
W.to_parquet(os.path.join(out, 'player_weight.parquet'), index=False)
print('periods', len(P), 'snaps', len(S))
print(S.describe().T[['mean', 'std', 'min', 'max']].round(3).to_string())
