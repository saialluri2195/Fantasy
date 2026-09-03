"""Quota-conscious live, cache, offline, and fixture Odds API ingestion."""
import json, logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import requests
from config import (
    ALL_ODDS_OPERATORS, GAME_MARKETS, NFL_SPORT_KEY, ODDS_API_BASE_URL,
    ODDS_API_KEY, PLAYER_PROP_MARKETS, PROP_LOOKAHEAD_DAYS, PROP_MAX_EVENTS,
    RAW_DATA_DIR, TARGET_SPORTSBOOKS,
)
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
        response, payload = self._request(
            f"sports/{NFL_SPORT_KEY}/odds",
            {"regions": "us", "markets": ",".join(GAME_MARKETS),
             "bookmakers": ",".join(TARGET_SPORTSBOOKS), "oddsFormat": "american"},
        )
        if not isinstance(payload, list): raise OddsSourceError("Odds API returned a non-list payload")
        prop_events, prop_offers = self._merge_near_term_props(payload)
        now = datetime.now(timezone.utc).isoformat(); envelope = {"fetched_at": now, "source": "the-odds-api", "payload": payload}
        stamp = now.replace(":", "-").replace("+", "_")
        for path in (self.latest_cache, self.cache_dir / f"odds_{stamp}.json"): path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        quota = {k: response.headers.get(k) for k in ("x-requests-remaining", "x-requests-used") if response.headers.get(k)}
        if quota: logger.info("Odds API quota metadata: %s", quota)
        return payload, {"source_mode": "live", "fetched_at": now, "quota": quota,
                         "prop_events": prop_events, "prop_offers": prop_offers}

    def _request(self, endpoint, params):
        params = {**params, "apiKey": ODDS_API_KEY}
        try:
            response = self.session.get(f"{ODDS_API_BASE_URL}/{endpoint}", params=params, timeout=30)
            response.raise_for_status()
            return response, response.json()
        except requests.RequestException as exc:
            # Requests exceptions may contain the fully rendered URL, including
            # the apiKey query parameter. Never surface or log that value.
            raise OddsSourceError(f"Odds API request failed ({type(exc).__name__})") from exc

    def _merge_near_term_props(self, events):
        now = datetime.now(timezone.utc); cutoff = now + timedelta(days=PROP_LOOKAHEAD_DAYS)
        upcoming = []
        for event in events:
            try: commence = datetime.fromisoformat(str(event.get("commence_time", "")).replace("Z", "+00:00"))
            except ValueError: continue
            if now <= commence <= cutoff: upcoming.append(event)
        upcoming.sort(key=lambda event: event.get("commence_time", "")); upcoming = upcoming[:PROP_MAX_EVENTS]
        prop_dir = self.cache_dir / "props"; prop_dir.mkdir(parents=True, exist_ok=True)
        fetched_events = offer_count = 0
        for event in upcoming:
            event_id = event.get("id")
            try:
                _, prop_event = self._request(
                    f"sports/{NFL_SPORT_KEY}/events/{event_id}/odds",
                    {"regions": "us,us_dfs", "markets": ",".join(PLAYER_PROP_MARKETS),
                     "bookmakers": ",".join(ALL_ODDS_OPERATORS), "oddsFormat": "american"},
                )
            except OddsSourceError as exc:
                logger.warning("Skipping player props for event %s: %s", event_id, exc); continue
            if not isinstance(prop_event, dict): continue
            prop_books = prop_event.get("bookmakers") or []
            if prop_books:
                event.setdefault("bookmakers", []).extend(prop_books); fetched_events += 1
                offer_count += sum(len(market.get("outcomes") or []) for book in prop_books for market in book.get("markets") or [])
            cache_path = prop_dir / f"{event_id}.json"
            cache_path.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "payload": prop_event}, indent=2), encoding="utf-8")
        logger.info("Player props: %s near-term events returned %s offers", fetched_events, offer_count)
        return fetched_events, offer_count
    @staticmethod
    def _read(path):
        try: return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise OddsSourceError(f"Could not read {path}: {exc}") from exc
