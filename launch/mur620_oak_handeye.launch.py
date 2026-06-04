from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_name = LaunchConfiguration("robot_name")
    arm = LaunchConfiguration("arm")
    launch_camera = LaunchConfiguration("launch_camera")
    camera_launch_file = LaunchConfiguration("camera_launch_file")
    camera_parent_frame = LaunchConfiguration("camera_parent_frame")

    camera_driver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [
                    FindPackageShare("oak_camera_calibration"),
                    "launch",
                    camera_launch_file,
                ]
            )
        ),
        condition=IfCondition(launch_camera),
        launch_arguments={
            "parent_frame": camera_parent_frame,
        }.items(),
    )

    handeye_session = Node(
        package="oak_camera_calibration",
        executable="semi_auto_handeye_session",
        name="semi_auto_handeye_session",
        output="screen",
        parameters=[
            {
                "image_topic": LaunchConfiguration("image_topic"),
                "camera_info_topic": LaunchConfiguration("camera_info_topic"),
                "output_dir": LaunchConfiguration("output_dir"),
                "sample_prefix": LaunchConfiguration("sample_prefix"),
                "robot_name": robot_name,
                "arm": arm,
                "robot_base_frame": LaunchConfiguration("robot_base_frame"),
                "robot_tcp_frame": LaunchConfiguration("robot_tcp_frame"),
                "planning_frame": LaunchConfiguration("planning_frame"),
                "action_name": LaunchConfiguration("action_name"),
                "move_enabled": LaunchConfiguration("move_enabled"),
                "gui_enabled": LaunchConfiguration("gui_enabled"),
                "keyboard_jog_enabled": LaunchConfiguration("keyboard_jog_enabled"),
                "jog_twist_topic": LaunchConfiguration("jog_twist_topic"),
                "jog_linear_velocity": LaunchConfiguration("jog_linear_velocity"),
                "jog_angular_velocity": LaunchConfiguration("jog_angular_velocity"),
                "jog_linear_acceleration": LaunchConfiguration("jog_linear_acceleration"),
                "jog_angular_acceleration": LaunchConfiguration("jog_angular_acceleration"),
                "jog_hold_timeout": LaunchConfiguration("jog_hold_timeout"),
                "log_key_codes": LaunchConfiguration("log_key_codes"),
                "display_max_side": LaunchConfiguration("display_max_side"),
                "draw_rejected_markers": LaunchConfiguration("draw_rejected_markers"),
                "samples": LaunchConfiguration("samples"),
                "sphere_radius_m": LaunchConfiguration("sphere_radius_m"),
                "sphere_yaw_span_deg": LaunchConfiguration("sphere_yaw_span_deg"),
                "sphere_pitch_span_deg": LaunchConfiguration("sphere_pitch_span_deg"),
                "max_linear_velocity": LaunchConfiguration("max_linear_velocity"),
                "max_angular_velocity": LaunchConfiguration("max_angular_velocity"),
                "move_timeout": LaunchConfiguration("move_timeout"),
                "handeye_method": LaunchConfiguration("handeye_method"),
                "squares_x": LaunchConfiguration("squares_x"),
                "squares_y": LaunchConfiguration("squares_y"),
                "square_length_m": LaunchConfiguration("square_length_m"),
                "marker_length_m": LaunchConfiguration("marker_length_m"),
                "dictionary": LaunchConfiguration("dictionary"),
                "min_charuco_corners": LaunchConfiguration("min_charuco_corners"),
                "coarse_max_side": LaunchConfiguration("coarse_max_side"),
                "refine_max_side": LaunchConfiguration("refine_max_side"),
            }
        ],
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_name", default_value="mur620"),
            DeclareLaunchArgument("arm", default_value="r"),
            DeclareLaunchArgument("launch_camera", default_value="true"),
            DeclareLaunchArgument("camera_launch_file", default_value="oak4_pro_af_4k.launch.py"),
            DeclareLaunchArgument("camera_parent_frame", default_value="mur620/UR10_r/tool0"),
            DeclareLaunchArgument("image_topic", default_value="/oak/rgb/image_raw"),
            DeclareLaunchArgument("camera_info_topic", default_value="/oak/rgb/camera_info"),
            DeclareLaunchArgument("output_dir", default_value="~/oak_charuco_handeye_samples"),
            DeclareLaunchArgument("sample_prefix", default_value="sample"),
            DeclareLaunchArgument("robot_base_frame", default_value="mur620/UR10_r/base_link"),
            DeclareLaunchArgument("robot_tcp_frame", default_value="mur620/UR10_r/tool0"),
            DeclareLaunchArgument("planning_frame", default_value="mur620/UR10_r/base_link"),
            DeclareLaunchArgument("action_name", default_value="/mur620/jparse_move_r"),
            DeclareLaunchArgument("move_enabled", default_value="false"),
            DeclareLaunchArgument("gui_enabled", default_value="true"),
            DeclareLaunchArgument("keyboard_jog_enabled", default_value="true"),
            DeclareLaunchArgument(
                "jog_twist_topic",
                default_value="/mur620/jparse_velocity_controller_r/twist_cmd",
            ),
            DeclareLaunchArgument("jog_linear_velocity", default_value="0.03"),
            DeclareLaunchArgument("jog_angular_velocity", default_value="0.25"),
            DeclareLaunchArgument("jog_linear_acceleration", default_value="0.12"),
            DeclareLaunchArgument("jog_angular_acceleration", default_value="1.0"),
            DeclareLaunchArgument("jog_hold_timeout", default_value="1.0"),
            DeclareLaunchArgument("log_key_codes", default_value="true"),
            DeclareLaunchArgument("display_max_side", default_value="1600"),
            DeclareLaunchArgument("draw_rejected_markers", default_value="true"),
            DeclareLaunchArgument("samples", default_value="12"),
            DeclareLaunchArgument("sphere_radius_m", default_value="0.0"),
            DeclareLaunchArgument("sphere_yaw_span_deg", default_value="50.0"),
            DeclareLaunchArgument("sphere_pitch_span_deg", default_value="35.0"),
            DeclareLaunchArgument("max_linear_velocity", default_value="0.06"),
            DeclareLaunchArgument("max_angular_velocity", default_value="0.25"),
            DeclareLaunchArgument("move_timeout", default_value="30.0"),
            DeclareLaunchArgument("handeye_method", default_value="tsai"),
            DeclareLaunchArgument("squares_x", default_value="14"),
            DeclareLaunchArgument("squares_y", default_value="9"),
            DeclareLaunchArgument("square_length_m", default_value="0.065"),
            DeclareLaunchArgument("marker_length_m", default_value="0.048"),
            DeclareLaunchArgument("dictionary", default_value="DICT_4X4_250"),
            DeclareLaunchArgument("min_charuco_corners", default_value="8"),
            DeclareLaunchArgument("coarse_max_side", default_value="1600"),
            DeclareLaunchArgument("refine_max_side", default_value="2200"),
            camera_driver,
            handeye_session,
        ]
    )
