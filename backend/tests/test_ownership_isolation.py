"""Cross-user document ownership and isolation tests."""

from io import BytesIO
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_user(email_prefix: str) -> tuple[str, str]:
    email = f"{email_prefix}_{id(email_prefix)}@example.com"
    resp = client.post("/api/auth/register", json={"email": email, "password": "Password123!"})
    data = resp.json()
    return data["user"]["id"], data["access_token"]


def _make_jpeg_bytes() -> bytes:
    buf = BytesIO()
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestOwnershipIsolation:
    def test_cross_user_isolation(self):
        # 1. Create User A and User B
        _, token_a = _create_user("user_a")
        _, token_b = _create_user("user_b")

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 2. User A uploads a document
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("doc_a.jpg", _make_jpeg_bytes(), "image/jpeg")},
            headers=headers_a,
        )
        assert upload_resp.status_code == 201
        doc_a_id = upload_resp.json()["id"]

        # 3. User A can access their document
        resp_a = client.get(f"/api/documents/{doc_a_id}", headers=headers_a)
        assert resp_a.status_code == 200

        # 4. User B CANNOT access User A's document (403)
        resp_b = client.get(f"/api/documents/{doc_a_id}", headers=headers_b)
        assert resp_b.status_code == 403

        # 5. User B CANNOT preview User A's document (403)
        preview_b = client.get(f"/api/documents/{doc_a_id}/preview", headers=headers_b)
        assert preview_b.status_code == 403

        # 6. User B CANNOT detect text on User A's document (403)
        detect_b = client.post(
            f"/api/documents/{doc_a_id}/detect",
            json={"query": "test"},
            headers=headers_b,
        )
        assert detect_b.status_code == 403

        # 7. User B CANNOT create edit on User A's document (403)
        edit_b = client.post(
            f"/api/documents/{doc_a_id}/edits",
            json={
                "page_number": 0,
                "original_text": "old",
                "replacement_text": "new",
                "original_box": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.05},
            },
            headers=headers_b,
        )
        assert edit_b.status_code == 403

        # 8. User B CANNOT list edits on User A's document (403)
        list_edits_b = client.get(f"/api/documents/{doc_a_id}/edits", headers=headers_b)
        assert list_edits_b.status_code == 403

        # 9. User B CANNOT export User A's document (403)
        export_b = client.post(
            f"/api/documents/{doc_a_id}/exports",
            json={"output_format": "png", "mode": "preserve"},
            headers=headers_b,
        )
        assert export_b.status_code == 403

        # 10. User B CANNOT delete User A's document (403)
        delete_b = client.delete(f"/api/documents/{doc_a_id}", headers=headers_b)
        assert delete_b.status_code == 403

        # 11. User A CAN delete their own document
        delete_a = client.delete(f"/api/documents/{doc_a_id}", headers=headers_a)
        assert delete_a.status_code == 200
