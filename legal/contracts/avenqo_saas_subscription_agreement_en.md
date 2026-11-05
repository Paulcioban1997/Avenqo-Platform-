# AVENQO SAAS SUBSCRIPTION AGREEMENT (MSA)
**CONTRACT REFERENCE: AVENQO-SAAS-2026-V1.1-EN**
**DOCUMENT STATUS: UNDER LEGAL REVIEW (UNDER_REVIEW / LEGAL_REVIEW_REQUIRED)**
*(DRAFT FOR FOUNDER AND QUEBEC BAR LEGAL COUNSEL EXAMINATION — NOT APPROVED FOR CLIENT SIGNATURE)*

---

### BETWEEN THE UNDERSIGNED PARTIES:

**1. THE PROVIDER:**
**PMC SOLUTIONS AI** (enterprise pending incorporation in Quebec, Canada, represented by Mircea Paul Cioban, Founder), having its principal place of business in Quebec, Canada, operating the **Avenqo** technology platform (hereinafter referred to as "**PMC Solutions AI**" or the "**Provider**").
*Incorporation Notice: Upon official issuance of the certificate of incorporation by the Registraire des entreprises du Québec (REQ), all rights and obligations of PMC Solutions AI hereunder shall automatically novate and transfer to the corporate entity PMC Solutions AI Inc. without disruption of contractual continuity.*

**AND**

**2. THE CLIENT:**
The client corporate entity **{{COMPANY_NAME}}**, having its business address at {{COMPANY_ADDRESS}} (Avenqo Unique Tenant Identifier: `{{COMPANY_ID}}`), represented by {{SIGNATORY_NAME}}, acting in their capacity as {{SIGNATORY_TITLE}} duly authorized to legally bind their organization (hereinafter referred to as the "**Client**").

(The Provider and the Client are individually referred to as a "**Party**" and collectively as the "**Parties**").

---

### PREAMBLE
The Provider has created, designed, and operates the integrated cloud software platform known as **Avenqo** (the "**Platform**"), offering modular business intelligence, retail data connectors, customer relationship management (CRM), and workflow automation tools (Central AI).
The Client wishes to subscribe to a Software-as-a-Service (SaaS) access to the Platform for its internal commercial purposes, subject to the terms, conditions, and limitations set forth herein.

---

### SECTION 1 — DEFINITIONS
- **SaaS Platform**: The multi-tenant software environment of Avenqo remotely accessible over secure network protocols.
- **Client Data**: All electronic data, records, catalogs, files, transactions, customer dossiers, and metadata uploaded or synchronized by the Client into its dedicated tenant environment.
- **Business Modules**: Specialized software functional packages subscribed and activated by the Client within the strict entitlement boundaries of its selected subscription plan: **{{ACTIVE_MODULES}}**.
- **AI Credits**: Computational calculation units allocated monthly under the applicable subscription tier or purchased as add-on packs, deducted upon inference execution and automated data processing.

---

### SECTION 2 — SERVICE SCOPE, SUBSCRIPTION TIERS, AND ACCESS GRANT
2.1 **Grant of Access**: The Provider grants to the Client, which accepts, a non-exclusive, non-transferable, non-sublicensable, worldwide (subject to applicable export control laws) right to access and use the Platform and subscribed modules.
2.2 **Commercial Subscription Tier Specifications**:
- **Base Plan**: Includes core platform access, **two (2) selectable business modules**, and a monthly quota of **6,500 AI credits**.
- **Professional Plan**: Includes core platform access, **five (5) selectable business modules** from the active catalog, and a monthly quota of **20,000 AI credits**. The Professional plan does not grant unlimited access to all platform modules.
- **Enterprise Plan**: Custom quote configuration with tailored module allocations and quota caps, governed by an executed enterprise addendum.
2.3 **Multi-Tenant Architecture and Isolation**: Services operate within a shared cloud infrastructure featuring strict database-level data partitioning enforced by PostgreSQL Row-Level Security (RLS).
2.4 **No Transfer of Intellectual Property**: This Agreement conveys an operational SaaS access right only and does not constitute a sale, assignment, or transfer of source code, algorithms, or patentable assets.

---

### SECTION 3 — PRICING, INVOICING, AND TAX TERMS
3.1 **Subscription Fee**: The Client subscribes to the service under the periodic agreed fee of: **{{SUBSCRIPTION_PRICE}}**.
3.2 **Tax Terms and Statutory Collection**: Fees are stated exclusive of taxes. Applicable sales taxes (including Canadian GST and Quebec QST, or applicable statutory taxes in the Client's jurisdiction) shall be charged and collected in accordance with applicable tax statutes and PMC Solutions AI's official tax registration status at the time of invoicing.
3.3 **Automatic Renewal**: {{RENEWAL_TERMS}}.
3.4 **AI Credit Quotas and Fail-Closed Safeguard**: Monthly credits renew at cycle start without cumulative rollover. Add-on packs remain active as long as the subscription is maintained. If credit balances reach zero, automated artificial intelligence inferences suspend (*fail-closed*) until recharged or refreshed, avoiding unanticipated overage charges.

---

### SECTION 4 — SERVICE AVAILABILITY (SLA) AND SUPPORT
4.1 **Sustainable Availability Commitment**: The Provider shall deploy commercially reasonable efforts to achieve a monthly target availability of **99.0%** for the production Platform.
4.2 **Calculation Methodology and SLA Exclusions**: Availability is calculated monthly as follows: `[(Total Monthly Minutes - Non-Excluded Downtime Minutes) / Total Monthly Minutes] x 100`. The following circumstances are strictly excluded from downtime calculations:
- Scheduled maintenance windows announced with at least 48 hours advance notice.
- Outages or degradations originating from third-party hosting, infrastructure, or network transit providers (e.g., Cloudflare, Railway, AWS).
- Failures of integrated partner third-party APIs (e.g., Stripe, banking gateways, Google Workspace, Telnyx, external LLM providers).
- Client acts, omissions, misconfigurations, or events of force majeure.
4.3 **Sole and Exclusive Remedy (Service Credits)**: If verified monthly availability falls below 99.0%, the Client may request, within fifteen (15) days following the affected month, a service credit applied to its next monthly invoice:
- Availability between 95.0% and 98.9%: 10% credit of the monthly base subscription fee.
- Availability below 95.0%: 20% credit of the monthly base subscription fee.
Service credits constitute the Client's sole and exclusive remedy for any availability shortfall. No cash refunds or separate indemnity shall be payable.

---

### SECTION 5 — NATURE OF AI TOOLS AND DISCLAIMER OF OUTCOME GUARANTEE
5.1 **Decision Support Function**: Syntheses, projections, classifications, and recommendations generated by Avenqo AI modules are indicative decision-support tools. PMC Solutions AI does not warrant that inferences are exhaustive, error-free, or universally applicable to unpredictable business environments.
5.2 **Client Operational Responsibility**: The Client maintains exclusive accountability for supervising, reviewing, and validating the implementation of AI-generated recommendations in its business operations.

---

### SECTION 6 — CLIENT RESPONSIBILITIES
6.1 **Lawful and Compliant Use**: The Client covenants to use the Platform in strict compliance with applicable laws of Quebec and Canada, specifically including privacy regulations (Quebec Law 25, PIPEDA).
6.2 **Access Security**: The Client is solely responsible for preserving the confidentiality and integrity of credentials, tokens, and access rights assigned to its authorized users.
6.3 **Legality of Ingested Records**: The Client warrants that it owns or possesses all required statutory consents and legal authorizations to upload, process, and synchronize Client Data on Avenqo.

---

### SECTION 7 — TERMINATION AND REVERSIBILITY
7.1 **Termination for Convenience**: The Client may terminate its subscription at any time through the self-service billing portal. Termination becomes effective at the end of the active monthly billing cycle, without retroactive pro-rata refund.
7.2 **Termination for Cause**: Either Party may terminate this Agreement immediately upon written notice if the other Party materially breaches any term and fails to cure such breach within thirty (30) days of formal written notification.
7.3 **Data Reversibility**: For thirty (30) days following the termination effective date, the Client may retrieve its complete data in standard machine-readable formats (JSON/CSV). Following this 30-day window, the Provider permanently and securely deletes all Client production data, subject only to mandatory seven (7) year statutory tax archiving requirements.

---

### SECTION 8 — LIMITATION OF LIABILITY AND CIVIL CODE OF QUEBEC
8.1 **Financial Liability Cap**: Subject expressly to Section 8.3 below, the aggregate cumulative liability of PMC Solutions AI for all claims arising out of or related to this Agreement is strictly capped at the total subscription fees actually paid by the Client to PMC Solutions AI during the three (3) months immediately preceding the event giving rise to liability (or $500 CAD, whichever is greater).
8.2 **Exclusion of Consequential Damages**: To the maximum extent permitted by applicable law, neither Party shall be liable for indirect, incidental, special, punitive, or consequential damages, or loss of profits, revenue, business opportunity, or data.
8.3 **Mandatory Provisions of Article 1474 of the Civil Code of Quebec**: Nothing in this Agreement shall operate to limit or exclude the liability of either Party for gross negligence (*faute lourde*), intentional fault (*faute intentionnelle*), or bodily or moral injury, pursuant to public order provisions of Article 1474 of the Civil Code of Quebec.

---

### SECTION 9 — LINGUISTIC COMPLIANCE (QUEBEC)
Pursuant to the *Charter of the French Language* (CQLR c. C-11, as amended by Law 96), the Parties confirm that the French version of this Agreement was provided and made available to the Client prior to the examination or signature of any translated version.

---

### SECTION 10 — GOVERNING LAW AND JURISDICTION
This Agreement is governed by and construed in accordance with the laws of the Province of Quebec and the federal laws of Canada applicable therein. Any dispute regarding its validity, interpretation, or enforcement shall be submitted exclusively to the competent courts sitting in the judicial district of Montreal, Province of Quebec, Canada.

---

### EXECUTION AND SIGNATURE MODALITIES

#### ELECTRONIC SIGNATURE (CQLR c. C-1.1)
Secured by real-time SHA-256 hash digest, immutable UTC timestamp, and permanent inclusion in the Avenqo audit registry.

#### MANUSCRIPT WET-INK SIGNATURE
Printable, physically executable, and uploadable under `/settings/contracts` for administrative integrity validation (`PENDING_VERIFICATION`).

---

**FOR THE CLIENT:**  
Company Legal Name: {{COMPANY_NAME}}  
Authorized Signatory Name: {{SIGNATORY_NAME}}  
Title / Role: {{SIGNATORY_TITLE}}  
Effective Date: {{EFFECTIVE_DATE}}  
Client Signature: {{SIGNATURE_BLOCK_CLIENT}}

**FOR PMC SOLUTIONS AI:**  
Entity: PMC SOLUTIONS AI (enterprise pending incorporation in Quebec, Canada)  
Representative: Mircea Paul Cioban  
Title: Founder  
Date: {{EFFECTIVE_DATE}}  
Authorized Countersignature:  
`[Pending authorized countersignature by PMC Solutions AI]`
