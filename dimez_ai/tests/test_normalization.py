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

def test_player_prop_vig_is_removed_per_player_and_line():
    payload=[{"id":"game","home_team":"Home","away_team":"Away","commence_time":"2030-01-01T00:00:00Z","bookmakers":[
        {"key":"draftkings","title":"DraftKings","markets":[{"key":"player_pass_yds","outcomes":[
            {"name":"Over","description":"Quarterback A","point":250.5,"price":-110},
            {"name":"Under","description":"Quarterback A","point":250.5,"price":-110},
            {"name":"Over","description":"Quarterback B","point":225.5,"price":-120},
            {"name":"Under","description":"Quarterback B","point":225.5,"price":100}
        ]}]}]}]
    rows,rejected=normalize_odds(payload)
    assert not rejected and len(rows)==4
    player_a=[row for row in rows if row["player_name"]=="Quarterback A"]
    assert sum(row["fair_probability"] for row in player_a)==1
    assert {market_identity(row) for row in player_a}=={
        ("game","player_pass_yds","Quarterback A","Over",250.5),
        ("game","player_pass_yds","Quarterback A","Under",250.5),
    }
