#!/usr/bin/env bash
# Compatibility launcher; canonical setup script lives in scripts/setup.sh.
exec "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/scripts/setup.sh" "$@"
