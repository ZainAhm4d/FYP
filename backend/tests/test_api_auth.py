"""
Integration tests for the authentication API: registration, login, profile,
and the security edge cases (duplicate email, weak password, bad credentials,
missing/invalid token).
"""
import uuid

API = "/api/v1"


def _email():
    return f"auth_{uuid.uuid4().hex[:10]}@example.com"


def test_register_and_login_happy_path(client):
    email = _email()
    r = client.post(f"{API}/auth/register",
                    json={"email": email, "password": "GoodPass1!", "full_name": "A B"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == email
    assert "password" not in body and "hashed_password" not in body

    r = client.post(f"{API}/auth/login", data={"username": email, "password": "GoodPass1!"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_duplicate_email_rejected(client):
    email = _email()
    payload = {"email": email, "password": "GoodPass1!", "full_name": "Dup"}
    assert client.post(f"{API}/auth/register", json=payload).status_code == 201
    r = client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()


def test_weak_password_rejected(client):
    # Rejected either by pydantic schema (422) or validate_password (400):
    # too short / no uppercase / no special / no lowercase / no digit.
    for pw in ["short", "alllowercase1!", "NoSpecial1", "NOLOWER1!", "NoDigits!"]:
        r = client.post(f"{API}/auth/register",
                        json={"email": _email(), "password": pw, "full_name": "X"})
        assert r.status_code in (400, 422), f"password {pw!r} should be rejected"


def test_invalid_email_format_rejected(client):
    r = client.post(f"{API}/auth/register",
                    json={"email": "not-an-email", "password": "GoodPass1!", "full_name": "X"})
    assert r.status_code == 422  # pydantic EmailStr validation


def test_login_wrong_password(client):
    email = _email()
    client.post(f"{API}/auth/register",
                json={"email": email, "password": "GoodPass1!", "full_name": "X"})
    r = client.post(f"{API}/auth/login", data={"username": email, "password": "WrongPass1!"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post(f"{API}/auth/login",
                    data={"username": _email(), "password": "Whatever1!"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get(f"{API}/auth/users/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get(f"{API}/auth/users/me",
                   headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401


def test_me_returns_profile(client, auth):
    r = client.get(f"{API}/auth/users/me", headers=auth["headers"])
    assert r.status_code == 200
    assert r.json()["email"] == auth["email"]
