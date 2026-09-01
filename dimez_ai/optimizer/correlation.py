"""
Parlay Correlation Adjustment — Account for same-game prop correlations.
"""

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger("dimez_ai.optimizer.correlation")

# Same-game correlation estimates (based on historical analysis)
# Same-direction legs (e.g., QB over pass yards + WR over rec yards) are positively correlated
SAME_GAME_SAME_DIRECTION_CORR = 0.35
SAME_GAME_OPPOSITE_DIRECTION_CORR = -0.15
CROSS_GAME_CORR = 0.05


def adjust_parlay_probability(
    legs: List[Dict],
    leg_probs: List[float],
) -> float:
    """
    Adjust naive parlay probability for correlation between legs.

    Same-game, same-direction legs are positively correlated and should
    NOT be multiplied naively. This applies a correlation discount.

    Args:
        legs: List of leg dicts with game_id, prop_type, etc.
        leg_probs: List of individual leg probabilities

    Returns:
        Correlation-adjusted parlay probability
    """
    if len(legs) <= 1:
        return leg_probs[0] if leg_probs else 0.0

    naive_prob = np.prod(leg_probs)

    # Count same-game pairs
    game_ids = [leg.get("game_id", "") for leg in legs]
    same_game_pairs = 0
    total_pairs = 0

    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            total_pairs += 1
            if game_ids[i] and game_ids[i] == game_ids[j]:
                same_game_pairs += 1

    if same_game_pairs == 0:
        # Cross-game: minimal correlation adjustment
        discount = CROSS_GAME_CORR * total_pairs * 0.01
        return max(naive_prob * (1 - discount), 0.001)

    # Same-game correlation discount
    corr_factor = SAME_GAME_SAME_DIRECTION_CORR * same_game_pairs / total_pairs
    adjusted = naive_prob * (1 + corr_factor)

    # Cap at naive probability (correlation can only reduce independent assumption)
    adjusted = min(adjusted, naive_prob)

    # Apply conservative discount for same-game parlays
    same_game_discount = 1 - (same_game_pairs / len(legs)) * 0.15
    adjusted *= same_game_discount

    return max(adjusted, 0.001)


def compute_correlation_matrix(
    legs: List[Dict],
) -> np.ndarray:
    """
    Compute pairwise correlation matrix for parlay legs.

    Returns NxN correlation matrix.
    """
    n = len(legs)
    corr = np.eye(n)

    for i in range(n):
        for j in range(i + 1, n):
            game_i = legs[i].get("game_id", "")
            game_j = legs[j].get("game_id", "")

            if game_i and game_i == game_j:
                # Same game — check direction
                if _same_direction(legs[i], legs[j]):
                    corr[i, j] = corr[j, i] = SAME_GAME_SAME_DIRECTION_CORR
                else:
                    corr[i, j] = corr[j, i] = SAME_GAME_OPPOSITE_DIRECTION_CORR
            else:
                corr[i, j] = corr[j, i] = CROSS_GAME_CORR

    return corr


def _same_direction(leg_a: Dict, leg_b: Dict) -> bool:
    """Check if two same-game legs bet in the same direction."""
    type_a = leg_a.get("prop_type", "")
    type_b = leg_b.get("prop_type", "")

    # Passing + receiving on same team = same direction
    if "pass" in type_a and "reception" in type_b:
        return True
    if "rush" in type_a and "rush" in type_b:
        return True

    return type_a == type_b
