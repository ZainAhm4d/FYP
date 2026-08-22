# AI-Driven BI Dashboard Generator

A self-service business intelligence platform that turns raw spreadsheets and
live data sources into interactive dashboards — without requiring the user to
know SQL, write cleaning scripts, or design charts by hand.

Upload a CSV/Excel file (or connect a Google Sheet, MySQL, or PostgreSQL
source) → review and approve a proposed data-cleaning plan → ask a question
in plain English or pick an analysis template → get an interactive chart with
auto-generated written insights → arrange charts into a dashboard → share,
export, or schedule it as a recurring email report.

---

## Key features

- **JWT authentication** with a full account lifecycle (self-service delete,
  admin-managed deactivate/soft-delete/restore/purge).
- **Consent-based data cleaning** — the pipeline proposes fixes (missing
  values, duplicates, header/aggregate rows, inconsistent categories,
  currency/date parsing) with cell-level before/after examples; nothing is
  applied until the user approves it, and the original file is never
  modified.
- **Manual cell/column chat editors** — LLM-backed assistants for fixing
  individual cells or running whitelisted bulk column transforms.
- **8 analytical query templates** (trend, category comparison, distribution,
  top-K, scatter, correlation, grouped aggregation, period-over-period) plus
  a **natural-language query box** backed by a 3-tier NLP engine (LLM →
  offline sentence-embeddings → keyword fallback) with automatic multi-key
  failover across AI providers.
- **Anomaly detection** (Z-score, Isolation Forest) and **forecasting**
  (linear regression with confidence intervals).
- **Cross-dataset relationships** — suggests and materializes joins between a
  user's datasets, with a fan-out safety guard against accidental row
  multiplication.
- **Live data** — Google Sheets (auto-refresh + push webhook), MySQL,
  PostgreSQL.
- **Dashboards** — drag/arrange charts, KPI widgets, public share links,
  viewer/editor collaboration, export to PDF/PNG/CSV/interactive HTML.
- **Scheduled email reports** (daily/weekly/monthly) via Resend, SendGrid, or
  SMTP.
- **Admin portal** — user management, usage stats, full audit log.


---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0, SQLite |
| Data processing | pandas 3.x, numpy, pyarrow (Parquet) |
| Auth | python-jose (JWT), passlib + bcrypt |
| NLP | OpenRouter (LLM), sentence-transformers, spaCy |
| Analytics | scikit-learn, scipy |
| Charts | Plotly (server-built spec, Plotly.js rendering) |
| Scheduling / Email | APScheduler; Resend / SendGrid / SMTP |
| Export | kaleido (PNG), reportlab (PDF) |
| Frontend | Vanilla JavaScript, Tailwind CSS, no build framework |

---

## Project structure

```
src/
├── backend/            FastAPI application (see backend/README.md)
│   ├── app/
│   │   ├── api/v1/      routers: auth, datasets, queries, dashboards,
│   │   │                anomalies, schedules, collaborations,
│   │   │                relationships, admin
│   │   ├── core/         config, database, security, rate limiter, cache
│   │   ├── models/       SQLAlchemy models
│   │   ├── schemas/      Pydantic request/response models
│   │   ├── crud/         database access per entity
│   │   └── services/     cleaning pipeline, NLP, analytics, visualization,
│   │                     insights, integrations, scheduler, email
│   ├── data/             uploads / processed (cleaned) / samples — gitignored
│   └── tests/            pytest suite (~180 tests)
└── frontend/            Static HTML/CSS/JS pages (see frontend/README.md)
    ├── js/
    │   ├── pages/         one script per page
    │   ├── components/    shared navbar, notifications, loading, tooltips…
    │   └── visualization/ chart rendering, dashboard layout
    └── css/
```

---

## Getting started

Full setup and run instructions live in
[`HOW_TO_RUN.md`](HOW_TO_RUN.md). Short version:

```powershell
# Terminal 1 — backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then fill in SECRET_KEY and any optional keys
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
python -m http.server 3000
```

Then open **http://localhost:3000**. Interactive API docs are available at
**http://localhost:8000/docs**.

Everything except `SECRET_KEY` is optional — the app runs fully offline with
no AI key, no email provider, and no external database connection configured;
those features simply degrade gracefully to their fallback behavior (see
`backend/.env.example` for what each optional setting unlocks).

---

## Running the tests

```powershell
cd backend
.\venv\Scripts\Activate.ps1
pytest
```

Tests run against an isolated `test_app.db` and never touch the real
development database or files.

---

## License / status

Private, unpublished student project (Final Year Project). Not licensed for
reuse or redistribution.
