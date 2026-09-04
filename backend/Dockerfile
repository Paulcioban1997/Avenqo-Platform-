# syntax=docker/dockerfile:1
# Backend Avenqo — image de production (Phase 34).
#
# Limitations connues (voir docs/production-deployment.md) :
#  - Les migrations ne sont PAS appliquées automatiquement par cette image ;
#    `alembic upgrade head` (ou l'équivalent `create_all` documenté) doit être
#    exécuté explicitement comme étape de déploiement séparée.
#  - Aucune variable secrète n'est copiée dans l'image ; tout est injecté à
#    l'exécution via variables d'environnement.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Dépendances système minimales. Railway PostgreSQL tourne en 18.x ; le client
# pg_dump doit être de la même version majeure (un pg_dump 17 refuse un serveur 18).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gosu \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY alembic.ini alembic.ini
COPY alembic alembic
COPY shared shared
COPY payments payments
COPY modules modules
COPY scripts scripts
COPY frontend/assets/i18n frontend/assets/i18n

RUN useradd --create-home --shell /usr/sbin/nologin avenqo \
    && chown -R avenqo:avenqo /srv
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Stays root at startup: a Railway volume mounted at ARTIFACT_ROOT is
# created root:root, which the entrypoint fixes before handing off to the
# unprivileged application user (avenqo) via gosu.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status==200 else 1)"

# En production, ne PAS activer --reload et ne PAS monter le code source
# en volume (contrairement au usage de docker-compose.yml, réservé au dev).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
