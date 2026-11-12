# Demo page

`docs/index.html` is one self-contained page (the interface is in Turkish). It replays the NBA night of
18 December 2025: 12 real games and one generated game, all on one day clock.

## Time
- Day clock and game clock run 1:1: at 1x the game clock loses one second per second; a game lasts 48 minutes
  (longer with overtime). Breaks between quarters and stoppages are not modelled.
- Speeds 1x, 5x, 10x, 20x (default), 50x, 60x. The speed of each was measured (8-10 s each); the largest deviation
  was 0.2%. The page draws 60 frames per second.
- Top bar: play/pause (also the space bar), a slider over the day, speed choice. Arrow keys change the game.
- The day runs from 02:00 to 04:23 (143 minutes at 1x, 7 minutes at 20x). The page opens paused at 02:51 with
  7 games live (one generated), 2 finished and 4 not started.
- The game clock also runs between events: period and time left come from the day clock, the score from the last
  event. Events arrive on average 6, at most 28 game seconds apart.

## Views
- **Games:** the list of games, the selected game (win probability, its curve, score), the day panel, the last
  events and the data status.
- **Half court:** the ball moves frame by frame with the game clock (entry from half court, pass points, arcing shot,
  rebound, free throw, turnover). Shot and rebound locations, times and teams come from the data; pass points and
  rebound directions are only visual. The last 10 shots are marked (team colour, filled = made). At release a ring,
  a dashed arc to the rim and a label ("2'lik / 3'lük", free throw) appear; at the rim a ring shows made or missed.
- **Model:** Brier score, log loss, errors by season type (including playoff), calibration curve and error by time
  remaining (test seasons 2023-2026, numbers from `results/baseline_report.txt`). For each finished real game, its own
  error. The generated game is excluded from every accuracy number.

## What is real and what is not
- Real: the 12 games, teams, scores, period scores and event texts (from `data/processed`; final scores match
  `games.csv`). Win probabilities are recomputed for every event with `models/model_coefficients.json`. Shot locations
  come from `data/raw/play_by_play_2026.parquet` (`coordinate_x_raw`, `coordinate_y_raw`), matched to the clean data
  by `game_play_number` (6,092 events, all 2,239 shots with a location).
- Error on this day's 12 real games (Brier): model 0.192, pre-game probability alone 0.200. Twelve games are a small
  sample; on the 5,273 test games the values are 0.152 and 0.204.
- Not real: the start times (assigned for the presentation, see above). The data-feed warning is shown with an
  example state ("how the warning looks"); it is not yet connected to `src/feed_checks.py`. Hatched boxes are places
  for content that is not built yet.
- The generated game (MIN @ CHI, 02:30) is not a real game: two of the six teams that did not play that night were
  drawn with a fixed seed and `src/simulation/game_simulator.py` generated the game from 2025-26 team strengths
  (seed 1). It is labelled in the list and on the game screen. Its event texts are generic and its shot locations are
  drawn from the training season 2022 shot distribution (`results/simulation/shot_locations.json`).

## Data source
Play-by-play: [sportsdataverse/hoopR-nba-data](https://github.com/sportsdataverse/hoopR-nba-data), CC BY 4.0
(see the main README). The page states the source in the model view.

## Rebuilding
```
python -I app/demo/build_day_data.py                                   # -> app/demo/day_data.json
python -I app/demo/embed_day_data.py docs/index.html app/demo/day_data.json
```
`build_day_data.py` needs the cleaned 2026 play-by-play and the raw 2026 file (not in git). Other locations can be
given with the environment variables `LIVESCORE_REPO` and `LIVESCORE_RAW`.
