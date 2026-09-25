# WP3: Actor-keyed history helpers and the last-2-innings fix

**Depends on:** WP0 (golden tests). **Edits:** `MlbBuildModelData.py`,
`tests/test_golden.py` (only the `BATTER_COLUMNS_EXPECTED_TO_CHANGE`
constant). **Creates:** `tests/test_history_helpers.py`.

## Goal

Every history helper currently assumes the frame holds **one** player, so the
player is an implicit group. WP4 needs to run them on frames with many
players. This WP makes the player (the "actor") an explicit group key,
generalizes the mix helper into a weighted cumulative mean, and fixes a bug.
**Per-player output must stay identical**, apart from the one deliberate bug
fix.

## Read first

- `MlbBuildModelData.py` in full
- `docs/model_data_builder.md` (explains the intent of each helper)

## Changes

### 1. Make the actor an explicit key in `_build_pitch_mix_features`

The method already receives `self_col` (`"pitcher_id"` or `"batter_id"`) but
never uses it. Use it:

| where | currently | change to |
|---|---|---|
| `work` columns | no actor | include `self_col` |
| career mix | `["_career_key"]` (constant 0) | `[self_col]`, and delete `_career_key` |
| game mix | `["g_id_int"]` | `[self_col, "g_id_int"]` |
| this_inning | `["g_id_int", "inning"]` | `[self_col, "g_id_int", "inning"]` |
| by_count | `["count_key"]` | `[self_col, "count_key"]` |
| opponent | `[opponent_col]` | `[self_col, opponent_col]` |
| last_2_innings | `game_col="g_id_int"` | `game_cols=[self_col, "g_id_int"]` (see #3) |
| `pitch_num_in_game` | `groupby("g_id_int")` | `groupby([self_col, "g_id_int"])` |
| `prev_*` shifts | `groupby("g_id_int")` | `groupby([self_col, "g_id_int"])` |

In a single-player frame `self_col` is constant, so the results are
unchanged. The golden test proves it.

### 2. Generalize the mix helper into `_group_cumulative_mean`

Add a static method:

```python
@staticmethod
def _group_cumulative_mean(df, value_cols, group_cols, suffix, weight=None):
    """Mean of value_cols over strictly-prior rows in each group, optionally
    weighted (e.g. weight = is_fastball gives "mean over prior fastballs
    only"). Rows whose value is NaN contribute nothing to that column.
    Returns (mean, n_obs): mean columns are f"{c}_{suffix}", NaN wherever
    the prior weighted count is 0; n_obs is the prior count of rows with
    weight > 0 (ignoring value NaNs)."""
```

Algorithm, per value column `c`, where `w` = `weight` (a Series aligned to
df, default all 1.0) and `g` = `df.groupby(group_cols)`:

```
w_eff  = w * df[c].notna()
num    = df[c].fillna(0) * w_eff
cum_num_before = g-cumsum(num)   - num
cum_w_before   = g-cumsum(w_eff) - w_eff
mean   = cum_num_before / cum_w_before.where(cum_w_before > 0)
n_obs  = g-cumsum(w > 0) - (w > 0)
```

Compute the cumsums for all columns at once:
`pd.DataFrame(...).groupby([df[k] for k in group_cols]).cumsum()`.

Then rewrite `_group_cumulative_mix` as a thin wrapper, so the output stays
bit-identical:

```python
mean, n_obs = _group_cumulative_mean(df, type_cols, group_cols, suffix)
return mean, n_obs
```

The golden tests must pass with `rtol=1e-9`. If floating-point differences
appear because the dummies are now cast to float, that tolerance absorbs them.
Don't loosen it.

**Group keys that can be NaN.** pandas 1.5 drops NaN-keyed groups. Inside
`_group_cumulative_mean`, fill NaN in any **object-dtype** group column with
`"NA"` on a temporary copy. Numeric ids are never NaN; leave those alone.

### 3. Fix `_last_two_innings_mix` (real bug, batter side)

It's meant to mix the current inning (partial) plus the inning before. It
works by subtracting "cumulative totals through inning `cur - 2`", found with
an **exact** merge on `inning == cur - 2`. When the actor has no pitches in
inning `cur - 2`, the merge finds nothing, `fillna(0)` subtracts nothing, and
the result silently becomes the **whole game so far**. Pitchers pitch in
consecutive innings, so it rarely matters for them. Batters bat every 2–3
innings, so on the batter side it's wrong most of the time.

Fix: change the signature to `(df, type_cols, game_cols, inning_col="inning")`
and look up "cumulative totals through the **latest inning ≤ cur − 2**"
instead of exactly `cur − 2`. Use `pd.merge_asof(..., on=inning_col,
by=game_cols, direction="backward")`, which needs both sides sorted by
`inning_col`. Sort a copy, merge, then restore the original index order. Rows
with no earlier inning get 0, as now.

Then, in `tests/test_golden.py`, set:

```python
BATTER_COLUMNS_EXPECTED_TO_CHANGE = [c for c in golden_batter.columns
                                     if c.endswith("_last_2_innings")] + ["last_2_innings_n_pitches"]
```

(Write it however fits the file, but keep the intent.) The **pitcher**
golden tests must still pass unchanged. If they don't, the fix is wrong.

### 4. Optional fixed dummy categories

Add a parameter `type_categories=None` to `_build_pitch_mix_features`. When
it's given, build the dummies as
`pd.get_dummies(pd.Categorical(df["type"], categories=type_categories), prefix="type")`
with `index=df.index`, so that columns exist for types absent from this
frame. When it's `None`, keep the current behavior. WP4 passes
`MlbLabels.pitch_types(...)`.

### 5. Extract the windowed-mix block into a reusable method

Move the body that computes the six window families and their cold-start
fills into:

```python
def _windowed_mix(self, work, dummy_cols, self_col, opponent_col, opponent_suffix):
    """The six mix windows (this_inning, last_2_innings, game, by_count,
    <opponent_suffix>, career) over dummy_cols, cold-start-filled from
    career. Returns (list_of_mix_frames, n_obs_frame)."""
```

`_build_pitch_mix_features` calls it for the type dummies. WP5a will call it
again with pitch-family dummies. `work` must already hold `self_col`,
`opponent_col`, `g_id_int`, `inning`, `count_key`, `game_date`, the dummy
columns, and the decay helper column (`season`/`game_date_dt`) when needed.

## Tests (`tests/test_history_helpers.py`)

Use small hand-built frames (10–20 rows) so the expected numbers can be
checked by hand:

1. `_group_cumulative_mean` with two actors interleaved: each actor's mean
   uses only its own earlier rows, and the first row of each is NaN.
2. With `weight`: the mean over prior rows where weight = 1 only, and
   `n_obs` counts only weighted rows.
3. A NaN value in the middle is skipped, and later means ignore it.
4. An object group key containing NaN is still grouped (as "NA") rather than
   producing NaN output.
5. `_last_two_innings_mix`: a batter with pitches in innings 1, 4 and 7. On
   the inning-7 rows, the last-2-innings mix counts only earlier inning-7
   pitches (inning 6 has none), so the first inning-7 pitch has NaN mix and
   n = 0. Before the fix this test fails.
6. Two actors in one frame: the result for actor A equals running the method
   on A's rows alone (check for both `_group_cumulative_mix` and
   `_last_two_innings_mix`).

## Acceptance

- The full suite passes: pitcher golden fixtures (both decay modes)
  unchanged; batter golden unchanged apart from the listed last-2-innings
  columns.
- Report how many batter rows' `*_last_2_innings` values changed on the
  golden batter, as evidence the bug was real.
