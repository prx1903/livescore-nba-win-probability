"""Where shots are taken: counts of field-goal attempts on a 1 ft grid, from the raw play-by-play of training seasons.

Usage (from the repository root):
    python -I src/simulation/estimate_shot_locations.py data/raw data/processed results/simulation/shot_locations.json 2022

The raw files (data/raw/play_by_play_<year>.parquet) carry coordinate_x_raw and coordinate_y_raw: x from sideline to
sideline (0-50 ft), y from the centre of the attacked rim towards half court (ft; the free-throw line is at 13.75).
The cleaned play-by-play has no coordinates, so this script reads the raw files; only valid games of games.csv are
used. Output: per category (made2, made3, miss) a list of [x cell, y cell, count] for 1 ft cells (x 0-49, y -5..46;
farther shots are put in the last row). The file holds counts per cell, not single records.
The simulator draws a cell with these weights and a point inside it; only synthetic games use it.
"""
import sys, json
import numpy as np, pandas as pd

raw_dir, data_dir, out_path = sys.argv[1:4]
years = [int(y) for y in sys.argv[4:]] or [2022]
games = pd.read_csv(f'{data_dir}/games.csv')
games = games[games.is_valid]
parts = []
for y in years:
    r = pd.read_parquet(f'{raw_dir}/play_by_play_{y}.parquet',
                        columns=['game_id', 'type_text', 'scoring_play', 'score_value', 'shooting_play',
                                 'coordinate_x_raw', 'coordinate_y_raw'])
    r = r[r.game_id.isin(set(games[games.file_year == y].game_id))]
    r = r[r.shooting_play.astype(bool) & ~r.type_text.fillna('').str.startswith('Free Throw')]
    parts.append(r.dropna(subset=['coordinate_x_raw', 'coordinate_y_raw']))
f = pd.concat(parts)
made = f.scoring_play.astype(bool)
cat = np.where(~made, 'miss', np.where(f.score_value == 3, 'made3', 'made2'))
cx = np.clip(np.floor(f.coordinate_x_raw), 0, 49).astype(int)
cy = np.clip(np.floor(f.coordinate_y_raw), -5, 46).astype(int)
d = pd.DataFrame(dict(cat=cat, x=cx, y=cy))
out = {'source': f'raw play-by-play, file years {years} (training), valid games of games.csv', 'cell_ft': 1,
       'coordinates': 'x 0-50 ft sideline to sideline; y ft from the rim centre towards half court',
       'n': {}, 'categories': {}}
for c, g in d.groupby('cat'):
    cnt = g.groupby(['x', 'y']).size()
    out['categories'][c] = [[int(x), int(y), int(n)] for (x, y), n in cnt.items()]
    out['n'][c] = int(len(g))
json.dump(out, open(out_path, 'w'))
print('written', out_path, out['n'], {c: len(v) for c, v in out['categories'].items()}, 'cells')
