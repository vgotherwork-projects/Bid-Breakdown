# Employee Cost & Bid Calculator

A **FastAPI** web app that derives a full salary/cost breakdown from an employee's annual
**CTC**, including PTO and gratuity (driven by date of joining), a configurable per-hour rate,
and a marked-up billing rate. Ships with a responsive, mobile-friendly UI.

## Features

- **Inputs:** annual CTC, employment type (existing / new hire), date of joining, annual
  working hours (default 1880), markup % (default 25).
- **Breakdown (monthly / annual / per-hour):** Basic (CTC slab table), HRA (50% of Basic),
  Conveyance, Medical, Employer PF, Special Pay, Total Earning, Paid Time-Off, Gratuity, Grand Total.
- **Billing rate** = grand-total per-hour rate × (1 + markup %).
- Interactive UI at `/`, JSON API at `POST /bids/calculate`, Swagger docs at `/docs`, health at `/health`.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/ · Docs: http://127.0.0.1:8000/docs

## Test

```powershell
pytest
```

## Run with Docker

```bash
docker build -t cost-bid-calculator .
docker run -p 8000:8000 cost-bid-calculator
```

## Deploy to Render (public URL)

This repo includes `render.yaml` (a Render Blueprint), so deployment is one-click:

1. Push this repo to GitHub (see below).
2. Go to <https://dashboard.render.com> → **New** → **Blueprint**.
3. Connect your GitHub account and select this repository.
4. Render reads `render.yaml`, builds, and deploys a **web service** on the free plan.
5. You'll get a public URL like `https://cost-bid-calculator.onrender.com`.

The service binds to `$PORT`, installs from `requirements.txt`, starts with
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, and uses `/health` for health checks.

> Alternatives: **Railway** / **Heroku-style** hosts use the `Procfile`; any Docker host
> (Fly.io, Hugging Face Spaces, Cloud Run) can use the `Dockerfile`.

## Push to GitHub

```powershell
# One-time: authenticate (opens your browser)
gh auth login

# Create the repo and push (run from this folder)
gh repo create cost-bid-calculator --public --source . --push
```

## Project layout

```
python-api/
├── app/
│   ├── main.py            # App factory, routers, static mount
│   ├── config.py          # Settings (pydantic-settings)
│   ├── bid_schemas.py     # Employee bid input/breakdown models
│   ├── calculator.py      # CTC -> components, PTO, gratuity, billing rate
│   ├── routers/           # bids, health, items
│   └── static/            # index.html, styles.css, app.js (responsive UI)
├── tests/                 # pytest suite
├── requirements.txt
├── Dockerfile / .dockerignore
├── render.yaml            # Render Blueprint
├── Procfile / runtime.txt # Railway / Heroku-style hosts
└── README.md
```
