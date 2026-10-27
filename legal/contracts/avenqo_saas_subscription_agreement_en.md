# AVENQO SAAS SUBSCRIPTION AGREEMENT
**CONTRACT REFERENCE: AVENQO-SAAS-2026-V1-EN**
*(DRAFT SUBJECT TO LEGAL REVIEW BY A QUEBEC ATTORNEY — PRE-COMMERCIAL USAGE)*

---

### BETWEEN THE UNDERSIGNED PARTIES:

**1. THE PROVIDER:**
**PMC SOLUTIONS AI INC.**, a legal person duly incorporated under the laws of the Province of Quebec, having its head office in Quebec, Canada, represented by its duly authorized officers (hereinafter referred to as "**PMC Solutions AI**" or the "**Provider**").

**AND**

**2. THE CLIENT:**
The business entity, corporation, or sole proprietorship identified during digital registration by its legal corporate name, business address, authorized representative, and unique Avenqo account identifier (hereinafter referred to as the "**Client**").

(The Provider and the Client are hereinafter individually referred to as a "**Party**" and collectively as the "**Parties**").

---

### PREAMBLE
The Provider has designed, developed, and operates the integrated cloud platform named **Avenqo** (the "**Platform**"), offering modular business intelligence, retail data connector integrations, customer relationship management (CRM), and automated decision support (Central AI).
The Client wishes to subscribe to a Software-as-a-Service (SaaS) access to the Platform for its internal business purposes, pursuant to the terms and conditions set forth herein.

---

### SECTION 1 — DEFINITIONS
- **SaaS Platform**: The multi-tenant software environment of Avenqo remotely accessible over secure network connections.
- **Client Data**: All electronic data, files, customer records, transactions, and metadata uploaded or synchronized by the Client to its dedicated tenant environment.
- **Business Modules**: The functional modules subscribed by the Client (including Retail AI, CRM AI, Voice AI, Copilot, Accounting/Invoicing).
- **AI Credits**: Numeric computational units allocated monthly according to the selected subscription plan or purchased as credit packs, deducted upon inference and algorithmic execution.

---

### SECTION 2 — SERVICE SCOPE AND GRANT OF ACCESS
2.1 **Access Grant**: The Provider grants to the Client, which accepts, a non-exclusive, non-transferable, revocable (upon termination), and worldwide (subject to applicable export laws) right to access and use the Platform and subscribed modules.
2.2 **Multi-Tenant Architecture & Isolation**: Services are provided in a multi-tenant infrastructure with cryptographic and database-level tenant isolation enforced via PostgreSQL Row-Level Security (RLS).
2.3 **No Code Transfer**: This Agreement confers a SaaS usage right only and does not constitute a sale, assignment, or transfer of source code or underlying intellectual property rights.

---

### SECTION 3 — PRICING, INVOICING, AND AI CREDITS
3.1 **Canonical Reference Pricing**: Official reference pricing is established in Canadian Dollars (CAD):
- **Base Plan**: $29.99 CAD / month (including 6,500 monthly AI credits and 2 selectable business modules).
- **Professional Plan**: $49.99 CAD / month (including 20,000 monthly AI credits and all business modules).
- **Enterprise Plan**: Custom quote and tailored capacity quotas governed by an enterprise addendum.
3.2 **Applicable Taxes**: All fees are exclusive of taxes. Canadian federal and provincial sales taxes (GST/QST) or other applicable jurisdictions' sales taxes shall be collected in accordance with current statutory requirements.
3.3 **Automatic Renewal**: Subscriptions are entered into for an initial term of one (1) month and renew automatically for successive one-month periods unless terminated prior to the conclusion of the active billing cycle.
3.4 **Credit Depletion & Quotas**: Monthly credits are allocated at cycle renewal. Purchased credit packs do not expire during an active subscription. If available credits reach zero, AI inference operations fail closed until recharged.

---

### SECTION 4 — PROVIDER OBLIGATIONS & SECURITY
4.1 **Uptime Target**: The Provider shall exercise commercially reasonable efforts to maintain a target service availability of 99.5%, excluding scheduled maintenance windows.
4.2 **Encryption and Backup Standards**: The Provider implements industry-standard security safeguards, including TLS 1.3 encryption in transit and AES-256 encryption at rest, along with isolated automated daily backups.
4.3 **Data Privacy & AI Training Restriction**: The Provider strictly agrees never to use Client Data to train public, generalized, or cross-tenant foundation machine learning models without express prior written consent.

---

### SECTION 5 — CLIENT RESPONSIBILITIES
5.1 **Lawful Use**: The Client covenants to use the Platform in compliance with all applicable Canadian and Quebec laws, specifically including the Quebec *Act respecting the protection of personal information in the private sector* (Law 25) and PIPEDA.
5.2 **Credential Security**: The Client maintains exclusive responsibility for safeguarding its administrative access tokens, passwords, and multi-factor authentication devices.
5.3 **Ownership of Ingested Records**: The Client warrants that it possesses all necessary rights, licenses, and customer consents to process and upload Client Data to the Platform.

---

### SECTION 6 — INTELLECTUAL PROPERTY
6.1 **Platform Ownership**: PMC Solutions AI Inc. retains exclusive ownership of all copyrights, patents, trade secrets, trademarks, visual designs, backend architectures, and software algorithms embodying Avenqo.
6.2 **Client Data Ownership**: The Client remains the sole and exclusive owner of all Client Data, transactional histories, customer dossiers, and proprietary business records.

---

### SECTION 7 — TERMINATION AND DATA PORTABILITY
7.1 **Termination for Convenience**: The Client may terminate its subscription at any time via the account settings portal. Termination becomes effective at the end of the active billing period.
7.2 **Termination for Cause**: Either Party may terminate this Agreement immediately upon written notice if the other Party materially breaches any term and fails to cure such breach within fifteen (15) days of written notice.
7.3 **Data Export and Deletion**: Upon termination, the Client shall have a thirty (30) day window to retrieve its data in standard exportable formats (JSON/CSV). Thereafter, the Provider securely deletes all production tenant data.

---

### SECTION 8 — LIMITATION OF LIABILITY
8.1 To the maximum extent permitted by applicable Quebec law, the total cumulative liability of PMC Solutions AI Inc. arising under this Agreement shall not exceed the aggregate fees actually paid by the Client in the three (3) months preceding the event giving rise to liability.
8.2 Neither Party shall be liable for indirect, punitive, special, incidental, or consequential damages, or loss of profits or business opportunity.

---

### SECTION 9 — GOVERNING LAW AND JURISDICTION
This Agreement shall be governed by and construed in accordance with the laws of the Province of Quebec and the federal laws of Canada applicable therein. The Parties irrevocably submit to the exclusive jurisdiction of the competent courts sitting in the judicial district of Montreal, Quebec.

---

### SECTION 10 — ELECTRONIC SIGNATURE AND CONSENT
Pursuant to the Quebec *Act to establish a legal framework for information technology* (CQLR c. C-1.1), the Parties agree that digital assent, cryptographic time-stamping (UTC), IP recording, and SHA-256 digest signing constitute a valid and enforceable electronic signature binding the Parties.
