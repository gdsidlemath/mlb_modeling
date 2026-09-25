import os
import sqlite3

SEASON_DBS = {
    2022: "mlb_pitch_data_2022.db",
    2023: "mlb_pitch_data_2023.db",
    2024: "mlb_pitch_data_2024.db",
    2025: "mlb_pitch_data_2025.db",
}

PITCH_COUNT_QUERY = """
select a.pitcher_id, count(*) as n_pitches
from pitches p
join abs a on p.g_id_int = a.g_id_int and p.ab_ind = a.ab_ind
group by a.pitcher_id
"""


def pitch_counts_by_season(data_dir="data", season_dbs=None):
    """{season: {pitcher_id: n_pitches}} for every season database found."""

    season_dbs = season_dbs or SEASON_DBS

    counts = {}
    for season, db_name in season_dbs.items():
        db_path = os.path.join(data_dir, db_name)
        if not os.path.exists(db_path):
            continue

        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute(PITCH_COUNT_QUERY)
        counts[season] = dict(cur.fetchall())
        con.close()

    return counts


def total_pitch_counts(data_dir="data", season_dbs=None):
    """{pitcher_id: total_n_pitches} summed across every season found."""

    totals = {}
    for season_counts in pitch_counts_by_season(data_dir, season_dbs).values():
        for pitcher_id, n in season_counts.items():
            totals[pitcher_id] = totals.get(pitcher_id, 0) + n

    return totals


def top_pitcher(data_dir="data", season_dbs=None):
    """(pitcher_id, total_n_pitches) for the pitcher with the most pitches
    across every season database found."""

    totals = total_pitch_counts(data_dir, season_dbs)
    return max(totals.items(), key=lambda kv: kv[1])


if __name__ == "__main__":
    by_season = pitch_counts_by_season()
    totals = {}
    for season_counts in by_season.values():
        for pitcher_id, n in season_counts.items():
            totals[pitcher_id] = totals.get(pitcher_id, 0) + n

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)

    print("top 10 pitchers by total pitches across all seasons found:")
    for pitcher_id, total in ranked[:10]:
        breakdown = ", ".join(
            f"{season}={by_season[season].get(pitcher_id, 0)}" for season in sorted(by_season)
        )
        print(f"  {pitcher_id}: {total} ({breakdown})")
