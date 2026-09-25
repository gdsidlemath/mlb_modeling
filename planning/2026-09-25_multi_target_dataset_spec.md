# Spec: one modular dataset for six pitch-level predictions

Goal: one materialized table, one row per pitch, that serves all six tasks
now, and later serves them as a cascade:

```
context ─► (1) pitch type ─► (2) arrival speed ─► (3) location ─► (4) swing? ─► (5) contact | swing ─► (6) pitch outcome
```

Each task takes the table, applies a row filter, picks a target, and picks a
**feature tier**. The table holds everything; a task registry decides what
each task is allowed to see.

Numbers below come from `data/mlb_pitch_data_2024.db` (709,512 pitches).

> **Implementation plans:** [impl/00_README.md](impl/00_README.md). They
> were written after scanning all 11 season DBs and supersede this spec
> wherever the two differ: extra codes I/Q/R/Z, extra types ""/AB/IN/PO,
> exact feature names, and tier rules.

## Decisions (2026-09-25)

| question | decision | where it lands |
|---|---|---|
| Foul tips | Grouped with `swinging_strike` for the outcome label. The mapping is a swappable constructor argument, so this can be changed later | §2 `OUTCOME_CODE_MAP` |
| Location target | Categorical: statsapi `zone`. Raw `pX`/`pZ` are **not** targets | §2, §3 |
| Pitch type granularity | Fine-grained `type` stays the target. A swappable `PITCH_FAMILY_MAP` adds a `y_pitch_family` alternative | §2 |
| Career history window | Use all scraped data (2015 onward) | §1 |

**About "14 zones":** statsapi never uses zone 10. There are **13 classes**:
1–9 inside the strike zone (3×3 grid) and 11–14 for the four outer
quadrants. Both 2015 and 2024 contain only those 13 values plus a few NaN
(285 in 2024, 1,754 in 2015).

---

## 1. Change the row set: league-wide rather than per pitcher

**Current:** `build_pitcher_data(pitcher_id)` builds one pitcher's pitch
sequence, and every history feature is grouped implicitly within that pitcher.
Batter history comes only from pitches this pitcher threw to the batter
(`*_vs_batter`).

**Problem:** tasks 4–6 depend mostly on the batter: how often they swing,
chase and whiff. A per-pitcher frame can't see a batter's history against the
rest of the league. Pitch-type/speed/location also benefit from a single
table.

**Change:** add `build_league_data(date_from=None, date_until=None)`, which
returns every pitch with **both** pitcher-side and batter-side history
features on the same row. Per-pitcher models still work: filter
`pitcher_id == X`.

Required refactor in `MlbBuildModelData`:

- Every history helper (`_group_cumulative_mix`, `_last_two_innings_mix`,
  `_group_decayed_mix_*`, `_unbounded_group_mix`) assumes a single-player
  frame. Prepend the actor id to every group key:
  - career: `["_career_key"]` → `["pitcher_id"]` (or `["batter_id"]`)
  - game: `["g_id_int"]` → `["pitcher_id", "g_id_int"]`
  - by_count: `["count_key"]` → `["pitcher_id", "count_key"]`
  - vs_opponent: `[opponent_col]` → `["pitcher_id", "batter_id"]`
  - `_last_two_innings_mix`: `game_col` becomes a list of keys.
- Run the feature builder twice, once for the pitcher side and once for the
  batter side, and prefix the columns (`p_` / `b_`) so they don't collide.
- The `prev_*` shifts currently use `groupby("g_id_int")`. That is correct
  only in a single-pitcher frame. League-wide they must be
  `groupby(["pitcher_id", "g_id_int"])`.
- **Multi-season loading (decided: use everything):** `_load_raw_tables`
  reads a single `.db`, so "career" currently means "this season only".
  Accept a list of season DBs, or a glob such as `mlb_pitch_data_20??.db`
  that excludes `_test`, and concat all of them (2015–2025). Career,
  by_count and vs_opponent features then cover each player's full scraped
  history. Every row is still computed only from strictly earlier pitches, so
  using more history adds no leakage. The only rows that start cold are
  players' first pitches in 2015 and the real debuts after that.
  - **Size:** about 7.5M pitches across 11 seasons (2020 is short). The
    vectorized cumsum/groupby helpers handle that fine. The `"day"` decay mode
    runs a Python-level `groupby().apply(ewm)`, which will be slow with
    league-wide group keys. Vectorize it or build it one season at a time
    before using it at this scale.
  - **Stale history:** with all history available, a plain average weights a
    2015 pitch the same as last week's. The existing `mix_decay_mode`
    (`"season"`/`"day"`) is the fix, and matters more now. Evaluate it again
    on the league-wide table instead of keeping the per-pitcher conclusion.
  - **Pitch-type taxonomy drift:** statsapi introduced `ST` (sweeper) and
    `SV` (slurve) partway through the range, so the same pitcher's pitch can
    be `SL` in older seasons and `ST` in newer ones. Fine-grained career
    mixes will split that history across two columns. The family-level mixes
    (§4) don't have this problem, so compute pitch-type history at **both**
    granularities.
  - **Save each season to its own file:** compute features over the full
    concatenated history, then write one parquet file per season
    (`data/model_pitches_<season>.parquet`). A later incremental update only
    has to rewrite the newest season, as long as the running career state from
    the previous season is kept.
- **Materialize:** a league-wide build is expensive, so write it once per
  season to `data/model_pitches_<season>.parquet` (or a `model_pitches` table)
  and load that, rather than rebuilding on every model fit.

Join key for everything downstream (including later out-of-fold cascade
predictions): `(g_id_int, ab_ind, p_ind)`.

---

## 2. Targets: add explicit, derived label columns

The raw columns stay as they are. Add derived target columns with a `y_`
prefix so it's always clear what's a label:

| task | column(s) | kind | source / definition |
|---|---|---|---|
| 1. type | `y_pitch_type` | multiclass | `type`, with non-competitive types dropped (see filters). **Primary target** |
| 1. (alt) | `y_pitch_family` | multiclass | `PITCH_FAMILY_MAP[type]`, see below |
| 2. speed | `y_end_speed` | regression | `endSpeed`, the speed at the plate ("arrival"). Keep `startSpeed` available as an alternative target |
| 3. location | `y_zone` | multiclass (13) | `zone` as an int category: 1–9 inside the strike zone, 11–14 outside. Stored as a string/categorical so no model reads it as an ordered number |
| 4. swing | `y_swing` | binary | from `code`, see mapping |
| 5. contact | `y_contact` | binary, **NaN when no swing** | from `code`, see mapping |
| 6. outcome | `y_outcome` | multiclass | from `code` + at-bat `eventType`, see mapping |
| 6. (alt) | `y_run_value` | regression | `delta_pitcher_run_exp` (Savant, about 99.9% coverage) |

### Swappable mappings

All three code/type → label mappings are **module-level default dicts that
can be overridden per build**. The builder takes them as constructor
arguments, so an experiment can pass its own mapping without editing the
class:

```python
BuildMlbModelData(...,
                  swing_code_map=None,     # defaults to SWING_CODE_MAP
                  outcome_code_map=None,   # defaults to OUTCOME_CODE_MAP
                  pitch_family_map=None)   # defaults to PITCH_FAMILY_MAP
```

- Each mapping is validated when the table is built. Any `code`/`type` in the
  data that isn't a key (and isn't in the global-exclusion list) raises an
  error listing the missing keys. A new statsapi code must never silently
  become NaN.
- The build records which mappings it used. Write a hash of each mapping (or
  the dict itself as JSON) next to the parquet file, so a saved table always
  says which foul-tip and family choices produced its labels.
- The labels also feed history features: batter whiff%, outcome mixes and
  family mixes are all built from `y_*`. **Changing a mapping means
  rebuilding the table**, not just relabeling a column. A second saved table
  per mapping variant is fine.

### `code` → swing / contact / outcome mapping

`SWING_CODE_MAP` (code → `(y_swing, y_contact)`) and `OUTCOME_CODE_MAP`
(code → outcome class, or `"IN_PLAY"` meaning "resolve from `eventType`") are
two separate dicts. That keeps the foul-tip outcome choice independent of the
contact choice.

| code | call | n (2024) | `y_swing` | `y_contact` | `y_outcome` |
|---|---|---|---|---|---|
| B | Ball | 235,786 | 0 | NaN | `ball` |
| *B | Ball In Dirt | 15,023 | 0 | NaN | `ball` |
| C | Called Strike | 116,208 | 0 | NaN | `called_strike` |
| H | Hit By Pitch | 2,020 | 0 | NaN | `hbp` |
| P | Pitchout | 54 | excluded | excluded | excluded |
| S | Swinging Strike | 74,769 | 1 | 0 | `swinging_strike` |
| W | Swinging Strike (Blocked) | 3,935 | 1 | 0 | `swinging_strike` |
| M | Missed Bunt | 202 | 1 (bunt) | 0 | `swinging_strike` |
| T / O | Foul Tip | 7,368 | 1 | **1** | `swinging_strike` (**see note**) |
| F | Foul | 128,707 | 1 | 1 | `foul` |
| L | Foul Bunt | 1,233 | 1 (bunt) | 1 | `foul` |
| X | In play, out(s) | 80,995 | 1 | 1 | `in_play_*` via `eventType` |
| D | In play, no out | 27,509 | 1 | 1 | `in_play_*` via `eventType` |
| E | In play, run(s) | 15,703 | 1 | 1 | `in_play_*` via `eventType` |

**Foul tips (decided):** `OUTCOME_CODE_MAP` maps `T` and `O` to
`swinging_strike`, because for the count a foul tip behaves like a swinging
strike: it's always a strike, and strike three if caught with two strikes.
`SWING_CODE_MAP` keeps `y_contact=1`, because the bat did touch the ball. To
change either choice, pass an edited copy of that dict. For example:
`{**OUTCOME_CODE_MAP, "T": "foul", "O": "foul"}`.

**In-play split** (the pitch that ends the at-bat carries `abs.eventType`):

- `in_play_out`: field_out, force_out, grounded_into_double_play, double_play,
  fielders_choice_out, sac_fly, sac_bunt, sac_fly_double_play, triple_play
- `in_play_single`: single
- `in_play_xbh`: double, triple
- `in_play_hr`: home_run
- `in_play_other` (or fold into out): field_error, fielders_choice,
  catcher_interf

This gives 9 outcome classes: ball, called_strike, swinging_strike, foul, hbp,
in_play_out, in_play_single, in_play_xbh, in_play_hr. The labels nest:
P(swing) × P(contact | swing) × P(in-play | contact) is consistent with the
outcome distribution, which will matter when the cascade is stitched together.

Also add `is_bunt` = code in (L, M) or `trajectory` in (bunt_grounder,
bunt_popup, bunt_line_drive), about 2.6k pitches. Bunts are strategic rather
than swing decisions. By default, exclude them from swing and contact (this is
a task filter, and the rows stay in the table).

### `PITCH_FAMILY_MAP` (default; swappable)

| family | types |
|---|---|
| `fastball` | FF, SI, FC |
| `breaking` | SL, ST, SV, CU, KC, CS |
| `offspeed` | CH, FS, FO, SC |
| `knuckle` | KN |

- FC could reasonably go under `breaking`, and some analyses split out a
  fourth `cutter` group. This is exactly the kind of choice that should be
  tested by swapping the dict.
- The family is used in three places:
  1. the `y_pitch_family` target
  2. family-level history mixes (§4), which are robust to the SL/ST taxonomy
     change
  3. batter swing/contact rates by family (§4)

  Fine-grained `type` stays the primary target and the primary mix
  granularity.

---

## 3. Split `RESULT_COLUMNS` into tiers, so the cascade can "unlock" columns

Currently every post-release column is one flat ban list. For the cascade,
later stages have to be allowed to see earlier stages' targets. Replace the
list with ordered tiers:

| tier | columns | first usable as a feature by |
|---|---|---|
| `T0_CONTEXT` | count, outs, bases, score, inning, weather, handedness, all history/mix features, `prev_*`, rest days, times-through-order | all tasks |
| `T1_TYPE` | `type` (+ derived pitch family) | speed, location, swing, contact, outcome |
| `T2_SPEED` | `endSpeed`, `startSpeed` | location, swing, contact, outcome |
| `T3_LOCATION` | `zone` (categorical), plus features derived only from zone: `in_zone` (1–9), `zone_row` (high/mid/low), `zone_col` (in/mid/away, flipped for batter hand), `zone_outer` (11–14 quadrant) | swing, contact, outcome |
| `POST_PITCH_PHYSICS` | `pX`, `pZ`, `x`, `y` (exact plate location), spin, break/pfx, release point/velocities/accel, `plateTime`, `extension`, `arm_angle`, `typeConfidence` | never (the cascade doesn't predict these. A later "movement" stage could unlock them) |
| `POST_SWING` | `code`, `call`, bat tracking, launch/hit data, xStats, win/run-exp, `y_*` | never |
| `HINDSIGHT` | `*_days_until_next_game` | never |

**Why `pX`/`pZ` moved to never-usable:** location is predicted as a zone,
so at cascade time the swing/contact/outcome models will only receive a
predicted zone. If they train on the exact `pX`/`pZ`, they learn from
information they won't have when making predictions. So the location tier
contains only zone and columns derived from zone. Past `pX`/`pZ` values are
still fine inside **history** features (tier T0), because those come from
earlier pitches.

Each task declares `max_tier`, and the feature list is all columns up to and
including that tier. This replaces the `RESULT_COLUMNS`/`LABEL_COLUMNS` pair.
The two lists have already drifted apart; put a single source of truth in
`MlbBuildModelData` and import it in the model.

**Teacher forcing:** the table stores true upstream values, so downstream
models initially train on true type/speed/location. That's fine for building
each model in isolation. At cascade time, upstream inputs will be predictions,
and a model trained only on true values will be overconfident. Later, add
out-of-fold upstream predictions as extra columns (`pred_type_*`,
`pred_end_speed`, ...) joined on the pitch key. No schema change is needed
now beyond keeping the key stable.

---

## 4. New history features the new targets need

Today every history feature is a **pitch-type mix**. Speed, location, swing,
contact and outcome need their own history.

**Generalize the helper first.** `_group_cumulative_mix` already computes
"cumulative mean of arbitrary columns over strictly-prior rows in a group".
Rename it `_group_cumulative_mean(df, value_cols, group_cols, suffix,
weight_cols=None)`. The `weight_cols` argument handles conditional means, for
example "mean speed on *fastballs* only" = cumsum(speed × is_FF) /
cumsum(is_FF), or "chase rate" = cumsum(swing × out_of_zone) /
cumsum(out_of_zone). Route the decay variants through the same signature. Then
every family below is config rather than new code.

### Pitcher side (`p_` prefix)

| feature family | for task | windows |
|---|---|---|
| pitch-type mix (existing) | type | this_inning, last_2_innings, game, by_count, vs_batter, career |
| pitch-**family** mix (same windows, via `PITCH_FAMILY_MAP`) | type | same as above |
| mean `endSpeed` / `startSpeed` **per pitch type** | speed | game, career (+ recent-N games) |
| in-game velo delta: game-to-date mean − career mean, per type | speed (fatigue) | game |
| **zone mix** (13-way distribution) per pitch type, split by batter hand | location | career, by_count |
| zone mix per pitch type in this game | location | game |
| in-zone% per type | location, swing | career, by_count |
| induced swing%, chase%, whiff% per type | swing, contact | career |
| outcome-class mix | outcome | career, by_count |

### Batter side (`b_` prefix, new)

| feature family | for task | windows |
|---|---|---|
| swing% overall / in-zone / out-of-zone (chase) | swing | career, by_count, game |
| swing% by pitch family (FB / breaking / offspeed) | swing | career |
| contact% given swing: overall, in-zone, out-of-zone, by pitch family | contact | career |
| outcome-class mix | outcome | career, by_count |
| batter zone mix seen / swing% by zone | location, swing | career |
| mean `strikeZoneTop` / `strikeZoneBottom` | location, swing | career |
| pitch-type mix *seen* (existing `build_batter_data` logic) | type | career, vs_pitcher |

### Within-at-bat sequence (new)

The existing `prev_*` columns shift within the **game**, so on the first pitch
of an at-bat they describe the pitcher's last pitch to the *previous* batter.
Keep them, and add at-bat–scoped versions (`groupby([... , "g_id_int",
"ab_ind"])`):

- `prev_ab_type`, `prev_ab_family`, `prev_ab_end_speed`, `prev_ab_zone`,
  `prev_ab_swing`, `prev_ab_contact`, `prev_ab_outcome` (NaN on the first
  pitch of the at-bat). The previous pitch's exact `pX`/`pZ` would be
  allowed, since it's in the past. Use the zone anyway for consistency with
  the target, and add `prev_ab_px`/`prev_ab_pz` later only if they
  measurably help.
- `pitch_num_in_ab`: this is `p_ind`, which is currently thrown away as an ID
  column. Expose it as a feature under a new name.
- `n_fouls_in_ab`, `n_pitch_types_seen_in_ab`

### Fix these alongside the history work

- **`strikeZoneTop` / `strikeZoneBottom`** are measured per pitch (321k
  distinct values in 2024) and currently get into the model as features, since
  they aren't in `RESULT_COLUMNS`. Stance at the moment of the pitch is
  borderline leakage. Drop them as current-row features, and use the
  batter's *prior* mean instead. The zone target already comes from
  statsapi, so nothing else needs them.
- `in_zone` and the other zone-derived columns come from the current pitch's
  zone, so they belong in tier T3 and not T0.
- `prev_zone` is currently one-hot encoded as a raw int in
  `_prepare_features_onehot`. Keep treating it as a 13-way categorical (and
  do the same for `prev_ab_zone`).

---

## 5. Per-task row filters

Global filters (dropped from the table entirely):

- `type` in {`FA`, `EP`, `CS`} (position players pitching and eephus: 2024
  mean endSpeed of 47–63 mph) plus `UN`, `PO` and `IN` if present, and
  `code == "P"` (pitchout). Keep `KN` because it's a real pitcher's pitch.

Task-level filters (the rows stay in the table and the registry applies them):

| task | rows |
|---|---|
| type | `y_pitch_type` notna (drops 285 untyped) |
| speed | `y_end_speed` notna (99.96%) |
| location | `y_zone` notna (drops 285 in 2024) |
| swing | all, minus `is_bunt`, minus intentional-walk at-bats |
| contact | `y_swing == 1`, minus `is_bunt` |
| outcome | all |

---

## 6. Task registry (the "modular" part)

A small declarative spec, one entry per task, e.g. in a new
`MlbTasks.py`:

```python
@dataclass(frozen=True)
class TaskSpec:
    name: str                 # "pitch_type", "pitch_family", "end_speed", "location", "swing", "contact", "outcome"
    targets: list[str]        # ["y_pitch_type"] / ["y_zone"] / ...
    kind: str                 # "multiclass" | "binary" | "regression"
    max_tier: str             # "T0_CONTEXT" | "T1_TYPE" | "T2_SPEED" | "T3_LOCATION"
    row_filter: Callable[[pd.DataFrame], pd.Series]
    eval_metrics: list[str]   # accuracy/logloss, MAE/RMSE, AUC/Brier, ...
```

| task | kind | max_tier | baseline to beat |
|---|---|---|---|
| pitch_type | multiclass | T0 | pitcher career mix / Markov on prev type |
| pitch_family (alt) | multiclass | T0 | pitcher career family mix |
| end_speed | regression | T1 | pitcher career mean for that type |
| location | multiclass (13 zones) | T2 | pitcher career zone mix for type × batter hand |
| swing | binary | T3 | batter career swing% (zone-split) |
| contact | binary | T3 | batter career contact% |
| outcome | multiclass | T3 | count-conditional league outcome mix |

---

## 7. Knock-on changes in `MlbPitchPredictionModel.py` (after the dataset)

These are not part of the dataset work, but listed so the scope is visible:

- Rename it to something like `PitchTaskModel(task: TaskSpec, ...)`. The
  current code is hard-wired to `TARGET_COLUMN = "type"` and classification.
- Regression path (speed only): `RandomForestRegressor` / `XGBRegressor` /
  `CatBoostRegressor`. Location is now a 13-class classifier, so it reuses the
  existing multiclass path. The tuning loops currently
  score on `accuracy_score`. Change them to take a task-specific score
  (logloss for classifiers, which also suits probability outputs better than
  accuracy; RMSE for regressors).
- For swing/contact/outcome, report probabilities (`predict_proba`),
  calibration (Brier/log loss) and AUC, rather than accuracy.
- `_prepare_features_onehot` hard-codes the categorical list. Drive it from
  the tier/categorical metadata instead, and add `prev_ab_*` categoricals.
  Once T1 is unlocked, `type` itself becomes a categorical *feature*.
- A chronological split still applies. League-wide, split by `game_date`,
  not by row position within a pitcher.

---

## Suggested implementation order

1. `SWING_CODE_MAP` / `OUTCOME_CODE_MAP` / `PITCH_FAMILY_MAP` as
   overridable constructor arguments with validation, then the `y_*` label
   columns, `is_bunt` and global filters. These are cheap, and task 4–6
   labels exist after this step.
2. Column tiers, which replace `RESULT_COLUMNS`/`LABEL_COLUMNS`.
3. Generalize `_group_cumulative_mean`, add an actor id to the group keys, and
   add `build_league_data`. Check that it matches `build_pitcher_data` output
   for one pitcher, which is a good regression test.
4. Multi-season loading and materialization to parquet.
5. New feature families: speed/location history, then batter swing/contact
   history, then within-at-bat features.
6. Task registry, then generalize the model class.

## Remaining open questions

- Default `PITCH_FAMILY_MAP` placement of FC (fastball vs breaking vs its
  own group). Settle it by testing different dicts; it doesn't block anything.
- Decay mode for all-history career features (`None` / `"season"` /
  `"day"`). Settle it empirically once the league-wide table exists.
