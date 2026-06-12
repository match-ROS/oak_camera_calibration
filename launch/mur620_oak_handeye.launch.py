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
    camera_cam_pos_x = LaunchConfiguration("camera_cam_pos_x")
    camera_cam_pos_y = LaunchConfiguration("camera_cam_pos_y")
    camera_cam_pos_z = LaunchConfiguration("camera_cam_pos_z")
    camera_cam_roll = LaunchConfiguration("camera_cam_roll")
    camera_cam_pitch = LaunchConfiguration("camera_cam_pitch")
    camera_cam_yaw = LaunchConfiguration("camera_cam_yaw")

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
            "cam_pos_x": camera_cam_pos_x,
            "cam_pos_y": camera_cam_pos_y,
            "cam_pos_z": camera_cam_pos_z,
            "cam_roll": camera_cam_roll,
            "cam_pitch": camera_cam_pitch,
            "cam_yaw": camera_cam_yaw,
        }.items(),
    )

    handeye_session = Node(
        package="oak_camera_calibration",
        executable="semi_auto_handeye_session",
        name="semi_auto_handeye_session",
        output="screen",
        emulate_tty=True,
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
                "jog_frame": LaunchConfiguration("jog_frame"),
                "jog_linear_velocity": LaunchConfiguration("jog_linear_velocity"),
                "jog_angular_velocity": LaunchConfiguration("jog_angular_velocity"),
                "jog_linear_acceleration": LaunchConfiguration("jog_linear_acceleration"),
                "jog_angular_acceleration": LaunchConfiguration("jog_angular_acceleration"),
                "jog_hold_timeout": LaunchConfiguration("jog_hold_timeout"),
                "log_key_codes": LaunchConfiguration("log_key_codes"),
                "display_max_side": LaunchConfiguration("display_max_side"),
                "draw_rejected_markers": LaunchConfiguration("draw_rejected_markers"),
                "draw_board_center_overlay": LaunchConfiguration(
                    "draw_board_center_overlay"
                ),
                "samples": LaunchConfiguration("samples"),
                "sphere_radius_m": LaunchConfiguration("sphere_radius_m"),
                "sphere_yaw_span_deg": LaunchConfiguration("sphere_yaw_span_deg"),
                "sphere_pitch_span_deg": LaunchConfiguration("sphere_pitch_span_deg"),
                "target_pattern": LaunchConfiguration("target_pattern"),
                "hemisphere_axis_source": LaunchConfiguration("hemisphere_axis_source"),
                "sphere_polar_span_deg": LaunchConfiguration("sphere_polar_span_deg"),
                "sphere_spiral_turns": LaunchConfiguration("sphere_spiral_turns"),
                "max_linear_velocity": LaunchConfiguration("max_linear_velocity"),
                "max_angular_velocity": LaunchConfiguration("max_angular_velocity"),
                "move_timeout": LaunchConfiguration("move_timeout"),
                "target_max_tcp_delta_m": LaunchConfiguration("target_max_tcp_delta_m"),
                "target_max_camera_delta_m": LaunchConfiguration("target_max_camera_delta_m"),
                "target_min_camera_delta_m": LaunchConfiguration("target_min_camera_delta_m"),
                "target_max_rotation_deg": LaunchConfiguration("target_max_rotation_deg"),
                "split_target_motion": LaunchConfiguration("split_target_motion"),
                "split_rotation_step_deg": LaunchConfiguration("split_rotation_step_deg"),
                "center_camera_xy_only": LaunchConfiguration("center_camera_xy_only"),
                "use_camera_tf_initial_guess": LaunchConfiguration(
                    "use_camera_tf_initial_guess"
                ),
                "load_session_state": LaunchConfiguration("load_session_state"),
                "require_tcp_camera_estimate_for_targets": LaunchConfiguration(
                    "require_tcp_camera_estimate_for_targets"
                ),
                "camera_look_axis": LaunchConfiguration("camera_look_axis"),
                "camera_roll_reference": LaunchConfiguration("camera_roll_reference"),
                "target_max_camera_z_above_start_m": LaunchConfiguration(
                    "target_max_camera_z_above_start_m"
                ),
                "handeye_method": LaunchConfiguration("handeye_method"),
                "handeye_min_samples": LaunchConfiguration("handeye_min_samples"),
                "handeye_max_residual_translation_m": LaunchConfiguration(
                    "handeye_max_residual_translation_m"
                ),
                "handeye_max_residual_rotation_deg": LaunchConfiguration(
                    "handeye_max_residual_rotation_deg"
                ),
                "handeye_max_tcp_camera_translation_m": LaunchConfiguration(
                    "handeye_max_tcp_camera_translation_m"
                ),
                "squares_x": LaunchConfiguration("squares_x"),
                "squares_y": LaunchConfiguration("squares_y"),
                "square_length_m": LaunchConfiguration("square_length_m"),
                "marker_length_m": LaunchConfiguration("marker_length_m"),
                "dictionary": LaunchConfiguration("dictionary"),
                "board_id_order": LaunchConfiguration("board_id_order"),
                "min_charuco_corners": LaunchConfiguration("min_charuco_corners"),
                "coarse_max_side": LaunchConfiguration("coarse_max_side"),
                "refine_max_side": LaunchConfiguration("refine_max_side"),
            }
        ],
    )

    jog_gui = Node(
        package="oak_camera_calibration",
        executable="robot_jog_gui",
        name="robot_jog_gui",
        output="screen",
        emulate_tty=True,
        condition=IfCondition(LaunchConfiguration("jog_gui_enabled")),
        parameters=[
            {
                "robot_name": robot_name,
                "arm": arm,
                "twist_topic": LaunchConfiguration("jog_twist_topic"),
                "action_name": LaunchConfiguration("action_name"),
                "home_pose_file": LaunchConfiguration("jog_home_pose_file"),
                "home_max_linear_velocity": LaunchConfiguration("jog_home_max_linear_velocity"),
                "home_max_angular_velocity": LaunchConfiguration("jog_home_max_angular_velocity"),
                "home_timeout": LaunchConfiguration("jog_home_timeout"),
                "jog_frame": LaunchConfiguration("jog_frame"),
                "linear_velocity": LaunchConfiguration("jog_linear_velocity"),
                "angular_velocity": LaunchConfiguration("jog_angular_velocity"),
                "linear_acceleration": LaunchConfiguration("jog_linear_acceleration"),
                "angular_acceleration": LaunchConfiguration("jog_angular_acceleration"),
                "hold_timeout": LaunchConfiguration("jog_hold_timeout"),
                "window_name": LaunchConfiguration("jog_gui_window_name"),
                "log_key_codes": LaunchConfiguration("log_key_codes"),
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
            DeclareLaunchArgument("camera_cam_pos_x", default_value="0.0068564203"),
            DeclareLaunchArgument("camera_cam_pos_y", default_value="-0.0892312561"),
            DeclareLaunchArgument("camera_cam_pos_z", default_value="0.1018930213"),
            DeclareLaunchArgument("camera_cam_roll", default_value="-3.0221294847"),
            DeclareLaunchArgument("camera_cam_pitch", default_value="-1.5221462887"),
            DeclareLaunchArgument("camera_cam_yaw", default_value="-1.7026932502"),
            DeclareLaunchArgument("image_topic", default_value="/oak/rgb/image_raw"),
            DeclareLaunchArgument("camera_info_topic", default_value="/oak/rgb/camera_info"),
            DeclareLaunchArgument(
                "output_dir",
                default_value="~/oak_charuco_6x9_column_major_handeye_samples",
            ),
            DeclareLaunchArgument("sample_prefix", default_value="sample"),
            DeclareLaunchArgument("robot_base_frame", default_value="mur620/UR10_r/base_link"),
            DeclareLaunchArgument("robot_tcp_frame", default_value="mur620/UR10_r/tool0"),
            DeclareLaunchArgument("planning_frame", default_value="mur620/UR10_r/base_link"),
            DeclareLaunchArgument("action_name", default_value="/mur620/jparse_move_r"),
            DeclareLaunchArgument("move_enabled", default_value="false"),
            DeclareLaunchArgument("gui_enabled", default_value="true"),
            DeclareLaunchArgument("keyboard_jog_enabled", default_value="false"),
            DeclareLaunchArgument("jog_gui_enabled", default_value="true"),
            DeclareLaunchArgument("jog_gui_window_name", default_value="mur620 robot jog"),
            DeclareLaunchArgument(
                "jog_home_pose_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("oak_camera_calibration"),
                        "config",
                        "mur620_ur10_r_home.yaml",
                    ]
                ),
            ),
            DeclareLaunchArgument("jog_home_max_linear_velocity", default_value="0.025"),
            DeclareLaunchArgument("jog_home_max_angular_velocity", default_value="0.10"),
            DeclareLaunchArgument("jog_home_timeout", default_value="30.0"),
            DeclareLaunchArgument(
                "jog_twist_topic",
                default_value="/mur620/jparse_velocity_controller_r/twist_cmd",
            ),
            DeclareLaunchArgument("jog_frame", default_value="UR10_r/base_link"),
            DeclareLaunchArgument("jog_linear_velocity", default_value="0.03"),
            DeclareLaunchArgument("jog_angular_velocity", default_value="0.25"),
            DeclareLaunchArgument("jog_linear_acceleration", default_value="0.12"),
            DeclareLaunchArgument("jog_angular_acceleration", default_value="1.0"),
            DeclareLaunchArgument("jog_hold_timeout", default_value="1.0"),
            DeclareLaunchArgument("log_key_codes", default_value="true"),
            DeclareLaunchArgument("display_max_side", default_value="1600"),
            DeclareLaunchArgument("draw_rejected_markers", default_value="true"),
            DeclareLaunchArgument("draw_board_center_overlay", default_value="true"),
            DeclareLaunchArgument("samples", default_value="18"),
            DeclareLaunchArgument("sphere_radius_m", default_value="0.0"),
            DeclareLaunchArgument("sphere_yaw_span_deg", default_value="30.0"),
            DeclareLaunchArgument("sphere_pitch_span_deg", default_value="20.0"),
            DeclareLaunchArgument("target_pattern", default_value="spiral_hemisphere"),
            DeclareLaunchArgument("hemisphere_axis_source", default_value="board_normal"),
            DeclareLaunchArgument("sphere_polar_span_deg", default_value="50.0"),
            DeclareLaunchArgument("sphere_spiral_turns", default_value="1.25"),
            DeclareLaunchArgument("max_linear_velocity", default_value="0.025"),
            DeclareLaunchArgument("max_angular_velocity", default_value="0.10"),
            DeclareLaunchArgument("move_timeout", default_value="30.0"),
            DeclareLaunchArgument("target_max_tcp_delta_m", default_value="0.25"),
            DeclareLaunchArgument("target_max_camera_delta_m", default_value="0.30"),
            DeclareLaunchArgument("target_min_camera_delta_m", default_value="0.04"),
            DeclareLaunchArgument("target_max_rotation_deg", default_value="35.0"),
            DeclareLaunchArgument("split_target_motion", default_value="true"),
            DeclareLaunchArgument("split_rotation_step_deg", default_value="25.0"),
            DeclareLaunchArgument("center_camera_xy_only", default_value="true"),
            DeclareLaunchArgument("use_camera_tf_initial_guess", default_value="true"),
            DeclareLaunchArgument("load_session_state", default_value="true"),
            DeclareLaunchArgument("require_tcp_camera_estimate_for_targets", default_value="true"),
            DeclareLaunchArgument("camera_look_axis", default_value="plus_z"),
            DeclareLaunchArgument("camera_roll_reference", default_value="current"),
            DeclareLaunchArgument("target_max_camera_z_above_start_m", default_value="0.01"),
            DeclareLaunchArgument("handeye_method", default_value="tsai"),
            DeclareLaunchArgument("handeye_min_samples", default_value="4"),
            DeclareLaunchArgument("handeye_max_residual_translation_m", default_value="0.05"),
            DeclareLaunchArgument("handeye_max_residual_rotation_deg", default_value="10.0"),
            DeclareLaunchArgument("handeye_max_tcp_camera_translation_m", default_value="0.75"),
            DeclareLaunchArgument("squares_x", default_value="6"),
            DeclareLaunchArgument("squares_y", default_value="9"),
            DeclareLaunchArgument("square_length_m", default_value="0.065"),
            DeclareLaunchArgument("marker_length_m", default_value="0.048"),
            DeclareLaunchArgument("dictionary", default_value="DICT_4X4_250"),
            DeclareLaunchArgument("board_id_order", default_value="column_major"),
            DeclareLaunchArgument("min_charuco_corners", default_value="8"),
            DeclareLaunchArgument("coarse_max_side", default_value="1600"),
            DeclareLaunchArgument("refine_max_side", default_value="2200"),
            camera_driver,
            handeye_session,
            jog_gui,
        ]
    )
