"""
Parlay Recommender — Builds optimized weekly parlay recommendations.

Orchestrates the full pipeline:
  1. Pull live odds from The Odds API
  2. Detect edges across all markets
  3. Build optimized parlay slates (best value, safer, long shots)
  4. Line-shop each leg for the best sportsbook price
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config import (
    CURRENT_SEASON,
    MIN_EDGE_THRESHOLD,
    PARLAY_TEMPLATES,
    RESPONSIBLE_GAMBLING_NOTE,
)
from engine.parlay import ParlayEngine
from engine.line_shopping import find_best_odds, find_best_prop_odds
from ingestion.odds import pull_game_odds, pull_player_props

logger = logging.getLogger("parlay_assister.engine.recommender")


class ParlayRecommender:
    """
    Top-level recommendation engine.

    Call `generate_weekly_slate()` to get a complete set of parlay
    recommendations for the upcoming NFL week.
    """

    def __init__(self, min_edge: float = MIN_EDGE_THRESHOLD):
        self.engine = ParlayEngine(min_edge=min_edge)
        self.min_edge = min_edge

    def generate_weekly_slate(
        self,
        season: int = CURRENT_SEASON,
        week: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Dict:
        """
        Generate a complete weekly parlay recommendation slate.

        Returns a dict with:
            - game_edges: Best game-level edges (ML, spreads, totals)
            - prop_edges: Best player prop edges
            - recommended_parlays: Auto-built parlays by template
            - line_shopping: Best price per market across books
            - games: Summary of this week's games
            - metadata: Timestamp, parameters, disclaimers
        """
        logger.info(f"Generating weekly slate: season={season}, week={week}")

        # 1. Pull live odds
        game_odds = pull_game_odds(season, week, overwrite=force_refresh)
        player_props = pull_player_props(season, week, overwrite=force_refresh)

        # 2. Detect edges
        game_edges = self.engine.find_game_edges(game_odds)
        prop_edges = self.engine.find_prop_edges(player_props)

        # 3. Line shopping
        best_game_prices = find_best_odds(game_odds)
        best_prop_prices = find_best_prop_odds(player_props)

        # 4. Build recommended parlays
        all_edges = self._combine_edges(game_edges, prop_edges)
        recommended_parlays = self._build_parlay_slate(all_edges)

        # 5. Games summary
        games_summary = self._summarize_games(game_odds)

        # 6. Try to enrich with Polymarket data
        polymarket_data = self._fetch_polymarket_context()

        return {
            "game_edges": game_edges.to_dict("records") if not game_edges.empty else [],
            "prop_edges": prop_edges.to_dict("records") if not prop_edges.empty else [],
            "recommended_parlays": recommended_parlays,
            "line_shopping": {
                "games": best_game_prices.to_dict("records") if not best_game_prices.empty else [],
                "props": best_prop_prices.to_dict("records") if not best_prop_prices.empty else [],
            },
            "games": games_summary,
            "polymarket": polymarket_data,
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "season": season,
                "week": week,
                "min_edge": self.min_edge,
                "total_game_edges": len(game_edges),
                "total_prop_edges": len(prop_edges),
                "total_parlays": len(recommended_parlays),
                "disclaimer": RESPONSIBLE_GAMBLING_NOTE,
            },
        }

    def _combine_edges(
        self,
        game_edges: pd.DataFrame,
        prop_edges: pd.DataFrame,
    ) -> List[Dict]:
        """Combine game and prop edges into a single sorted list."""
        all_edges = []

        if not game_edges.empty:
            for _, row in game_edges.iterrows():
                edge = row.to_dict()
                edge["label"] = (
                    f"{row.get('outcome', '')} "
                    f"({row.get('market', '')}"
                    f"{' ' + str(row.get('point', '')) if row.get('point') else ''})"
                )
                all_edges.append(edge)

        if not prop_edges.empty:
            for _, row in prop_edges.iterrows():
                edge = row.to_dict()
                edge["label"] = (
                    f"{row.get('player_name', '')} "
                    f"{row.get('side', '')} {row.get('line', '')} "
                    f"{_format_prop_type(row.get('prop_type', ''))}"
                )
                all_edges.append(edge)

        # Sort by edge descending
        all_edges.sort(key=lambda x: x.get("edge", 0), reverse=True)
        return all_edges

    def _build_parlay_slate(self, all_edges: List[Dict]) -> List[Dict]:
        """
        Build recommended parlays from the top edges.

        Creates parlays matching each template (best value, safer, long shot).
        Avoids putting highly correlated legs (same game) together unless
        it's a deliberate SGP.
        """
        if not all_edges:
            return []

        parlays = []

        for template_key, template in PARLAY_TEMPLATES.items():
            target_legs = template["legs"]
            min_edge = template["min_edge"]
            label = template["label"]

            # Filter edges meeting this template's min edge
            eligible = [e for e in all_edges if e.get("edge", 0) >= min_edge]
            if not eligible:
                continue

            if isinstance(target_legs, tuple):
                # Range of legs (e.g., 4-6 for long shots)
                min_legs, max_legs = target_legs
                n_legs = min(max_legs, len(eligible))
                if n_legs < min_legs:
                    continue
            else:
                n_legs = target_legs
                if len(eligible) < n_legs:
                    continue

            # Pick top N by edge, preferring cross-game diversity
            selected = self._select_diverse_legs(eligible, n_legs)

            # Evaluate the parlay
            parlay_eval = self.engine.evaluate_parlay(selected)
            parlay_eval["template"] = label
            parlay_eval["template_key"] = template_key
            parlays.append(parlay_eval)

        return parlays

    def _select_diverse_legs(
        self, edges: List[Dict], n_legs: int
    ) -> List[Dict]:
        """
        Select legs for a parlay, preferring cross-game diversity.

        Tries to avoid stacking too many legs from the same game
        (unless few games are available).
        """
        selected = []
        used_games = set()

        # First pass: pick top edges from different games
        for edge in edges:
            if len(selected) >= n_legs:
                break
            game_id = edge.get("game_id", "")
            if game_id not in used_games:
                selected.append(edge)
                if game_id:
                    used_games.add(game_id)

        # Second pass: fill remaining slots regardless of game
        if len(selected) < n_legs:
            for edge in edges:
                if len(selected) >= n_legs:
                    break
                if edge not in selected:
                    selected.append(edge)

        return selected[:n_legs]

    def _summarize_games(self, game_odds: pd.DataFrame) -> List[Dict]:
        """Create a summary of this week's games from the odds data."""
        if game_odds.empty:
            return []

        games = []
        seen = set()
        for _, row in game_odds.iterrows():
            game_id = row.get("game_id", "")
            if game_id in seen:
                continue
            seen.add(game_id)
            games.append({
                "game_id": game_id,
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "commence_time": row.get("commence_time"),
                "season": row.get("season"),
                "week": row.get("week"),
            })
        return games

    def _fetch_polymarket_context(self) -> List[Dict]:
        """Fetch Polymarket NFL market data for supplemental context."""
        try:
            from ingestion.polymarket import fetch_nfl_markets, extract_implied_probabilities
            markets = fetch_nfl_markets(active_only=True, limit=50)
            poly_df = extract_implied_probabilities(markets)
            if poly_df.empty:
                return []
            return poly_df.to_dict("records")
        except Exception as e:
            logger.warning(f"Could not fetch Polymarket data: {e}")
            return []


def _format_prop_type(prop_type: str) -> str:
    """Convert API prop type keys to human-readable labels."""
    labels = {
        "player_pass_yds": "Pass Yards",
        "player_pass_tds": "Pass TDs",
        "player_pass_completions": "Completions",
        "player_pass_attempts": "Pass Attempts",
        "player_rush_yds": "Rush Yards",
        "player_rush_attempts": "Rush Attempts",
        "player_rush_tds": "Rush TDs",
        "player_reception_yds": "Rec Yards",
        "player_receptions": "Receptions",
        "player_reception_tds": "Rec TDs",
        "player_kicking_points": "Kicker Points",
        "player_tackles_assists": "Tackles+Assists",
    }
    return labels.get(prop_type, prop_type.replace("player_", "").replace("_", " ").title())
