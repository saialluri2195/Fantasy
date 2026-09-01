# NFL Parlay Assister

## Overview

This closed-beta MVP ingests NFL odds from The Odds API or a saved fixture, preserves raw responses, normalizes exact-line markets, removes vig for complete markets, calculates multi-book consensus and pricing edges, shops DraftKings/FanDuel/BetMGM, builds conservative explainable parlays, and stores reproducible results in SQLite. FastAPI serves both the API and a lightweight web interface.

Odds and probabilities are estimates, not guarantees. Betting involves risk and is restricted by age and jurisdiction.

## Architecture

`ingestion/odds_source.py` handles live/cache/offline/fixture inputs. `engine/` owns normalization and all math. `service.py` coordinates refreshes. `storage/` provides transactional history. `api/main.py` exposes the backend and `app/index.html` is the no-build frontend. Legacy fantasy modules remain isolated and are not used by the runner, API, or UI.

## Installation

```powershell
cd dimez_ai
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.template .env
```

## Environment variables

Set `ODDS_API_KEY` for live refreshes. `GEMINI_API_KEY` is optional and currently reported diagnostically; deterministic explanations work without it. Thresholds are documented in `.env.template`.

Never commit `.env`. If any credential was previously committed, pasted, or logged, rotate it immediately; deleting it from the current file is not sufficient.

## Run tests

```powershell
python -m compileall -q .
python -m pytest -q
```

## Run fixture mode

```powershell
python run_pipeline.py --stage all --fixture data/fixtures/odds_api_nfl.json
```

With no mode flags, the runner deliberately uses the bundled fixture to conserve quota.

## Run live refresh

```powershell
python run_pipeline.py --stage all --force-refresh
```

Cached/offline mode: `python run_pipeline.py --stage all --offline`.

## Start API and frontend

```powershell
python run_pipeline.py --stage serve
```

Open `http://127.0.0.1:8000/`. API documentation is at `/docs`.

## Data and cache locations

Raw live responses: `data/raw/odds/`. Fixture: `data/fixtures/odds_api_nfl.json`. SQLite history: `data/parlay_assister.db`. These runtime files are ignored except for fixtures.

## Troubleshooting

- “ODDS_API_KEY is not configured”: use fixture mode or add a valid server-side key.
- Offline cache missing: run one successful live refresh first or use the fixture.
- A failed refresh is recorded but never replaces the latest successful set.
- Unsupported or malformed rows are rejected individually and counted.

## Known beta limitations

Player props require event-specific API requests and are not fetched by the quota-conservative live game-market smoke path yet. Polymarket and Gemini are optional and cannot affect calculations. Same-game correlation uses an explicitly labeled conservative heuristic, not a trained model. There is no authentication, bankroll management, or multi-sport support.

## Responsible gambling

Nothing shown is a lock or guarantee. Only bet money you can afford to lose and comply with applicable legal-age and jurisdiction rules.
