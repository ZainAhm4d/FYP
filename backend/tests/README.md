# Test Suite

Automated tests for the AI-Driven BI Dashboard Generator backend. Covers the
data-processing, NLP, analytics, insights and visualization services plus the
full HTTP API (auth, datasets, queries, dashboards + sharing).

## Running

From the `backend/` directory:

```bash
venv/Scripts/python.exe -m pytest          # full suite
venv/Scripts/python.exe -m pytest -q        # quiet
venv/Scripts/python.exe -m pytest tests/test_api_queries.py   # one file
```

The suite uses an **isolated SQLite database** (`test_app.db`) configured in
`conftest.py` *before* the app is imported, so your real `app.db` is never
touched. The DB is recreated fresh on every run.

## Dependencies

```bash
pip install pytest "httpx<0.28"
```

> **Note:** `requirements.txt` pins `httpx==0.28.1`, which is **incompatible**
> with FastAPI 0.104.1 / Starlette 0.27.0's `TestClient` (it removed the
> `app=` shortcut). Install `httpx==0.27.2` to run the API tests, or upgrade
> FastAPI/Starlette. See the testing report for details.

## Layout

| File | What it covers |
|------|----------------|
| `conftest.py` | Isolated DB, TestClient, auth + sample-upload fixtures |
| `test_services_data.py` | TypeDetector, DataCleaner (missing/dupes/outliers/normalize) |
| `test_services_nlp.py` | Keyword intent, entity extraction, parser (offline) |
| `test_services_analytics.py` | All 8 query executors, anomaly detection, insights |
| `test_services_viz.py` | ChartFactory + ChartBuilder for every chart type |
| `test_api_auth.py` | Register/login/me + security edge cases |
| `test_api_datasets.py` | Upload (CSV/XLSX), columns, processing, anomalies, isolation |
| `test_api_queries.py` | 8 templates over HTTP, `/natural`, history, errors |
| `test_api_dashboards.py` | CRUD, ownership isolation, view-only sharing |
| `test_intent_accuracy.py` | Phase-2 intent-accuracy metric (writes a report) |

## Findings & fixes

Two real bugs were found during the initial run and have since been **fixed**;
the tests that documented them are now passing regression tests:

- `test_services_analytics.py::test_missing_required_param_is_handled`
  — `QueryExecutor.execute_query` now fails gracefully on missing params.
- `test_api_queries.py::test_natural_ambiguous_llm_path`
  — the LLM parser now returns a clarification for ambiguous/gibberish input.

Full write-up: `../../TESTING_REPORT_PHASE2.md`.
