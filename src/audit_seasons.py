"""Sezon sezon denetim tablosu: maç sayısı, uzatma oranı, ev sahibi kazanma, spread kapsamı ve spread isabeti,
skor gerilemesi, skor toplamı uyuşmazlığı, sütun farkları. Kullanım: python src/audit_seasons.py data/raw
(data/README.md'deki 'spread 2013'ten önce sabit yer tutucu' bulgusu bu tablodan çıkarıldı; çıktısı kaydedilmedi.)"""
import pandas as pd, numpy as np, pyarrow.parquet as pq, glob, os, sys
rows=[]; cols_ref=None; colsets={}
for f in sorted(glob.glob(os.path.join(sys.argv[1] if len(sys.argv) > 1 else 'data/raw', 'play_by_play_*.parquet'))):
    y=int(f[-12:-8]); sch=pq.read_schema(f).names; colsets[y]=set(sch)
    want=[c for c in ['game_id','game_play_number','sequence_number','season_type','period_number','home_score','away_score','home_team_spread','game_spread_available','scoring_play','score_value','start_game_seconds_remaining','end_game_seconds_remaining','type_text','score_source','game_date'] if c in sch]
    d=pd.read_parquet(f,columns=want)
    sortc='game_play_number' if 'game_play_number' in d else 'sequence_number'
    d=d.sort_values(['game_id',sortc])
    g=d.groupby('game_id'); last=g.tail(1).set_index('game_id'); first=g.head(1).set_index('game_id')
    r=pd.DataFrame({'hs':last.home_score,'as_':last.away_score,'per':g.period_number.max(),'n':g.size(),'st':first.season_type})
    if 'home_team_spread' in d: r['spr']=first.home_team_spread
    else: r['spr']=np.nan
    r['m']=r.hs-r.as_
    reg=r[r.st==2]
    dec=((d.groupby('game_id').home_score.diff()<0)|(d.groupby('game_id').away_score.diff()<0)).groupby(d.game_id).any().sum()
    s=d[d.scoring_play.astype(bool)].groupby('game_id').score_value.sum() if 'scoring_play' in d else pd.Series(dtype=float)
    mis=((s-(r.hs+r.as_).reindex(s.index))!=0).sum() if len(s) else -1
    has=r.spr.notna()
    pick=((r.spr>0)==(r.m>0))[has&(r.spr!=0)].mean() if has.any() else np.nan
    rows.append(dict(season=y,games=len(r),reg=len(reg),ot_reg=round((reg.per>4).mean(),3),home_win=round((r.m>0).mean(),3),ties=int((r.m==0).sum()),
      spr_cov=round(has.mean(),3),spr_pick_acc=round(pick,3) if pick==pick else np.nan,rows_med=int(r.n.median()),score_decr=int(dec),score_sum_mismatch=int(mis),
      has_score_source='score_source' in d, score_rebuilt=(round((first.get('score_source')=='rebuilt').mean(),3) if 'score_source' in d else np.nan),
      cols=len(sch)))
out=pd.DataFrame(rows); pd.set_option('display.width',250); print(out.to_string(index=False))
base=colsets[2024]
for y,c in colsets.items():
    if c!=base: print(y,'missing vs 2024:',sorted(base-c),' extra:',sorted(c-base))
