#!/usr/bin/env python3
"""NFL-only command line runner."""
import argparse,json,logging
from pathlib import Path
from config import ODDS_API_KEY
from service import RefreshService

def main():
    parser=argparse.ArgumentParser(description="NFL Parlay Assister pipeline")
    parser.add_argument("--stage",choices=["ingest","recommend","all","serve"],default="all")
    parser.add_argument("--fixture",type=Path); parser.add_argument("--offline",action="store_true"); parser.add_argument("--force-refresh",action="store_true"); parser.add_argument("--verbose",action="store_true"); parser.add_argument("--port",type=int,default=8000)
    args=parser.parse_args(); logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    if args.stage=="serve":
        if ODDS_API_KEY and ODDS_API_KEY != "your_odds_api_key_here":
            try:
                result=RefreshService().refresh(force_refresh=True)
                print(json.dumps(result,indent=2))
            except Exception as exc:
                logging.getLogger("parlay_assister").warning(
                    "Live startup refresh failed (%s); serving the last successful data set.", type(exc).__name__
                )
        else:
            logging.getLogger("parlay_assister").warning(
                "ODDS_API_KEY is not configured; serving existing data. Add the key to .env for live refreshes."
            )
        import uvicorn; uvicorn.run("api.main:app",host="127.0.0.1",port=args.port,reload=False); return
    if not args.fixture and not args.offline and not ODDS_API_KEY:
        parser.error("ODDS_API_KEY is not configured. Add it to .env, use --offline, or explicitly pass --fixture PATH.")
    result=RefreshService().refresh(fixture=args.fixture,offline=args.offline,force_refresh=args.force_refresh or not args.offline)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
