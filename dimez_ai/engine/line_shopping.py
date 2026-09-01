"""
Line Shopping Engine — Compare odds across sportsbooks to find the best price.

For every market (moneyline, spread, total, player prop), compares prices
across DraftKings, FanDuel, and BetMGM to identify the sportsbook offering
the best value for each side of the bet.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("parlay_assister.engine.line_shopping")


def american_to_decimal(odds: float) -> float:
    """Convert American odds to decimal odds."""
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)


def decimal_to_american(decimal_odds: float) -> float:
    """Convert decimal odds to American odds."""
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


def american_to_implied(odds: float) -> float:
    """Convert American odds to implied probability (with vig)."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def find_best_odds(
    odds_df: pd.DataFrame,
    market_type: str = "all",
) -> pd.DataFrame:
    """
    For each unique market/outcome, find the sportsbook with the best price.

    Args:
        odds_df: DataFrame with columns [bookmaker, market, outcome, price, ...]
        market_type: Filter to specific market ('h2h', 'spreads', 'totals', 'all')

    Returns:
        DataFrame with best price per market/outcome and the sportsbook offering it.
    """
    if odds_df.empty:
        return pd.DataFrame()

    df = odds_df.copy()
    if market_type != "all":
        df = df[df["market"] == market_type]

    if df.empty:
        return pd.DataFrame()

    # Group by game + market + outcome (+ point for spreads/totals)
    group_cols = ["game_id", "market", "outcome"]
    if "point" in df.columns:
        group_cols.append("point")

    results = []
    for group_key, group in df.groupby(group_cols, dropna=False):
        if len(group) == 0:
            continue

        # Best price = highest American odds (most favorable to bettor)
        best_idx = group["price"].idxmax()
        best_row = group.loc[best_idx]

        # All book prices for comparison
        book_prices = {
            row["bookmaker"]: row["price"]
            for _, row in group.iterrows()
        }

        results.append({
            "game_id": best_row.get("game_id"),
            "home_team": best_row.get("home_team"),
            "away_team": best_row.get("away_team"),
            "market": best_row.get("market"),
            "outcome": best_row.get("outcome"),
            "point": best_row.get("point"),
            "best_price": best_row["price"],
            "best_book": best_row["bookmaker"],
            "best_implied_prob": american_to_implied(best_row["price"]),
            "book_prices": book_prices,
            "price_spread": group["price"].max() - group["price"].min(),
            "n_books": len(group),
        })

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values("price_spread", ascending=False)
    return result_df


def find_best_prop_odds(props_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each player prop, find the sportsbook with the best over/under price.

    Returns DataFrame with best book per prop side.
    """
    if props_df.empty:
        return pd.DataFrame()

    results = []
    group_cols = ["player_name", "prop_type", "line"]
    for group_key, group in props_df.groupby(group_cols, dropna=False):
        player, prop_type, line = group_key

        # Best over price (highest American odds)
        best_over_idx = group["over_price"].idxmax()
        best_over = group.loc[best_over_idx]

        # Best under price
        best_under_idx = group["under_price"].idxmax()
        best_under = group.loc[best_under_idx]

        over_prices = {row["bookmaker"]: row["over_price"] for _, row in group.iterrows()}
        under_prices = {row["bookmaker"]: row["under_price"] for _, row in group.iterrows()}

        results.append({
            "player_name": player,
            "prop_type": prop_type,
            "line": line,
            "best_over_price": best_over["over_price"],
            "best_over_book": best_over["bookmaker"],
            "best_under_price": best_under["under_price"],
            "best_under_book": best_under["bookmaker"],
            "over_prices_by_book": over_prices,
            "under_prices_by_book": under_prices,
            "over_price_spread": group["over_price"].max() - group["over_price"].min(),
            "under_price_spread": group["under_price"].max() - group["under_price"].min(),
            "n_books": len(group),
        })

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values("over_price_spread", ascending=False)
    return result_df


def compute_line_value(
    market_odds: Dict[str, float],
    consensus_prob: float,
) -> Dict[str, float]:
    """
    For each sportsbook's odds, compute the value relative to consensus.

    Returns dict of bookmaker -> value_pct (positive = bettor edge).
    """
    values = {}
    for book, odds in market_odds.items():
        implied = american_to_implied(odds)
        # Positive value means the book's implied prob is lower than consensus
        # (i.e., better odds for the bettor)
        values[book] = round((consensus_prob - implied) * 100, 2)
    return values
