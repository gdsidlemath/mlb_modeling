# WP0: Test harness and golden snapshots

**Depends on:** nothing. **Creates:** `tests/` only. **Don't modify** any `.py`
file at the repo root.

## Goal

The repo has no tests. Later WPs refactor `MlbBuildModelData.py`, so before
anything changes, freeze its current output as "golden" fixtures and add a test
that fails if that output changes.

## Read first

- `planning/impl/00_README.md` (environment facts, rules)
- `MlbBuildModelData.py`, specifically `build_pitcher_data`,
  `build_batter_data` and `_build_pitch_mix_features`

## Steps

1. Create `tests/__init__.py` (empty) and `tests/fixtures/` (directory).

2. Create `tests/helpers.py`:

   ```python
   import os
   from MlbBuildModelData import BuildMlbModelData

   REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
   DATA_DIR = os.path.join(REPO_ROOT, "data")
   FIXTURE_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")
   TEST_DB_NAME = "mlb_pitch_data_test"
   GOLDEN_PITCHER_ID = 666159

   def make_test_builder(**kwargs):
       """BuildMlbModelData wired to the small fixture db."""
       return BuildMlbModelData(data_as_type="db", load_dir=DATA_DIR,
                                load_name=TEST_DB_NAME, **kwargs)
   ```

   Add `GOLDEN_BATTER_ID`: query the test DB for the batter with the most
   pitches faced (`select batter_id, count(*) from abs join pitches using
   (g_id_int, ab_ind) group by batter_id order by 2 desc limit 1`) and
   hard-code that id in the constant, with a comment saying how it was chosen.

3. Create `tests/make_golden.py`, a script (not a test) that builds and
   saves:
   - `build_pitcher_data(GOLDEN_PITCHER_ID)` → `tests/fixtures/golden_pitcher.pkl`
   - `build_batter_data(GOLDEN_BATTER_ID)` → `tests/fixtures/golden_batter.pkl`
   - The same pitcher with `mix_decay_mode="season"` →
     `tests/fixtures/golden_pitcher_season_decay.pkl`

   Use `DataFrame.to_pickle`. Run it once with
   `python -m tests.make_golden`.

4. Create `tests/test_golden.py` (`unittest.TestCase`):
   - Rebuild each of the three frames. For each, assert that:
     - every golden column is still present (new columns are **allowed**)
     - row count is equal
     - `pd.testing.assert_frame_equal(new[golden.columns], golden,
       check_dtype=False, check_exact=False, rtol=1e-9)`
   - Add a module-level constant `BATTER_COLUMNS_EXPECTED_TO_CHANGE = []`.
     WP3 will fill it in, because WP3 deliberately fixes a batter-side bug.
     Drop those columns from both frames before comparing.

5. Create `tests/test_smoke.py`: `import MlbBuildModelData,
   MlbPitchPredictionModel` succeeds, and a `PitchPredictionModel(classifier=
   "random_forest", n_estimators=20).fit(golden pitcher frame).evaluate()`
   returns an accuracy between 0 and 1. This protects the existing model
   from breaking.

## Acceptance

- `python -m unittest discover -s tests -t . -v` passes: golden tests plus
  the smoke test, at least 4 tests in total.
- The three `.pkl` fixtures exist, and each is under 5 MB.

## Report back

Report the chosen `GOLDEN_BATTER_ID`, the fixture shapes (rows × cols) and the
test output.
