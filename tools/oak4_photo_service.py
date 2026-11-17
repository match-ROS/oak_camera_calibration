#!/usr/bin/env python3
"""Lazy ROS 2 OAK4 photograph service and independent CLI, using an isolated SDK worker."""
import argparse
from datetime import datetime
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import uuid

TOOLS = Path(__file__).resolve().parent
WORKSPACE = TOOLS.parents[2]


class PhotoCapture:
    def __init__(self, workspace=WORKSPACE):
        self.workspace = Path(workspace)
        self.root = self.workspace / 'setup/oak4/photos'
        self.mutex = threading.Lock()
        self.state_mutex = threading.Lock()
        self.state = dict(phase='IDLE', last_result=None)

    def status(self):
        with self.state_mutex:
            return dict(self.state)

    def update(self, **kwargs):
        with self.state_mutex:
            self.state.update(kwargs)

    def capture(self, mode='hq', frames=None, iso=100, focus=None):
        depth = mode.startswith('depth_')
        rgbd = mode == 'rgbd'
        frames = (16 if depth else 8) if frames is None else frames
        modes = ('standard', 'hq', 'compare', 'depth_standard', 'depth_hq', 'depth_compare', 'rgbd')
        if mode not in modes or type(frames) is not int or not (4 if depth else 1) <= frames <= 32 or not 100 <= iso <= 1600:
            raise ValueError('Invalid mode, frames (RGB 1..32, depth 4..32) or ISO (100..1600)')
        if depth and iso != 100:
            raise ValueError('--iso controls RGB only; depth uses locked mono auto-exposure')
        if rgbd and iso != 100:
            raise ValueError('RGB-D uses automatic exposure; --iso is not supported')
        if focus is not None and (type(focus) is not int or not 0 <= focus <= 255 or depth):
            raise ValueError('--focus requires RGB and an integer 0..255')
        if not self.mutex.acquire(blocking=False):
            raise RuntimeError('Another photo transaction is active')
        directory = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            # Cross-process exclusion for CLI and service; never unlink this lock file.
            with (self.root / '.capture.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('Another photo transaction is active (CLI/service)') from None
                live = subprocess.run(['systemctl', '--user', 'is-active', '--quiet',
                                       'uwa-oak4-live.service'], capture_output=True, timeout=5)
                if live.returncode == 0:
                    raise RuntimeError('OAK live view is active; close it before taking a photo')
                import yaml
                inventory = self.workspace / 'src/multi_arm_manipulation_UWA/config/hardware_inventory.yaml'
                camera = yaml.safe_load(inventory.read_text())['cameras']['oak4']
                ip = str(ipaddress.ip_address(camera['ip']))
                sdk = self.workspace / '.venvs/oak4/bin/python'
                oakctl = self.workspace / 'setup/oak4/bin/oakctl'
                for path in (sdk, oakctl):
                    if not os.access(path, os.X_OK):
                        raise RuntimeError(f'Missing runtime {path}; run tools/setup_oak4.sh')
                stamp = datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
                data_root = (self.workspace / 'setup/oak4/rgbd' if rgbd else
                             self.workspace / 'setup/oak4/depth' if depth else self.root)
                data_root.mkdir(parents=True, exist_ok=True)
                directory = data_root / f'{stamp}-{mode}-{uuid.uuid4().hex[:8]}'
                directory.mkdir()
                self.update(phase='CAPTURING', mode=mode, directory=str(directory), error=None)
                worker = ('oak4_rgbd_capture.py' if rgbd else
                          'oak4_depth_capture.py' if depth else 'oak4_photo_capture.py')
                command = [str(oakctl), 'run-script', str(sdk), '-u', str(TOOLS / worker),
                           '--ip', ip, '--device-id', str(camera.get('device_id', '')),
                           '--output', str(directory), '--frames', str(frames)]
                if rgbd:
                    command.extend(['--focus', str(116 if focus is None else focus)])
                else:
                    command.extend(['--mode', mode.removeprefix('depth_')])
                if not depth and not rgbd:
                    command.extend(['--iso', str(iso)])
                    if focus is not None:
                        command.extend(['--focus', str(focus)])
                env = dict(os.environ, DEPTHAI_TELEMETRY='0', OAKCTL_ANALYTICS='0')
                # Keep SDK Python independent of ROS/system site-packages.
                env.pop('PYTHONPATH', None)
                with (directory / 'capture.log').open('w') as log:
                    child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                             env=env, start_new_session=True)
                    try:
                        code = child.wait(timeout=300)
                    except BaseException:
                        self._terminate(child)
                        raise
                report_path = directory / 'metadata.json'
                if code != 0:
                    raise RuntimeError(f'Camera worker exited {code}; see {directory / "capture.log"}')
                report = json.loads(report_path.read_text())
                if not report.get('success'):
                    raise RuntimeError(f'Capture incomplete; see {report_path}')
                result = dict(directory=str(directory), metadata=str(report_path), mode=mode,
                              images={k: str(directory / report[k]['path']) for k in
                                      ('standard', 'hq_single', 'hq') if report.get(k, {}).get('path')},
                              exposure_limited=report.get('exposure_limited', False),
                              data_files={k: str(directory / v) for k, v in report.get('data_files', {}).items()})
                (directory / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
                self.update(phase='READY', last_result=result, error=None)
                return result
        except Exception as error:
            self.update(phase='FAILED', error=str(error))
            if directory:
                (directory / 'failure.json').write_text(json.dumps(dict(error=str(error))) + '\n')
            raise
        finally:
            self.mutex.release()

    @staticmethod
    def _terminate(child):
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()


def serve(capture):
    # Domain65 matches the dedicated OAK context; never default to robot Domain66.
    os.environ['ROS_DOMAIN_ID'] = '65'
    os.environ['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    import rclpy
    from rclpy.callback_groups import ReentrantCallbackGroup
    from rclpy.executors import MultiThreadedExecutor
    from std_srvs.srv import Trigger
    rclpy.init()
    node = rclpy.create_node('photo', namespace='/oak4')
    group = ReentrantCallbackGroup()

    def snapshot(request, response):
        response.success = True
        response.message = json.dumps(capture.status())
        return response

    def callback(mode):
        def take(request, response):
            try:
                response.message = json.dumps(capture.capture(mode))
                response.success = True
            except Exception as error:
                response.message = str(error)
                response.success = False
                node.get_logger().error(str(error))
            return response
        return take

    for mode in ('hq', 'standard', 'compare'):
        node.create_service(Trigger, f'photo/capture_{mode}', callback(mode), callback_group=group)
    node.create_service(Trigger, 'photo/status', snapshot, callback_group=group)
    for mode in ('hq', 'standard', 'compare'):
        node.create_service(Trigger, f'depth/capture_{mode}', callback('depth_' + mode), callback_group=group)
    node.create_service(Trigger, 'depth/status', snapshot, callback_group=group)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    node.get_logger().info('READY: /oak4/photo/capture_hq, capture_standard, capture_compare; /oak4/depth/capture_hq, capture_standard, capture_compare; status (domain65)')
    try:
        executor.spin()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        executor.shutdown(wait_for_threads=True)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('serve', 'capture'))
    parser.add_argument('--mode', choices=('hq', 'standard', 'compare', 'depth_hq', 'depth_standard', 'depth_compare', 'rgbd'), default='hq')
    parser.add_argument('--frames', type=int, default=None, help='Defaults: RGB 8, depth 16')
    parser.add_argument('--iso', type=int, default=100)
    parser.add_argument('--focus', type=int, default=None, help='RGB manual lens position 0..255; omit for autofocus')
    args = parser.parse_args()
    capture = PhotoCapture()
    if args.action == 'serve':
        serve(capture)
    else:
        try:
            print(json.dumps(capture.capture(args.mode, args.frames, args.iso, args.focus), indent=2))
        except Exception as error:
            parser.exit(1, f'FAILED: {error}\n')


if __name__ == '__main__':
    main()
