"""
CH-09 — relationship suggestion engine + fan-out guard + consent flow.
"""
import io
import time

import numpy as np
import pandas as pd
import pytest

from app.services.data_processing.relationship_detector import (
    suggest_relationships, estimate_join_rows,
)

API = "/api/v1"


# ── Detector service ──────────────────────────────────────────────────────────

def _orders_customers():
    rng = np.random.default_rng(7)
    cust_ids = [f"C-{i:04d}" for i in range(100)]
    customers = pd.DataFrame({
        "id": cust_ids,
        "name": [f"Customer {i}" for i in range(100)],
        "region": rng.choice(["North", "South", "East"], 100),
    })
    orders = pd.DataFrame({
        "order_id": [f"O-{i:05d}" for i in range(400)],
        "customer_id": rng.choice(cust_ids[:80], 400),   # 80% containment vs customers
        "amount": rng.integers(10, 5000, 400),
    })
    return orders, customers


def test_ch09_fk_pair_suggested_with_cardinality():
    orders, customers = _orders_customers()
    cands = suggest_relationships({1: orders, 2: customers},
                                  {1: "orders.csv", 2: "customers.csv"})
    assert cands, "expected the customer_id ↔ id link to be found"
    top = cands[0]
    assert {top["left_column"], top["right_column"]} == {"customer_id", "id"}
    # orders side repeats, customers side unique → many_to_one (or one_to_many mirrored)
    assert top["cardinality"] in ("many_to_one", "one_to_many")
    assert top["containment"] >= 0.5
    assert len(top["matched_examples"]) > 0


def test_ch09_same_name_disjoint_values_not_suggested():
    # Both files have an 'id' column, but the values never overlap: the name
    # similarity alone must NOT produce a suggestion.
    a = pd.DataFrame({"id": range(1000, 1100), "v": range(200, 300)})
    b = pd.DataFrame({"id": range(5000, 5100), "w": range(70000, 70100)})
    cands = suggest_relationships({1: a, 2: b}, {1: "a.csv", 2: "b.csv"})
    assert cands == []


def test_ch09_repeating_measures_not_suggested():
    # Two quantity-style columns share values but neither is a key - no link.
    a = pd.DataFrame({"qty": [1, 2, 3, 4, 5] * 30})
    b = pd.DataFrame({"count": [1, 2, 3, 4, 5] * 40})
    cands = suggest_relationships({1: a, 2: b}, {1: "a.csv", 2: "b.csv"})
    assert cands == []


def test_ch09_estimate_join_rows_counts_fanout():
    l = pd.DataFrame({"k": ["a"] * 50 + ["b"] * 50})
    r = pd.DataFrame({"k": ["a"] * 40 + ["b"] * 40})
    assert estimate_join_rows(l, "k", r, "k") == 50 * 40 * 2


# ── API: suggest + fan-out guard + consent ────────────────────────────────────

def _upload(client, headers, df, fname):
    buf = io.BytesIO(df.to_csv(index=False).encode())
    r = client.post(f"{API}/datasets/", headers=headers,
                    files={"file": (fname, buf, "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait(client, headers, did, tries=40):
    for _ in range(tries):
        st = client.get(f"{API}/datasets/{did}", headers=headers).json().get("processing_status")
        if st not in ("analyzing", "pending", "processing"):
            return st
        time.sleep(0.25)
    return st


def test_ch09_suggest_endpoint_and_nm_fanout_409(client, auth):
    H = auth["headers"]
    # many-to-many: dup keys on both sides with heavy fan-out
    l = pd.DataFrame({"key": ["k1"] * 60 + ["k2"] * 60, "lv": range(120)})
    r = pd.DataFrame({"key": ["k1"] * 60 + ["k2"] * 60, "rv": range(120)})
    lid = _upload(client, H, l, "nm_left.csv")
    rid = _upload(client, H, r, "nm_right.csv")
    _wait(client, H, lid); _wait(client, H, rid)

    resp = client.get(f"{API}/relationships/suggest?dataset_ids={lid},{rid}", headers=H)
    assert resp.status_code == 200, resp.text
    cands = resp.json()["candidates"]
    assert any(c["cardinality"] == "many_to_many" for c in cands)

    # create the N:M relationship, then materialize without confirmation → 409
    c = next(c for c in cands if c["cardinality"] == "many_to_many")
    resp = client.post(f"{API}/relationships", headers=H, json={
        "left_dataset_id": c["left_dataset_id"], "left_column": c["left_column"],
        "right_dataset_id": c["right_dataset_id"], "right_column": c["right_column"],
        "join_type": "inner", "cardinality": c["cardinality"],
    })
    assert resp.status_code == 201, resp.text
    rel_id = resp.json()["id"]

    resp = client.post(f"{API}/relationships/{rel_id}/materialize", headers=H, json={})
    assert resp.status_code == 409, f"expected fan-out guard, got {resp.status_code}: {resp.text}"

    # explicit confirmation proceeds and lands in the consent (review) flow
    resp = client.post(f"{API}/relationships/{rel_id}/materialize", headers=H,
                       json={"confirm_fanout": True})
    assert resp.status_code == 201, resp.text
    new_id = resp.json()["dataset_id"]
    st = _wait(client, H, new_id)
    assert st in ("review", "ready"), f"joined dataset should enter review flow, got {st}"


def test_ch09_join_types_widened(client, auth):
    H = auth["headers"]
    l = pd.DataFrame({"pid": [f"P{i}" for i in range(30)], "sales": range(30)})
    r = pd.DataFrame({"pid": [f"P{i}" for i in range(25)], "cost": range(25)})
    lid = _upload(client, H, l, "jt_left.csv")
    rid = _upload(client, H, r, "jt_right.csv")
    _wait(client, H, lid); _wait(client, H, rid)
    resp = client.post(f"{API}/relationships", headers=H, json={
        "left_dataset_id": lid, "left_column": "pid",
        "right_dataset_id": rid, "right_column": "pid",
        "join_type": "outer",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["join_type"] == "outer"
    assert resp.json()["cardinality"] == "one_to_one"
