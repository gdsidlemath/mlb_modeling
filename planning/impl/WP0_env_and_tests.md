# WP0: Python 3.13 environment, pandas 3 port, pytest harness

**Depends on:** nothing. **Runs alone:** every other WP assumes the
environment this one creates.

**Creates:** `pyproject.toml`, `uv.lock`, `tests/` (harness, reference
fixtures, first tests). **Edits:** `.gitignore`, `run_season_range.sh`, and
the existing `.py` files **only as needed** to keep behavior identical under
the new versions.

## Goal

Move the project from Python 3.8 / pandas 1.5 / numpy 1.23 to **Python
3.13 / pandas 3 / numpy 2**, with pytest as the test runner. Prove the port
changed no builder output.

The proof works like this:
1. Before switching, record what the current builder produces, using the
   **old** interpreter.
2. After switching, assert that the new interpreter produces the same thing.

These are major-version upgrades, so "it imports" isn't enough.

## Read first

- `planning/impl/00_README.md`, especially the **Environment** section. It
  lists the pandas 3 behavior changes you'll hit.
- `MlbBuildModelData.py` and `MlbPitchPredictionModel.py`

---

## Phase A: record reference output with the OLD stack (do this first)

0. Check that `data/mlb_pitch_data_test.db` is the **clean** fixture: 84,873
   pitches, with no duplicate `(g_id_int, ab_ind, p_ind)`. If it's missing or
   different, regenerate it with `python3 utils/make_test_db.py`. That script
   is stdlib-only and needs `data/mlb_pitch_data_2023.db` and `_2024.db`.
1. Create `tests/__init__.py` (empty) and `tests/fixtures/reference/`.
2. Create `tests/helpers.py`. It **must stay valid Python 3.8**, because
   Phase A runs it under 3.8: no `list[str]`, no `X | None`, no match
   statements.

   ```python
   import os
   from MlbBuildModelData import BuildMlbModelData

   REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
   DATA_DIR = os.path.join(REPO_ROOT, "data")
   REFERENCE_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "reference")
   TEST_DB_NAME = "mlb_pitch_data_test"
   # Most pitches thrown / faced in the fixture db; both appear in both
   # seasons, so the season-decay reference actually decays something.
   GOLDEN_PITCHER_ID = 657277   # 490 pitches
   GOLDEN_BATTER_ID = 668804    # 440 pitches

   def make_test_builder(**kwargs):
       """BuildMlbModelData wired to the small fixture db."""
       return BuildMlbModelData(data_as_type="db", load_dir=DATA_DIR,
                                load_name=TEST_DB_NAME, **kwargs)
   ```

3. Create `tests/make_reference.py` (also valid Python 3.8). It inserts
   `REPO_ROOT` into `sys.path`, then writes three CSVs with
   `to_csv(path, index=False, float_format="%.17g")`:
   - `pitcher.csv`: `make_test_builder().build_pitcher_data(GOLDEN_PITCHER_ID)`
   - `batter.csv`: `make_test_builder().build_batter_data(GOLDEN_BATTER_ID)`
   - `pitcher_season_decay.csv`: the same as `pitcher.csv`, but with
     `make_test_builder(mix_decay_mode="season")`

   The files are CSV, not pickle, because pandas 3 can't reliably read
   pickles written by pandas 1.5.
4. Run it with the **old** stack. It's recreated on demand with uv; this was
   verified to work on 2026-09-25:
   ```
   uv run --no-project --python 3.8 --with pandas==1.5.0 --with numpy==1.23.3 \
       python tests/make_reference.py
   ```
   Expect `pitcher.csv` to have 490 rows and `batter.csv` 440. **If the row
   counts differ, stop.** It means the fixture has duplicates again.
5. `.gitignore` ignores `*.csv`, so add these lines to keep the fixtures
   committable:
   ```
   !tests/fixtures/**/*.csv
   .venv/
   ```
   Check with `git status --short tests/`. The three CSVs must show up.

**Don't edit any root `.py` file before Phase A is done.** The references
must reflect the untouched code.

## Phase B: create the Python 3.13 environment

1. Check `uv --version` (0.10.9 is at `~/.local/bin/uv`) and
   `uv python list --only-installed` (it should include 3.13.12). If 3.13 is
   missing, run `uv python install 3.13`.
2. Add a `.gitattributes` containing `* text=auto eol=lf`. The repo was
   previously edited from Windows, and this keeps line endings LF in WSL.
3. Create `pyproject.toml`:

   ```toml
   [project]
   name = "mlb-modeling"
   version = "0.1.0"
   requires-python = ">=3.13,<3.14"
   dependencies = [
       "pandas>=3.0",
       "numpy>=2.3",
       "scikit-learn>=1.8",
       "xgboost>=3.0",
       "catboost>=1.2.10",
       "pyarrow>=21",
       "requests>=2.32",
   ]

   [dependency-groups]
   dev = ["pytest>=9"]

   [tool.uv]
   package = false

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   pythonpath = ["."]
   addopts = "-ra -m 'not slow'"
   markers = ["slow: reads full-season databases; run with `uv run pytest -m slow`"]
   filterwarnings = [
       "error::FutureWarning",
       "error::pandas.errors.ChainedAssignmentError",
   ]
   ```

4. Run `uv sync` (this creates `.venv/` and `uv.lock`). Then run
   `uv run python -c "import sys, pandas, numpy, sklearn, xgboost, catboost, pyarrow; print(sys.version, pandas.__version__, numpy.__version__)"`.
   If **catboost** (or anything else) fails to install on 3.13, **stop and
   report it**. Don't lower `requires-python` on your own.
5. In `run_season_range.sh`, change `python run_season_scrape.py` to
   `uv run python run_season_scrape.py`.

The root-level `testMlbApiScraper.py` is an ad-hoc script, not a test.
`testpaths = ["tests"]` keeps pytest from collecting it. Leave it alone.

## Phase C: port the code

1. `uv run python -c "import MlbApiScraper, MlbBuildModelData, MlbPitchPredictionModel"`
2. Write the Phase D reference test, run it, and fix whatever differs. Known
   spots to check (confirm each; fix only what actually breaks or differs):

   | where | pandas 3 / numpy 2 change | expected action |
   |---|---|---|
   | `MlbBuildModelData._build_pitch_mix_features`: `pd.get_dummies(df["type"], prefix="type")` | returns `bool` now; the `cumsum() - type_dummies` arithmetic runs on bool | pass `dtype=float` |
   | `MlbPitchPredictionModel._prepare_features_onehot`: `pd.get_dummies(...)` | `bool` dummies | fine (bool counts as numeric); verify |
   | `MlbPitchPredictionModel._prepare_features_categorical`: `.astype(str).fillna("NA")` | `astype(str)` now keeps NaN, so missing values become `"NA"` instead of `"nan"` | no code change needed. Note it in the report (the CatBoost missing-category label changes; model quality doesn't) |
   | anything flagged by `ChainedAssignmentError` / `FutureWarning` | Copy-on-Write, deprecations | rewrite with `.loc` / the non-deprecated API |
   | `MlbApiScraper.py` | not exercised by tests (it needs the network) | static read-through for removed APIs (`DataFrame.append`, `applymap`, `np.NaN`, `fillna(method=)`). **Don't run a scrape** |

3. Every fix must keep the Phase A references matching. If a difference
   can't be removed (e.g. a legitimately different float rounding in a
   library), document the column and the size of the difference, and widen
   the tolerance **for that column only**.

## Phase D: pytest harness and first tests

1. **`tests/conftest.py`** (shared fixtures; later WPs add to it):

   ```python
   import pytest
   from tests.helpers import make_test_builder, GOLDEN_PITCHER_ID, GOLDEN_BATTER_ID

   @pytest.fixture(scope="session")
   def test_builder():
       """Shared builder on the fixture db. Read-only: tests that modify the
       builder's raw tables must use make_builder instead."""
       return make_test_builder()

   @pytest.fixture
   def make_builder():
       """Factory for a fresh, independently-modifiable builder."""
       return make_test_builder
   ```

2. **`tests/reference.py`**: a helper
   `assert_matches_reference(new_df, ref_csv_path, skip_columns=())`:
   - Every reference column exists in `new_df`. Extra columns in `new_df`
     are **allowed**, since later WPs add features.
   - The row counts are equal. Compare rows positionally (both frames are
     sorted the same way by the builder).
   - Numeric reference columns: `np.allclose(to_numeric(new), ref,
     rtol=1e-9, atol=0, equal_nan=True)`.
   - Other columns: compare as strings, with NaN/None mapped to `""` on both
     sides. If a column differs only in representation (e.g. timestamp
     formatting), normalize both sides and add a comment explaining it.
   - On failure, the message lists the mismatching columns and, for each,
     the first mismatching row and its values.

3. **`tests/test_reference.py`**: parametrized over the three references.
   Rebuild each frame with the new interpreter and call
   `assert_matches_reference`. Define a module-level constant
   `BATTER_COLUMNS_EXPECTED_TO_CHANGE: list[str] = []` and pass it as
   `skip_columns` for the batter case. WP3 fills it in, because it
   deliberately fixes a batter-side bug.

4. **`tests/test_smoke.py`**:
   - Importing the three root modules succeeds.
   - `@pytest.mark.parametrize("classifier", ["random_forest", "xgboost", "catboost"])`:
     `PitchPredictionModel(classifier=..., n_estimators=20).fit(pitcher frame).evaluate()`
     returns an `accuracy` in [0, 1]. This exercises xgboost 3 and catboost
     on 3.13.

## Acceptance

- `uv run pytest` passes: 3 reference tests, 1 import test and 3 smoke
  tests.
- **No warning filters loosened**, except targeted `ignore` entries for
  third-party (non-pandas) warnings, each with a comment naming the source.
- `git status` shows `pyproject.toml`, `uv.lock`, the `.gitignore` change,
  `tests/` (including the three CSVs) and any ported `.py` files. `.venv/`
  doesn't appear.

## Report back

- `GOLDEN_BATTER_ID` and the reference shapes
- resolved versions (`uv pip list`)
- every code change made for the port, with a one-line reason each
- any reference column that needed special tolerance or normalization,
  and why
