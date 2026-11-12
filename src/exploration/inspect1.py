import sys, pandas as pd
df = pd.read_parquet(sys.argv[1])
print(df.shape); print(df.dtypes.to_string())
print("games", df.game_id.nunique())
print(df.season_type.value_counts(dropna=False).to_string())
if 'score_source' in df: print(df.score_source.value_counts(dropna=False).to_string())
for c in ['home_team_spread','game_spread','home_favorite']:
    g=df.groupby('game_id')[c].first(); print(c,'nonnull games',g.notna().sum(),'of',len(g)); print(g.describe().to_string() if g.dtype!=object else g.value_counts().head())
mp=df.groupby('game_id').period_number.max(); print("max period dist"); print(mp.value_counts().sort_index().to_string())
print(df.groupby('season_type').game_id.nunique().to_string())
print(df.head(3).T.to_string())
