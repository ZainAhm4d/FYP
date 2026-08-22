"""
CH-18 — admin portal: access control, lifecycle (deactivate / soft delete /
restore), retention purge, self-service deletion.
"""
import os
import uuid
from datetime import datetime, timedelta

API = "/api/v1"


def _make_user(client, is_admin=False):
    em = f"adm_{uuid.uuid4().hex[:8]}@example.com"
    pw = "GoodPass1!"
    r = client.post(f"{API}/auth/register",
                    json={"email": em, "password": pw, "full_name": "Adm Test"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    if is_admin:
        from app.core.database import SessionLocal
        from app.models.user import User
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.id == uid).first()
            u.is_admin = True
            db.commit()
        finally:
            db.close()
    tok = client.post(f"{API}/auth/login",
                      data={"username": em, "password": pw}).json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {tok}"}, "email": em,
            "password": pw, "id": uid}


def test_non_admin_gets_403(client):
    user = _make_user(client)
    for path in ("/admin/users", "/admin/stats", "/admin/audit"):
        r = client.get(f"{API}{path}", headers=user["headers"])
        assert r.status_code == 403, f"{path}: {r.status_code}"


def test_admin_lists_users_with_counts(client):
    admin = _make_user(client, is_admin=True)
    r = client.get(f"{API}/admin/users", headers=admin["headers"])
    assert r.status_code == 200, r.text
    rows = r.json()
    assert any(u["email"] == admin["email"] and u["is_admin"] for u in rows)
    assert all("dataset_count" in u and "dashboard_count" in u for u in rows)

    r = client.get(f"{API}/admin/stats", headers=admin["headers"])
    assert r.status_code == 200
    assert r.json()["total_users"] >= 1


def test_deactivate_blocks_login_and_token(client):
    admin = _make_user(client, is_admin=True)
    victim = _make_user(client)

    r = client.put(f"{API}/admin/users/{victim['id']}/deactivate", headers=admin["headers"])
    assert r.status_code == 200, r.text

    # Existing token dies on next request
    r = client.get(f"{API}/auth/users/me", headers=victim["headers"])
    assert r.status_code == 403

    # Login blocked
    r = client.post(f"{API}/auth/login",
                    data={"username": victim["email"], "password": victim["password"]})
    assert r.status_code == 403

    # Reactivate restores access
    r = client.put(f"{API}/admin/users/{victim['id']}/reactivate", headers=admin["headers"])
    assert r.status_code == 200
    r = client.post(f"{API}/auth/login",
                    data={"username": victim["email"], "password": victim["password"]})
    assert r.status_code == 200


def test_soft_delete_restore_and_email_freed(client):
    admin = _make_user(client, is_admin=True)
    victim = _make_user(client)
    original_email = victim["email"]

    r = client.delete(f"{API}/admin/users/{victim['id']}", headers=admin["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is not None

    # Original email freed for re-registration
    r = client.post(f"{API}/auth/register",
                    json={"email": original_email, "password": "GoodPass1!", "full_name": "New"})
    assert r.status_code == 201, r.text

    # Restore with a fresh email
    new_email = f"restored_{uuid.uuid4().hex[:6]}@example.com"
    r = client.post(f"{API}/admin/users/{victim['id']}/restore?new_email={new_email}",
                    headers=admin["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["deleted_at"] is None
    assert r.json()["email"] == new_email


def test_cannot_delete_self_or_last_admin(client):
    admin = _make_user(client, is_admin=True)
    r = client.delete(f"{API}/admin/users/{admin['id']}", headers=admin["headers"])
    assert r.status_code == 400


def test_purge_removes_rows_and_files(client):
    from app.core.database import SessionLocal
    from app.models.user import User
    from app.api.v1.admin import purge_deleted_users
    from app.core.config import settings

    admin = _make_user(client, is_admin=True)
    victim = _make_user(client)

    # Give the victim an uploads dir with a file
    vdir = os.path.join(settings.UPLOAD_DIR, f"user_{victim['id']}")
    os.makedirs(vdir, exist_ok=True)
    with open(os.path.join(vdir, "junk.csv"), "w") as fh:
        fh.write("a,b\n1,2\n")

    client.delete(f"{API}/admin/users/{victim['id']}", headers=admin["headers"])

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == victim["id"]).first()
        u.deleted_at = datetime.utcnow() - timedelta(days=settings.ADMIN_USER_RETENTION_DAYS + 1)
        db.commit()
        purged = purge_deleted_users(db)
        assert purged >= 1
        assert db.query(User).filter(User.id == victim["id"]).first() is None
    finally:
        db.close()
    assert not os.path.exists(vdir)


def test_self_service_deletion_requires_password(client):
    user = _make_user(client)
    # wrong password → 403
    r = client.request("DELETE", f"{API}/auth/users/me", headers=user["headers"],
                       json={"password": "WrongPass1!"})
    assert r.status_code == 403
    # correct password → deleted, token dead
    r = client.request("DELETE", f"{API}/auth/users/me", headers=user["headers"],
                       json={"password": user["password"]})
    assert r.status_code == 204, r.text
    r = client.get(f"{API}/auth/users/me", headers=user["headers"])
    assert r.status_code in (401, 403)


def test_audit_log_records_actions(client):
    admin = _make_user(client, is_admin=True)
    victim = _make_user(client)
    client.put(f"{API}/admin/users/{victim['id']}/deactivate", headers=admin["headers"])
    r = client.get(f"{API}/admin/audit", headers=admin["headers"])
    assert r.status_code == 200
    assert any(row["action"] == "deactivate" and row["target_user_id"] == victim["id"]
               for row in r.json())
