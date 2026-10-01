"""Authentication dependencies specific to Avenqo AI entry points."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.models import CompanyMembership


def get_active_ai_membership(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> CompanyMembership:
    membership = db.scalar(
        select(CompanyMembership).where(
            CompanyMembership.user_id == identity.user.id,
            CompanyMembership.company_id == identity.user.company_id,
            CompanyMembership.is_active.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="An active tenant membership is required for AI access.",
        )
    return membership