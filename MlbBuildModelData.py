import os
import sqlite3 as lite

import numpy as np
import pandas as pd


class BuildMlbModelData:

    # Columns on the pitches table that describe what actually happened on a given
    # pitch (the ground truth a next-pitch model would be trying to predict), as
    # opposed to the *_this_inning/_last_2_innings/_game/_by_count/_vs_batter/
    # _vs_pitcher/prev_* columns this class adds, which are all computed from
    # pitches strictly before the row's own.
    LABEL_COLUMNS = ["type", "zone", "startSpeed", "endSpeed", "code", "call",
                      "launchSpeed", "launchAngle", "totalDistance"]

    MIX_DECAY_MODES = (None, "day", "season")

    def __init__(self,
                 data_as_type=None,
                 load_dir="./",
                 load_name="",
                 save_as_name="",
                 save_as_type=None,
                 save_dir="./",
                 mix_decay_mode=None,
                 mix_halflife_days=180,
                 mix_season_decay=0.5):
        """mix_decay_mode: how the career-spanning pitch-mix features
        (career/by_count/vs_opponent - the ones NOT naturally bounded to a
        single game) weight older pitches. Evaluated empirically (see
        planning notes) and found to help some pitchers and hurt others at
        any single fixed rate, so it defaults to None (plain, unweighted
        average - prior behavior) rather than being on by default.

        - None: plain cumulative average, no recency weighting.
        - "day": exponential decay by elapsed calendar days, halflife
          `mix_halflife_days`. A pitch `mix_halflife_days` days older than the
          current one carries half the weight of a pitch from today.
        - "season": exponential decay by season, rate `mix_season_decay`. The
          current season's pitches are unweighted; pitches from N seasons ago
          are weighted `mix_season_decay ** N`. Coarser than "day" - doesn't
          decay within a season, only across season boundaries.

        The this_inning/last_2_innings/game mix families are always plain
        (they're already bounded to a single game and don't need this)."""

        if mix_decay_mode not in self.MIX_DECAY_MODES:
            raise ValueError(f"mix_decay_mode must be one of {self.MIX_DECAY_MODES}, got {mix_decay_mode!r}")
        self.mix_decay_mode = mix_decay_mode
        self.mix_halflife_days = mix_halflife_days
        self.mix_season_decay = mix_season_decay

        self.data_as_type = data_as_type.lower() if data_as_type is not None else None
        self.load_dir = load_dir
        self.load_name = load_name
        if self.data_as_type == "csv":
            self.load_csv_loc = os.path.join(self.load_dir, self.load_name)
        elif self.data_as_type == "db":
            self.load_db_cnx = lite.connect(os.path.join(self.load_dir, self.load_name) + ".db")

        self.save_as_type = save_as_type.lower() if save_as_type is not None else None
        self.save_dir = save_dir
        self.save_as_name = save_as_name
        if self.save_as_type == "csv":
            self.save_csv_loc = os.path.join(self.save_dir, self.save_as_name)
        elif self.save_as_type == "db":
            self.save_db_cnx = lite.connect(os.path.join(self.save_dir, self.save_as_name) + ".db")

        self._pitches_df = None
        self._abs_df = None
        self._games_df = None

    def _load_raw_tables(self):

        if self._pitches_df is not None:
            return

        if self.data_as_type == "csv":
            self._pitches_df = pd.read_csv(self.load_csv_loc + "_pitches.csv", index_col=0)
            self._abs_df = pd.read_csv(self.load_csv_loc + "_abs.csv", index_col=0)
            self._games_df = pd.read_csv(self.load_csv_loc + "_games.csv", index_col=0)
        elif self.data_as_type == "db":
            self._pitches_df = pd.read_sql("select * from pitches", self.load_db_cnx)
            self._abs_df = pd.read_sql("select * from abs", self.load_db_cnx)
            self._games_df = pd.read_sql("select * from games", self.load_db_cnx)
        else:
            raise ValueError("data_as_type must be 'csv' or 'db' to load source data")

    def _pitch_sequence(self, player_id, role, date_until=None):
        """Every pitch involving player_id (as pitcher or batter), joined with its
        at-bat/game context, sorted chronologically."""

        self._load_raw_tables()

        role_col = "pitcher_id" if role == "pitcher" else "batter_id"
        ab_keys = self._abs_df.loc[self._abs_df[role_col] == player_id, ["g_id_int", "ab_ind"]]

        df = self._pitches_df.merge(ab_keys, on=["g_id_int", "ab_ind"], how="inner")
        df = df.merge(
            self._abs_df[["g_id_int", "ab_ind", "batter_id", "pitcher_id", "batter_stance",
                           "pitcher_hand", "inning", "halfInning", "outs", "on1b", "on2b",
                           "on3b", "awayScore", "homeScore", "startTime"]],
            on=["g_id_int", "ab_ind"], how="left",
        )
        df = df.merge(
            self._games_df[["g_id_int", "game_date", "home_team", "away_team", "day_night",
                             "weather_condition", "temperature", "wind_speed", "wind_direction"]],
            on="g_id_int", how="left",
        )

        if date_until is not None:
            df = df[df["game_date"] < int(str(date_until).replace("-", ""))]

        df = df.sort_values(["game_date", "g_id_int", "ab_ind", "p_ind"]).reset_index(drop=True)

        return df

    @staticmethod
    def _group_cumulative_mix(df, type_cols, group_cols, suffix):
        """Pitch-type mix within each group (e.g. same batter, same count, same
        game), using only pitches strictly before the current row. Assumes df is
        already sorted chronologically.

        Returns (mix, n_obs): mix is NaN wherever there are zero prior
        observations in the group (first pitch of that game/count/matchup/
        career) - callers are responsible for deciding how to fill that, since
        0 would be indistinguishable from "confirmed never throws this pitch".
        n_obs is the prior-observation count backing each mix row, exposed so
        the model can weigh low-sample mixes accordingly."""

        type_dummies = df[type_cols]
        cum_before = df.groupby(group_cols)[type_cols].cumsum() - type_dummies
        count_before = df.groupby(group_cols).cumcount()

        mix = cum_before.div(count_before.where(count_before > 0), axis=0)
        mix.columns = [f"{c}_{suffix}" for c in type_cols]

        return mix, count_before

    @staticmethod
    def _last_two_innings_mix(df, type_cols, game_col="g_id_int", inning_col="inning"):
        """Pitch-type mix over the current (partial) inning plus the one
        immediately before it, using only pitches strictly before the current
        row. Returns (mix, n_obs) - see _group_cumulative_mix."""

        type_dummies = df[type_cols]
        game_cum_before = df.groupby(game_col)[type_cols].cumsum() - type_dummies
        game_count_before = df.groupby(game_col).cumcount()

        inning_totals = df.groupby([game_col, inning_col])[type_cols].sum()
        inning_totals["n_pitches"] = df.groupby([game_col, inning_col]).size()
        inning_cum_through = inning_totals.groupby(level=0).cumsum()

        lookup = df[[game_col, inning_col]].copy()
        lookup[inning_col] = lookup[inning_col] - 2
        older = lookup.merge(inning_cum_through.reset_index(), on=[game_col, inning_col], how="left")
        older = older[type_cols + ["n_pitches"]].fillna(0.0)
        older.index = df.index

        last2_sum = game_cum_before - older[type_cols]
        last2_count = game_count_before - older["n_pitches"]

        mix = last2_sum.div(last2_count.where(last2_count > 0), axis=0)
        mix.columns = [f"{c}_last_2_innings" for c in type_cols]

        return mix, last2_count

    @staticmethod
    def _group_decayed_mix_day(df, type_cols, group_cols, suffix, halflife_days, time_col="game_date_dt"):
        """Like _group_cumulative_mix, but weights prior pitches by exponential
        decay over elapsed calendar time (halflife_days) instead of a plain
        average, so recent pitches dominate stale ones. n_obs is still the
        plain (undecayed) prior-observation count. Returns (mix, n_obs)."""

        halflife = pd.Timedelta(days=halflife_days)

        def _decayed(g):
            shifted = g[type_cols].shift(1)
            return shifted.ewm(halflife=halflife, times=g[time_col]).mean()

        mix = df.groupby(group_cols, group_keys=False)[type_cols + [time_col]].apply(_decayed)
        mix = mix.reindex(df.index)
        mix.columns = [f"{c}_{suffix}" for c in type_cols]

        count_before = df.groupby(group_cols).cumcount()
        return mix, count_before

    @staticmethod
    def _season_prior_carry(sub, value_cols, season_decay):
        """sub: one group's (season -> totals) rows, sorted by season, columns
        = value_cols (pitch-type totals plus a pitch-count column). Returns a
        same-shape frame giving, at each season, the decayed carry-in from all
        STRICTLY earlier seasons of this group: V(s) = totals(s) +
        season_decay**gap * V(prev_s), gap = seasons apart (handles missed
        seasons - the gap is in season number, not row position)."""

        seasons = sub.index.to_numpy()
        vals = sub[value_cols].to_numpy(dtype=float)
        carry = np.zeros_like(vals)
        v_prev = np.zeros(vals.shape[1])
        prev_season = None
        for i in range(len(seasons)):
            if prev_season is not None:
                carry[i] = (season_decay ** (seasons[i] - prev_season)) * v_prev
            v_prev = vals[i] + carry[i]
            prev_season = seasons[i]
        return pd.DataFrame(carry, index=sub.index, columns=value_cols)

    def _group_decayed_mix_season(self, df, type_cols, group_cols, suffix, season_decay, season_col="season"):
        """Like _group_cumulative_mix, but pitches from season N are weighted
        season_decay**N relative to the current season (N=0). Within a season,
        pitches are weighted equally (plain cumulative average); only the
        season boundary applies decay. Returns (mix, n_obs), n_obs the plain
        (undecayed) prior-observation count."""

        type_dummies = df[type_cols]
        group_season_cols = group_cols + [season_col]

        within_cum_before = df.groupby(group_season_cols)[type_cols].cumsum() - type_dummies
        within_count_before = df.groupby(group_season_cols).cumcount()

        value_cols = type_cols + ["_n"]
        season_totals = df.groupby(group_season_cols)[type_cols].sum()
        season_totals["_n"] = df.groupby(group_season_cols).size()

        n_group_cols = len(group_cols)
        carry = season_totals.groupby(level=list(range(n_group_cols)), group_keys=False).apply(
            lambda sub: self._season_prior_carry(
                sub.reset_index(level=list(range(n_group_cols)), drop=True), value_cols, season_decay
            )
        )
        carry.index = season_totals.index

        merged = df[group_season_cols].merge(carry.reset_index(), on=group_season_cols, how="left")
        merged.index = df.index

        weighted_sum = within_cum_before + merged[type_cols].to_numpy()
        weighted_count = within_count_before + merged["_n"].to_numpy()

        mix = weighted_sum.div(pd.Series(weighted_count, index=df.index).where(lambda s: s > 0), axis=0)
        mix.columns = [f"{c}_{suffix}" for c in type_cols]

        count_before = df.groupby(group_cols).cumcount()
        return mix, count_before

    def _unbounded_group_mix(self, work, type_cols, group_cols, suffix):
        """Dispatches to plain/day-decayed/season-decayed cumulative mix per
        self.mix_decay_mode, for the mix families that span more than a single
        game (career, by_count, vs_opponent)."""

        if self.mix_decay_mode == "day":
            return self._group_decayed_mix_day(work, type_cols, group_cols, suffix, self.mix_halflife_days)
        elif self.mix_decay_mode == "season":
            return self._group_decayed_mix_season(work, type_cols, group_cols, suffix, self.mix_season_decay)
        else:
            return self._group_cumulative_mix(work, type_cols, group_cols, suffix)

    @staticmethod
    def _fill_cold_start(mix, fallback):
        """Fill a mix frame's cold-start NaN rows with the matching columns of
        `fallback` (e.g. career-to-date mix) instead of 0, so "no observations
        yet" doesn't read as "confirmed zero probability"."""

        aligned_fallback = fallback.set_axis(mix.columns, axis=1)
        return mix.fillna(aligned_fallback)

    def _build_pitch_mix_features(self, df, self_col, opponent_col, opponent_suffix):

        type_dummies = pd.get_dummies(df["type"], prefix="type")
        type_cols = type_dummies.columns.tolist()
        work = pd.concat(
            [df[["g_id_int", "inning", "balls", "strikes", "game_date", opponent_col]], type_dummies], axis=1
        )
        work["_career_key"] = 0
        if self.mix_decay_mode == "day":
            work["game_date_dt"] = pd.to_datetime(work["game_date"].astype(str), format="%Y%m%d")
        elif self.mix_decay_mode == "season":
            work["season"] = work["game_date"] // 10000

        df = df.copy()
        df["pitch_num_in_game"] = df.groupby("g_id_int").cumcount() + 1

        for col, new_col in [("type", "prev_pitch_type"), ("zone", "prev_zone"),
                              ("startSpeed", "prev_start_speed"), ("call", "prev_call")]:
            df[new_col] = df.groupby("g_id_int")[col].shift(1)

        # Career-to-date mix (no grouping) doubles as both a feature in its own
        # right and the fallback for every other mix family's cold-start rows.
        # Only the very first pitch of a player's loaded history has no career
        # mix to fall back on - filling that lone edge case with 0 is fine.
        career_mix, career_n = self._unbounded_group_mix(work, type_cols, ["_career_key"], "career")
        career_fallback = career_mix.fillna(0.0)

        game_mix, game_n = self._group_cumulative_mix(work, type_cols, ["g_id_int"], "game")
        this_inning_mix, this_inning_n = self._group_cumulative_mix(
            work, type_cols, ["g_id_int", "inning"], "this_inning"
        )
        last_2_innings_mix, last_2_innings_n = self._last_two_innings_mix(work, type_cols)

        work["count_key"] = work["balls"].astype(str) + "-" + work["strikes"].astype(str)
        count_mix, count_n = self._unbounded_group_mix(work, type_cols, ["count_key"], "by_count")

        opponent_mix, opponent_n = self._unbounded_group_mix(work, type_cols, [opponent_col], opponent_suffix)

        game_mix = self._fill_cold_start(game_mix, career_fallback)
        this_inning_mix = self._fill_cold_start(this_inning_mix, career_fallback)
        last_2_innings_mix = self._fill_cold_start(last_2_innings_mix, career_fallback)
        count_mix = self._fill_cold_start(count_mix, career_fallback)
        opponent_mix = self._fill_cold_start(opponent_mix, career_fallback)

        n_obs = pd.DataFrame({
            "game_n_pitches": game_n, "this_inning_n_pitches": this_inning_n,
            "last_2_innings_n_pitches": last_2_innings_n, "by_count_n_pitches": count_n,
            f"{opponent_suffix}_n_pitches": opponent_n, "career_n_pitches": career_n,
        })

        return pd.concat(
            [df, this_inning_mix, last_2_innings_mix, game_mix, count_mix, opponent_mix,
             career_mix, n_obs],
            axis=1,
        )

    def build_pitcher_data(self, pitcher_id, date_until=None):
        """One row per pitch thrown by pitcher_id, with pre-pitch context/history
        features plus that pitch's actual outcome (see LABEL_COLUMNS)."""

        df = self._pitch_sequence(pitcher_id, role="pitcher", date_until=date_until)
        if df.empty:
            return df

        return self._build_pitch_mix_features(
            df, self_col="pitcher_id", opponent_col="batter_id", opponent_suffix="vs_batter"
        )

    def build_batter_data(self, batter_id, date_until=None):
        """One row per pitch faced by batter_id, with pre-pitch context/history
        features plus that pitch's actual outcome (see LABEL_COLUMNS)."""

        df = self._pitch_sequence(batter_id, role="batter", date_until=date_until)
        if df.empty:
            return df

        return self._build_pitch_mix_features(
            df, self_col="batter_id", opponent_col="pitcher_id", opponent_suffix="vs_pitcher"
        )
