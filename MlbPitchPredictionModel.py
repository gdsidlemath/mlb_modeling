from itertools import product

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.preprocessing import LabelEncoder


class PitchPredictionModel:
    """Per-pitcher next-pitch-type classifier, trained on a BuildMlbModelData
    feature frame (see MlbBuildModelData.build_pitcher_data)."""

    # Columns that describe the CURRENT pitch's own trajectory, spin, release
    # physics, batted-ball result, or result-derived Statcast metrics (xwOBA,
    # bat speed, win expectancy delta, etc). These are only knowable after the
    # pitch is thrown/swung at, so they can never be used as predictive
    # features - only prior/context columns (counts, base state, prev_*, the
    # rolling/expanding pitch-mix columns) are fair game. Superset of
    # BuildMlbModelData.LABEL_COLUMNS.
    RESULT_COLUMNS = [
        "code", "call", "type", "startSpeed", "endSpeed",
        "aY", "aZ", "pfxX", "pfxZ", "pX", "pZ", "vX0", "vY0", "vZ0",
        "x", "y", "x0", "y0", "z0", "aX",
        "breakAngle", "breakLength", "breakY", "breakVertical",
        "breakVerticalInduced", "breakHorizontal", "spinRate", "spinDirection",
        "zone", "typeConfidence", "plateTime", "extension",
        "launchSpeed", "launchAngle", "totalDistance", "trajectory", "hardness",
        "location", "coordX", "coordY",
        "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
        "estimated_slg_using_speedangle", "woba_value", "woba_denom",
        "babip_value", "iso_value", "launch_speed_angle",
        "delta_home_win_exp", "delta_run_exp", "delta_pitcher_run_exp",
        "home_win_exp", "bat_win_exp", "bat_speed", "swing_length",
        "attack_angle", "attack_direction", "swing_path_tilt",
        "intercept_ball_minus_batter_pos_x_inches",
        "intercept_ball_minus_batter_pos_y_inches", "arm_angle", "hyper_speed",
        # Not outcome columns, but still leakage: "days until next game" is only
        # knowable after that next game is scheduled/played, which post-dates
        # this pitch. Their backward-looking siblings (*_days_since_prev_game)
        # are legitimate rest-day features and are deliberately left out of
        # this list.
        "pitcher_days_until_next_game", "batter_days_until_next_game",
    ]

    # Identifiers/join keys and raw timestamps: not predictive signal in
    # themselves.
    ID_COLUMNS = ["index", "g_id_int", "ab_ind", "p_ind", "batter_id", "pitcher_id",
                  "home_team", "away_team", "game_date", "startTime"]

    TARGET_COLUMN = "type"

    # Discrete/unordered columns. RandomForest and XGBoost get these one-hot
    # encoded (see _prepare_features_onehot); CatBoost takes them natively as
    # categorical columns instead (see _prepare_features_categorical) - no
    # one-hot expansion, which is CatBoost's main selling point here (the
    # one-hot feature space runs ~110+ columns; CatBoost's native path runs
    # ~65-85 for the same information).
    CATEGORICAL_FEATURE_COLUMNS = ["batter_stance", "pitcher_hand", "halfInning", "day_night",
                                    "weather_condition", "wind_direction",
                                    "prev_pitch_type", "prev_call", "prev_zone"]

    # Default grid searched by _tune_xgboost when tune_xgboost=True.
    XGB_PARAM_GRID = {
        "max_depth": [3, 4, 6, 8],
        "learning_rate": [0.02, 0.05, 0.1, 0.3],
    }
    XGB_MAX_ESTIMATORS = 500
    XGB_EARLY_STOPPING_ROUNDS = 20

    # Default grid searched by _tune_random_forest when tune_random_forest=True.
    # RandomForest has no boosting/early-stopping mechanism, so n_estimators
    # stays fixed at the instance's n_estimators and only tree-shape params
    # are searched.
    RF_PARAM_GRID = {
        "max_depth": [None, 10, 20, 30],
        "min_samples_leaf": [1, 2, 5, 10],
    }

    # Default grid searched by _tune_catboost when tune_catboost=True.
    CATBOOST_PARAM_GRID = {
        "depth": [4, 6, 8, 10],
        "learning_rate": [0.02, 0.05, 0.1, 0.3],
    }
    CATBOOST_MAX_ITERATIONS = 500
    CATBOOST_EARLY_STOPPING_ROUNDS = 20

    def __init__(self, classifier="random_forest", n_estimators=200, test_frac=0.25,
                 min_pitches=50, random_state=0, tune_val_frac=0.15,
                 tune_xgboost=False, xgb_param_grid=None,
                 tune_random_forest=False, rf_param_grid=None,
                 tune_catboost=False, catboost_param_grid=None):
        """classifier: 'random_forest', 'xgboost', or 'catboost'.

        tune_xgboost/tune_random_forest/tune_catboost: if True (only used
        when classifier matches), carve the tail tune_val_frac share off the
        chronological training split as a validation set and grid-search that
        classifier's param grid against it, then refit on the full training
        split with the winning params before evaluating on the held-out test
        set. The test set is never used for tuning.

        xgboost and catboost are both boosted, so their tuning searches
        max_depth(/depth)/learning_rate and uses early stopping against the
        validation set to pick the iteration count for each grid point (see
        XGB_MAX_ESTIMATORS/CATBOOST_MAX_ITERATIONS). RandomForest has no
        boosting or early-stopping concept, so its tuning instead searches
        max_depth/min_samples_leaf at a fixed n_estimators and picks the grid
        point with the best plain validation accuracy.
        """

        self.classifier = classifier
        self.n_estimators = n_estimators
        self.test_frac = test_frac
        self.min_pitches = min_pitches
        self.random_state = random_state
        self.tune_val_frac = tune_val_frac

        self.tune_xgboost = tune_xgboost
        self.xgb_param_grid = xgb_param_grid or self.XGB_PARAM_GRID
        self.tune_random_forest = tune_random_forest
        self.rf_param_grid = rf_param_grid or self.RF_PARAM_GRID
        self.tune_catboost = tune_catboost
        self.catboost_param_grid = catboost_param_grid or self.CATBOOST_PARAM_GRID

        self.model = None
        self.feature_cols = None
        self.X_test = None
        self.y_test = None
        self.train_size = None
        self.test_size = None
        self._label_encoder = None
        self.best_xgb_params_ = None
        self.best_rf_params_ = None
        self.best_catboost_params_ = None
        self.tuning_results_ = None
        self.cat_features = None

    def _build_classifier(self, **overrides):

        if self.classifier == "random_forest":
            params = {"n_estimators": self.n_estimators, "random_state": self.random_state}
            params.update(overrides)
            return RandomForestClassifier(**params)
        elif self.classifier == "xgboost":
            from xgboost import XGBClassifier
            params = {"n_estimators": self.n_estimators, "random_state": self.random_state,
                       "eval_metric": "mlogloss"}
            params.update(overrides)
            return XGBClassifier(**params)
        elif self.classifier == "catboost":
            from catboost import CatBoostClassifier
            params = {"iterations": self.n_estimators, "random_state": self.random_state,
                      "loss_function": "MultiClass", "verbose": False}
            params.update(overrides)
            return CatBoostClassifier(**params)
        else:
            raise ValueError(
                f"unknown classifier: {self.classifier!r} (expected 'random_forest', 'xgboost', or 'catboost')"
            )

    def _tune_xgboost(self, X_train, y_train):
        """Grid-search max_depth/learning_rate against a validation split cut
        from the tail of X_train/y_train (chronologically after sub-train,
        chronologically before the real test set), using early stopping to
        pick n_estimators for each combo. Returns the winning params dict."""

        from xgboost import XGBClassifier

        val_cutoff = int(len(X_train) * (1 - self.tune_val_frac))
        sub_X_train, sub_X_val = X_train.iloc[:val_cutoff], X_train.iloc[val_cutoff:]
        sub_y_train, sub_y_val = y_train.iloc[:val_cutoff], y_train.iloc[val_cutoff:]

        results = []
        best_score, best_params = -1.0, None

        for max_depth, learning_rate in product(self.xgb_param_grid["max_depth"],
                                                  self.xgb_param_grid["learning_rate"]):
            model = XGBClassifier(
                n_estimators=self.XGB_MAX_ESTIMATORS,
                max_depth=max_depth,
                learning_rate=learning_rate,
                random_state=self.random_state,
                eval_metric="mlogloss",
                early_stopping_rounds=self.XGB_EARLY_STOPPING_ROUNDS,
            )
            model.fit(sub_X_train, sub_y_train, eval_set=[(sub_X_val, sub_y_val)], verbose=False)

            n_estimators = model.best_iteration + 1
            val_preds = model.predict(sub_X_val)
            val_accuracy = accuracy_score(sub_y_val, val_preds)

            results.append({"max_depth": max_depth, "learning_rate": learning_rate,
                             "n_estimators": n_estimators, "val_accuracy": val_accuracy})

            if val_accuracy > best_score:
                best_score = val_accuracy
                best_params = {"max_depth": max_depth, "learning_rate": learning_rate,
                                "n_estimators": n_estimators}

        self.tuning_results_ = pd.DataFrame(results).sort_values("val_accuracy", ascending=False)
        self.best_xgb_params_ = best_params
        return best_params

    def _tune_random_forest(self, X_train, y_train):
        """Grid-search max_depth/min_samples_leaf against a validation split
        cut from the tail of X_train/y_train. RandomForest has no early
        stopping, so unlike _tune_xgboost/_tune_catboost each grid point is
        just fit once (at self.n_estimators) and scored on the validation
        split directly. Returns the winning params dict."""

        val_cutoff = int(len(X_train) * (1 - self.tune_val_frac))
        sub_X_train, sub_X_val = X_train.iloc[:val_cutoff], X_train.iloc[val_cutoff:]
        sub_y_train, sub_y_val = y_train.iloc[:val_cutoff], y_train.iloc[val_cutoff:]

        results = []
        best_score, best_params = -1.0, None

        for max_depth, min_samples_leaf in product(self.rf_param_grid["max_depth"],
                                                     self.rf_param_grid["min_samples_leaf"]):
            model = RandomForestClassifier(
                n_estimators=self.n_estimators,
                max_depth=max_depth,
                min_samples_leaf=min_samples_leaf,
                random_state=self.random_state,
            )
            model.fit(sub_X_train, sub_y_train)

            val_preds = model.predict(sub_X_val)
            val_accuracy = accuracy_score(sub_y_val, val_preds)

            results.append({"max_depth": max_depth, "min_samples_leaf": min_samples_leaf,
                             "val_accuracy": val_accuracy})

            if val_accuracy > best_score:
                best_score = val_accuracy
                best_params = {"max_depth": max_depth, "min_samples_leaf": min_samples_leaf}

        self.tuning_results_ = pd.DataFrame(results).sort_values("val_accuracy", ascending=False)
        self.best_rf_params_ = best_params
        return best_params

    def _tune_catboost(self, X_train, y_train, cat_features):
        """Grid-search depth/learning_rate against a validation split cut
        from the tail of X_train/y_train, using early stopping to pick
        iterations for each combo - mirrors _tune_xgboost. Returns the
        winning params dict."""

        from catboost import CatBoostClassifier

        val_cutoff = int(len(X_train) * (1 - self.tune_val_frac))
        sub_X_train, sub_X_val = X_train.iloc[:val_cutoff], X_train.iloc[val_cutoff:]
        sub_y_train, sub_y_val = y_train.iloc[:val_cutoff], y_train.iloc[val_cutoff:]

        results = []
        best_score, best_params = -1.0, None

        for depth, learning_rate in product(self.catboost_param_grid["depth"],
                                             self.catboost_param_grid["learning_rate"]):
            model = CatBoostClassifier(
                iterations=self.CATBOOST_MAX_ITERATIONS,
                depth=depth,
                learning_rate=learning_rate,
                random_state=self.random_state,
                loss_function="MultiClass",
                verbose=False,
                early_stopping_rounds=self.CATBOOST_EARLY_STOPPING_ROUNDS,
            )
            model.fit(sub_X_train, sub_y_train, cat_features=cat_features,
                      eval_set=(sub_X_val, sub_y_val), use_best_model=True)

            iterations = model.get_best_iteration() + 1
            val_preds = model.predict(sub_X_val).ravel()
            val_accuracy = accuracy_score(sub_y_val, val_preds)

            results.append({"depth": depth, "learning_rate": learning_rate,
                             "iterations": iterations, "val_accuracy": val_accuracy})

            if val_accuracy > best_score:
                best_score = val_accuracy
                best_params = {"depth": depth, "learning_rate": learning_rate, "iterations": iterations}

        self.tuning_results_ = pd.DataFrame(results).sort_values("val_accuracy", ascending=False)
        self.best_catboost_params_ = best_params
        return best_params

    def _prepare_features(self, df):
        """Dispatches to the one-hot (random_forest/xgboost) or native-categorical
        (catboost) feature prep. Returns (features, feature_cols, cat_features) -
        cat_features is always [] outside of catboost."""

        if self.classifier == "catboost":
            return self._prepare_features_categorical(df)

        features, feature_cols = self._prepare_features_onehot(df)
        return features, feature_cols, []

    def _prepare_features_onehot(self, df):

        work = df.copy()

        work["batter_stance"] = (work["batter_stance"] == "R").astype(int)
        work["pitcher_hand"] = (work["pitcher_hand"] == "R").astype(int)
        work["same_hand"] = (work["batter_stance"] == work["pitcher_hand"]).astype(int)
        work["halfInning"] = (work["halfInning"] == "top").astype(int)
        work["day_night"] = (work["day_night"] == "day").astype(int)
        for base in ["on1b", "on2b", "on3b"]:
            work[base] = work[base].notna().astype(int)

        # prev_zone is a discrete strike-zone region code (statsapi zones
        # 1-14), not an ordinal quantity, so it's one-hot encoded like
        # prev_pitch_type/prev_call rather than fed in as a raw number.
        work["prev_zone"] = work["prev_zone"].astype("Int64")

        categorical_cols = ["prev_pitch_type", "prev_call", "prev_zone",
                             "weather_condition", "wind_direction"]
        dummy_frames = [pd.get_dummies(work[c], prefix=c) for c in categorical_cols]
        work = pd.concat([work] + dummy_frames, axis=1)
        work = work.drop(columns=categorical_cols)

        drop_cols = set(self.RESULT_COLUMNS) | set(self.ID_COLUMNS)
        feature_cols = [c for c in work.columns
                         if c not in drop_cols and pd.api.types.is_numeric_dtype(work[c])]

        features = work[feature_cols].fillna(0)

        return features, feature_cols

    def _prepare_features_categorical(self, df):
        """CatBoost variant: CATEGORICAL_FEATURE_COLUMNS are kept as native
        string categories (no one-hot expansion) and passed to CatBoost as
        cat_features; everything else is numeric, same leakage exclusions as
        the one-hot path."""

        work = df.copy()
        for base in ["on1b", "on2b", "on3b"]:
            work[base] = work[base].notna().astype(int)

        drop_cols = set(self.RESULT_COLUMNS) | set(self.ID_COLUMNS)
        cat_cols = [c for c in self.CATEGORICAL_FEATURE_COLUMNS if c in work.columns]
        feature_cols = [c for c in work.columns
                         if c not in drop_cols and c != self.TARGET_COLUMN
                         and (c in cat_cols or pd.api.types.is_numeric_dtype(work[c]))]
        cat_cols = [c for c in cat_cols if c in feature_cols]

        features = work[feature_cols].copy()
        features[cat_cols] = features[cat_cols].astype(str).fillna("NA")
        numeric_cols = [c for c in feature_cols if c not in cat_cols]
        features[numeric_cols] = features[numeric_cols].fillna(0)

        return features, feature_cols, cat_cols

    def fit(self, pitcher_df):
        """pitcher_df: output of BuildMlbModelData.build_pitcher_data, already
        sorted chronologically. Splits chronologically (train on the earlier
        (1 - test_frac) share, test on the later share) so no future pitch
        ever informs a prediction earlier in time."""

        # A small share of pitches (~0.04% in scraped data) have no classified
        # pitch type (statsapi/Savant couldn't identify it). Since type is the
        # prediction target, these rows carry no trainable signal and are
        # dropped rather than left to break classifier fitting downstream.
        pitcher_df = pitcher_df[pitcher_df[self.TARGET_COLUMN].notna()]

        if len(pitcher_df) < self.min_pitches:
            raise ValueError(f"Need at least {self.min_pitches} pitches to train, got {len(pitcher_df)}")

        features, feature_cols, cat_features = self._prepare_features(pitcher_df)
        target = pitcher_df[self.TARGET_COLUMN]

        # xgboost's default multiclass objective requires 0..n-1 integer
        # labels; random forest and catboost handle the raw string pitch
        # codes natively.
        if self.classifier == "xgboost":
            self._label_encoder = LabelEncoder()
            target = pd.Series(self._label_encoder.fit_transform(target), index=target.index)

        cutoff = int(len(features) * (1 - self.test_frac))

        X_train, X_test = features.iloc[:cutoff], features.iloc[cutoff:]
        y_train, y_test = target.iloc[:cutoff], target.iloc[cutoff:]

        if self.classifier == "xgboost" and self.tune_xgboost:
            best_params = self._tune_xgboost(X_train, y_train)
            self.model = self._build_classifier(**best_params)
        elif self.classifier == "random_forest" and self.tune_random_forest:
            best_params = self._tune_random_forest(X_train, y_train)
            self.model = self._build_classifier(**best_params)
        elif self.classifier == "catboost" and self.tune_catboost:
            best_params = self._tune_catboost(X_train, y_train, cat_features)
            self.model = self._build_classifier(**best_params)
        else:
            self.model = self._build_classifier()

        if self.classifier == "catboost":
            self.model.fit(X_train, y_train, cat_features=cat_features)
        else:
            self.model.fit(X_train, y_train)

        self.feature_cols = feature_cols
        self.cat_features = cat_features
        self.X_test, self.y_test = X_test, y_test
        self.train_size, self.test_size = len(X_train), len(X_test)

        return self

    def evaluate(self):

        preds = self.model.predict(self.X_test)
        if self.classifier == "catboost":
            # CatBoost's multiclass predict() returns an (n, 1) array of
            # string labels rather than a flat 1-D array.
            preds = preds.ravel()
        y_test = self.y_test

        if self._label_encoder is not None:
            preds = self._label_encoder.inverse_transform(preds)
            y_test = self._label_encoder.inverse_transform(y_test)
            classes = self._label_encoder.classes_
        else:
            classes = self.model.classes_

        accuracy = accuracy_score(y_test, preds)
        baseline_accuracy = pd.Series(y_test).value_counts(normalize=True).max()

        cm = confusion_matrix(y_test, preds, labels=classes)
        confusion_df = pd.DataFrame(cm, index=classes, columns=classes)

        importances = pd.Series(
            self.model.feature_importances_, index=self.feature_cols
        ).sort_values(ascending=False)

        return {
            "accuracy": accuracy,
            "baseline_accuracy": baseline_accuracy,
            "confusion_matrix": confusion_df,
            "feature_importances": importances,
            "train_size": self.train_size,
            "test_size": self.test_size,
        }
