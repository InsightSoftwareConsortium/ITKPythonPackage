#!/bin/bash

set -e
set -o pipefail

_script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

pushd ${_script_dir} > /dev/null

docker run --rm -it \
	--name df-shellcheck \
	-v $(pwd):/usr/src:ro \
	--workdir /usr/src \
	r.j3ss.co/shellcheck ./internal/shellcheck-run.sh

exit_code=$?

popd > /dev/null

exit $exit_code
