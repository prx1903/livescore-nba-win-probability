import pandas as pd, numpy as np
pd.set_option('display.width',250)
for y in (2005,2013,2015,2022):
    d=pd.read_parquet(f'data/raw/play_by_play_{y}.parquet')
    print('=====',y, d.shape)
    f=d.groupby('game_id')[['home_team_spread','game_spread','home_favorite','game_spread_available']].first()
    print('spread value counts top:', f.home_team_spread.round(2).value_counts().head(4).to_dict(), ' avail:', f.game_spread_available.value_counts().to_dict(), 'fav:', f.home_favorite.value_counts().to_dict())
    print('uniq spreads', f.home_team_spread.nunique())
    # ordering diagnostics
    g=d[d.game_id==d.game_id.iloc[len(d)//2]].sort_values('game_play_number')
    print('seq sorted by play number? ', g.sequence_number.is_monotonic_increasing, ' game_play_number==1..n', (g.game_play_number.values==np.arange(1,len(g)+1)).all())
    s=d.sort_values(['game_id','sequence_number'])
    dd=((s.groupby('game_id').home_score.diff()<0)|(s.groupby('game_id').away_score.diff()<0)).groupby(s.game_id).any().sum()
    print('score decreasing games when sorted by sequence_number:', dd, '/', d.game_id.nunique())
    # score_value sum vs diffs
    sc=d[d.scoring_play]
    print('scoring_play rows', len(sc), 'score_value dist', sc.score_value.value_counts().head(5).to_dict())
    one=d[d.game_id==d.game_id.iloc[len(d)//2]].sort_values('game_play_number')
    one['dh']=one.home_score.diff().fillna(0); one['da']=one.away_score.diff().fillna(0)
    print(one[['period_number','clock_display_value','type_text','home_score','away_score','scoring_play','score_value','dh','da']].iloc[30:48].to_string())
