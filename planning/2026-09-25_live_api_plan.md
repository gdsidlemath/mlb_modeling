# Plan: 2026-09-25 - live prediction API

Continuation of workstream 4 from `2026-09-24_next_steps.md` ("Live API
design"), now fleshed out into an actual architecture after today's model-side
work gave it more to build on. Nothing below is implemented yet - this is the
design/scoping pass the original plan called for, to pick up and build from
tomorrow.

## What changed today that this plan depends on

- `MlbBuildModelData`: fixed a leakage bug (`*_days_until_next_game` was
  reachable as a feature), fixed cold-start mix columns silently reading as
  "confirmed zero" instead of "no data yet" (now falls back to career mix),
  and added optional `mix_decay_mode` (`"day"` or `"season"`) for
  recency-weighting the career-spanning mix features. Empirically mixed
  results per-pitcher (see git history/session notes) - left off by default.
- `MlbPitchPredictionModel`: fixed a null-`type`-target crash, added
  `catboost` as a third `classifier` option (native categoricals instead of
  one-hot - smaller feature space, beat XGBoost on every test pitcher), and
  added `tune_random_forest`/`tune_catboost` grid-search tuning paths
  alongside the existing `tune_xgboost`. Tuning gave a real lift for both
  (RF 33.9%→37.1%, CatBoost 30.5%→38.8% on the test pitcher).

These give the live API real model artifacts to serve, not just the stub
`build_pitcher_data` had on `master` before this branch.

## Core design: two-tier cache

The original plan's open question was "how to keep it fast (rebuilding full
history per request will be too slow)". After building the actual feature
pipeline, the expensive part is narrower than "full history": only the
career-spanning mix families (`career`, `by_count`, `vs_batter`/`vs_pitcher`)
need a pitcher's entire multi-season history. The game-scoped families
(`game`, `this_inning`, `last_2_innings`) are already bounded to a single
game by construction (~100-150 pitches).

That split gives a natural two-tier cache:

1. **Pre-game snapshot** (expensive, once per pitcher per day): run
   `build_pitcher_data(pitcher_id, date_until=today)`, but keep only the
   final cumulative state backing `career_mix`/`by_count_mix`/`vs_batter_mix`
   as of right before today's game - not the full row-by-row history.
2. **In-game incremental delta** (cheap, updated per pitch): this game's
   pitch-type counts by inning/count/batter, maintained in memory as pitches
   land. `game_mix`/`this_inning_mix`/`last_2_innings_mix` come entirely from
   this delta.

Producing a feature vector for "the next pitch about to be thrown" is
snapshot + delta, an O(1) combine - never touching the historical DataFrame
on the request path. A crash/restart mid-game only costs replaying that one
game's pitches against the cached snapshot, so the delta doesn't need durable
persistence (open question 4 below, if that assumption is wrong for the
target deployment).

### Data flow

```
daily scheduler -> fetch today's probable starters
                 -> for each: build_pitcher_data(date_until=today) -> cache snapshot

live poller -> poll statsapi live-feed every ~5-10s per active game
            -> diff playEvents against last-seen index -> new pitch(es)?
            -> update in-game delta (O(1) per pitch)
            -> BEFORE applying the new pitch's own outcome: combine
               snapshot + delta -> feature vector -> model.predict() -> cache "current prediction"
            -> THEN apply the pitch's actual outcome to the delta
```

## Model storage & retraining

- Keep the per-pitcher-model design (matches the existing per-pitcher
  approach). Store as `models/{pitcher_id}/{trained_through_date}.{pkl|cbm}`
  plus a `model_registry` SQLite table: `pitcher_id, trained_through_date,
  classifier, feature_cols (json), cat_features (json), test_accuracy,
  baseline_accuracy`. The registry tells the live server whether a model
  exists for a pitcher and the exact feature contract it expects.
- Retrain as a decoupled batch job, not on the serving path.
- **Feature-contract guard**: the live incremental state must produce
  exactly the columns the stored model was trained on, in the same order.
  One-hot pitch-type columns (RF/XGBoost) are derived per-pitcher at
  training time - a pitcher debuting a new pitch type mid-season needs the
  live vector reindexed against `model.feature_cols` (missing dummy filled
  with 0), or predictions silently break. This is a real argument for
  **CatBoost for live serving specifically**: native categorical handling
  degrades gracefully on an unseen category value instead of needing an
  explicit reindex step.

## Fallback tier for `min_pitches`

- **Full model** - pitcher clears `min_pitches`, trained model exists.
- **Naive mix fallback** - some history but not enough to train on: return
  the raw `career_mix`/`by_count_mix` from the snapshot directly as the
  predicted distribution (this is the trivial Markov-style baseline from
  workstream 3, repurposed as the low-data fallback instead of just an eval
  yardstick).
- **No data** - brand-new callup: explicit "insufficient data" response
  rather than a silent guess.

The API response should carry which tier served the prediction.

## API surface (FastAPI)

- `GET /pitchers/{pitcher_id}/status` - model exists?, trained_through_date,
  classifier, test/baseline accuracy, pitch count.
- `GET /predict/{game_pk}/{pitcher_id}` - current predicted next-pitch-type
  distribution (full probabilities, not just argmax), which tier served it,
  and the pitch count the prediction is based on.
- Poller lifecycle is automatic off the daily schedule (probable starters),
  not manually triggered per game, for v1.

## Decisions needed before/while implementing

1. **Poller infra**: a single async loop cycling active `gamePks` inside the
   FastAPI process (simplest, fine for a handful of concurrent games) vs. a
   separate worker process. Leaning toward the former for v1.
2. **Retrain cadence**: weekly vs. every-N-starts. Leaning toward weekly -
   no evidence yet the model degrades faster than that.
3. **Per-pitcher classifier choice**: lock everyone to one classifier (e.g.
   CatBoost, for the reindex-safety reason above) vs. let the registry track
   a per-pitcher best-backtested classifier. Leaning toward one classifier
   for all pitchers for v1 - per-pitcher-best is real complexity for a
   currently unproven accuracy gain.
4. **In-game delta persistence**: proposed in-memory only (cheap replay on
   restart). Would need to become durable for a multi-process/multi-instance
   deployment where in-memory state can't be shared - depends on target
   deployment, not yet decided.

## Suggested next step

Pick one piece to start with tomorrow: the snapshot/delta state manager
(everything else depends on it), or the FastAPI skeleton with the
registry/endpoints. Snapshot/delta manager is probably the right place to
start since it's the part with actual technical risk (making sure the
incremental math matches the batch `MlbBuildModelData` output exactly).
