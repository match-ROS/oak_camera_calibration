from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="oak_camera_calibration",
                executable="oak_sample_gui",
                name="oak_sample_gui",
                output="screen",
            )
        ]
    )
