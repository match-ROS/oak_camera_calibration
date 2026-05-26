from glob import glob
from setuptools import find_packages, setup

package_name = "oak_camera_calibration"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="rosmatch",
    maintainer_email="rosmatch@example.com",
    description="Tools for OAK hand-eye calibration image capture.",
    license="TODO",
    entry_points={
        "console_scripts": [
            "capture_oak_snapshot = oak_camera_calibration.capture_oak_snapshot:main",
        ],
    },
)
