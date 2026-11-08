#!/bin/sh
# Fix ownership of persistent storage & directories before dropping privileges
# to the unprivileged application user (avenqo) via gosu.
set -e

# If invoked with the entrypoint itself as the first argument (e.g. from Railway startCommand),
# shift to avoid redundant re-invocation.
if [ "$1" = "/usr/local/bin/docker-entrypoint.sh" ] || [ "$1" = "docker-entrypoint.sh" ]; then
    shift
fi

if [ -n "$ARTIFACT_ROOT" ] && [ -d "$ARTIFACT_ROOT" ]; then
    echo "Ensuring artifact volume permissions at $ARTIFACT_ROOT"
    chown -R avenqo:avenqo "$ARTIFACT_ROOT" 2>/dev/null || true
    chmod -R u+rwX,g+rwX "$ARTIFACT_ROOT" 2>/dev/null || true
fi

BACKUP_DIR="${BACKUP_ROOT:-/srv/var/backups}"
mkdir -p "$BACKUP_DIR" 2>/dev/null || true
chown -R avenqo:avenqo /srv/var 2>/dev/null || true
chmod -R u+rwx,g+rwx /srv/var 2>/dev/null || true

MODEL_DIR="${MODEL_REGISTRY_ROOT:-/srv/var/models}"
if [ -n "$MODEL_DIR" ]; then
    echo "Validating model directory ownership at $MODEL_DIR"
    install -d -o avenqo -g avenqo -m 2775 "$MODEL_DIR" 2>/dev/null || mkdir -p "$MODEL_DIR" 2>/dev/null || true
    model_owner=$(stat -c '%U:%G' "$MODEL_DIR" 2>/dev/null || true)
    if [ "$model_owner" != "avenqo:avenqo" ]; then
        chown -R avenqo:avenqo "$MODEL_DIR" 2>/dev/null || true
        chmod -R 2775 "$MODEL_DIR" 2>/dev/null || true
    fi
fi

if [ -d "/srv/var" ]; then
    var_owner=$(stat -c '%U:%G' "/srv/var" 2>/dev/null || true)
    if [ "$var_owner" != "avenqo:avenqo" ]; then
        chown -R avenqo:avenqo /srv/var 2>/dev/null || true
    fi
fi

umask 0002

# Only drop privileges via gosu if currently running as root (UID 0)
if [ "$(id -u)" = "0" ]; then
    exec gosu avenqo "$@"
else
    exec "$@"
fi
