#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace="$(cd -- "$script_dir/../../.." && pwd)"
python="$workspace/.venvs/oak4/bin/python"
case "${1:-live}" in
  live)
    shift || true
    systemctl --user stop uwa-oak4-live.service 2>/dev/null || true
    systemd-run --user --unit=uwa-oak4-live --collect \
      --property=KillMode=mixed --property=KillSignal=SIGINT --property=TimeoutStopSec=20 \
      --setenv="DISPLAY=${DISPLAY:-:0}" --setenv=QT_QPA_PLATFORM=xcb \
      --setenv=QT_QPA_FONTDIR=/usr/share/fonts/truetype/dejavu \
      "$python" "$script_dir/oak4_extremes.py" --preview --seconds 0 "$@"
    ;;
  stop) systemctl --user stop uwa-oak4-live.service ;;
  status) systemctl --user status uwa-oak4-live.service --no-pager ;;
  test)
    shift
    systemctl --user stop uwa-oak4-live.service 2>/dev/null || true
    exec "$python" "$script_dir/oak4_extremes.py" "$@"
    ;;
  *) echo "Usage: bash $0 {live [--profile NAME]|test [arguments]|stop|status}" >&2; exit 2 ;;
esac
