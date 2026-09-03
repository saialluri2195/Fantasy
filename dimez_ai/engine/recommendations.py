"""Deterministic line shopping, market consensus, and parlay construction."""
from collections import Counter, defaultdict
from itertools import combinations
from config import ALL_ODDS_OPERATORS, DFS_OPERATORS, MAX_HEADLINE_LEG_USES, MIN_CONSENSUS_BOOKS, MIN_EDGE_THRESHOLD, RESPONSIBLE_GAMBLING_NOTE, TARGET_SPORTSBOOKS
from engine.normalization import market_identity
from engine.odds_math import consensus_probability, decimal_to_american, edge, expected_value, independent_probability, parlay_decimal_odds

def rank_candidates(records, min_edge=MIN_EDGE_THRESHOLD):
    groups = defaultdict(list)
    for row in records: groups[market_identity(row)].append(row)
    candidates, shopping = [], []
    for identity, offers in groups.items():
        usable = [o for o in offers if o.get("fair_probability") is not None]
        consensus_offers = [o for o in usable if o["sportsbook"] in TARGET_SPORTSBOOKS]
        books = {o["sportsbook"] for o in consensus_offers}
        offered = offers if str(offers[0].get("market_key","")).startswith("player_") else [o for o in offers if o["sportsbook"] in TARGET_SPORTSBOOKS]
        best = max(offered, key=lambda o: o["decimal_odds"])
        prices = {b: None for b in ALL_ODDS_OPERATORS}; prices.update({o["sportsbook"]: o["american_odds"] for o in offers})
        shopping.append({"identity": list(identity), "event_id": best["event_id"], "market_key": best["market_key"], "market_type": best["market_type"], "selection": best["selection"],
            "player_name": best.get("player_name"), "line": best.get("line"), "best_sportsbook": best["sportsbook"],
            "best_american_odds": best["american_odds"], "home_team": best.get("home_team"), "away_team": best.get("away_team"),
            "commence_time": best.get("commence_time"), "retrieved_at": best.get("retrieved_at"), "is_dfs": best["sportsbook"] in DFS_OPERATORS,
            "prices": prices, "consensus_probability": None, "books_supporting_consensus": len(books)})
        if len(books) < MIN_CONSENSUS_BOOKS: continue
        per_book = {}
        for offer in consensus_offers: per_book.setdefault(offer["sportsbook"], offer["fair_probability"])
        consensus = consensus_probability(list(per_book.values()), MIN_CONSENSUS_BOOKS)
        shopping[-1]["consensus_probability"] = consensus
        value = edge(consensus, best["raw_implied_probability"])
        if value < min_edge: continue
        item = dict(best); item.update({"consensus_probability": consensus, "edge": value, "books_supporting_consensus": len(books),
            "other_prices": prices, "is_dfs": best["sportsbook"] in DFS_OPERATORS,
            "confidence": "high" if value >= .05 and len(books) == 3 and best["sportsbook"] not in DFS_OPERATORS else "medium" if value >= .03 else "low"})
        item["candidate_key"] = "|".join("" if v is None else str(v) for v in identity); candidates.append(item)
    candidates.sort(key=lambda x: (x["edge"], x["books_supporting_consensus"], x["consensus_probability"]), reverse=True)
    for rank, item in enumerate(candidates, 1): item["rank"] = rank
    return candidates, shopping

def conflicts(a, b):
    if a["candidate_key"] == b["candidate_key"]: return True
    if a["event_id"] != b["event_id"]: return False
    if a["market_key"] == b["market_key"]:
        if a.get("player_name") == b.get("player_name") and a.get("line") == b.get("line") and {a["selection"], b["selection"]} == {"Over", "Under"}: return True
        if a["market_key"] == "h2h" and a["selection"] != b["selection"]: return True
        if a["market_key"] in {"spreads", "totals"} and a["selection"] != b["selection"] and a.get("line") == b.get("line"): return True
    return False

def generate_parlays(candidates):
    # Build the largest category before the safer card so the diversity cap
    # cannot consume every eligible leg before a four-leg parlay is considered.
    specs = (("best_value", 2, lambda x: (x["edge"], x["consensus_probability"])),
             ("long_shot", 4, lambda x: (x["decimal_odds"], x["edge"])),
             ("safer", 3, lambda x: (x["consensus_probability"], x["edge"])))
    usage, results = Counter(), []
    for category, count, sort_key in specs:
        viable = []
        for combo in combinations(sorted(candidates, key=sort_key, reverse=True)[:12], count):
            if len({x["sportsbook"] for x in combo}) != 1: continue
            if any(conflicts(a, b) for a, b in combinations(combo, 2)) or any(usage[x["candidate_key"]] >= MAX_HEADLINE_LEG_USES for x in combo): continue
            same = sum(a["event_id"] == b["event_id"] for a, b in combinations(combo, 2)); adjustment = max(.85, 1 - .05 * same)
            indep = independent_probability(x["consensus_probability"] for x in combo); final = indep * adjustment
            odds = parlay_decimal_odds(x["decimal_odds"] for x in combo); ev = expected_value(final, odds)
            if ev > 0: viable.append(((sum(x["edge"] for x in combo), final) if category != "long_shot" else (odds, ev), combo, indep, adjustment, final, odds, ev))
        if not viable: continue
        _, combo, indep, adjustment, final, odds, ev = max(viable, key=lambda x: x[0])
        for leg in combo: usage[leg["candidate_key"]] += 1
        results.append({"type": category, "independent_probability": indep, "correlation_adjustment": adjustment, "estimated_probability": final,
            "combined_decimal_odds": odds, "combined_american_odds": decimal_to_american(odds), "expected_value": ev, "expected_profit": ev,
            "confidence": "medium" if adjustment == 1 else "low", "correlation_note": "Cross-game legs treated as independent." if adjustment == 1 else "Same-game exposure received a conservative heuristic discount.",
            "explanation": f"{count}-leg {category.replace('_', ' ')} parlay at {combo[0]['sportsbook']} with estimated {final:.1%} win probability and {ev:+.1%} EV.",
            "responsible_gambling_note": RESPONSIBLE_GAMBLING_NOTE, "legs": [dict(x) for x in combo]})
    return results
