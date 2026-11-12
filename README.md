# NBA live win probability

A research project that estimates, at every moment of an NBA game, the probability that the home team wins.
It also gives the probability of overtime, the expected final score and the outcome of each period, and it can
replay games event by event as if they were live.

**Demo:** `docs/index.html` (open it in a browser, or see the GitHub Pages link of this repository).
It replays one NBA night (12 real games of 18 December 2025 and one generated game) with the live probability,
a half-court view of the last shots, and a model view with accuracy charts. The interface, most code comments and
the text reports in `results/` are in Turkish.

## Results (test seasons 2022-23 to 2025-26, 5,273 games)

| Model | Brier score | Log loss |
|---|---|---|
| Pre-game line (spread) only | 0.2045 | 0.5943 |
| **Logistic model (delivered)**: score margin, time left, pre-game line | **0.1519** | **0.4557** |
| Score-distribution model (`src/v2`) | 0.1521 | 0.4561 |

- Difference logistic − spread only: −0.0530, 95% game-clustered bootstrap interval [−0.0564, −0.0496].
- The score-distribution model is as accurate as the logistic model for the win probability (difference not
  distinguishable from zero) and also gives overtime, final-score and period-outcome probabilities.
- A model search (gradient boosting, splines, calibration wrappers, ensembles, rolling windows) found no candidate
  that beats the logistic model under a rule written before the test (`results/experiments/README.md`).
- The feature set was chosen on the validation season 2021-22 (training 2012-13 to 2020-21); the final model was
  trained on 2012-13 to 2021-22.

Details: `results/baseline_report.txt`, `results/season_type_report.txt`, `results/v2/model_report.txt`.

## Repository structure

```
src/
  download_raw.py           download the raw play-by-play files and check them against data/raw/MANIFEST.csv
  build_dataset.py          clean the raw data -> data/processed (games.csv, pbp_clean/, cleaning_report.txt)
  train_baseline.py         logistic model -> models/model_coefficients.json, results/baseline_report.txt
  winprob.py                prediction function shared by training, replay and demo
  live_replay.py            live-feed replay: producer thread -> queue -> model -> output
  feed_checks.py            checks for missing, broken, repeated and late events
  eval_by_season_type.py    accuracy for regular season, playoff and play-in
  audit_seasons.py          season-by-season audit of the raw files
  v2/                       score-distribution model (team ratings, snapshots, model, Python reference)
  experiments/              model search (forward validation, one-time test)
  simulation/               game simulator: synthetic games from team strengths (see its README)
  exploration/              one-off scripts used while exploring the data
app/demo/                   scripts and data that build the demo page (see NOTES.md)
docs/index.html             the demo page (served by GitHub Pages)
data/                       data notes, MANIFEST.csv, games.csv, cleaning report (large files are not in git)
models/                     model files
results/                    reports and outputs of every step
tests/                      tests (run each file with python)
```

## Setup

Tested with Python 3.13 (all steps) and 3.10 (cleaning step); other versions were not tried.

```
pip install -r requirements.txt
```

## Rebuilding everything

Run from the repository root (on Windows use `python`).

```
# 1. Raw data (about 340 MB for 2013-2026; skipped if already in data/raw)
python src/download_raw.py --out data/raw --from 2013 --to 2026

# 2. Cleaning -> data/processed
python -I src/build_dataset.py data/raw data/processed 2013 2026

# 3. Logistic model -> models/ and results/
python src/train_baseline.py data/processed models results

# 4. Replay of one game in the terminal (list example ids with --list)
python src/live_replay.py --data data/processed --model models/model_coefficients.json --game 401585662 --speed 60
# replay with 30% of events dropped and a 40 s pause before event 150
python src/live_replay.py --data data/processed --model models/model_coefficients.json --game 401585662 --speed 0 --drop-rate 0.3 --delay-at 150 --delay-sec 40

# 5. Accuracy by season type
python src/eval_by_season_type.py data/processed models/model_coefficients.json results

# 6. Score-distribution model -> results/v2
python -I src/v2/prep.py data/processed results/v2
python -I src/v2/ratings.py data/processed results/v2
python -I src/v2/model.py results/v2 models/model_coefficients.json

# 7. Model search (needs lightgbm; about 8 minutes)
python -I src/experiments/snapshots.py data/processed results/v2/pregame.parquet results/experiments/snapshots.parquet
python -I src/experiments/run_validation.py src/experiments/config.json
python -I src/experiments/run_test.py src/experiments/config.json

# 8. Game simulator (see src/simulation/README.md)
python -I src/simulation/estimate_rates.py data/processed results/simulation/rates.json
python -I src/simulation/calibrate.py .
python -I src/simulation/validate.py .

# 9. Demo page (see app/demo/NOTES.md)
python -I app/demo/build_day_data.py
python -I app/demo/embed_day_data.py docs/index.html app/demo/day_data.json

# Tests
python tests/test_feed_checks.py
python tests/test_models.py
python tests/test_simulator.py
```

Do not use `python -I` for `live_replay.py`: it imports the local `winprob.py`.

## Data and attribution

Play-by-play data: [sportsdataverse/hoopR-nba-data](https://github.com/sportsdataverse/hoopR-nba-data),
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The upstream repository states that its
play-by-play comes from ESPN. This project cleaned the data (score, clock and validity corrections listed in
`data/README.md`) and derived the files in `data/processed`, `results` and the demo from it.
The raw and cleaned play-by-play files are not in git because of their size; `src/download_raw.py` and
`src/build_dataset.py` rebuild them.

## Known limitations

- No real live feed: the replay streams past games event by event. Missing and late data were tested by dropping
  and delaying events in the replay.
- The score correction (running maximum within a game) was not checked against a second source.
- Whether the pre-game line is the opening or closing line is not documented upstream. The 2002-2012 files carry a
  constant placeholder line, so the analysis starts with 2012-13.
- Play-in games are identified by their date range, not by documentation.
- Seasons drift (lower home-win rate after 2020, higher totals); the models have no season effect.
- The test seasons were evaluated more than once during development, so the test results are not from a strictly
  single-use hold-out.
- The model has no player, possession, foul or injury information.
- Synthetic games from `src/simulation` are for demonstrations and system tests only; they are generated from the
  same pre-game expectations the models use and are never used to measure accuracy.

## License

No license has been chosen for the code; all rights are reserved by the author. The data has its own license
(see above).
