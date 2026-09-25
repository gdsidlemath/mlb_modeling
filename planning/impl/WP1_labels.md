# WP1: Label mappings and `y_*` / `cur_*` columns

**Depends on:** WP0 (test harness). **Creates:** `MlbLabels.py`,
`tests/test_labels.py`. **Don't modify** `MlbBuildModelData.py`. WP4 wires
this module in.

## Goal

A standalone module that turns a joined pitch frame (pitches + at-bat columns)
into target labels. All mappings are plain dicts that callers can override, so
experiments can swap them without editing code.

## Input contract

`add_labels(df, ...)` receives a DataFrame that has at least these columns:
`code`, `type`, `endSpeed`, `zone`, `trajectory`, `eventType` (from the
`abs` table), `batter_stance`, and optionally `delta_pitcher_run_exp`. If
that last column is missing, `y_run_value` is all NaN. The function must not
reorder or drop rows (`apply_global_filters` is the only function that drops
rows).

## Module contents (`MlbLabels.py`)

These constants were checked against all 11 season DBs (2015–2025), which
contain every code, type and in-play `eventType` listed below.

```python
IN_PLAY = "IN_PLAY"   # sentinel in OUTCOME_CODE_MAP: resolve via eventType

# Pitch codes dropped from the dataset entirely: pitchouts (P, Q, R) and
# intentional balls (I; only exists in 2015-2016, before the automatic IBB).
EXCLUDED_CODES = {"P", "Q", "R", "I"}

# Pitch types dropped entirely: position players/eephus (FA, EP, CS),
# automatic/intentional/pitchout/unknown (AB, IN, PO, UN). "" and None are
# NOT dropped: they're normalized to NaN (unclassified but real pitch).
EXCLUDED_TYPES = {"FA", "EP", "CS", "AB", "IN", "PO", "UN"}

# code -> (y_swing, y_contact). y_contact is NaN when there was no swing.
SWING_CODE_MAP = {
    "B": (0, nan), "*B": (0, nan), "C": (0, nan), "H": (0, nan),
    "S": (1, 0), "W": (1, 0), "M": (1, 0),
    "T": (1, 1), "O": (1, 1), "F": (1, 1), "L": (1, 1),
    "X": (1, 1), "D": (1, 1), "E": (1, 1), "Z": (1, 1),
}

# Foul tips (T, O) are grouped with swinging strikes: for the count they
# always add a strike (strike three if caught with two strikes), unlike a
# plain foul. Override with {**OUTCOME_CODE_MAP, "T": "foul", "O": "foul"}.
OUTCOME_CODE_MAP = {
    "B": "ball", "*B": "ball", "C": "called_strike", "H": "hbp",
    "S": "swinging_strike", "W": "swinging_strike", "M": "swinging_strike",
    "T": "swinging_strike", "O": "swinging_strike",
    "F": "foul", "L": "foul",
    "X": IN_PLAY, "D": IN_PLAY, "E": IN_PLAY, "Z": IN_PLAY,
}

EVENT_OUTCOME_MAP = {
    "single": "in_play_single",
    "double": "in_play_xbh", "triple": "in_play_xbh",
    "home_run": "in_play_hr",
    # everything else that ends an at-bat on a ball in play:
    "field_out": "in_play_out", "force_out": "in_play_out",
    "grounded_into_double_play": "in_play_out", "double_play": "in_play_out",
    "triple_play": "in_play_out", "fielders_choice_out": "in_play_out",
    "fielders_choice": "in_play_out", "field_error": "in_play_out",
    "sac_fly": "in_play_out", "sac_fly_double_play": "in_play_out",
    "sac_bunt": "in_play_out", "sac_bunt_double_play": "in_play_out",
    "catcher_interf": "in_play_out", "game_advisory": "in_play_out",
}

PITCH_FAMILY_MAP = {
    "FF": "fastball", "SI": "fastball", "FC": "fastball",
    "SL": "breaking", "ST": "breaking", "SV": "breaking",
    "CU": "breaking", "KC": "breaking",
    "CH": "offspeed", "FS": "offspeed", "FO": "offspeed", "SC": "offspeed",
    "KN": "knuckle",
}

ZONES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14]
OUTCOME_CLASSES = ["ball", "called_strike", "swinging_strike", "foul", "hbp",
                   "in_play_out", "in_play_single", "in_play_xbh", "in_play_hr"]
BUNT_TRAJECTORIES = {"bunt_grounder", "bunt_popup", "bunt_line_drive"}
BUNT_EVENTS = {"sac_bunt", "sac_bunt_double_play"}
```

Functions (all pure, none mutating their input; return a copy):

| function | behavior |
|---|---|
| `pitch_types(pitch_family_map=None)` | `sorted(map)` |
| `pitch_families(pitch_family_map=None)` | `sorted(set(map.values()))` |
| `normalize_types(df)` | `type` values `""` → NaN |
| `apply_global_filters(df)` | normalize types, then drop rows with `code in EXCLUDED_CODES` or `type in EXCLUDED_TYPES`. Keep NaN type |
| `validate_maps(df, swing_code_map, outcome_code_map, event_outcome_map, pitch_family_map)` | Run on an **already filtered** frame. Raise `ValueError` listing every `code` missing from either code map, every non-NaN `type` missing from the family map, and every `eventType` on an in-play row missing from the event map. The message must include the offending values and their row counts |
| `add_labels(df, swing_code_map=None, outcome_code_map=None, event_outcome_map=None, pitch_family_map=None)` | `None` → module default. Calls `validate_maps` first, then adds the columns below |
| `mapping_manifest(...)` (same four args) | JSON-serializable dict of the four maps (tuples → lists, NaN → None) plus `"sha1"`: SHA-1 of `json.dumps(maps, sort_keys=True)` |

## Columns `add_labels` adds

| column | dtype | definition |
|---|---|---|
| `y_pitch_type` | object | `type` (NaN stays NaN) |
| `y_pitch_family` | object | `pitch_family_map[type]`, NaN if type NaN |
| `y_end_speed` | float | `endSpeed` |
| `y_zone` | object | `str(int(zone))`, e.g. `"5"`, `"11"`. NaN if zone NaN |
| `y_swing` | float | from `SWING_CODE_MAP` |
| `y_contact` | float | from `SWING_CODE_MAP`, NaN when no swing |
| `y_outcome` | object | `outcome_code_map[code]`. If `IN_PLAY`, use `event_outcome_map[eventType]` |
| `y_run_value` | float | `delta_pitcher_run_exp`, or NaN if the column is absent |
| `is_bunt` | int 0/1 | code in {L, M}, or `trajectory` in BUNT_TRAJECTORIES, or (in play and `eventType` in BUNT_EVENTS) |
| `cur_family` | object | same as `y_pitch_family` (a *feature* copy for tier T1; kept separate so WP2 can classify it) |
| `cur_in_zone` | float | 1.0 if zone in 1–9, 0.0 if zone in 11–14, NaN if zone NaN |
| `cur_zone_row` | object | `"high"` (1-3, 11, 12), `"mid"` (4-6), `"low"` (7-9, 13, 14) |
| `cur_zone_col` | object | relative to the batter: `"in"` / `"mid"` / `"away"`, see below |

**`cur_zone_col`**: zones are numbered from the **catcher's** view. Column A
is zones 1, 4, 7, 11, 13 (catcher's left); column B is 2, 5, 8 (middle);
column C is 3, 6, 9, 12, 14 (catcher's right). A right-handed batter stands
on the catcher's left, so for `batter_stance == "R"`, A = `"in"` and C =
`"away"`. For `"L"` it's the reverse. Column B = `"mid"`. **Verify this
orientation in a test** (see below). If the data contradicts it, swap the
mapping and say so in your report.

## Tests (`tests/test_labels.py`)

Build the input frame directly from the test DB: `pitches` joined to `abs` on
`(g_id_int, ab_ind)`, taking `eventType` and `batter_stance` from `abs`.

1. On the test DB: `apply_global_filters` → `add_labels` runs without error.
   Every `y_outcome` is in `OUTCOME_CLASSES` or NaN, and NaN count == 0.
2. For every row with `y_swing == 0`, `y_contact` is NaN. With `y_swing == 1`,
   `y_contact` ∈ {0, 1}.
3. A code missing from the map raises: add a fake row with `code="QQ"`, and
   `validate_maps` raises a `ValueError` whose message contains `"QQ"`.
4. Overriding the map works: with `{**OUTCOME_CODE_MAP, "T": "foul", "O":
   "foul"}`, every `code == "T"` row gets `y_outcome == "foul"`.
5. The in-play pitch is the last pitch of its at-bat: for rows with code in
   {X, D, E, Z}, `p_ind` equals the max `p_ind` of that `(g_id_int, ab_ind)`.
   Allow ≤ 0.1% violations and print the count.
6. Zone orientation: for `batter_stance == "R"` rows, the mean `pX` of rows
   whose `cur_zone_col == "in"` is **less** than for `"away"` (pX is negative
   toward the catcher's left). The reverse holds for `"L"`.
7. `mapping_manifest()` is JSON-serializable, and its `sha1` changes when one
   map entry changes.
8. `apply_global_filters` drops every `EXCLUDED_CODES`/`EXCLUDED_TYPES` row
   and keeps rows with NaN type.

## Acceptance

- Full suite passes.
- **Also run once on one full season** (not as a unit test, since it's too
  slow):
  `apply_global_filters` + `add_labels` on `data/mlb_pitch_data_2015.db`
  (it has the most unusual codes). Report the `y_outcome` value counts and the
  number of rows dropped by the global filter.
