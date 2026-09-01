import json
from pathlib import Path
from engine.normalization import normalize_odds
from engine.recommendations import rank_candidates
def test_best_exact_line_price_and_consensus():
    data=json.loads((Path(__file__).parents[1]/"data/fixtures/odds_api_nfl.json").read_text()); rows,_=normalize_odds(data); candidates,shopping=rank_candidates(rows)
    kc=next(x for x in shopping if x["selection"]=="Kansas City Chiefs"); assert kc["best_sportsbook"]=="draftkings" and kc["best_american_odds"]==130 and kc["books_supporting_consensus"]==3
