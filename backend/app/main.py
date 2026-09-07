"""
FastAPI Main Application
Entry point for the BI Dashboard Generator API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.api.v1 import auth, datasets, queries, dashboards, anomalies, schedules, collaborations, relationships, admin
from app.services.nlp import preload_model
from app.services.scheduler import report_scheduler

# Create database tables (new tables only; existing tables are not altered)
Base.metadata.create_all(bind=engine)


def _apply_schema_migrations() -> None:
    """Idempotent column additions for tables created before new columns were defined."""
    stmts = [
        # Sharing columns on dashboards (Day 5)
        "ALTER TABLE dashboards ADD COLUMN share_token VARCHAR",
        "ALTER TABLE dashboards ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE dashboards ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0",
        # query_history table is created by create_all; no ALTER needed.
        # Schedule timing columns (Phase 3 upgrade)
        "ALTER TABLE report_schedules ADD COLUMN send_hour INTEGER NOT NULL DEFAULT 8",
        "ALTER TABLE report_schedules ADD COLUMN send_minute INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE report_schedules ADD COLUMN day_of_week INTEGER",
        "ALTER TABLE report_schedules ADD COLUMN day_of_month INTEGER",
        "ALTER TABLE report_schedules ADD COLUMN timezone VARCHAR NOT NULL DEFAULT 'UTC'",
        # Background-processing status (real-time upload fix)
        "ALTER TABLE datasets ADD COLUMN processing_status VARCHAR NOT NULL DEFAULT 'ready'",
        # Live-data source tracking (Google Sheets auto-refresh)
        "ALTER TABLE datasets ADD COLUMN source_type VARCHAR NOT NULL DEFAULT 'upload'",
        "ALTER TABLE datasets ADD COLUMN source_url VARCHAR",
        "ALTER TABLE datasets ADD COLUMN refresh_interval_minutes INTEGER",
        "ALTER TABLE datasets ADD COLUMN last_refreshed DATETIME",
        "ALTER TABLE datasets ADD COLUMN ingest_token VARCHAR",
        # CH-09: inferred join cardinality on relationships
        "ALTER TABLE dataset_relationships ADD COLUMN cardinality VARCHAR",
        # CH-10: when a push webhook last delivered for this dataset
        "ALTER TABLE datasets ADD COLUMN last_push_at DATETIME",
        # CH-18: admin portal + account lifecycle
        "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN deleted_at DATETIME",
        "ALTER TABLE users ADD COLUMN deactivated_at DATETIME",
        "ALTER TABLE users ADD COLUMN last_login_at DATETIME",
    ]
    db = SessionLocal()
    try:
        for stmt in stmts:
            try:
                db.execute(text(stmt))
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()


_apply_schema_migrations()

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS — local-dev defaults plus any production origin(s) set via
# the CORS_ORIGINS env var (see core/config.py).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_effective,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Pre-load the NLP model, seed the admin account, start the scheduler."""
    preload_model()
    # CH-18: idempotent superadmin seed from ADMIN_EMAIL/ADMIN_PASSWORD env vars
    from app.core.database import SessionLocal
    from app.api.v1.admin import seed_admin_account
    db = SessionLocal()
    try:
        seed_admin_account(db)
    finally:
        db.close()
    report_scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    report_scheduler.shutdown()


# Root endpoint
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "AI-Driven BI Dashboard Generator API",
        "version": settings.VERSION,
        "docs": "/docs"
    }


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# Include API routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(datasets.router, prefix=f"{settings.API_V1_STR}/datasets", tags=["Datasets"])
app.include_router(queries.router, prefix=f"{settings.API_V1_STR}/queries", tags=["Queries"])
app.include_router(dashboards.router, prefix=f"{settings.API_V1_STR}/dashboards", tags=["Dashboards"])
app.include_router(anomalies.router,  prefix=f"{settings.API_V1_STR}",             tags=["Anomalies"])
app.include_router(schedules.router,       prefix=f"{settings.API_V1_STR}/schedules",   tags=["Schedules"])
app.include_router(collaborations.router, prefix=f"{settings.API_V1_STR}/dashboards",    tags=["Collaborations"])
app.include_router(relationships.router,  prefix=f"{settings.API_V1_STR}/relationships", tags=["Relationships"])
app.include_router(admin.router,           prefix=f"{settings.API_V1_STR}/admin",         tags=["Admin"])
