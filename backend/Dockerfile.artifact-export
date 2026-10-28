# One-shot rescue image. It does not contain Avenqo's API, Alembic, or the
# normal docker-entrypoint.sh (which may chown the mounted volume).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN python -m pip install --no-cache-dir boto3==1.43.81 cryptography==50.0.0
COPY scripts/export_artifact_volume.py /srv/export_artifact_volume.py

# The volume is owned by the application user. Read-only rescue requires root
# to inspect all files; the process has no code path that writes under ROOT.
USER 0
CMD ["python", "/srv/export_artifact_volume.py", "export"]
