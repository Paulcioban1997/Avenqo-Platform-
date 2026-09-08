#!/bin/sh
# Fix ownership of the persistent volume (Railway mounts it root:root) before
# dropping privileges to the unprivileged application user via gosu.
set -e

if [ -n "$ARTIFACT_ROOT" ]; then
    echo "Validating artifact volume ownership at $ARTIFACT_ROOT"
    install -d -o avenqo -g avenqo -m 2770 "$ARTIFACT_ROOT"
    chown -R avenqo:avenqo "$ARTIFACT_ROOT"
    find "$ARTIFACT_ROOT" -type d -exec chmod u+rwx,g+rx,g+s {} +
    find "$ARTIFACT_ROOT" -type f -exec chmod u+rw,g+r {} +
fi

umask 0002
exec gosu avenqo "$@"
