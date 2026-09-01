"""Transactional refresh persistence and retrieval."""
import json
from datetime import datetime, timezone
from storage.database import connect

class Repository:
    def __init__(self, path=None): self.path = path
    def _connect(self): return connect(self.path) if self.path else connect()
    def start_refresh(self, source_mode):
        with self._connect() as db:
            cur = db.execute("INSERT INTO refresh_runs(started_at,status,source_mode) VALUES(?,?,?)", (datetime.now(timezone.utc).isoformat(), "running", source_mode)); return cur.lastrowid
    def fail_refresh(self, refresh_id, error):
        with self._connect() as db: db.execute("UPDATE refresh_runs SET completed_at=?,status='failed',error=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), str(error)[:2000], refresh_id))
    def complete_refresh(self, refresh_id, records, candidates, recommendations, games):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            for r in records: db.execute("INSERT INTO odds_snapshots(refresh_id,event_id,market,selection,player_name,line,sportsbook,american_odds,decimal_odds,raw_implied_probability,fair_probability,retrieved_at,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (refresh_id,r["event_id"],r["market_key"],r["selection"],r.get("player_name"),r.get("line"),r["sportsbook"],r["american_odds"],r["decimal_odds"],r["raw_implied_probability"],r.get("fair_probability"),r["retrieved_at"],json.dumps(r)))
            for c in candidates: db.execute("INSERT INTO candidates(refresh_id,payload_json) VALUES(?,?)", (refresh_id,json.dumps(c)))
            for rec in recommendations:
                cur = db.execute("INSERT INTO recommendations(refresh_id,type,created_at,independent_probability,correlation_adjustment,estimated_probability,combined_decimal_odds,combined_american_odds,expected_value,confidence,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (refresh_id,rec["type"],now,rec["independent_probability"],rec["correlation_adjustment"],rec["estimated_probability"],rec["combined_decimal_odds"],rec["combined_american_odds"],rec["expected_value"],rec["confidence"],json.dumps(rec)))
                for leg in rec["legs"]: db.execute("INSERT INTO recommendation_legs(recommendation_id,event_id,market,selection,player_name,line,sportsbook,american_odds,decimal_odds,consensus_probability,book_implied_probability,edge,other_prices_json,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cur.lastrowid,leg["event_id"],leg["market_key"],leg["selection"],leg.get("player_name"),leg.get("line"),leg["sportsbook"],leg["american_odds"],leg["decimal_odds"],leg["consensus_probability"],leg["raw_implied_probability"],leg["edge"],json.dumps(leg.get("other_prices")),json.dumps(leg)))
            db.execute("UPDATE refresh_runs SET completed_at=?,status='success',games_found=?,raw_offers_found=?,normalized_offers=?,candidates_generated=?,recommendations_generated=? WHERE id=?",
                (now,games,len(records),len(records),len(candidates),len(recommendations),refresh_id))
    def latest_run(self, any_status=False):
        where = "" if any_status else "WHERE status='success'"
        with self._connect() as db:
            row = db.execute(f"SELECT * FROM refresh_runs {where} ORDER BY id DESC LIMIT 1").fetchone(); return dict(row) if row else None
    def list_json(self, table, column="payload_json", refresh_id=None):
        allowed = {"candidates","odds_snapshots","recommendations"}; assert table in allowed
        refresh_id = refresh_id or ((self.latest_run() or {}).get("id"))
        if not refresh_id: return []
        with self._connect() as db:
            rows = db.execute(f"SELECT id,{column} FROM {table} WHERE refresh_id=? ORDER BY id", (refresh_id,)).fetchall()
            result=[]
            for row in rows:
                item=json.loads(row[column]); item.setdefault("id",row["id"]); item.setdefault("refresh_id",refresh_id); result.append(item)
            return result
    def recommendation(self, recommendation_id):
        with self._connect() as db:
            row=db.execute("SELECT id,refresh_id,payload_json FROM recommendations WHERE id=?",(recommendation_id,)).fetchone()
            if not row: return None
            item=json.loads(row["payload_json"]); item.update({"id":row["id"],"refresh_id":row["refresh_id"]}); return item
