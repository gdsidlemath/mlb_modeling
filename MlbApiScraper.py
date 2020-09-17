from datetime import datetime
import json
import os
import sqlite3 as lite

import requests
import pandas as pd

class MlbApiScraper:

    def __init__(self,
                 seasons=None,
                 months=None,
                 days=None,
                 teams=None,
                 as_type=None,
                 db_name="",
                 save_dir="."):

        if seasons is None:
            seasons = list(range(2010, 2020))
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
                                 2020: (3, 26)}

        self.seasons = seasons
        self.months = months
        self.days = days
        self.teams = team_id_list

        self.as_type = as_type.lower()
        self.save_dir = save_dir
        if self.as_type == "csv":
            self.save_csv_loc = os.path.join(self.save_dir, self.db_name)
        elif self.as_type == "db":
            self.db_name = db_name
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

        all_id_list = [gid for gid_list in temp_id_list for gid in gid_list]

        all_game_list, all_ab_list, all_pitch_list = [], [], []
        for gid in all_id_list:
            raw_data = self.get_api_game_data(gid=gid)
            df_list = self.build_game_dataframes(raw_data)
            if not any([df is None for df in df_list]):
                game_df, ab_df, pitch_df = df_list
                all_game_list.append(game_df.reset_index(drop=True))
                all_ab_list.append(ab_df.reset_index(drop=True))
                all_pitch_list.append(pitch_df.reset_index(drop=True))

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
        else:
            self.all_game_df = all_game_df
            self.all_ab_df = all_ab_df
            self.all_pitch_df = all_pitch_df
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
                "weather_condition": game_data["weather"].pop("condition", None),
                "temperature": game_data["weather"].pop("temp", None),
                "wind_speed": game_data["weather"]["wind"].split(",")[0],
                "wind_direction": game_data["weather"]["wind"].split(",")[-1].strip(),
                "winning_pitcher": winner, #game_json["liveData"]["decisions"]["winner"]["id"],
                "losing_pitcher": loser #game_json["liveData"]["decisions"]["loser"]["id"]
            }
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

                        pitches = [ev for ev in play["playEvents"] if "call" in list(ev["details"].keys())]

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
            batter_df = pd.read_csv(self.csv_save_loc + "_abs.csv")["batter_id"].unique()
            pitcher_df = pd.read_csv(self.csv_save_loc + "_abs.csv")["pitcher_id"].unique()
        elif self.as_type == "db":
            unique_batter_query = "select distinct batter_id from abs"
            batter_df = pd.read_sql(unique_batter_query, self.db_cnx)
            unique_pitcher_query = "select distinct pitcher_id from abs"
            pitcher_df = pd.read_sql(unique_pitcher_query, self.db_cnx)
        else:
            batter_df = self.all_ab_df["batter_id"].unique()
            pitcher_df = self.all_ab_df["pitcher_id"].unique()

        player_list = list(set(batter_df.tolist() + pitcher_df.tolist()))

        for plyr_id in player_list:
            url = "https://statsapi.mlb.com/api/v1/people/" + str(plyr_id)
            id_dict = self.get_raw_url_data(url)
            plyr_dict = json.loads(id_dict)
            temp_dict = {}

            plyr_dict_vals = ["id", "firstName", "lastName", "birthDate", "birthCountry", "height", "weight", "draftYear", "strikeZoneTop", "strikeZoneBottom"]
            for val in plyr_dict_vals:
                temp_dict[val] = plyr_dict[val]
            plyr_pos_vals = list(plyr_dict["primaryPosition"].keys())
            for pval in plyr_pos_vals:
                temp_dict["pos" + pval] = plyr_dict["primaryPosition"][pval]
            temp_dict["batHand"] = plyr_dict["batSide"]["code"]
            temp_dict["pitchHand"] = plyr_dict["pitchHand"]["code"]
            player_dict[plyr_id] = temp_dict

        player_df = pd.DataFrame(player_dict, index=list(player_dict.keys()))

        if self.as_type == "db":
            player_df.to_sql(name="players", con=self.db_cnx)
        elif self.as_type == "csv":
            player_df.to_csv(self.save_csv_loc + "_players.csv")
        else:
            self.player_df = player_df
            return self

def main():

    pfxs = MlbApiScraper(days=[1, 30], months=[5,6], seasons=[2018, 2019], as_type="db", db_name="2010_2019_seasons_temp", save_dir="data")

    pfxs.get_all_api_game_dfs()

    pfxs.get_player_data()

if __name__ == "__main__":
    main()
