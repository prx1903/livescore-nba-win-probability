# Data notes

## Source and license
[sportsdataverse/hoopR-nba-data](https://github.com/sportsdataverse/hoopR-nba-data),
`nba/pbp/parquet/play_by_play_<year>.parquet`, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (the repository's `LICENSE.md`). The upstream repository
states that its play-by-play comes from ESPN.

The file year is the year in which the season ends: 2024 = 2023-24. This project uses file years 2013-2026.
`raw/` holds 2002-2026 (25 files); 2002-2012 were not used in the models, only in the audit (`src/audit_seasons.py`).
`raw/MANIFEST.csv` lists the size and SHA-256 of the downloaded files. Upstream files can change; files checked later
had different checksums (for example, ATL-DET of 2017-12-14 is 91-105 in the newer upstream file and 262-105 in the
downloaded copy). The project uses the downloaded copy pinned by the manifest.

Changes made by this project: the cleaning rules below. Not in git (size): `raw/*.parquet` and
`processed/pbp_clean/`; `src/download_raw.py` and `src/build_dataset.py` rebuild them.

## Folders
- `raw/` - raw parquet files (62-67 columns depending on the season) and `MANIFEST.csv`.
- `processed/games.csv` - one row per game.
- `processed/pbp_clean/pbp_clean_<year>.parquet` - cleaned event rows.
- `processed/cleaning_report.txt` - rows removed and changed, season by season.

## Cleaning rules (`src/build_dataset.py`)
1. Only games in which both teams are NBA franchises (team id 1-30); 22 All-Star and similar games removed.
2. Score: running maximum within the game (`cummax`). The raw score has temporary drops of 1-2 points; the raw
   columns stay as `*_raw`.
3. Time: `game_seconds_elapsed`; regulation 0-2880 s, each overtime +300 s. The remaining time is recomputed from the
   quarter clock (`start_quarter_seconds_remaining`), because the raw `start_game_seconds_remaining` of the 2013-2019
   files was computed with ten-minute quarters (360/240/120 s too small in quarters 1-3). The raw value stays in
   `start_game_seconds_remaining_raw`. In overtime the remaining time starts from that period's 300 s.
4. `is_valid`: last row has 0 s left, last row is `End Game` or `End Period`, at least 4 periods, no tie, total
   score >= 120, `final_conflict` False (the clean final score equals the raw score of the last row), and no team
   above 200 points. The 7 invalid games stay in `games.csv`.
5. `spread_home`: empty when the raw `game_spread_available` is False.

## `games.csv` columns
| Column | Meaning |
|---|---|
| game_id | event id of the source |
| file_year, season, season_label | file year (= season end year), season, e.g. `2012-13` |
| season_type | 2 = regular season (16,875 games), 3 = playoff (1,174), 5 = 37 games (play-in, inferred from the date range) |
| game_date | source `game_date` (time zone not verified) |
| home_team_id, away_team_id, home_abbrev, away_abbrev | teams |
| n_rows, n_periods | number of events; highest period number (4 = no overtime, 5 = one overtime) |
| home_final, away_final | clean score of the last row |
| home_end_reg, away_end_reg | score of the last row of period 4 |
| last_type, last_secs_remaining | event type and remaining time of the last row |
| spread_home | pre-game line; > 0 means the home team is favoured. Opening or closing not documented. Empty in 6 games |
| total_final, final_margin | total score; home minus away |
| home_win_final | home team won (overtime included), 0/1 |
| has_ot, reg_tied, home_win_reg | overtime played; tied after regulation; home team ahead after regulation (empty if tied) |
| is_valid, reg_consistent | validity rule; `has_ot == reg_tied`. False in 3 games (2018 x 2, 2021 x 1): their end-of-regulation score is unreliable |
| final_conflict | clean final score differs from the raw score of the last row; if True, `is_valid` is False |

## `pbp_clean` columns
`game_id, season, season_type, game_play_number` (event order), `period_number, clock_display_value,
start_game_seconds_remaining` (corrected), `start_game_seconds_remaining_raw` (raw), `game_seconds_elapsed,
is_overtime_period, type_text, scoring_play, shooting_play, team_id, athlete_id_1, sequence_number,
home_score, away_score` (clean), `home_score_raw, away_score_raw` (raw).

## Known data issues
- In the 2013-2019 files the `score_value` column is unreliable; the score is taken from `home_score` / `away_score`.
- The 2002 and 2003 files look partial (528 and 1,052 games; about 1,300 in other seasons). 2012 (1,075) and
  2020-2021 (1,139, 1,172) are shortened seasons.
- 2002-2012: the spread is a constant placeholder (`game_spread_available` False); it is meaningful from 2013.
- Raw score drops: for example, 1,223 games of the 2013 file have at least one step back.
- 7 invalid games: incomplete records (time left > 0 or the last row is not an end of game); one game has 3 periods.
- No player or ball tracking; who is on the court can only be rebuilt from `Substitution` events.
