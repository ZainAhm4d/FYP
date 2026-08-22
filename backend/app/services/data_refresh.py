"""
Live-data refresh service.

Two responsibilities:

1. `refresh_dataset(db, dataset)` — re-fetch a connected source (Google Sheets),
   overwrite the dataset's source file, and re-run the cleaning pipeline.
   The user consented to automatic cleaning when they enabled auto-refresh.

2. `refresh_dashboard_data(db, dashboard)` — re-execute every chart's stored
   query against the CURRENT data and write the fresh results (plotly specs,
   query results, insights) back into config_json. Used by the report
   scheduler so emailed reports always reflect the latest data, and by the
   manual/auto refresh in the dashboard UI (which calls /queries/execute
   per chart from the browser instead).

A background sweep (`refresh_due_datasets`) runs every few minutes via the
existing APScheduler and refreshes any dataset whose interval has elapsed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd
from app.services.data_processing.io_utils import read_tabular


# ── Dataset refresh (source → file → clean) ──────────────────────────────────

def refresh_dataset(db, dataset) -> bool:
    """
    Re-fetch a connected dataset from its source and re-clean it while HONORING
    the user's approved cleaning decisions (CP-05):
      - if an approved policy exists → replay it (same fills/merges/choices).
        Any brand-new value-level issue in the fresh data → status 'review'.
      - if no policy exists (never reviewed) → re-analyze only, status 'review'.
        Never auto-apply value-level merges the user never approved.
    Returns True on success.
    """
    if dataset.source_type != "google_sheets" or not dataset.source_url:
        return False

    from app.services.integrations.google_sheets import fetch_google_sheet
    from app.services.data_processing.preprocessor import DataPreprocessor
    from app.services.data_processing.cleaning_plan import (
        build_plan, apply_policy, load_policy,
    )
    from app.api.v1.datasets import _plan_path
    import json as _json

    try:
        df = fetch_google_sheet(dataset.source_url)
        if df is None or df.empty:
            raise ValueError("Source returned no data")

        # Overwrite the source file (same path — mtime bump invalidates caches
        # and stale stored cleaning plans automatically)
        df.to_csv(dataset.file_path, index=False)

        pre = DataPreprocessor()
        processed_dir = str(pre.processed_dir)
        policy = load_policy(processed_dir, dataset.id, dataset.user_id)

        if policy:
            # Replay approved decisions on the fresh data
            cleaned, actions, report, has_new, fresh_plan = apply_policy(df, policy)
            pre._save_processed_dataset(cleaned, dataset.id, dataset.user_id)
            # Refresh the stored plan so the review screen shows any new issues
            try:
                plan_file = _plan_path(dataset.id, dataset.user_id)
                plan_file.parent.mkdir(parents=True, exist_ok=True)
                fresh_plan["dataset_id"] = dataset.id
                plan_file.write_text(_json.dumps(fresh_plan, default=str), encoding="utf-8")
            except Exception:
                pass
            dataset.cleaned_status = True
            dataset.processing_status = "review" if has_new else "ready"
            dataset.row_count = len(cleaned)
            dataset.column_count = len(cleaned.columns)
        else:
            # Never reviewed → just re-analyze; do NOT auto-apply value merges
            plan = build_plan(df)
            plan["dataset_id"] = dataset.id
            try:
                plan_file = _plan_path(dataset.id, dataset.user_id)
                plan_file.parent.mkdir(parents=True, exist_ok=True)
                plan_file.write_text(_json.dumps(plan, default=str), encoding="utf-8")
            except Exception:
                pass
            dataset.cleaned_status = False
            dataset.processing_status = "review"
            dataset.row_count = len(df)
            dataset.column_count = len(df.columns)

        dataset.last_refreshed = datetime.utcnow()
        db.commit()
        print(f"[Refresh] dataset #{dataset.id} refreshed: {len(df)} rows "
              f"(status={dataset.processing_status})")
        return True
    except Exception as exc:
        print(f"[Refresh] dataset #{dataset.id} failed: {exc}")
        try:
            dataset.last_refreshed = datetime.utcnow()   # back off until next interval
            db.commit()
        except Exception:
            pass
        return False


def refresh_due_datasets() -> None:
    """Sweep job: refresh every connected dataset whose interval has elapsed."""
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset

    db = SessionLocal()
    try:
        candidates = db.query(Dataset).filter(
            Dataset.source_type == "google_sheets",
            Dataset.refresh_interval_minutes.isnot(None),
        ).all()
        now = datetime.utcnow()
        for ds in candidates:
            due = (ds.last_refreshed is None or
                   now - ds.last_refreshed >= timedelta(minutes=ds.refresh_interval_minutes))
            if due:
                refresh_dataset(db, ds)
    except Exception as exc:
        print(f"[Refresh] sweep failed: {exc}")
    finally:
        db.close()


# ── Dashboard data refresh (re-execute stored queries) ───────────────────────

def refresh_dashboard_data(db, dashboard) -> int:
    """
    Re-run every chart's stored query against current data and update
    config_json in place. Returns the number of charts refreshed.
    Charts without a dataset/template binding (text/KPI/divider widgets,
    or legacy charts) are left untouched; KPIs recompute from their source
    chart's data downstream.
    """
    from app.services.data_processing.preprocessor import DataPreprocessor
    from app.services.analytics import QueryExecutor
    from app.services.visualization import ChartFactory, ChartBuilder
    from app.services.insights import generate_insights

    try:
        config = json.loads(dashboard.config_json)
    except Exception:
        return 0

    charts = config.get("charts", [])
    pre = DataPreprocessor()
    df_cache: dict = {}
    refreshed = 0

    for ch in charts:
        if (ch.get("widget_type") or "chart") != "chart":
            continue
        dataset_id = (ch.get("dataset") or {}).get("id")
        template_type = (ch.get("template") or {}).get("type")
        parameters = (ch.get("queryResult") or {}).get("parameters") or ch.get("parameters") or {}
        if not dataset_id or not template_type:
            continue

        try:
            if dataset_id not in df_cache:
                df = pre.get_processed_dataset(dataset_id, dashboard.user_id)
                if df is None:
                    from app.models.dataset import Dataset
                    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
                    if not ds:
                        df_cache[dataset_id] = None
                        continue
                    df = read_tabular(ds.file_path)
                df_cache[dataset_id] = df
            df = df_cache[dataset_id]
            if df is None or df.empty:
                continue

            executor = QueryExecutor(df)
            query_result = executor.execute_query(template_type=template_type, parameters=parameters)
            if not query_result.get("success"):
                continue

            chart_config = ChartFactory.create_chart_config(
                template_type=template_type, query_result=query_result, parameters=parameters)
            plotly_spec = ChartBuilder.build_chart(chart_config)
            insights = generate_insights(
                template_type=template_type, query_result=query_result, parameters=parameters)

            ch["plotlySpec"] = plotly_spec
            ch["queryResult"] = {**query_result, "parameters": parameters, "insights": insights}
            refreshed += 1
        except Exception as exc:
            print(f"[Refresh] chart '{ch.get('title')}' on dashboard #{dashboard.id} failed: {exc}")
            continue

    if refreshed:
        dashboard.config_json = json.dumps(config, default=str)
        db.commit()
        print(f"[Refresh] dashboard #{dashboard.id}: {refreshed} chart(s) re-queried")
    return refreshed
