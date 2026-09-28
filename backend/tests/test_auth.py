"""Tests for user authentication, registration, login, logout, and account management."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestRegistration:
    def test_register_valid_user(self):
        email = f"user_{id(self)}@example.com"
        resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": "Password123!"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == email

    def test_register_duplicate_email_fails(self):
        email = f"dup_{id(self)}@example.com"
        client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
        resp = client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_register_invalid_email_fails(self):
        resp = client.post("/api/auth/register", json={"email": "not-an-email", "password": "Password123!"})
        assert resp.status_code == 400
        assert "Invalid email format" in resp.json()["detail"]

    def test_register_weak_password_fails(self):
        resp = client.post("/api/auth/register", json={"email": "weak@example.com", "password": "short"})
        assert resp.status_code == 400
        assert "at least 8 characters" in resp.json()["detail"]


class TestLogin:
    def test_login_success(self):
        email = f"login_test_{id(self)}@example.com"
        client.post("/api/auth/register", json={"email": email, "password": "SecurePassword1!"})

        resp = client.post("/api/auth/login", json={"email": email, "password": "SecurePassword1!"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email"] == email

    def test_login_wrong_password_fails(self):
        email = f"wrong_pw_{id(self)}@example.com"
        client.post("/api/auth/register", json={"email": email, "password": "SecurePassword1!"})

        resp = client.post("/api/auth/login", json={"email": email, "password": "WrongPassword99!"})
        assert resp.status_code == 401
        assert "Incorrect email or password" in resp.json()["detail"]

    def test_login_nonexistent_user_fails(self):
        resp = client.post("/api/auth/login", json={"email": "nonexistent@example.com", "password": "Password123!"})
        assert resp.status_code == 401


class TestUserProfileAndSessions:
    def test_get_me_authenticated(self):
        email = f"me_test_{id(self)}@example.com"
        reg = client.post("/api/auth/register", json={"email": email, "password": "Password123!"}).json()
        token = reg["access_token"]

        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == email

    def test_get_me_unauthenticated_fails(self):
        client.cookies.clear()
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_logout(self):
        email = f"logout_test_{id(self)}@example.com"
        reg = client.post("/api/auth/register", json={"email": email, "password": "Password123!"}).json()
        token = reg["access_token"]

        resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "Logged out" in resp.json()["message"]

    def test_logout_all(self):
        email = f"logout_all_{id(self)}@example.com"
        reg = client.post("/api/auth/register", json={"email": email, "password": "Password123!"}).json()
        token = reg["access_token"]

        resp = client.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "All sessions revoked" in resp.json()["message"]

    def test_delete_account(self):
        email = f"del_acc_{id(self)}@example.com"
        reg = client.post("/api/auth/register", json={"email": email, "password": "Password123!"}).json()
        token = reg["access_token"]

        resp = client.delete("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        # Login should now fail
        login_resp = client.post("/api/auth/login", json={"email": email, "password": "Password123!"})
        assert login_resp.status_code == 401
