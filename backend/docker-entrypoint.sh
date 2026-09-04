#!/bin/sh
# Fixe la propriÃ©tÃ© du volume persistant (montÃ© root:root par dÃ©faut par
# Railway) avant de passer la main Ã  l'utilisateur applicatif non-root.
set -e

if [ -n "$ARTIFACT_ROOT" ] && [ -d "$ARTIFACT_ROOT" ]; then
    chown -R avenqo:avenqo "$ARTIFACT_ROOT" 2>/dev/null || true
fi

exec gosu avenqo "$@"
