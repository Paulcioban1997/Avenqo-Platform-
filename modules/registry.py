"""Central registry of optional Avenqo business modules."""

from dataclasses import dataclass
from enum import StrEnum


class ModuleAvailability(StrEnum):
    AVAILABLE = "available"
    COMING_SOON = "coming_soon"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class BusinessModuleDefinition:
    key: str
    display_name: str
    description: str
    availability: ModuleAvailability
    category: str
    premium: bool = False
    credit_multiplier: float = 1.0

    @property
    def is_available(self) -> bool:
        return self.availability == ModuleAvailability.AVAILABLE


BUSINESS_MODULE_REGISTRY: tuple[BusinessModuleDefinition, ...] = (
    BusinessModuleDefinition("retail", "Retail Intelligence", "Retail sales, products and customer intelligence.", ModuleAvailability.AVAILABLE, "commerce"),
    BusinessModuleDefinition("crm", "CRM AI", "Customer relationship intelligence and actions.", ModuleAvailability.COMING_SOON, "customer"),
    BusinessModuleDefinition("marketing", "Marketing AI", "Campaign and audience intelligence.", ModuleAvailability.COMING_SOON, "growth"),
    BusinessModuleDefinition("appointments", "Appointments AI", "Booking and scheduling intelligence.", ModuleAvailability.COMING_SOON, "operations"),
    BusinessModuleDefinition("accounting", "Accounting AI", "Accounting workflow intelligence.", ModuleAvailability.COMING_SOON, "finance"),
    BusinessModuleDefinition("ocr", "OCR / Documents AI", "Structured extraction from business documents.", ModuleAvailability.COMING_SOON, "documents"),
    BusinessModuleDefinition("hr", "HR AI", "Workforce and people operations intelligence.", ModuleAvailability.COMING_SOON, "people"),
    BusinessModuleDefinition("voice", "Voice AI", "Voice interaction automation.", ModuleAvailability.COMING_SOON, "communication", premium=True, credit_multiplier=2.0),
    BusinessModuleDefinition("media", "Media AI", "Business media generation and organization.", ModuleAvailability.COMING_SOON, "content", premium=True, credit_multiplier=2.0),
    BusinessModuleDefinition("legal", "Legal AI", "Contract and legal document intelligence.", ModuleAvailability.COMING_SOON, "legal"),
    BusinessModuleDefinition("workflow", "Workflow Automation", "Cross-system workflow automation.", ModuleAvailability.COMING_SOON, "operations"),
    BusinessModuleDefinition("ai_agents", "AI Agents", "Advanced custom business agents.", ModuleAvailability.COMING_SOON, "automation", premium=True, credit_multiplier=2.0),
)

BUSINESS_MODULES_BY_KEY = {module.key: module for module in BUSINESS_MODULE_REGISTRY}


def get_business_module(key: str) -> BusinessModuleDefinition | None:
    return BUSINESS_MODULES_BY_KEY.get(key)


__all__ = [
    "BUSINESS_MODULE_REGISTRY",
    "BUSINESS_MODULES_BY_KEY",
    "BusinessModuleDefinition",
    "ModuleAvailability",
    "get_business_module",
]