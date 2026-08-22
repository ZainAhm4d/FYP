"""
Shared pytest fixtures.

An isolated SQLite database (test_app.db) is configured BEFORE the app is
imported, so the real app.db is never touched. A module-scoped TestClient
boots the FastAPI app (running startup events: schema migration + NLP preload).
"""
import os
import warnings

warnings.filterwarnings("ignore")

# ── Point the app at an isolated DB *before* importing anything from app.* ──────
os.environ["DATABASE_URL"] = "sqlite:///./test_app.db"

# Remove any stale test DB so each run starts clean.
if os.path.exists("test_app.db"):
    try:
        os.remove("test_app.db")
    except OSError:
        pass

import uuid
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core import rate_limiter

API = "/api/v1"


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Clear the in-process rate-limiter counters before every test.

    Under TestClient all requests share one client IP, so without this the
    whole suite shares one sliding window and legitimately 429s once the
    per-window cap (e.g. 5 registrations/hour) is hit. Resetting per test
    keeps production behaviour intact while letting the suite run in a single
    process; tests that deliberately exercise a 429 still exhaust the limit
    within their own body. See TI-01 in CLEANING_PIPELINE.md.
    """
    for lim in (rate_limiter.login_limiter,
                rate_limiter.register_limiter,
                rate_limiter.upload_limiter):
        lim._hits.clear()
    yield

# Absolute paths to the bundled sample datasets.
SAMPLES = os.path.join("data", "samples")
ECOMMERCE = os.path.join(SAMPLES, "ecommerce_sales.csv")
INVENTORY = os.path.join(SAMPLES, "inventory_management.csv")
HR = os.path.join(SAMPLES, "hr_analytics.csv")


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _unique_email() -> str:
    return f"tester_{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture(scope="session")
def auth(client):
    """Register + login a fresh user; return {'headers':..., 'email':..., 'id':...}."""
    email = _unique_email()
    password = "TestPass1!"
    r = client.post(f"{API}/auth/register", json={
        "email": email, "password": password, "full_name": "Test User",
    })
    assert r.status_code == 201, r.text
    uid = r.json()["id"]

    r = client.post(f"{API}/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "email": email,
        "password": password,
        "id": uid,
    }


def _upload(client, headers, path):
    """Upload a dataset file and return the created dataset JSON."""
    fname = os.path.basename(path)
    with open(path, "rb") as fh:
        r = client.post(
            f"{API}/datasets/",
            headers=headers,
            files={"file": (fname, fh, "text/csv")},
        )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="session")
def ecommerce_ds(client, auth):
    """Upload the ecommerce sample once for the whole session."""
    return _upload(client, auth["headers"], ECOMMERCE)


@pytest.fixture(scope="session")
def hr_ds(client, auth):
    return _upload(client, auth["headers"], HR)


@pytest.fixture(scope="session")
def inventory_ds(client, auth):
    return _upload(client, auth["headers"], INVENTORY)


# ── Synthetic frames for service-level edge-case testing ───────────────────────

@pytest.fixture
def spike_frame():
    """Time series with an obvious spike on one date (anomaly target)."""
    dates = pd.date_range("2024-01-01", periods=12, freq="MS")
    revenue = [100, 110, 105, 115, 120, 118, 900, 122, 119, 125, 130, 128]
    return pd.DataFrame({"date": dates, "revenue": revenue,
                         "region": (["North", "South"] * 6)})


@pytest.fixture
def messy_frame():
    """Frame with missing values, duplicates, typos and case variants."""
    return pd.DataFrame({
        "region": ["North", "north", "NORTH", "South", "South", "South", None],
        "sales": [100, 200, None, 150, 150, 150, 90],
        "qty": [1, 2, 3, 4, 4, 4, None],
    })
