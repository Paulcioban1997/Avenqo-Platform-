"""Injection du service de devis Enterprise."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.services.enterprise_quote_service import EnterpriseQuoteService
from backend.app.services.resend_client import ResendQuoteMailer


def get_quote_mailer(settings: Settings = Depends(get_settings)):
    if settings.transactional_email_api_key:
        return ResendQuoteMailer(settings)
    return None


def get_enterprise_quote_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    mailer=Depends(get_quote_mailer),
) -> EnterpriseQuoteService:
    return EnterpriseQuoteService(db, settings, mailer)
