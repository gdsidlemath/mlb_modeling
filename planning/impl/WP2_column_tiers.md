# WP2: Column tiers (`MlbColumns.py`)

**Depends on:** WP0. **Creates:** `MlbColumns.py`, `tests/test_columns.py`.
**Don't modify** `MlbPitchPredictionModel.py`. Its `RESULT_COLUMNS` stays
until WP7 replaces the class.

## Goal

This is the single source of truth for which columns a task may use as
features. Every column is assigned a **tier**. A task declares the highest
tier it may see, and gets the columns at that tier or below. Unknown **raw**
columns raise an error, so a new scraper column can never silently become a
feature.

## Tiers

```python
FEATURE_TIERS = ["T0_CONTEXT", "T1_TYPE", "T2_SPEED", "T3_LOCATION"]  # ordered
NON_FEATURE_TIERS = ["ID", "TARGET", "POST_PITCH_PHYSICS", "POST_SWING", "HINDSIGHT"]
```

## Raw column assignments

Every raw column the league frame can contain (from `pitches`, `abs` and
`games`) must be listed in exactly one dict entry:

```python
RAW_COLUMN_TIERS = {
    # ID: keys, ids, timestamps
    "index": "ID", "g_id_int": "ID", "ab_ind": "ID", "p_ind": "ID",
    "batter_id": "ID", "pitcher_id": "ID", "home_team": "ID", "away_team": "ID",
    "game_date": "ID", "startTime": "ID", "startTime_int": "ID",
    "g_id_str": "ID", "season": "ID",

    # T0: known before the pitch
    "balls": "T0_CONTEXT", "strikes": "T0_CONTEXT", "outs": "T0_CONTEXT",
    "inning": "T0_CONTEXT", "halfInning": "T0_CONTEXT",
    "on1b": "T0_CONTEXT", "on2b": "T0_CONTEXT", "on3b": "T0_CONTEXT",
    "awayScore": "T0_CONTEXT", "homeScore": "T0_CONTEXT",
    "batter_stance": "T0_CONTEXT", "pitcher_hand": "T0_CONTEXT",
    "day_night": "T0_CONTEXT", "weather_condition": "T0_CONTEXT",
    "temperature": "T0_CONTEXT", "wind_speed": "T0_CONTEXT",
    "wind_direction": "T0_CONTEXT", "stadium": "T0_CONTEXT",
    "ht_win_pct": "T0_CONTEXT", "at_win_pct": "T0_CONTEXT",
    "ht_gms_plyd": "T0_CONTEXT", "at_gms_plyd": "T0_CONTEXT",
    "n_thruorder_pitcher": "T0_CONTEXT",
    "n_priorpa_thisgame_player_at_bat": "T0_CONTEXT",
    "pitcher_days_since_prev_game": "T0_CONTEXT",
    "batter_days_since_prev_game": "T0_CONTEXT",

    # cascade tiers
    "type": "T1_TYPE", "cur_family": "T1_TYPE",
    "startSpeed": "T2_SPEED", "endSpeed": "T2_SPEED",
    "zone": "T3_LOCATION", "cur_in_zone": "T3_LOCATION",
    "cur_zone_row": "T3_LOCATION", "cur_zone_col": "T3_LOCATION",

    # never: physics of the current pitch (incl. exact plate location, since
    # the cascade predicts only the zone)
    **{c: "POST_PITCH_PHYSICS" for c in [
        "pX", "pZ", "x", "y", "x0", "y0", "z0", "vX0", "vY0", "vZ0",
        "aX", "aY", "aZ", "pfxX", "pfxZ", "breakAngle", "breakLength",
        "breakY", "breakVertical", "breakVerticalInduced", "breakHorizontal",
        "spinRate", "spinDirection", "typeConfidence", "plateTime",
        "extension", "arm_angle",
        # measured per pitch (batter's posture at that moment); use the
        # batter's prior mean instead (WP5b b_sz_*_career)
        "strikeZoneTop", "strikeZoneBottom",
    ]},

    # never: result of the pitch / swing / at-bat
    **{c: "POST_SWING" for c in [
        "code", "call", "eventType", "description", "is_bunt",
        "launchSpeed", "launchAngle", "totalDistance", "trajectory",
        "hardness", "location", "coordX", "coordY",
        "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
        "estimated_slg_using_speedangle", "woba_value", "woba_denom",
        "babip_value", "iso_value", "launch_speed_angle",
        "delta_home_win_exp", "delta_run_exp", "delta_pitcher_run_exp",
        "home_win_exp", "bat_win_exp", "bat_speed", "swing_length",
        "attack_angle", "attack_direction", "swing_path_tilt",
        "intercept_ball_minus_batter_pos_x_inches",
        "intercept_ball_minus_batter_pos_y_inches", "hyper_speed",
    ]},

    # never: only knowable afterward
    **{c: "HINDSIGHT" for c in [
        "pitcher_days_until_next_game", "batter_days_until_next_game",
        "endTime", "endTime_int", "winning_pitcher", "losing_pitcher",
    ]},
}
```

`home_win_exp` / `bat_win_exp` are Savant values recorded *at* the pitch.
They're classified as POST_SWING to be safe; leave them there.

## Derived column rules (for columns not in `RAW_COLUMN_TIERS`)

Apply these checks in order and stop at the first match:

1. starts with `y_` → `TARGET`
2. contains `_this_zone` → `T3_LOCATION`
3. contains `_this_type` or `_this_family` → `T1_TYPE`
4. starts with `p_`, `b_`, `prev_ab_`, `n_` (and ends with `_in_ab`), or
   equals `pitch_num_in_ab` → `T0_CONTEXT`
5. **Legacy per-player builder names**, so `build_pitcher_data` output
   also classifies: starts with `prev_` or `type_`, equals
   `pitch_num_in_game`, or ends with `_n_pitches` → `T0_CONTEXT`
6. otherwise → raise `KeyError(f"unclassified column: {col}")`

## Public API

```python
def column_tier(col: str) -> str
def tier_table(columns) -> pd.DataFrame        # column, tier; for docs/debugging
def feature_columns(columns, max_tier: str) -> List[str]
    # all columns whose tier is in FEATURE_TIERS and <= max_tier; input order kept
def categorical_columns(feature_cols, df) -> List[str]
    # object/category dtype columns among feature_cols, plus any in
    # ZONE_LIKE_COLUMNS present (zone codes are categories, not numbers)
ZONE_LIKE_COLUMNS = ["zone", "prev_zone", "p_prev_zone", "b_prev_zone", "prev_ab_zone"]
```

## Tests (`tests/test_columns.py`)

1. Every column of every table in `data/mlb_pitch_data_test.db` (`pitches`,
   `abs`, `games`) classifies without raising.
2. Every column of `tests/fixtures/golden_pitcher.pkl` classifies without
   raising.
3. `feature_columns(cols, "T0_CONTEXT")` contains none of `type`, `zone`,
   `endSpeed`, `pX`, `code`, `y_swing`, `p_zone_5_this_type_vs_hand_career`,
   `b_swing_rate_this_zone_career`.
4. `feature_columns(cols, "T1_TYPE")` contains `type`, `cur_family` and
   `p_end_speed_this_type_career`, but not `endSpeed` or
   `b_contact_rate_this_zone_career`.
5. `feature_columns(cols, "T3_LOCATION")` contains `zone` and `cur_in_zone`
   but not `pX` or `strikeZoneTop`.
6. `column_tier("some_new_raw_col")` raises `KeyError`.
7. No key appears twice in `RAW_COLUMN_TIERS`. Build the dict so a duplicate
   would be detectable, e.g. assert that the sum of the list lengths equals
   the number of keys.

For tests 3–5, `cols` is a hand-written list of example names mixing raw and
derived columns.

## Acceptance

The full suite passes. Report any test-DB column that didn't fit and which
tier you gave it.
