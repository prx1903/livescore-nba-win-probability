"""
NBA canlı kazanma olasılığı projesi: hoopR-nba-data play-by-play temizleme.

Kullanım:
    python3 -I build_dataset.py <ham_parquet_klasoru> <cikti_klasoru> [ilk_dosya_yili] [son_dosya_yili]

Girdi : play_by_play_<yıl>.parquet dosyaları (sportsdataverse/hoopR-nba-data, ESPN kaynaklı).
         Dosya yılı sezonun BİTİŞ yılıdır: 2024 = 2023-24 sezonu.
Çıktı : games.csv, pbp_clean/pbp_clean_<yıl>.parquet, cleaning_report.txt

Kurallar (hepsi cleaning_report.txt'e sayılarıyla yazılır):
  1. Yalnızca iki takımı da NBA franchise'ı olan maçlar (takım id 1-30). All-Star ve benzeri maçlar çıkar.
  2. Skor sütunları: maç içi çalışan maksimum (cummax). Ham skorda geçici 1-2 puanlık gerilemeler var.
     Ham sütunlar da korunur (home_score_raw, away_score_raw).
  3. Bitmemiş / bozuk maçlar işaretlenir (is_valid=False) ama games.csv'de kalır:
       - son satırda kalan süre 0 değil (ya da son satır End Game/End Period değil), 4'ten az periyot,
         final skorda beraberlik, toplam skor < 120. (2013-17'de maçlar çoğunlukla 'End Period' ile biter; geçerli sayılır.)
  4. Zaman: game_seconds_elapsed. Normal süre 0-2880 sn; her uzatma +300 sn.
     Ham start_game_seconds_remaining 2013-2019 dosyalarında 10 dakikalık çeyrekle hesaplanmış
     (1., 2., 3. çeyrekte 360/240/120 sn eksik). Bu yüzden kalan süre çeyrek saatinden
     (start_quarter_seconds_remaining) yeniden hesaplanır. Ham değer start_game_seconds_remaining_raw olarak kalır.
  5. Etiketler:
       home_win_final : maç sonu (uzatma dahil) ev sahibi kazandı mı
       reg_tied       : normal sürenin sonunda beraberlik mi (uzatmaya gitti)
       home_win_reg   : normal süre sonu ev sahibi önde mi (beraberlikte boş)
  7. final_conflict: temiz (cummax) final skoru, son satırdaki ham skordan farklıysa True ve maç geçersiz sayılır.
     Bu, skorda geçici yukarı sıçrama olan maçları yakalar (örnek: ATL-DET 2017-12-14, 13 Ekim'deki ham dosyada 262-105).
     Ayrıca bir takımın final skoru 200'ü geçerse maç geçersiz sayılır (gerçekte olmayan bir skor).
  6. Spread: home_team_spread > 0 ise ev sahibi favori. game_spread_available=False ise spread boş yazılır.
"""
import sys, glob, os
import numpy as np
import pandas as pd

raw_dir, out_dir = sys.argv[1], sys.argv[2]
y0 = int(sys.argv[3]) if len(sys.argv) > 3 else 2013
y1 = int(sys.argv[4]) if len(sys.argv) > 4 else 2026
os.makedirs(out_dir, exist_ok=True)

COLS = ['game_id', 'game_play_number', 'sequence_number', 'season', 'season_type', 'game_date',
        'period_number', 'clock_display_value', 'start_game_seconds_remaining', 'start_quarter_seconds_remaining',
        'end_game_seconds_remaining', 'type_text', 'scoring_play', 'shooting_play',
        'team_id', 'athlete_id_1', 'home_score', 'away_score',
        'home_team_id', 'away_team_id', 'home_team_abbrev', 'away_team_abbrev',
        'home_team_spread', 'game_spread_available']

report, games_all = [], []
n_pbp_rows = 0
def log(s):
    print(s); report.append(s)

for y in range(y0, y1 + 1):
    f = os.path.join(raw_dir, f'play_by_play_{y}.parquet')
    d = pd.read_parquet(f, columns=COLS)
    d = d.sort_values(['game_id', 'game_play_number']).reset_index(drop=True)
    n_games_raw = d.game_id.nunique()

    # 1. NBA franchise maçları
    nba = d.home_team_id.between(1, 30) & d.away_team_id.between(1, 30)
    n_excl = d.loc[~nba, 'game_id'].nunique()
    d = d[nba].copy()

    # 2. Skor temizleme
    d['home_score_raw'] = d.home_score
    d['away_score_raw'] = d.away_score
    g = d.groupby('game_id')
    d['home_score'] = g.home_score.cummax()
    d['away_score'] = g.away_score.cummax()
    n_changed_rows = int(((d.home_score != d.home_score_raw) | (d.away_score != d.away_score_raw)).sum())
    n_changed_games = int(d.loc[(d.home_score != d.home_score_raw) | (d.away_score != d.away_score_raw), 'game_id'].nunique())

    # 4. Zaman (kalan süre çeyrek saatinden yeniden hesaplanır, bkz. kural 4)
    p = d.period_number.astype(int)
    q_rem = d.start_quarter_seconds_remaining.astype(float)
    rem = pd.Series(np.where(p <= 4, (4 - p) * 720 + q_rem, q_rem), index=d.index)
    d['start_game_seconds_remaining_raw'] = d.start_game_seconds_remaining
    time_diff = (rem - d.start_game_seconds_remaining.astype(float)).abs() > 0.5
    n_time_fixed, n_time_fixed_games = int(time_diff.sum()), int(d.loc[time_diff, 'game_id'].nunique())
    d['start_game_seconds_remaining'] = rem
    d['game_seconds_elapsed'] = np.where(p <= 4, 2880 - rem, 2880 + 300 * (p - 5) + (300 - rem))
    d['is_overtime_period'] = p > 4

    # Maç tablosu
    g = d.groupby('game_id')
    first, last = g.head(1).set_index('game_id'), g.tail(1).set_index('game_id')
    reg = d[d.period_number == 4].groupby('game_id').tail(1).set_index('game_id')
    gm = pd.DataFrame({
        'file_year': y, 'season': first.season, 'season_label': first.season.map(lambda s: f'{s-1}-{str(s)[2:]}'),
        'season_type': first.season_type, 'game_date': first.game_date,
        'home_team_id': first.home_team_id, 'away_team_id': first.away_team_id,
        'home_abbrev': first.home_team_abbrev, 'away_abbrev': first.away_team_abbrev,
        'n_rows': g.size(), 'n_periods': g.period_number.max(),
        'home_final': last.home_score, 'away_final': last.away_score,
        'home_end_reg': reg.home_score, 'away_end_reg': reg.away_score,
        'last_type': last.type_text, 'last_secs_remaining': last.start_game_seconds_remaining,
        'spread_home': first.home_team_spread.where(first.game_spread_available.astype(bool)),
    })
    gm['total_final'] = gm.home_final + gm.away_final
    gm['home_win_final'] = (gm.home_final > gm.away_final).astype(int)
    gm['has_ot'] = gm.n_periods > 4
    gm['reg_tied'] = gm.home_end_reg == gm.away_end_reg
    gm['home_win_reg'] = np.where(gm.reg_tied, np.nan, (gm.home_end_reg > gm.away_end_reg).astype(float))
    gm['final_margin'] = gm.home_final - gm.away_final
    gm['is_valid'] = (gm.last_secs_remaining == 0) & gm.last_type.isin(['End Game', 'End Period']) & (gm.n_periods >= 4) & (gm.final_margin != 0) & (gm.total_final >= 120)
    gm['reg_consistent'] = gm.has_ot == gm.reg_tied  # uzatma varsa normal süre sonu berabere olmalı
    gm['final_conflict'] = (last.home_score != last.home_score_raw) | (last.away_score != last.away_score_raw)
    gm['is_valid'] = gm.is_valid & ~gm.final_conflict
    gm['is_valid'] = gm.is_valid & (gm[['home_final', 'away_final']].max(axis=1) <= 200)  # NBA'de takım skoru rekoru 200'ün altında
    n_invalid = int((~gm.is_valid).sum())
    log(f'{y}: ham_mac={n_games_raw} nba_disi_cikarilan={n_excl} kalan={len(gm)} gecersiz={n_invalid} '
        f'skor_degisen_satir={n_changed_rows} skor_degisen_mac={n_changed_games} '
        f'reg_tutarsiz={int((~gm.reg_consistent).sum())} '
        f'zaman_duzeltilen_satir={n_time_fixed} zaman_duzeltilen_mac={n_time_fixed_games} '
        f'final_celiskili_mac={int(gm.final_conflict.sum())}')
    games_all.append(gm.reset_index())
    keep = ['game_id', 'season', 'season_type', 'game_play_number', 'period_number', 'clock_display_value',
            'start_game_seconds_remaining', 'start_game_seconds_remaining_raw', 'game_seconds_elapsed', 'is_overtime_period', 'type_text',
            'scoring_play', 'shooting_play', 'team_id', 'athlete_id_1', 'sequence_number',
            'home_score', 'away_score', 'home_score_raw', 'away_score_raw']
    os.makedirs(os.path.join(out_dir, 'pbp_clean'), exist_ok=True)
    d[keep].to_parquet(os.path.join(out_dir, 'pbp_clean', f'pbp_clean_{y}.parquet'), index=False)
    n_pbp_rows += len(d)

games = pd.concat(games_all, ignore_index=True)
games.to_csv(os.path.join(out_dir, 'games.csv'), index=False)

log('')
log(f'TOPLAM maç={len(games)} geçerli={int(games.is_valid.sum())} geçersiz={int((~games.is_valid).sum())}')
log(f'Geçerli maçlarda uzatma oranı={games[games.is_valid].has_ot.mean():.3f}  ev sahibi kazanma={games[games.is_valid].home_win_final.mean():.3f}')
log(f'Spread dolu oran (geçerli)={games[games.is_valid].spread_home.notna().mean():.3f}')
log(f'Satır sayısı pbp_clean (14 dosya)={n_pbp_rows}')
open(os.path.join(out_dir, 'cleaning_report.txt'), 'w').write('\n'.join(report) + '\n')
