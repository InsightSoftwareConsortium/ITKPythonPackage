#!/bin/bash

set -e
set -o pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

pushd $SCRIPT_DIR > /dev/null

docker run --rm -it \
	--name df-shellcheck \
	-v $(pwd):/usr/src:ro \
	--workdir /usr/src \
	r.j3ss.co/shellcheck ./internal/shellcheck-run.sh

exit_code=$?

popd > /dev/null

exit $exit_code
