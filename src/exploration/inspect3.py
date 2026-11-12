import pandas as pd
df = pd.read_parquet('data/raw/play_by_play_2024.parquet').sort_values(['game_id','game_play_number'])
ot = df[df.period_number>4].game_id.iloc[0]
d = df[df.game_id==ot]
print(d[d.period_number>=4][['period_number','clock_display_value','start_game_seconds_remaining','end_game_seconds_remaining','home_score','away_score','type_text']].iloc[[0,1,-40,-30,-12,-11,-10,-9,-3,-2,-1]].to_string())
print(d.groupby('period_number').start_game_seconds_remaining.agg(['max','min']))
last=df.groupby('game_id').tail(1)
print(last.type_text.value_counts().head()); print(last.end_game_seconds_remaining.isna().mean(), last.start_game_seconds_remaining.describe())
s=df[df.scoring_play].groupby('game_id').score_value.sum()
fin=last.set_index('game_id'); tot=(fin.home_score+fin.away_score)
m=(s-tot.reindex(s.index)); print(m[m!=0])
print("spread==0 games:", df.groupby('game_id').home_team_spread.first().eq(0).sum())
