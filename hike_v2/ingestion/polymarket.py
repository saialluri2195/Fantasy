"""
Polymarket Ingestion — Fetch NFL market data from Polymarket (free, no API key).

Gamma API (public): market discovery, metadata, current prices
CLOB API (public): historical price data

All read operations require no authentication.
"""

import logging
from typing import Dict, List, Optional

import pandas as pd
import requests

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from config import POLYMARKET_GAMMA_API_URL, POLYMARKET_CLOB_API_URL, RAW_DATA_DIR
from ingestion.utils import (
    DataSourceError,
    ensure_not_empty,
    log_data_quality,
    save_versioned,
    version_path,
)

logger = logging.getLogger("hike_v2.ingestion.polymarket")


def _gamma_request(endpoint: str, params: dict = None) -> list:
    """Make a GET request to the Polymarket Gamma API."""
    url = f"{POLYMARKET_GAMMA_API_URL}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 429:
            raise DataSourceError("Polymarket Gamma API rate limited") from e
        raise DataSourceError(f"Gamma API error {resp.status_code}: {e}") from e
    except requests.exceptions.RequestException as e:
        raise DataSourceError(f"Gamma API request failed: {e}") from e


def _clob_request(endpoint: str, params: dict = None) -> dict:
    """Make a GET request to the Polymarket CLOB API."""
    url = f"{POLYMARKET_CLOB_API_URL}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 429:
            raise DataSourceError("Polymarket CLOB API rate limited") from e
        raise DataSourceError(f"CLOB API error {resp.status_code}: {e}") from e
    except requests.exceptions.RequestException as e:
        raise DataSourceError(f"CLOB API request failed: {e}") from e


def fetch_nfl_markets(
    active_only: bool = True,
    limit: int = 100,
) -> List[dict]:
    """
    Fetch NFL markets from Polymarket Gamma API.

    Returns list of market dicts with question, outcomePrices, clobTokenIds, etc.
    """
    params = {
        "limit": limit,
        "tag": "nfl",
    }
    if active_only:
        params["active"] = "true"

    markets = _gamma_request("markets", params)
    logger.info(f"Fetched {len(markets)} NFL markets from Polymarket")
    return markets


def fetch_event_markets(event_slug: str) -> List[dict]:
    """Fetch all markets for a specific event by slug."""
    data = _gamma_request(f"events/slug/{event_slug}")
    return data.get("markets", []) if isinstance(data, dict) else []


def fetch_market_price_history(
    market_id: str,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Fetch historical price data for a Polymarket market.

    Returns DataFrame with columns: timestamp, price.
    """
    params = {"market": market_id, "interval": interval}
    if start_ts:
        params["startTs"] = start_ts
    if end_ts:
        params["endTs"] = end_ts

    data = _clob_request("prices-history", params)
    history = data.get("history", [])

    if not history:
        return pd.DataFrame(columns=["timestamp", "price"])

    df = pd.DataFrame(history)
    df.rename(columns={"t": "timestamp", "p": "price"}, inplace=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    return df


def extract_implied_probabilities(
    markets: List[dict],
) -> pd.DataFrame:
    """
    Extract YES-outcome implied probabilities from Polymarket markets.

    Polymarket prices are direct implied probabilities (0.00-1.00).
    No vig removal needed — prices are set by the order book.

    Returns DataFrame with columns:
        question, condition_id, yes_price, no_price, volume_24hr
    """
    rows = []
    for m in markets:
        prices = m.get("outcomePrices")
        if prices and len(prices) >= 2:
            yes_price = float(prices[0])
            no_price = float(prices[1])
        else:
            continue

        rows.append({
            "question": m.get("question", ""),
            "condition_id": m.get("conditionId", ""),
            "yes_price": yes_price,
            "no_price": no_price,
            "implied_prob_no_vig": yes_price,
            "volume_24hr": float(m.get("volume24hr", 0)),
            "liquidity": float(m.get("liquidity", 0)),
        })

    df = pd.DataFrame(rows)
    return df


def pull_polymarket_nfl_prices(
    season: int,
    overwrite: bool = False,
) -> pd.DataFrame:
    """
    Pull current Polymarket NFL market prices.

    Returns DataFrame of implied probabilities from Polymarket.
    Falls back to sample data if API is unreachable.
    """
    poly_dir = RAW_DATA_DIR / "odds"
    filepath = version_path(poly_dir, "polymarket_prices", season, 0)

    if filepath.exists() and not overwrite:
        logger.info(f"Polymarket prices for {season} already cached.")
        return pd.read_parquet(filepath)

    try:
        markets = fetch_nfl_markets(active_only=True, limit=200)
        df = extract_implied_probabilities(markets)
        ensure_not_empty(df, f"polymarket_prices_{season}")
    except (DataSourceError, requests.RequestException) as e:
        logger.warning(f"Cannot reach Polymarket API ({e}). Using sample data.")
        df = _generate_sample_polymarket_prices()
    except Exception as e:
        logger.warning(f"Unexpected error fetching Polymarket data ({e}). Using sample data.")
        df = _generate_sample_polymarket_prices()

    log_data_quality(df, f"polymarket_prices_{season}")
    save_versioned(df, poly_dir, "polymarket_prices", season, 0, overwrite=True)
    return df


def _generate_sample_polymarket_prices() -> pd.DataFrame:
    """Generate sample Polymarket prices for development/testing."""
    import numpy as np

    sample_markets = [
        "Chiefs vs Bills winner",
        "49ers vs Cowboys winner",
        "Eagles vs Packers winner",
        "Ravens vs Bengals winner",
        "Patrick Mahomes passing TDs over 2.5",
        "Josh Allen passing TDs over 2.5",
        "Christian McCaffrey rushing TDs over 1.5",
        "Tyreek Hill receiving yards over 75.5",
    ]
    rows = []
    rng = np.random.default_rng(42)
    for question in sample_markets:
        yes_price = round(rng.uniform(0.35, 0.75), 4)
        rows.append({
            "question": question,
            "condition_id": f"cond_{hash(question) % 10**8:08x}",
            "yes_price": yes_price,
            "no_price": round(1 - yes_price, 4),
            "implied_prob_no_vig": yes_price,
            "volume_24hr": round(rng.uniform(10000, 500000), 0),
            "liquidity": round(rng.uniform(5000, 100000), 0),
        })
    return pd.DataFrame(rows)
