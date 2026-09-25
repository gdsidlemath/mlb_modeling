# `MlbBuildModelData.py`

Turns the raw `games`/`abs`/`pitches` tables written by `MlbApiScraper` into
one feature row per pitch, suitable for training a next-pitch classifier
(`MlbPitchPredictionModel`). Everything it computes for a given row uses only
pitches that happened *before* that row — see [Leakage rules](#leakage-rules)
below.

## Entry points

### `build_pitcher_data(pitcher_id, date_until=None)`

One row per pitch **thrown by** `pitcher_id`. This is the one used for
next-pitch-type prediction models.

### `build_batter_data(batter_id, date_until=None)`

One row per pitch **faced by** `batter_id`. Mirror image of
`build_pitcher_data` — same feature set, but pitch-mix history is built from
the batter's perspective (a `vs_pitcher` mix instead of `vs_batter`).

Both take an optional `date_until` (e.g. `"2024-07-15"` or `20240715`): rows
are filtered to games strictly before that date. This is the primitive a live
prediction service would call with "today" to get a feature row reflecting
only what's happened so far — no future data leaks in because the underlying
join/filter happens before any of the cumulative-mix math runs.

Both return an empty DataFrame if the player has no pitches in the loaded
data (e.g. bad ID, or `date_until` before their first appearance).

## Internal pipeline

`build_pitcher_data`/`build_batter_data` call, in order:

1. **`_load_raw_tables()`** — lazily loads `pitches`, `abs`, `games` from the
   configured CSV files or SQLite db (whichever `data_as_type` was set to in
   `__init__`) into `self._pitches_df`/`_abs_df`/`_games_df`. Cached after the
   first call, so building both pitcher and batter data (or multiple
   pitchers) from the same `BuildMlbModelData` instance only hits disk once.

2. **`_pitch_sequence(player_id, role, date_until)`** — filters `abs` down to
   at-bats where `player_id` is the pitcher (or batter), inner-joins `pitches`
   onto that (so only pitches from those at-bats survive), then left-joins in
   the rest of the at-bat context (stance/hand, inning, outs, baserunners,
   score, `startTime`) and game context (date, teams, day/night, weather).
   Applies `date_until` here, then sorts chronologically
   (`game_date, g_id_int, ab_ind, p_ind`) — every downstream cumulative
   calculation depends on this sort order being correct.

3. **`_build_pitch_mix_features(df, self_col, opponent_col, opponent_suffix)`**
   — the feature-engineering core. For `build_pitcher_data`, `self_col` is
   `"pitcher_id"`, `opponent_col` is `"batter_id"`, `opponent_suffix` is
   `"vs_batter"` (and vice versa for `build_batter_data`). It:
   - one-hot encodes `type` (the pitch type actually thrown) into
     `type_<CODE>` dummy columns — these dummies are the raw ingredient every
     pitch-mix feature below is computed from.
   - adds `pitch_num_in_game` (1-indexed pitch count within the game).
   - adds four `prev_*` columns (`prev_pitch_type`, `prev_zone`,
     `prev_start_speed`, `prev_call`) — a 1-pitch lookback within the same
     game via `groupby("g_id_int").shift(1)`. `NaN` for a player's first pitch
     of a game.
   - computes five pitch-mix feature families (below) via
     `_group_cumulative_mix` and `_last_two_innings_mix`.

### Pitch-mix feature families

Each family answers "of the pitches thrown so far in \<scope\>, what fraction
was each pitch type?" — five different scopes:

| suffix | scope | grouped by |
|---|---|---|
| `_this_inning` | pitches earlier in the current inning | `g_id_int, inning` |
| `_last_2_innings` | pitches in the current + previous inning | special (see below) |
| `_game` | pitches earlier in the current game | `g_id_int` |
| `_by_count` | pitches earlier in this ball-strike count, across all games | `balls-strikes` string key |
| `_vs_batter` / `_vs_pitcher` | pitches earlier against this specific opponent, across all games | `batter_id` or `pitcher_id` |

`_this_inning`, `_game`, `_by_count`, and `_vs_batter`/`_vs_pitcher` all go
through **`_group_cumulative_mix(df, type_cols, group_cols, suffix)`**: within
each group, `cumsum() - own_row` gives the count of each pitch type strictly
before the current row, divided by `cumcount()` (pitches strictly before,
total). Division by zero (first pitch in a group) yields `NaN`, left as-is
rather than filled — the model treats "no history yet" as missing rather than
0%.

`_last_2_innings` needs different logic because "current inning + previous
inning" isn't a single groupby key — it's a sliding 2-inning window.
**`_last_two_innings_mix`** computes it by taking the game-level cumulative
mix (same as `_game`, i.e. everything before this pitch in the game) and
subtracting off everything more than 2 innings old: it builds per-inning
totals, cumulative-sums those by game, then looks up the cumulative total
*as of 2 innings ago* (via a merge on `inning - 2`) and subtracts. What's left
is exactly the 2-inning trailing window. This was hand-verified against real
box scores during development (see git history) rather than trusted blindly.

## Leakage rules

No column in the output can be computed from the *current* pitch's own
outcome — every `_this_inning`/`_last_2_innings`/`_game`/`_by_count`/
`_vs_batter`/`_vs_pitcher`/`prev_*` column is strictly pre-pitch. The
counterpart is `LABEL_COLUMNS`:

```python
LABEL_COLUMNS = ["type", "zone", "startSpeed", "endSpeed", "code", "call",
                  "launchSpeed", "launchAngle", "totalDistance"]
```

These describe what *actually happened* on the row's own pitch (the ground
truth), and are present in the output for training/evaluation — but a model
must never be given them as input features. `MlbPitchPredictionModel`'s
`RESULT_COLUMNS` is a superset of this list covering every Statcast physics/
outcome column, and is what actually gets excluded at training time; see
[MlbPitchPredictionModel.py](../MlbPitchPredictionModel.py).

## Output columns, by category

`build_pitcher_data`/`build_batter_data` return one row per pitch, ~127
columns for a full season+ of data. Grouped:

- **Identifiers / join keys**: `index`, `g_id_int`, `ab_ind`, `p_ind`,
  `batter_id`, `pitcher_id`, `home_team`, `away_team`, `game_date`,
  `startTime`.
- **Pitch outcome (ground truth — see `LABEL_COLUMNS` above, never a feature)**:
  `type`, `zone`, `startSpeed`, `endSpeed`, `code`, `call`, `launchSpeed`,
  `launchAngle`, `totalDistance`, plus a long tail of raw Statcast physics
  columns carried straight through from `pitches` (spin, break, release
  position/velocity, plate location, xStats, bat-tracking — anything
  knowable only after the pitch happened).
- **Pre-pitch game/count state**: `inning`, `halfInning`, `outs`, `balls`,
  `strikes`, `on1b`/`on2b`/`on3b`, `awayScore`/`homeScore`,
  `pitch_num_in_game`.
  - `pitch_num_in_game` is computed here; the rest come straight from `abs`.
- **Matchup context**: `batter_stance`, `pitcher_hand`.
- **Game/weather context**: `day_night`, `weather_condition`, `temperature`,
  `wind_speed`, `wind_direction`.
- **1-pitch lookback**: `prev_pitch_type`, `prev_zone`, `prev_start_speed`,
  `prev_call`.
- **Pitch-mix history** (5 families x however many pitch types the player
  throws, e.g. `type_FF_game`, `type_SI_this_inning`, `type_ST_by_count`,
  `type_CH_vs_batter`, `type_FC_last_2_innings`, ...): the columns described
  above.
- **Savant-only supplemental columns** (see
  [scraper_and_schema.md](scraper_and_schema.md)): `n_thruorder_pitcher`,
  `n_priorpa_thisgame_player_at_bat`, `pitcher_days_since_prev_game`,
  `batter_days_since_prev_game`, `pitcher_days_until_next_game`,
  `batter_days_until_next_game`. These are pass-through Savant fields, not
  computed here — `pitcher/batter_days_until_next_game` in particular is only
  knowable in hindsight and should be excluded from live-prediction features
  even though it isn't in `LABEL_COLUMNS`.

## Worked example

`build_pitcher_data(657277)` (Logan Webb, 2024 season db) returns 3,201 rows
x 127 columns. A slice from pitches 4-8 of his first game that season
(a subset of columns, to show the mechanics):

```
 pitch_num  inning  balls  strikes  type  zone  prev_pitch_type  prev_zone  prev_start_speed  prev_call         type_FF_this_inning  type_SI_this_inning  type_FF_game  type_SI_game  type_FF_by_count  type_FF_vs_batter
         4       1      1        2    CH  13.0               CH       14.0              89.7  Ball                              0.0              0.666667           0.0      0.666667               NaN                0.0
         5       1      2        2    SI   4.0               CH       13.0              89.8  Ball                              0.0              0.500000           0.0      0.500000               NaN                0.0
         6       1      2        2    ST  14.0               SI        4.0              93.1  Foul                              0.0              0.600000           0.0      0.600000               0.0                0.0
         7       1      0        0    CH  13.0               ST       14.0              84.0  Swinging Strike                   0.0              0.500000           0.0      0.500000               0.0                NaN
         8       1      0        1    ST  14.0               CH       13.0              87.6  Swinging Strike                   0.0              0.428571           0.0      0.428571               0.0                0.0
```

Reading row 1 (pitch 4, a changeup): `prev_pitch_type=CH` and
`prev_zone=14.0` describe pitch 3, not this one. `type_SI_game=0.666667`
means 2 of the 3 pitches Webb had thrown so far in the game were sinkers.
`type_FF_by_count` is `NaN` because this is the first pitch of the game at a
1-2 count — no history yet at that specific count, so the mix is undefined
rather than 0. `type_FF_vs_batter` is `0.0` (not `NaN`) for this batter,
meaning Webb has thrown this batter at least one pitch somewhere in the
loaded history (possibly an earlier season) — just never a fastball —
while it's `NaN` for the batter two rows down, who Webb has no prior
pitches against at all in the loaded data.
