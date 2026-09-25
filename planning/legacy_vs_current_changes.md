# Legacy vs. current: what changed and why

There are actually two "legacy" layers in this repo, and it's worth being
clear about which one each comparison below is against:

1. **The truly old code** (`legacy/` folder on `master`): Python 2,
   XML/HTML-scraping of the old Gameday/PitchFx feeds, hand-rolled numpy
   classifiers, flat `.txt` file storage. Not runnable as-is (Python 2 only,
   `svmutil`/`cPickle` imports, hardcoded `PitcherFiles/` paths).
2. **The pre-Savant modern layer** (`MlbApiScraper.py`/`MlbBuildModelData.py`
   as they stood on `master` before this branch): a working Python 3/pandas
   statsapi scraper, but `MlbBuildModelData.build_pitcher_data`/
   `build_batter_data` were unimplemented stubs (`pass`), and there was no
   model-training code at this layer at all.

This branch (1) fixed real bugs in the pre-Savant scraper, (2) added Savant
as a supplemental data source, (3) fully implemented the feature-engineering
layer that was previously a stub, and (4) added a model-training layer that
didn't exist at this layer before — replacing what `legacy/` used to do, but
built from scratch rather than ported.

## 1. Scraping: data source and reliability

| | `legacy/PitchFxScraper.py` | pre-Savant `MlbApiScraper.py` (master) | current `MlbApiScraper.py` |
|---|---|---|---|
| Source | Old Gameday/PitchFx XML feeds, scraped with `lxml`/`BeautifulSoup` | statsapi.mlb.com JSON | statsapi.mlb.com JSON, **+ Savant CSV for fields statsapi lacks** |
| Language/deps | Python 2, `xmltodict`, `IPython.embed` debugging hooks left in | Python 3, `requests`/`pandas` | same |
| Season coverage | 2009-2019 hardcoded default | 2010-2019 hardcoded default | 2010-2026, `opening_day_dict` extended through 2026 |
| Failure handling | none visible | one bad game killed the whole scrape (unhandled exception) | per-game try/except — logs and skips, scrape continues |
| Progress visibility | none | none | status prints every 50 games, `flush=True` throughout so log-file redirection shows progress live |
| Known bugs | N/A (not evaluated) | (a) postponed/rescheduled games double/triple counted — schedule listing can repeat one `gamePk` under multiple dates; (b) pitch filter (`"call" in ev["details"]`) crashed on non-pitch events like pickoffs; (c) weather `temp`/`wind` stored as raw unparsed strings; (d) `get_player_data` had several real bugs (unhandled `people` API wrapper, broken `pd.DataFrame` construction) | all four fixed — see [scraper_and_schema.md](../docs/scraper_and_schema.md#known-pitfalls-fixed-in-code) for the dedup/pitch-filter fixes in detail |

**Why add Savant at all, given statsapi already has pitch physics?** Initial
plan was a full Savant replacement; decided against it once we confirmed
statsapi's live-feed `pitchData`/`hitData` already covers spin, break,
release position/velocity, and batted-ball outcomes. Savant is used only for
the genuinely missing fields (`SAVANT_GAP_COLUMNS`): xStats, win/run
expectancy, bat-tracking, and rest/times-through-order fields. This keeps
statsapi as the primary, reliable, unauthenticated source and limits
exposure to Savant's quirks (User-Agent gating, the 25,000-row silent
truncation cap) to a narrow supplemental merge.

## 2. Pitch type representation

**Legacy** (`makepitcherdata.py`, `ClassificationTreePrediction.py`): pitch
types collapsed into 6 numeric buckets (`getcount` loops `range(0,6)`,
pitches stored as ints 1-6) — the actual pitch type (fastball vs. sinker vs.
cutter, etc.) was thrown away before modeling.

**Current**: real pitch type codes (`FF`, `SI`, `SL`, `CH`, `ST`, `FC`, ...)
are carried through and one-hot encoded (`pitch_num_in_game`, all
`type_<CODE>_*` mix columns in `MlbBuildModelData`). Explicit choice, made
when scoping the feature-building step: a pitcher's actual repertoire is
more informative than a 6-way bucket, and one-hot handles pitchers with
different repertoires without imposing a false ordinal relationship.

## 3. Rolling pitch-mix history: pitch-count windows vs. inning-based

Legacy had no equivalent rolling-history feature. This is new design work in
`MlbBuildModelData._build_pitch_mix_features`. First draft used
pitch-count-based windows (last 5/10/20 pitches) — **explicitly rejected**
in favor of inning-based windows (this inning, last two innings, game so
far), because a batter's plate-appearance-relevant history is naturally
bounded by innings/at-bats, not an arbitrary pitch count that spans innings
or games inconsistently. See
[model_data_builder.md](../docs/model_data_builder.md#pitch-mix-feature-families)
for the five resulting feature families and how `_last_two_innings_mix`
computes the sliding 2-inning window.

## 4. `prev_zone`: numeric vs. categorical

First pass fed `prev_zone` (the discrete 1-14 strike-zone region code from
the previous pitch) in as a raw number. **Corrected**: zone codes have no
ordinal relationship (zone 5 isn't "between" zone 4 and zone 6 in any
meaningful sense), so it's cast to `Int64` and one-hot encoded like
`prev_pitch_type`/`prev_call`, in both `MlbBuildModelData` output and
`MlbPitchPredictionModel._prepare_features`.

## 5. Weather/time-of-day features

Not present in either legacy layer. Added because they're context a
real-world bettor/analyst would consider (dome vs. outdoor, wind, day vs.
night game) — `day_night`, `weather_condition`, `temperature`, `wind_speed`,
`wind_direction` are pulled into `_pitch_sequence`'s game-context join and
one-hot encoded (`weather_condition`, `wind_direction`) or binarized
(`day_night`) at model-prep time.

## 6. Modeling approach

| | `legacy/CTpitchpredict.py` / `ClassificationTreePrediction.py` | current `MlbPitchPredictionModel.py` |
|---|---|---|
| Algorithm | `sklearn.ensemble` (RandomForest-family) called through hand-rolled matrix normalization/error-matrix code; also references to `svmutil` (LibSVM) in `testpredict.py`, seemingly abandoned mid-development | `RandomForestClassifier` and `XGBClassifier`, selectable via a `classifier` param, same public `fit()`/`evaluate()` API for both |
| Feature engineering | Loaded pre-computed `.txt` matrices per pitcher (`PitcherFiles/<ID>d.txt`) — the actual feature computation isn't in a runnable, inspectable state in this repo | Computed on demand by `MlbBuildModelData`, fully documented, leakage-checked (`RESULT_COLUMNS` excludes every outcome/physics column) |
| Train/test split | Not clearly deterministic/chronological in the visible code | explicit chronological split (train on earlier share, test on later) — avoids look-ahead leakage |
| Per-player scope | One model per pitcher (matches legacy's per-`PitcherFiles/<ID>` structure) | same — per-pitcher models, `min_pitches` floor to avoid training on too little data |
| Hyperparameter tuning | none visible | `tune_xgboost=True` grid-searches `max_depth`/`learning_rate` with early stopping against a validation split carved from the *tail* of the training data (never touching the held-out test set) — see `_tune_xgboost` |
| Runnability | Python 2, missing dependencies (`svmutil`), hardcoded local paths — not runnable without porting | runs end-to-end against the SQLite dbs this pipeline produces |

This is the piece described as "replacing legacy's broken classifier
scripts" — not a port, a from-scratch implementation, because the legacy
classifier code wasn't in a working state to begin with (Python 2, missing
deps, and the feature files it expects were never regenerated).

## 7. Persistence

**Legacy**: flat `.txt` files per pitcher under a `PitcherFiles/` directory,
written/read via `numpy.loadtxt`/`pickle`. No shared schema, no querying
across pitchers without re-loading every file.

**Current**: SQLite (`games`/`abs`/`pitches`/`players` tables), queryable
directly (used e.g. by `utils/find_top_pitcher.py`'s SQL join/aggregate) and
shared across the scraper, feature builder, and modeling layers without
custom per-file formats. CSV is also supported as an output format
(`as_type="csv"`) for cases where a db isn't wanted.

## 8. New tooling that didn't exist before

- `run_season_scrape.py` — parametrized single-season scrape runner (used for
  the 2022/2023/2025 backfill scrapes).
- `utils/find_top_pitcher.py` — cross-season pitch-count leaderboard via
  direct SQL, used to pick a representative pitcher (Logan Webb, most total
  pitches 2022-2025) for model testing.
- `utils/tune_xgboost_comparison.py` — reusable RandomForest/XGBoost
  comparison harness with hyperparameter tuning.
- `docs/model_data_builder.md`, `docs/scraper_and_schema.md` — reference docs
  for the feature-engineering and scraping/schema layers (this file's
  siblings in `planning/`).

## Net effect

The pre-Savant modern layer was a working scraper with an unimplemented
modeling story; `legacy/` was a non-runnable prototype of that modeling
story from an earlier, less capable version of the data. This branch merged
the useful parts of both — keeping the modern scraper as the base, fixing
its real bugs, supplementing it with Savant only where genuinely needed, and
building the feature-engineering and modeling layers `legacy/` had
attempted, using real pitch types and inning-based history windows instead
of the 6-bucket/pitch-count approach `legacy/` used.
