# WP5b: Swing / contact / outcome history

**Depends on:** WP4. If WP5a has landed, append to its registry lists rather
than replacing them. **Edits:** `MlbBuildModelData.py` (one or two new
methods plus registry entries). **Creates:**
`tests/test_features_plate_discipline.py`.

## Goal

Add the history features that the swing, contact and outcome tasks need.
The same method runs on **both** sides:
- batter side: what this batter does (their swing and chase rates)
- pitcher side: what this pitcher induces (induced swings and whiffs)

## Read first

`planning/impl/00_README.md`, `planning/impl/WP5a_pitch_history_features.md`
(the "Common setup" section applies here unchanged),
`MlbBuildModelData._group_cumulative_mean`, `MlbLabels.py` (the columns
`y_swing`, `y_contact`, `y_outcome`, `is_bunt`, `cur_in_zone`,
`cur_family`).

## Weights

Bunts are strategic, not swing decisions. Every swing/contact rate below
excludes bunt pitches from both numerator and denominator.

```python
not_bunt   = 1.0 - sub["is_bunt"]
in_zone    = (sub["cur_in_zone"] == 1).astype(float)    # NaN zone -> 0
out_zone   = (sub["cur_in_zone"] == 0).astype(float)
swung      = (sub["y_swing"] == 1).astype(float) * not_bunt
fam_is[F]  = (sub["cur_family"] == F).astype(float)     # per family F
zone_key   = sub["zone"].fillna(-1).astype(int).astype(str)   # NaN-safe key
family_key = sub["cur_family"].fillna("NA")
```

## Method: `_family_plate_discipline` (register for **both** sides)

"value → weight" means the mean of `value` over prior rows, weighted by
`weight`.

| output column | value | weight | group keys |
|---|---|---|---|
| `swing_rate_career` | `y_swing` | `not_bunt` | `[self_col]` |
| `swing_rate_by_count` | `y_swing` | `not_bunt` | `[self_col, count_key]` |
| `swing_rate_game` | `y_swing` | `not_bunt` | `[self_col, "g_id_int"]` |
| `zone_swing_rate_career` | `y_swing` | `not_bunt * in_zone` | `[self_col]` |
| `chase_rate_career` | `y_swing` | `not_bunt * out_zone` | `[self_col]` |
| `chase_rate_by_count` | `y_swing` | `not_bunt * out_zone` | `[self_col, count_key]` |
| `swing_rate_fam_<F>_career` (per family) | `y_swing` | `not_bunt * fam_is[F]` | `[self_col]` |
| `swing_rate_this_family_career` | `y_swing` | `not_bunt` | `[self_col, family_key]` |
| `swing_rate_this_zone_career` | `y_swing` | `not_bunt` | `[self_col, zone_key]` |
| `contact_rate_career` | `y_contact` | `swung` | `[self_col]` |
| `zone_contact_rate_career` | `y_contact` | `swung * in_zone` | `[self_col]` |
| `chase_contact_rate_career` | `y_contact` | `swung * out_zone` | `[self_col]` |
| `contact_rate_fam_<F>_career` | `y_contact` | `swung * fam_is[F]` | `[self_col]` |
| `contact_rate_this_family_career` | `y_contact` | `swung` | `[self_col, family_key]` |
| `contact_rate_this_zone_career` | `y_contact` | `swung` | `[self_col, zone_key]` |
| `outcome_<cls>_career` (9 cols) | outcome dummies | `y_outcome` notna | `[self_col]` |
| `outcome_<cls>_by_count` (9 cols) | outcome dummies | `y_outcome` notna | `[self_col, count_key]` |
| **batter side only:** `sz_top_career` | `strikeZoneTop` | – | `[self_col]` |
| **batter side only:** `sz_bot_career` | `strikeZoneBottom` | – | `[self_col]` |

Notes:
- Outcome dummies use fixed categories `MlbLabels.OUTCOME_CLASSES`, prefix
  `outcome`.
- Set `_this_family` columns to NaN where `cur_family` is NaN, and
  `_this_zone` columns to NaN where `zone` is NaN.
- The `y_contact` values are NaN on non-swing rows, but weight `swung` is 0
  on those rows, and `_group_cumulative_mean` also drops NaN values. Both are
  consistent.
- `_group_cumulative_mean` takes one weight for all its `value_cols`. Where
  the weights differ, make separate calls. Keep the call count reasonable by
  grouping columns that share a weight and key.
- Tiers follow automatically from the names: `_this_family` → T1,
  `_this_zone` → T3, everything else T0.
- No cold-start fill: leave NaN.

**Why this uses the current row's labels safely:** `y_swing`, `y_contact`
and `y_outcome` are POST_SWING for the *current* pitch. The helper subtracts
the current row (`cumsum − current`), so each row only sees earlier rows'
labels. The leakage test's perturbation case (a) changes `code`, which
changes the current row's labels, and checks that this row's T0/T1 features
don't move.

## Registration

Append `"_family_plate_discipline"` to **both**
`SIDE_FEATURE_FAMILIES["pitcher"]` and `["batter"]`. Decide the batter-only
`sz_*` columns inside the method with `self_col == "batter_id"`.

## Tests (`tests/test_features_plate_discipline.py`)

1. **Hand-checked values.** Use a small one-batter frame with codes
   [B, S, F, C, X, L(bunt), S] and known `cur_in_zone`. Check by hand, on
   the last row: `swing_rate_career` (the bunt is excluded from the
   denominator), `chase_rate_career` and `contact_rate_career`.
2. **Tiers.** Every new column classifies. `_this_zone` columns → T3,
   `_this_family` → T1, the rest T0.
3. **Test-DB sanity.** The mean of `b_swing_rate_career` (non-NaN) is between
   0.35 and 0.60, and the mean of `b_chase_rate_career` is below the mean of
   `b_zone_swing_rate_career`. On rows where all nine `b_outcome_*_career`
   columns are non-NaN, they sum to 1 ± 1e-6.
4. **Predictive sanity.** The AUC of `b_swing_rate_this_zone_career` for
   predicting `y_swing` is > 0.6 (on non-NaN, non-bunt rows). Compute it with
   `sklearn.metrics.roc_auc_score`.
5. The whole suite passes, including `tests/test_leakage.py`.

## Acceptance

The full suite passes. Report the new column count per side and the
test-DB mean `b_swing_rate_career`, `b_chase_rate_career` and
`b_contact_rate_career`.
