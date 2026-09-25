# WP6: Task registry and baselines (`MlbTasks.py`)

**Depends on:** WP2 (tiers) and WP5a/b/c (the baselines read their
columns). **Creates:** `MlbTasks.py`, `tests/test_tasks.py`. **Don't edit**
`MlbBuildModelData.py`.

## Goal

A declarative description of the seven prediction tasks. Each entry says
which target the task uses, what kind of prediction it is, the highest tier
of columns it may see, which rows it trains on, and the simple baseline it
must beat. WP7's model class consumes this.

## API

Use modern annotations (`list[str]`, `X | None`, `collections.abc.Callable`).

```python
@dataclass(frozen=True)
class TaskSpec:
    name: str
    target: str                      # a y_* column
    kind: str                        # "multiclass" | "binary" | "regression"
    max_tier: str                    # one of MlbColumns.FEATURE_TIERS
    row_filter: Callable[[pd.DataFrame], pd.Series]          # boolean mask
    baseline: Callable[[pd.DataFrame, pd.DataFrame], pd.Series]
        # (eval_df, train_df) -> class label (multiclass),
        #                        P(y=1) (binary), value (regression)
    baseline_proba: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame] | None = None
        # multiclass only: (eval_df, train_df) -> DataFrame, one column per
        # class, rows sum to 1

TASKS: dict[str, TaskSpec]
def get_task(name) -> TaskSpec                      # KeyError listing valid names
def split_by_date(df, test_frac) -> (train_df, test_df)
def task_data(df, task) -> (X, y, feature_cols, cat_cols)
def evaluate_baseline(task, train_df, eval_df) -> dict
```

## Tasks

| name | target | kind | max_tier | row_filter |
|---|---|---|---|---|
| `pitch_type` | `y_pitch_type` | multiclass | `T0_CONTEXT` | target notna |
| `pitch_family` | `y_pitch_family` | multiclass | `T0_CONTEXT` | target notna |
| `end_speed` | `y_end_speed` | regression | `T1_TYPE` | target notna & `y_pitch_type` notna |
| `location` | `y_zone` | multiclass | `T2_SPEED` | target notna & `y_pitch_type` notna |
| `swing` | `y_swing` | binary | `T3_LOCATION` | `is_bunt == 0` & `y_zone` notna |
| `contact` | `y_contact` | binary | `T3_LOCATION` | `y_swing == 1` & `is_bunt == 0` & `y_zone` notna |
| `outcome` | `y_outcome` | multiclass | `T3_LOCATION` | target notna & `y_zone` notna |

## Baselines

Each baseline uses a chain of **fallbacks**, from the first to the last
source listed. A fallback is used only on rows where the earlier source is
NaN. For "argmax of a mix", pick the column with the highest value and parse
the class out of the column name. A row whose mix columns are all NaN falls
through to the next source.

| task | baseline | fallbacks | `baseline_proba` |
|---|---|---|---|
| pitch_type | argmax `p_type_<T>_career` | train mode of target | the mix columns row-normalized; all-NaN rows → train class frequencies |
| pitch_family | argmax `p_fam_<F>_career` | train mode | same |
| end_speed | `p_end_speed_this_type_career` | train mean of target per `type` → overall train mean | – |
| location | argmax `p_zone_<Z>_this_type_vs_hand_career` | argmax `p_zone_<Z>_vs_hand_career` → train mode | same fallbacks, normalized |
| swing | `b_swing_rate_this_zone_career` | `b_swing_rate_career` → train mean | – |
| contact | `b_contact_rate_this_zone_career` | `b_contact_rate_career` → train mean | – |
| outcome | argmax `b_outcome_<cls>_by_count` | argmax `b_outcome_<cls>_career` → train mode | same fallbacks, normalized |

The class labels must match the target's values exactly. Zone columns give
`"5"` or `"11"` (strings, like `y_zone`), and outcome columns give
`"in_play_hr"`, etc.

## Other functions

- `split_by_date(df, test_frac)`: choose a cutoff `game_date` so that about
  `test_frac` of rows fall on or after it. The train split is
  `game_date < cutoff`; the test split is `game_date >= cutoff`. No date may
  appear on both sides.
- `task_data(df, task)`:
  1. `rows = df[task.row_filter(df)]`
  2. `feature_cols = MlbColumns.feature_columns(rows.columns, task.max_tier)`
  3. `cat_cols = MlbColumns.categorical_columns(feature_cols, rows)`
  4. Return `rows[feature_cols], rows[task.target], feature_cols, cat_cols`.
  5. **Assert** that `task.target` isn't in `feature_cols`.
- `evaluate_baseline(task, train_df, eval_df)`. Both frames are already
  row-filtered. It returns metrics by kind:
  - multiclass: `accuracy`, plus `log_loss` (with
    `labels=sorted(train ∪ eval classes)`) when `baseline_proba` exists
  - binary: `auc`, `brier`, `log_loss` (clip probabilities to
    [1e-6, 1 − 1e-6])
  - regression: `mae`, `rmse`

## Tests (`tests/test_tasks.py`)

Use the session-scoped `league_frame` fixture from `tests/conftest.py`
(read-only: `.copy()` before modifying). Parametrize per-task checks over
`MlbTasks.TASKS`.

1. Every task: `task_data` returns a non-empty X and a y with no NaN, and the
   target isn't in the features.
2. **The tier gates hold:**
   - the `pitch_type` features exclude `type`, `cur_family` and every
     `_this_type` column
   - the `end_speed` features include `type` but exclude `endSpeed` and
     `startSpeed`
   - the `location` features include `endSpeed` but exclude `zone`,
     `cur_in_zone` and `pX`
   - the `swing` features include `zone` and `cur_in_zone`
3. `split_by_date` never puts a date on both sides, and the test share is
   within 0.1 of `test_frac`.
4. Every baseline returns a value (no NaN) for every eval row. The
   `baseline_proba` rows sum to 1 ± 1e-6.
5. `evaluate_baseline` on a 75/25 date split returns the expected keys for
   all seven tasks. The swing baseline AUC is > 0.6, and the end_speed
   baseline MAE is < 3 mph.
6. `get_task("nope")` raises a `KeyError` that lists the valid names.

## Acceptance

The full suite passes. Report the baseline metrics table (task × metrics) on
the test DB.
