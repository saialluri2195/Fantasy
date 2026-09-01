"""Thin HTTP API over the refresh service and repository."""
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from config import DEFAULT_FIXTURE, GEMINI_API_KEY, RESPONSIBLE_GAMBLING_NOTE, STALE_AFTER_MINUTES
from service import RefreshInProgress, RefreshService
from storage.repository import Repository

app=FastAPI(title="NFL Parlay Assister",version="0.1.0")
repo=Repository(); service=RefreshService(repo)
class RefreshRequest(BaseModel):
    fixture: str | None=None
    offline: bool=False
    force_refresh: bool=False

def stale(run):
    if not run or not run.get("completed_at"): return True
    completed=datetime.fromisoformat(run["completed_at"].replace("Z","+00:00")); return (datetime.now(timezone.utc)-completed).total_seconds()>STALE_AFTER_MINUTES*60

@app.get("/")
def index(): return FileResponse(Path(__file__).resolve().parents[1]/"app"/"index.html")
@app.get("/health")
def health():
    latest,last=repo.latest_run(),repo.latest_run(any_status=True)
    return {"status":"ok","database":"ok","last_successful_refresh":latest,"last_refresh_result":last,"data_exists":bool(latest),
        "stale":stale(latest),"stale_after_minutes":STALE_AFTER_MINUTES,"gemini_configured":bool(GEMINI_API_KEY),"polymarket_configured":False}
@app.get("/games")
def games():
    rows=repo.list_json("odds_snapshots"); seen={}
    for r in rows: seen.setdefault(r["event_id"],{k:r.get(k) for k in ("event_id","home_team","away_team","commence_time","retrieved_at")})
    return {"games":list(seen.values()),"stale":stale(repo.latest_run())}
@app.get("/markets")
def markets(event_id:str|None=None,market_type:str|None=None,sportsbook:str|None=None,player_name:str|None=None,confidence:str|None=None):
    rows=repo.list_json("candidates")
    filters={"event_id":event_id,"market_type":market_type,"sportsbook":sportsbook,"player_name":player_name,"confidence":confidence}
    for key,value in filters.items():
        if value is not None: rows=[r for r in rows if str(r.get(key,"")).lower()==value.lower()]
    return {"markets":rows,"stale":stale(repo.latest_run())}
@app.get("/recommendations")
def recommendations(category:str|None=Query(None)):
    rows=repo.list_json("recommendations")
    if category: rows=[r for r in rows if r.get("type")==category]
    return {"recommendations":rows,"stale":stale(repo.latest_run()),"responsible_gambling_note":RESPONSIBLE_GAMBLING_NOTE}
@app.get("/recommendations/{recommendation_id}")
def recommendation(recommendation_id:int):
    item=repo.recommendation(recommendation_id)
    if not item: raise HTTPException(404,"Recommendation not found")
    return item
@app.post("/refresh")
def refresh(request:RefreshRequest):
    try: return service.refresh(fixture=Path(request.fixture) if request.fixture else None,offline=request.offline,force_refresh=request.force_refresh)
    except RefreshInProgress as exc: raise HTTPException(409,str(exc)) from exc
    except Exception as exc: raise HTTPException(503,f"Refresh failed; previous successful data was preserved. {exc}") from exc
@app.get("/diagnostics")
def diagnostics(): return {"last_successful":repo.latest_run(),"last_attempt":repo.latest_run(any_status=True),"default_fixture":str(DEFAULT_FIXTURE)}
