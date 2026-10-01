import { bucket, defineRailway, github, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const AvenqoPlatform = github("Paulcioban1997/Avenqo-Platform-", { checkSuites: false });

  const Postgres = postgres("Postgres", { region: "sfo" });
  Postgres.networking = { privateNetworkEndpoint: "postgres", tcpProxies: { "5432": {} } };
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const avenqoPlatformVolumeNU6W = volume("avenqo-platform--volume-nU6W", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 5000 });
  const avenqoBackups = bucket("avenqo-backups", { region: "iad" });
  const AvenqoPlatform2 = service("Avenqo-Platform-", {
    source: AvenqoPlatform,
    healthcheck: "/api/v1/health",
    healthcheckTimeout: 600,
    replicas: { "sfo": 1 },
    domains: [{ domain: "api.avenqo.ca", port: 8000 }],
    networking: { privateNetworkEndpoint: "avenqo-platform" },
    volumeMounts: { "/data/artifacts": avenqoPlatformVolumeNU6W },
    env: { AI_PRIMARY_PROVIDER: preserve(), ALLOWED_HOSTS: preserve(), ANTHROPIC_API_KEY: preserve(), ANTHROPIC_MODEL: preserve(), ARTIFACT_ROOT: preserve(), AUTH_JWT_SECRET: preserve(), BACKUP_S3_ACCESS_KEY: preserve(), BACKUP_S3_BUCKET: preserve(), BACKUP_S3_ENDPOINT_URL: preserve(), BACKUP_S3_REGION: preserve(), BACKUP_S3_SECRET_KEY: preserve(), CONNECTOR_ENCRYPTION_KEYS: preserve(), CORS_ORIGINS: preserve(), DATABASE_URL: preserve(), EMAIL_API_KEY: preserve(), EMAIL_FROM_EMAIL: preserve(), EMAIL_FROM_NAME: preserve(), EMAIL_PROVIDER: preserve(), ENVIRONMENT: preserve(), FRONTEND_URL: preserve(), GEMINI_MODEL: preserve(), GIT_SHA: preserve(), GOOGLE_AI_API_KEY: preserve(), GOOGLE_CALENDAR_CLIENT_ID: preserve(), GOOGLE_CALENDAR_CLIENT_SECRET: preserve(), GOOGLE_CALENDAR_REDIRECT_URI: preserve(), OPENAI_API_KEY: preserve(), OPENAI_MODEL: preserve(), RAILWAY_DOCKERFILE_PATH: preserve(), SHOPIFY_API_VERSION: preserve(), SHOPIFY_CLIENT_ID: preserve(), SHOPIFY_CLIENT_SECRET: preserve(), SHOPIFY_REDIRECT_URI: preserve(), SHOPIFY_SCOPES: preserve(), SHOPIFY_WEBHOOK_URI: preserve(), SMTP_FROM_EMAIL: preserve(), SMTP_HOST: preserve(), SMTP_PASSWORD: preserve(), SMTP_PORT: preserve(), SMTP_USERNAME: preserve(), SMTP_USE_TLS: preserve(), STRIPE_PRICE_BASE: preserve(), STRIPE_PRICE_CREDIT_25000: preserve(), STRIPE_PRICE_CREDIT_6500: preserve(), STRIPE_PRICE_CREDIT_65000: preserve(), STRIPE_PRICE_CREDIT_DEMO: preserve(), STRIPE_PRICE_CREDIT_PROFESSIONAL: preserve(), STRIPE_PRICE_DEMO: preserve(), STRIPE_PRICE_ENTERPRISE: preserve(), STRIPE_PRICE_PROFESSIONAL: preserve(), STRIPE_SECRET_KEY: preserve(), STRIPE_WEBHOOK_SECRET: preserve(), WOOCOMMERCE_ALLOW_INSECURE_LOCALHOST: preserve(), WOOCOMMERCE_APP_NAME: preserve(), WOOCOMMERCE_CALLBACK_URI: preserve(), WOOCOMMERCE_WEBHOOK_URI: preserve() },
  });
  const avenqoDailyBackup = service("avenqo-daily-backup", {
    source: AvenqoPlatform,
    start: "python scripts/backup_db.py",
    replicas: { "us-east4-eqdc4a": 1 },
    deploy: { cronSchedule: "0 7 * * *", restartPolicyType: "NEVER" },
    env: { AUTH_JWT_SECRET: preserve(), BACKUP_S3_ACCESS_KEY: preserve(), BACKUP_S3_BUCKET: preserve(), BACKUP_S3_ENDPOINT_URL: preserve(), BACKUP_S3_REGION: preserve(), BACKUP_S3_SECRET_KEY: preserve(), DATABASE_URL: preserve(), ENVIRONMENT: preserve(), RAILWAY_DOCKERFILE_PATH: preserve() },
  });

  return project("alert-tenderness", {
    resources: [AvenqoPlatform2, Postgres, avenqoDailyBackup, postgresVolume, avenqoPlatformVolumeNU6W, avenqoBackups],
  });
});
