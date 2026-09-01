from pathlib import Path
from fastapi.testclient import TestClient
import api.main as api
from ingestion.odds_source import OddsSource
from service import RefreshService
from storage.repository import Repository
FIXTURE=Path(__file__).parents[1]/"data/fixtures/odds_api_nfl.json"
def test_api_routes(tmp_path,monkeypatch):
    repo=Repository(tmp_path/"api.db"); service=RefreshService(repo,OddsSource(tmp_path/"cache")); monkeypatch.setattr(api,"repo",repo); monkeypatch.setattr(api,"service",service)
    client=TestClient(api.app); assert client.get("/health").status_code==200
    response=client.post("/refresh",json={"fixture":str(FIXTURE)}); assert response.status_code==200
    assert client.get("/games").json()["games"]; assert client.get("/markets").json()["markets"]
    recs=client.get("/recommendations").json()["recommendations"]; assert recs
    assert client.get(f"/recommendations/{recs[0]['id']}").status_code==200
