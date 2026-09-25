# WP4: League-wide, multi-season, chunked build

**Depends on:** WP1 (`MlbLabels.py`), WP2 (`MlbColumns.py`), WP3 (refactored
helpers). **Edits:** `MlbBuildModelData.py`. **Creates:**
`build_model_table.py` (CLI script), `tests/test_league_build.py`,
`tests/test_leakage.py`.

This is the most intricate WP. Read it fully before starting.

## Goal

Produce one table containing every pitch, with pitcher-side (`p_*`) and
batter-side (`b_*`) history features, `y_*` labels, and `cur_*` columns.
History spans all loaded seasons. Output is one file per season.

A full 11-season table (about 7.9M rows × 300+ columns) doesn't fit in memory
as float64 (roughly 18 GB+), so the writer computes features **in chunks of
players**. This works because each side's features depend only on that
player's own pitches. The writer then assembles and writes **one season at a
time**.

## Read first

`MlbBuildModelData.py` (after WP3), `MlbLabels.py`, `MlbColumns.py`,
`planning/impl/00_README.md`.

## Changes to `BuildMlbModelData`

### Constructor

- `load_name` may be a `str` (current behavior) **or a list of str**. With a
  list, `_load_raw_tables` loads each DB/CSV set and `pd.concat`s each table.
  Keep the existing single-name behavior working (the golden tests cover it).
  Open DB connections inside `_load_raw_tables` rather than holding one
  `self.load_db_cnx`, but keep the attribute for the single-name case in case
  external code uses it.
- New kwargs, stored as given (`None` → `MlbLabels` default):
  `swing_code_map`, `outcome_code_map`, `event_outcome_map`,
  `pitch_family_map`.

### Class-level registries (empty here, filled by WP5a/b/c)

```python
# Method names called by _side_features for each side. Each method has the
# signature (self, sub, self_col, opponent_col) -> DataFrame of NEW columns
# (unprefixed, index == sub.index), computed from strictly-prior rows only.
SIDE_FEATURE_FAMILIES = {"pitcher": [], "batter": []}

# Method names called by _ab_features. Signature (self, frame) -> DataFrame
# of new columns, index == frame.index. Run per season on the assembled
# frame; may only look at earlier pitches in the SAME at-bat.
AB_FEATURE_FAMILIES = []
```

### `_league_pitch_frame(self)`

1. `_load_raw_tables()`; drop the `index` column from pitches if present.
2. `pitches` ⋈ `abs` on `(g_id_int, ab_ind)`, taking the same `abs` columns
   `_pitch_sequence` takes **plus `eventType`**. Then ⋈ `games` on
   `g_id_int`, taking the same `games` columns **plus** `stadium`,
   `ht_win_pct`, `at_win_pct`, `ht_gms_plyd`, `at_gms_plyd`. Convert the two
   `*_win_pct` string columns with `pd.to_numeric(errors="coerce")`.
3. Add `season = game_date // 10000`.
4. Check that `(g_id_int, ab_ind, p_ind)` is unique. If not, raise
   `ValueError` with the duplicate count and a sample. **Don't dedupe
   silently.** (Duplicates in real data mean a scrape bug; see
   `docs/scraper_and_schema.md`.)
5. `MlbLabels.apply_global_filters`, then `MlbLabels.add_labels(...)` with
   this instance's maps.
6. Sort by `game_date, g_id_int, ab_ind, p_ind`, then `reset_index(drop=True)`.
7. Memory: convert these **non-key** string columns to `category`: `call`,
   `description`, `eventType`, `trajectory`, `hardness`, `location`,
   `weather_condition`, `wind_direction`, `day_night`, `halfInning`. **Don't**
   categorize `code`, `type`, `batter_stance`, `pitcher_hand` or the
   `y_*`/`cur_*` columns. They're group keys and dummy sources. Keeping them
   as plain `str` avoids having to reason about categorical-groupby
   semantics (`observed=`, unused categories) in every helper.

### `_side_features(self, sub, side)`

- `side == "pitcher"` → `self_col="pitcher_id"`, `opponent_col="batter_id"`,
  `opponent_suffix="vs_batter"`, `prefix="p_"`. For `"batter"`, the mirror
  image, with `vs_pitcher` and `b_`.
- `out = self._build_pitch_mix_features(sub, self_col, opponent_col,
  opponent_suffix, type_categories=MlbLabels.pitch_types(self.pitch_family_map))`
- Keep only the columns **not** in `sub.columns` (the new features).
- Append the output of each method named in
  `SIDE_FEATURE_FAMILIES[side]`.
- Concat, add the prefix to every column, and return (index == `sub.index`).

### `_ab_features(self, frame)`

Concat the outputs of the `AB_FEATURE_FAMILIES` methods. Return an empty
frame with `frame.index` if the list is empty.

### `build_league_frame(self, date_until=None)`: in-memory, for small data and tests

```
base = self._league_pitch_frame()
if date_until: base = base[base.game_date < int(str(date_until).replace("-", ""))]
p = self._side_features(base, "pitcher")
b = self._side_features(base, "batter")
frame = pd.concat([base, p, b], axis=1)
return pd.concat([frame, self._ab_features(frame)], axis=1)
```

The `date_until` filter must happen **before** any features are computed
(the leakage test depends on it).

### `build_league_data(self, table_name="default", out_dir="data/model_tables", seasons=None, actor_chunk_size=200)`: chunked writer

1. `base = self._league_pitch_frame()`. This is the full history. `seasons`
   (a list of ints, default = all seasons in `base`) selects only which
   seasons get **written**.
2. `table_dir = os.path.join(out_dir, table_name)`, with a temporary
   directory at `table_dir/_tmp`.
3. For each side, and for each chunk of `actor_chunk_size` sorted unique
   actor ids:
   - `sub = base[base[self_col].isin(chunk)]`. The boolean mask preserves the
     global chronological order.
   - `feats = self._side_features(sub, side)`. Downcast float64 columns to
     float32.
   - Add the key columns `g_id_int, ab_ind, p_ind, season` from `sub`.
   - For each season in `seasons` present in the chunk, write
     `_tmp/<side>/season=<YYYY>/chunk_<i>.parquet`.
   - Print a progress line per chunk: side, chunk i/n, rows, seconds.
4. For each season in `seasons`:
   - `frame = base[base.season == s]`
   - For each side, concat that season's chunk files and `merge` onto
     `frame` on the three pitch keys with `how="left", validate="one_to_one"`.
     Assert the row count is unchanged and no side-feature column is entirely
     NaN.
   - `frame = concat([frame, self._ab_features(frame)], axis=1)`
   - Write `table_dir/season=<YYYY>.parquet`.
5. Format: always parquet. pyarrow is a project dependency (WP0). Parquet
   can't store mixed-type `object` columns: before writing, cast
   `on1b/on2b/on3b` to float, and cast any remaining `object`-dtype column to
   `str`. pandas 3 keeps NaN as missing when you do this. Assert afterwards
   that no `object` column remains.
6. Write `table_dir/manifest.json` containing:
   - `table_name`, UTC `created_at`, `source` (list of load names)
   - `mix_decay_mode`, `mix_halflife_days`, `mix_season_decay`
   - `mappings` (the `MlbLabels.mapping_manifest(...)` output)
   - `actor_chunk_size`, plus the `pandas` and `pyarrow` versions
   - `seasons`: `{year: {"rows": n, "cols": m}}`
   - `git_commit`: from `git rev-parse HEAD`, or `null` on failure
7. Remove `_tmp` on success. On failure, leave it for debugging.
8. Return the list of written paths.

### Module-level loader

```python
def load_model_table(table_name="default", table_dir="data/model_tables",
                     seasons=None, columns=None):
    """Concat the per-season files of a built table (all seasons in the
    manifest if seasons is None), optionally reading only `columns`."""
```

### CLI: `build_model_table.py` (repo root)

It uses argparse and takes these arguments:
- `--dbs` (glob, default `data/mlb_pitch_data_20??.db`; never matches
  `_test`)
- `--seasons` (e.g. `2023 2024`; default all)
- `--table-name`, `--chunk-size`
- `--decay {none,season,day}`

It prints elapsed time and the output paths. Look at
`run_season_scrape.py` for the house CLI style.

## Tests

### Shared fixture: add to `tests/conftest.py`

```python
@pytest.fixture(scope="session")
def league_frame(test_builder):
    """build_league_frame() on the fixture db, built once per test session.
    Read-only: copy before modifying."""
    return test_builder.build_league_frame()
```

WP5a–WP7 reuse this fixture. Use it wherever a test just needs the league
frame. Tests that modify raw tables use the `make_builder` factory instead.

### `tests/test_league_build.py` (test DB)

1. **Pitcher equivalence.** Get a fresh builder from `make_builder()`, call
   `_load_raw_tables()`, then
   replace `_pitches_df` with `MlbLabels.apply_global_filters(_pitches_df)`
   so both paths see the same rows. Compare
   `build_pitcher_data(GOLDEN_PITCHER_ID)` with the league frame filtered to
   that `pitcher_id`, with the `p_`
   prefix stripped. On the per-player frame's feature columns that exist in
   both, values must be equal (`rtol=1e-9`). Align rows on the three pitch
   keys. Cast non-numeric columns to `object` on both sides before comparing:
   the league frame's `call` is categorical, so `p_prev_call` will be too.
2. **Batter equivalence.** The same for `build_batter_data(golden batter)`
   against the `b_` columns.
3. **Chunked equals in-memory.** Run `build_league_data` into `tmp_path`
   with `actor_chunk_size=25`, then `load_model_table`. After sorting by keys,
   it equals `build_league_frame()`: the same column set, floats within
   `rtol=1e-5` (float32 vs float64).
4. The manifest exists and has the listed keys. `mappings.sha1` is 40 hex
   characters.
5. Duplicate keys raise: `load_name=[test, test]` raises `ValueError`.
6. **Fixed dummy columns.** `p_type_<T>_career` exists for **every** type in
   `MlbLabels.pitch_types()`, even ones that are absent from the test DB.

### `tests/test_leakage.py` (the guard every later WP must keep passing)

1. **Prefix invariance.** `full = build_league_frame()` and
   `cut = build_league_frame(date_until=20240401)`. The fixture spans
   2023-09-20..2024-04-07, so this cuts inside the 2024 slice. For every row
   in `cut`
   (matched on the pitch keys), **every column** equals `full`, with NaN
   equal to NaN. A future-data leak anywhere makes this fail.
2. **Same-row perturbation.** Pick rows that are the **last pitch in the
   data for both their pitcher and their batter**. Require at least 5 such
   rows. Perturbing them can't affect any other chosen row. Run two cases,
   each on a fresh builder from the `make_builder` fixture, whose
   `_pitches_df` has been modified on those rows with `.loc`:
   - (a) change `code` (`"B"`↔`"S"`), `endSpeed` (+5), `startSpeed` (+5),
     `pX` (+1), `pZ` (+1), `zone` (to a different valid zone) and
     `launchSpeed`. Assert that, on those rows, every column with
     `MlbColumns.column_tier` in {`T0_CONTEXT`, `T1_TYPE`} is unchanged.
   - (b) change `type` to a different valid type (`"FF"`↔`"SL"`). Assert
     that every `T0_CONTEXT` column on those rows is unchanged.

## Acceptance

1. The full suite passes.
2. **One real-data run** (not a unit test):
   `uv run python build_model_table.py --dbs "data/mlb_pitch_data_202[34].db"
   --seasons 2024 --table-name wp4_check`. Report:
   - wall time
   - `base.memory_usage(deep=True).sum()` (print it inside the method behind
     a `verbose` flag)
   - peak RSS: run the command under `/usr/bin/time -v` and report "Maximum
     resident set size". Check `free -g` first. If WSL shows about 11 GB
     rather than about 31 GB, the `.wslconfig` change hasn't taken effect;
     stop and report instead of running.
   - output file size, rows × cols
   - the number of `p_`/`b_` columns

   Delete `data/model_tables/wp4_check` afterwards unless told otherwise.
3. **Don't** run the 11-season build. WP8 does that.
