"""Application service coordinating fetch, calculation, and atomic persistence."""
import logging, threading, time
from pathlib import Path
from config import DEFAULT_FIXTURE
from engine.normalization import normalize_odds
from engine.recommendations import generate_parlays, rank_candidates
from ingestion.odds_source import OddsSource
from storage.repository import Repository
logger=logging.getLogger("parlay_assister.refresh")

class RefreshInProgress(RuntimeError): pass
class RefreshService:
    _lock=threading.Lock()
    def __init__(self, repository=None, source=None): self.repository=repository or Repository(); self.source=source or OddsSource()
    def refresh(self, *, fixture=None, offline=False, force_refresh=False):
        if not self._lock.acquire(blocking=False): raise RefreshInProgress("A refresh is already running")
        started=time.monotonic(); refresh_id=None
        try:
            mode="fixture" if fixture else "offline" if offline else "live"
            refresh_id=self.repository.start_refresh(mode); payload, meta=self.source.fetch(fixture=fixture,offline=offline,force_refresh=force_refresh)
            records,rejected=normalize_odds(payload); candidates,shopping=rank_candidates(records); parlays=generate_parlays(candidates)
            if not records: raise ValueError("Refresh produced no valid normalized offers")
            self.repository.complete_refresh(refresh_id,records,candidates,parlays,len({r['event_id'] for r in records}))
            summary={"refresh_id":refresh_id,"status":"success","games":len({r['event_id'] for r in records}),"offers":len(records),"rejected":len(rejected),
                "candidates":len(candidates),"recommendations":len(parlays),"source_mode":meta["source_mode"],"duration":round(time.monotonic()-started,3),"line_shopping":len(shopping)}
            logger.info("refresh complete: %s",summary); return summary
        except Exception as exc:
            if refresh_id: self.repository.fail_refresh(refresh_id,exc)
            logger.exception("refresh failed"); raise
        finally: self._lock.release()

def fixture_refresh(path=DEFAULT_FIXTURE): return RefreshService().refresh(fixture=Path(path))
