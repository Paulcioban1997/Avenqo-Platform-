"""Composition des services métier RetailSense."""

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.repositories.module_entitlements import SQLAlchemyModuleEntitlements
from backend.app.repositories.retail_business_context import SQLAlchemyRetailBusinessContext
from modules.entitlements import ModuleAccessService
from modules.retailsense.assistant import RetailAssistantService


def get_retail_assistant(db: Session = Depends(get_db)) -> RetailAssistantService:
    return RetailAssistantService(
        access=ModuleAccessService(SQLAlchemyModuleEntitlements(db)),
        context=SQLAlchemyRetailBusinessContext(db),
    )