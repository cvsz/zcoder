#!/usr/bin/env bash
# Compatibility launcher; canonical build script lives in scripts/build.sh.
exec "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/scripts/build.sh" "$@"
