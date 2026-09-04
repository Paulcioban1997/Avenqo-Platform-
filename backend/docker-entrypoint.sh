#!/bin/sh
# Fix ownership of the persistent volume (Railway mounts it root:root) before
# dropping privileges to the unprivileged application user via gosu.
set -e

if [ -n "$ARTIFACT_ROOT" ] && [ -d "$ARTIFACT_ROOT" ]; then
    chown -R avenqo:avenqo "$ARTIFACT_ROOT" 2>/dev/null || true
fi

exec gosu avenqo "$@"
