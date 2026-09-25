# `MlbApiScraper.py` and the database it builds

Pulls one season (or date range) of MLB pitch-by-pitch data and writes it to
SQLite (or CSV) as three tables: `games`, `abs`, `pitches` (plus an optional
`players` table). `MlbBuildModelData` reads these tables back out; see
[model_data_builder.md](model_data_builder.md).

## Data sources

Two APIs, used for different things:

- **statsapi.mlb.com** (no auth/headers needed) — the primary source. Three
  endpoints:
  - `schedule` — which games happened in a date range, and their `gamePk`s.
  - `game/<gamePk>/feed/live` — the full play-by-play for one game: every
    at-bat, every pitch, with pitch physics (`pitchData`/`hitData` — release
    position/velocity, movement/break, spin, plate location, and for batted
    balls: exit velocity, launch angle, distance).
  - `people/<id>` — player bio info (name, DOB, height/weight, bats/throws).
    Only called by `get_player_data()`, which `main()` currently skips (too
    slow for a full-season scrape and not needed for modeling).
  statsapi already covers nearly all Statcast-style pitch physics, so it's the
  source of truth for everything except a specific list of fields Savant has
  that statsapi doesn't.

- **baseballsavant.mlb.com** `/statcast_search/csv` — supplemental only.
  Requires a browser-like `User-Agent` header (`SAVANT_HEADERS`) or the
  request 403s. Used only to fill in `SAVANT_GAP_COLUMNS`: Statcast's derived
  xStats (`estimated_ba_using_speedangle`, etc.), win/run expectancy deltas,
  bat-tracking (`bat_speed`, `swing_length`, `attack_angle`, ...), and a few
  count-of-games/rest-day fields (`n_thruorder_pitcher`,
  `n_priorpa_thisgame_player_at_bat`, `*_days_since_prev_game`,
  `*_days_until_next_game`).

## Scrape flow (`main()` / a `run_season_scrape.py` invocation)

1. `get_all_api_game_dfs()` — statsapi pass. Builds `games`/`abs`/`pitches`
   and writes them to the db (or CSVs).
2. `get_savant_supplemental_data(chunk_days=1)` — Savant pass, date-chunked.
   Result held in `self.savant_df`, not written to disk on its own.
3. `merge_savant_data()` — left-merges `savant_df` onto `pitches` on
   `(g_id_int, ab_ind, p_ind)` and re-saves `pitches` (`if_exists="replace"`
   for db).

## `get_all_api_game_dfs()` — statsapi pass, step by step

1. `get_api_id_data()` hits the `schedule` endpoint for the configured
   season(s)/month range/day range (see `__init__` date-range handling below)
   and returns the raw schedule JSON(s).
2. Every game listed is filtered to `gameType in ["R","F","D","L","W"]`
   (regular season, wild card, division series, league series, world series
   — excludes spring training/exhibition) and to games involving a team in
   `self.teams` (all 30 by default).
3. **Dedup**: a postponed-and-resumed game can appear under multiple calendar
   dates in the schedule (its postponed date(s) plus its actual makeup date)
   while sharing one `gamePk`. `all_id_list = list(dict.fromkeys(...))`
   collapses those to one fetch per `gamePk`. (This was a real bug — see
   [Known pitfalls](#known-pitfalls-fixed-in-code).)
4. For each `gamePk`: `get_api_game_data()` fetches the live-feed JSON, then
   `build_game_dataframes()` → `build_game_dictionary()` parses it into one
   game-level dict (with a nested list of at-bat dicts, each with a nested
   list of pitch dicts) and flattens that into three DataFrames. A failure on
   any single game is caught, logged (`skipping game {gid}: {exc}`), and
   skipped — one bad game doesn't kill the whole scrape.
5. All per-game DataFrames are concatenated and written out.

### `__init__` date-range handling

`seasons`/`months`/`days` each default to a *range* (`seasons`: 2010-2026,
`months`: 3-11, `days`: 1-30) or can be passed as `[start, end]` to build a
custom range, or a single value. **Important**: `months`/`days` are not
enumerated per-calendar-month — `get_api_id_data()` only ever uses
`min(months)/min(days)` as the start boundary and `max(months)/max(days)` as
the end boundary of one continuous date range per season (e.g.
`months=[3,9], days=[1,30]` → March 1 through September 30, not "the 1st-30th
of every month 3-9"). `days=[1,30]` (not 31) is intentional: it's just an
end-of-range boundary day, and using 31 would build an invalid date like
"09/31" for a 30-day month.

### `build_game_dictionary()` — parsing one game's live-feed JSON

- Pulls game-level metadata: teams, records at game time, venue,
  day/night, and weather. `temperature` is coerced to `int` (raw field is a
  string). `wind` comes as one string like `"5 mph, In From LF"` — split on
  the comma into `wind_speed` (int) and `wind_direction` (str).
- Walks `playsByInning` (top/bottom of each inning, in order) to get at-bats
  in chronological order, and for each at-bat (`play`):
  - Result info (`eventType`, `description`), the score/outs *before* the
    at-bat (carried over from the previous play, or 0/0/0 for the game's
    first at-bat).
  - Baserunners *before* the at-bat, reconstructed from the *previous* play's
    runner-movement data (`get_runners`) — i.e. `on1b`/`on2b`/`on3b` describe
    the state a pitcher/batter actually faced, not the state after their
    at-bat.
  - `inning`, `halfInning`, `startTime`/`endTime` (parsed to actual
    timestamps, plus an `_int` HHMMSS companion column).
  - Batter/pitcher id and handedness (`batSide`/`pitchHand`).
  - Pitches: filtered to events where `isPitch` is true and `pitchData` is
    present (excludes non-pitch `playEvents` like pickoff attempts, which
    don't have `pitchData` and used to throw a `KeyError` under the old
    filter — see [Known pitfalls](#known-pitfalls-fixed-in-code)). For each
    pitch: call code/description, pitch type code, the ball-strike count
    *before* this pitch, and every field under `pitchData` (including nested
    `coordinates`/`breaks`) plus `hitData` if the pitch was put in play
    (`None` for all hit-data fields otherwise).

## Savant pass

- **Chunking**: `_savant_date_chunks(chunk_days=1)` splits the configured
  season/date range into `chunk_days`-sized windows (daily by default).
  Necessary because Savant's CSV export **silently truncates at exactly
  25,000 rows** (`SAVANT_ROW_CAP`) with no error or truncation flag — a
  month-sized league-wide chunk reliably hits that cap. Daily chunks return
  roughly 4,000-4,900 rows, safely under it. `get_savant_csv()` still checks
  and prints a loud warning if any chunk ever comes back at/above the cap, so
  silent truncation can't happen unnoticed again.
- Each chunk is filtered to the same game types as the statsapi pass, reduced
  to `SAVANT_GAP_COLUMNS` plus its own join keys (`game_pk`,
  `at_bat_number`, `pitch_number`), and those keys are renamed/adjusted to
  match statsapi's: `g_id_int = game_pk`, `ab_ind = at_bat_number - 1`
  (Savant's at-bat number is 1-indexed, statsapi's `ab_ind` is 0-indexed),
  `p_ind = pitch_number`.
- All chunks are concatenated into `self.savant_df`.

## `merge_savant_data()`

Left-merge of `savant_df` onto `all_pitch_df` on
`(g_id_int, ab_ind, p_ind)`, then re-saves the `pitches` table/CSV in place
(`if_exists="replace"` for the db case). Left join means every statsapi pitch
is kept even if Savant coverage is missing for it (e.g. spring training edge
cases, or a chunk that failed) — those rows just get `NaN` in the
`SAVANT_GAP_COLUMNS`. `bat_speed`/swing-related columns are `NaN` for any
pitch that wasn't swung at, by construction (Savant only populates them on
swings) — that's expected, not a coverage gap.

## Database schema

Three tables (plus `players`, populated separately by `get_player_data()`,
not run in the current `main()`). All joined via `g_id_int` /
`(g_id_int, ab_ind)` / `(g_id_int, ab_ind, p_ind)`. Sizes below are from the
2024 season db (`data/mlb_pitch_data_2024.db`).

### `games` (2,429 rows x 18 cols, one row per game)

| column | type | meaning |
|---|---|---|
| `g_id_int` | int | statsapi `gamePk` — primary join key |
| `g_id_str` | text | statsapi's string game id, e.g. `2024_03_20_lan_sdn_1` |
| `game_date` | int | `YYYYMMDD`, e.g. `20240320` |
| `home_team` / `away_team` | int | statsapi team ids |
| `ht_win_pct` / `at_win_pct` | text | team win pct entering the game (statsapi's own string format, e.g. `.500`) |
| `ht_gms_plyd` / `at_gms_plyd` | int | games played entering the game |
| `stadium` | int | statsapi venue id |
| `day_night` | text | `"day"` / `"night"` |
| `weather_condition` | text | e.g. `"Dome"`, `"Sunny"`, `"Cloudy"` |
| `temperature` | int | degrees F |
| `wind_speed` | int | mph |
| `wind_direction` | text | e.g. `"In From LF"` |
| `winning_pitcher` / `losing_pitcher` | int | player id, `None` if game not final |

Sample row: `g_id_int=745444`, `2024_03_20_lan_sdn_1`, `game_date=20240320`,
`home_team=135` (SD), `away_team=119` (LAD), `day_night=night`,
`weather_condition=Dome`, `temperature=72`, `wind_speed=0`,
`wind_direction=None` — a domed-stadium game, so no real wind/weather to
report (Savant/statsapi both represent that as `Dome` + null wind).

### `abs` (182,903 rows x 21 cols, one row per at-bat)

| column | type | meaning |
|---|---|---|
| `g_id_int`, `ab_ind` | int | join keys (`ab_ind` is 0-indexed, chronological within the game) |
| `eventType` / `description` | text | outcome of the at-bat, e.g. `walk`, `force_out` |
| `awayScore` / `homeScore` | int | score **before** this at-bat |
| `outs` | int | outs **before** this at-bat |
| `on1b` / `on2b` / `on3b` | numeric/text (mixed `REAL`/`TEXT`, see note) | baserunner id **before** this at-bat, `None`/`NaN` if empty |
| `inning` | int | 1-indexed |
| `halfInning` | text | `"top"` / `"bottom"` |
| `startTime` / `endTime` | timestamp | wall-clock start/end of the at-bat |
| `startTime_int` / `endTime_int` | int | same, as `HHMMSS` |
| `batter_id` / `pitcher_id` | int | statsapi player ids |
| `batter_stance` / `pitcher_hand` | text | `"L"` / `"R"` |

Note: `on1b`/`on2b`/`on3b` show up with inconsistent SQLite column affinity
(`on1b` as `REAL`, `on2b`/`on3b` as `TEXT`) purely because `to_sql` infers
type per-column from whichever values happened to populate first — the
actual values are always either a player id or `None`/`NaN`. Any consumer
should treat all three uniformly as "nullable id."

Sample row: `g_id_int=745444, ab_ind=0`, `eventType=walk`,
`batter_id=605141` (Mookie Betts), `pitcher_id=506433`, `inning=1, top`,
`on1b=NaN` (bases empty entering the at-bat, as expected — it's the game's
first at-bat).

### `pitches` (709,512 rows x 76 cols, one row per pitch)

Three column groups:

- **Join keys**: `g_id_int`, `ab_ind`, `p_ind` (1-indexed pitch number within
  the at-bat).
- **statsapi pitch physics/outcome** (~45 cols): `code`/`call` (raw call code
  + description, e.g. `B`/`"Ball"`), `type` (pitch type code, e.g. `FF`,
  `SI`, `SL`), `strikes`/`balls` (count **before** this pitch),
  `startSpeed`/`endSpeed`, strike zone top/bottom, release position/velocity
  (`x0,y0,z0,vX0,vY0,vZ0,aX,aY,aZ`), plate crossing (`pX,pZ,x,y`), movement/
  break (`pfxX,pfxZ,breakAngle,breakLength,breakY,breakVertical,
  breakVerticalInduced,breakHorizontal`), `spinRate`/`spinDirection`, `zone`
  (statsapi's 1-14 strike-zone region code), `plateTime`, `extension`, and
  for batted balls: `launchSpeed`/`launchAngle`/`totalDistance`/`trajectory`/
  `hardness`/`location`/`coordX`/`coordY` (all `None` if the pitch wasn't put
  in play).
- **Savant supplemental** (`SAVANT_GAP_COLUMNS`, ~27 cols, `NaN` until
  `merge_savant_data()` runs): xStats, win/run expectancy deltas,
  bat-tracking metrics, and the rest/times-through-order fields
  (`n_thruorder_pitcher`, `n_priorpa_thisgame_player_at_bat`,
  `pitcher_days_since_prev_game`, `batter_days_since_prev_game`,
  `pitcher_days_until_next_game`, `batter_days_until_next_game`). Note
  `*_days_until_next_game` is only knowable in hindsight — fine for training,
  but must not be used as a live-prediction feature (flagged again in
  [model_data_builder.md](model_data_builder.md)).

Sample rows (subset of columns), first at-bat of game 745444 (Mookie Betts
vs. Yu Darvish):

```
 p_ind code  call type  strikes  balls  startSpeed  zone  spinRate  n_thruorder_pitcher  n_priorpa_thisgame_player_at_bat  pitcher_days_since_prev_game  bat_speed
     1    B  Ball   FF        0      0        94.5  12.0    2395.0                     1                                 0                          None       None
     2    F  Foul   FF        0      1        92.6   3.0    2304.0                     1                                 0                          None       None
     3    B  Ball   SI        1      1        93.4   6.0    2325.0                     1                                 0                          None       None
```

`n_priorpa_thisgame_player_at_bat=0` on all three because this is the first
plate appearance of the game (the very first at-bat, `ab_ind=0`) — there's no
prior PA yet to count. `bat_speed=None` on the called ball (pitch 1) and the
ball (pitch 3) as expected — no swing, no bat-speed reading. Pitch 2 is a
foul, which *is* a swing, yet still shows `bat_speed=None` — see the caveat
below on why that's expected rather than a bug.

> Caveat on the sample above: pitch 2 is a foul ball (a swing) but shows
> `bat_speed=None`. This isn't a scraper bug — Savant's public bat-tracking
> coverage has real gaps (not every swing gets a tracked bat-speed value,
> particularly early in the bat-tracking rollout / on certain swing types).
> Confirmed during development that bat_speed's ~44.6% overall non-null rate
> roughly matches the swing rate, so it's underlying data coverage, not a
> join problem.

### `players` (not populated in current `main()`)

Written by `get_player_data()`: one row per player id seen in `abs`
(`batter_id`/`pitcher_id` union), via the statsapi `people/<id>` endpoint.
Columns: `id`, `firstName`, `lastName`, `birthDate`, `birthCountry`,
`height`, `weight`, `draftYear`, `strikeZoneTop`, `strikeZoneBottom`,
`pos*` (primary position fields), `batHand`, `pitchHand`. Skipped in the
current full-season scrape flow (too slow — one API call per player — and
not needed for the modeling pipeline, which only needs ids/handedness
already present in `abs`).

## Known pitfalls (fixed in code)

These caused real data corruption during development and are worth knowing
about if something looks off in a future scrape:

- **Savant row-cap truncation**: see [Savant pass](#savant-pass) above.
  Symptom was ~90% of pitches missing Savant data after a month-chunked
  scrape, with every affected chunk landing at exactly 25,000 rows.
- **Duplicate postponed-game rows**: before the dedup fix, a
  postponed-and-rescheduled game got scraped once per calendar date it
  appeared under in the schedule listing, producing byte-identical duplicate
  games/at-bats/pitches. Symptom was a player's total pitch count coming out
  roughly 3x too high. If a future scrape ever looks inflated, check
  `select g_id_int, count(*) from games group by g_id_int having count(*) > 1`
  first.
- **Non-pitch play events crashing the parser**: pickoff attempts and other
  non-pitch `playEvents` don't have a `pitchData` key; the pitch filter must
  check `isPitch` **and** `"pitchData" in ev`, not just presence of a `call`
  key.
