import json
from pathlib import Path
from engine.normalization import market_identity,normalize_odds
FIXTURE=Path(__file__).parents[1]/"data/fixtures/odds_api_nfl.json"
def test_normalizes_fixture_and_exact_lines():
    rows,rejected=normalize_odds(json.loads(FIXTURE.read_text()))
    assert len(rows)==30 and not rejected; assert all(r["fair_probability"] for r in rows)
    a=dict(rows[6]); b=dict(a); b["line"]=49.5
    assert market_identity(a)!=market_identity(b)
def test_rejects_bad_rows_without_crashing():
    rows,rejected=normalize_odds([{"id":"x"}]); assert rows==[] and rejected
