import calendar
from datetime import datetime
from io import StringIO
import json
import os
import sqlite3 as lite

import requests
import pandas as pd

class MlbApiScraper:

    # Baseball Savant blocks requests without a browser-like User-Agent.
    SAVANT_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MlbApiScraper/1.0)"}
    SAVANT_CSV_URL = "https://baseballsavant.mlb.com/statcast_search/csv"

    # statsapi's live-feed pitchData/hitData already covers pitch physics
    # (spin rate/axis, break, release position/velocity, exit velo, launch
    # angle, distance). These are the fields Savant has that statsapi doesn't.
    SAVANT_GAP_COLUMNS = [
        "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
        "estimated_slg_using_speedangle", "woba_value", "woba_denom",
        "babip_value", "iso_value", "launch_speed_angle",
        "delta_home_win_exp", "delta_run_exp", "delta_pitcher_run_exp",
        "home_win_exp", "bat_win_exp", "bat_speed", "swing_length",
        "attack_angle", "attack_direction", "swing_path_tilt",
        "intercept_ball_minus_batter_pos_x_inches",
        "intercept_ball_minus_batter_pos_y_inches", "arm_angle",
        "hyper_speed", "n_thruorder_pitcher", "n_priorpa_thisgame_player_at_bat",
        "pitcher_days_since_prev_game", "batter_days_since_prev_game",
        "pitcher_days_until_next_game", "batter_days_until_next_game",
    ]

    def __init__(self,
                 seasons=None,
                 months=None,
                 days=None,
                 teams=None,
                 as_type=None,
                 db_name="",
                 save_dir="."):

        if seasons is None:
            seasons = list(range(2010, 2027))
        elif not isinstance(seasons, (tuple, list)):
            seasons = [seasons]
        elif len(seasons) == 2:
            seasons = list(range(seasons[0], seasons[1] + 1))
        if months is None:
            months = [3, 11]
        elif not isinstance(months, (tuple, list)):
            months = [months]
        elif len(months) == 2:
            months = list(range(months[0], months[1] + 1))
        if days is None:
            days = [1, 30]
        elif not isinstance(days, (tuple, list)):
            days = [days]
        elif len(days) == 2:
            days = list(range(days[0], days[1] + 1))

        # *** only add "flo" distinction if interest is in specific teams ***
        if teams is not None:
            if min(seasons) < 2012:
                if any(t == "mia" for t in teams) and not any(t == "flo" for t in teams):
                    teams.append("flo")
                if any(t == "flo" for t in teams) and not any(t == "mia" for t in teams):
                    teams.append("mia")

        self.team_dict = {"ana": 108, "nya": 147, "bal": 110, "cle": 114, "chn": 112, "kca": 118,
                          "was": 120, "det": 116, "cha": 145, "hou": 117, "tor": 141, "mia": 146,
                          "col": 115, "mil": 158, "min": 142, "nyn": 121, "ari": 109, "oak": 133,
                          "bos": 111, "pit": 134, "atl": 144, "sdn": 135, "cin": 113, "sfn": 137,
                          "phi": 143, "sln": 138, "lan": 119, "tba": 139, "sea": 136, "tex": 140}


        if teams is None:
            teams_list = ["ana", "nya", "bal", "cle", "chn", "was", "det", "cha", "hou",
                     "tor", "mia", "col", "mil", "min", "nyn", "ari", "oak", "bos",
                     "pit", "atl", "sdn", "cin", "sfn", "phi", "sln", "lan",
                     "tba", "sea", "tex", "kca"]
        else:
            teams_list = teams

        team_id_list = []
        for tm in teams_list:
            team_id_list.append(self.team_dict[tm.lower()])

        self.opening_day_dict = {2009: (4, 5),
                                 2010: (4, 4),
                                 2011: (3, 31),
                                 2012: (3, 28),
                                 2013: (3, 31),
                                 2014: (3, 30),
                                 2015: (4, 5),
                                 2016: (4, 3),
                                 2017: (4, 2),
                                 2018: (3, 29),
                                 2019: (3, 28),
                                 2020: (3, 26),
                                 2021: (4, 1),
                                 2022: (4, 7),
                                 2023: (3, 30),
                                 2024: (3, 28),
                                 2025: (3, 27),
                                 2026: (3, 26)}

        self.seasons = seasons
        self.months = months
        self.days = days
        self.teams = team_id_list

        self.as_type = as_type.lower() if as_type is not None else None
        self.save_dir = save_dir
        self.db_name = db_name
        if self.as_type == "csv":
            self.save_csv_loc = os.path.join(self.save_dir, self.db_name)
        elif self.as_type == "db":
            self.db_cnx = lite.connect(os.path.join(self.save_dir, self.db_name) + ".db")

        self.all_game_df = None
        self.all_ab_df = None
        self.all_pitch_df = None

    def get_raw_url_data(self,
                         url):

        page = requests.get(url)

        return page.content

    def get_api_id_data(self):

        if len(self.days) == 1 and len(self.months) == 1 and len(self.seasons) == 1:
            start_date = str(self.months[0]).zfill(2) + "/" + str(self.days[0]).zfill(2) + "/" + str(self.seasons)
            end_date = start_date
        else:
            if len(self.seasons) > 1:
                date_list = []
                for season in self.seasons:
                    start_date = str(min(self.months)).zfill(2) + "/" + str(min(self.days)).zfill(2) + "/" + str(season)
                    end_date = str(max(self.months)).zfill(2) + "/" + str(max(self.days)).zfill(2) + "/" + str(season)
                    date_list.append((start_date, end_date))
            else:
                start_date = str(min(self.months)).zfill(2) + "/" + str(min(self.days)).zfill(2) + "/" + str(self.seasons[0])
                end_date = str(max(self.months)).zfill(2) + "/" + str(max(self.days)).zfill(2) + "/" + str(self.seasons[0])

        if len(self.seasons) > 1:
            json_list = []
            for sd, ed in date_list:
                url = "https://statsapi.mlb.com/api/v1/schedule/?sportId=1&startDate=" + sd + "&endDate=" + ed

                raw = self.get_raw_url_data(url)

                raw_json = json.loads(raw)

                json_list.append(raw_json)
        else:
            url = "https://statsapi.mlb.com/api/v1/schedule/?sportId=1&startDate=" + start_date + "&endDate=" + end_date

            raw = self.get_raw_url_data(url)

            raw_json = json.loads(raw)

            json_list = [raw_json]

        return json_list

    def get_api_game_data(self, gid):

        url = "https://statsapi.mlb.com/api/v1.1/game/" + str(gid) + "/feed/live"

        raw = self.get_raw_url_data(url)

        raw_json = json.loads(raw)

        return raw_json

    def get_all_api_game_dfs(self):

        base_list = self.get_api_id_data()

        date_list = [b["dates"] for b in base_list]

        day_dicts = [sd["games"] for d in date_list for sd in d]

        temp_id_list = []

        for d_dict in day_dicts:
            day_gid_list = [b["gamePk"] for b in d_dict if b["gameType"] in ["R", "F", "D", "L", "W"] and (b["teams"]["away"]["team"]["id"] in self.teams or b["teams"]["home"]["team"]["id"] in self.teams)]
            temp_id_list.append(day_gid_list)

        # A postponed-and-resumed/rescheduled game can appear under multiple
        # calendar dates in the schedule listing (its original postponed
        # date(s) plus its actual makeup date) while sharing one gamePk -
        # dedupe so it isn't fetched/appended more than once.
        all_id_list = list(dict.fromkeys(gid for gid_list in temp_id_list for gid in gid_list))

        print(f"found {len(all_id_list)} games to scrape", flush=True)

        all_game_list, all_ab_list, all_pitch_list = [], [], []
        for i, gid in enumerate(all_id_list):
            try:
                raw_data = self.get_api_game_data(gid=gid)
                df_list = self.build_game_dataframes(raw_data)
            except Exception as exc:
                print(f"skipping game {gid}: {exc}", flush=True)
                continue

            if not any([df is None for df in df_list]):
                game_df, ab_df, pitch_df = df_list
                all_game_list.append(game_df.reset_index(drop=True))
                all_ab_list.append(ab_df.reset_index(drop=True))
                all_pitch_list.append(pitch_df.reset_index(drop=True))

            if (i + 1) % 50 == 0:
                print(f"processed {i + 1}/{len(all_id_list)} games ({len(all_game_list)} kept)", flush=True)

        print(f"done scraping games: {len(all_game_list)}/{len(all_id_list)} kept", flush=True)

        all_game_df = pd.concat(all_game_list, sort=False)
        all_ab_df = pd.concat(all_ab_list, sort=False)
        all_pitch_df = pd.concat(all_pitch_list, sort=False)

        if self.as_type == "db":
            all_game_df.to_sql(name="games", con=self.db_cnx)
            all_ab_df.to_sql(name="abs", con=self.db_cnx)
            all_pitch_df.to_sql(name="pitches", con=self.db_cnx)
        elif self.as_type == "csv":
            all_game_df.to_csv(self.save_csv_loc + "_games.csv")
            all_ab_df.to_csv(self.save_csv_loc + "_abs.csv")
            all_pitch_df.to_csv(self.save_csv_loc + "_pitches.csv")

        self.all_game_df = all_game_df
        self.all_ab_df = all_ab_df
        self.all_pitch_df = all_pitch_df

        return self

    # Savant's CSV export silently truncates at this many rows (observed: a
    # full-league month request comes back at exactly 25000 rows with no error
    # or truncation flag). Chunk requests small enough to stay well under it,
    # and warn loudly if a chunk ever comes close, since that means data is
    # being silently dropped.
    SAVANT_ROW_CAP = 25000

    def _savant_date_chunks(self, chunk_days=1):

        chunks = []
        for season in self.seasons:
            start_month, start_day = min(self.months), min(self.days)
            end_month, end_day = max(self.months), max(self.days)
            end_day = min(end_day, calendar.monthrange(season, end_month)[1])

            chunk_start = datetime(season, start_month, start_day)
            season_end = datetime(season, end_month, end_day)

            while chunk_start <= season_end:
                chunk_end = min(chunk_start + pd.Timedelta(days=chunk_days - 1), season_end)
                chunks.append((chunk_start, chunk_end))
                chunk_start = chunk_end + pd.Timedelta(days=1)

        return chunks

    def get_savant_csv(self, start_date, end_date):

        params = {
            "all": "true",
            "hfSea": str(start_date.year) + "|",
            "game_date_gt": start_date.strftime("%Y-%m-%d"),
            "game_date_lt": end_date.strftime("%Y-%m-%d"),
            "type": "details",
        }

        resp = requests.get(self.SAVANT_CSV_URL, params=params, headers=self.SAVANT_HEADERS, timeout=120)
        resp.raise_for_status()

        df = pd.read_csv(StringIO(resp.text))

        if len(df) >= self.SAVANT_ROW_CAP:
            print(f"WARNING: savant chunk {start_date.date()}-{end_date.date()} returned "
                  f"{len(df)} rows (>= {self.SAVANT_ROW_CAP} cap) - likely truncated, "
                  f"use a smaller chunk_days", flush=True)

        if df.empty:
            return df

        # Match the game types statsapi already filters to: regular season,
        # wild card, division series, league series, and world series.
        df = df[df["game_type"].isin(["R", "F", "D", "L", "W"])]

        return df

    def get_savant_supplemental_data(self, chunk_days=1):

        frames = []
        for start_date, end_date in self._savant_date_chunks(chunk_days=chunk_days):
            print(f"fetching savant data {start_date.date()} to {end_date.date()}", flush=True)
            try:
                df = self.get_savant_csv(start_date, end_date)
            except Exception as exc:
                print(f"skipping savant chunk {start_date.date()}-{end_date.date()}: {exc}", flush=True)
                continue
            if df.empty:
                continue
            print(f"  got {len(df)} savant rows", flush=True)

            keep_cols = ["game_pk", "at_bat_number", "pitch_number"]
            keep_cols += [c for c in self.SAVANT_GAP_COLUMNS if c in df.columns]
            df = df[keep_cols].copy()

            df["g_id_int"] = df["game_pk"]
            df["ab_ind"] = df["at_bat_number"] - 1
            df["p_ind"] = df["pitch_number"]
            df = df.drop(columns=["game_pk", "at_bat_number", "pitch_number"])

            frames.append(df)

        self.savant_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        return self

    def merge_savant_data(self, resave=True):

        if self.all_pitch_df is None or getattr(self, "savant_df", None) is None or self.savant_df.empty:
            return self

        self.all_pitch_df = self.all_pitch_df.merge(
            self.savant_df, on=["g_id_int", "ab_ind", "p_ind"], how="left"
        )

        if resave:
            if self.as_type == "db":
                self.all_pitch_df.to_sql(name="pitches", con=self.db_cnx, if_exists="replace")
            elif self.as_type == "csv":
                self.all_pitch_df.to_csv(self.save_csv_loc + "_pitches.csv")

        return self

    def build_game_dictionary(self, game_json):

        def get_pitch_dict(pitches, ind_tuple):

            out_p_list = []
            g_id, ab_ind = ind_tuple
            for pi_ind, pitch in enumerate(pitches):
                out_p_dict = {}
                out_p_dict["g_id_int"] = g_id
                out_p_dict["ab_ind"] = ab_ind
                out_p_dict["p_ind"] = pitch["pitchNumber"]
                out_p_dict["code"] = pitch["details"]["call"].pop("code", None)
                out_p_dict["call"] = pitch["details"]["call"].pop("description", None)
                type = pitch["details"].pop("type", None)
                if type is not None:
                    out_p_dict["type"] = type.pop("code", None)
                else:
                    out_p_dict["type"] = None
                if pi_ind > 0:
                    out_p_dict["strikes"] = prev_pitch_count.pop("strikes", None)
                    out_p_dict["balls"] = prev_pitch_count.pop("balls", None)
                else:
                    out_p_dict["strikes"] = 0
                    out_p_dict["balls"] = 0
                for val in list(pitch["pitchData"].keys()):
                    if val == "coordinates":
                        temp_dict = pitch["pitchData"]["coordinates"]
                        for tval in list(temp_dict.keys()):
                            out_p_dict[tval] = temp_dict.pop(tval, None)
                    elif val == "breaks":
                        temp_dict = pitch["pitchData"]["breaks"]
                        for tval in list(temp_dict.keys()):
                            out_p_dict[tval] = temp_dict.pop(tval, None)
                    else:
                        out_p_dict[val] = pitch["pitchData"].pop(val, None)
                hit_data_dict = pitch.pop("hitData", None)
                if hit_data_dict is not None:
                    for val in list(hit_data_dict.keys()):
                        if val == "coordinates":
                            temp_dict = hit_data_dict["coordinates"]
                            for tval in list(temp_dict.keys()):
                                out_p_dict[tval] = temp_dict.pop(tval, None)
                        else:
                            out_p_dict[val] = hit_data_dict.pop(val, None)
                else:
                    for val in ["launchSpeed", "launchAngle", "totalDistance", "trajectory", "hardness", "location", "coordX", "coordY"]:
                        out_p_dict[val] = None

                prev_pitch_count = pitch["count"]

                out_p_list.append(out_p_dict)

            return out_p_list

        def get_runners(move_list, prior_base_dict):

            if len(move_list) == 1 and move_list[0]["movement"]["isOut"] is True:
                return prior_base_dict
            else:
                new_base_dict = {"on1b": None, "on2b": None, "on3b": None}
                unique_moves = [(runner["details"]["runner"]["id"], runner["movement"]["start"], runner["movement"]["end"], runner["movement"]["isOut"]) for runner in move_list]
                unique_runners = list(set([r[0] for r in unique_moves]))
                unique_priors = list(set(prior_base_dict.values()))
                non_movers = [rn for rn in unique_priors if rn not in unique_runners and rn != None]
                if len(non_movers) > 0:
                    for nm in non_movers:
                        base = [k for k in list(prior_base_dict.keys()) if prior_base_dict[k] == nm][0]
                        new_base_dict[base] = nm
                for ur in unique_runners:
                    ur_ends = [r[2] for r in unique_moves if r[0] == ur]
                    ur_outs = [r[3] for r in unique_moves if r[0] == ur]
                    if not any([ure == "score" for ure in ur_ends]) and not any([uro for uro in ur_outs]):
                        on_base = str(max([int(ure[0]) for ure in ur_ends if ure is not None]))
                        new_base_dict["on" + on_base + "b"] = ur
                return new_base_dict

        game_data = game_json["gameData"]

        plays = game_json["liveData"]["plays"]["allPlays"]

        if len(plays) > 0:
            if game_json["gameData"]["status"]["statusCode"] != "FT":
                winner = game_json["liveData"]["decisions"]["winner"]["id"]
                loser = game_json["liveData"]["decisions"]["loser"]["id"]
            else:
                winner, loser = None, None

            game_dict = {
                "g_id_int": game_data["game"]["pk"],
                "g_id_str": game_data["game"]["id"].replace("/", "_").replace("-","_").replace("mlb", ""),
                "game_date": int(game_data["datetime"]["originalDate"].replace("-", "")),
                "home_team": game_data["teams"]["home"]["id"],
                "ht_win_pct": game_data["teams"]["home"]["record"]["winningPercentage"],
                "ht_gms_plyd": game_data["teams"]["home"]["record"]["gamesPlayed"],
                "away_team": game_data["teams"]["away"]["id"],
                "at_win_pct": game_data["teams"]["away"]["record"]["winningPercentage"],
                "at_gms_plyd": game_data["teams"]["away"]["record"]["gamesPlayed"],
                "stadium": game_data["venue"]["id"],
                "day_night": game_data["datetime"].get("dayNight", None),
                "weather_condition": game_data["weather"].pop("condition", None),
                "winning_pitcher": winner, #game_json["liveData"]["decisions"]["winner"]["id"],
                "losing_pitcher": loser #game_json["liveData"]["decisions"]["loser"]["id"]
            }

            temp_raw = game_data["weather"].pop("temp", None)
            game_dict["temperature"] = int(temp_raw) if temp_raw not in (None, "") else None

            wind_raw = game_data["weather"].pop("wind", None) or ""
            wind_speed_str, _, wind_direction_str = wind_raw.partition(",")
            wind_speed_str = wind_speed_str.strip().split(" ")[0]
            game_dict["wind_speed"] = int(wind_speed_str) if wind_speed_str.isdigit() else None
            game_dict["wind_direction"] = wind_direction_str.strip() or None
            plays_by_inning = [(pbi_dict["top"], pbi_dict["bottom"]) for pbi_dict in game_json["liveData"]["plays"]["playsByInning"]]
            all_ab_list = []
            for inning_inds in plays_by_inning:
                for half_inds in inning_inds:
                    for temp_ind, play_ind in enumerate(half_inds):
                        play = plays[play_ind]
                        ab_info_dict = {}
                        ab_info_dict["g_id_int"] = game_dict["g_id_int"]
                        ab_info_dict["ab_ind"] = play["atBatIndex"]

                        for res_val in ["eventType", "description"]:
                            ab_info_dict[res_val] = play["result"].pop(res_val, None)

                        if temp_ind > 0:
                            for res_val in ["awayScore", "homeScore"]:
                                ab_info_dict[res_val] = previous_play_res[res_val]
                            ab_info_dict["outs"] = prev_outs
                        else:
                            ab_info_dict["awayScore"] = 0
                            ab_info_dict["homeScore"] = 0
                            ab_info_dict["outs"] = 0

                        if temp_ind > 0:
                            if temp_ind == 1:
                                twice_previous_runners = {"on1b": None, "on2b": None, "on3b": None}
                            else:
                                twice_previous_runners = prev_play_runners_on
                            runners_on = get_runners(previous_play_runners, twice_previous_runners)
                        else:
                            runners_on = {"on1b": None, "on2b": None, "on3b": None}
                        for key_val in list(runners_on.keys()):
                            ab_info_dict[key_val] = runners_on[key_val]

                        for abt_val in ["inning", "halfInning", "startTime", "endTime"]:
                            if "Time" in abt_val:
                                tv = play["about"].pop(abt_val, None)
                                if tv is not None:
                                    ab_info_dict[abt_val] = datetime.strptime(tv[:-5], "%Y-%m-%dT%H:%M:%S")
                                    ab_info_dict[abt_val + "_int"] = int(tv[11:-5].replace(":", ""))
                                else:
                                    ab_info_dict[abt_val] = tv
                            else:
                                ab_info_dict[abt_val] = play["about"].pop(abt_val, None)

                        ab_info_dict["batter_id"] = play["matchup"]["batter"].pop("id", None)
                        ab_info_dict["batter_stance"] = play["matchup"]["batSide"].pop("code", None)
                        ab_info_dict["pitcher_id"] = play["matchup"]["pitcher"].pop("id", None)
                        ab_info_dict["pitcher_hand"] = play["matchup"]["pitchHand"].pop("code", None)

                        pitches = [ev for ev in play["playEvents"] if ev.get("isPitch") and "pitchData" in ev]

                        ab_ind_tuple = (ab_info_dict["g_id_int"], ab_info_dict["ab_ind"])
                        ab_info_dict["pitches"] = get_pitch_dict(pitches, ab_ind_tuple)

                        all_ab_list.append(ab_info_dict)

                        previous_play_res = play["result"]
                        previous_play_runners = play["runners"]
                        prev_play_runners_on = runners_on
                        prev_outs = play["count"]["outs"]

            game_dict.update({"at_bats": all_ab_list})
        else:
            game_dict = None

        return game_dict

    def build_game_dataframes(self, game_json):
        game_dict = self.build_game_dictionary(game_json)

        if game_dict is not None:
            ab_list = game_dict.pop("at_bats")

            pl_temp = [ab.pop("pitches") for ab in ab_list]
            pitch_list = [p for pl in pl_temp for p in pl]

            game_ind = game_dict["g_id_int"]
            game_df = pd.DataFrame(game_dict, index=[game_ind])

            ab_ind = [ab["ab_ind"] for ab in ab_list]
            ab_df = pd.DataFrame(ab_list, index=ab_ind)

            p_ind = [p["p_ind"] for p in pitch_list]
            pitch_df = pd.DataFrame(pitch_list, index=p_ind)

            return game_df, ab_df, pitch_df
        else:
            return None, None, None

    def get_player_data(self):

        player_dict = {}
        if self.as_type == "csv":
            batter_vals = pd.read_csv(self.save_csv_loc + "_abs.csv")["batter_id"].unique()
            pitcher_vals = pd.read_csv(self.save_csv_loc + "_abs.csv")["pitcher_id"].unique()
        elif self.as_type == "db":
            batter_vals = pd.read_sql("select distinct batter_id from abs", self.db_cnx)["batter_id"].unique()
            pitcher_vals = pd.read_sql("select distinct pitcher_id from abs", self.db_cnx)["pitcher_id"].unique()
        else:
            batter_vals = self.all_ab_df["batter_id"].unique()
            pitcher_vals = self.all_ab_df["pitcher_id"].unique()

        player_list = list(set(batter_vals.tolist() + pitcher_vals.tolist()))

        for plyr_id in player_list:
            url = "https://statsapi.mlb.com/api/v1/people/" + str(plyr_id)
            id_dict = self.get_raw_url_data(url)
            people = json.loads(id_dict).get("people", [])
            if not people:
                continue
            plyr_dict = people[0]
            temp_dict = {}

            plyr_dict_vals = ["id", "firstName", "lastName", "birthDate", "birthCountry", "height", "weight", "draftYear", "strikeZoneTop", "strikeZoneBottom"]
            for val in plyr_dict_vals:
                temp_dict[val] = plyr_dict.get(val)
            for pval, pval_val in plyr_dict.get("primaryPosition", {}).items():
                temp_dict["pos" + pval] = pval_val
            temp_dict["batHand"] = plyr_dict.get("batSide", {}).get("code")
            temp_dict["pitchHand"] = plyr_dict.get("pitchHand", {}).get("code")
            player_dict[plyr_id] = temp_dict

        player_df = pd.DataFrame.from_dict(player_dict, orient="index")

        if self.as_type == "db":
            player_df.to_sql(name="players", con=self.db_cnx)
        elif self.as_type == "csv":
            player_df.to_csv(self.save_csv_loc + "_players.csv")
        else:
            self.player_df = player_df
            return self

def main():

    pfxs = MlbApiScraper(days=[1, 30], months=[3, 9], seasons=[2024], as_type="db", db_name="mlb_pitch_data_2024", save_dir="data")

    print("scraping statsapi game data...", flush=True)
    pfxs.get_all_api_game_dfs()

    print("fetching savant supplemental data...", flush=True)
    pfxs.get_savant_supplemental_data()

    print("merging savant data onto pitches...", flush=True)
    pfxs.merge_savant_data()

    print("done", flush=True)

if __name__ == "__main__":
    main()
