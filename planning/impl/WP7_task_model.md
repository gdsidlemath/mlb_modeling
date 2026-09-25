# WP7: Generic task model (`MlbTaskModel.py`)

**Depends on:** WP6. **Creates:** `MlbTaskModel.py`,
`tests/test_task_model.py`. **Don't edit** `MlbPitchPredictionModel.py`.
The existing `PitchPredictionModel` stays as-is for the per-pitcher
workflow. Use it as a **style and logic reference**: its three tuning loops,
estimator construction, and one-hot vs CatBoost-native preparation carry
over.

## Goal

One class that trains and evaluates any `TaskSpec` from `MlbTasks.TASKS` on
a league table (or a slice of one, e.g. a single pitcher). It supports
classification and regression across random forest, XGBoost and CatBoost, and
reports model metrics next to the task's baseline.

## API

```python
class TaskModel:
    def __init__(self, task, estimator="xgboost", n_estimators=200,
                 test_frac=0.25, random_state=0, tune=False, param_grid=None,
                 tune_val_frac=0.15, max_train_rows=None, **estimator_params):
        """task: TaskSpec or task name. estimator: 'random_forest' |
        'xgboost' | 'catboost'. max_train_rows: random subsample of the
        TRAIN split only (test stays complete) - for league-scale data."""

    def fit(self, df, test_df=None): ...
        # df = league table or slice. If test_df is given, df is the train
        # set and no split is made (e.g. train 2023-24, test 2025). Both are
        # row-filtered by the task inside fit. Returns self.
    def evaluate(self) -> dict: ...
    def predict(self, df) -> pd.Series: ...        # labels / P(y=1) / values
    def predict_proba(self, df) -> pd.DataFrame: ...  # classifiers only
```

## Behavior

**`fit`:**
1. `train_df, test_df = MlbTasks.split_by_date(df[task.row_filter(df)], test_frac)`.
   When `test_df` is passed, instead row-filter both frames and assert that
   `train.game_date.max() < test.game_date.min()`.
2. `max_train_rows`: `train_df.sample(n, random_state)` when larger.
3. Features come from `MlbTasks.task_data`.
4. Keep `self.train_df_` / `self.test_df_` for baselines, and
   `self.X_test_` / `self.y_test_`.

**Feature preparation** (fit on train only; stored so `predict` can
reproduce it):
- **catboost:** keep `cat_cols` as native categoricals (`astype(str)`, NaN →
  `"NA"`). Leave numeric NaN as NaN, since CatBoost handles it.
- **xgboost / random_forest:** one-hot encode `cat_cols` with
  `pd.get_dummies`. Record the train dummy columns and `reindex(columns=...,
  fill_value=0)` at predict time, so unseen categories become all-zero. Also
  convert the `on1b/on2b/on3b` ids to 0/1 occupancy flags, as the existing
  class does, for all estimators.
- **random_forest only:** scikit-learn 1.3 RF doesn't accept NaN, so fill
  NaN with -999. XGBoost keeps NaN.
- Drop any non-numeric column left after encoding. Store the final column
  list as `self.feature_cols_`.

**Estimators by kind:**

| kind | random_forest | xgboost | catboost |
|---|---|---|---|
| multiclass | `RandomForestClassifier` | `XGBClassifier(eval_metric="mlogloss")` + `LabelEncoder` | `CatBoostClassifier(loss_function="MultiClass")` |
| binary | `RandomForestClassifier` | `XGBClassifier(eval_metric="logloss")` | `CatBoostClassifier(loss_function="Logloss")` |
| regression | `RandomForestRegressor` | `XGBRegressor(eval_metric="rmse")` | `CatBoostRegressor(loss_function="RMSE")` |

For XGBoost, pass `tree_method="hist"`, `n_jobs=-1`. For binary, cast y to
int.

**Tuning** (`tune=True`). Port the three `_tune_*` loops from
`PitchPredictionModel`. Take the validation split as the **date-tail** of
train (use `split_by_date` on train with `tune_val_frac`). Default grids come
from that class's `*_PARAM_GRID` constants. **The score is task-dependent,
not accuracy:**
- classification: validation `log_loss(labels=classes)`, lower is better
- regression: validation RMSE

Early stopping works as in the existing loops for xgboost/catboost. Store
`self.best_params_` and `self.tuning_results_`.

**`evaluate()` returns:**
- `model`: the metrics dict with the same keys as
  `MlbTasks.evaluate_baseline` for this kind (multiclass also includes
  `log_loss` from `predict_proba`)
- `baseline`: `MlbTasks.evaluate_baseline(task, train_df_, test_df_)`
- `feature_importances`: a Series sorted in descending order
- `train_size`, `test_size`
- multiclass: `confusion_matrix` (DataFrame, labels = union of classes)
- binary: `calibration`, a DataFrame of 10 equal-width probability bins with
  mean predicted, observed rate and count

## Tests (`tests/test_task_model.py`)

Use the test-DB `build_league_frame()` once in `setUpClass`, with small
models (`n_estimators=20`, catboost `iterations=30`).

1. Every task with `estimator="xgboost"`: fit and evaluate succeed, and every
   metric is finite.
2. One task per kind (`location`, `swing`, `end_speed`) with
   `random_forest` and with `catboost`: fit and evaluate succeed.
3. **Prediction consistency.** `predict(test_df_)` equals the predictions
   used inside `evaluate`. `predict` on a frame with one categorical column
   replaced by an unseen value doesn't raise.
4. **No leakage through features.** For the `pitch_type` task,
   `feature_cols_` contains no column whose `MlbColumns.column_tier` is
   above T0. That includes one-hot children: map each dummy column back to
   its parent to check.
5. `tune=True` on `swing` with xgboost and a 2×2 grid: `best_params_` is set.
6. `max_train_rows=1000` gives `train_size == 1000`.
7. `fit(train, test_df=test)` with an explicit date split works, and
   overlapping dates raise.

## Acceptance

The full suite passes. Report a table of test-DB `model` vs `baseline` for
each task, using xgboost. On data this small the model may not beat the
baseline; just report the numbers.
