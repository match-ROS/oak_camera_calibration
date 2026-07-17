from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    parent_frame = LaunchConfiguration("parent_frame")
    cam_pos_x = LaunchConfiguration("cam_pos_x")
    cam_pos_y = LaunchConfiguration("cam_pos_y")
    cam_pos_z = LaunchConfiguration("cam_pos_z")
    cam_roll = LaunchConfiguration("cam_roll")
    cam_pitch = LaunchConfiguration("cam_pitch")
    cam_yaw = LaunchConfiguration("cam_yaw")
    pointcloud_enable = LaunchConfiguration("pointcloud_enable")

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
            "camera_model": "OAK4-D-PRO",
            "override_cam_model": "true",
            "parent_frame": parent_frame,
            "cam_pos_x": cam_pos_x,
            "cam_pos_y": cam_pos_y,
            "cam_pos_z": cam_pos_z,
            "cam_roll": cam_roll,
            "cam_pitch": cam_pitch,
            "cam_yaw": cam_yaw,
            "pointcloud.enable": pointcloud_enable,
            # Loading the RSP and camera component into the same container is
            # racy in the Jazzy depthai_ros_driver_v3 launch file. In failed
            # starts only oak_state_publisher appears and the Driver is lost.
            "rsp_use_composition": "false",
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
                        "oak4_pro_af_gui.yaml",
                    ]
                ),
                description="DepthAI ROS driver parameter file for GUI preview.",
            ),
            DeclareLaunchArgument(
                "parent_frame",
                default_value="mur620/UR10_r/tool0",
                description="Parent frame for OAK calibration TF publication.",
            ),
            DeclareLaunchArgument(
                "cam_pos_x",
                default_value="0.0068564203",
                description="Calibrated OAK base-frame X offset from parent frame.",
            ),
            DeclareLaunchArgument(
                "cam_pos_y",
                default_value="-0.0892312561",
                description="Calibrated OAK base-frame Y offset from parent frame.",
            ),
            DeclareLaunchArgument(
                "cam_pos_z",
                default_value="0.1018930213",
                description="Calibrated OAK base-frame Z offset from parent frame.",
            ),
            DeclareLaunchArgument(
                "cam_roll",
                default_value="-3.0221294847",
                description="Calibrated OAK base-frame roll from parent frame.",
            ),
            DeclareLaunchArgument(
                "cam_pitch",
                default_value="-1.5221462887",
                description="Calibrated OAK base-frame pitch from parent frame.",
            ),
            DeclareLaunchArgument(
                "cam_yaw",
                default_value="-1.7026932502",
                description="Calibrated OAK base-frame yaw from parent frame.",
            ),
            DeclareLaunchArgument(
                "pointcloud_enable",
                default_value="false",
                description="Forwarded to depthai_ros_driver_v3 as pointcloud.enable.",
            ),
            oak_driver,
        ]
    )
