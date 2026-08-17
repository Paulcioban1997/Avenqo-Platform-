"""Routes protégées de gestion des employés du tenant courant."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.permissions import permissions_for
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_account_notifier, require_permission
from backend.app.models import User
from backend.app.schemas.auth import UserResponse
from backend.app.schemas.employees import EmployeeCreateRequest, EmployeeUpdateRequest
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.employee_service import (
    EmployeeConflictError,
    EmployeeNotFoundError,
    EmployeePermissionError,
    EmployeeService,
)

router = APIRouter(prefix="/employees", tags=["employees"])
manage_users = require_permission("users:manage")


def get_employee_service(
    db: Session = Depends(get_db),
    notifier: AccountNotifier = Depends(get_account_notifier),
) -> EmployeeService:
    return EmployeeService(db, notifier)


def employee_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        company_id=user.company_id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        role=user.role,
        permissions=permissions_for(user.role),
        is_active=user.is_active,
        email_verified_at=user.email_verified_at,
    )


@router.get("", response_model=list[UserResponse])
def list_employees(
    identity: CurrentIdentity = Depends(manage_users),
    service: EmployeeService = Depends(get_employee_service),
) -> list[UserResponse]:
    return [employee_response(user) for user in service.list(identity.user)]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    request: EmployeeCreateRequest,
    identity: CurrentIdentity = Depends(manage_users),
    service: EmployeeService = Depends(get_employee_service),
) -> UserResponse:
    try:
        return employee_response(service.create(identity.user, request))
    except EmployeeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except EmployeePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.patch("/{employee_id}", response_model=UserResponse)
def update_employee(
    employee_id: UUID,
    request: EmployeeUpdateRequest,
    identity: CurrentIdentity = Depends(manage_users),
    service: EmployeeService = Depends(get_employee_service),
) -> UserResponse:
    try:
        return employee_response(service.update(identity.user, employee_id, request))
    except EmployeeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EmployeePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc