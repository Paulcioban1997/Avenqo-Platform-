# DATA PROCESSING ADDENDUM (DPA)
**CONTRACT REFERENCE: AVENQO-DPA-2026-V1**
*(COMPLIANT WITH QUEBEC LAW 25 AND CANADIAN PIPEDA)*

---

### BETWEEN THE UNDERSIGNED:

**1. THE PROVIDER (PROCESSOR):**
**PMC SOLUTIONS AI** (business entity in the process of incorporation in Quebec, Canada), operating the **Avenqo** AI technology platform, represented by its authorized founders (with formal contractual update upon registration with the Registraire des entreprises du Québec) (hereinafter referred to as "**PMC Solutions AI**" or the "**Processor**").

**AND**

**2. THE CLIENT (DATA CONTROLLER):**
The client business **{{COMPANY_NAME}}**, identified by its unique tenant identifier `{{COMPANY_ID}}`, represented by **{{SIGNATORY_NAME}}**, acting in their capacity as **{{SIGNATORY_TITLE}}** (hereinafter referred to as the "**Client**" or the "**Data Controller**").

---

### 1. PURPOSE AND SCOPE
This Data Processing Addendum ("DPA") governs the processing of personal data and business records performed by PMC Solutions AI on behalf of the Client in connection with the Avenqo cloud platform (Plan: **{{SUBSCRIPTION_PLAN}}**, Active Modules: **{{ACTIVE_MODULES}}**).

### 2. PRIVACY LAW COMPLIANCE
The Parties undertake to comply with all applicable privacy legislation, notably:
- The *Act respecting the protection of personal information in the private sector* (Quebec, CQLR c. P-39.1, amended by **Law 25**).
- The *Personal Information Protection and Electronic Documents Act* (Canada, **PIPEDA**).
- Where applicable, the *General Data Protection Regulation* (EU 2016/679, **GDPR**).

### 3. DATA OWNERSHIP AND PROCESSING INSTRUCTIONS
1. **Exclusive Ownership:** The Client retains full, exclusive, and unalienable ownership of all personal and enterprise data processed through Avenqo.
2. **Documented Instructions:** The Processor processes personal data solely in accordance with documented instructions from the Client and strictly for delivering the subscribed services.
3. **No Public AI Model Training:** The Processor strictly warrants that Client personal and business data is **NEVER** used to train public or cross-tenant foundation models.

### 4. SECURITY STANDARDS AND ENCRYPTION
The Processor implements enterprise-grade technical and organizational safeguards:
- **Encryption at rest:** AES-256 hardware encryption on all databases, storage volumes, and document archives.
- **Encryption in transit:** Mandatory TLS 1.3 protocol for all API requests and webhook transfers.
- **Strict Multi-Tenant Isolation:** Complete logical and physical database boundary enforced by `company_id`.

### 5. PRIVACY INCIDENT NOTIFICATION (LAW 25)
In the event of a security incident presenting a risk of serious injury to individuals, the Processor agrees to:
1. Notify the Client in writing without undue delay (within a maximum of **48 hours**).
2. Promptly implement all reasonable measures to mitigate risk and limit the scope of the incident.
3. Fully cooperate with the Client in meeting statutory reporting duties to the Commission d'accès à l'information du Québec (CAI) or the Office of the Privacy Commissioner of Canada.

### 6. DATA DELETION AND RETURN
Upon termination or expiration of the Client's subscription, the Processor undertakes, at the Client's election, to:
1. Enable full data export in standard machine-readable formats (CSV, JSON, PDF).
2. Securely and irrevocably purge all production copies of Client data, subject only to mandatory legal tax retention duties (7 years in Canada).

---

### EFFECTIVE DATE AND VERSION
- **Effective Date:** {{EFFECTIVE_DATE}}
- **Contract Version:** {{CONTRACT_VERSION}}
- **Legal Notice:** DRAFT CONTRACTUAL TEMPLATE SUBJECT TO LEGAL COUNSEL VALIDATION PRIOR TO COMMERCIAL USE

---

**FOR THE CLIENT (DATA CONTROLLER):**  
Company: {{COMPANY_NAME}}  
Authorized Signatory: {{SIGNATORY_NAME}}  
Title: {{SIGNATORY_TITLE}}  
Date: {{EFFECTIVE_DATE}}  

**FOR PMC SOLUTIONS AI (PROCESSOR):**  
Authorized Representative: Mircea Paul Cioban  
Title: Founder, PMC Solutions AI  
Date: {{EFFECTIVE_DATE}}  

