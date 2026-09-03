"""Convert Odds API payloads into one downstream representation."""
from datetime import datetime, timezone
from typing import Any, Iterable
from collections import defaultdict
from config import ALL_ODDS_OPERATORS
from engine.odds_math import american_to_decimal, american_to_implied_probability, remove_vig

def normalize_odds(payload: Iterable[dict[str, Any]], retrieved_at: str | None = None) -> tuple[list[dict], list[str]]:
    retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    records, rejected = [], []
    for event in payload:
        event_id, home, away = str(event.get("id") or ""), event.get("home_team"), event.get("away_team")
        if not event_id or not home or not away:
            rejected.append("event missing id/home/away"); continue
        for book in event.get("bookmakers") or []:
            if book.get("key") not in ALL_ODDS_OPERATORS: continue
            for market in book.get("markets") or []:
                key, outcomes = market.get("key"), market.get("outcomes") or []
                groups = defaultdict(list)
                for outcome in outcomes:
                    try:
                        price, line = float(outcome["price"]), outcome.get("point")
                        is_prop = str(key).startswith("player_")
                        if (key in {"spreads", "totals"} or is_prop) and line is None: raise ValueError("line required")
                        if not outcome.get("name") or (is_prop and not outcome.get("description")): raise ValueError("selection/player required")
                        group_key = (outcome.get("description"), line) if is_prop else (None, None)
                        groups[group_key].append((outcome, american_to_implied_probability(price)))
                    except (KeyError, TypeError, ValueError) as exc: rejected.append(f"{event_id}/{key}: {exc}")
                for grouped in groups.values():
                    fair = None
                    if len(grouped) >= 2 and len({str(item[0].get("name")) for item in grouped}) >= 2:
                        try: fair = remove_vig([item[1] for item in grouped])
                        except ValueError: pass
                    for i, (outcome, raw_probability) in enumerate(grouped):
                        price, selection = float(outcome["price"]), str(outcome["name"])
                        is_prop = str(key).startswith("player_")
                        records.append({"event_id": event_id, "commence_time": event.get("commence_time"), "home_team": home,
                            "away_team": away, "market_key": key, "market_type": "player_prop" if is_prop else key,
                            "sportsbook": book["key"], "sportsbook_title": book.get("title") or book["key"], "selection": selection,
                            "player_name": outcome.get("description") if is_prop else None, "side": selection if selection in {"Over", "Under"} else None,
                            "line": outcome.get("point"), "american_odds": int(price), "decimal_odds": american_to_decimal(price),
                            "raw_implied_probability": raw_probability, "fair_probability": fair[i] if fair else None,
                            "consensus_probability": None, "edge": None, "retrieved_at": retrieved_at})
    return records, rejected

def market_identity(record: dict) -> tuple:
    return (record["event_id"], record["market_key"], record.get("player_name"), record["selection"], record.get("line"))
