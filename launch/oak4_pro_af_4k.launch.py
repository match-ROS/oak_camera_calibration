from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")

    oak_driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [
                    FindPackageShare("depthai_ros_driver_v3"),
                    "launch",
                    "driver.launch.py",
                ]
            )
        ),
        launch_arguments={
            "name": "oak",
            "namespace": "",
            "params_file": params_file,
            "camera_model": "OAK4-D",
            "override_cam_model": "true",
            "parent_frame": "tool0",
        }.items(),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("oak_camera_calibration"),
                        "config",
                        "oak4_pro_af_4k.yaml",
                    ]
                ),
                description="DepthAI ROS driver parameter file.",
            ),
            oak_driver,
        ]
    )
