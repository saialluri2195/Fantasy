"""SQLite schema and connection management."""
import sqlite3
from pathlib import Path
from config import DATABASE_PATH

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS refresh_runs(id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL,
 source_mode TEXT NOT NULL, games_found INTEGER DEFAULT 0, raw_offers_found INTEGER DEFAULT 0, normalized_offers INTEGER DEFAULT 0,
 candidates_generated INTEGER DEFAULT 0, recommendations_generated INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS odds_snapshots(id INTEGER PRIMARY KEY, refresh_id INTEGER NOT NULL REFERENCES refresh_runs(id), event_id TEXT,
 market TEXT, selection TEXT, player_name TEXT, line REAL, sportsbook TEXT, american_odds INTEGER, decimal_odds REAL,
 raw_implied_probability REAL, fair_probability REAL, retrieved_at TEXT, payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, refresh_id INTEGER NOT NULL REFERENCES refresh_runs(id), payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recommendations(id INTEGER PRIMARY KEY, refresh_id INTEGER NOT NULL REFERENCES refresh_runs(id), type TEXT NOT NULL,
 created_at TEXT NOT NULL, independent_probability REAL, correlation_adjustment REAL, estimated_probability REAL, combined_decimal_odds REAL,
 combined_american_odds INTEGER, expected_value REAL, confidence TEXT, status TEXT DEFAULT 'active', payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recommendation_legs(id INTEGER PRIMARY KEY, recommendation_id INTEGER NOT NULL REFERENCES recommendations(id), event_id TEXT,
 market TEXT, selection TEXT, player_name TEXT, line REAL, sportsbook TEXT, american_odds INTEGER, decimal_odds REAL,
 consensus_probability REAL, book_implied_probability REAL, edge REAL, other_prices_json TEXT, payload_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_refresh_status ON refresh_runs(status, completed_at);
"""

def connect(path=DATABASE_PATH):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False); conn.row_factory = sqlite3.Row; conn.executescript(SCHEMA)
    return conn
