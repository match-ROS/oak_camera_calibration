#!/usr/bin/env bash
# Persistent photo service; starting it does not open or stream the camera.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
unit=uwa-oak4-photo.service
case "${1:-help}" in
  install)
    unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$unit_dir"
    cat > "$unit_dir/$unit" <<EOF
[Unit]
Description=UWA OAK4 48MP standard and static HQ photo service (ROS domain 65)
[Service]
Type=simple
ExecStart=/bin/bash "$script_dir/oak4_photo.sh" serve
KillSignal=SIGINT
KillMode=mixed
TimeoutStopSec=330
Restart=on-failure
RestartSec=5
[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now "$unit"
    ;;
  start|stop|restart|status)
    exec systemctl --user "$1" "$unit" --no-pager ;;
  logs) exec journalctl --user -u "$unit" -n 60 --no-pager ;;
  serve)
    set +u
    source /opt/ros/lyrical/setup.bash
    set -u
    export ROS_DOMAIN_ID=65 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
    exec /usr/bin/python3 "$script_dir/oak4_photo_service.py" serve ;;
  view-depth)
    shift
    set +u
    source /opt/ros/lyrical/setup.bash
    set -u
    export ROS_DOMAIN_ID=65 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
    exec /usr/bin/python3 "$script_dir/oak4_depth_rviz.py" "$@" ;;
  check)
    shift
    exec /usr/bin/python3 "$script_dir/oak4_photo_check.py" "$@" ;;
  capture)
    shift
    exec /usr/bin/python3 "$script_dir/oak4_photo_service.py" capture "$@" ;;
  *) echo "Usage: bash $0 {check [--count 3] [--focus 116]|view-depth [--capture DIRECTORY]|install|start|stop|restart|status|logs|capture [--mode hq|standard|compare|hdr|depth_hq|depth_standard|depth_compare|rgbd] [--frames N] [--iso 100] [--focus 0..255]}" ;;
esac
