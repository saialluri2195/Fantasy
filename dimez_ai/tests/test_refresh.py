import json
from pathlib import Path
import pytest
from ingestion.odds_source import OddsSource
from service import RefreshService
from storage.repository import Repository
FIXTURE=Path(__file__).parents[1]/"data/fixtures/odds_api_nfl.json"
def test_fixture_refresh_and_failed_refresh_preserves_good_data(tmp_path):
    repo=Repository(tmp_path/"test.db"); service=RefreshService(repo,OddsSource(tmp_path/"cache")); result=service.refresh(fixture=FIXTURE)
    assert result["status"]=="success" and repo.latest_run()["id"]==result["refresh_id"] and repo.list_json("recommendations")
    assert repo.list_json("line_shopping")
    bad=tmp_path/"bad.json"; bad.write_text("[]")
    with pytest.raises(ValueError): service.refresh(fixture=bad)
    assert repo.latest_run()["id"]==result["refresh_id"] and repo.latest_run(any_status=True)["status"]=="failed"
def test_refresh_lock(tmp_path):
    service=RefreshService(Repository(tmp_path/"x.db"),OddsSource(tmp_path/"c")); assert service._lock.acquire(False)
    try:
        from service import RefreshInProgress
        with pytest.raises(RefreshInProgress): service.refresh(fixture=FIXTURE)
    finally: service._lock.release()
