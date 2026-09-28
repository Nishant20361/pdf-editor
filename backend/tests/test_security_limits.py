"""Security headers, observability, and background job tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.job_service import job_manager
from app.storage import get_storage

client = TestClient(app)


class TestObservabilityAndHealth:
    def test_health_endpoint(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert "version" in resp.json()

    def test_readiness_endpoint(self):
        resp = client.get("/api/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"] == "connected"
        assert data["checks"]["storage"] == "writeable"


class TestSecurityHardening:
    def test_security_headers_present(self):
        resp = client.get("/api/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers

    def test_request_id_attached(self):
        resp = client.get("/api/health")
        assert "X-Request-ID" in resp.headers


class TestStorageAbstraction:
    def test_local_storage_crud(self):
        storage = get_storage()
        test_data = b"storage abstraction test data"
        filename = "unit_test_file.txt"

        # Save
        path_str = storage.save("originals", filename, test_data)
        assert storage.exists("originals", filename)

        # Read
        read_bytes = storage.read("originals", filename)
        assert read_bytes == test_data

        # Delete
        assert storage.delete("originals", filename)
        assert not storage.exists("originals", filename)


class TestBackgroundJobs:
    def test_job_creation_and_cancellation(self):
        job = job_manager.create_job("test_ocr_job", user_id=None)
        assert job.id is not None
        assert job.status.value == "queued"

        # Get via API
        resp = client.get(f"/api/jobs/{job.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test_ocr_job"

        # Cancel
        cancel_resp = client.post(f"/api/jobs/{job.id}/cancel")
        assert cancel_resp.status_code == 200

        # Check status is cancelled
        resp2 = client.get(f"/api/jobs/{job.id}")
        assert resp2.json()["status"] == "cancelled"
