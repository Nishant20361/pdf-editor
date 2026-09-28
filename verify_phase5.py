"""Comprehensive End-to-End Verification script for Phase 5."""

import json
import os
import shutil
import sys
import time
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF
import requests
from PIL import Image, ImageDraw, ImageFont

BASE_URL = "http://localhost:8000"
SCRATCH_DIR = Path("/tmp/phase5_verification")
shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

def step(title: str):
    print(f"\n========================================================")
    print(f"👉 STEP: {title}")
    print(f"========================================================")

def ok(msg: str):
    print(f"  ✅ PASS: {msg}")

def fail(msg: str):
    print(f"  ❌ FAIL: {msg}")
    sys.exit(1)

def main():
    print("🚀 Starting Phase 5 End-to-End Verification...")

    # Step 1: Health & Readiness
    step("1. Health & Readiness Probe Verification")
    r = requests.get(f"{BASE_URL}/api/health")
    if r.status_code != 200 or r.json().get("status") != "healthy":
        fail(f"Health check failed: {r.status_code} {r.text}")
    ok(f"Liveness probe healthy: {r.json()}")

    r = requests.get(f"{BASE_URL}/api/readiness")
    if r.status_code != 200 or r.json().get("status") != "ready":
        fail(f"Readiness check failed: {r.status_code} {r.text}")
    checks = r.json()["checks"]
    ok(f"Readiness probe passed: DB={checks['database']}, Storage={checks['storage']}, Queue={checks['queue']}")

    # Step 2: Register two test users
    step("2. User Registration & Authentication")
    ts = int(time.time())
    email_alice = f"alice_{ts}@e2e.local"
    email_bob = f"bob_{ts}@e2e.local"
    pw = "SuperSecret123!"

    r_alice = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email_alice, "password": pw})
    if r_alice.status_code != 201:
        fail(f"Alice registration failed: {r_alice.text}")
    token_alice = r_alice.json()["access_token"]
    user_alice_id = r_alice.json()["user"]["id"]
    ok(f"Alice registered successfully: {email_alice} (id: {user_alice_id[:8]}...)")

    r_bob = requests.post(f"{BASE_URL}/api/auth/register", json={"email": email_bob, "password": pw})
    if r_bob.status_code != 201:
        fail(f"Bob registration failed: {r_bob.text}")
    token_bob = r_bob.json()["access_token"]
    user_bob_id = r_bob.json()["user"]["id"]
    ok(f"Bob registered successfully: {email_bob} (id: {user_bob_id[:8]}...)")

    # Verify /api/auth/me
    headers_alice = {"Authorization": f"Bearer {token_alice}"}
    headers_bob = {"Authorization": f"Bearer {token_bob}"}

    me_alice = requests.get(f"{BASE_URL}/api/auth/me", headers=headers_alice).json()
    if me_alice["email"] != email_alice:
        fail(f"Alice profile check failed: {me_alice}")
    ok("Profile retrieval /api/auth/me verified")

    # Step 3: Create test files
    step("3. Create Test Image and Multi-Page PDF")
    # Image
    img = Image.new("RGB", (600, 300), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Original Invoice Total", fill=(20, 20, 20))
    img_path = SCRATCH_DIR / "alice_image.png"
    img.save(img_path, format="PNG")

    # Multi-page PDF
    pdf = fitz.open()
    for p_num, text_str in enumerate(["First Page Native Text", "Second Page Invoice", "Third Page Summary"]):
        page = pdf.new_page(width=595, height=842)
        page.insert_text((72, 100), text_str, fontsize=20, color=(0, 0, 0))
    pdf_path = SCRATCH_DIR / "alice_doc.pdf"
    pdf.save(str(pdf_path))
    pdf.close()
    ok("Generated test image and 3-page test PDF")

    # Step 4: Upload separate files for both users
    step("4. Upload Files for Alice and Bob")
    with open(img_path, "rb") as f:
        r_up_img = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("alice_invoice.png", f, "image/png")},
            headers=headers_alice,
        )
    if r_up_img.status_code != 201:
        fail(f"Alice image upload failed: {r_up_img.text}")
    alice_img_doc = r_up_img.json()
    ok(f"Alice uploaded image: id={alice_img_doc['id']}")

    with open(pdf_path, "rb") as f:
        r_up_pdf = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("alice_contract.pdf", f, "application/pdf")},
            headers=headers_alice,
        )
    if r_up_pdf.status_code != 201:
        fail(f"Alice PDF upload failed: {r_up_pdf.text}")
    alice_pdf_doc = r_up_pdf.json()
    ok(f"Alice uploaded PDF: id={alice_pdf_doc['id']}, pages={alice_pdf_doc['page_count']}")

    with open(img_path, "rb") as f:
        r_up_bob = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("bob_private.png", f, "image/png")},
            headers=headers_bob,
        )
    if r_up_bob.status_code != 201:
        fail(f"Bob upload failed: {r_up_bob.text}")
    bob_doc = r_up_bob.json()
    ok(f"Bob uploaded image: id={bob_doc['id']}")

    # Step 5: Verify Cross-User Isolation
    step("5. Cross-User Document Access Isolation")
    # Bob attempts to view Alice's document metadata
    r_iso_meta = requests.get(f"{BASE_URL}/api/documents/{alice_img_doc['id']}", headers=headers_bob)
    if r_iso_meta.status_code != 403:
        fail(f"Expected 403 for Bob accessing Alice metadata, got {r_iso_meta.status_code}")
    ok("Bob denied access to Alice metadata (HTTP 403)")

    # Bob attempts to preview Alice's PDF
    r_iso_prev = requests.get(f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/preview?page=0", headers=headers_bob)
    if r_iso_prev.status_code != 403:
        fail(f"Expected 403 for Bob previewing Alice PDF, got {r_iso_prev.status_code}")
    ok("Bob denied preview access to Alice document (HTTP 403)")

    # Bob attempts to detect text on Alice's PDF
    r_iso_det = requests.post(
        f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/detect",
        json={"query": "Invoice"},
        headers=headers_bob,
    )
    if r_iso_det.status_code != 403:
        fail(f"Expected 403 for Bob detecting text on Alice PDF, got {r_iso_det.status_code}")
    ok("Bob denied text detection on Alice document (HTTP 403)")

    # Dashboard listing check
    docs_alice = requests.get(f"{BASE_URL}/api/documents", headers=headers_alice).json()["documents"]
    docs_bob = requests.get(f"{BASE_URL}/api/documents", headers=headers_bob).json()["documents"]
    alice_ids = {d["id"] for d in docs_alice}
    bob_ids = {d["id"] for d in docs_bob}
    if bob_doc["id"] in alice_ids or alice_img_doc["id"] in bob_ids:
        fail("Dashboard documents leaking across users!")
    ok(f"Dashboard isolation verified: Alice sees {len(docs_alice)} docs, Bob sees {len(docs_bob)} docs")

    # Step 6: Detect and Replace Text
    step("6. Text Detection & Replacement Edits")
    # Detect on Alice's PDF
    det_resp = requests.post(
        f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/detect",
        json={"query": "Invoice"},
        headers=headers_alice,
    ).json()
    if not det_resp["detections"]:
        fail(f"No text detected for 'Invoice': {det_resp}")
    det = det_resp["detections"][0]
    ok(f"Detected text '{det['text']}' on page {det['page_number']}")

    # Apply replacement edit
    edit_resp = requests.post(
        f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/edits",
        json={
            "page_number": det["page_number"],
            "original_text": det["text"],
            "replacement_text": "REPLACED_E2E_INVOICE",
            "original_box": det["bounding_box"],
            "font_family": "Arial",
            "font_size": 18,
            "font_color": "#112233",
        },
        headers=headers_alice,
    )
    if edit_resp.status_code != 201:
        fail(f"Alice edit creation failed: {edit_resp.text}")
    edit_id = edit_resp.json()["id"]
    ok(f"Applied replacement edit id={edit_id}")

    # Step 7: Persistence & Edit Recovery
    step("7. Database Persistence & Edit Recovery")
    # Verify edits list returns persisted edit
    edits_list = requests.get(f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/edits", headers=headers_alice).json()
    if edits_list["count"] < 1:
        fail("Edits not found after saving")
    ok(f"Edit persistence verified: count={edits_list['count']}, text={edits_list['edits'][0]['replacement_text']}")

    # Step 8: Export Edited Multi-Page PDF & Download
    step("8. Export Multi-Page PDF with Edits")
    exp_resp = requests.post(
        f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/exports",
        json={"output_format": "pdf", "mode": "preserve"},
        headers=headers_alice,
    )
    if exp_resp.status_code != 201:
        fail(f"Export creation failed: {exp_resp.text}")
    exp_job = exp_resp.json()
    ok(f"Export job created: id={exp_job['id']}, status={exp_job['status']}")

    # Download export
    dl_resp = requests.get(
        f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/exports/{exp_job['id']}/download",
        headers=headers_alice,
    )
    if dl_resp.status_code != 200:
        fail(f"Download failed: {dl_resp.status_code}")
    exported_pdf_path = SCRATCH_DIR / "exported_contract.pdf"
    exported_pdf_path.write_bytes(dl_resp.content)
    ok(f"Downloaded exported PDF ({len(dl_resp.content)} bytes)")

    # Verify exported PDF content with fitz
    exp_doc = fitz.open(str(exported_pdf_path))
    if exp_doc.page_count != 3:
        fail(f"Exported PDF page count wrong: {exp_doc.page_count}")
    p1_text = exp_doc[1].get_text()
    if "REPLACED_E2E_INVOICE" not in p1_text:
        fail(f"Replaced text not in exported PDF: {p1_text}")
    ok(f"Verified replacement string 'REPLACED_E2E_INVOICE' is in exported PDF page 2!")
    exp_doc.close()

    # Step 9: Unauthorized Download Attempt Fails
    step("9. Unauthorized Download Protection")
    r_unauth_dl = requests.get(
        f"{BASE_URL}/api/documents/{alice_pdf_doc['id']}/exports/{exp_job['id']}/download",
        headers=headers_bob,
    )
    if r_unauth_dl.status_code != 403:
        fail(f"Expected 403 for Bob downloading Alice's export, got {r_unauth_dl.status_code}")
    ok("Bob denied download of Alice's export (HTTP 403)")

    # Step 10: Delete Document and File Cleanup
    step("10. Document Deletion & Storage Cleanup")
    del_resp = requests.delete(f"{BASE_URL}/api/documents/{alice_img_doc['id']}", headers=headers_alice)
    if del_resp.status_code != 200:
        fail(f"Failed to delete document: {del_resp.text}")
    ok(f"Deleted document {alice_img_doc['id']}")

    # Confirm deletion from API
    confirm_del = requests.get(f"{BASE_URL}/api/documents/{alice_img_doc['id']}", headers=headers_alice)
    if confirm_del.status_code != 404:
        fail(f"Expected 404 after deletion, got {confirm_del.status_code}")
    ok("Verified document no longer exists (HTTP 404)")

    # Step 11: Security Headers & Request-ID
    step("11. Security Headers & Request-ID Verification")
    h_resp = requests.get(f"{BASE_URL}/api/health")
    assert "X-Request-ID" in h_resp.headers, "Missing X-Request-ID"
    assert "X-Content-Type-Options" in h_resp.headers, "Missing X-Content-Type-Options"
    assert "X-Frame-Options" in h_resp.headers, "Missing X-Frame-Options"
    assert "Content-Security-Policy" in h_resp.headers, "Missing Content-Security-Policy"
    ok("All security headers (CSP, X-Frame-Options, X-Content-Type-Options, X-Request-ID) present")

    print("\n🎉 ALL 11 END-TO-END VERIFICATION STEPS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
