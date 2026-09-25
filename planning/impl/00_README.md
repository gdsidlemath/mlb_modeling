# Implementation plans: multi-target pitch dataset

These work packages (WPs) implement
[../2026-09-25_multi_target_dataset_spec.md](../2026-09-25_multi_target_dataset_spec.md).
Each WP is written so an agent with **no other context** can carry it out.
Read this README first, then only your own WP file. Where a WP file and the
spec disagree, **the WP file wins**: the WPs include data checks that were run
after the spec was written.

## Before any WP starts (orchestrator / user)

1. **Commit the current working tree.** `MlbBuildModelData.py` has
   uncommitted changes and `MlbPitchPredictionModel.py` is untracked. An agent
   in an isolated worktree starts from the last commit and will not see them.
2. Optional: `pip install "pyarrow<18"` (the last line of releases that
   supports Python 3.8). Without it, WP4 falls back to pickle files.

## Work packages and order

| WP | title | depends on | edits | suitable for |
|---|---|---|---|---|
| [WP0](WP0_baseline_tests.md) | Test harness + golden snapshots | – | new `tests/` | small model |
| [WP1](WP1_labels.md) | Label mappings and `y_*` columns | WP0 | new `MlbLabels.py` | small model |
| [WP2](WP2_column_tiers.md) | Column tiers | WP0 | new `MlbColumns.py` | small model |
| [WP3](WP3_builder_refactor.md) | Actor-keyed history helpers + last-2-innings fix | WP0 | `MlbBuildModelData.py` | mid-size model |
| [WP4](WP4_league_build.md) | League-wide, multi-season, chunked build | WP1, WP2, WP3 | `MlbBuildModelData.py`, new script | **strongest available** |
| [WP5a](WP5a_pitch_history_features.md) | Speed / zone / family history | WP4 | `MlbBuildModelData.py` | mid-size model |
| [WP5b](WP5b_plate_discipline_features.md) | Swing / contact / outcome history | WP4 (after WP5a if run sequentially) | `MlbBuildModelData.py` | mid-size model |
| [WP5c](WP5c_at_bat_features.md) | Within-at-bat features | WP4 | `MlbBuildModelData.py` | small model |
| [WP6](WP6_task_registry.md) | Task registry + baselines | WP2, WP5a, WP5b, WP5c | new `MlbTasks.py` | small model |
| [WP7](WP7_task_model.md) | Generic task model class | WP6 | new `MlbTaskModel.py` | mid-size model |
| [WP8](WP8_docs.md) | Docs + full-data build | WP7 | `docs/` | small model |

```
WP0 ─┬─ WP1 ─┐
     ├─ WP2 ─┼─ WP4 ─┬─ WP5a ─┐
     └─ WP3 ─┘       ├─ WP5b ─┼─ WP6 ── WP7 ── WP8
                     └─ WP5c ─┘
```

- WP1, WP2 and WP3 touch different files and can run in parallel.
- WP5a, WP5b and WP5c each add a method to `MlbBuildModelData.py` and one
  line to a registry list. Run them **sequentially** (a → b → c). If they do
  run in parallel, the only expected merge conflict is in the registry lists.

## Environment facts (verified 2026-09-25)

- **Python 3.8.0**, pandas 1.5.0, numpy 1.23.3, scikit-learn 1.3.2, xgboost
  2.1.4, catboost 1.2.10. 48 GB RAM, 8 logical CPUs, Windows.
- **Python 3.8 syntax only.** Do not use `list[str]` / `dict[str, int]` /
  `X | None` in annotations (use `typing.List`, `Dict`, `Optional`), and
  don't use `str.removeprefix`, `functools.cache` or the dict `|` operator.
- **pandas 1.5 pitfalls:**
  - `pd.get_dummies` returns `uint8`. A groupby `cumsum` upcasts to `uint64`,
    so it's safe.
  - **`groupby` drops rows whose key is NaN** (their result is NaN). Fill NaN
    keys with a sentinel string such as `"NA"` before grouping, or pass
    `dropna=False`.
  - `merge_asof` needs the `on` column sorted globally and free of NaN.
  - There's no `DataFrame.map` (use `applymap`) and no `include_groups=` on
    `groupby.apply`.
- **No pytest.** Tests use stdlib `unittest`. Run them from the repo root:
  `python -m unittest discover -s tests -t . -v`
- **Test fixture DB:** `data/mlb_pitch_data_test.db`: 92 games, 27,155
  pitches, 2024-04-01..2024-08-09. Build it with
  `BuildMlbModelData(data_as_type="db", load_dir="data", load_name="mlb_pitch_data_test")`.
  The heaviest pitcher in it is `666159` (360 pitches).
- **Full data:** `data/mlb_pitch_data_2015.db` … `_2025.db`, about 7.9M
  pitches. **Don't run full 11-season builds unless your WP says to.** They
  take a long time and a lot of memory.

## Rules for every WP

1. **No leakage.** Every history feature for pitch *i* uses only pitches
   strictly before *i* in the order `(game_date, g_id_int, ab_ind, p_ind)`.
   Use the existing pattern `cumsum() - current` or `shift(1)`. Never include
   the current row.
2. **Don't edit** `MlbApiScraper.py`, anything under `data/`, or
   `MlbPitchPredictionModel.py` (WP7 builds a new class next to it).
3. **Match the house style.** That means class-level UPPER_CASE constants,
   docstrings that explain *why*, sparse comments, and 4-space indents. Read
   the file you're editing before writing.
4. **Every WP adds tests** under `tests/`, and the whole suite must pass
   before you finish.
5. **Don't commit** unless the orchestrator tells you to. When you finish,
   report: files changed, test output (pass/fail counts), anything in your WP
   you couldn't do or had to change, and any data surprises.

## Shared naming conventions (WP2 enforces these, WP4/WP5 must follow them)

| pattern | meaning | tier |
|---|---|---|
| `y_*` | target labels | never a feature |
| `p_*` | pitcher-side history feature (WP4 adds the prefix) | by the rules below |
| `b_*` | batter-side history feature | by the rules below |
| `cur_*` | derived from the *current* pitch's type/zone | explicit per column (WP2) |
| name contains `_this_type` or `_this_family` | history conditioned on the current pitch's type/family | **T1_TYPE** |
| name contains `_this_zone` | history conditioned on the current pitch's zone | **T3_LOCATION** |
| `prev_ab_*`, `pitch_num_in_ab`, `n_*_in_ab` | within-at-bat lookback | T0_CONTEXT |
| other `p_*` / `b_*` | history over prior pitches | T0_CONTEXT |

Any feature that uses the **current** row's type, family or zone as a
**group key** must contain one of the `_this_*` markers in its name. That's
how the tier code knows it can't be used before the cascade reaches that
stage.

## Fixed category lists (defined in WP1's `MlbLabels.py`; import them, don't copy)

- `ZONES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14]`. Zone 10 never occurs.
- `OUTCOME_CLASSES = ["ball", "called_strike", "swinging_strike", "foul",
  "hbp", "in_play_out", "in_play_single", "in_play_xbh", "in_play_hr"]`
- `pitch_types(pitch_family_map)` = `sorted(pitch_family_map)`, and
  `pitch_families(pitch_family_map)` = `sorted(set(pitch_family_map.values()))`

In a league-wide build, dummy columns **must** come from these fixed lists
(`pd.Categorical(..., categories=...)`) and not from whatever values are
present. Otherwise different player chunks end up with different columns.
