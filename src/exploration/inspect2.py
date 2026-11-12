import sys, pandas as pd, numpy as np
df = pd.read_parquet(sys.argv[1])
df = df.sort_values(['game_id','game_play_number'])
print("dup (game,play_number):", df.duplicated(['game_id','game_play_number']).sum(), " dup id:", df.duplicated(['game_id','id']).sum())
print("game_spread_available:", df.groupby('game_id').game_spread_available.first().value_counts().to_dict())
g = df.groupby('game_id')
last = g.tail(1).set_index('game_id')
first = g.head(1).set_index('game_id')
res = pd.DataFrame({'hs':last.home_score,'as_':last.away_score,'spr':first.home_team_spread,'fav':first.home_favorite,'st':first.season_type,'per':g.period_number.max(),'n':g.size(),'date':first.game_date})
res['home_win']=(res.hs>res.as_)
res['margin']=res.hs-res.as_
print("ties at last row:", (res.margin==0).sum(), " home win rate:", res.home_win.mean().round(3))
print("rows/game:", res.n.describe().round(1).to_dict())
print("short games (<300 rows):", (res.n<300).sum())
# spread sign vs margin
print("corr(spread, margin):", np.corrcoef(res.spr,res.margin)[0,1].round(3))
print("fav sign agrees with spread>0:", ((res.spr>0)==res.fav).mean().round(3))
print("spread==0:", (res.spr==0).sum())
# spread-implied pick accuracy
pick = res.spr>0
print("spread-pick accuracy:", (pick==res.home_win).mean().round(3))
# score monotonic within game
bad=0; bad_games=set()
for gid,d in df.groupby('game_id'):
    if (d.home_score.diff().dropna()<0).any() or (d.away_score.diff().dropna()<0).any():
        bad+=1; bad_games.add(gid)
print("games with decreasing score:", bad)
# time monotonic: end_game_seconds_remaining non-increasing
bt=0
for gid,d in df.groupby('game_id'):
    if (d.start_game_seconds_remaining.diff().dropna()>0).any(): bt+=1
print("games where start_game_seconds_remaining increases:", bt)
print("clock NaN rows:", df.start_game_seconds_remaining.isna().sum())
print("last row seconds remaining dist:", last.end_game_seconds_remaining.describe().round(1).to_dict())
# OT frac regular season
rs=res[res.st==2]; print("reg season games",len(rs),"OT frac", (rs.per>4).mean().round(3), "n OT",(rs.per>4).sum())
print("date range", res.date.min(), res.date.max())
print("sum of scoring_play score_value vs final total (mismatch games):", end=" ")
s=df[df.scoring_play].groupby('game_id').score_value.sum()
print(((s - (res.hs+res.as_).reindex(s.index))!=0).sum(), "of", len(s))
print("type_text top:"); print(df.type_text.value_counts().head(12).to_string())
