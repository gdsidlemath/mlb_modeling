# WP5c: Within-at-bat sequence features

**Depends on:** WP4. **Edits:** `MlbBuildModelData.py` (one method plus the
`AB_FEATURE_FAMILIES` entry). **Creates:** `tests/test_features_at_bat.py`.

## Goal

The existing `p_prev_*` / `b_prev_*` columns look back one pitch **within
the game**. On the first pitch of an at-bat, `p_prev_*` therefore describes
the pitcher's last pitch to the *previous* batter. Add lookbacks scoped to
the **current at-bat**.

These features need no player history, only earlier pitches in the same
at-bat. So they run on the assembled per-season frame through
`AB_FEATURE_FAMILIES` (see WP4), not in the player chunks. An at-bat never
spans seasons.

## Read first

`planning/impl/00_README.md`, `MlbBuildModelData._ab_features` and the
`AB_FEATURE_FAMILIES` docstring.

## Method: `_family_at_bat_sequence(self, frame)`

`frame` is sorted chronologically. Group by `["g_id_int", "ab_ind"]` (call it
`g`). Return these columns (no prefix; the names already follow the README
conventions):

| column | definition |
|---|---|
| `pitch_num_in_ab` | `g.cumcount() + 1`. Don't use `p_ind`: global filters remove some pitches, so `p_ind` can skip numbers |
| `prev_ab_type` | `g["type"].shift(1)` |
| `prev_ab_family` | `g["cur_family"].shift(1)` |
| `prev_ab_end_speed` | `g["endSpeed"].shift(1)` |
| `prev_ab_zone` | `g["y_zone"].shift(1)` (string zone code, so it stays categorical) |
| `prev_ab_swing` | `g["y_swing"].shift(1)` |
| `prev_ab_contact` | `g["y_contact"].shift(1)` |
| `prev_ab_outcome` | `g["y_outcome"].shift(1)` |
| `n_fouls_in_ab` | prior pitches in this at-bat with `y_outcome == "foul"`: `g-cumsum(is_foul) − is_foul` |
| `n_pitch_types_seen_in_ab` | distinct non-NaN types among prior pitches in the at-bat. `first = ~frame.duplicated(["g_id_int", "ab_ind", "type"]) & frame["type"].notna()`, then `g-cumsum(first) − first` |

Do the groupby on a copy with just the needed columns, to keep it fast.
Everything is NaN or 0 on the first pitch of each at-bat.

## Registration

`AB_FEATURE_FAMILIES = ["_family_at_bat_sequence"]`

## Tests (`tests/test_features_at_bat.py`)

1. **Hand-built frame:** two at-bats of four and three pitches. Check each
   column row by row. The first pitch of each at-bat has NaN `prev_ab_*`,
   `pitch_num_in_ab == 1` and zero counts. A repeated type doesn't increase
   `n_pitch_types_seen_in_ab`.
2. **Tiers.** All 10 columns classify as `T0_CONTEXT` via
   `MlbColumns.column_tier`. If `prev_ab_zone` isn't treated as categorical by
   `MlbColumns.categorical_columns`, report it (it's listed in
   `ZONE_LIKE_COLUMNS`).
3. **Test DB.** `pitch_num_in_ab` max is ≥ 10, and for every at-bat
   `pitch_num_in_ab` equals 1..n with no gaps.
4. The whole suite passes, including `tests/test_leakage.py`.

## Acceptance

The full suite passes.
