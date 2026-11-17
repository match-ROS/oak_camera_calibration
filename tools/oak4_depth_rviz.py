#!/usr/bin/env python3
"""Show a saved native HQ depth snapshot in a dedicated, read-only RViz view."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import subprocess

import cv2
import numpy as np
import yaml
from oak4_depth_geometry import depth_to_xyz

TOOLS = Path(__file__).resolve().parent
WORKSPACE = TOOLS.parents[2]
FRAME = 'oak4_snapshot_rectified_right_optical'
VIEW_FRAME = 'oak4_snapshot_view'


def select_capture(directory):
    if directory:
        root = Path(directory).expanduser().resolve()
    else:
        candidates = sorted((WORKSPACE / 'setup/oak4/depth').glob('*/metadata.json'), reverse=True)
        root = None
        for path in candidates:
            data = json.loads(path.read_text())
            if data.get('success') and data.get('projection') and data.get('hq'):
                root = path.parent
                break
        if root is None:
            raise ValueError('No HQ depth with rectified projection; capture a new --mode depth_hq first')
    metadata = json.loads((root / 'metadata.json').read_text())
    if not metadata.get('success') or metadata.get('kind') != 'depth':
        raise ValueError('Select a successful depth capture')
    if not metadata.get('projection'):
        raise ValueError('Old capture has no rectified projection; capture a new HQ depth, do not substitute factory K')
    return root, metadata


def configuration():
    def cloud(name, topic, enabled):
        return dict(Class='rviz_default_plugins/PointCloud2', Name=name, Enabled=enabled,
                    **{'Topic': {'Value': topic, 'Reliability Policy': 'Reliable',
                                'Durability Policy': 'Transient Local', 'History Policy': 'Keep Last', 'Depth': 1},
                       'Style': 'Points', 'Size (Pixels)': 2, 'Size (m)': .003,
                       'Position Transformer': 'XYZ', 'Color Transformer': 'AxisColor', 'Axis': 'X',
                       'Use Fixed Frame': True, 'Autocompute Value Bounds': False,
                       'Min Value': 0., 'Max Value': 6., 'Alpha': 1., 'Decay Time': 0})
    return {'Panels': [{'Class': 'rviz_common/Displays', 'Name': 'Displays'},
                       {'Class': 'rviz_common/Views', 'Name': 'Views'}],
            'Visualization Manager': {
                'Class': '', 'Name': 'root', 'Enabled': True,
                'Global Options': {'Fixed Frame': VIEW_FRAME, 'Background Color': '35; 39; 45', 'Frame Rate': 30},
                'Displays': [cloud('HQ DEPTH - static snapshot', '/oak4/depth_snapshot/hq/points', True),
                             cloud('STANDARD - single frame (optional)', '/oak4/depth_snapshot/standard/points', False),
                             {'Class': 'rviz_default_plugins/MarkerArray', 'Name': 'SNAPSHOT date and legend',
                              'Enabled': True, 'Marker Topic': {'Value': '/oak4/depth_snapshot/labels',
                               'Reliability Policy': 'Reliable', 'Durability Policy': 'Transient Local'}}],
                'Tools': [{'Class': 'rviz_default_plugins/MoveCamera'}, {'Class': 'rviz_default_plugins/Interact'},
                          {'Class': 'rviz_default_plugins/Select'}, {'Class': 'rviz_default_plugins/FocusCamera'},
                          {'Class': 'rviz_default_plugins/Measure'}],
                'Views': {'Current': {'Class': 'rviz_default_plugins/Orbit', 'Name': 'Depth overview',
                    'Target Frame': '<Fixed Frame>', 'Distance': 5., 'Pitch': .3, 'Yaw': 3.35,
                    'Near Clip Distance': .01, 'Focal Point': {'X': 2.2, 'Y': 0., 'Z': -.3}}}},
            'Window Geometry': {'Width': 1500, 'Height': 950}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', help='Capture directory; default latest successful HQ with projection metadata')
    args = parser.parse_args()
    directory, metadata = select_capture(args.capture)
    k = metadata['projection']['K']
    size = tuple(metadata['projection']['size'])
    clouds = {}
    for key in ('hq', 'standard'):
        depth = cv2.imread(str(directory / metadata[key]['path']), cv2.IMREAD_UNCHANGED)
        if depth is None or depth.shape[::-1] != size:
            raise ValueError(f'{key}: depth file does not match recorded projection')
        clouds[key] = depth_to_xyz(depth, k)
    if not len(clouds['hq']):
        raise ValueError('HQ depth contains no valid points')
    os.environ['ROS_DOMAIN_ID'] = '65'
    os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    import rclpy
    from rclpy.qos import QoSProfile, DurabilityPolicy
    from rclpy.signals import SignalHandlerOptions
    from sensor_msgs.msg import PointCloud2, PointField
    from geometry_msgs.msg import TransformStamped
    from std_msgs.msg import String
    from visualization_msgs.msg import Marker, MarkerArray
    from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('depth_snapshot_view', namespace='/oak4')
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    publishers = {key: node.create_publisher(PointCloud2, f'/oak4/depth_snapshot/{key}/points', qos) for key in clouds}
    label_pub = node.create_publisher(MarkerArray, '/oak4/depth_snapshot/labels', qos)
    status_pub = node.create_publisher(String, '/oak4/depth_snapshot/info', qos)
    tf = StaticTransformBroadcaster(node)
    transform = TransformStamped()
    transform.header.frame_id = VIEW_FRAME
    transform.child_frame_id = FRAME
    transform.header.stamp = node.get_clock().now().to_msg()
    # Optical X right/Y down/Z forward -> view X forward/Y left/Z up.
    transform.transform.rotation.x = -.5
    transform.transform.rotation.y = .5
    transform.transform.rotation.z = -.5
    transform.transform.rotation.w = .5
    tf.sendTransform(transform)
    messages = {}
    for key, points in clouds.items():
        message = PointCloud2()
        message.header.frame_id = FRAME
        message.height = 1
        message.width = len(points)
        message.fields = [PointField(name=name, offset=i*4, datatype=PointField.FLOAT32, count=1)
                          for i, name in enumerate(('x', 'y', 'z'))]
        message.is_bigendian = False
        message.point_step = 12
        message.row_step = len(points)*12
        message.data = points.tobytes()
        message.is_dense = True
        messages[key] = message
    label = Marker()
    label.header.frame_id = VIEW_FRAME
    label.ns = 'oak4_depth_snapshot'
    label.id = 0
    label.type = Marker.TEXT_VIEW_FACING
    label.action = Marker.ADD
    label.pose.position.x = 2.
    label.pose.position.z = 1.1
    label.pose.orientation.w = 1.
    label.scale.z = .075
    label.color.r = label.color.g = label.color.b = label.color.a = 1.
    label.text = (f'STATIC HQ DEPTH - {metadata["started_at"][:19]}\n'
                  f'{len(metadata["frames"])} frames | {len(clouds["hq"]):,} valid points | units: metres\n'
                  'Camera coordinates - no cell registration - not live')
    info = dict(capture=str(directory), captured_at=metadata['started_at'],
                point_counts={key: len(value) for key, value in clouds.items()},
                fixed_frame=VIEW_FRAME, optical_frame=FRAME, domain=65,
                registration='camera-local; no world/cell transform',
                timestamp_semantics='ROS header is republish time; acquisition metadata remains immutable',
                projection_source=metadata['projection']['source'])
    runtime = WORKSPACE / 'setup/oak4/rviz'
    runtime.mkdir(parents=True, exist_ok=True)
    cfg = runtime / 'depth-snapshot.rviz'
    cfg.write_text(yaml.safe_dump(configuration(), sort_keys=False))
    (runtime / 'latest-view.json').write_text(json.dumps(info, indent=2) + '\n')
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'xcb'
    for key in ('GTK_PATH', 'GTK_EXE_PREFIX', 'GTK_IM_MODULE_FILE', 'GIO_MODULE_DIR', 'GSETTINGS_SCHEMA_DIR'):
        if '/snap/' in env.get(key, ''):
            env.pop(key, None)
    child = None
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    def publish():
        now = node.get_clock().now().to_msg()
        for key, message in messages.items():
            message.header.stamp = now
            publishers[key].publish(message)
        label.header.stamp = now
        label_pub.publish(MarkerArray(markers=[label]))
        status_pub.publish(String(data=json.dumps(info)))
    timer = node.create_timer(1., publish)
    publish()
    try:
        child = subprocess.Popen(['rviz2', '-d', str(cfg), '--ros-args', '-r', '__node:=oak4_depth_rviz'],
                                 env=env, start_new_session=True)
        node.get_logger().info('Showing STATIC HQ snapshot: ' + str(directory))
        while not stopped and child.poll() is None and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=.2)
        if child.poll() not in (None, 0) and not stopped:
            raise RuntimeError(f'RViz exited with code {child.returncode}')
    finally:
        if child and child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=5)
        node.destroy_timer(timer)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
