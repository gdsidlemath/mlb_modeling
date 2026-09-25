"""Build data/mlb_pitch_data_test.db: a small, duplicate-free fixture db cut
from the real season dbs, used by the test suite.

Two date slices from two seasons, so tests exercise multi-season history
(career carry-over, season decay) and not just a single month. The previous
fixture had duplicate games/at-bats/pitches (it predates the scraper's
postponed-game dedup fix); if it's still present it is kept as
mlb_pitch_data_test.dirty.db rather than overwritten.

Run from the repo root: python utils/make_test_db.py
"""

import os
import sqlite3

DATA_DIR = "data"
OUT_NAME = "mlb_pitch_data_test.db"
DIRTY_NAME = "mlb_pitch_data_test.dirty.db"

# (source db, first game_date, last game_date), inclusive
SLICES = [
    ("mlb_pitch_data_2023.db", 20230920, 20230930),
    ("mlb_pitch_data_2024.db", 20240328, 20240407),
]

TABLE_KEYS = {
    "games": ["g_id_int"],
    "abs": ["g_id_int", "ab_ind"],
    "pitches": ["g_id_int", "ab_ind", "p_ind"],
}


def _columns(cnx, schema, table):
    return [row[1] for row in cnx.execute(f"pragma {schema}.table_info({table})")]


def _copy_slice(cnx, table, where):
    """Append src.<table> rows matching `where` into main.<table>, creating
    the table on first use and adding any columns this season has that an
    earlier one didn't (Savant columns vary by season)."""

    src_cols = _columns(cnx, "src", table)
    main_cols = _columns(cnx, "main", table)

    if not main_cols:
        cnx.execute(f"create table main.{table} as select * from src.{table} where 0")
        main_cols = src_cols
    for col in src_cols:
        if col not in main_cols:
            cnx.execute(f'alter table main.{table} add column "{col}"')

    col_list = ", ".join(f'"{c}"' for c in src_cols)
    cnx.execute(f"insert into main.{table} ({col_list}) select {col_list} from src.{table} where {where}")


def main():

    out_path = os.path.join(DATA_DIR, OUT_NAME)
    dirty_path = os.path.join(DATA_DIR, DIRTY_NAME)
    if os.path.exists(out_path):
        if os.path.exists(dirty_path):
            os.remove(out_path)
        else:
            os.rename(out_path, dirty_path)

    cnx = sqlite3.connect(out_path)
    for db_name, first, last in SLICES:
        cnx.execute("attach database ? as src", (os.path.join(DATA_DIR, db_name),))
        game_filter = f"game_date between {first} and {last}"
        in_games = f"g_id_int in (select g_id_int from src.games where {game_filter})"
        _copy_slice(cnx, "games", game_filter)
        _copy_slice(cnx, "abs", in_games)
        _copy_slice(cnx, "pitches", in_games)
        cnx.commit()
        cnx.execute("detach database src")

    for table, keys in TABLE_KEYS.items():
        key_list = ", ".join(keys)
        n, n_distinct = cnx.execute(
            f"select count(*), (select count(*) from (select 1 from {table} group by {key_list})) from {table}"
        ).fetchone()
        assert n == n_distinct, f"{table}: {n - n_distinct} duplicate {key_list} rows"
        print(f"{table}: {n} rows")

    print("date range:", cnx.execute("select min(game_date), max(game_date) from games").fetchone())
    for role in ["pitcher_id", "batter_id"]:
        top = cnx.execute(
            f"select a.{role}, count(*) from pitches p join abs a using (g_id_int, ab_ind) "
            f"group by a.{role} order by 2 desc, 1 limit 3"
        ).fetchall()
        print(f"top {role}s (id, pitches):", top)

    cnx.execute("vacuum")
    cnx.close()


if __name__ == "__main__":
    main()
