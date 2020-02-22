import json
import os
import sqlite3 as lite

import pandas as pd

class BuildMlbModelData:

    def __init__(self,
                 data_as_type=None,
                 load_dir="./",
                 load_name="",
                 save_as_name="",
                 save_as_type=None,
                 save_dir="./"):

        self.data_as_type = data_as_type.lower()
        self.load_dir = load_dir
        self.load_name = load_name
        if self.data_as_type == "csv":
            self.load_csv_loc = os.path.join(self.load_dir, self.load_name)
        elif self.data_as_type == "db":
            self.load_db_cnx = lite.connect(os.path.join(self.load_dir, self.load_name) + ".db")

        self.save_as_type = save_as_type.lower()
        self.save_dir = save_dir
        self.save_name = save_name
        if self.save_as_type == "csv":
            self.save_csv_loc = os.path.join(self.save_dir, self.save_name)
        elif self.save_as_type == "db":
            self.save_db_cnx = lite.connect(os.path.join(self.save_dir, self.save_name) + ".db")

    def build_pitcher_data(self, pitcher_id, date_until=None):

        pass

    def build_batter_data(self, batter_id, date_until=None):

        pass

