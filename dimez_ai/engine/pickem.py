"""Build same-operator DFS pick'em cards from transparent line advantages."""
from collections import defaultdict
from statistics import median
from config import DFS_OPERATORS, TARGET_SPORTSBOOKS


def find_line_advantages(records):
    groups = defaultdict(list)
    for row in records:
        if row.get("market_type") == "player_prop" and not str(row.get("market_key", "")).endswith("_alternate"):
            groups[(row["event_id"], row["market_key"], row.get("player_name"), row.get("side"))].append(row)
    advantages = []
    for offers in groups.values():
        sportsbook_lines = {}
        for offer in offers:
            if offer["sportsbook"] in TARGET_SPORTSBOOKS:
                sportsbook_lines.setdefault(offer["sportsbook"], float(offer["line"]))
        if len(sportsbook_lines) < 2:
            continue
        reference = median(sportsbook_lines.values())
        for offer in offers:
            if offer["sportsbook"] not in DFS_OPERATORS or offer.get("side") not in {"Over", "Under"}:
                continue
            line = float(offer["line"])
            advantage = reference - line if offer["side"] == "Over" else line - reference
            relative = advantage / max(abs(reference), 1.0)
            # Exclude nonstandard promotions/outliers (for example a 0.5 pass-yard line).
            if advantage <= 0 or relative > 0.50:
                continue
            advantages.append({
                "operator": offer["sportsbook"], "event_id": offer["event_id"], "home_team": offer.get("home_team"),
                "away_team": offer.get("away_team"), "commence_time": offer.get("commence_time"),
                "player_name": offer.get("player_name"), "market_key": offer["market_key"], "side": offer["side"],
                "line": line, "sportsbook_reference_line": reference, "reference_books": sorted(sportsbook_lines),
                "line_advantage": advantage, "line_advantage_pct": relative, "indicative_american_odds": offer["american_odds"],
                "indicative_decimal_odds": offer["decimal_odds"], "retrieved_at": offer.get("retrieved_at"),
            })
    # Keep only the stronger side if both sides for one player/market somehow qualify.
    best = {}
    for item in advantages:
        key = (item["operator"], item["event_id"], item["player_name"], item["market_key"])
        if key not in best or item["line_advantage_pct"] > best[key]["line_advantage_pct"]:
            best[key] = item
    return sorted(best.values(), key=lambda item: (item["line_advantage_pct"], item["line_advantage"]), reverse=True)


def generate_pickem_cards(records):
    candidates = find_line_advantages(records); cards = []
    for operator in DFS_OPERATORS:
        eligible = [item for item in candidates if item["operator"] == operator]
        for size in (2, 3, 4):
            selected, used_players, used_events = [], set(), set()
            for prefer_new_event in (True, False):
                for item in eligible:
                    if len(selected) >= size: break
                    if item["player_name"] in used_players or item in selected: continue
                    if prefer_new_event and item["event_id"] in used_events: continue
                    selected.append(item); used_players.add(item["player_name"]); used_events.add(item["event_id"])
                if len(selected) >= size: break
            if len(selected) != size: continue
            cards.append({
                "operator": operator, "type": f"{size}_pick", "leg_count": size, "legs": selected,
                "basis": "Each line is more favorable than the median exact market line from at least two sportsbooks.",
                "pricing_note": "DFS payouts and multipliers can change with selections; no combined payout or EV is asserted.",
                "retrieved_at": max(item["retrieved_at"] or "" for item in selected),
            })
    return cards
