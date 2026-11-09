#!/usr/bin/env bash
# Host-only SDK setup; does not alter networking, device OS or ROS Python.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace="$(cd -- "$script_dir/../../.." && pwd)"
venv="$workspace/.venvs/oak4"
artifacts="$workspace/setup/oak4"
mkdir -p "$artifacts/bin"
if [[ ! -x "$venv/bin/python" ]]; then
  python3 -m venv --without-pip "$venv"
fi
if ! "$venv/bin/python" -m pip --version >/dev/null 2>&1; then
  python3 - "$artifacts/get-pip.py" <<'PY'
from pathlib import Path
from urllib.request import urlopen
import sys
Path(sys.argv[1]).write_bytes(urlopen('https://bootstrap.pypa.io/get-pip.py', timeout=60).read())
PY
  "$venv/bin/python" "$artifacts/get-pip.py"
fi
"$venv/bin/python" -m pip install -r "$script_dir/requirements-oak4.txt"
if [[ ! -x "$artifacts/bin/oakctl" ]]; then
  python3 - "$artifacts/bin/oakctl" <<'PY'
from pathlib import Path
from urllib.request import urlopen
import platform
import sys
if platform.machine() != 'x86_64':
    raise SystemExit('This oakctl download is for Linux x86_64 only.')
target = Path(sys.argv[1])
target.write_bytes(urlopen('https://oakctl-releases.luxonis.com/data/0.31.1/linux_x86_64/oakctl', timeout=120).read())
target.chmod(0o755)
PY
fi
"$artifacts/bin/oakctl" --version
# depthai 3.12.0's WHEEL has a blank line before its valid cp314 tags;
# pip check misreads those tags as a missing platform declaration. Verify the
# native imports instead; do not rewrite the vendor's installed metadata.
"$venv/bin/python" - <<'PY'
import cv2
import depthai
import numpy
print('Native import check:', depthai.__version__, cv2.__version__, numpy.__version__)
PY
echo "Ready: bash $script_dir/oak4.sh live --profile rgb_preview"
