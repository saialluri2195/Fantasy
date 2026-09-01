"""
Model Calibration — Isotonic regression and Platt scaling utilities.
"""

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger("dimez_ai.models.calibration")


class CalibratedModel:
    """
    Wrapper that applies post-hoc calibration to a classifier's probabilities.
    """

    def __init__(self, base_model, method: str = "isotonic"):
        """
        Args:
            base_model: Sklearn-compatible classifier with predict_proba
            method: 'isotonic' or 'sigmoid' (Platt scaling)
        """
        self.base_model = base_model
        self.method = method
        self.calibrator = None
        self.is_fitted = False

    def fit(self, X, y):
        """Fit base model and calibrator on training data."""
        self.base_model.fit(X, y)
        raw_probs = self.base_model.predict_proba(X)[:, 1]

        if self.method == "isotonic":
            self.calibrator = IsotonicRegression(out_of_bounds="clip")
            self.calibrator.fit(raw_probs, y)
        else:
            self.calibrator = LogisticRegression()
            self.calibrator.fit(raw_probs.reshape(-1, 1), y)

        self.is_fitted = True
        return self

    def predict_proba(self, X) -> np.ndarray:
        """Return calibrated probabilities."""
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        raw_probs = self.base_model.predict_proba(X)[:, 1]

        if self.method == "isotonic":
            calibrated = self.calibrator.predict(raw_probs)
        else:
            calibrated = self.calibrator.predict_proba(
                raw_probs.reshape(-1, 1)
            )[:, 1]

        calibrated = np.clip(calibrated, 0.01, 0.99)
        return np.column_stack([1 - calibrated, calibrated])

    def predict(self, X) -> np.ndarray:
        """Return binary predictions using 0.5 threshold."""
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def compute_calibration_curve(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute calibration curve data for reliability diagram.

    Returns (fraction_of_positives, mean_predicted_value) arrays.
    """
    fraction_pos, mean_pred = calibration_curve(
        y_true, y_prob, n_bins=n_bins, strategy="uniform"
    )
    return fraction_pos, mean_pred


def plot_calibration_curve(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    label: str = "Model",
    n_bins: int = 10,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """Plot a reliability diagram comparing predicted vs actual probabilities."""
    fraction_pos, mean_pred = compute_calibration_curve(y_true, y_prob, n_bins)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
    ax.plot(mean_pred, fraction_pos, "s-", label=label)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.set_title("Calibration Curve (Reliability Diagram)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info(f"Calibration curve saved to {save_path}")

    return fig


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Compute Brier score (lower is better)."""
    return float(np.mean((y_prob - y_true) ** 2))
