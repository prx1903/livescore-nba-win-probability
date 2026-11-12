# Model search

Goal: find a model that beats the logistic model (baseline). Everything in this folder is rebuilt from one
configuration file, `src/experiments/config.json`.

## Running

```
python -I src/experiments/snapshots.py data/processed results/v2/pregame.parquet results/experiments/snapshots.parquet
python -I src/experiments/run_validation.py src/experiments/config.json      # ~8 minutes
python -I src/experiments/run_test.py       src/experiments/config.json      # ~4 seconds
python tests/test_models.py
```

`snapshots.parquet` is a cache and is not in git. `run_validation.py` never loads the test seasons
(`S = S[S.year < test_min]`); the test seasons are used once, only in `run_test.py`.

## Design

- Snapshots: every 60 s, k = 2880 excluded; when several events share a second, the last one by
  `game_play_number`. Same rule as `train_baseline.py`; 869,993 rows, 18,026 games.
- Forward validation: validation seasons 2020, 2021, 2022 (file years), each trained only on earlier seasons
  (2013-2019, 2013-2020, 2013-2021). Selection by the mean Brier score over the three seasons.
- Calibration candidates train the base model without the last training season and learn the correction on that
  season; the validation season is never seen. Cost: less training data.
- Final evaluation: training 2013-2022 (2019-2022 for the rolling-window candidate), test 2023-2026, 254,328
  snapshots, 5,273 games. Paired bootstrap over games, 2,000 repetitions.

Candidates: logistic, HistGradientBoosting and LightGBM (raw inputs, with and without monotone constraints,
engineered features), spline and interaction logistic, boosting with team ratings, Platt and isotonic calibration,
ensembles, rolling training windows (last 4 and 6 seasons).

## Acceptance rule (fixed before the test)

A candidate replaces the baseline only if all three hold:
1. the 95% interval of the Brier difference excludes zero and the candidate is better,
2. calibration is not worse than the baseline,
3. the prediction time is acceptable for the replay.

## Result

Selected on validation: the same logistic model trained on the last 4 seasons. Test Brier 0.15170 against 0.15190,
difference −0.00019, 95% interval [−0.00040, +0.00002]. The interval contains zero, so the baseline stays.
Expected calibration error 0.0088 against 0.0144 (the rule only required that calibration does not get worse).
Boosting models, ensembles and boosting with team ratings were worse than the baseline on validation.
The candidate is kept as `models/model_g_logit_base_win4_v1.json`; the delivered model is
`models/model_coefficients.json`.

## Files

```
model_search/
  validation_table.csv     every candidate x fold: Brier, log loss, ECE, by time remaining, training window, time
  validation_report.txt    run log and ranking
  selection.json           selected candidate, family winners, mean Brier scores
  final_test.txt / .json   test result, bootstrap interval, calibration, decision
  config.json              configuration used (copy)
  versions.json            Python and library versions, random seed
repro/                     rebuild of the baseline (baseline_report.txt, model_coefficients.json,
                           season_type_report.txt) for comparison with the files in the repository
```
