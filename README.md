# VendorGate

Vendor onboarding system for India (GSTIN / IFSC / bank proof). Modular monolith: FastAPI + React, SQLite, gate pipeline with explainable checks.

## What it does

Runs an intake through five gates (completeness → document extraction → format → consistency → credibility), then decides **approved / pending / rejected**.

- **LLM** (Sarvam): reads PDFs and adjudicates medium-band name matches; drafts vendor emails
- **Rules**: produce the final outcome
- **Live**: OpenSanctions screening
- **Simulated**: penny-drop bank verify + GST registry (swap-ready clients)

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill SARVAM_* and OPENSANCTIONS_*
python fixtures/make_fixtures.py
cd frontend && npm ci && npm run build && cd ..
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

## Demo

**Dashboard → Demo fixtures**

| Fixture | Expected |
|---------|----------|
| F0 | approved |
| EC-1 | pending (ownership / penny-drop name band) |
| EC-2 | rejected (valid GSTIN, wrong state) |
| EC-3 | pending + vendor email (missing bank proof) |
| EC-4 | pending internal (sanctions; no vendor email) |

Manual upload packs: `demo_kits/` (Load demo kit on `/new`, then drop that folder’s PDFs).

## Environment

| Variable | Required | Notes |
|----------|----------|-------|
| `SARVAM_API_KEY` | yes | LLM |
| `SARVAM_MODEL` | yes | e.g. `sarvam-105b` |
| `OPENSANCTIONS_API_KEY` | yes | live sanctions |
| `DATABASE_URL` | no | default `sqlite:///data/app.db` |
| `RULESET_VERSION` | no | shown on runs |
| `PORT` | Railway | set by platform |

## Railway

1. New project from this GitHub repo  
2. Set the env vars above  
3. Deploy — build regenerates fixtures and builds the frontend  
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Tests

```bash
pytest tests/ -q
```

## Layout

```
app/           FastAPI + gates + services
frontend/      React (Vite) → built into app/static
fixtures/      F0 / EC-1–EC-4 generators + generated PDFs
demo_kits/     Manual /new walkthrough packs
tests/         Unit + fixture tests
```
