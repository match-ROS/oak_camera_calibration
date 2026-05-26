from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_base_frame", default_value="base_link"),
            DeclareLaunchArgument("robot_tcp_frame", default_value="tool0"),
            Node(
                package="oak_camera_calibration",
                executable="oak_sample_gui",
                name="oak_sample_gui",
                output="screen",
                parameters=[
                    {
                        "robot_base_frame": LaunchConfiguration("robot_base_frame"),
                        "robot_tcp_frame": LaunchConfiguration("robot_tcp_frame"),
                    }
                ],
            )
        ]
    )
