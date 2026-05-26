# oak_camera_calibration

ROS 2 helpers for hand-eye calibration with an OAK 4 Pro AF mounted on a UR10e
end effector.

## First step: acquire calibrated RGB images

Build the package from the workspace root:

```bash
cd /home/rosmatch/colcon_ws_recker
source /opt/ros/jazzy/setup.bash
colcon build --packages-select oak_camera_calibration --symlink-install
source install/setup.bash
```

If ROS prints warnings about switching between `one` and `jazzy`, start a fresh
terminal or clear the old ROS environment before sourcing Jazzy:

```bash
unset ROS_DISTRO ROS_VERSION ROS_PYTHON_VERSION ROS_ROOT ROS_PACKAGE_PATH
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH
unset LD_LIBRARY_PATH PYTHONPATH
source /opt/ros/jazzy/setup.bash
source /home/rosmatch/colcon_ws_recker/install/setup.bash
```

Start the OAK via the installed DepthAI ROS 2 V3 driver:

```bash
ros2 launch oak_camera_calibration oak4_pro_af_rgb.launch.py
```

This uses `config/oak4_pro_af_rgb.yaml` and requests an 8000x6000 RGB stream
at low FPS. If USB bandwidth or processing load is too high, start with the 4K
profile:

```bash
ros2 launch oak_camera_calibration oak4_pro_af_4k.launch.py
```

Save one image together with the factory calibration published as `CameraInfo`:

```bash
ros2 run oak_camera_calibration capture_oak_snapshot
```

By default the snapshot tool listens to:

- `/oak/rgb/image_raw`
- `/oak/rgb/camera_info`

and writes to `~/oak_handeye_samples`. It ignores the first frames while
auto-exposure and autofocus settle, skips very dark frames, then stores the
sharpest frame from a short burst. It writes the raw image, the received
`CameraInfo`, image metrics, and a rectified PNG computed from that
`CameraInfo`. For hand-eye calibration it is usually best to keep the raw image
plus distortion coefficients and let the calibration/detection code use both
explicitly.

You can override topics or output path like this:

```bash
ros2 run oak_camera_calibration capture_oak_snapshot --ros-args \
  -p image_topic:=/oak/rgb/image_raw \
  -p camera_info_topic:=/oak/rgb/camera_info \
  -p output_dir:=~/oak_handeye_samples \
  -p save_rectified:=true
```

Useful snapshot parameters while tuning image quality:

```bash
ros2 run oak_camera_calibration capture_oak_snapshot --ros-args \
  -p warmup_frames:=20 \
  -p select_frames:=20 \
  -p min_mean_intensity:=10.0 \
  -p timeout_sec:=60.0
```

If images remain blurry after warmup, inspect live focus first:

```bash
ros2 run rqt_image_view rqt_image_view /oak/rgb/image_raw
```

For calibration captures, fixed lighting and a fixed working distance are
preferable. Once the target distance is known, manual focus via the DepthAI
driver parameters can be tested instead of relying on autofocus.

## GUI sample capture

For repeated hand-eye samples, keep the camera driver running and start the GUI:

```bash
ros2 run oak_camera_calibration oak_sample_gui
```

The GUI uses the 10x7 ArUco GridBoard with `DICT_4X4_250`, 30 mm markers, and
10 mm separation. It detects the board with a downscaled full-image pass, then
refines inside an ROI so the full 8k image is never passed directly to
`cv2.aruco.detectMarkers()`.

By default each saved sample also stores the current TF from `base_link` to `tool0`.
If your UR TCP frame has a different name, pass it explicitly:

```bash
ros2 run oak_camera_calibration oak_sample_gui --ros-args \
  -p robot_base_frame:=base_link \
  -p robot_tcp_frame:=tool0
```

The HUD shows whether this TF is available. With the default
`require_robot_pose:=true` and `require_detection_pose:=true`, pressing `s` only
writes a sample if the image, `CameraInfo`, marker pose, and robot TF are all
available.

Keys:

- `s`: save one sample
- `d`: toggle marker detection
- `q` or `Esc`: close the GUI

Samples are appended to `~/oak_handeye_samples` as `sample_000`, `sample_001`,
and so on. Closing the GUI never deletes samples; delete files manually only
when you really want to discard them.

Each sample contains:

- raw PNG
- optional rectified PNG
- annotated PNG
- `CameraInfo` YAML
- JSON metadata with board model, marker IDs, ROI, pose, reprojection error, and
  the UR base-to-TCP transform

## Compute hand-eye transform

After capturing multiple poses, compute the camera transform relative to the TCP:

```bash
ros2 run oak_camera_calibration compute_handeye --samples-dir ~/oak_handeye_samples
```

The tool uses OpenCV's eye-in-hand calibration and prints `tcp <- camera`,
per-sample translational/rotational consistency, and the marker reprojection
error. Samples without robot TF are skipped. Large residuals are a good hint
that a sample should be inspected and deleted manually before recomputing.
