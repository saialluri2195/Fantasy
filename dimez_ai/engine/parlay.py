"""
Parlay Value Engine — Detect edges where consensus probability diverges
from individual sportsbook implied probabilities.

This is the core parlay analysis module. It does NOT depend on ML models —
instead, it uses cross-book consensus probabilities as "true" probabilities
and flags legs where individual books offer better-than-fair odds.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config import (
    RESPONSIBLE_GAMBLING_NOTE,
    MIN_EDGE_THRESHOLD,
    CONFIDENCE_TIERS,
)
from engine.correlation import adjust_parlay_probability
from engine.line_shopping import american_to_decimal, american_to_implied

logger = logging.getLogger("parlay_assister.engine.parlay")


class ParlayEngine:
    """
    Core parlay analysis engine.

    Uses cross-book consensus probabilities (averaged no-vig probs from
    DraftKings, FanDuel, and BetMGM) as the "true" probability baseline.
    Flags individual book offerings that diverge positively from consensus.
    """

    def __init__(self, min_edge: float = MIN_EDGE_THRESHOLD):
        self.min_edge = min_edge

    # ──────────────────────────────────────────
    # Edge detection — Game Markets
    # ──────────────────────────────────────────

    def find_game_edges(self, game_odds_df: pd.DataFrame) -> pd.DataFrame:
        """
        Find edges in game-level markets (moneylines, spreads, totals).

        For each market+outcome, compute consensus no-vig probability across
        all sportsbooks, then flag any individual book whose implied prob is
        lower than consensus by at least min_edge (= better odds for bettor).

        Returns DataFrame sorted by edge size.
        """
        if game_odds_df.empty:
            return pd.DataFrame()

        group_cols = ["game_id", "market", "outcome"]
        if "point" in game_odds_df.columns:
            group_cols.append("point")

        results = []
        for group_key, group in game_odds_df.groupby(group_cols, dropna=False):
            # Consensus probability = average no-vig probability across books
            consensus_prob = group["implied_prob_no_vig"].mean()

            for _, row in group.iterrows():
                book_implied = american_to_implied(row["price"])
                # Edge = consensus "true" prob minus this book's implied prob
                # Positive edge means book is offering better odds than fair
                edge = consensus_prob - book_implied

                if edge >= self.min_edge:
                    results.append({
                        "type": "game",
                        "game_id": row.get("game_id"),
                        "home_team": row.get("home_team"),
                        "away_team": row.get("away_team"),
                        "market": row.get("market"),
                        "outcome": row.get("outcome"),
                        "point": row.get("point"),
                        "price": row.get("price"),
                        "book_implied_prob": round(book_implied, 4),
                        "consensus_prob": round(consensus_prob, 4),
                        "edge": round(edge, 4),
                        "edge_pct": round(edge * 100, 1),
                        "bookmaker": row.get("bookmaker"),
                        "confidence": _classify_confidence(edge, consensus_prob),
                        "commence_time": row.get("commence_time"),
                    })

        edges = pd.DataFrame(results)
        if not edges.empty:
            edges = edges.sort_values("edge", ascending=False).reset_index(drop=True)
            edges["rank"] = range(1, len(edges) + 1)
        return edges

    # ──────────────────────────────────────────
    # Edge detection — Player Props
    # ──────────────────────────────────────────

    def find_prop_edges(self, props_df: pd.DataFrame) -> pd.DataFrame:
        """
        Find edges in player prop markets.

        Same consensus-vs-individual-book approach as game edges.

        Returns DataFrame sorted by edge size.
        """
        if props_df.empty:
            return pd.DataFrame()

        group_cols = ["player_name", "prop_type", "line"]
        results = []

        for group_key, group in props_df.groupby(group_cols, dropna=False):
            player, prop_type, line = group_key

            # Consensus over/under probabilities
            consensus_over = group["over_implied_no_vig"].mean()
            consensus_under = group["under_implied_no_vig"].mean()

            for _, row in group.iterrows():
                over_implied = american_to_implied(row["over_price"])
                under_implied = american_to_implied(row["under_price"])

                over_edge = consensus_over - over_implied
                under_edge = consensus_under - under_implied

                # Flag over side if edge is positive
                if over_edge >= self.min_edge:
                    results.append({
                        "type": "prop",
                        "player_name": player,
                        "prop_type": prop_type,
                        "side": "Over",
                        "line": line,
                        "price": row["over_price"],
                        "book_implied_prob": round(over_implied, 4),
                        "consensus_prob": round(consensus_over, 4),
                        "edge": round(over_edge, 4),
                        "edge_pct": round(over_edge * 100, 1),
                        "bookmaker": row.get("bookmaker"),
                        "confidence": _classify_confidence(over_edge, consensus_over),
                        "game_id": row.get("game_id"),
                    })

                # Flag under side if edge is positive
                if under_edge >= self.min_edge:
                    results.append({
                        "type": "prop",
                        "player_name": player,
                        "prop_type": prop_type,
                        "side": "Under",
                        "line": line,
                        "price": row["under_price"],
                        "book_implied_prob": round(under_implied, 4),
                        "consensus_prob": round(consensus_under, 4),
                        "edge": round(under_edge, 4),
                        "edge_pct": round(under_edge * 100, 1),
                        "bookmaker": row.get("bookmaker"),
                        "confidence": _classify_confidence(under_edge, consensus_under),
                        "game_id": row.get("game_id"),
                    })

        edges = pd.DataFrame(results)
        if not edges.empty:
            edges = edges.sort_values("edge", ascending=False).reset_index(drop=True)
            edges["rank"] = range(1, len(edges) + 1)
        return edges

    # ──────────────────────────────────────────
    # Parlay evaluation
    # ──────────────────────────────────────────

    def evaluate_parlay(self, legs: List[Dict]) -> Dict:
        """
        Evaluate a multi-leg parlay with correlation adjustment.

        Args:
            legs: List of dicts with consensus_prob, price, game_id, etc.

        Returns:
            Dict with parlay EV, adjusted probability, and analysis.
        """
        if not legs:
            return {"error": "No legs provided"}

        leg_probs = [leg.get("consensus_prob", 0.5) for leg in legs]

        # Naive parlay probability (independence assumption)
        naive_prob = float(np.prod(leg_probs))

        # Correlation-adjusted probability
        adjusted_prob = adjust_parlay_probability(legs, leg_probs)

        # Combined decimal odds (what the sportsbook pays)
        combined_odds = float(np.prod([
            american_to_decimal(leg.get("price", -110)) for leg in legs
        ]))

        # Expected value: (prob of winning * payout) - cost
        parlay_ev = adjusted_prob * combined_odds - 1

        # Per-leg details
        leg_details = []
        for leg in legs:
            label = leg.get("player_name") or f"{leg.get('outcome', '')} ({leg.get('market', '')})"
            leg_details.append({
                "label": label,
                "prop_type": leg.get("prop_type", leg.get("market", "")),
                "side": leg.get("side", leg.get("outcome", "")),
                "line": leg.get("line", leg.get("point")),
                "price": leg.get("price"),
                "consensus_prob": leg.get("consensus_prob"),
                "edge": leg.get("edge"),
                "bookmaker": leg.get("bookmaker"),
            })

        return {
            "num_legs": len(legs),
            "legs": leg_details,
            "naive_probability": round(naive_prob, 4),
            "adjusted_probability": round(adjusted_prob, 4),
            "correlation_discount": round(naive_prob - adjusted_prob, 4),
            "combined_decimal_odds": round(combined_odds, 2),
            "combined_american_odds": _decimal_to_american(combined_odds),
            "expected_value": round(parlay_ev, 4),
            "expected_value_pct": round(parlay_ev * 100, 1),
            "recommendation": _parlay_recommendation(parlay_ev, adjusted_prob),
            "responsible_gambling_note": RESPONSIBLE_GAMBLING_NOTE,
        }


# ──────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────

def _classify_confidence(edge: float, prob: float) -> str:
    """Classify edge confidence tier."""
    for tier, thresholds in CONFIDENCE_TIERS.items():
        if edge >= thresholds["min_edge"] and prob >= thresholds["min_prob"]:
            return tier
    return "low"


def _decimal_to_american(decimal_odds: float) -> int:
    """Convert decimal odds to American odds."""
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1) * 100))
    if decimal_odds > 1.0:
        return int(round(-100 / (decimal_odds - 1)))
    return -100


def _parlay_recommendation(ev: float, prob: float) -> str:
    """Generate human-readable parlay recommendation."""
    if ev > 0.1 and prob > 0.15:
        return "🟢 Strong positive EV — consensus model sees real value here"
    if ev > 0.05 and prob > 0.10:
        return "🟡 Moderate positive EV — edge is there but variance is high"
    if ev > 0:
        return "🟡 Marginal positive EV — small edge, expect high variance"
    if ev > -0.05:
        return "🔴 Near break-even — no meaningful edge detected"
    return "🔴 Negative EV — market likely has better information"
