#!/bin/bash

set -e
set -o pipefail

(
exit_code=0

#
# SC1090: Can't follow non-constant source. Use a directive to specify location.
# SC2006: Use $(..) instead of legacy `..`.
# SC2046: Quote this to prevent word splitting.
# SC2086: Double quote to prevent globbing and word splitting.
# SC2153: Possible misspelling: SCRIPT_DIR may not be assigned, but script_dir is.
# SC2155: Declare and assign separately to avoid masking return values.
#

# find all executables and run `shellcheck`
for f in $(find . -type f -not -iwholename '*.git*' | sort -u); do
	if file "$f" | grep --quiet -e shell -e bash; then
		shellcheck \
      -e SC1090 \
      -e SC2046 \
      -e SC2086 \
      "$f" \
    && echo "[OK]: successfully linted $f" || echo "[FAILED]: found issues linting $f"
    current_exit_code=$?
    if [[ $current_exit_code != 0 ]]; then
      exit_code=$current_exit_code
    fi
	fi
done

exit $exit_code
)
