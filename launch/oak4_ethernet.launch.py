"""Standalone Ethernet OAK4; no robot bringup or historic hand-eye transform."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=PathJoinSubstitution([
            FindPackageShare('oak_camera_calibration'), 'config', 'oak4_ethernet.yaml'])),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(PathJoinSubstitution([
            FindPackageShare('depthai_ros_driver'), 'launch', 'driver.launch.py'])),
            launch_arguments={
                'name': 'oak', 'namespace': '',
                'params_file': LaunchConfiguration('params_file'),
                'camera_model': 'OAK4-D', 'override_cam_model': 'true',
                'parent_frame': 'oak_mount',
                'cam_pos_x': '0.0', 'cam_pos_y': '0.0', 'cam_pos_z': '0.0',
                'cam_roll': '0.0', 'cam_pitch': '0.0', 'cam_yaw': '0.0',
                'rsp_use_composition': 'false',
            }.items()),
    ])
