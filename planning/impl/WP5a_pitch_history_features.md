# WP5a: Pitch-family, zone and speed history features

**Depends on:** WP4. **Edits:** `MlbBuildModelData.py` (three new methods
plus registry entries). **Creates:** `tests/test_features_pitch_history.py`.

## Goal

Add the history features the **type** (family-level), **speed** and
**location** tasks need. Every feature is computed with the WP3 helpers
(`_group_cumulative_mean`, `_windowed_mix`), so the no-leakage property comes
from those helpers. Don't write new cumulative logic.

## Read first

`planning/impl/00_README.md` (the naming conventions matter here: the
`_this_type` marker decides the tier), `MlbBuildModelData.py` (the
`_group_cumulative_mean`, `_windowed_mix` and `_side_features` docstrings),
`MlbLabels.py`, `MlbColumns.py`.

## Common setup inside each method

```python
opp_hand = "batter_stance" if self_col == "pitcher_id" else "pitcher_hand"
opponent_suffix = "vs_batter" if opponent_col == "batter_id" else "vs_pitcher"
type_key = sub["type"].fillna("NA")          # NaN-safe group key
count_key = sub["balls"].astype(str) + "-" + sub["strikes"].astype(str)
```

Build any extra key columns on a working copy. **Never mutate `sub`.**
Return a DataFrame with `index == sub.index` containing only new columns,
**without** the `p_`/`b_` prefix (`_side_features` adds it).

## Method 1: `_family_pitch_family_mix` (register for **both** sides)

Family dummies from `cur_family` with fixed categories
(`MlbLabels.pitch_families(self.pitch_family_map)`), prefix `fam`. So the
columns are `fam_fastball`, `fam_breaking`, etc.

Build `work` the way `_build_pitch_mix_features` does for type dummies (the
same key/date/decay-helper columns), then call `self._windowed_mix(work,
fam_cols, self_col, opponent_col, opponent_suffix)` and return the
concatenated mix frames. **Drop its `n_obs` frame**, because it duplicates
the type-mix counts.

This yields `fam_<F>_{this_inning,last_2_innings,game,by_count,<opponent_suffix>,career}`,
which is 6 × (number of families) columns. It honors `mix_decay_mode`
automatically.

Why: fine-grained type mixes are split by the SL→ST relabelling across
seasons, and family mixes aren't.

## Method 2: `_family_zone_history` (register for **both** sides; the `this_type` parts are pitcher side only)

Zone dummies with fixed categories `MlbLabels.ZONES` from `sub["zone"]`,
prefix `zone`, giving `zone_1` … `zone_14`. The weight is
`sub["zone"].notna().astype(float)`, so pitches with no zone don't dilute
the mix.

| output columns | value | group keys | weight |
|---|---|---|---|
| `zone_<Z>_vs_hand_career` | zone dummies | `[self_col, opp_hand]` | zone notna |
| `zone_<Z>_by_count` | zone dummies | `[self_col, count_key]` | zone notna |
| `in_zone_rate_career` | `cur_in_zone` | `[self_col]` | – |
| `in_zone_rate_by_count` | `cur_in_zone` | `[self_col, count_key]` | – |
| **pitcher only:** `zone_<Z>_this_type_vs_hand_career` | zone dummies | `[self_col, type_key, opp_hand]` | zone notna |
| **pitcher only:** `in_zone_rate_this_type_career` | `cur_in_zone` | `[self_col, type_key]` | – |

`_group_cumulative_mean` names outputs `f"{c}_{suffix}"`, so pass suffixes
`vs_hand_career`, `by_count`, `this_type_vs_hand_career`, etc. For
`in_zone_rate_*`, rename the single output column.

On rows where `type` is NaN, set the `_this_type` columns to NaN (the "NA"
group is meaningless).

**No cold-start fill** for these columns. Leave NaN when there's no prior
data. Tree models handle NaN, and WP7 decides how to fill for random forest.

## Method 3: `_family_speed_history` (register for the **pitcher** side only)

| output column | value | group keys | weight |
|---|---|---|---|
| `end_speed_this_type_career` | `endSpeed` | `[self_col, type_key]` | – |
| `end_speed_this_type_game` | `endSpeed` | `[self_col, "g_id_int", type_key]` | – |
| `end_speed_this_type_game_delta` | `game − career` (the two columns above) | | |
| `start_speed_this_type_career` | `startSpeed` | `[self_col, type_key]` | – |
| `n_pitches_this_type_career` | the `n_obs` from `end_speed_this_type_career` | | |
| `fb_end_speed_career` | `endSpeed` | `[self_col]` | `cur_family == "fastball"` |
| `fb_end_speed_game` | `endSpeed` | `[self_col, "g_id_int"]` | same |
| `fb_end_speed_game_delta` | game − career | | |

`_this_type` columns are NaN on rows where `type` is NaN. The `fb_*` columns
don't depend on the current pitch, so they're T0 (fatigue signal usable even
for the type task).

## Registration

```python
SIDE_FEATURE_FAMILIES = {
    "pitcher": ["_family_pitch_family_mix", "_family_zone_history", "_family_speed_history"],
    "batter":  ["_family_pitch_family_mix", "_family_zone_history"],
}
```

`_family_zone_history` decides the pitcher-only parts with
`self_col == "pitcher_id"`.

## Tests (`tests/test_features_pitch_history.py`)

1. **Hand-checked values.** Use a 12-row, one-pitcher frame (build it through
   the public path, or call the method directly on a frame that has the
   required columns), with types [FF, SL, FF, FF, SL, …] and known speeds.
   Assert `end_speed_this_type_career` on specific rows equals the mean of
   prior same-type speeds, and that the first FF row is NaN.
2. **Tiers.** On the `league_frame` fixture (WP4, `tests/conftest.py`), every new `p_`/`b_` column
   classifies with `MlbColumns.column_tier`. Every column containing
   `_this_type` is `T1_TYPE`, and every other new column is `T0_CONTEXT`.
3. **Sanity on the test DB.** The Pearson correlation of
   `p_end_speed_this_type_career` with `endSpeed` is > 0.9 (on rows with
   both non-NaN). For rows where `p_zone_*_vs_hand_career` is non-NaN, the 13
   columns sum to 1 ± 1e-6.
4. **Fixed columns.** `p_zone_<Z>_by_count` exists for all 13 zones, and
   `p_fam_<F>_career` for every family.
5. The whole existing suite passes, **especially `tests/test_leakage.py`**.

## Acceptance

The full suite passes. Report the number of new `p_` and `b_` columns, and
the time `build_league_frame()` on the test DB takes before and after this
WP.
