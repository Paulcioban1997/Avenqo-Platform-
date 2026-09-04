#!/bin/sh
# Fixe la propriété du volume persistant (monté root:root par défaut par
# Railway) avant de passer la main à l'utilisateur applicatif non-root.
set -e

if [ -n "$ARTIFACT_ROOT" ] && [ -d "$ARTIFACT_ROOT" ]; then
    chown -R avenqo:avenqo "$ARTIFACT_ROOT" 2>/dev/null || true
fi

exec gosu avenqo "$@"
