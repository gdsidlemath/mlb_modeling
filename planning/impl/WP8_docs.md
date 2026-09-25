# WP8: Docs, full-data build, first real results

**Depends on:** WP7. **Edits:** `docs/model_data_builder.md`. **Creates:**
`docs/model_table.md`, `utils/describe_model_table.py`,
`utils/evaluate_tasks.py`, `planning/<date>_multi_target_results.md`.

## Steps

1. **Full build.** Run the CLI over all seasons, in the background (it takes
   hours). Log to `data/model_table_build.log`:
   `uv run python build_model_table.py --table-name default > data/model_table_build.log 2>&1`
   (and `uv run python utils/...` for the scripts below)
   Record the wall time, the peak memory if observable (Task Manager / a
   `psutil` poll if installed; otherwise skip), the files written, and the
   total size.

2. **Column catalog.** Write `utils/describe_model_table.py`. It loads one
   season of a table (`load_model_table(seasons=[2024])`) and writes
   `docs/model_table.md` containing:
   - one row per column: column, tier (`MlbColumns.column_tier`), dtype,
     non-null %, and an example value
   - grouped by tier, then by prefix (`p_`, `b_`, `prev_ab_`, `cur_`, `y_`,
     raw)
   - a short header explaining the tiers and the naming conventions (copy
     from `planning/impl/00_README.md`)

3. **Update `docs/model_data_builder.md`.** Add a section on
   `build_league_frame` / `build_league_data` / `load_model_table`: the
   chunking and why it exists, the per-season output layout, the manifest,
   the swappable label maps and the fact that swapping one means a rebuild,
   and the last-2-innings fix (what changed for batter-side rows). Keep the
   existing per-player sections. They're still valid.

4. **First real results.** `utils/evaluate_tasks.py` trains
   `TaskModel(task, estimator="xgboost", n_estimators=300,
   max_train_rows=300_000)` for every task, on seasons 2023–2024, and
   evaluates it on 2025, via `fit(train_df, test_df=test_df)`. Write
   `planning/<date>_multi_target_results.md` containing:
   - a task × (model metrics, baseline metrics) table
   - the top 15 feature importances per task
   - a short "surprises" list: any task that doesn't beat its baseline, and
     any feature in the top 15 that looks like leakage (e.g. an unexpected
     `_this_*` column in a low-tier task). The tier tests should make that
     impossible, so report it loudly if it happens.

## Acceptance

- `docs/model_table.md` covers 100% of the columns (the script asserts this).
- The results doc exists, with numbers for all seven tasks.
- The full test suite still passes.
