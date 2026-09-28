"""Application configuration using pydantic-settings."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Central configuration for the PDF Editor backend."""

    # --- Project paths ---
    BASE_DIR: Path = BACKEND_DIR
    UPLOAD_DIR: Path = BACKEND_DIR / "uploads"
    DATA_DIR: Path = BASE_DIR / "data"
    LOCAL_MODE: bool = True

    # --- Database ---
    DATABASE_URL: str = f"sqlite:///{BACKEND_DIR / 'pdf_editor.db'}"

    # --- Auth & Security ---
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "pdf-editor-super-secret-key-32-bytes-secure-production-random-token-xyz")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_NAME: str = "pdf_access_token"
    COOKIE_SECURE: bool = False  # Set to True in production with HTTPS
    COOKIE_SAMESITE: str = "lax"

    # --- Storage Abstraction ---
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")  # "local" or "s3"
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")

    # --- Usage Limits ---
    MAX_FILE_SIZE_MB: int = 50
    MAX_PDF_PAGES: int = 100
    MAX_IMAGE_PIXELS: int = 25000000  # 25 MP max to prevent decompression bombs
    MAX_DOCUMENTS_PER_USER: int = 100
    MAX_EXPORTS_PER_HOUR: int = 30
    MAX_OCR_PER_HOUR: int = 50
    MAX_STORAGE_PER_USER_MB: int = 250
    RATE_LIMIT_PER_MINUTE: int = 120

    # --- File constraints ---
    ALLOWED_EXTENSIONS: set[str] = {"jpg", "jpeg", "png", "pdf"}
    ALLOWED_MIME_TYPES: set[str] = {
        "image/jpeg",
        "image/png",
        "application/pdf",
    }

    # --- Cleanup ---
    FILE_TTL_MINUTES: int = 60
    CLEANUP_INTERVAL_SECONDS: int = 300

    # --- Preview ---
    PREVIEW_DPI: int = 150

    # --- CORS ---
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    class Config:
        env_file = PROJECT_DIR / ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


settings = Settings()
