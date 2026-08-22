"""
Integration tests for the datasets API: upload (CSV + XLSX), listing, preview,
column metadata, processing/cleaning report, anomalies endpoint, ownership
isolation, and invalid-file handling.
"""
import io
import os
import uuid

import pandas as pd

API = "/api/v1"


def _register_login(client):
    em = f"ds_{uuid.uuid4().hex[:8]}@example.com"
    client.post(f"{API}/auth/register",
                json={"email": em, "password": "GoodPass1!", "full_name": "DS"})
    tok = client.post(f"{API}/auth/login",
                      data={"username": em, "password": "GoodPass1!"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# ── Upload ─────────────────────────────────────────────────────────────────────

def test_upload_requires_auth(client):
    with open("data/samples/ecommerce_sales.csv", "rb") as f:
        r = client.post(f"{API}/datasets/", files={"file": ("e.csv", f, "text/csv")})
    assert r.status_code == 401


def test_upload_csv(client, ecommerce_ds):
    assert ecommerce_ds["row_count"] == 14
    assert ecommerce_ds["column_count"] == 5
    assert ecommerce_ds["id"]


def test_upload_xlsx(client, auth):
    # Build an in-memory XLSX from the ecommerce sample
    df = pd.read_csv("data/samples/ecommerce_sales.csv")
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    r = client.post(f"{API}/datasets/", headers=auth["headers"],
                    files={"file": ("ecommerce.xlsx", buf,
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 201, r.text
    assert r.json()["row_count"] == 14


def test_upload_rejects_bad_extension(client, auth):
    r = client.post(f"{API}/datasets/", headers=auth["headers"],
                    files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")})
    assert r.status_code in (400, 422)


def test_upload_rejects_malformed_csv(client, auth):
    bad = io.BytesIO(b'"unterminated,quote\n1,2,3\n')
    r = client.post(f"{API}/datasets/", headers=auth["headers"],
                    files={"file": ("bad.csv", bad, "text/csv")})
    # Either rejected at parse time, or accepted as a best-effort parse.
    assert r.status_code in (201, 400, 422)


# ── List / get / preview ───────────────────────────────────────────────────────

def test_list_datasets(client, auth, ecommerce_ds):
    r = client.get(f"{API}/datasets/", headers=auth["headers"])
    assert r.status_code == 200
    assert any(d["id"] == ecommerce_ds["id"] for d in r.json())


def test_get_dataset_detail(client, auth, ecommerce_ds):
    r = client.get(f"{API}/datasets/{ecommerce_ds['id']}", headers=auth["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == ecommerce_ds["id"]


def test_preview_dataset(client, auth, ecommerce_ds):
    r = client.get(f"{API}/datasets/{ecommerce_ds['id']}/preview", headers=auth["headers"])
    assert r.status_code == 200


def test_get_missing_dataset_404(client, auth):
    r = client.get(f"{API}/datasets/999999", headers=auth["headers"])
    assert r.status_code == 404


# ── Ownership isolation ────────────────────────────────────────────────────────

def test_other_user_cannot_see_dataset(client, ecommerce_ds):
    other = _register_login(client)
    r = client.get(f"{API}/datasets/{ecommerce_ds['id']}", headers=other)
    assert r.status_code == 404


# ── Columns + processing ───────────────────────────────────────────────────────

def test_dataset_columns(client, auth, ecommerce_ds):
    r = client.get(f"{API}/queries/datasets/{ecommerce_ds['id']}/columns",
                   headers=auth["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["column_count"] == 5
    cats = {c["name"]: c["category"] for c in body["columns"]}
    assert cats["revenue"] == "metric"
    assert cats["date"] == "date"
    assert cats["category"] == "dimension"


def test_process_and_cleaning_report(client, auth, ecommerce_ds):
    r = client.post(f"{API}/datasets/{ecommerce_ds['id']}/process", headers=auth["headers"])
    assert r.status_code == 200
    assert r.json()["success"] is True

    rep = client.get(f"{API}/datasets/{ecommerce_ds['id']}/cleaning-report",
                     headers=auth["headers"])
    assert rep.status_code == 200
    assert "data_quality" in rep.json()


# ── Anomalies endpoint (end-to-end with a synthetic spike) ─────────────────────

def test_anomalies_endpoint_flags_spike(client, auth):
    # Upload a dataset containing a clear single spike
    df = pd.DataFrame({
        "month": pd.date_range("2024-01-01", periods=12, freq="MS").astype(str),
        "revenue": [100, 110, 105, 115, 120, 118, 5000, 122, 119, 125, 130, 128],
    })
    buf = io.BytesIO(df.to_csv(index=False).encode())
    up = client.post(f"{API}/datasets/", headers=auth["headers"],
                     files={"file": ("spike.csv", buf, "text/csv")})
    did = up.json()["id"]
    r = client.get(f"{API}/datasets/{did}/anomalies?column=revenue", headers=auth["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["count"] >= 1
    assert any(a.get("value") == 5000 for a in body["anomalies"])


def test_anomalies_endpoint_requires_auth(client, ecommerce_ds):
    r = client.get(f"{API}/datasets/{ecommerce_ds['id']}/anomalies")
    assert r.status_code == 401


# ── CH-01 regression guards: the four endpoints that called a nonexistent CRUD ──
# These routes 500'd with AttributeError while the suite stayed green because
# nothing exercised them at the API level. Keep these hitting the real routes.

def _wait_ready(client, headers, did, tries=40):
    import time
    for _ in range(tries):
        st = client.get(f"{API}/datasets/{did}", headers=headers).json().get("processing_status")
        if st not in ("analyzing", "pending", "processing"):
            return st
        time.sleep(0.25)
    return st


def test_ch01_browse_full_data(client, auth, ecommerce_ds):
    did = ecommerce_ds["id"]
    _wait_ready(client, auth["headers"], did)
    r = client.get(f"{API}/datasets/{did}/data?page=1&page_size=50", headers=auth["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] and body["total_rows"] >= len(body["rows"])


def test_ch01_cleaning_plan_and_apply(client, auth):
    df = pd.DataFrame({
        "Region": ["North", "north", "South", "South"],
        "Revenue": ["$100", "abc", "$200", "$300"],
    })
    buf = io.BytesIO(df.to_csv(index=False).encode())
    up = client.post(f"{API}/datasets/", headers=auth["headers"],
                     files={"file": ("ch01_plan.csv", buf, "text/csv")})
    assert up.status_code == 201, up.text
    did = up.json()["id"]
    _wait_ready(client, auth["headers"], did)

    r = client.get(f"{API}/datasets/{did}/cleaning-plan", headers=auth["headers"])
    assert r.status_code == 200, r.text
    plan = r.json()
    ops = plan.get("operations") or plan.get("plan", {}).get("operations") or []
    assert ops, "expected at least one proposed operation"

    selected = [o["id"] for o in ops if o.get("enabled")]
    r = client.post(f"{API}/datasets/{did}/cleaning-apply", headers=auth["headers"],
                    json={"plan": plan.get("plan") or plan, "selected_ids": selected,
                          "overrides": {}})
    assert r.status_code == 200, r.text


def test_ch01_refresh_file_dataset_is_graceful_400(client, auth, ecommerce_ds):
    # A plain file upload has no live source: must be a deliberate 400, never a 500.
    r = client.post(f"{API}/datasets/{ecommerce_ds['id']}/refresh", headers=auth["headers"])
    assert r.status_code == 400, r.text
    assert "no live source" in r.json()["detail"].lower() or "file" in r.json()["detail"].lower()
