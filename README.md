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

and writes to `~/oak_handeye_samples`. It stores the raw image, the received
`CameraInfo`, and a rectified PNG computed from that `CameraInfo`. For hand-eye
calibration it is usually best to keep the raw image plus distortion
coefficients and let the calibration/detection code use both explicitly.

You can override topics or output path like this:

```bash
ros2 run oak_camera_calibration capture_oak_snapshot --ros-args \
  -p image_topic:=/oak/rgb/image_raw \
  -p camera_info_topic:=/oak/rgb/camera_info \
  -p output_dir:=~/oak_handeye_samples \
  -p save_rectified:=true
```
