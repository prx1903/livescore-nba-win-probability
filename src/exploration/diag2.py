import pandas as pd, numpy as np
pd.set_option('display.width',250)
for y in (2013,2022):
    d=pd.read_parquet(f'data/raw/play_by_play_{y}.parquet').sort_values(['game_id','game_play_number'])
    d['dh']=d.groupby('game_id').home_score.diff(); d['da']=d.groupby('game_id').away_score.diff()
    bad=d[(d.dh<0)|(d.da<0)]
    print('=====',y,'decrease rows',len(bad),'games',bad.game_id.nunique())
    print(bad.type_text.value_counts().head(8).to_dict())
    print('magnitudes', bad.dh.where(bad.dh<0, bad.da).describe().round(1).to_dict())
    gid=bad.game_id.iloc[0]; g=d[d.game_id==gid].reset_index(drop=True)
    i=g.index[(g.dh<0)|(g.da<0)][0]
    print(g.loc[max(0,i-4):i+4,['game_play_number','sequence_number','period_number','clock_display_value','type_text','home_score','away_score']].to_string())
    # scores monotone if we sort by seconds remaining desc? check fraction of decreasing rows that vanish when sorted by (period, -start secs, sequence)
    s=d.sort_values(['game_id','period_number','start_game_seconds_remaining','sequence_number'],ascending=[True,True,False,True])
    s['dh']=s.groupby('game_id').home_score.diff(); s['da']=s.groupby('game_id').away_score.diff()
    print('decrease games after time sort', ((s.dh<0)|(s.da<0)).groupby(s.game_id).any().sum())
    s2=d.sort_values(['game_id','sequence_number']); s2['dh']=s2.groupby('game_id').home_score.diff(); s2['da']=s2.groupby('game_id').away_score.diff()
    print('decrease games after sequence sort', ((s2.dh<0)|(s2.da<0)).groupby(s2.game_id).any().sum())
