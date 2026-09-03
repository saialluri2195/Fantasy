# Fantasy / Dimez AI — Project Findings

This document describes the entire repository as it exists today: what the product is, how the live system works, every module (including unused leftovers), the mathematical strategies, technologies, data flow, tests, limits, and how to run it.

The Git repository root is `Fantasy/`. All application code lives in `dimez_ai/` (renamed from `hike_v2`). There is no other application at the repo root besides this document.

---

## 1. What the project is

**NFL Parlay Assister** is a closed-beta MVP that:

1. Ingests NFL sportsbook odds (live from The Odds API, from a local cache, or from a bundled JSON fixture).
2. Keeps only DraftKings, FanDuel, and BetMGM.
3. Normalizes each offer to a single internal record (exact line, American and decimal odds, implied probability).
4. Removes vig (bookmaker juice) on complete two-sided markets.
5. Builds a **cross-book consensus probability** and a **pricing edge**.
6. **Line-shops**: for each exact market/selection/line, picks the book with the best (highest) American/decimal odds.
7. Builds up to three **explainable parlays** (best value, safer, long shot) with a conservative same-game correlation discount.
8. Persists every successful refresh in SQLite so results are reproducible.
9. Serves a FastAPI backend and a single-file HTML UI.

It is **not** a fantasy football draft optimizer in the current live path, even though the folder is named `Fantasy` and leftover “HIKE v2” modules still talk about projections, sentiment, Streamlit, and ML.

Odds, probabilities, edges, and expected value are **estimates**, not guarantees. The UI and API repeat a responsible-gambling disclaimer. There is no bankroll sizing, no authentication, and no betting execution.

---



## 2. Intended problem

Sportsbooks price the same NFL outcome at different numbers, and they embed vigorish so raw implied probabilities sum to more than 100%. A bettor who parlays several legs without accounting for juice, line differences, or same-game dependence will overstate win probability.

This project tries to help by:

- Treating **multi-book no-vig consensus** as a crude “true” probability (not an ML model in the live path).
- Flagging a book when its **with-vig implied probability is lower than consensus** (better price for the bettor).
- Always attaching the **best available price** among the three books.
- Combining only **positive-EV** parlays, refusing contradictory legs, and **discounting** same-game combinations instead of multiplying probabilities as if they were independent.

That is a **market-making / line-shopping / conservative parlay construction** approach, not a predictive sports model.

---



## 3. Technologies used



### Live, installed stack (`dimez_ai/requirements.txt`)


| Package                                                                                      | Role                              |
| -------------------------------------------------------------------------------------------- | --------------------------------- |
| Python 3 (run via `py` / `python`)                                                           | Language                          |
| FastAPI (`>=0.104,<1`)                                                                       | HTTP API                          |
| Uvicorn (`>=0.24,<1`)                                                                        | ASGI server                       |
| Pydantic (FastAPI dependency)                                                                | Request models (`RefreshRequest`) |
| Requests (`>=2.31,<3`)                                                                       | The Odds API HTTP client          |
| python-dotenv (`>=1,<2`)                                                                     | Load `.env` into `config.py`      |
| pytest (`>=7.4,<9`)                                                                          | Tests                             |
| httpx (`>=0.25,<1`)                                                                          | Used by FastAPI `TestClient`      |
| SQLite3 (stdlib)                                                                             | Persistence                       |
| argparse, logging, json, pathlib, itertools, collections, threading, datetime, math (stdlib) | CLI, math, I/O, refresh lock      |


The live UI is **plain HTML + CSS + vanilla JavaScript** in `dimez_ai/app/index.html`. There is no React, no npm build, no CSS framework.

The Odds API (`https://api.the-odds-api.com/v4`) is the only live data source on the supported path. Sport key: `americanfootball_nfl`. Region: `us`. Odds format: American.

### Mentioned but **not** in `requirements.txt` and **not** on the live path

These appear in leftover HIKE v2 files and would fail if imported in a clean venv:


| Library / module                                                                    | Where it appears                                                                                                                                                                                                 |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| pandas, numpy                                                                       | `engine/line_shopping.py`, `engine/parlay.py`, `engine/recommender.py`, `engine/correlation.py`, `ingestion/utils.py`, `ingestion/polymarket.py`, `optimizer/*`, `models/*`, `backtest/*`, `app/pages/parlay.py` |
| scikit-learn (`LogisticRegression`, `IsotonicRegression`, `CalibratedClassifierCV`) | `models/win_probability.py`, `models/calibration.py`                                                                                                                                                             |
| XGBoost                                                                             | `models/win_probability.py`                                                                                                                                                                                      |
| matplotlib                                                                          | `models/calibration.py`                                                                                                                                                                                          |
| pyarrow (parquet)                                                                   | `ingestion/utils.py`                                                                                                                                                                                             |
| Streamlit                                                                           | `app/pages/parlay.py`                                                                                                                                                                                            |
| Gemini                                                                              | `GEMINI_API_KEY` in config/health only; no client code                                                                                                                                                           |
| Polymarket Gamma/CLOB APIs                                                          | `ingestion/polymarket.py`; health reports `polymarket_configured: false`                                                                                                                                         |


Missing packages the leftovers import: `features.builder`, `models.projection`, `backtest.metrics`, `backtest.baselines`, and config symbols such as `CURRENT_SEASON`, `PARLAY_TEMPLATES`, `CONFIDENCE_TIERS`, `POLYMARKET_*`, `MODEL_ARTIFACTS_DIR`, `SEASONS`, `POSITION_GROUPS`, `SGP_*`.

---



## 4. Repository layout

```
Fantasy/                          # git root
  PROJECT.md                      # this document
  dimez_ai/                       # application
    README.md                     # short operator README
    requirements.txt
    .env.template
    .gitignore
    config.py                     # env, books, markets, thresholds
    run_pipeline.py               # CLI: ingest / recommend / all / serve
    service.py                    # RefreshService orchestration
    api/main.py                   # FastAPI + static index.html
    app/index.html                # live UI
    app/pages/parlay.py           # leftover Streamlit page (unused)
    ingestion/odds_source.py      # live/cache/offline/fixture fetch
    ingestion/odds.py             # thin compatibility re-exports
    ingestion/utils.py            # leftover parquet helpers
    ingestion/polymarket.py       # leftover Polymarket client
    engine/odds_math.py           # authoritative conversions, vig, EV
    engine/normalization.py       # Odds API → internal records
    engine/recommendations.py     # consensus, shopping, parlays (LIVE)
    engine/line_shopping.py       # leftover pandas shopping
    engine/parlay.py              # leftover ParlayEngine
    engine/recommender.py         # leftover weekly slate orchestrator
    engine/correlation.py         # leftover correlation heuristics
    storage/database.py           # SQLite schema
    storage/repository.py         # transactional reads/writes
    models/                       # leftover ML (broken imports)
    optimizer/                    # leftover model-vs-market finder
    backtest/walk_forward.py      # leftover walk-forward backtest
    data/fixtures/odds_api_nfl.json
    data/raw/                     # gitignored live cache
    data/parlay_assister.db       # gitignored SQLite
    tests/                        # pytest for the LIVE path
```

Git history of note: commit `5166f6a` (`codex_run1`) then `740f8f5` (rename `hike_v2` → `dimez_ai`).

---



## 5. Live architecture (what actually runs)

```
CLI (run_pipeline.py)  or  POST /refresh
            │
            ▼
     RefreshService          ← threading.Lock, one refresh at a time
            │
            ├─ OddsSource.fetch()     fixture | cache | live API
            ├─ normalize_odds()       engine/normalization.py
            ├─ rank_candidates()      consensus + edge + best book
            ├─ generate_parlays()     2/3/4-leg templates, EV > 0
            └─ Repository             SQLite, atomic complete vs fail
                    │
                    ▼
         FastAPI reads latest successful run
                    │
                    ▼
              app/index.html
```

`run_pipeline.py --stage ingest|recommend|all` all call the **same** `RefreshService.refresh()`. Only `--stage serve` is different (starts Uvicorn).

README statement: “Legacy fantasy modules remain isolated and are not used by the runner, API, or UI.” That is accurate for the live path.

---



## 6. Configuration

File: `dimez_ai/config.py`. Loads `dimez_ai/.env` via python-dotenv.


| Setting                 | Default                   | Meaning                                                       |
| ----------------------- | ------------------------- | ------------------------------------------------------------- |
| `ODDS_API_KEY`          | empty / placeholder       | Required for live refresh                                     |
| `GEMINI_API_KEY`        | empty                     | Optional; **diagnostic only** (`/health` `gemini_configured`) |
| `PARLAY_DATA_DIR`       | `dimez_ai/data`           | Data root                                                     |
| `PARLAY_DATABASE_PATH`  | `data/parlay_assister.db` | SQLite file                                                   |
| `MIN_EDGE_THRESHOLD`    | `0.015` (1.5%)            | Minimum consensus − implied to become a candidate             |
| `MIN_CONSENSUS_BOOKS`   | `2`                       | Books required (with fair/no-vig probs)                       |
| `STALE_AFTER_MINUTES`   | `30`                      | API/UI “stale” flag                                           |
| `MAX_HEADLINE_LEG_USES` | `2`                       | How many headline parlays a single leg may appear in          |


Hard-coded in config (not env):

- Books: `draftkings`, `fanduel`, `betmgm`
- Game markets fetched live: `h2h`, `spreads`, `totals`
- Player prop **keys listed** (pass/rush/rec yards, TDs, completions, attempts, kicking, tackles+assists) but **not requested** on the live smoke path
- Default fixture: `data/fixtures/odds_api_nfl.json`

Never commit `.env`. Rotate any key that was ever committed or logged.

---



## 7. Data ingestion (`ingestion/odds_source.py`)

`OddsSource.fetch(fixture=, offline=, force_refresh=)` chooses a mode:

1. **Fixture** — if `fixture` is set, read that JSON list of events. Used by tests, the UI refresh button, and the CLI default.
2. **Cache / offline** — if `offline=True`, or if `data/raw/odds/latest.json` exists and `force_refresh` is false, unwrap `{fetched_at, payload}` from the cache. Offline with no cache raises `OddsSourceError`.
3. **Live** — GET
  `{ODDS_API_BASE_URL}/sports/americanfootball_nfl/odds`  
   with `apiKey`, `regions=us`, `markets=h2h,spreads,totals`, `bookmakers=draftkings,fanduel,betmgm`, `oddsFormat=american`, timeout 30s.  
   Missing/placeholder key raises a clear error. Non-list JSON is rejected. Failures wrap `requests.RequestException`.

Live success writes:

- `data/raw/odds/latest.json` (envelope: `fetched_at`, `source`, `payload`)
- `data/raw/odds/odds_{utc-stamp}.json` (same envelope, timestamped)

Quota headers `x-requests-remaining` / `x-requests-used` are logged if present.

**CLI default (quota conservation):** if you pass neither `--fixture`, `--offline`, nor `--force-refresh`, the runner **forces the bundled fixture**. Live network use requires `--force-refresh` and a real key.

`ingestion/odds.py` only re-exports `OddsSource` / `OddsSourceError` and vig helpers (`remove_vig_multiplicative` = proportional; `remove_vig_power` unused by the live path). It does **not** define `pull_game_odds` / `pull_player_props` (leftover recommender still imports those names).

---



## 8. Normalization (`engine/normalization.py`)

Input: Odds API-style list of events with nested `bookmakers` → `markets` → `outcomes`.

For each event:

- Require `id`, `home_team`, `away_team`; else reject the event.
- Skip books not in `TARGET_SPORTSBOOKS`.
- For each outcome: require numeric `price`; require `point` for spreads, totals, and `player_*` markets; require `name`; player props also require `description` (player name).
- Bad rows are counted in `rejected` and do not abort the rest of the payload.

For a market with **at least two valid outcomes**, implied probabilities are vig-removed with `remove_vig` (proportional). Incomplete markets keep `fair_probability = None` and later cannot enter consensus.

Each output record includes: `event_id`, `commence_time`, teams, `market_key`, `market_type` (`player_prop` or the game key), sportsbook, selection, player/side/line, American and decimal odds, `raw_implied_probability`, `fair_probability`, placeholders for consensus/edge, `retrieved_at`.

**Market identity** (exact line, not “close enough”):

`(event_id, market_key, player_name, selection, line)`

A 48.5 total and a 49.5 total are different markets. Tests assert that.

---



## 9. Authoritative math (`engine/odds_math.py`)

All live calculations go through this module. Functions reject non-finite values.

### Odds conversions

- American → decimal: `1 + odds/100` if `odds > 0`; `1 + 100/|odds|` if `odds < 0`. Zero American odds is invalid.
- Decimal → American: `(odds-1)*100` if decimal ≥ 2; `-100/(odds-1)` if 1 < decimal < 2.
- Implied probability (with juice): `1 / decimal_odds`.



### Vig removal

`remove_vig([p1, p2, ...])` requires ≥ 2 probabilities, each in (0, 1), then **normalizes so they sum to 1**:

`fair_i = p_i / Σ p_j`

Example: two sides at 0.55/0.55 → 0.50/0.50. This is the multiplicative/proportional no-vig method, not Shin or power methods (power exists only as an unused helper in `ingestion/odds.py`).

### Consensus

Simple **equal-weight average** of per-book fair probabilities, requiring `MIN_CONSENSUS_BOOKS` (default 2). One probability is kept per sportsbook (last write wins if a book listed the same market twice).

### Edge

`edge = consensus_probability − offered_raw_implied_probability`

Positive edge means consensus thinks the outcome is more likely than the **best book’s with-vig price** implies — i.e. the price looks too generous relative to the other books.

### Parlay math (independence first)

- Combined decimal odds: product of leg decimals.
- Independent probability: product of leg consensus probabilities.
- Expected value (also aliased as `expected_profit`): `P * decimal_odds − 1`  
(profit per 1 unit staked if the estimated probability is correct).

---



## 10. Candidate ranking and line shopping (`engine/recommendations.py`)

`rank_candidates(records)`:

1. Group offers by exact `market_identity`.
2. Keep offers with `fair_probability`.
3. Drop groups with fewer than `MIN_CONSENSUS_BOOKS` distinct books.
4. Consensus = average of one fair probability per book.
5. **Best offer** = max `decimal_odds` (best American price for the bettor).
6. Record a **shopping** row for every consensus-eligible identity: best book, best American odds, DK/FD/MGM prices (`null` if a book did not post that exact line), consensus, book count.
7. Compute `edge(consensus, best.raw_implied_probability)`. If `edge < MIN_EDGE_THRESHOLD`, the market is shopped but **not** a parlay candidate.
8. Confidence on candidates:
  - `high`: edge ≥ 5% **and** 3 books
  - `medium`: edge ≥ 3%
  - `low`: otherwise
9. Sort by `(edge, books_supporting_consensus, consensus_probability)` descending; assign `rank`.

The live UI’s “Line Shopping” section is these candidate `other_prices` maps, not `engine/line_shopping.py`.

---



## 11. Parlay construction strategy (`generate_parlays`)

Three templates, **in this order** (so the diversity cap cannot eat every leg before a 4-leg slate is considered):


| Type         | Legs | Sort key (desc)                 | Intent                    |
| ------------ | ---- | ------------------------------- | ------------------------- |
| `best_value` | 2    | `(edge, consensus_probability)` | Highest-edge short parlay |
| `long_shot`  | 4    | `(decimal_odds, edge)`          | Longer odds / more legs   |
| `safer`      | 3    | `(consensus_probability, edge)` | Higher per-leg consensus  |


Process per template:

1. Sort all candidates by that template’s key; take the **top 12**.
2. Enumerate combinations of the required size.
3. Drop combos with pairwise **conflicts** or any leg already used `MAX_HEADLINE_LEG_USES` times (default 2) across headline parlays.
4. Count same-game pairs. Correlation multiplier:
  `adjustment = max(0.85, 1 − 0.05 × same_game_pair_count)`  
   Cross-game only → 1.0. Each same-game pair knocks 5% off, floored at 0.85.
5. `independent_probability` = product of consensus probs.
  `estimated_probability` = independent × adjustment.  
   Combined odds = product of **best-book** decimals.  
   `EV = estimated_probability × combined_odds − 1`.
6. Keep only combos with **EV > 0**.
7. Pick the combo that maximizes:
  - `long_shot`: `(combined_odds, EV)`
  - others: `(sum of leg edges, estimated_probability)`
8. Increment usage for those legs; emit one parlay object with explanation text, correlation note, responsible-gambling note, and copied leg dicts.

Parlay confidence: `medium` if adjustment is 1 (all cross-game), else `low` (same-game heuristic was applied).

### Conflict rules (`conflicts`)

Same-event legs conflict when:

- Identical `candidate_key`, or
- Same market, same player, same line, Over vs Under, or
- Moneyline (`h2h`) opposite teams, or
- Spreads/totals opposite sides **and** the same line.

Different games never conflict. Same-game moneyline + spread for the same team is **allowed**. Correlation is handled only by the 5%/floor-85% discount, not by a trained copula or SGP model.

---



## 12. Persistence (`storage/`)

SQLite with `PRAGMA foreign_keys=ON`. Schema in `storage/database.py`:


| Table                 | Purpose                                                                    |
| --------------------- | -------------------------------------------------------------------------- |
| `refresh_runs`        | Attempt log: mode, status `running`/`success`/`failed`, counts, error text |
| `odds_snapshots`      | Every normalized offer + JSON payload                                      |
| `candidates`          | Edge-qualified legs as JSON                                                |
| `recommendations`     | Headline parlays + numeric columns                                         |
| `recommendation_legs` | Per-leg denormalized fields + JSON                                         |


`Repository.complete_refresh` writes snapshots, candidates, recommendations, and legs, then marks the run successful — all in one connection/`with` block (transactional).

`fail_refresh` only stamps the run failed. **A failed refresh never deletes or replaces the last successful dataset.** API list endpoints read the latest **successful** `refresh_id`. Tests cover this.

Connections: `timeout=10`, `check_same_thread=False`, `Row` factory. Path created if missing.

---



## 13. Refresh service (`service.py`)

- Non-blocking `threading.Lock`; second concurrent refresh raises `RefreshInProgress` (HTTP 409).
- Mode label: `fixture` / `offline` / `live`.
- After normalize/rank/parlay, **zero valid records** raises `ValueError` (failed run, previous success kept).
- Returns a JSON-serializable summary: refresh id, games, offers, rejected count, candidates, recommendations, source mode, duration, line-shopping row count.
- `fixture_refresh()` helper uses `DEFAULT_FIXTURE`.

Rejected outcome rows are counted in the summary but **not stored** as their own table.

---



## 14. HTTP API (`api/main.py`)

FastAPI app title `NFL Parlay Assister` v0.1.0. Shared `Repository` + `RefreshService`.


| Method | Path                    | Behavior                                                                                                                                                   |
| ------ | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/`                     | `app/index.html`                                                                                                                                           |
| GET    | `/health`               | DB ok, last success, last attempt (any status), `data_exists`, `stale`, `stale_after_minutes`, `gemini_configured`, `polymarket_configured` (always false) |
| GET    | `/games`                | Unique events from latest successful `odds_snapshots`                                                                                                      |
| GET    | `/markets`              | Latest `candidates`; optional filters `event_id`, `market_type`, `sportsbook`, `player_name`, `confidence` (case-insensitive equality)                     |
| GET    | `/recommendations`      | Latest parlays; optional `category` matches `type`                                                                                                         |
| GET    | `/recommendations/{id}` | One parlay by row id; 404 if missing                                                                                                                       |
| POST   | `/refresh`              | Body `{fixture?, offline?, force_refresh?}`; 409 if locked; 503 if failed (message says previous data preserved)                                           |
| GET    | `/diagnostics`          | Last success, last attempt, default fixture path                                                                                                           |
| GET    | `/docs`                 | FastAPI Swagger UI (framework default)                                                                                                                     |


Stale: no successful run, or `completed_at` older than `STALE_AFTER_MINUTES`.

Gemini is **not** used to write explanations. Explanations are f-strings in `generate_parlays`.

---



## 15. Frontend (`app/index.html`)

Single dark page, no build step. On load it fetches `/health`, `/recommendations`, `/markets`, `/games` in parallel.

Sections:

- Status bar + **Refresh fixture data** (POST `/refresh` with `fixture: data/fixtures/odds_api_nfl.json`)
- **Top Parlays** — type, legs with book and American odds, combined odds, win %, EV, correlation note
- **Best Edges** — table of candidate markets
- **This Week’s Games**
- **Line Shopping** — per-candidate DK/FD/MGM prices, checkmark on the chosen book
- Disclaimer footer

If there is no data yet, parlays show “No qualifying parlays.” Errors surface in the status span.

`app/pages/parlay.py` is a **Streamlit** leftover (“Parlay Value Finder”) that imports missing `features.builder` and `pull_player_props`. It is **not** served by FastAPI.

---



## 16. Bundled fixture

`data/fixtures/odds_api_nfl.json` — four synthetic 2026 NFL games, three books each:


| Event                   | Markets in fixture      |
| ----------------------- | ----------------------- |
| Buffalo at Kansas City  | moneylines + total 48.5 |
| Minnesota at Detroit    | moneylines              |
| Cincinnati at Baltimore | spread ±2.5             |
| Dallas at Philadelphia  | total 47.5              |


Thirty valid outcomes after normalization (test: `len(rows)==30`, no rejects). DraftKings often posts the longest plus-money prices (e.g. Chiefs +130 vs FanDuel +100), which is what line-shopping tests assert.

---



## 17. Tests

Run from `dimez_ai/` after installing requirements:

```
python -m compileall -q .
python -m pytest -q
```

`tests/conftest.py` puts the package root on `sys.path`.


| File                     | What it locks in                                                                |
| ------------------------ | ------------------------------------------------------------------------------- |
| `test_odds_math.py`      | Conversions, vig, consensus, edge, parlay product, EV, invalid inputs           |
| `test_normalization.py`  | Fixture → 30 rows; exact-line identity; malformed events rejected               |
| `test_odds_ingestion.py` | Fixture + cache modes; offline without cache errors                             |
| `test_line_shopping.py`  | Chiefs best book DraftKings +130, 3-book consensus                              |
| `test_recommender.py`    | Ranking, confidence books ≥ 2, all three parlay types with EV > 0, ML conflicts |
| `test_parlay_ev.py`      | Reproducible 2-leg EV                                                           |
| `test_correlation.py`    | Same-game combo gets adjustment < 1                                             |
| `test_refresh.py`        | Successful fixture persist; empty payload fails but keeps last success; lock    |
| `test_api.py`            | Health, refresh, games, markets, recommendation detail                          |


Leftover modules (`models/`, `optimizer/`, pandas `engine/parlay.py`, etc.) have **no** tests in this tree.

---



## 18. How to run (complete)

Working directory must be `dimez_ai` so `config` / `api.main` imports resolve.

### Install (Windows PowerShell)

```powershell
cd dimez_ai
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.template .env
```

Edit `.env` and set `ODDS_API_KEY` only if you will call the live API.

### Tests

```powershell
python -m compileall -q .
python -m pytest -q
```



### Pipeline (writes SQLite + prints JSON summary)

Default — **fixture**, no API quota:

```powershell
python run_pipeline.py --stage all
```

Explicit fixture:

```powershell
python run_pipeline.py --stage all --fixture data/fixtures/odds_api_nfl.json
```

Use last live cache (requires a previous successful live fetch):

```powershell
python run_pipeline.py --stage all --offline
```

Hit The Odds API (requires real key):

```powershell
python run_pipeline.py --stage all --force-refresh
```

Verbose logs: add `--verbose`.

`--stage ingest` and `--stage recommend` currently do the same full refresh as `--stage all`.

### API + UI

```powershell
python run_pipeline.py --stage serve
```

- UI: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Uvicorn: host `127.0.0.1`, port `8000`, `reload=False`. Equivalent: `python -m uvicorn api.main:app --host 127.0.0.1 --port 8000`.

The UI refresh button always reloads the **fixture**, not live odds. Live refresh from HTTP:

```http
POST /refresh
{"force_refresh": true}
```



### Data locations (gitignored except fixtures)

- Raw live JSON: `dimez_ai/data/raw/odds/`
- Database: `dimez_ai/data/parlay_assister.db`
- Fixture: `dimez_ai/data/fixtures/odds_api_nfl.json`



### Troubleshooting

- `ODDS_API_KEY is not configured` — use fixture/offline or set a real key.
- Offline cache missing — one live `--force-refresh` first, or use the fixture.
- Failed refresh is logged; latest successful games/markets/parlays stay.
- Unsupported/malformed outcomes are skipped and counted in `rejected`.
- Empty normalized set (`[]` fixture) fails the run.

---



## 19. Leftover HIKE v2 / fantasy stack (not used by runner, API, or HTML UI)

These files remain in the tree. They describe an **earlier product idea**: train projection and prop-hit models, beat a naive baseline, then compare **model probability vs sportsbook implied** (and optionally Polymarket). They do not run in the current MVP and many imports are broken against today’s `config.py` and `requirements.txt`.

### `engine/line_shopping.py`

Pandas grouping by `game_id` / `market` / `outcome` / `point`; best American `price`; prop over/under shopping; `compute_line_value` as `(consensus − implied) * 100`. Duplicate conversion helpers (not `odds_math`).

### `engine/parlay.py` — `ParlayEngine`

Consensus as mean of `implied_prob_no_vig`; flags every book-row with edge ≥ threshold (not just the best book). Prop edges from `over_implied_no_vig` / `under_implied_no_vig`. `evaluate_parlay` uses leftover `engine/correlation.py`. Imports missing `CONFIDENCE_TIERS`.

### `engine/recommender.py` — `ParlayRecommender`

Intended weekly slate: pull odds, find edges, shop lines, build `PARLAY_TEMPLATES`, Polymarket context. Imports `CURRENT_SEASON`, `PARLAY_TEMPLATES`, `pull_game_odds`, `pull_player_props` — none exist in current config/odds module. Diverse-leg picker prefers one leg per `game_id`.

### `engine/correlation.py` and `optimizer/correlation.py`

Heuristic pairwise same-game counts. Constants (in optimizer copy): same-direction 0.35, opposite −0.15, cross-game 0.05. Naive product is discounted; comments say correlation must not raise probability above independence. Direction heuristic: pass+reception, rush+rush, or equal `prop_type`. Engine copy expects `SGP_*` / `CROSS_GAME_CORR` in config (absent). **Live parlays do not call these modules.**

### `ingestion/utils.py`

Versioned parquet paths (`weekly_stats_2023_w05.parquet`), empty-frame failures, null-rate logging, staleness (default 168 hours), `save_versioned` / `load_versioned` via pyarrow. Logger name still `dimez_ai.ingestion`. Unused by `OddsSource`.

### `ingestion/polymarket.py`

Public Gamma (`markets`, `events/slug/...`) and CLOB (`prices-history`) clients. Treats order-book YES prices as already no-vig. `pull_polymarket_nfl_prices` caches parquet and **falls back to seeded random sample markets** if the API fails. Imports missing `POLYMARKET_GAMMA_API_URL` / `POLYMARKET_CLOB_API_URL`.

### `models/win_probability.py`

Calibrated classifier: logistic regression or XGBoost, wrapped in `CalibratedModel`, pickle to `MODEL_ARTIFACTS_DIR`. Labels from actual stat vs line (or median). Imports missing `features.builder` and `MODEL_ARTIFACTS_DIR`.

### `models/calibration.py`

Isotonic or Platt (sigmoid) calibration on **training** probabilities (not a held-out calibrator — a methodology caveat). Reliability diagrams, Brier score.

### `models/retrain.py`

Walk-forward retrain of missing `ProjectionModel` plus win-prob models for receiving/rushing/passing yards and receptions. Maps prop type → stat column and position (QB/RB/WR).

### `optimizer/parlay.py` — `ParlayValueFinder`

**Different strategy from the live app:** edge = `model_prob − market_prob`. Parlay EV uses model probs and optimizer correlation. `display_polymarket_context` fuzzy-matches player name tokens to Polymarket questions.

### `backtest/walk_forward.py`

Train on past seasons, test on the next; compare to naive rolling average and season average; sentiment ablation (keep/exclude sentiment features if MAE improves); prop Brier-score walk-forward. Notes that historical sportsbook lines are not actually ingested, so labels use **median stats**, not real lines. CLI `__main__` exists but depends on missing `features`, `ProjectionModel`, `BACKTEST_`* config, `backtest.metrics`, `backtest.baselines`.

### `app/pages/parlay.py`

Streamlit UI: edge slider, load pickled models, sample edges if untrained, multiselect “evaluate parlay” that currently returns a stub JSON.

Package `__init__.py` files still say “HIKE v2”.

---



## 20. Strategy comparison (live vs leftover)


|                    | **Live MVP**                                                     | **Leftover HIKE / ML design**                      |
| ------------------ | ---------------------------------------------------------------- | -------------------------------------------------- |
| “True” probability | Average no-vig implied across ≥2 books                           | Calibrated classifier / projection model           |
| Edge               | Consensus − book’s raw implied, on the **best** price            | Model − market, per book row                       |
| Markets            | Game h2h / spreads / totals (props supported if present in JSON) | Player props + projections + sentiment             |
| Correlation        | 5% per same-game pair, floor 0.85                                | Same-game direction constants + extra 15% discount |
| Parlays            | Exhaustive combos of top 12; one of each template; EV > 0        | Template ranges, greedy diversity, model EV        |
| Extra signals      | None                                                             | Polymarket, Gemini (never wired), Streamlit        |
| Persistence        | SQLite refresh history                                           | Parquet season/week files, pickle artifacts        |


The live system is a **relative-value / consensus-pricing** engine. If all three books are wrong in the same direction, consensus will be wrong too. It cannot discover “the market is mispricing this team” except as **disagreement between those three books**.

---



## 21. Known beta limitations (from code + README)

- Live fetch is **game markets only** (quota). Player props need per-event Odds API calls and are not in the smoke path.
- Polymarket and Gemini **cannot affect** live calculations; Gemini is unused; Polymarket is leftover.
- Same-game correlation is an **explicit conservative heuristic**, not a trained model.
- No auth, no bankroll/Kelly, no multi-sport, no bet placement, no user accounts.
- `--stage ingest` vs `recommend` is not a real pipeline split.
- Combo search is capped at 12 candidates; many +EV slates are never considered.
- Conflict rules do not block all economically duplicated exposure (e.g. same team ML + spread).
- Fair probabilities need a **complete two-sided market**; one-sided books drop out of consensus.
- UI refresh is fixture-only; stale banner is time-based, not “games already started.”
- Leftover ML/backtest/Streamlit code is incomplete and not installable from `requirements.txt`.

---



## 22. End-to-end example (fixture)

1. Four games, three books, 30 normalized two-sided offers.
2. Identities with ≥2 books get consensus and a best price (often DraftKings plus-money).
3. Edges below 1.5% are shopped but not parlay legs.
4. Remaining candidates are mixed into a 2-leg best-value, 4-leg long-shot, and 3-leg safer card when combinations are conflict-free, under the usage cap, and EV-positive after the same-game discount.
5. SQLite stores the run; `/recommendations` and the HTML cards display them.

That is the full supported product.

---



## 23. File-by-file live-path map


| File                              | Role in the running system              |
| --------------------------------- | --------------------------------------- |
| `config.py`                       | Paths, keys, books, markets, thresholds |
| `run_pipeline.py`                 | CLI entry                               |
| `service.py`                      | Orchestration + lock                    |
| `ingestion/odds_source.py`        | Fetch modes                             |
| `ingestion/odds.py`               | Re-exports only                         |
| `engine/odds_math.py`             | Math                                    |
| `engine/normalization.py`         | Schema mapping                          |
| `engine/recommendations.py`       | Edges, shopping, parlays                |
| `storage/database.py`             | Schema                                  |
| `storage/repository.py`           | CRUD                                    |
| `api/main.py`                     | HTTP                                    |
| `app/index.html`                  | UI                                      |
| `data/fixtures/odds_api_nfl.json` | Offline demo data                       |
| `tests/*`                         | Regression for the above                |


Everything else in `dimez_ai/` is historical or unused.

---



## 24. Responsible use

Nothing this project outputs is a lock. Edges are disagreements among three U.S. books after a simple vig strip, plus a hand-tuned parlay haircut. Only wager where it is legal, at legal age, with money you can afford to lose.