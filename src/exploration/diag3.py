import pandas as pd, numpy as np, glob
out=[]
for f in sorted(glob.glob('data/raw/play_by_play_*.parquet')):
    y=int(f[-12:-8]); d=pd.read_parquet(f,columns=['game_id','game_play_number','home_score','away_score','period_number','season_type']).sort_values(['game_id','game_play_number'])
    g=d.groupby('game_id')
    last=g.tail(1).set_index('game_id'); mx=g[['home_score','away_score']].max()
    diff_last_vs_max=((last.home_score!=mx.home_score)|(last.away_score!=mx.away_score)).sum()
    tie_last=(last.home_score==last.away_score).sum(); tie_max=(mx.home_score==mx.away_score).sum()
    tot=(mx.home_score+mx.away_score)
    out.append(dict(season=y,games=len(mx),last_ne_max=int(diff_last_vs_max),ties_last=int(tie_last),ties_max=int(tie_max),min_total=int(tot.min()),games_total_lt_150=int((tot<150).sum()),median_total=int(tot.median()),null_periods=int((g.period_number.max()<4).sum())))
print(pd.DataFrame(out).to_string(index=False))
