from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    parent_frame = LaunchConfiguration("parent_frame")

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
            "parent_frame": parent_frame,
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
            DeclareLaunchArgument(
                "parent_frame",
                default_value="mur620/UR10_r/tool0",
                description="Parent frame for OAK calibration TF publication.",
            ),
            oak_driver,
        ]
    )
