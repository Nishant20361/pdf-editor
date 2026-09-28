# PDF Editor — Production-Ready Web Application

A secure, high-performance web application for uploading, previewing, searching, editing, and exporting text in both images and native/scanned PDFs. Built with FastAPI, Next.js, PyMuPDF, OpenCV, and SQLAlchemy with multi-tenant user authentication and PostgreSQL/SQLite persistence.

---

## Architecture Overview

```
                          ┌───────────────────────────┐
                          │   Reverse Proxy (Nginx)   │
                          │   Ports: 80 / 443 (SSL)   │
                          └─────────────┬─────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 │                                             │
                 ▼                                             ▼
    ┌──────────────────────────┐                  ┌──────────────────────────┐
    │   Next.js 16 Frontend    │                  │     FastAPI Backend      │
    │   Port: 3000             │                  │     Port: 8000           │
    │   - Tailwind CSS v4      │                  │   - Python 3.11+         │
    │   - React 19 Client      │                  │   - PyMuPDF / OpenCV     │
    │   - Auth & Dashboard UI  │                  │   - Bcrypt + PyJWT Auth  │
    └──────────────────────────┘                  └─────────────┬────────────┘
                                                                │
                                      ┌─────────────────────────┼─────────────────────────┐
                                      ▼                         ▼                         ▼
                          ┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
                          │   PostgreSQL / SQLite │ │    Storage Engine     │ │   Background Jobs     │
                          │   - Users & Sessions  │ │   - Local disk        │ │   - OCR / Rendering   │
                          │   - Documents & Edits │ │   - S3 / Object Store │ │   - Large Exports     │
                          │   - Audits & Quotas   │ │   - Signed URLs       │ │   - Temp File Cleanup │
                          └───────────────────────┘ └───────────────────────┘ └───────────────────────┘
```

---

## Features

### 1. Document Upload & Preview (Phase 1)
- Drag-and-drop file upload with real-time upload progress.
- Validation: strict magic-byte file signature validation, MIME-type verification, and path traversal protection.
- High-resolution preview rendering for single images and multi-page PDFs.

### 2. Smart Text Detection & OCR (Phase 2)
- Fast native PDF text extraction with exact coordinate extraction.
- Automatic fallback to RapidOCR / Tesseract for scanned pages and images.
- Case-sensitive and exact-match search capabilities.

### 3. Realistic Text Replacement (Phase 3)
- Vector-level PDF redaction and text insertion preserving background layout.
- Inpainting, blurring, and solid background cleanup for scanned documents.
- Automatic font matching, size scaling, weight/style controls, and custom color pickers.
- Undo, Redo, and Reset Page/Document controls.

### 4. High-Quality Export (Phase 4)
- Multi-format exports: PNG, JPEG (configurable quality), WebP, Vector PDF, Flattened PDF, and ZIP archives.
- Page selection: All, Current Page, Edited Pages Only, or Custom Page Ranges (e.g. `1-3, 5, 8-10`).
- Memory-efficient 8KB chunk streaming downloads.

### 5. Production Readiness & Persistence (Phase 5)
- **User Authentication**: Email/password registration, bcrypt hashing, JWT access tokens, and HTTP-only cookies.
- **Document Ownership & Isolation**: Strictly isolated documents, edits, and downloads between accounts.
- **Persistent Database**: SQLite for local development, PostgreSQL with connection pooling for production.
- **Auto-Save & Recovery**: All edits persist to database and reload seamlessly on page refresh or browser restart.
- **Storage Abstraction**: Swappable local disk storage and S3-compatible cloud storage (AWS S3, MinIO, Cloudflare R2).
- **Security Hardening**: Content Security Policy (CSP), X-Frame-Options, rate limiting, and log redaction.
- **Observability**: Dedicated `/api/health` and `/api/readiness` probe endpoints checking DB, storage, and queue.

---

## Project Structure

```
pdf-editor/
├── frontend/                     # Next.js 16 + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx        # App layout with Google Fonts
│   │   │   ├── page.tsx          # Main application page (Dashboard/Editor)
│   │   │   ├── providers.tsx     # Client provider wrapper
│   │   │   └── globals.css       # Design system and glassmorphism styles
│   │   ├── components/
│   │   │   ├── auth/             # Login and Registration modals
│   │   │   ├── dashboard/        # Authenticated document management dashboard
│   │   │   ├── editor/           # Workspace, canvas, font & replacement panels
│   │   │   ├── legal/            # Privacy Policy and Terms of Service modals
│   │   │   ├── preview/          # Sharp image and PDF renderers
│   │   │   └── upload/           # Drag-and-drop dropzone & progress bars
│   │   ├── lib/
│   │   │   ├── api.ts            # Authenticated API client
│   │   │   └── auth-context.tsx  # React authentication context
│   │   └── types/                # TypeScript shared models
│   ├── Dockerfile                # Production multi-stage build
│   └── package.json
│
├── backend/                      # FastAPI Python Application
│   ├── app/
│   │   ├── auth/                 # Authentication, JWT, and user management
│   │   ├── db/                   # SQLAlchemy models, sessions, and schema init
│   │   ├── models/               # Pydantic data schemas & persistent stores
│   │   ├── routers/              # API endpoints (upload, detection, edits, export, jobs)
│   │   ├── services/             # Core image/pdf processing, OCR, and export engine
│   │   ├── storage/              # Local and S3 storage abstraction
│   │   ├── utils/                # Security validation, rate limiter, middleware
│   │   ├── config.py             # App configuration via pydantic-settings
│   │   └── main.py               # Lifespan events, middlewares, exception handling
│   ├── tests/                    # 101 unit and integration tests (100% pass)
│   ├── Dockerfile                # Production backend container
│   └── requirements.txt
│
├── .github/workflows/ci.yml      # CI pipeline for linting, testing, and building
├── docker-compose.yml            # Multi-service production stack
├── nginx.conf                    # Nginx reverse proxy routing
├── .env.example                  # Environment variable reference
├── verify_phase5.py              # End-to-end verification test suite
└── README.md
```

---

## Quickstart (Local Development)

### Prerequisites
- Python 3.11+
- Node.js 20+ and npm

### 1. Start Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m app.db.init_db
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API server runs at `http://localhost:8000`. OpenAPI docs available at `http://localhost:8000/docs`.

### 2. Start Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## Production Deployment with Docker Compose

Deploy the complete stack (PostgreSQL, Redis, Backend, Frontend, and Nginx) with a single command:

```bash
# 1. Clone repository and navigate to root
cd "pdf editor"

# 2. Configure environment
cp .env.example .env
# Edit .env with your production secrets (e.g. JWT_SECRET_KEY, POSTGRES_PASSWORD)

# 3. Launch stack
docker compose up -d --build

# 4. Verify running services
docker compose ps
curl http://localhost/api/health
curl http://localhost/api/readiness
```

---

## Running Tests

### Backend Test Suite (101 tests)
```bash
cd backend
python3 -m pytest tests -v
```

### End-to-End System Verification
```bash
python3 verify_phase5.py
```

### Frontend Build & Typecheck
```bash
cd frontend
npm run build
```

---

## Security, Privacy, and Responsible Use

1. **Private by Default**: Documents and preview thumbnails belong strictly to the authenticated user and cannot be accessed across accounts.
2. **Immediate Deletion**: Deleting a document instantly removes the original upload, preview images, database records, and exported artifacts from server disks.
3. **No Content Logging**: OCR text, search queries, and replacement content are filtered and redacted from production logs.
4. **Decompression Bomb Protection**: Uploads enforce strict pixel count caps (max 25 MP) and PDF page count limits.

---

## License

MIT License. See LICENSE for details.
