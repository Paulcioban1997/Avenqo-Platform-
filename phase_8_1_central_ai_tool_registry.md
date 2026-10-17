# AVENQO — PHASE 8.1
## CENTRAL AI TOOL REGISTRY SPECIFICATION & CAPABILITY CATALOG

**Date:** October 17, 2026  
**Module:** Avenqo Central AI & Assistant Dispatch  
**Registry Architecture:** `ToolRegistry` + `AssistantRegistry` (`backend/app/ai/tools/`)  
**Status:** **SANDBOX READY (50 Registered Enterprise Tools)**

---

### 1. ARCHITECTURAL PRINCIPLES

1. **Explicit Ownership:** Every tool declares its owning agent(s) via `agent_ids = frozenset({...})`.
2. **Strict Mutability Contracts:**
   - Read-only tools must declare `read_only = True` and `mutates = False`.
   - Mutating tools must declare `read_only = False`, `mutates = True`, specify non-empty `mutation_capabilities`, and enforce `confirmation_policy = "explicit_user_confirmation"`.
3. **Tenant & Plan Entitlements:**
   - Tools are never exposed indiscriminately to all users.
   - `ToolRegistry.available_for()` enforces tenant capability flags, minimum subscription plans, and user permissions (`ai:use`, `data:read`, `crm:appointments:write`, `workflow:manage`).
4. **Zero Hallucination / Zero Fabrication:**
   - Tools return typed data structures originating exclusively from PostgreSQL RLS-filtered tables.

---

### 2. COMPREHENSIVE TOOL REGISTRY CATALOG

#### A. Retail AI Tools
- **`get_sales_summary`**
  - *Owning Agents:* `retail`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Computes real revenue, order volumes, average basket size, and refunds across specified date ranges.
- **`get_customer_segments`**
  - *Owning Agents:* `retail`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Retrieves RFM customer segments (`Champions`, `Fidèles`, `À risque`, `Inactifs`) with counts, average spend, and recency metrics.
- **`get_demand_forecast`**
  - *Owning Agents:* `retail`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Produces predictive sales forecasts over 7, 30, or 90 days using verified regression models.

#### B. CRM AI Tools
- **`check_availability`**
  - *Owning Agents:* `crm`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Verifies business operating hours, existing appointment conflicts, and practitioner availability.
- **`list_available_slots`**
  - *Owning Agents:* `crm`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Returns available time windows on a given date formatted in company timezone.
- **`search_appointments`**
  - *Owning Agents:* `crm`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Searches active, confirmed, or completed bookings by client name, keyword, or date.
- **`create_appointment`**
  - *Owning Agents:* `crm`, `cross_agent`
  - *Contract:* `read_only=False`, `mutates=True`, `mutation_capabilities={"crm.appointment.write", "appointment.create", "calendar.write"}`
  - *Description:* Resolves or creates tenant client, verifies slot conflict, reserves appointment, and triggers calendar synchronization. Requires explicit user confirmation.
- **`cancel_appointment`**
  - *Owning Agents:* `crm`, `cross_agent`
  - *Contract:* `read_only=False`, `mutates=True`, `mutation_capabilities={"crm.appointment.write", "appointment.cancel", "calendar.write"}`
  - *Description:* Updates appointment status to `cancelled` and removes associated external calendar event. Requires explicit user confirmation.

#### C. Accounting AI Tools
- **`get_financial_overview`**
  - *Owning Agents:* `accounting`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Retrieves cash balance, accounts receivable, accounts payable, and net margin from verified invoices and ledger transactions.
- **`reconcile_sales_and_accounting`**
  - *Owning Agents:* `accounting`, `retail`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Compares commerce normalized orders against confirmed accounting invoices/transactions. Computes exact variance without fabricating balance reconciliations.

#### D. Marketing AI Tools
- **`draft_marketing_campaign`**
  - *Owning Agents:* `marketing`, `cross_agent`
  - *Contract:* `read_only=False`, `mutates=True`, `mutation_capabilities={"campaign.create", "marketing.campaign.write"}`
  - *Description:* When `confirmed=False`, synthesizes target segment data into a proposal and requests explicit user confirmation. When `confirmed=True`, persists `MediaGeneration` record and deducts 1 AI credit.

#### E. Document & OCR AI Tools
- **`get_ocr_document`**
  - *Owning Agents:* `ocr`, `accounting`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Retrieves parsed text, line items, supplier details, and confidence scores from uploaded OCR documents.
- **`propose_accounting_from_ocr`**
  - *Owning Agents:* `ocr`, `accounting`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Generates an unconfirmed `AccountingInvoice` draft (`is_confirmed=False`) with human validation mandated before general ledger commitment.

#### F. Legal AI Tools
- **`analyze_legal_document`**
  - *Owning Agents:* `legal`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Performs contract risk assessment, clause summarization, and obligation extraction with mandatory non-advice disclaimer.

#### G. Enterprise Memory Tools
- **`save_enterprise_memory`**
  - *Owning Agents:* `memory`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Persists strategic facts, team instructions, or user preferences in Mem0 / PostgreSQL with strict tenant boundary tagging.
- **`search_enterprise_memory`**
  - *Owning Agents:* `memory`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Semantic and keyword recall across past conversations restricted to authenticated company scope.

#### H. Automation & Workflow Tools
- **`draft_automation_workflow`**
  - *Owning Agents:* `workflow`, `cross_agent`
  - *Contract:* `read_only=False`, `mutates=True`, `mutation_capabilities={"workflow.create", "automation.write"}`
  - *Description:* Configures event trigger and target action. Requires explicit confirmation before persisting and activating.
- **`execute_automation_workflow`**
  - *Owning Agents:* `workflow`, `cross_agent`
  - *Contract:* `read_only=False`, `mutates=True`, `mutation_capabilities={"workflow.execute", "automation.write"}`
  - *Description:* Manually or contextually executes active workflows with idempotent key deduplication.

#### I. Platform, Marketplace & Billing Tools
- **`get_commerce_connections_status`**
  - *Owning Agents:* `marketplace`, `retail`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Reports real-time status (`READY`, `DISCONNECTED`, `SYNCING`) and sync timestamps of active commerce channels.
- **`get_ai_credits_balance`**
  - *Owning Agents:* `billing`, `cross_agent`
  - *Contract:* `read_only=True`, `mutates=False`
  - *Description:* Returns tenant monthly included credits, used credits, purchased credits, and overall balance.

---

### 3. ASSISTANT DISPATCH REGISTRY

The `AssistantRegistry` enables Central AI to route intents naturally:

| Assistant Slug | Primary Category | Intent Keywords | Dispatched Tools Sample |
| :--- | :--- | :--- | :--- |
| **`cross_agent`** | Intelligence | all, global, general, central | Orchestrates all registered tools with user confirmation |
| **`retail`** | Commerce | ventes, stock, panier, prévision | `get_sales_summary`, `get_customer_segments`, `get_demand_forecast` |
| **`crm`** | Growth / Ops | rdv, rendez-vous, disponibilité, client | `check_availability`, `create_appointment`, `cancel_appointment` |
| **`accounting`** | Finance | compta, facture, tva, trésorerie, écart | `get_financial_overview`, `reconcile_sales_and_accounting` |
| **`marketing`** | Growth | campagne, promo, segmentation, email | `draft_marketing_campaign` |
| **`ocr`** | Documents | scanner, facture fournisseur, ticket | `get_ocr_document`, `propose_accounting_from_ocr` |
| **`legal`** | Legal | contrat, clause, conformité, loi 25 | `analyze_legal_document` |
| **`workflow`** | Operations | automatisation, déclencheur, workflow | `draft_automation_workflow`, `execute_automation_workflow` |
| **`memory`** | Platform | souvenir, préférence, consigne, rappel | `save_enterprise_memory`, `search_enterprise_memory` |
