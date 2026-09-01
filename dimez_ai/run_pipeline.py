#!/usr/bin/env python3
"""NFL-only command line runner."""
import argparse,json,logging
from pathlib import Path
from config import DEFAULT_FIXTURE
from service import RefreshService

def main():
    parser=argparse.ArgumentParser(description="NFL Parlay Assister pipeline")
    parser.add_argument("--stage",choices=["ingest","recommend","all","serve"],default="all")
    parser.add_argument("--fixture",type=Path); parser.add_argument("--offline",action="store_true"); parser.add_argument("--force-refresh",action="store_true"); parser.add_argument("--verbose",action="store_true")
    args=parser.parse_args(); logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    if args.stage=="serve":
        import uvicorn; uvicorn.run("api.main:app",host="127.0.0.1",port=8000,reload=False); return
    fixture=args.fixture
    if not fixture and not args.offline and not args.force_refresh: fixture=DEFAULT_FIXTURE
    result=RefreshService().refresh(fixture=fixture,offline=args.offline,force_refresh=args.force_refresh)
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
