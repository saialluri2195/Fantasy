import json
from pathlib import Path
import pytest
from datetime import datetime, timedelta, timezone
from ingestion.odds_source import OddsSource,OddsSourceError
FIXTURE=Path(__file__).parents[1]/"data/fixtures/odds_api_nfl.json"
def test_fixture_and_cache_modes(tmp_path):
    source=OddsSource(tmp_path); payload,meta=source.fetch(fixture=FIXTURE); assert len(payload)==4 and meta["source_mode"]=="fixture"
    source.latest_cache.write_text(json.dumps({"fetched_at":"now","payload":payload})); cached,meta=source.fetch(offline=True); assert cached==payload and meta["source_mode"]=="cache"
def test_offline_without_cache(tmp_path):
    with pytest.raises(OddsSourceError): OddsSource(tmp_path).fetch(offline=True)

def test_request_error_does_not_expose_api_key(tmp_path, monkeypatch):
    import ingestion.odds_source as module
    class FailingSession:
        @staticmethod
        def get(*args, **kwargs):
            raise module.requests.ConnectionError("https://example.test?apiKey=secret-value")
    monkeypatch.setattr(module, "ODDS_API_KEY", "secret-value")
    with pytest.raises(OddsSourceError) as error:
        OddsSource(tmp_path, session=FailingSession()).fetch(force_refresh=True)
    assert "secret-value" not in str(error.value)

def test_live_fetch_merges_near_term_player_props(tmp_path, monkeypatch):
    import ingestion.odds_source as module
    commence=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    game={"id":"event-1","home_team":"Home","away_team":"Away","commence_time":commence,
          "bookmakers":[{"key":"draftkings","title":"DraftKings","markets":[{"key":"h2h","outcomes":[{"name":"Home","price":-110},{"name":"Away","price":-110}]}]}]}
    prop={"id":"event-1","home_team":"Home","away_team":"Away","commence_time":commence,
          "bookmakers":[{"key":"underdog","title":"Underdog Fantasy","markets":[{"key":"player_pass_yds","outcomes":[
              {"name":"Over","description":"Player A","point":250.5,"price":-110},{"name":"Under","description":"Player A","point":250.5,"price":-110}]}]}]}
    class Response:
        headers={}
        def __init__(self,payload): self.payload=payload
        def raise_for_status(self): pass
        def json(self): return self.payload
    class Session:
        calls=[]
        @classmethod
        def get(cls,url,**kwargs):
            cls.calls.append((url,kwargs)); return Response(prop if "/events/event-1/" in url else [game])
    monkeypatch.setattr(module,"ODDS_API_KEY","configured")
    payload,meta=OddsSource(tmp_path,session=Session).fetch(force_refresh=True)
    assert meta["source_mode"]=="live" and meta["prop_events"]==1 and meta["prop_offers"]==2
    assert any(book["key"]=="underdog" for book in payload[0]["bookmakers"])
    assert (tmp_path/"props"/"event-1.json").exists()
