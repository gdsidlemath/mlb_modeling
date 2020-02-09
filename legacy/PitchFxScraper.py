from __future__ import division
from itertools import product
from lxml import etree
from lxml import html
from bs4 import BeautifulSoup
from scipy import stats
import numpy as np
import requests
import re
from datetime import datetime
import pickle
#from definedataclass import GamePitchData
import time
import sys
import traceback
import xml.etree.ElementTree as ET
import pandas as pd
import xmltodict
import json
from IPython import embed

class PitchFxScraper:

    def __init__(self,
                 seasons=None,
                 months=None,
                 days=None,
                 teams=None):

        if seasons is None:
            seasons = [2009, 2019]
        if months is None:
            months = [3, 11]
        if days is None:
            days = [1, 31]

        # *** include all values within intervals ***
        for i, timeval in enumerate([seasons, months, days]):
            if isinstance(timeval, (list, tuple)):
                if len(timeval) == 2 and np.abs(timeval[1] - timeval[0]) > 2:  # interval
                    newval = list(range(timeval[0], timeval[1] + 1))
                else:  # normal list
                    newval = timeval
            else:  # integer has to be made to a list for looping
                newval = [timeval]

            if i == 0:
                seasons = newval
            elif i == 1:
                months = newval
            elif i == 2:
                days = newval

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

    def get_raw_url_data(self,
                         url):

        page = requests.get(url)

        return page.content

    def get_api_id_data(self):

        if len(self.days) == 1 and len(self.months) == 1 and len(self.seasons) == 1:
            start_date = str(self.months[0]).zfill(2) + "/" + str(self.days[0]).zfill(2) + "/" + str(self.seasons[0])
            end_date = start_date
        else:
            start_date = str(min(self.months)).zfill(2) + "/" + str(min(self.days)).zfill(2) + "/" + str(min(self.seasons))
            end_date = str(max(self.months)).zfill(2) + "/" + str(max(self.days)).zfill(2) + "/" + str(max(self.seasons))

        url = "https://statsapi.mlb.com/api/v1/schedule/?sportId=1&startDate=" + start_date + "&endDate=" + end_date

        raw = self.get_raw_url_data(url)

        raw_json = json.loads(raw)

        return raw_json

    def get_api_game_data(self, gid):

        url = "https://statsapi.mlb.com/api/v1.1/game/" + gid + "/feed/live"

        raw = self.get_raw_url_data(url)

        raw_json = json.loads(raw)

        return raw_json

    def get_all_api_game_dfs(self):

        base_data = self.get_api_id_data()

        day_dicts = [d["games"] for d in base_data["dates"]]

        temp_id_list = []

        for d_dict in day_dicts:
            day_gid_list = [b["gamePk"] for b in d_dict]
            temp_id_list.append(day_gid_list)

        all_id_list = [gid for gid_list in temp_id_list for gid in gid_list]

        print(all_id_list)

    def get_game_list_by_day(self,
                             day,
                             month,
                             year):

        opening_day = self.opening_day_dict[year]

        if datetime(year, month, day) >= datetime(year, opening_day[0], opening_day[1]):

            url = "http://gd2.mlb.com/components/game/mlb/year_" + str(year) + "/month_" + str(month).zfill(2) + "/day_" + str(day).zfill(2)

            url_content = self.get_raw_url_data(url)

            soup_games = BeautifulSoup(url_content, "xml").find_all("a", string=re.compile("gid"))

            games_list = []
            for g in soup_games:
                del g["href"]
                gid_string = str(g).replace("<a>", "").replace("</a>", "")[:-1]
                if len(self.teams) < 30:  # Full list has 30 teams
                    if any([tm_nm in gid_string for tm_nm in self.teams]):
                        games_list.append(gid_string)
                else:
                    games_list.append(gid_string)

            return games_list

        else:

            return []

    def get_game_atbat_data(self,
                            game_id):

        def update_ab_dict(tp_dict, year):

            tp_dict.update({"pitches": list(ab.iter())[1:]})
            if year < 2019:
                tp_dict.update({"start_ab_time": datetime.strptime(tp_dict["start_tfs_zulu"], "%Y-%m-%dT%H:%M:%SZ")})
                tp_dict.update({"end_ab_time": datetime.strptime(tp_dict["end_tfs_zulu"], "%Y-%m-%dT%H:%M:%SZ")})
                tp_dict.update({"bheight_inches": 12 * int(tp_dict["b_height"].split("-")[0]) + int(tp_dict["b_height"].split("-")[-1])})
            else:
                tp_dict.update({"start_ab_time": datetime.strptime(tp_dict["start_tfs_zulu"][:-5], "%Y-%m-%dT%H:%M:%S")}) #.000Z")})
                tp_dict.update({"end_ab_time": datetime.strptime(tp_dict["end_tfs_zulu"][:-5], "%Y-%m-%dT%H:%M:%S")}) #.000Z")})
                tp_dict.update({"bheight_inches": 12 * int(tp_dict["b_height"].split("' ")[0]) + int(tp_dict["b_height"].split("' ")[-1])})
            duration = tp_dict["end_ab_time"] - tp_dict["start_ab_time"]
            tp_dict.update({"ab_time_length": np.round(duration.total_seconds(), 2)})
            tp_dict.update({"p_int": int(tp_dict["pitcher"])})
            tp_dict.update({"b_int": int(tp_dict["batter"])})
            tp_dict.update({"stance": int(tp_dict["stand"] == "R")})
            tp_dict.update({"throws": int(tp_dict["p_throws"] == "R")})

            score_diff = int(tp_dict["home_team_runs"]) - int(tp_dict["away_team_runs"])
            if tp_dict["half"] == 1:
                score_diff = -1 * score_diff
            tp_dict.update({"p_score_diff": score_diff})

            return tp_dict

        year = game_id[4:8]
        month = game_id[9:11]
        day = game_id[12:14]
        away_team = game_id[15:18]
        home_team = game_id[22:25]
        dbhd_num = game_id[-1]  # double header number

        short_gid = away_team + "_at_" + home_team + "_" + dbhd_num + "_on_" + year[-2:] + month + day

        day_string = "year_" + year + "/month_" + month + "/day_" + day + "/"

        url = "http://gd2.mlb.com/components/game/mlb/" + day_string + game_id + "/inning/inning_all.xml"

        url_content = self.get_raw_url_data(url)

        root = ET.fromstring(url_content)

        if root.tag == "Error":

            return None

        else:

            top_list = [e for e in list(root.iter()) if e.tag == "top"]
            bottom_list = [e for e in list(root.iter()) if e.tag == "bottom"]

            top_atbat_list0 = [[e for e in list(tope.iter()) if e.tag == "atbat"] for tope in top_list]
            bot_atbat_list0 = [[e for e in list(bote.iter()) if e.tag == "atbat"] for bote in bottom_list]

            top_atbat_list = [item for sublist in top_atbat_list0 for item in sublist]
            bot_atbat_list = [item for sublist in bot_atbat_list0 for item in sublist]

            atbat_list = top_atbat_list + bot_atbat_list

            ab_val_remove_list = ["num", "des_es", "event_es", "play_guid", "event_num",
                                  "start_tfs_zulu", "end_tfs_zulu", "pitcher", "batter", "stand", "p_throws",
                                  "b", "s", "start_ab_time", "end_ab_time", "score"]

            ab_dict = {}
            for ab in atbat_list:
                temp_dict = ab.attrib
                if any(ab == tab for tab in top_atbat_list):
                    temp_dict.update({"half": "T"})
                else:
                    temp_dict.update({"half": "B"})
                temp_dict = update_ab_dict(temp_dict, int(year))
                id_val = int(temp_dict["start_tfs"])
                for rm_val in ab_val_remove_list:
                    temp_dict.pop(rm_val, None)
                ab_dict[id_val] = temp_dict

            home_ab_num = 0
            away_ab_num = 0
            tot_ab = 0

            for t_key in sorted(ab_dict.keys()):
                if ab_dict[t_key]["half"] == "T":
                    ab_dict[t_key].update({"ab_num": away_ab_num})
                    away_ab_num += 1
                else:
                    ab_dict[t_key].update({"ab_num": home_ab_num})
                    home_ab_num += 1
                ab_dict[tot_ab] = ab_dict.pop(t_key)
                tot_ab += 1

            return (ab_dict, short_gid)

    def build_game_dataframe(self,
                             ab_dict):

        all_ab_df = pd.DataFrame()
        for ab_num in ab_dict.keys():
            single_ab = ab_dict[ab_num]
            single_ab["ab_des"] = single_ab.pop("des", None)
            pitches = single_ab.pop("pitches", None)
            p_dict_list = [p.attrib for p in pitches if p.tag == "pitch"]
            ab_df_temp = pd.DataFrame(len(p_dict_list) * [single_ab], index=len(p_dict_list) * [ab_num])
            for pi, p_dict in enumerate(p_dict_list):
                [p_dict.pop(val, None) for val in ["play_guid", "des_es", "mt", "tfs_zulu", "event2_es", "cc", "sv_id"]]
            p_df = pd.DataFrame(p_dict_list, index=len(p_dict_list) * [ab_num])
            ab_df = pd.concat([ab_df_temp, p_df], axis=1)
            all_cols = list(all_ab_df.columns)
            p_cols = list(ab_df.columns)
            all_missing = list(set(p_cols).difference(all_cols))
            for acm in all_missing:
                all_ab_df[acm] = np.nan
            p_missing = list(set(all_cols).difference(p_cols))
            for pcm in p_missing:
                ab_df[pcm] = np.nan
            all_ab_df = pd.concat([all_ab_df, ab_df], axis=0, sort=False)

        all_ab_df = all_ab_df.reset_index().rename(columns={"index": "game_ab_num"})
        # all_ab_df["game_id"] = gid

        return all_ab_df

    def get_all_game_dfs(self):

        all_df_list = []
        for year, month, day in list(product(self.seasons, self.months, self.days)):
            print(year, " ", month, " ", day)
            opening_day = self.opening_day_dict[year]
            if datetime(year, month, day) >= datetime(year, opening_day[0], opening_day[1]):
                gid_list = self.get_game_list_by_day(day, month, year)
                day_df_list = []
                print(gid_list)
                for gid in gid_list:
                    ret_val = self.get_game_atbat_data(gid.strip())
                    if ret_val is not None:
                        ab_dict, ugid = ret_val
                        pitch_df = self.build_game_dataframe(ab_dict)
                        day_df_list.append(pitch_df)
                    print(gid)
                all_day_df = pd.concat(day_df_list, keys=gid_list, axis=0, sort=False)
                all_df_list.append(all_day_df)
        all_game_df = pd.concat(all_df_list, axis=0, sort=False)

        print(all_game_df.shape)

        return all_game_df


def build_zone(sztop, szbot, px, py, stand):  # Find what zone each pitch was thrown in

    maxh = np.max(py)
    minh = np.min(py)

    maxw = np.max(px)
    minw = np.min(px)

    szright = 17 / 2
    szleft = -17 / 2

    bboxright = 29 / 2
    bboxleft = -29 / 2

    szwsplit = (1 / 3) * (17)

    zone = []

    for i in range(0, len(px)):

        sztopt = sztop[i]
        szbott = szbot[i]

        pxt = px[i]
        pyt = py[i]

        """print stand[i]
        print [sztopt,szbott,szright,szleft]
        print [pxt,pyt]"""

        szhdiff = sztopt - szbott
        szhmid = (1 / 2) * szhdiff + szbott
        szhsplit = (1 / 3) * szhdiff

        if "L" in stand[i]:
            if (pxt >= szleft and pxt < szleft + szwsplit and pyt <= sztopt and pyt >= sztopt - szhsplit):
                zone.append(1)
            elif (pxt >= szleft + szwsplit and pxt < szleft + 2 * szwsplit and pyt <= sztopt and pyt >= sztopt - szhsplit):
                zone.append(2)
            elif (pxt >= szleft + 2 * szwsplit and pxt <= szright and pyt <= sztopt and pyt >= sztopt - szhsplit):
                zone.append(3)
            elif (pxt >= szleft and pxt < szleft + szwsplit and pyt < sztopt - szhsplit and pyt >= sztopt - 2 * szhsplit):
                zone.append(4)
            elif (pxt >= szleft + szwsplit and pxt < szleft + 2 * szwsplit and pyt < sztopt - szhsplit and pyt >= sztopt - 2 * szhsplit):
                zone.append(5)
            elif (pxt >= szleft + 2 * szwsplit and pxt <= szright and pyt < sztopt - szhsplit and pyt >= sztopt - 2 * szhsplit):
                zone.append(6)
            elif (pxt >= szleft and pxt < szleft + szwsplit and pyt <= sztopt - 2 * szhsplit and pyt >= szbott):
                zone.append(7)
            elif (pxt >= szleft + szwsplit and pxt < szleft + 2 * szwsplit and pyt <= sztopt - 2 * szhsplit and pyt >= szbott):
                zone.append(8)
            elif (pxt >= szleft + 2 * szwsplit and pxt <= szright and pyt <= sztopt - 2 * szhsplit and pyt >= szbott):
                zone.append(9)
            elif (pxt >= bboxleft and pxt < 0 and pyt <= maxh and pyt > szhmid):
                zone.append(10)
            elif (pxt >= 0 and pxt <= bboxright and pyt <= maxh and pyt > szhmid):
                zone.append(11)
            elif (pxt >= bboxleft and pxt < 0 and pyt <= szhmid and pyt > 0):
                zone.append(12)
            elif (pxt >= 0 and pxt <= bboxright and pyt <= szhmid and pyt > 0):
                zone.append(13)
            elif (pxt >= minw and pxt < bboxleft and pyt <= maxh and pyt > szhmid):
                zone.append(14)
            elif (pxt > bboxright and pxt <= maxw and pyt <= maxh and pyt > szhmid):
                zone.append(15)
            elif (pxt >= minw and pxt < bboxleft and pyt <= szhmid and pyt > 0):
                zone.append(16)
            elif (pxt > bboxright and pxt <= maxw and pyt <= szhmid and pyt > 0):
                zone.append(17)
            elif (py < 0):
                zone.append(18)
            else:
                zone.append(0)

        else:

            if (pxt >= szleft and pxt < szleft + szwsplit and pyt <= sztopt and pyt >= sztopt - szhsplit):
                zone.append(3)
            elif (pxt >= szleft + szwsplit and pxt < szleft + 2 * szwsplit and pyt <= sztopt and pyt >= sztopt - szhsplit):
                zone.append(2)
            elif (pxt >= szleft + 2 * szwsplit and pxt <= szright and pyt <= sztopt and pyt >= sztopt - szhsplit):
                zone.append(1)
            elif (pxt >= szleft and pxt < szleft + szwsplit and pyt < sztopt - szhsplit and pyt >= sztopt - 2 * szhsplit):
                zone.append(6)
            elif (pxt >= szleft + szwsplit and pxt < szleft + 2 * szwsplit and pyt < sztopt - szhsplit and pyt >= sztopt - 2 * szhsplit):
                zone.append(5)
            elif (pxt >= szleft + 2 * szwsplit and pxt <= szright and pyt < sztopt - szhsplit and pyt >= sztopt - 2 * szhsplit):
                zone.append(4)
            elif (pxt >= szleft and pxt < szleft + szwsplit and pyt <= sztopt - 2 * szhsplit and pyt >= szbott):
                zone.append(9)
            elif (pxt >= szleft + szwsplit and pxt < szleft + 2 * szwsplit and pyt <= sztopt - 2 * szhsplit and pyt >= szbott):
                zone.append(8)
            elif (pxt >= szleft + 2 * szwsplit and pxt <= szright and pyt <= sztopt - 2 * szhsplit and pyt >= szbott):
                zone.append(7)
            elif (pxt >= bboxleft and pxt < 0 and pyt <= maxh and pyt > szhmid):
                zone.append(11)
            elif (pxt >= 0 and pxt <= bboxright and pyt <= maxh and pyt > szhmid):
                zone.append(10)
            elif (pxt >= bboxleft and pxt < 0 and pyt <= szhmid and pyt > 0):
                zone.append(13)
            elif (pxt >= 0 and pxt <= bboxright and pyt <= szhmid and pyt > 0):
                zone.append(12)
            elif (pxt >= minw and pxt < bboxleft and pyt <= maxh and pyt > szhmid):
                zone.append(15)
            elif (pxt > bboxright and pxt <= maxw and pyt <= maxh and pyt > szhmid):
                zone.append(14)
            elif (pxt >= minw and pxt < bboxleft and pyt <= szhmid and pyt > 0):
                zone.append(17)
            elif (pxt > bboxright and pxt <= maxw and pyt <= szhmid and pyt > 0):
                zone.append(16)
            elif (py < 0):
                zone.append(18)
            else:
                zone.append(0)

    # print zone[i]

    return zone


def main():

    pfxs = PitchFxScraper(days=[10, 18], months=4, seasons=2019)  # days=[10, 13], months=[8, 9], seasons=2019)

    pfxs.get_all_api_game_dfs()

    #print(json.dumps(pfxs.get_api_id_data(), indent=4))
    #pfxs.get_game_list_by_day(3, 1, 2019)

    #pitch_df = pfxs.get_all_game_dfs()

    '''ab_dict, use_gid = pfxs.get_game_atbat_data("gid_2017_04_14_pitmlb_chnmlb_1")

    pitch_df = pfxs.build_game_dataframe(ab_dict, use_gid)'''

    #pitch_df.to_csv("all_pitch_data.csv")

if __name__ == "__main__":

    main()



