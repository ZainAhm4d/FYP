"""
Collaboration Endpoints
Manage per-dashboard collaborators (invite, list, update role, revoke).
All mutating actions require the caller to be the dashboard owner.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.collaboration import (
    InviteCollaboratorRequest,
    UpdateRoleRequest,
    CollaboratorOut,
)
from app.crud import collaboration as crud_collab

router = APIRouter()


def _collab_to_out(c) -> CollaboratorOut:
    return CollaboratorOut(
        id=c.id,
        user_id=c.user_id,
        email=c.user.email,
        full_name=c.user.full_name,
        role=c.role,
        created_at=c.created_at,
    )


@router.post("/{dashboard_id}/collaborators", response_model=CollaboratorOut, status_code=status.HTTP_201_CREATED)
async def invite_collaborator(
    dashboard_id: int,
    body: InviteCollaboratorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invite a registered user to a dashboard by email."""
    collab, err = crud_collab.invite_collaborator(
        db=db,
        dashboard_id=dashboard_id,
        owner_id=current_user.id,
        email=body.email,
        role=body.role,
    )
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return _collab_to_out(collab)


@router.get("/{dashboard_id}/collaborators", response_model=List[CollaboratorOut])
async def list_collaborators(
    dashboard_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all collaborators on a dashboard (owner only)."""
    collabs, err = crud_collab.list_collaborators(
        db=db,
        dashboard_id=dashboard_id,
        owner_id=current_user.id,
    )
    if err:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err)
    return [_collab_to_out(c) for c in collabs]


@router.put("/{dashboard_id}/collaborators/{collaborator_id}", response_model=CollaboratorOut)
async def update_collaborator_role(
    dashboard_id: int,
    collaborator_id: int,
    body: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a collaborator's role (owner only)."""
    collab, err = crud_collab.update_role(
        db=db,
        dashboard_id=dashboard_id,
        collaborator_id=collaborator_id,
        owner_id=current_user.id,
        role=body.role,
    )
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return _collab_to_out(collab)


@router.delete("/{dashboard_id}/collaborators/{collaborator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_collaborator(
    dashboard_id: int,
    collaborator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a collaborator from a dashboard (owner only)."""
    _, err = crud_collab.revoke(
        db=db,
        dashboard_id=dashboard_id,
        collaborator_id=collaborator_id,
        owner_id=current_user.id,
    )
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return None
