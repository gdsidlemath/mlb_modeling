from __future__ import division
import requests
from datetime import datetime
import pandas as pd
import json
import sqlite3 as lite
import sys

class MlbApiScraper:

    def __init__(self,
                 seasons=None,
                 months=None,
                 days=None,
                 teams=None,
                 as_db=False,
                 as_csv=False,
                 db_name="",
                 ds_name=""):

        if seasons is None:
            seasons = list(range(2010, 2020))
        elif not isinstance(seasons, (tuple, list)):
            seasons = [seasons]
        else:
            seasons = list(range(seasons[0], seasons[1] + 1))
        if months is None:
            months = [3, 11]
        elif not isinstance(months, (tuple, list)):
            months = [months]
        if days is None:
            days = [1, 30]
        elif not isinstance(days, (tuple, list)):
            days = [days]

        # *** only add "flo" distinction if interest is in specific teams ***
        if teams is not None:
            if min(seasons) < 2012:
                if any(t == "mia" for t in teams) and not any(t == "flo" for t in teams):
                    teams.append("flo")
                if any(t == "flo" for t in teams) and not any(t == "mia" for t in teams):
                    teams.append("mia")

        if teams is None:
            teams = ["ana", "nya", "bal", "cle", "chn", "was", "det", "cha", "hou",
                     "tor", "mia", "col", "mil", "min", "nyn", "ari", "oak", "bos",
                     "pit", "atl", "sdn", "cin", "sfn", "phi", "sln", "lan",
                     "tba", "sea", "tex", "kca"]

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
        self.teams = teams

        self.as_db = as_db
        self.as_csv = as_csv
        self.ds_name = ds_name
        self.db_name = db_name

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
                start_date = str(min(self.months)).zfill(2) + "/" + str(min(self.days)).zfill(2) + "/" + str(self.seasons)
                end_date = str(max(self.months)).zfill(2) + "/" + str(max(self.days)).zfill(2) + "/" + str(self.seasons)

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
            day_gid_list = [b["gamePk"] for b in d_dict if b["gameType"] in ["R", "F", "D", "L", "W"]]
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

        if self.as_db:
            connect = lite.connect(self.db_name + ".db")
            all_game_df.to_sql(name="games", con=connect)
            all_ab_df.to_sql(name="abs", con=connect)
            all_pitch_df.to_sql(name="pitches", con=connect)
        elif self.as_csv:
            all_game_df.to_csv(self.ds_name + "_games.csv")
            all_ab_df.to_csv(self.ds_name + "_abs.csv")
            all_pitch_df.to_csv(self.ds_name + "_pitches.csv")
        else:
            return all_game_df, all_ab_df, all_pitch_df

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

        batter_dict = {}
        if self.as_db:
            cnx = lite.connect(self.db_name + ".db")
            unique_batter_query = "select distinct batter_id from abs"
            batter_df = pd.read_sql(unique_batter_query, cnx)
            for bt_id in batter_df.tolist():
                url = "https://statsapi.mlb.com/api/v1/people/" + bt_id
                id_dict = self.get_raw_url_data(url)
            pass

        return []

def main():

    g_list, a_list, p_list = [], [], []
    for season in range(2010, 2020):
        cnx = lite.connect(str(season) + "_season.db")
        g_list.append(pd.read_sql("select * from games", cnx).reset_index(drop=True))
        a_list.append(pd.read_sql("select * from abs", cnx).reset_index(drop=True))
        p_list.append(pd.read_sql("select * from pitches", cnx).reset_index(drop=True))

    all_ps = pd.concat(p_list)
    all_gs = pd.concat(g_list)
    all_as = pd.concat(a_list)

    connect = lite.connect("2010_2019_seasons.db")
    all_gs.to_sql(name="games", con=connect)
    all_as.to_sql(name="abs", con=connect)
    all_ps.to_sql(name="pitches", con=connect)

    exit()
    pfxs = MlbApiScraper(days=[1, 30], months=[2, 11], seasons=[2010, 2019], as_db=True, db_name="10_19_seasons")  # days=[10, 13], months=[8, 9], seasons=2019)

    pfxs.get_all_api_game_dfs()

    exit()

    #temp0.to_csv("temp.csv")

    temp = pfxs.get_api_game_data(565932)

    temp2 = pfxs.build_game_dataframes(temp)

    #pfxs.get_game_list_by_day(3, 1, 2019)

    #pitch_df = pfxs.get_all_game_dfs()

    '''ab_dict, use_gid = pfxs.get_game_atbat_data("gid_2017_04_14_pitmlb_chnmlb_1")

    pitch_df = pfxs.build_game_dataframe(ab_dict, use_gid)'''

    #pitch_df.to_csv("all_pitch_data.csv")

if __name__ == "__main__":

    main()



