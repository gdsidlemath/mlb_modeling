# Plan: 2026-09-24

Four workstreams, roughly in the order they make sense to tackle.

## 1. Document `MlbBuildModelData.py`

- New `docs/model_data_builder.md` covering, per function: what it takes in,
  what it produces, and *why* (e.g. why `_last_two_innings_mix` needs the
  shift-by-2 lookup instead of a simple rolling window).
- Include a real worked example: run `build_pitcher_data()` for a small
  window, dump ~10-15 rows to a markdown table (or a small CSV alongside it)
  showing actual column values, so the output shape is concrete rather than
  described in prose.
- Group the column reference by category (identifiers, count/base state,
  `prev_*`, the five pitch-mix families, weather/time) rather than one flat
  list.

## 2. Document the scraper / database

- New `docs/scraper_and_schema.md`: what comes from statsapi (game/live-feed/
  people endpoints) vs. what's supplemented from Savant, and exactly which
  fields the merge adds.
- Document the transformations that aren't obvious from the code alone —
  weather/wind string parsing, the postponed-game dedup, the Savant row-cap
  chunking — since those were the two real bugs hit during scraping, worth a
  paragraph each so they don't get reintroduced later.
- A schema section for `games`/`abs`/`pitches`/`players`: column, type,
  source, meaning.

## 3. Explore other model classes

- CatBoost first — handles categorical features (pitch type, zone, weather)
  natively instead of manual one-hot, which currently blows up the feature
  space; often strong out-of-the-box on tabular sports data.
- Since this is inherently sequential (a pitch-by-pitch sequence within an
  at-bat/game), scope a sequence model (LSTM or small transformer) as a
  genuinely different approach rather than another tree ensemble — bigger
  lift, likely a stretch goal rather than a same-day deliverable.
- Add a trivial baseline (simple prior-pitch-type transition/Markov model) so
  "beats baseline" means something sharper than just beating the
  most-frequent-class rate.

## 4. Live API design

- `build_pitcher_data(pitcher_id, date_until=...)` already exists, which is
  the right primitive for "features as of right now" — the design question is
  how to get *current* game state to feed it (statsapi live-feed polling for
  in-progress games) and how to keep it fast (rebuilding full history per
  request will be too slow; needs a cached feature-state per pitcher that
  updates incrementally as new pitches land).
- Decisions needed: model storage/versioning (one pickled model per pitcher —
  how often retrained?), API framework (FastAPI is the natural fit), and
  fallback behavior for pitchers below `min_pitches`.
- Most open-ended item — treat as a design/scoping pass first, then implement
  once the shape is agreed on.

## Suggested order

1 and 2 are quick, self-contained, and de-risk nothing breaking — good to
knock out first. 3 (CatBoost) is a fast experiment that can slot in anywhere.
4 deserves the most dedicated thinking time, so probably best tackled after
the documentation is fresh in context.
