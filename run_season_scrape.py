import sys

from MlbApiScraper import MlbApiScraper


def main():

    season = int(sys.argv[1])
    start_month, start_day = int(sys.argv[2]), int(sys.argv[3])
    end_month, end_day = int(sys.argv[4]), int(sys.argv[5])
    db_name = sys.argv[6]

    pfxs = MlbApiScraper(
        days=[start_day, end_day], months=[start_month, end_month], seasons=[season],
        as_type="db", db_name=db_name, save_dir="data",
    )

    print(f"scraping statsapi game data for {season}...", flush=True)
    pfxs.get_all_api_game_dfs()

    print("fetching savant supplemental data...", flush=True)
    pfxs.get_savant_supplemental_data(chunk_days=1)

    print("merging savant data onto pitches...", flush=True)
    pfxs.merge_savant_data()

    print("done", flush=True)


if __name__ == "__main__":
    main()
