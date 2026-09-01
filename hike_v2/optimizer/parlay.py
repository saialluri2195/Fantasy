"""
Parlay Value Finder — Detect edges where model prob exceeds market implied prob.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from config import RESPONSIBLE_GAMBLING_NOTE, POLYMARKET_GAMMA_API_URL
from models.win_probability import WinProbabilityModel
from optimizer.correlation import adjust_parlay_probability

logger = logging.getLogger("hike_v2.optimizer.parlay")


class ParlayValueFinder:
    """
    Find player/team prop legs where the model's calibrated win probability
    exceeds the sportsbook's implied probability.
    """

    def __init__(
        self,
        win_prob_models: Dict[str, WinProbabilityModel],
        min_edge: float = 0.03,
    ):
        """
        Args:
            win_prob_models: dict of prop_type -> fitted WinProbabilityModel
            min_edge: Minimum edge threshold to include a leg (default 3%)
        """
        self.models = win_prob_models
        self.min_edge = min_edge

    def find_edges(
        self,
        props_df: pd.DataFrame,
        features_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Find all prop legs with positive edge.

        Returns DataFrame sorted by edge size with columns:
            player_name, prop_type, line, model_prob, market_prob,
            edge, bookmaker, recommendation
        """
        results = []

        for _, prop in props_df.iterrows():
            prop_type = prop.get("prop_type", "player_reception_yds")
            player = prop.get("player_name", "")

            # Get model probability
            model = self._get_model_for_prop(prop_type)
            if model is None or not model.is_fitted:
                continue

            # Find matching features
            player_features = features_df[
                features_df.get("player_display_name", features_df.get("player_name", pd.Series())) == player
            ]
            if player_features.empty:
                continue

            model_prob = float(model.predict_proba(player_features)[0])
            market_prob = prop.get("over_implied_no_vig", prop.get("implied_prob_no_vig", 0.5))
            edge = model_prob - market_prob

            if edge >= self.min_edge:
                results.append({
                    "player_name": player,
                    "prop_type": prop_type,
                    "line": prop.get("line"),
                    "model_prob": round(model_prob, 4),
                    "market_prob": round(market_prob, 4),
                    "edge": round(edge, 4),
                    "edge_pct": round(edge * 100, 1),
                    "over_price": prop.get("over_price"),
                    "under_price": prop.get("under_price"),
                    "bookmaker": prop.get("bookmaker", ""),
                    "confidence": _edge_confidence(edge, model_prob),
                })

        edges = pd.DataFrame(results)
        if edges.empty:
            return edges

        edges = edges.sort_values("edge", ascending=False).reset_index(drop=True)
        edges["rank"] = range(1, len(edges) + 1)
        return edges

    def evaluate_parlay(
        self,
        legs: List[Dict],
        features_df: pd.DataFrame,
    ) -> Dict:
        """
        Evaluate a multi-leg parlay with correlation adjustment.

        Args:
            legs: List of dicts with player_name, prop_type, line, etc.
            features_df: Feature data for model predictions

        Returns:
            Dict with parlay EV, adjusted probability, and responsible gambling note
        """
        if not legs:
            return {"error": "No legs provided"}

        leg_probs = []
        leg_details = []

        for leg in legs:
            prop_type = leg.get("prop_type", "")
            player = leg.get("player_name", "")
            model = self._get_model_for_prop(prop_type)

            if model is None:
                leg_probs.append(leg.get("market_prob", 0.5))
                continue

            player_features = features_df[
                features_df.get("player_display_name", features_df.get("player_name", pd.Series())) == player
            ]
            if player_features.empty:
                leg_probs.append(leg.get("market_prob", 0.5))
                continue

            model_prob = float(model.predict_proba(player_features)[0])
            market_prob = leg.get("market_prob", 0.5)
            leg_probs.append(model_prob)

            leg_details.append({
                "player_name": player,
                "prop_type": prop_type,
                "line": leg.get("line"),
                "model_prob": round(model_prob, 4),
                "market_prob": round(market_prob, 4),
                "edge": round(model_prob - market_prob, 4),
            })

        # Naive parlay probability (independent assumption)
        naive_prob = np.prod(leg_probs)

        # Correlation-adjusted probability
        adjusted_prob = adjust_parlay_probability(legs, leg_probs)

        # Expected value calculation
        combined_odds = np.prod([
            _american_to_decimal(leg.get("over_price", -110)) for leg in legs
        ])
        parlay_ev = adjusted_prob * combined_odds - 1

        return {
            "num_legs": len(legs),
            "legs": leg_details,
            "naive_probability": round(naive_prob, 4),
            "adjusted_probability": round(adjusted_prob, 4),
            "correlation_discount": round(naive_prob - adjusted_prob, 4),
            "combined_decimal_odds": round(combined_odds, 2),
            "expected_value": round(parlay_ev, 4),
            "expected_value_pct": round(parlay_ev * 100, 1),
            "recommendation": _parlay_recommendation(parlay_ev, adjusted_prob),
            "responsible_gambling_note": RESPONSIBLE_GAMBLING_NOTE,
        }

    @staticmethod
    def display_polymarket_context(legs: List[Dict]) -> List[Dict]:
        """
        Enrich parlay legs with Polymarket market data when available.

        Adds a 'polymarket_prob' field per leg with the Polymarket
        implied probability for game-level outcomes.

        Returns legs with Polymarket data appended (no-op if API unreachable).
        """
        try:
            from ingestion.polymarket import fetch_nfl_markets, extract_implied_probabilities
            markets = fetch_nfl_markets(active_only=True, limit=50)
            poly_df = extract_implied_probabilities(markets)
            if poly_df.empty:
                return legs
        except Exception:
            return legs

        enriched = []
        for leg in legs:
            leg = dict(leg)
            player = leg.get("player_name", "").lower()
            player_words = set(player.split())

            best_match = None
            best_score = 0
            for _, row in poly_df.iterrows():
                q_words = set(row["question"].lower().split())
                overlap = len(player_words & q_words)
                if overlap > best_score:
                    best_score = overlap
                    best_match = row

            if best_match and best_score > 0:
                leg["polymarket_prob"] = best_match["implied_prob_no_vig"]
            enriched.append(leg)

        return enriched

    def _get_model_for_prop(self, prop_type: str) -> Optional[WinProbabilityModel]:
        for key, model in self.models.items():
            if prop_type in key or key in prop_type:
                return model
        return next(iter(self.models.values()), None) if self.models else None


def _american_to_decimal(odds: float) -> float:
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)


def _edge_confidence(edge: float, model_prob: float) -> str:
    if edge > 0.08 and model_prob > 0.6:
        return "high"
    if edge > 0.05:
        return "medium"
    return "low"


def _parlay_recommendation(ev: float, prob: float) -> str:
    if ev > 0.1 and prob > 0.15:
        return "Positive EV parlay — model sees value, but outcomes are uncertain"
    if ev > 0:
        return "Marginal positive EV — small edge, high variance"
    return "Negative EV — market likely has better information"
