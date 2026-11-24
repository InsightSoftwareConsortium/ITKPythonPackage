#!/usr/bin/env bash
# Sourced by the build scripts; not run on its own.

# require_env_vars NAME...
# Report every named variable that is unset or empty, then exit if any was.
require_env_vars() {
  local missing=0 v
  for v in "$@"; do
    if [ -z "${!v:-}" ]; then
      missing=1
      echo "ERROR: Required environment variable '$v' is not set or empty."
    fi
  done
  if [ "${missing}" -ne 0 ]; then
    exit 1
  fi
}
