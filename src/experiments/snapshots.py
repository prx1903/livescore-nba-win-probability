"""Deneyler icin ortak an goruntusu tablosu (tek kaynak, bir kez uretilir, parquet olarak onbellege alinir).

Anlik goruntu kurali train_baseline.py ile BIREBIR AYNI:
  - her mac icin 60 sn araliklarla k = 0, 60, ... (k = 2880 haric)
  - o ana kadarki son olay (merge_asof, backward); ayni saniyede birden fazla olay varsa
    game_play_number'a gore en sondaki
  - gecerli ve spread'i dolu maclar

Ek kolonlar (yalnizca aday modeller icin, baseline'da kullanilmaz):
  - takim gucu durumu: O_h, D_h, O_a, D_a, L, H (results/v2/pregame.parquet; her mac icin
    YALNIZCA o macten onceki maclarla hesaplanmis cevrimici durum)
  - rm = exp_h - exp_a, rt = exp_h + exp_a

Kullanim: python3 -I snapshots.py <veri_klasoru> <pregame_parquet|-> <cikti_parquet>
"""
import sys, os
import numpy as np, pandas as pd

def build(data_dir, pregame_path=None, years=range(2013, 2027)):
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

    S = pd.concat([snapshots(y) for y in years], ignore_index=True)
    S['y'] = games.home_win_final.reindex(S.game_id).values.astype(float)
    S['spread'] = games.spread_home.reindex(S.game_id).values
    S['season_type'] = games.season_type.reindex(S.game_id).values
    k = S.k.values
    S['is_ot'] = (k >= 2880).astype(float)
    S['tl'] = np.where(k >= 2880, 300 - ((k - 2880) % 300), 2880 - k).astype(float)
    S['m'] = (S.home_score - S.away_score).values.astype(float)
    if pregame_path:
        pg = pd.read_parquet(pregame_path, columns=['game_id', 'O_h', 'D_h', 'O_a', 'D_a', 'L', 'H', 'exp_h', 'exp_a'])
        pg['rm'] = pg.exp_h - pg.exp_a; pg['rt'] = pg.exp_h + pg.exp_a
        S = S.merge(pg.drop(columns=['exp_h', 'exp_a']), on='game_id', how='left')
    return S

if __name__ == '__main__':
    data_dir, pg, out = sys.argv[1], sys.argv[2], sys.argv[3]
    S = build(data_dir, None if pg == '-' else pg)
    S.to_parquet(out, index=False)
    print('an goruntusu:', len(S), '| mac:', S.game_id.nunique(), '| kolon:', list(S.columns))
    print('guc puani eksik satir:', int(S.O_h.isna().sum()) if 'O_h' in S else 'kolon yok')
    print(S.groupby('year').size().to_string())
