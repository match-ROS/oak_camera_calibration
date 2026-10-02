#!/usr/bin/env python3
"""Standalone MuR-style GUI with OAK4-D camera controls."""

import signal
import sys

from PyQt5 import QtWidgets

from match_mur_gui.base_gui import MurBaseGui
from match_mur_gui.app_icon import configure_gui_icon
from oak_camera_calibration.oak_gui_module import OakCameraModule


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QtWidgets.QApplication(sys.argv)
    icon = configure_gui_icon(app, "mur-oak-gui")
    window = MurBaseGui(
        modules=[OakCameraModule()],
        window_title="MuR OAK4-D Camera",
    )
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
