"""OAK camera extension module for the shared MuR GUI."""

import json
import os
import shlex
import threading
import time

import cv2
from cv_bridge import CvBridge
from PyQt5 import QtCore, QtGui, QtWidgets

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image

from match_mur_gui.base_gui import MurGuiModule, WS, setup_prefix


OAK_NODE = "/oak"
OAK_RGB_PREFIX = "rgb"
DEFAULT_COMPRESSED_TOPIC = "/oak/rgb/image_raw/compressed"
DEFAULT_RAW_TOPIC = "/oak/rgb/image_raw"
DEFAULT_OUTPUT_DIR = os.path.join(WS, "src", "oak_camera_calibration", "logs", "snapshots")
OAK_LOG_DIR = os.path.join(WS, "src", "oak_camera_calibration", "logs")
OAK_SETTINGS_FILE = os.path.join(OAK_LOG_DIR, "oak_gui_settings.json")
OAK_GENERATED_PARAMS_FILE = os.path.join(OAK_LOG_DIR, "oak_gui_driver_params.yaml")

OAK_RESOLUTION_PRESETS = [
    ("1280 x 720 @ 15 Hz", 1280, 720, 15.0),
    ("1920 x 1080 @ 15 Hz", 1920, 1080, 15.0),
    ("3840 x 2160 @ 5 Hz", 3840, 2160, 5.0),
    ("8000 x 6000 @ 5 Hz", 8000, 6000, 5.0),
    ("Custom", None, None, None),
]
OAK_RGBD_MAX_WIDTH = 1920
OAK_RGBD_MAX_HEIGHT = 1080
OAK_RGBD_MAX_FPS = 15.0

DEFAULT_OAK_SETTINGS = {
    "profile": "rgb",
    "width": 1920,
    "height": 1080,
    "fps": 15.0,
    "compressed": True,
    "low_bandwidth": True,
    "quality": 75,
    "parent_frame": "mur620d/UR10_r/tool0",
}


class OakLiveViewBridge(QtCore.QThread):
    frame = QtCore.pyqtSignal(QtGui.QImage, str)
    status = QtCore.pyqtSignal(str)

    def __init__(self, topic=DEFAULT_COMPRESSED_TOPIC, compressed=True, max_side=960):
        super().__init__()
        self.topic = topic
        self.compressed = compressed
        self.max_side = int(max_side)
        self._node = None
        self._subscription = None
        self._stop = threading.Event()
        self._bridge = CvBridge()
        self._owns_rclpy = False
        self._last_status = 0.0

    def configure(self, topic, compressed, max_side):
        self.topic = topic
        self.compressed = compressed
        self.max_side = int(max_side)

    def shutdown(self):
        self._stop.set()

    def run(self):
        deadline = time.monotonic() + 2.0
        while not rclpy.ok() and time.monotonic() < deadline:
            self.msleep(20)
        if not rclpy.ok():
            rclpy.init(args=None)
            self._owns_rclpy = True

        self._node = rclpy.create_node("oak_gui_live_view")
        qos = QoSProfile(depth=1)
        qos.reliability = ReliabilityPolicy.BEST_EFFORT
        msg_type = CompressedImage if self.compressed else Image
        self._subscription = self._node.create_subscription(
            msg_type,
            self.topic,
            self._on_frame,
            qos,
        )
        self.status.emit(f"[oak] live view subscribed to {self.topic}")
        try:
            while rclpy.ok() and not self._stop.is_set():
                rclpy.spin_once(self._node, timeout_sec=0.05)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            if self._node is not None:
                if self._subscription is not None:
                    self._node.destroy_subscription(self._subscription)
                self._node.destroy_node()
                self._node = None
            if self._owns_rclpy and rclpy.ok():
                rclpy.shutdown()

    def _on_frame(self, msg):
        try:
            if self.compressed:
                image = self._bridge.compressed_imgmsg_to_cv2(msg, desired_encoding="bgr8")
            else:
                image = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:  # noqa: BLE001
            now = time.monotonic()
            if now - self._last_status > 2.0:
                self.status.emit(f"[oak] failed to decode frame from {self.topic}: {exc}")
                self._last_status = now
            return

        height, width = image.shape[:2]
        scale = min(1.0, float(self.max_side) / max(width, height))
        if scale < 1.0:
            image = cv2.resize(
                image,
                (int(width * scale), int(height * scale)),
                interpolation=cv2.INTER_AREA,
            )
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        qimage = QtGui.QImage(
            rgb.data,
            rgb.shape[1],
            rgb.shape[0],
            rgb.strides[0],
            QtGui.QImage.Format_RGB888,
        ).copy()
        stamp = msg.header.stamp
        label = f"{self.topic}  {width}x{height}  t={stamp.sec}.{stamp.nanosec:09d}"
        self.frame.emit(qimage, label)


class OakSettingsDialog(QtWidgets.QDialog):
    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self.setWindowTitle("OAK Settings")
        self.setMinimumWidth(520)

        layout = QtWidgets.QVBoxLayout(self)

        driver_box = QtWidgets.QGroupBox("Driver")
        form = QtWidgets.QFormLayout(driver_box)
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItem("RGB preview", "rgb")
        self.profile_combo.addItem("RGBD + PointCloud", "rgbd")
        self.resolution_combo = QtWidgets.QComboBox()
        for label, width, height, fps in OAK_RESOLUTION_PRESETS:
            self.resolution_combo.addItem(label, (width, height, fps))
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(320, 8000)
        self.width_spin.setSingleStep(160)
        self.height_spin = QtWidgets.QSpinBox()
        self.height_spin.setRange(240, 6000)
        self.height_spin.setSingleStep(120)
        self.fps_spin = QtWidgets.QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 60.0)
        self.fps_spin.setSingleStep(1.0)
        self.fps_spin.setDecimals(1)
        self.compressed_check = QtWidgets.QCheckBox("Publish compressed RGB")
        self.low_bandwidth_check = QtWidgets.QCheckBox("Low bandwidth")
        self.quality_spin = QtWidgets.QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setSingleStep(5)
        self.parent_frame_edit = QtWidgets.QLineEdit()

        size_row = QtWidgets.QWidget()
        size_layout = QtWidgets.QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(self.width_spin)
        size_layout.addWidget(QtWidgets.QLabel("x"))
        size_layout.addWidget(self.height_spin)
        size_layout.addWidget(QtWidgets.QLabel("@"))
        size_layout.addWidget(self.fps_spin)
        size_layout.addWidget(QtWidgets.QLabel("Hz"))

        transport_row = QtWidgets.QWidget()
        transport_layout = QtWidgets.QHBoxLayout(transport_row)
        transport_layout.setContentsMargins(0, 0, 0, 0)
        transport_layout.addWidget(self.compressed_check)
        transport_layout.addWidget(self.low_bandwidth_check)
        transport_layout.addWidget(QtWidgets.QLabel("Quality"))
        transport_layout.addWidget(self.quality_spin)
        transport_layout.addStretch(1)

        form.addRow("Mode", self.profile_combo)
        form.addRow("Preset", self.resolution_combo)
        form.addRow("RGB stream", size_row)
        form.addRow("Transport", transport_row)
        form.addRow("Parent frame", self.parent_frame_edit)
        layout.addWidget(driver_box)

        hint = QtWidgets.QLabel(
            "RGBD starts the stereo/depth pipeline and publishes /oak/rgbd/points. "
            "RGBD is limited to 1920x1080 here because higher RGB resolutions can "
            "make the DepthAI component unstable with pointcloud enabled."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("QLabel { color: #4a5568; }")
        layout.addWidget(hint)

        actions = QtWidgets.QHBoxLayout()
        apply_once = QtWidgets.QPushButton("Apply Once")
        apply_once.clicked.connect(self.apply_once)
        save_default = QtWidgets.QPushButton("Save Default")
        save_default.clicked.connect(self.save_default)
        start_now = QtWidgets.QPushButton("Start OAK")
        start_now.clicked.connect(self.start_now)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        actions.addWidget(apply_once)
        actions.addWidget(save_default)
        actions.addWidget(start_now)
        actions.addStretch(1)
        actions.addWidget(close)
        layout.addLayout(actions)

        self.resolution_combo.currentIndexChanged.connect(self.on_preset_changed)
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        self.compressed_check.toggled.connect(self.on_transport_changed)
        self.load_from_settings(self.module.current_settings())

    def load_from_settings(self, settings):
        profile = settings.get("profile", DEFAULT_OAK_SETTINGS["profile"])
        index = self.profile_combo.findData(profile)
        self.profile_combo.setCurrentIndex(max(0, index))
        self.width_spin.setValue(int(settings.get("width", DEFAULT_OAK_SETTINGS["width"])))
        self.height_spin.setValue(int(settings.get("height", DEFAULT_OAK_SETTINGS["height"])))
        self.fps_spin.setValue(float(settings.get("fps", DEFAULT_OAK_SETTINGS["fps"])))
        self.compressed_check.setChecked(bool(settings.get("compressed", DEFAULT_OAK_SETTINGS["compressed"])))
        self.low_bandwidth_check.setChecked(bool(settings.get("low_bandwidth", DEFAULT_OAK_SETTINGS["low_bandwidth"])))
        self.quality_spin.setValue(int(settings.get("quality", DEFAULT_OAK_SETTINGS["quality"])))
        self.parent_frame_edit.setText(str(settings.get("parent_frame", DEFAULT_OAK_SETTINGS["parent_frame"])))
        self.sync_preset_to_values()
        self.on_transport_changed()

    def sync_preset_to_values(self):
        current = (self.width_spin.value(), self.height_spin.value(), float(self.fps_spin.value()))
        custom_index = self.resolution_combo.count() - 1
        for index in range(self.resolution_combo.count()):
            width, height, fps = self.resolution_combo.itemData(index)
            if width is None:
                continue
            if (int(width), int(height), float(fps)) == current:
                self.resolution_combo.blockSignals(True)
                self.resolution_combo.setCurrentIndex(index)
                self.resolution_combo.blockSignals(False)
                return
        self.resolution_combo.blockSignals(True)
        self.resolution_combo.setCurrentIndex(custom_index)
        self.resolution_combo.blockSignals(False)

    def on_preset_changed(self, _index):
        width, height, fps = self.resolution_combo.currentData()
        if width is None:
            return
        self.width_spin.setValue(int(width))
        self.height_spin.setValue(int(height))
        self.fps_spin.setValue(float(fps))
        self.clamp_rgbd_values()

    def on_profile_changed(self, _index):
        self.clamp_rgbd_values()
        self.sync_preset_to_values()

    def clamp_rgbd_values(self):
        if self.profile_combo.currentData() != "rgbd":
            return
        changed = False
        if self.width_spin.value() > OAK_RGBD_MAX_WIDTH:
            self.width_spin.setValue(OAK_RGBD_MAX_WIDTH)
            changed = True
        if self.height_spin.value() > OAK_RGBD_MAX_HEIGHT:
            self.height_spin.setValue(OAK_RGBD_MAX_HEIGHT)
            changed = True
        if self.fps_spin.value() > OAK_RGBD_MAX_FPS:
            self.fps_spin.setValue(OAK_RGBD_MAX_FPS)
            changed = True
        if changed and self.module.context is not None:
            self.module.context.append_log(
                "[oak] RGBD + PointCloud limited to 1920x1080@15Hz for driver stability"
            )

    def on_transport_changed(self):
        enabled = self.compressed_check.isChecked()
        self.quality_spin.setEnabled(enabled)

    def settings(self):
        return {
            "profile": self.profile_combo.currentData(),
            "width": int(self.width_spin.value()),
            "height": int(self.height_spin.value()),
            "fps": float(self.fps_spin.value()),
            "compressed": bool(self.compressed_check.isChecked()),
            "low_bandwidth": bool(self.low_bandwidth_check.isChecked()),
            "quality": int(self.quality_spin.value()),
            "parent_frame": self.parent_frame_edit.text().strip() or DEFAULT_OAK_SETTINGS["parent_frame"],
        }

    def apply_once(self):
        self.module.apply_settings(self.settings(), persist=False)

    def save_default(self):
        self.module.apply_settings(self.settings(), persist=True)

    def start_now(self):
        self.module.apply_settings(self.settings(), persist=False)
        self.module.start_driver()


class OakControlDialog(QtWidgets.QDialog):
    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self.setWindowTitle("OAK4-D Camera")
        self.setMinimumSize(760, 620)

        layout = QtWidgets.QVBoxLayout(self)

        stream_box = QtWidgets.QGroupBox("Live View")
        stream_layout = QtWidgets.QGridLayout(stream_box)
        self.compressed_check = QtWidgets.QCheckBox("compressed")
        self.compressed_check.setChecked(True)
        self.topic_edit = QtWidgets.QLineEdit(DEFAULT_COMPRESSED_TOPIC)
        self.max_side = QtWidgets.QSpinBox()
        self.max_side.setRange(240, 2160)
        self.max_side.setSingleStep(120)
        self.max_side.setValue(960)
        self.image_label = QtWidgets.QLabel("no frame")
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_label.setMinimumSize(640, 360)
        self.image_label.setStyleSheet("QLabel { background: #111827; color: #e5e7eb; }")
        self.frame_info = QtWidgets.QLabel("idle")
        self.frame_info.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        self.compressed_check.toggled.connect(self._sync_topic_for_transport)
        start_live = QtWidgets.QPushButton("Start Live")
        start_live.clicked.connect(self.start_live)
        stop_live = QtWidgets.QPushButton("Stop Live")
        stop_live.clicked.connect(self.module.stop_live_view)
        stream_layout.addWidget(QtWidgets.QLabel("Topic"), 0, 0)
        stream_layout.addWidget(self.topic_edit, 0, 1, 1, 3)
        stream_layout.addWidget(self.compressed_check, 0, 4)
        stream_layout.addWidget(QtWidgets.QLabel("Max side"), 1, 0)
        stream_layout.addWidget(self.max_side, 1, 1)
        stream_layout.addWidget(start_live, 1, 3)
        stream_layout.addWidget(stop_live, 1, 4)
        stream_layout.addWidget(self.image_label, 2, 0, 1, 5)
        stream_layout.addWidget(self.frame_info, 3, 0, 1, 5)
        layout.addWidget(stream_box, 1)

        params_box = QtWidgets.QGroupBox("Camera Controls")
        params_layout = QtWidgets.QGridLayout(params_box)

        self.focus = QtWidgets.QSpinBox()
        self.focus.setRange(0, 255)
        self.focus.setValue(120)
        focus_button = QtWidgets.QPushButton("Manual Focus")
        focus_button.clicked.connect(lambda: self.module.set_manual_focus(self.focus.value()))
        auto_focus = QtWidgets.QPushButton("Auto Focus")
        auto_focus.clicked.connect(self.module.set_auto_focus)

        self.exposure = QtWidgets.QSpinBox()
        self.exposure.setRange(1, 33000)
        self.exposure.setSingleStep(500)
        self.exposure.setValue(8000)
        self.iso = QtWidgets.QSpinBox()
        self.iso.setRange(100, 1600)
        self.iso.setSingleStep(50)
        self.iso.setValue(400)
        exposure_button = QtWidgets.QPushButton("Manual Exposure")
        exposure_button.clicked.connect(
            lambda: self.module.set_manual_exposure(self.exposure.value(), self.iso.value())
        )
        auto_exposure = QtWidgets.QPushButton("Auto Exposure")
        auto_exposure.clicked.connect(self.module.set_auto_exposure)

        self.white_balance = QtWidgets.QSpinBox()
        self.white_balance.setRange(1000, 12000)
        self.white_balance.setSingleStep(100)
        self.white_balance.setValue(4500)
        wb_button = QtWidgets.QPushButton("Manual WB")
        wb_button.clicked.connect(
            lambda: self.module.set_manual_white_balance(self.white_balance.value())
        )
        auto_wb = QtWidgets.QPushButton("Auto WB")
        auto_wb.clicked.connect(self.module.set_auto_white_balance)

        self.sharpness = QtWidgets.QSpinBox()
        self.sharpness.setRange(0, 4)
        self.sharpness.setValue(1)
        sharpness_button = QtWidgets.QPushButton("Set Sharpness")
        sharpness_button.clicked.connect(lambda: self.module.set_sharpness(self.sharpness.value()))

        params_layout.addWidget(QtWidgets.QLabel("Focus"), 0, 0)
        params_layout.addWidget(self.focus, 0, 1)
        params_layout.addWidget(focus_button, 0, 2)
        params_layout.addWidget(auto_focus, 0, 3)
        params_layout.addWidget(QtWidgets.QLabel("Exposure us / ISO"), 1, 0)
        params_layout.addWidget(self.exposure, 1, 1)
        params_layout.addWidget(self.iso, 1, 2)
        params_layout.addWidget(exposure_button, 1, 3)
        params_layout.addWidget(auto_exposure, 1, 4)
        params_layout.addWidget(QtWidgets.QLabel("White balance K"), 2, 0)
        params_layout.addWidget(self.white_balance, 2, 1)
        params_layout.addWidget(wb_button, 2, 2)
        params_layout.addWidget(auto_wb, 2, 3)
        params_layout.addWidget(QtWidgets.QLabel("Sharpness"), 3, 0)
        params_layout.addWidget(self.sharpness, 3, 1)
        params_layout.addWidget(sharpness_button, 3, 2)
        layout.addWidget(params_box)

        actions = QtWidgets.QHBoxLayout()
        snapshot = QtWidgets.QPushButton("Snapshot")
        snapshot.clicked.connect(self.module.capture_snapshot)
        sample = QtWidgets.QPushButton("Sample GUI")
        sample.clicked.connect(self.module.open_sample_gui)
        settings = QtWidgets.QPushButton("Settings")
        settings.clicked.connect(self.module.open_settings)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        actions.addWidget(snapshot)
        actions.addWidget(sample)
        actions.addWidget(settings)
        actions.addStretch(1)
        actions.addWidget(close)
        layout.addLayout(actions)

    def _sync_topic_for_transport(self, compressed):
        current = self.topic_edit.text().strip()
        if compressed and current == DEFAULT_RAW_TOPIC:
            self.topic_edit.setText(DEFAULT_COMPRESSED_TOPIC)
        elif not compressed and current == DEFAULT_COMPRESSED_TOPIC:
            self.topic_edit.setText(DEFAULT_RAW_TOPIC)

    def start_live(self):
        self.module.start_live_view(
            self.topic_edit.text().strip(),
            self.compressed_check.isChecked(),
            self.max_side.value(),
        )

    def update_frame(self, qimage, text):
        pixmap = QtGui.QPixmap.fromImage(qimage)
        available = self.image_label.size()
        if available.width() > 8 and available.height() > 8:
            pixmap = pixmap.scaled(
                available,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        self.image_label.setPixmap(pixmap)
        self.frame_info.setText(text)

    def closeEvent(self, event):
        self.module.stop_live_view()
        super().closeEvent(event)


class OakCameraModule(MurGuiModule):
    def __init__(self):
        self.context = None
        self._control_dialog = None
        self._settings_dialog = None
        self._live_bridge = None
        self._oak_settings = dict(DEFAULT_OAK_SETTINGS)
        self._last_topic = DEFAULT_COMPRESSED_TOPIC
        self._last_compressed = True
        self._last_max_side = 960

    def setup_ui(self, context):
        self.context = context
        self._oak_settings = self.load_settings()
        self._apply_live_defaults_from_settings(self._oak_settings)
        context.add_action_button("Start OAK", self.start_driver, section="OAK")
        context.add_action_button("Stop OAK", self.stop_driver, section="OAK")
        context.add_action_button("OAK Settings", self.open_settings, section="OAK")
        context.add_action_button("OAK Live", self.open_controls, section="OAK")
        context.add_tool_button("OAK Snapshot", self.capture_snapshot, section="OAK")
        context.add_tool_button("OAK Sample GUI", self.open_sample_gui, section="OAK")
        self.status_label = QtWidgets.QLabel("idle")
        self.status_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        context.add_status_row("OAK", self.status_label)
        context.append_log("[gui] OAK camera module loaded.")

    def load_settings(self):
        settings = dict(DEFAULT_OAK_SETTINGS)
        try:
            with open(OAK_SETTINGS_FILE, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                settings.update(stored)
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError) as exc:
            if self.context is not None:
                self.context.append_log(f"[oak] failed to read settings: {exc}")
        return self.normalize_settings(settings)

    def save_settings(self, settings):
        os.makedirs(OAK_LOG_DIR, exist_ok=True)
        with open(OAK_SETTINGS_FILE, "w", encoding="utf-8") as handle:
            json.dump(self.normalize_settings(settings), handle, indent=2, sort_keys=True)
            handle.write("\n")

    def normalize_settings(self, settings):
        merged = dict(DEFAULT_OAK_SETTINGS)
        merged.update(settings or {})
        merged["profile"] = "rgbd" if str(merged.get("profile")).lower() == "rgbd" else "rgb"
        merged["width"] = max(320, min(8000, int(merged.get("width", DEFAULT_OAK_SETTINGS["width"]))))
        merged["height"] = max(240, min(6000, int(merged.get("height", DEFAULT_OAK_SETTINGS["height"]))))
        merged["fps"] = max(1.0, min(60.0, float(merged.get("fps", DEFAULT_OAK_SETTINGS["fps"]))))
        if merged["profile"] == "rgbd":
            merged["width"] = min(merged["width"], OAK_RGBD_MAX_WIDTH)
            merged["height"] = min(merged["height"], OAK_RGBD_MAX_HEIGHT)
            merged["fps"] = min(merged["fps"], OAK_RGBD_MAX_FPS)
        merged["compressed"] = bool(merged.get("compressed", DEFAULT_OAK_SETTINGS["compressed"]))
        merged["low_bandwidth"] = bool(merged.get("low_bandwidth", DEFAULT_OAK_SETTINGS["low_bandwidth"]))
        merged["quality"] = max(1, min(100, int(merged.get("quality", DEFAULT_OAK_SETTINGS["quality"]))))
        merged["parent_frame"] = str(merged.get("parent_frame") or DEFAULT_OAK_SETTINGS["parent_frame"])
        return merged

    def current_settings(self):
        return self.normalize_settings(self._oak_settings)

    def apply_settings(self, settings, persist=False):
        self._oak_settings = self.normalize_settings(settings)
        self._apply_live_defaults_from_settings(self._oak_settings)
        if persist:
            self.save_settings(self._oak_settings)
            self.context.append_log(f"[gui] OAK settings saved to {OAK_SETTINGS_FILE}")
        else:
            self.context.append_log("[gui] OAK settings applied for this session")
        self._set_status(self._settings_summary(self._oak_settings))

    def _apply_live_defaults_from_settings(self, settings):
        compressed = bool(settings.get("compressed", True))
        self._last_compressed = compressed
        self._last_topic = DEFAULT_COMPRESSED_TOPIC if compressed else DEFAULT_RAW_TOPIC
        if self._control_dialog is not None:
            self._control_dialog.compressed_check.setChecked(compressed)
            self._control_dialog.topic_edit.setText(self._last_topic)

    def _settings_summary(self, settings):
        mode = "RGBD + PointCloud" if settings["profile"] == "rgbd" else "RGB"
        transport = "compressed" if settings["compressed"] else "raw"
        return (
            f"[oak] profile={mode}, rgb={settings['width']}x{settings['height']}@"
            f"{settings['fps']:.1f}Hz, {transport}"
        )

    def _write_driver_params(self, settings):
        settings = self.normalize_settings(settings)
        os.makedirs(OAK_LOG_DIR, exist_ok=True)
        rgbd = settings["profile"] == "rgbd"
        low_bandwidth = bool(settings["low_bandwidth"])
        compressed = bool(settings["compressed"])
        lines = [
            "/oak:",
            "  ros__parameters:",
            "    driver:",
            "      i_enable_ir: false",
            "      i_pipeline_auto_calibration_mode: ''",
            "    pipeline_gen:",
            "      i_enable_imu: false",
            f"      i_enable_rgbd: {'true' if rgbd else 'false'}",
            "      i_nn_type: none",
            f"      i_pipeline_type: {'rgbd' if rgbd else 'rgb'}",
            "    rgb:",
            "      i_board_socket_id: 0",
            "      i_disable_node: false",
            "      i_enable_feature_tracker: false",
            "      i_enable_lazy_publisher: false",
            "      i_enable_nn: false",
            f"      i_fps: {settings['fps']:.1f}",
            f"      i_height: {settings['height']}",
            f"      i_low_bandwidth: {'true' if low_bandwidth else 'false'}",
            f"      i_low_bandwidth_quality: {settings['quality']}",
            "      i_max_q_size: 2",
            f"      i_publish_compressed: {'true' if compressed else 'false'}",
            "      i_publish_raw: false",
            "      i_publish_topic: true",
            f"      i_undistorted: {'true' if rgbd else 'false'}",
            f"      i_width: {settings['width']}",
        ]
        if rgbd:
            lines.extend(
                [
                    "    stereo:",
                    "      i_depth_preset: DEFAULT",
                    "      i_publish_topic: true",
                ]
            )
        with open(OAK_GENERATED_PARAMS_FILE, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return OAK_GENERATED_PARAMS_FILE

    def _run_local(self, name, command, on_finished=None, env=None):
        self.context.start_process(
            name,
            setup_prefix() + command,
            env=env,
            on_finished=on_finished,
        )

    def _param_command(self, assignments):
        commands = []
        for name, value in assignments:
            if isinstance(value, bool):
                value_text = "true" if value else "false"
            else:
                value_text = str(value)
            commands.append(
                "ros2 param set "
                + shlex.quote(OAK_NODE)
                + " "
                + shlex.quote(f"{OAK_RGB_PREFIX}.{name}")
                + " "
                + shlex.quote(value_text)
            )
        return " && ".join(commands)

    def _set_params(self, label, assignments):
        command = self._param_command(assignments)
        self.context.append_log(f"[gui] OAK {label}: setting runtime parameters")
        self._run_local(f"oak_param_{label}", command)

    def start_driver(self):
        settings = self.current_settings()
        params_file = self._write_driver_params(settings)
        pointcloud_enable = "true" if settings["profile"] == "rgbd" else "false"
        command = (
            "exec ros2 launch oak_camera_calibration oak4_pro_af_gui.launch.py "
            + f"params_file:={shlex.quote(params_file)} "
            + f"parent_frame:={shlex.quote(settings['parent_frame'])} "
            + f"pointcloud_enable:={pointcloud_enable}"
        )
        self.context.append_log(f"[gui] Starting OAK4-D driver: {self._settings_summary(settings)}")
        self._run_local(
            "oak_driver",
            command,
            env={"FASTDDS_BUILTIN_TRANSPORTS": "UDPv4"},
        )

    def stop_driver(self):
        self.stop_live_view()
        process = self.context.window.processes.get("oak_driver")
        if process is not None and process.state() != QtCore.QProcess.NotRunning:
            self.context.append_log("[gui] stopping OAK driver")
            process.terminate()
            if not process.waitForFinished(2000):
                process.kill()
            return
        self.context.append_log("[gui] OAK driver was not started by this GUI")

    def open_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = OakSettingsDialog(self, self.context.window)
        else:
            self._settings_dialog.load_from_settings(self.current_settings())
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def open_controls(self):
        if self._control_dialog is None:
            self._control_dialog = OakControlDialog(self, self.context.window)
        self._control_dialog.show()
        self._control_dialog.raise_()
        self._control_dialog.activateWindow()
        if self._live_bridge is None:
            self.start_live_view(
                self._control_dialog.topic_edit.text().strip(),
                self._control_dialog.compressed_check.isChecked(),
                self._control_dialog.max_side.value(),
            )

    def start_live_view(self, topic=None, compressed=None, max_side=None):
        self.stop_live_view()
        self._set_status("starting live view...")
        self._last_topic = topic or self._last_topic
        self._last_compressed = self._last_compressed if compressed is None else bool(compressed)
        self._last_max_side = int(max_side or self._last_max_side)
        self._live_bridge = OakLiveViewBridge(
            topic=self._last_topic,
            compressed=self._last_compressed,
            max_side=self._last_max_side,
        )
        self._live_bridge.status.connect(self._set_status)
        self._live_bridge.frame.connect(self._on_frame)
        self._live_bridge.start()

    def stop_live_view(self):
        if self._live_bridge is None:
            return
        self._live_bridge.shutdown()
        self._live_bridge.wait(1500)
        self._live_bridge = None
        self._set_status("live view stopped")

    def _on_frame(self, qimage, text):
        if hasattr(self, "status_label"):
            self.status_label.setText(text)
        if self._control_dialog is not None:
            self._control_dialog.update_frame(qimage, text)

    def _set_status(self, text):
        if hasattr(self, "status_label"):
            self.status_label.setText(text)
        self.context.append_log(text if text.startswith("[oak]") else f"[oak] {text}")

    def capture_snapshot(self):
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        command = (
            "exec ros2 run oak_camera_calibration capture_oak_snapshot --ros-args "
            + f"-p image_topic:={DEFAULT_COMPRESSED_TOPIC} "
            + "-p image_compressed:=true "
            + "-p camera_info_topic:=/oak/rgb/camera_info "
            + f"-p output_dir:={shlex.quote(DEFAULT_OUTPUT_DIR)} "
            + "-p prefix:=oak_gui"
        )
        self.context.append_log(f"[gui] Capturing OAK snapshot to {DEFAULT_OUTPUT_DIR}")
        self._run_local("oak_snapshot", command)

    def open_sample_gui(self):
        output_dir = os.path.join(WS, "src", "oak_camera_calibration", "logs", "samples")
        os.makedirs(output_dir, exist_ok=True)
        command = (
            "exec ros2 run oak_camera_calibration oak_sample_gui --ros-args "
            + f"-p image_topic:={DEFAULT_RAW_TOPIC} "
            + "-p camera_info_topic:=/oak/rgb/camera_info "
            + f"-p output_dir:={shlex.quote(output_dir)}"
        )
        self.context.append_log(f"[gui] Opening OAK sample GUI with output {output_dir}")
        self._run_local("oak_sample_gui", command)

    def set_manual_focus(self, focus):
        self._set_params("focus", [("r_set_man_focus", True), ("r_focus", int(focus))])

    def set_auto_focus(self):
        self._set_params("autofocus", [("r_set_man_focus", False)])

    def set_manual_exposure(self, exposure_us, iso):
        self._set_params(
            "exposure",
            [
                ("r_set_man_exposure", True),
                ("r_exposure", int(exposure_us)),
                ("r_iso", int(iso)),
            ],
        )

    def set_auto_exposure(self):
        self._set_params("auto_exposure", [("r_set_man_exposure", False)])

    def set_manual_white_balance(self, white_balance):
        self._set_params(
            "white_balance",
            [
                ("r_set_man_whitebalance", True),
                ("r_whitebalance", int(white_balance)),
            ],
        )

    def set_auto_white_balance(self):
        self._set_params("auto_white_balance", [("r_set_man_whitebalance", False)])

    def set_sharpness(self, sharpness):
        self._set_params(
            "sharpness",
            [
                ("r_set_sharpness", True),
                ("r_sharpness", int(sharpness)),
            ],
        )

    def on_shutdown(self):
        self.stop_live_view()
