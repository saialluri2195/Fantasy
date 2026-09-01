"""
Walk-Forward Retraining — Retrain models incorporating each new week's results.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import MODEL_ARTIFACTS_DIR, SEASONS, POSITION_GROUPS
from models.projection import ProjectionModel, train_projection_models
from models.win_probability import WinProbabilityModel, create_prop_labels
from features.builder import build_feature_table, build_all_position_features

logger = logging.getLogger("hike_v2.models.retrain")


def retrain_projection_models(
    train_seasons: List[int],
    position_groups: Optional[List[str]] = None,
    save: bool = True,
) -> Dict[str, ProjectionModel]:
    """
    Retrain projection models on specified seasons.

    Args:
        train_seasons: Seasons to train on
        position_groups: Which positions to train (default: all)
        save: Whether to save model artifacts

    Returns:
        dict mapping position_group -> fitted ProjectionModel
    """
    positions = position_groups or POSITION_GROUPS
    logger.info(f"Retraining projection models on seasons {train_seasons}")

    feature_tables = {}
    for pos in positions:
        df = build_feature_table(pos, train_seasons, mode="train")
        if not df.empty:
            feature_tables[pos] = df

    models = train_projection_models(feature_tables)
    logger.info(f"Retrained {len(models)} projection models")
    return models


def retrain_win_probability_models(
    train_seasons: List[int],
    prop_types: Optional[List[str]] = None,
) -> Dict[str, WinProbabilityModel]:
    """
    Retrain win probability models for specified prop types.
    """
    prop_types = prop_types or [
        "player_over_receiving_yards",
        "player_over_rushing_yards",
        "player_over_passing_yards",
        "player_over_receptions",
    ]
    models = {}

    for prop_type in prop_types:
        stat_col = _prop_type_to_stat(prop_type)
        pos = _prop_type_to_position(prop_type)

        df = build_feature_table(pos, train_seasons, mode="train")
        if df.empty:
            continue

        labels = create_prop_labels(df, "over", stat_col=stat_col)
        if labels.sum() == 0:
            continue

        model = WinProbabilityModel(prop_type)
        model.fit(df, labels)
        model.save()
        models[prop_type] = model

    logger.info(f"Retrained {len(models)} win probability models")
    return models


def walk_forward_retrain(
    all_seasons: List[int],
    train_window: int = 3,
) -> Dict[int, Dict[str, ProjectionModel]]:
    """
    Walk-forward retraining: train on N seasons, roll forward.

    Returns dict mapping test_season -> models trained on prior seasons.
    """
    results = {}

    for i in range(train_window, len(all_seasons)):
        test_season = all_seasons[i]
        train_seasons = all_seasons[i - train_window:i]

        logger.info(
            f"Walk-forward: training on {train_seasons}, "
            f"testing on {test_season}"
        )

        models = retrain_projection_models(train_seasons)
        results[test_season] = models

    return results


def _prop_type_to_stat(prop_type: str) -> str:
    mapping = {
        "player_over_receiving_yards": "receiving_yards",
        "player_over_rushing_yards": "rushing_yards",
        "player_over_passing_yards": "passing_yards",
        "player_over_receptions": "receptions",
    }
    return mapping.get(prop_type, "receiving_yards")


def _prop_type_to_position(prop_type: str) -> str:
    if "passing" in prop_type:
        return "QB"
    if "rushing" in prop_type:
        return "RB"
    return "WR"