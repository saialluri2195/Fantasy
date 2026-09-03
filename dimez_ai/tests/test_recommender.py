import json
from pathlib import Path
from engine.normalization import normalize_odds
from engine.recommendations import conflicts,generate_parlays,rank_candidates
def fixture_candidates():
    rows,_=normalize_odds(json.loads((Path(__file__).parents[1]/"data/fixtures/odds_api_nfl.json").read_text())); return rank_candidates(rows)[0]
def test_filter_rank_confidence_and_parlays():
    candidates=fixture_candidates(); assert len(candidates)>=4 and candidates==sorted(candidates,key=lambda x:x["rank"])
    assert all(x["books_supporting_consensus"]>=2 for x in candidates)
    parlays=generate_parlays(candidates); assert {p["type"] for p in parlays}=={"best_value","safer","long_shot"}; assert all(p["expected_value"]>0 for p in parlays)
def test_conflicts_opposite_moneylines():
    a={"candidate_key":"a","event_id":"g","market_key":"h2h","selection":"A","line":None}; b={**a,"candidate_key":"b","selection":"B"}; assert conflicts(a,b)

def test_generated_parlay_uses_one_operator():
    for parlay in generate_parlays(fixture_candidates()):
        assert len({leg["sportsbook"] for leg in parlay["legs"]})==1
