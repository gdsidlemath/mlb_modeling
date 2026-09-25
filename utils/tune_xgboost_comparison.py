import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MlbBuildModelData import BuildMlbModelData
from MlbPitchPredictionModel import PitchPredictionModel

SEASON_DBS = {
    2022: "mlb_pitch_data_2022.db",
    2023: "mlb_pitch_data_2023.db",
    2024: "mlb_pitch_data_2024.db",
    2025: "mlb_pitch_data_2025.db",
}


def load_pitcher_df(pitcher_id, data_dir="data", season_dbs=None):
    """Concatenate one pitcher's feature frame across every season db found,
    sorted back into chronological order."""

    season_dbs = season_dbs or SEASON_DBS

    frames = []
    for season, db_name in season_dbs.items():
        db_path = os.path.join(data_dir, db_name)
        if not os.path.exists(db_path):
            continue
        load_name = db_name[:-3] if db_name.endswith(".db") else db_name
        builder = BuildMlbModelData(data_as_type="db", load_dir=data_dir, load_name=load_name)
        frames.append(builder.build_pitcher_data(pitcher_id))

    pitcher_df = pd.concat(frames, ignore_index=True)
    pitcher_df = pitcher_df.sort_values(["game_date", "g_id_int", "ab_ind", "p_ind"]).reset_index(drop=True)
    return pitcher_df


def compare(pitcher_id, tune_val_frac=0.15, random_state=0):
    pitcher_df = load_pitcher_df(pitcher_id)
    print(f"total pitches for {pitcher_id}: {len(pitcher_df)}", flush=True)

    t0 = time.time()
    tuned = PitchPredictionModel(classifier="xgboost", tune_xgboost=True,
                                  tune_val_frac=tune_val_frac, random_state=random_state)
    tuned.fit(pitcher_df)
    tuned_results = tuned.evaluate()
    tuned_elapsed = time.time() - t0

    print("\n=== xgboost (tuned) ===")
    print(f"fit+eval time: {tuned_elapsed:.1f} s")
    print(f"best params: {tuned.best_xgb_params_}")
    print(f"accuracy: {tuned_results['accuracy']:.4f}")
    print(f"baseline_accuracy: {tuned_results['baseline_accuracy']:.4f}")
    print("top 10 feature importances:")
    print(tuned_results["feature_importances"].head(10))
    print("\ntuning grid results (top 8 by val accuracy):")
    print(tuned.tuning_results_.head(8).to_string(index=False))

    return tuned, tuned_results


if __name__ == "__main__":
    PITCHER_ID = 657277  # Logan Webb, most total pitches across 2022-2025
    compare(PITCHER_ID)
