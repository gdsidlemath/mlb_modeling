# Implementation plans: multi-target pitch dataset

These work packages (WPs) implement
[../2026-09-25_multi_target_dataset_spec.md](../2026-09-25_multi_target_dataset_spec.md).
Each WP is written so an agent with **no other context** can carry it out.
Read this README first, then only your own WP file. Where a WP file and the
spec disagree, **the WP file wins**: the WPs include data checks that were run
after the spec was written.

## Before any WP starts (orchestrator / user)

1. **The project lives in WSL:** `~/projects/mlb_modeling` (Ubuntu, WSL2),
   on branch `claude/baseball-savant-api-13d052`. Run Claude Code and every
   agent **inside WSL**, e.g. open the folder with VS Code/Cursor's WSL
   remote, or run `claude` from a WSL shell there. Don't work from the old
   Windows checkout on `Z:\`. Git can't even operate there from WSL.
2. **Restart WSL once so the new limits apply.** `C:\Users\gsidl\.wslconfig`
   was raised to 32 GB / 8 CPUs on 2026-09-25 (backup: `.wslconfig.bak-2026-09-25`).
   Run `wsl --shutdown` from Windows, reopen WSL, and check with `free -g` /
   `nproc`: expect ~31 GB and 8. Until then WSL is capped at 12 GB / 2 CPUs,
   which is too small for WP4 and WP8.
3. **Commit before starting agents.** An agent in an isolated worktree starts
   from the last commit.
4. **WP0 runs first and alone.** It moves the project from Python 3.8 /
   pandas 1.5 to **Python 3.13 / pandas 3** and sets up pytest. Every later
   WP assumes the environment WP0 creates.

## Work packages and order

| WP | title | depends on | edits | suitable for |
|---|---|---|---|---|
| [WP0](WP0_env_and_tests.md) | Python 3.13 environment, pandas 3 port, pytest harness + reference snapshots | – | `pyproject.toml`, existing `.py` files (port only), new `tests/` | mid-size model |
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

## Environment (set up by WP0)

- **Python 3.13**, in a project virtualenv (`.venv/`) managed by **uv**.
  Dependencies live in `pyproject.toml` and are locked in `uv.lock`, both
  committed. The expected version set (resolved 2026-09-25) is pandas
  3.0.6, numpy 2.5.3, scikit-learn 1.9.1, xgboost 3.4.1, catboost 1.2.10,
  pyarrow 25.0.1, pytest 9.1.1.
- **Platform: WSL2 Ubuntu.** uv 0.10.9 is at `~/.local/bin/uv`, and
  uv-managed CPython 3.13.12 is already installed.
- **Run everything through the venv:** `uv run python ...` and
  `uv run pytest`. The system `python3` in WSL is 3.8 with no pandas, so
  **never call bare `python3` or `pip`.**
- **Resources:** 32 GB RAM and 8 CPUs for WSL (see "Before any WP starts",
  step 2). The host has 48 GB.
- **Paths:** keep the repo, `.venv/`, `data/` and all outputs on the WSL
  filesystem (`~/projects/mlb_modeling`). **Never under `/mnt/c` or
  `/mnt/z`.** Those go through a slow Windows file-sharing layer, and SQLite
  locking on them is unreliable.
- **Use modern syntax:** `list[str]`, `dict[str, int]` and `X | None` in
  annotations, `str.removeprefix`, and `dataclass(slots=True)` where useful.
  Don't add `typing.List` / `Optional` imports.
- **pandas 3 rules** (these differ from what older examples and your
  training data may show):
  - **Copy-on-Write is always on.** Chained assignment
    (`df["a"][mask] = x`, or `sub = df[mask]; sub["c"] = ...` expecting `df`
    to change) never modifies the original. Use `df.loc[mask, "a"] = x`, and
    treat every subset as an independent copy.
  - **Strings default to the `str` dtype, not `object`.** Check with
    `pd.api.types.is_string_dtype(s)` or `is_object_dtype(s)`, never with
    `dtype == object`. `astype(str)` keeps NaN as NaN (it used to become the
    string `"nan"`). `read_sql` returns `str` columns.
  - **`pd.get_dummies` returns `bool`.** Pass `dtype=float` when the dummies
    feed arithmetic.
  - **`groupby` still drops rows whose key is NaN** (their result is NaN).
    Fill NaN keys with a sentinel such as `"NA"` before grouping, or pass
    `dropna=False`.
  - Categorical group keys default to `observed=True`.
  - `groupby(...).apply` no longer passes the grouping columns to the
    function. Select the columns you need explicitly.
  - `DataFrame.applymap` is gone (use `DataFrame.map`), and so is
    `fillna(method=...)` (use `ffill()`/`bfill()`).
  - `merge_asof` needs the `on` column sorted globally and free of NaN.
  - **Don't load pickles written by pandas 1.5.** Cross-version pickle
    compatibility isn't guaranteed.
- **numpy 2:** `np.NaN`, `np.Inf` and `np.float_` are gone. Use `np.nan`,
  `np.inf` and `np.float64`.
- **scikit-learn ≥ 1.4 random forests accept NaN natively.** Don't add
  sentinel fills just for RF.
- **Tests use pytest.** The config is in `pyproject.toml`
  (`[tool.pytest.ini_options]`), and it turns `FutureWarning` and pandas'
  `ChainedAssignmentError` into **errors**, so deprecated or
  silently-ineffective pandas usage fails the suite. Run the suite from the
  repo root:
  `uv run pytest`
  Conventions:
  - Tests are plain `test_*` functions in `tests/test_*.py`. Don't write
    `unittest.TestCase` classes.
  - Put shared expensive objects (test builder, league frame) in **session-
    or module-scoped fixtures** in `tests/conftest.py`, so they're built
    once. Add new shared fixtures there, not in individual test files.
  - Use the `tmp_path` fixture for scratch files (not `tempfile`), and
    `@pytest.mark.parametrize` for per-task / per-estimator loops.
  - Mark anything that reads a full-season DB with `@pytest.mark.slow`.
    Those tests are skipped by default; run them with `uv run pytest -m slow`.
- **Test fixture DB:** `data/mlb_pitch_data_test.db`, generated by
  `utils/make_test_db.py` from the 2023 and 2024 season DBs (`.db` files are
  git-ignored, so regenerate it on a fresh clone). It holds 285 games and
  84,873 pitches in two slices, 2023-09-20..09-30 and 2024-03-28..04-07, so
  multi-season history and season decay get exercised. It has no duplicate
  keys. Build it with
  `BuildMlbModelData(data_as_type="db", load_dir="data", load_name="mlb_pitch_data_test")`.
  - Golden pitcher `657277`: 490 pitches, both seasons.
  - Golden batter `668804`: 440 pitches, both seasons.
  - To split the fixture by date in tests (e.g. `date_until`), use
    `20240401`.

  The fixture it replaced had duplicate games (it predates the scraper's
  postponed-game fix), which made the builder emit 4× rows for some pitchers.
  That file is kept as `data/mlb_pitch_data_test.dirty.db`. Don't use it.
- **Full data:** `data/mlb_pitch_data_2015.db` … `_2025.db`, about 7.9M
  pitches. They were copied into the WSL clone on 2026-09-25 and verified
  (sizes, pitch counts, `pragma quick_check`). The originals remain on
  `Z:\`. **Don't run full 11-season builds unless your WP says to.** They
  take a long time and a lot of memory.

## Rules for every WP

1. **No leakage.** Every history feature for pitch *i* uses only pitches
   strictly before *i* in the order `(game_date, g_id_int, ab_ind, p_ind)`.
   Use the existing pattern `cumsum() - current` or `shift(1)`. Never include
   the current row.
2. **Don't edit** `MlbApiScraper.py`, anything under `data/`, or
   `MlbPitchPredictionModel.py` (WP7 builds a new class next to it). The one
   exception is WP0's Python 3.13 / pandas 3 port, which may touch any `.py`
   file, but only to keep behavior identical.
3. **Match the house style.** That means class-level UPPER_CASE constants,
   docstrings that explain *why*, sparse comments, and 4-space indents. Read
   the file you're editing before writing.
4. **Every WP adds tests** under `tests/`, and the whole suite
   (`uv run pytest`) must pass before you finish.
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
