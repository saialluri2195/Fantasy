import json
from pathlib import Path
import pytest
from ingestion.odds_source import OddsSource,OddsSourceError
FIXTURE=Path(__file__).parents[1]/"data/fixtures/odds_api_nfl.json"
def test_fixture_and_cache_modes(tmp_path):
    source=OddsSource(tmp_path); payload,meta=source.fetch(fixture=FIXTURE); assert len(payload)==4 and meta["source_mode"]=="fixture"
    source.latest_cache.write_text(json.dumps({"fetched_at":"now","payload":payload})); cached,meta=source.fetch(offline=True); assert cached==payload and meta["source_mode"]=="cache"
def test_offline_without_cache(tmp_path):
    with pytest.raises(OddsSourceError): OddsSource(tmp_path).fetch(offline=True)
