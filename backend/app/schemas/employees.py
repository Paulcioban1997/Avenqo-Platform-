"""SchÃ©mas HTTP de gestion des employÃ©s d'une entreprise Avenqo."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from backend.app.models import UserRole
from backend.app.schemas.auth import RegisterRequest


class EmployeeCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: UserRole = UserRole.USER

    _validate_password = field_validator("password")(
        RegisterRequest.validate_password.__func__
    )


class EmployeeUpdateRequest(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "EmployeeUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("Au moins une modification est requise")
        return self


class EmployeePath(BaseModel):
    employee_id: UUID
