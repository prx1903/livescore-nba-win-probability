"""
Modeli maç türüne göre ayrı ölçer: normal sezon, playoff, play-in. Yalnızca test sezonları (dosya yılı 2023-2026).

Kullanım:
  python src/eval_by_season_type.py data/processed models/model_coefficients.json results

Çıktı: results/season_type_report.txt

Anlık görüntüler train_baseline.py ile aynı kurala göre alınır (60 sn aralık, o ana kadarki son olay).
Tahmin winprob.predict ile yapılır, yani uygulamanın kullandığı formülle aynıdır.
Güven aralıkları maç-kümeli bootstrap ile (aynı maçın anları birlikte örneklenir).
season_type kodları (ESPN): 2 = normal sezon, 3 = playoff, 5 = play-in.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from winprob import load_model, predict

TYPE_NAMES = {2: 'normal sezon', 3: 'playoff', 5: 'play-in'}
TEST_YEARS = range(2023, 2027)

data_dir, model_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out_dir, exist_ok=True)
model = load_model(model_path)
games = pd.read_csv(os.path.join(data_dir, 'games.csv'))
games = games[games.is_valid & games.spread_home.notna() & games.file_year.isin(TEST_YEARS)].set_index('game_id')


def snapshots(year):
    d = pd.read_parquet(os.path.join(data_dir, 'pbp_clean', f'pbp_clean_{year}.parquet'),
                        columns=['game_id', 'game_play_number', 'game_seconds_elapsed', 'home_score', 'away_score'])
    d['game_id'] = d.game_id.astype('int64'); d['game_seconds_elapsed'] = d.game_seconds_elapsed.astype('float64')
    d = d[d.game_id.isin(games.index)].sort_values(['game_seconds_elapsed', 'game_play_number'], kind='stable')  # aynı saniyede olay sırasına göre son olay
    length = d.groupby('game_id').game_seconds_elapsed.max()
    grid = []
    for gid, L in length.items():
        ks = np.arange(0, int(L), 60)
        ks = ks[ks != 2880]
        grid.append(pd.DataFrame({'game_id': gid, 'k': ks.astype(float)}))
    grid = pd.concat(grid); grid['game_id'] = grid.game_id.astype('int64'); grid = grid.sort_values('k')
    s = pd.merge_asof(grid, d, left_on='k', right_on='game_seconds_elapsed', by='game_id', direction='backward')
    return s.dropna(subset=['home_score'])


S = pd.concat([snapshots(y) for y in TEST_YEARS], ignore_index=True)
k = S.k.values
ot = k >= 2880
tl = np.where(ot, 300 - ((k - 2880) % 300), 2880 - k)
m = (S.home_score - S.away_score).values
sp = games.spread_home.reindex(S.game_id).values
S['p'] = [predict(model, int(mi), float(t), bool(o), float(s)) for mi, t, o, s in zip(m, tl, ot, sp)]
S['y'] = games.home_win_final.reindex(S.game_id).values
S['season_type'] = games.season_type.reindex(S.game_id).values
S['sq'] = (S.p - S.y) ** 2
pc = S.p.clip(1e-3, 1 - 1e-3)
S['ll'] = -(S.y * np.log(pc) + (1 - S.y) * np.log(1 - pc))

rng = np.random.default_rng(0)
def boot_ci(per_game, n=1000):
    v = per_game.values
    means = [v[rng.integers(0, len(v), len(v))].mean() for _ in range(n)]
    return np.percentile(means, 2.5), np.percentile(means, 97.5)

lines = []
def log(t): print(t); lines.append(t)
log(f'Maç türüne göre test sonuçları (dosya yılı {TEST_YEARS.start}-{TEST_YEARS.stop - 1}), model: {model.get("train", "?")}')
log('Brier ve log loss maç başına ortalanıp maçlar arasında ortalandı; aralıklar maç-kümeli bootstrap %95.\n')
log(f'{"tür":14s} {"maç":>5s} {"an":>7s} {"ev kazanma":>10s} {"Brier":>7s} {"%95 aralık":>17s} {"log loss":>8s}')
per_game = S.groupby(['season_type', 'game_id'])[['sq', 'll']].mean()
for t, name in TYPE_NAMES.items():
    if t not in per_game.index.get_level_values(0):
        continue
    pg = per_game.loc[t]
    lo, hi = boot_ci(pg.sq)
    hw = games[games.season_type == t].home_win_final.mean()
    log(f'{name:14s} {len(pg):5d} {int((S.season_type == t).sum()):7d} {hw:10.3f} {pg.sq.mean():7.4f} '
        f'[{lo:.4f}, {hi:.4f}] {pg.ll.mean():8.4f}')

reg, po = per_game.loc[2].sq, per_game.loc[3].sq if 3 in per_game.index.get_level_values(0) else None
if po is not None:
    diffs = [po.values[rng.integers(0, len(po), len(po))].mean() - reg.values[rng.integers(0, len(reg), len(reg))].mean()
             for _ in range(1000)]
    log(f'\nPlayoff - normal sezon Brier farkı: {po.mean() - reg.mean():+.4f}  %95 aralık [{np.percentile(diffs, 2.5):+.4f}, {np.percentile(diffs, 97.5):+.4f}]')
    log('Aralık sıfırı içeriyorsa fark bu veriyle ayırt edilemiyor demektir.')

log('\nKalibrasyon (5 eşit bölme): tahmin ortalaması / gerçekleşen oran / an sayısı')
S['bin'] = pd.cut(S.p, np.linspace(0, 1, 6), include_lowest=True)
for t, name in TYPE_NAMES.items():
    sub = S[S.season_type == t]
    if not len(sub):
        continue
    parts = [f'{b}: {g.p.mean():.3f}/{g.y.mean():.3f}/{len(g)}' for b, g in sub.groupby('bin', observed=True)]
    log(f'  {name}: ' + '  '.join(parts))

log('\nNot: model tüm maç türleriyle birlikte eğitildi; playoff ve play-in için ayrı bir ayar yok.')
log('Play-in maç sayısı az olduğu için bu satır yalnızca bilgi amaçlıdır.')
open(os.path.join(out_dir, 'season_type_report.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
