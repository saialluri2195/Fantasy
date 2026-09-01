"""Convert Odds API payloads into one downstream representation."""
from datetime import datetime, timezone
from typing import Any, Iterable
from config import TARGET_SPORTSBOOKS
from engine.odds_math import american_to_decimal, american_to_implied_probability, remove_vig

def normalize_odds(payload: Iterable[dict[str, Any]], retrieved_at: str | None = None) -> tuple[list[dict], list[str]]:
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    records, rejected = [], []
    for event in payload:
        event_id, home, away = str(event.get("id") or ""), event.get("home_team"), event.get("away_team")
        if not event_id or not home or not away:
            rejected.append("event missing id/home/away"); continue
        for book in event.get("bookmakers") or []:
            if book.get("key") not in TARGET_SPORTSBOOKS: continue
            for market in book.get("markets") or []:
                key, outcomes = market.get("key"), market.get("outcomes") or []
                raw, valid = [], []
                for outcome in outcomes:
                    try:
                        price, line = float(outcome["price"]), outcome.get("point")
                        is_prop = str(key).startswith("player_")
                        if (key in {"spreads", "totals"} or is_prop) and line is None: raise ValueError("line required")
                        if not outcome.get("name") or (is_prop and not outcome.get("description")): raise ValueError("selection/player required")
                        raw.append(american_to_implied_probability(price)); valid.append(outcome)
                    except (KeyError, TypeError, ValueError) as exc: rejected.append(f"{event_id}/{key}: {exc}")
                fair = None
                if len(valid) >= 2:
                    try: fair = remove_vig(raw)
                    except ValueError: pass
                for i, outcome in enumerate(valid):
                    price, selection = float(outcome["price"]), str(outcome["name"])
                    is_prop = str(key).startswith("player_")
                    records.append({"event_id": event_id, "commence_time": event.get("commence_time"), "home_team": home,
                        "away_team": away, "market_key": key, "market_type": "player_prop" if is_prop else key,
                        "sportsbook": book["key"], "sportsbook_title": book.get("title") or book["key"], "selection": selection,
                        "player_name": outcome.get("description") if is_prop else None, "side": selection if selection in {"Over", "Under"} else None,
                        "line": outcome.get("point"), "american_odds": int(price), "decimal_odds": american_to_decimal(price),
                        "raw_implied_probability": raw[i], "fair_probability": fair[i] if fair else None,
                        "consensus_probability": None, "edge": None, "retrieved_at": retrieved_at})
    return records, rejected

def market_identity(record: dict) -> tuple:
    return (record["event_id"], record["market_key"], record.get("player_name"), record["selection"], record.get("line"))
