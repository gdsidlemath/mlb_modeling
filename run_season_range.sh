#!/usr/bin/env bash
# Runs run_season_scrape.py sequentially for each season in the given range.
# Usage: ./run_season_range.sh <start_season> <end_season>
set -euo pipefail

start_season=${1:-2015}
end_season=${2:-2021}

for season in $(seq "$start_season" "$end_season"); do
    db_name="mlb_pitch_data_${season}"
    log_file="data/scrape_${season}.log"
    echo "=== starting season ${season} -> ${db_name} (log: ${log_file}) ==="
    python run_season_scrape.py "$season" 3 1 11 30 "$db_name" > "$log_file" 2>&1
    echo "=== finished season ${season} ==="
done
