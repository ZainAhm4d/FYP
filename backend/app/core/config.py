"""
Application Configuration
Loads settings from environment variables
"""
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment"""
    
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AI-Driven BI Dashboard Generator"
    VERSION: str = "1.0.0"
    
    # Security
    SECRET_KEY: str  # Must be set in .env
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    DATABASE_URL: str = "sqlite:///./app.db"
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",  # VS Code Live Server default
        "http://127.0.0.1:5500"
    ]
    
    # File Upload
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    UPLOAD_DIR: str = "data/uploads"
    PROCESSED_DIR: str = "data/processed"
    ALLOWED_EXTENSIONS: set[str] = {"csv", "xlsx", "xls"}

    # OpenRouter LLM (optional — enhanced NLP when key is present).
    OPENROUTER_API_KEY: Optional[str] = None
    # Optional comma-separated list of additional OpenRouter API keys (e.g. from
    # separate accounts) so the parser can rotate to another key when one hits
    # its rate limit instead of making the user wait. If unset, only
    # OPENROUTER_API_KEY is used. OPENROUTER_API_KEY (if also set) is always
    # included as the first key.
    OPENROUTER_API_KEYS: Optional[str] = None
    OPENROUTER_MODEL: str = "meta-llama/llama-3.2-3b-instruct:free"

    # ── Email / Scheduled Reports (optional) ─────────────────────────────────
    # Set one of the two providers below; if neither is set, emails are logged
    # to the console only (useful for local dev / FYP demo).

    # Option A — Resend (preferred, resend.com — free 3 000 emails/month)
    RESEND_API_KEY: Optional[str] = None

    # Option B — SendGrid
    SENDGRID_API_KEY: Optional[str] = None

    # Option C — SMTP (e.g. Gmail with App Password)
    SMTP_HOST:     Optional[str] = None
    SMTP_PORT:     int           = 587
    SMTP_USER:     Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS:  bool          = True

    # Sender address — required for any provider
    REPORT_FROM_EMAIL: str = "noreply@bidashboard.local"

    # ── Admin portal (CH-18) ─────────────────────────────────────────────────
    # When both are set, a superadmin account is seeded at startup (idempotent).
    # Values live in .env only — never log or echo them.
    ADMIN_EMAIL:    Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    # Soft-deleted accounts are kept recoverable this many days, then a daily
    # job hard-purges their rows AND uploaded/processed files. 30 days covers
    # accidental (or malicious-admin) deletion recovery, then honors erasure.
    ADMIN_USER_RETENTION_DAYS: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
