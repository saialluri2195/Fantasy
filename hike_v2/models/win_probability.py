"""
Win Probability Model — Calibrated classifier for prop bets and spreads.
"""

import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import xgboost as xgb

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import MODEL_ARTIFACTS_DIR
from features.builder import get_feature_columns
from models.calibration import CalibratedModel, brier_score

logger = logging.getLogger("hike_v2.models.win_probability")


class WinProbabilityModel:
    """
    Calibrated classifier for prop bet win probabilities.

    Supports player props (over/under yards, receptions) and
    team props (spread cover, moneyline).
    """

    def __init__(
        self,
        prop_type: str = "player_over",
        use_gbm: bool = False,
        calibration_method: str = "isotonic",
    ):
        self.prop_type = prop_type
        self.use_gbm = use_gbm
        self.calibration_method = calibration_method
        self.model: Optional[CalibratedModel] = None
        self.feature_cols: List[str] = []
        self.is_fitted = False

    def _create_base_model(self):
        """Create the base classifier (logistic or GBM)."""
        if self.use_gbm:
            return xgb.XGBClassifier(
                n_estimators=150,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                random_state=42,
                use_label_encoder=False,
                eval_metric="logloss",
            )
        return LogisticRegression(max_iter=1000, random_state=42)

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        feature_cols: Optional[List[str]] = None,
    ) -> "WinProbabilityModel":
        """
        Train and calibrate the win probability model.

        Args:
            X: Feature DataFrame
            y: Binary target (1 = prop hit, 0 = prop missed)
            feature_cols: Feature columns to use
        """
        self.feature_cols = feature_cols or get_feature_columns(X)
        X_train = X[self.feature_cols].fillna(0)

        base = self._create_base_model()
        self.model = CalibratedModel(base, method=self.calibration_method)
        self.model.fit(X_train, y)

        self.is_fitted = True
        logger.info(
            f"Win probability model fitted ({self.prop_type}): "
            f"{len(self.feature_cols)} features, {len(y)} samples, "
            f"positive rate: {y.mean():.3f}"
        )
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated win probabilities."""
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        X_pred = X[self.feature_cols].fillna(0)
        return self.model.predict_proba(X_pred)[:, 1]

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """Evaluate model with Brier score."""
        probs = self.predict_proba(X)
        return {
            "brier_score": brier_score(y.values, probs),
            "mean_predicted_prob": float(np.mean(probs)),
            "actual_positive_rate": float(y.mean()),
            "n_samples": len(y),
        }

    def save(self, path: Optional[Path] = None) -> Path:
        """Save model to disk."""
        path = path or MODEL_ARTIFACTS_DIR / f"winprob_{self.prop_type}.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)

        artifact = {
            "prop_type": self.prop_type,
            "model": self.model,
            "feature_cols": self.feature_cols,
            "use_gbm": self.use_gbm,
            "calibration_method": self.calibration_method,
        }
        with open(path, "wb") as f:
            pickle.dump(artifact, f)

        logger.info(f"Saved win probability model to {path}")
        return path

    @classmethod
    def load(cls, path: Path) -> "WinProbabilityModel":
        """Load model from disk."""
        with open(path, "rb") as f:
            artifact = pickle.load(f)

        model = cls(
            artifact["prop_type"],
            artifact.get("use_gbm", False),
            artifact.get("calibration_method", "isotonic"),
        )
        model.model = artifact["model"]
        model.feature_cols = artifact["feature_cols"]
        model.is_fitted = True
        return model


def create_prop_labels(
    weekly_stats: pd.DataFrame,
    prop_type: str,
    line_col: str = "line",
    stat_col: str = "receiving_yards",
) -> pd.Series:
    """
    Create binary labels for prop bets from actual stats.

    Args:
        weekly_stats: Player weekly stats
        prop_type: 'over' or 'under'
        line_col: Column with the prop line (if available)
        stat_col: Column with the actual stat value

    Returns:
        Binary series (1 = prop hit)
    """
    if stat_col not in weekly_stats.columns:
        return pd.Series(0, index=weekly_stats.index)

    actual = weekly_stats[stat_col].fillna(0)

    if line_col in weekly_stats.columns:
        line = weekly_stats[line_col]
    else:
        # Use median as default line
        line = actual.median()

    if prop_type == "over":
        return (actual > line).astype(int)
    return (actual < line).astype(int)
