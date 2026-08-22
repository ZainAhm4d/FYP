"""
Dashboard Management Endpoints
CRUD operations for dashboard persistence
"""
import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.dashboard import (
    Dashboard,
    DashboardCreate,
    DashboardUpdate,
    DashboardListItem,
    DashboardExport,
    ShareResponse,
    PublicDashboardResponse,
    PdfFromImagesRequest,
)
from app.crud import dashboard as crud_dashboard
from app.crud import collaboration as crud_collab

router = APIRouter()


@router.post("", response_model=Dashboard, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    dashboard_data: DashboardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new dashboard
    
    - **name**: Dashboard name (required, max 100 chars)
    - **description**: Dashboard description (optional, max 500 chars)
    - **config_json**: Dashboard configuration with charts and layout
    """
    try:
        db_dashboard = crud_dashboard.create_dashboard(
            db=db,
            dashboard=dashboard_data,
            user_id=current_user.id
        )
        
        # Parse config_json back to dict for response
        db_dashboard.config_json = json.loads(db_dashboard.config_json)
        
        return db_dashboard
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create dashboard: {str(e)}"
        )


@router.get("", response_model=List[DashboardListItem])
async def get_dashboards(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all dashboards for the current user
    
    Returns a list of dashboards with basic metadata
    """
    try:
        dashboards = crud_dashboard.get_dashboards(
            db=db,
            user_id=current_user.id,
            skip=skip,
            limit=limit
        )

        def _to_item(dashboard, shared_role=None):
            config = json.loads(dashboard.config_json)
            desc = dashboard.description
            if shared_role:
                # Surface shared status without a schema change
                desc = f"[Shared with you — {shared_role}] {desc or ''}".strip()
            return DashboardListItem(
                id=dashboard.id,
                name=dashboard.name,
                description=desc,
                chart_count=len(config.get('charts', [])),
                is_public=bool(dashboard.is_public),
                created_at=dashboard.created_at,
                updated_at=dashboard.updated_at,
            )

        dashboard_list = [_to_item(d) for d in dashboards]

        # Dashboards shared with this user via collaboration
        from app.models.collaboration import DashboardCollaborator
        from app.models.dashboard import Dashboard as DashboardModel
        shared = (
            db.query(DashboardCollaborator, DashboardModel)
            .join(DashboardModel, DashboardCollaborator.dashboard_id == DashboardModel.id)
            .filter(DashboardCollaborator.user_id == current_user.id)
            .all()
        )
        for collab, dashboard in shared:
            dashboard_list.append(_to_item(dashboard, shared_role=collab.role))

        return dashboard_list
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve dashboards: {str(e)}"
        )


@router.get("/{dashboard_id}", response_model=Dashboard)
async def get_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific dashboard by ID
    
    Returns full dashboard configuration including all charts
    """
    try:
        # Owner access
        db_dashboard = crud_dashboard.get_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            user_id=current_user.id,
        )

        # Collaborator access (viewer or editor)
        if not db_dashboard:
            role = crud_collab.get_user_role(db, dashboard_id, current_user.id)
            if role:
                from app.models.dashboard import Dashboard as DashboardModel
                db_dashboard = db.query(DashboardModel).filter_by(id=dashboard_id).first()

        if not db_dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found"
            )

        db_dashboard.config_json = json.loads(db_dashboard.config_json)
        return db_dashboard

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve dashboard: {str(e)}"
        )


@router.put("/{dashboard_id}", response_model=Dashboard)
async def update_dashboard(
    dashboard_id: int,
    dashboard_update: DashboardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing dashboard
    
    Can update name, description, and/or config_json
    Only provided fields will be updated
    """
    try:
        db_dashboard = crud_dashboard.update_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            user_id=current_user.id,
            dashboard_update=dashboard_update,
        )

        # Allow editors to update too
        if not db_dashboard:
            role = crud_collab.get_user_role(db, dashboard_id, current_user.id)
            if role == "editor":
                from app.models.dashboard import Dashboard as DashboardModel
                target = db.query(DashboardModel).filter_by(id=dashboard_id).first()
                if target:
                    db_dashboard = crud_dashboard.update_dashboard(
                        db=db,
                        dashboard_id=dashboard_id,
                        user_id=target.user_id,
                        dashboard_update=dashboard_update,
                    )

        if not db_dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found"
            )
        
        # Parse config_json back to dict for response
        db_dashboard.config_json = json.loads(db_dashboard.config_json)
        
        return db_dashboard
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update dashboard: {str(e)}"
        )


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a dashboard
    
    Returns 204 No Content on success
    Returns 404 if dashboard not found
    """
    try:
        deleted = crud_dashboard.delete_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            user_id=current_user.id
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found"
            )
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete dashboard: {str(e)}"
        )


@router.get("/shared/{share_token}", response_model=PublicDashboardResponse)
async def get_shared_dashboard(
    share_token: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve a publicly shared dashboard by token — no authentication required.
    Increments the view counter on each access.
    """
    try:
        db_dashboard = crud_dashboard.get_dashboard_by_token(db, share_token)
        if not db_dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared dashboard not found or sharing has been disabled",
            )
        crud_dashboard.increment_view_count(db, db_dashboard)
        db_dashboard.config_json = json.loads(db_dashboard.config_json)
        return db_dashboard
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve shared dashboard: {str(e)}",
        )


@router.post("/{dashboard_id}/share", response_model=ShareResponse)
async def enable_sharing(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a public share link for a dashboard.
    Idempotent — calling it again returns the same token.
    """
    try:
        from app.core.config import settings
        db_dashboard = crud_dashboard.enable_sharing(db, dashboard_id, current_user.id)
        if not db_dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        share_url = f"http://localhost:5500/shared-dashboard.html?token={db_dashboard.share_token}"
        return ShareResponse(
            share_token=db_dashboard.share_token,
            share_url=share_url,
            is_public=db_dashboard.is_public,
            view_count=db_dashboard.view_count or 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable sharing: {str(e)}",
        )


@router.delete("/{dashboard_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def disable_sharing(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke the share link for a dashboard (makes it private again)."""
    try:
        db_dashboard = crud_dashboard.disable_sharing(db, dashboard_id, current_user.id)
        if not db_dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable sharing: {str(e)}",
        )


@router.get("/{dashboard_id}/export")
async def export_dashboard(
    dashboard_id: int,
    format: str = Query(default="json", pattern="^(json|pdf|png|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Export a dashboard.

    **format** (query param, default `json`):
    - `json` — dashboard configuration as JSON (existing behaviour)
    - `pdf`  — multi-page PDF, one chart per page with insights
    - `png`  — ZIP archive, one high-res PNG per chart
    - `csv`  — ZIP archive, one CSV per chart (tabular query data)
    """
    from datetime import datetime

    try:
        db_dashboard = crud_dashboard.get_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            user_id=current_user.id,
        )
        if not db_dashboard:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found",
            )

        config = json.loads(db_dashboard.config_json)
        charts = config.get("charts", [])
        safe_name = db_dashboard.name.replace(" ", "_").replace("/", "-")[:60]

        # ── JSON (default, backward-compatible) ─────────────────────────────
        if format == "json":
            export_data = DashboardExport(
                dashboard_name=db_dashboard.name,
                exported_at=datetime.utcnow(),
                charts=charts,
                data={
                    "description": db_dashboard.description,
                    "layout": config.get("layout", "grid"),
                    "chart_count": len(charts),
                    "created_at": db_dashboard.created_at.isoformat(),
                    "updated_at": db_dashboard.updated_at.isoformat(),
                },
            )
            return export_data

        # ── Binary exports ───────────────────────────────────────────────────
        from app.services.visualization.export_manager import ExportManager

        mgr = ExportManager()

        if format == "pdf":
            pdf_bytes = mgr.dashboard_to_pdf(
                dashboard_name=db_dashboard.name,
                description=db_dashboard.description or "",
                charts=charts,
            )
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_name}.pdf"'
                },
            )

        if format == "png":
            zip_bytes = mgr.dashboard_to_png_zip(charts)
            return StreamingResponse(
                io.BytesIO(zip_bytes),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_name}_charts.zip"'
                },
            )

        if format == "csv":
            zip_bytes = mgr.dashboard_to_csv_zip(charts)
            return StreamingResponse(
                io.BytesIO(zip_bytes),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_name}_data.zip"'
                },
            )

    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export dashboard: {str(e)}",
        )


@router.post("/{dashboard_id}/export/pdf")
async def export_dashboard_pdf_from_images(
    dashboard_id: int,
    body: PdfFromImagesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Assemble a PDF from chart images captured client-side by the browser.

    The browser renders each chart to a base64 PNG via `Plotly.toImage()` and
    POSTs them here. The server assembles the PDF with reportlab — no Kaleido
    needed, so this is fast regardless of the number of charts.
    """
    try:
        db_dashboard = crud_dashboard.get_dashboard(db, dashboard_id, current_user.id)
        if not db_dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")

        from app.services.visualization.export_manager import ExportManager
        mgr = ExportManager()
        pdf_bytes = mgr.dashboard_to_pdf_from_images(
            dashboard_name=body.dashboard_name or db_dashboard.name,
            description=body.description or (db_dashboard.description or ""),
            charts=[c.model_dump() for c in body.charts],
        )
        safe_name = db_dashboard.name.replace(" ", "_").replace("/", "-")[:60]
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
        )
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(e)}",
        )
