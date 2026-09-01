"""Central, environment-driven configuration for the NFL Parlay Assister."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = Path(os.getenv("PARLAY_DATA_DIR", PROJECT_ROOT / "data"))
RAW_DATA_DIR = DATA_DIR / "raw"
FIXTURE_DIR = DATA_DIR / "fixtures"
DATABASE_PATH = Path(os.getenv("PARLAY_DATABASE_PATH", DATA_DIR / "parlay_assister.db"))
for directory in (RAW_DATA_DIR, FIXTURE_DIR):
    directory.mkdir(parents=True, exist_ok=True)

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
NFL_SPORT_KEY = "americanfootball_nfl"
TARGET_SPORTSBOOKS = ("draftkings", "fanduel", "betmgm")
GAME_MARKETS = ("h2h", "spreads", "totals")
PLAYER_PROP_MARKETS = (
    "player_pass_yds", "player_pass_tds", "player_pass_completions",
    "player_pass_attempts", "player_rush_yds", "player_rush_attempts",
    "player_rush_tds", "player_reception_yds", "player_receptions",
    "player_reception_tds", "player_kicking_points", "player_tackles_assists",
)
MIN_EDGE_THRESHOLD = float(os.getenv("MIN_EDGE_THRESHOLD", "0.015"))
MIN_CONSENSUS_BOOKS = int(os.getenv("MIN_CONSENSUS_BOOKS", "2"))
STALE_AFTER_MINUTES = int(os.getenv("STALE_AFTER_MINUTES", "30"))
MAX_HEADLINE_LEG_USES = int(os.getenv("MAX_HEADLINE_LEG_USES", "2"))
DEFAULT_FIXTURE = FIXTURE_DIR / "odds_api_nfl.json"
RESPONSIBLE_GAMBLING_NOTE = (
    "Probabilities and edges are estimates, never guarantees. Betting involves risk. "
    "Only wager where legal and if you meet your jurisdiction's minimum age."
)
