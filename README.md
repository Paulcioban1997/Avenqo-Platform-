# Avenqo

Avenqo is the modular enterprise AI SaaS platform developed by PMC Solutions AI. Companies activate only the modules they need, while the shared AI Engine handles tenant-isolated data and model workflows.

## Architecture

**Next.js (`web/`) is the primary Avenqo SaaS web application.** It serves the public site, authentication, the signed-in workspace, business modules and administration. Flutter (`frontend/`) serves mobile and desktop and retains the existing Flutter web client.

Both clients call the FastAPI `/api/v1` contract. FastAPI owns permissions, subscription and module access, the AI credit ledger, financial calculations and tenant isolation. Retail, CRM and Accounting have implemented API paths and clients. See the [architecture reference](docs/ARCHITECTURE.md) for module availability, provider requirements and the scope of validation.

## Technology

- FastAPI and SQLAlchemy backend
- Flutter application for web, mobile, and desktop
- Next.js SaaS web application, including the public website and authentication
- Stripe billing integration
- Shared Python AI engine

## Structure of the project

- backend/: application core and service orchestration
- frontend/: application Flutter/Dart unique pour Web, mobile et desktop
- web/: primary Next.js SaaS client and authentication proxy
- modules/: reusable AI product modules
- shared/: shared AI engine
- payments/: billing and subscription preparation
- docs/: architecture and planning documents
- scripts/: operational helpers
- tests/: validation and quality strategy

## Adding a new AI module

1. Create a new folder under modules/
2. Document its responsibilities and boundaries
3. Keep its contracts isolated from other modules
4. Add its integration points in later implementation phases

## Phase 2 - Authentification Enterprise

The current phase delivers a FastAPI authentication foundation with:
- application factory via create_application()
- centralized settings via pydantic-settings
- request ID middleware
- centralized logging
- centralized error handling
- health endpoint at /api/v1/health
- root endpoint at /
- Argon2 passwords
- short-lived JWT access tokens
- rotating refresh tokens
- email verification and password recovery
- tenant-scoped organizations and employees
- role and permission enforcement

See [docs/authentication.md](docs/authentication.md) and [docs/roadmap.md](docs/roadmap.md).

## Phase 3 - Stripe

The billing layer supports Stripe Checkout, plan changes, end-of-period cancellation, Stripe Customer Portal, signed idempotent webhooks, and tenant-isolated invoice history. See [docs/billing.md](docs/billing.md).

## Client Web Next.js

Start FastAPI using the backend instructions below, then run the primary web client.

```powershell
cd web
npm ci
npm run dev
```

The local API defaults to `http://127.0.0.1:8000`. For Preview, the designated sandbox branches and Render sandbox builds, see the [deployment guide](docs/deployment.md).

## Client Flutter multiplateforme

Avenqo utilise une seule application Material dans `frontend/`. Les routes et
widgets sont partagés entre Web, Android, iOS, Windows, macOS et Linux.

Sous Windows, démarrer toute la pile locale avec une seule commande depuis la
racine du dépôt :

```powershell
.\scripts\start_local.ps1
```

Le script attend que l'API soit saine avant de lancer Flutter et limite la
surveillance Uvicorn à `backend/`, afin que les écritures SQLite ne redémarrent
pas le serveur pendant une connexion.

Pour tester l'interface locale avec les comptes et données réels du sandbox :

```powershell
.\scripts\start_local.ps1 -ApiTarget sandbox
```

Pour lancer uniquement Flutter :

```powershell
cd frontend
flutter pub get
flutter analyze
flutter test
flutter run -d chrome --web-port=8080 --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1
```

`--web-port=8080` est requis : `CORS_ORIGINS` (backend/.env) autorise explicitement
`http://localhost:8080`. Sans ce port fixe, Chrome choisit un port aléatoire et le
backend rejette silencieusement les requêtes (erreur CORS visible uniquement dans
la console navigateur).

## Running the backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --reload-dir backend --host 127.0.0.1 --port 8000
```

## Running tests

```powershell
pytest
```

## Phase 28 - Avenqo AI Chat

`/api/v1/ai/chat` provides tenant-isolated conversations, recent-message memory,
retrieval over authorized tenant resources, source traceability, and SSE streaming.
The provider abstraction supports OpenAI, Anthropic, and Gemini through environment
configuration; provider SDKs remain optional until a provider is selected.

```mermaid
flowchart TD
	User --> FastAPI
	FastAPI --> TenantSecurity[Tenant security]
	TenantSecurity --> ChatService
	ChatService --> Retrieval
	Retrieval --> TenantData[Tenant data]
	ChatService --> LLM[LLM provider]
	LLM --> Response[Response and sources]
```

Tenant identity comes only from authenticated server-side context. Conversation,
message, source, and retrieval queries are always scoped by `company_id`; retrieved
documents are explicitly treated as untrusted data and cannot override system rules.

## Local demo account

Create or refresh the verified demo tenant by providing its password through the environment:

```powershell
$env:AVENQO_DEMO_PASSWORD = "<demo-password>"
python -m scripts.seed_demo
Remove-Item Env:AVENQO_DEMO_PASSWORD
```
