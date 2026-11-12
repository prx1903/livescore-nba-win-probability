# Game simulator (synthetic games)

Generates NBA games that never happened, from the strengths of two teams, as play-by-play events in the format of
`data/processed/pbp_clean`. The live replay, the feed checks and the models read these events unchanged.

Synthetic games are for demonstrations and system tests. They are **not** used to measure model accuracy: they are
generated from the same pre-game expectations that the models use, so a model would be graded on its own inputs.
Event texts are generic ("Made 3-pt shot", "Defensive rebound") and contain no text from a data source.

## Files

| File | What it does | Output |
|---|---|---|
| `estimate_rates.py` | League rates per season and period from the cleaned play-by-play; end-game table from the training seasons 2014-2022 | `results/simulation/rates.json` |
| `game_simulator.py` | The simulator (imported by the other scripts) | – |
| `calibrate.py` | Fits the free parameters on training games (2014-2022) | `results/simulation/calibration.json`, `calibration_log.json` |
| `validate.py` | Compares simulated and real games of the test seasons (2023-2026) and runs the feed checks on every simulated event | `results/simulation/validation.json`, `validation_report.txt` |
| `estimate_shot_locations.py` | Counts of field-goal attempts on a 1 ft grid from the raw play-by-play of file year 2022 (training); the cleaned play-by-play has no coordinates | `results/simulation/shot_locations.json` |
| `simulate_game.py` | Generates one game and writes its events | `results/simulation/games/sim_<id>_events.csv`, `_info.json` |

Rebuild order (from the repository root): `estimate_rates.py` → `calibrate.py` → `validate.py`.

```
python -I src/simulation/estimate_rates.py data/processed results/simulation/rates.json
python -I src/simulation/calibrate.py .
python -I src/simulation/validate.py .
python -I src/simulation/estimate_shot_locations.py data/raw data/processed results/simulation/shot_locations.json 2022
```
`estimate_shot_locations.py` needs the raw file `data/raw/play_by_play_2022.parquet` (not in the repository);
`shot_locations.json` holds counts per 1 ft cell, not single records.

## Usage

```
python -I src/simulation/simulate_game.py --home BOS --away LAL --season 2025 --seed 7
python -I src/simulation/simulate_game.py --seed 7            # random season and teams
python -I src/simulation/simulate_game.py --teams 2025        # team codes of a season
# events: the columns of data/processed/pbp_clean plus shot_x, shot_y (empty except for field-goal attempts)
cd src && python live_replay.py --model ../models/model_coefficients.json --sim --home BOS --away LAL --season 2025 --sim-seed 7 --speed 60
```

`--season` is the file year (2025 = season 2024-25). The same seed gives the same game. Synthetic game ids start at
9,000,000,000, so they cannot collide with real ids.

## How a game is generated

1. **Score flow.** Expected regulation points of each team come from the team ratings of `src/v2/ratings.py`
   after the team's last game of the chosen season: expected margin μm and total μt (Section 5.6 of the report).
   A small game-level shock is added to the total.
2. **Possessions.** Each possession is a sequence of actions (turnover, field-goal attempt, free-throw trip) drawn
   from league rates of the season and period. The make probabilities of each team are scaled by one efficiency
   factor, solved so that its expected points equal its target. Overtime periods are played until the game is
   decided.
3. **Lead shrink and in-game form.** Make probabilities of the team in possession are multiplied by
   exp(−γ·lead + form), where form is a mean-reverting difference between the two teams (standard deviation
   `form_sd`, time constant 6 minutes, home +form/2, away −form/2).
4. **End game.** In the last 60 s of the fourth quarter and of overtime, actions follow the end-game table
   (time left × lead of the team in possession): action shares including deliberate fouls, time between
   possessions, the share of the remaining time used when a possession starts with 24 s or less, and the share of
   such possessions that run out the clock without an action.
5. **Shot locations.** Every field-goal attempt gets a location (`shot_x`, `shot_y`: x 0-50 ft from sideline to
   sideline, y in ft from the rim centre towards half court, as `coordinate_x_raw` / `coordinate_y_raw` of the raw
   data), drawn from the counts of the training season for made 2s, made 3s and misses. A separate random stream
   is used, so the game itself is the same with or without locations (checked on 300 games).

## Calibration

Targets come from the score-distribution model (`results/v2/sim_params.json`, training seasons): lead-shrink
coefficient β, standard deviation of the final regulation margin and total with 48 minutes left, and a slope of 1
of the final margin on μm. A persistent game-level margin shock was tried first; it moves β towards zero, and on a
grid of γ and shock no point reached both the target β and the target spread of margins. The extra spread
therefore comes from in-game form. See the docstring of `calibrate.py` for the steps.

Selected values (`results/simulation/calibration.json`): γ = 0.0036, form_sd = 0.208,
margin_scale = 1.377, points_scale = 0.956 (per season
0.935-0.964), margin shock 0, total shock 0.

| Training sample (1,500 games, 2014-2022) | Target | Simulated |
|---|---|---|
| Lead shrink β | -0.505 | -0.473 |
| SD of final margin around μm | 13.32 | 13.32 |
| SD of final total around μt | 18.09 | 18.22 |
| Slope of final margin on μm | 1 | 1.001 |
| Overtime rate (not a target) | – | 0.041 |

The simulated total cannot be made less variable with the parameters used (the total shock is already zero).

## Validation on the test seasons 2023-2026

Every real test game with a pre-game line (5,273 games) is simulated once with its own expectations
(`results/simulation/validation_report.txt`). Interval: 95 % for the difference of means.

| Metric | Real | Simulated | Difference |
|---|---|---|---|
| Final margin − μm, mean | 0.07 | 0.46 | +0.39 [-0.13, +0.91] |
| Final margin − μm, SD | 13.49 | 13.78 | +0.29 |
| Final total − μt, mean | 0.58 | -0.72 | -1.30 [-2.01, -0.60] |
| Final total − μt, SD | 17.81 | 19.12 | +1.31 |
| Home-win rate | 0.557 | 0.568 | +0.011 [-0.008, +0.030] |
| Overtime rate | 0.052 | 0.040 | -0.011 [-0.019, -0.003] |
| Within 3 points at end of regulation | 0.179 | 0.158 | -0.021 [-0.036, -0.007] |
| Within 3 points with 24 s left | 0.221 | 0.193 | -0.028 [-0.043, -0.012] |
| Lead shrink β | -0.429 | -0.447 | -0.018 |
| Slope of final margin on μm | 1.062 | 1.120 | +0.058 |
| Share of points in Q4 | 0.242 | 0.242 | +0.001 [-0.000, +0.002] |
| Lead changes per game | 6.61 | 6.63 | +0.03 [-0.19, +0.24] |
| Largest lead | 20.41 | 20.68 | +0.27 [-0.05, +0.60] |
| Longest scoring run (points) | 11.55 | 11.38 | -0.17 [-0.27, -0.07] |
| Free-throw attempts per game | 44.20 | 44.13 | -0.07 [-0.45, +0.32] |
| SD of margin at half-time | 11.82 | 12.18 | +0.36 |

Home-win rate by μm (real / simulated): μm −∞..-6: 0.200 / 0.256 · μm -6..-2: 0.398 / 0.377 · μm -2..2: 0.499 / 0.493 · μm 2..6: 0.621 / 0.645 · μm 6..∞: 0.786 / 0.791.

Feed checks on all 2,034,454 simulated events: 0 rejected, 0 warnings.

Known differences: fewer close finishes and ties than in real games (overtime about 4 % against 5 %), totals about
1 point low and more variable, the slope of the final margin on μm is higher than real (1.12 against 1.06) and
strong away favourites lose more often (home underdog wins 26 % against 20 % for μm ≤ −6). The test seasons differ
from the training seasons on their own: real β is −0.43 on 2023-2026 against the training target −0.51.

## Assumptions (not estimated from data)

- Time constant of in-game form: 6 minutes of game time.
- Possession length before the end game: gamma distribution (shape 3) with the mean pace of the season and
  period, limited to 3-24 s; after an offensive rebound, mean 6 s (shape 2), limited to 1-14 s.
- A shot at the buzzer at the end of a period has half the usual make probability.
- Team strengths are those after the team's last game of the season, also for a game shown earlier in that season.
