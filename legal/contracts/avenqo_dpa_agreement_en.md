# DATA PROCESSING ADDENDUM (DPA)
**CONTRACT REFERENCE: AVENQO-DPA-2026-V1.1-EN**
**DOCUMENT STATUS: UNDER LEGAL REVIEW (UNDER_REVIEW / LEGAL_REVIEW_REQUIRED)**
*(DRAFT FOR FOUNDER AND QUEBEC BAR LEGAL COUNSEL EXAMINATION — NOT APPROVED FOR CLIENT SIGNATURE)*

---

### BETWEEN THE UNDERSIGNED PARTIES:

**1. THE PROCESSOR:**
**PMC SOLUTIONS AI** (enterprise pending incorporation in Quebec, Canada, represented by Mircea Paul Cioban, Founder), having its principal place of business in Quebec, Canada, operating the **Avenqo** technology platform (hereinafter referred to as "**PMC Solutions AI**" or the "**Processor**").
*Incorporation Notice: Upon official issuance of the certificate of incorporation by the Registraire des entreprises du Québec (REQ), all rights and obligations of the Processor hereunder shall automatically transfer to PMC Solutions AI Inc.*

**AND**

**2. THE DATA CONTROLLER:**
The client corporate entity **{{COMPANY_NAME}}**, having its business address at {{COMPANY_ADDRESS}} (Avenqo Unique Tenant Identifier: `{{COMPANY_ID}}`), represented by {{SIGNATORY_NAME}}, acting in their capacity as {{SIGNATORY_TITLE}} duly authorized (hereinafter referred to as the "**Client**" or the "**Data Controller**").

(The Processor and the Data Controller are individually referred to as a "**Party**" and collectively as the "**Parties**").

---

### SECTION 1 — PURPOSE AND PROCESSING SCOPE
This Data Processing Addendum ("DPA") governs the processing of personal information and business records performed by PMC Solutions AI on behalf of the Client in connection with the provision of Avenqo cloud services (Plan: **{{SUBSCRIPTION_PLAN}}**, Active Modules: **{{ACTIVE_MODULES}}**).

---

### SECTION 2 — APPLICABLE PRIVACY LEGISLATION
The Parties covenant to execute their respective duties in full compliance with:
1. The *Act respecting the protection of personal information in the private sector* (Quebec, CQLR c. P-39.1, as amended by **Law 25**).
2. The *Personal Information Protection and Electronic Documents Act* (Canada, **PIPEDA**).
3. Where applicable to European residents, the *General Data Protection Regulation* (EU 2016/679, **GDPR**).

---

### SECTION 3 — ROLES AND DOCUMENTED INSTRUCTIONS
3.1 **Exclusive Data Ownership**: The Client retains sole, inalienable, and complete proprietary title in and to all business records and personal data entrusted to Avenqo.
3.2 **Client Instructions**: The Processor processes personal data strictly pursuant to documented instructions from the Client, solely for the delivery, maintenance, and security of subscribed services.
3.3 **Strict Prohibition of Public AI Training**: The Processor covenants that Client personal or business data shall **NEVER** be used to train, tune, or improve public, shared, or third-party artificial intelligence models without express prior written consent.

---

### SECTION 4 — AUTHORIZED SUB-PROCESSORS AND HOSTING
4.1 **List of Approved Technical Sub-Processors**: The Client grants specific authorization for the engagement of the following essential infrastructure sub-processors:
- **Vercel Inc.** (Frontend web user interface and Edge functions hosting and deployment - United States / Global).
- **Railway Corp.** (Backend application server hosting and PostgreSQL databases - United States / Canada).
- **Cloudflare Inc.** (Content Delivery Network CDN, DNS, Edge encryption, and DDoS protection - Global / Canada).
- **Stripe Payments Canada / Stripe Inc.** (Billing gateway and payment transaction processing - Canada / United States).
- **Resend Inc.** (Transactional email delivery infrastructure and alerts - United States).
- **Anthropic PBC / OpenAI LLC / Google LLC** (Artificial intelligence foundation model providers for Central AI advanced reasoning - United States, under non-training data privacy agreements).
- **Telnyx LLC** (Cloud telecommunications and SIP carrier network provider for Voice AI module - United States / Canada).
- **Retell AI (Retell Inc.)** (Conversational voice orchestration engine and real-time audio processing - United States).
4.2 **Cross-Border Transfers (Law 25)**: The Client acknowledges that certain sub-processors maintain facilities in the United States or abroad. The Processor ensures that such transfers are governed by contractual safeguards providing data protection equivalent to Quebec and Canadian statutory requirements.

---

### SECTION 5 — INFORMATION SECURITY AND BACKUPS
The Processor maintains robust administrative, technical, and physical safeguards:
- **Encryption at Rest**: AES-256 hardware encryption enforced on all databases, storage volumes, and document repositories.
- **Encryption in Transit**: Mandatory TLS 1.3 protocol across all public web endpoints and API communications.
- **Strict Multi-Tenant Isolation**: Rigorous logical partitioning per tenant identifier (`company_id`) via PostgreSQL Row-Level Security (RLS).
- **Automated Backups**: Daily automated encrypted backups stored in segregated environments.

---

### SECTION 6 — PRIVACY INCIDENT MANAGEMENT AND NOTIFICATION (LAW 25)
6.1 **Notification Window (48 Hours)**: In the event of a verified security incident involving a risk of serious injury to individuals, the Processor covenants to notify the Client in writing within a maximum of **forty-eight (48) hours** of confirmation.
6.2 **Immediate Remediation**: The Processor shall take all reasonable immediate steps to contain the breach, mitigate potential harm, and restore system integrity.
6.3 **Regulatory Cooperation**: The Processor shall actively assist the Client in fulfilling statutory breach notification duties toward the Commission d'accès à l'information du Québec (CAI), the Office of the Privacy Commissioner of Canada (OPC), or affected individuals.

---

### SECTION 7 — RETENTION, RETURN, AND IRREVOCABLE DELETION
7.1 **Operational Retention**: Personal data is retained solely during the term of the Client's active subscription.
7.2 **Reversibility Window**: Upon subscription termination, the Client enjoys a thirty (30) day retrieval window to export its records in standard structured formats (CSV/JSON).
7.3 **Irrevocable Deletion and Backup Purge**: Following the 30-day retrieval window, the Processor permanently and irreversibly purges production data within sixty (60) days. Encrypted automated security backups operate on a rolling retention cycle with automatic overwriting and definitive purge completed within a maximum of thirty (30) days following production deletion. Accounting ledgers and invoices are retained pursuant to mandatory Canadian seven (7) year statutory tax requirements.

---

### SECTION 8 — LIABILITY ALLOCATION AND CONTACT
The Processor's aggregate liability under this DPA is subject to the limitations set forth in Section 8 of the Master Subscription Agreement (MSA), subject to Article 1474 of the Civil Code of Quebec.  
Designated Privacy Officer: Mircea Paul Cioban (privacy@avenqo.ca).

---

### LINGUISTIC COMPLIANCE (QUEBEC)
Pursuant to the *Charter of the French Language* (Law 96), the Parties acknowledge that the French version of this Addendum was examined prior to any translated version.

---

**FOR THE CLIENT (DATA CONTROLLER):**  
Company: {{COMPANY_NAME}}  
Authorized Signatory: {{SIGNATORY_NAME}}  
Title: {{SIGNATORY_TITLE}}  
Date: {{EFFECTIVE_DATE}}  
Signature: {{SIGNATURE_BLOCK_CLIENT}}

**FOR PMC SOLUTIONS AI (PROCESSOR):**  
Entity: PMC SOLUTIONS AI (enterprise pending incorporation in Quebec, Canada)  
Representative: Mircea Paul Cioban  
Title: Founder  
Date: {{EFFECTIVE_DATE}}  
Authorized Countersignature:  
`[Pending authorized countersignature by PMC Solutions AI]`
