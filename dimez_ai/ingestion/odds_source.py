"""Quota-conscious live, cache, offline, and fixture Odds API ingestion."""
import json, logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests
from config import GAME_MARKETS, NFL_SPORT_KEY, ODDS_API_BASE_URL, ODDS_API_KEY, RAW_DATA_DIR, TARGET_SPORTSBOOKS
logger = logging.getLogger("parlay_assister.ingestion")
class OddsSourceError(RuntimeError): pass
class OddsSource:
    def __init__(self, cache_dir: Path = RAW_DATA_DIR / "odds", session: Any = requests):
        self.cache_dir, self.session = Path(cache_dir), session; self.cache_dir.mkdir(parents=True, exist_ok=True)
    @property
    def latest_cache(self): return self.cache_dir / "latest.json"
    def fetch(self, *, fixture=None, offline=False, force_refresh=False):
        if fixture: return self._read(Path(fixture)), {"source_mode": "fixture", "path": str(fixture)}
        if offline or (self.latest_cache.exists() and not force_refresh):
            if not self.latest_cache.exists(): raise OddsSourceError("Offline mode requested but no cache exists")
            envelope = self._read(self.latest_cache); return envelope["payload"], {"source_mode": "cache", "fetched_at": envelope.get("fetched_at")}
        if not ODDS_API_KEY or ODDS_API_KEY == "your_odds_api_key_here": raise OddsSourceError("ODDS_API_KEY is not configured; use --fixture or --offline")
        try:
            response = self.session.get(f"{ODDS_API_BASE_URL}/sports/{NFL_SPORT_KEY}/odds", params={"apiKey": ODDS_API_KEY, "regions": "us",
                "markets": ",".join(GAME_MARKETS), "bookmakers": ",".join(TARGET_SPORTSBOOKS), "oddsFormat": "american"}, timeout=30)
            response.raise_for_status(); payload = response.json()
            if not isinstance(payload, list): raise OddsSourceError("Odds API returned a non-list payload")
        except requests.RequestException as exc: raise OddsSourceError(f"Odds API request failed: {exc}") from exc
        now = datetime.now(timezone.utc).isoformat(); envelope = {"fetched_at": now, "source": "the-odds-api", "payload": payload}
        stamp = now.replace(":", "-").replace("+", "_")
        for path in (self.latest_cache, self.cache_dir / f"odds_{stamp}.json"): path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        quota = {k: response.headers.get(k) for k in ("x-requests-remaining", "x-requests-used") if response.headers.get(k)}
        if quota: logger.info("Odds API quota metadata: %s", quota)
        return payload, {"source_mode": "live", "fetched_at": now, "quota": quota}
    @staticmethod
    def _read(path):
        try: return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise OddsSourceError(f"Could not read {path}: {exc}") from exc
