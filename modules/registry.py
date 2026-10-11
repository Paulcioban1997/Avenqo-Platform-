"""Central registry of optional Avenqo business modules."""

from dataclasses import dataclass
from enum import StrEnum


RETAIL_MODULE_CODE = "retail"


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
    BusinessModuleDefinition("crm", "CRM AI", "Customer relationship intelligence and actions.", ModuleAvailability.AVAILABLE, "customer"),
    BusinessModuleDefinition("marketing", "Marketing AI", "Campaign copy generated from your authorized business context.", ModuleAvailability.AVAILABLE, "growth"),
    BusinessModuleDefinition("appointments", "Appointments AI", "Standalone booking product. Scheduling is available today inside CRM AI.", ModuleAvailability.COMING_SOON, "operations"),
    BusinessModuleDefinition("accounting", "Accounting AI", "Accounting workflow intelligence.", ModuleAvailability.AVAILABLE, "finance"),
    BusinessModuleDefinition("ocr", "OCR / Documents AI", "Secure upload, text extraction, classification and export.", ModuleAvailability.AVAILABLE, "documents"),
    BusinessModuleDefinition("hr", "HR AI", "Workforce intelligence beyond employee management.", ModuleAvailability.COMING_SOON, "people"),
    BusinessModuleDefinition("voice", "Voice AI", "Voice interaction automation.", ModuleAvailability.AVAILABLE, "communication", premium=True, credit_multiplier=2.0),
    BusinessModuleDefinition("media", "Media AI", "Authorized text generation with credit tracking and history.", ModuleAvailability.AVAILABLE, "content", premium=True, credit_multiplier=2.0),
    BusinessModuleDefinition("legal", "Legal AI", "Document analysis with explicit non-advice limits.", ModuleAvailability.AVAILABLE, "legal"),
    BusinessModuleDefinition("workflow", "Workflow Automation", "Tenant-scoped triggers, conditions and actions.", ModuleAvailability.AVAILABLE, "operations"),
    BusinessModuleDefinition("ai_agents", "AI Agents", "Catalog of implemented assistants with execution history.", ModuleAvailability.AVAILABLE, "automation", premium=True, credit_multiplier=2.0),
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