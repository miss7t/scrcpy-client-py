# scrcpy_device/api.py
import time
import logging
from typing import Optional, Tuple, Callable

import numpy as np

from ._config import ScrcpyConfig
from ._adb import ADBManager
from ._video import VideoStream
from ._control import ControlChannel
from ._exceptions import (
    ConnectionError,
    FrameTimeoutError,
    ServerStartError,
    ControlDisabledError,
    DeviceNotFoundError,
)
from ._utils import find_server_jar

logger = logging.getLogger(__name__)


class ScrcpyClient:
    """Main interface for scrcpy device control.

    Provides high-level methods for device interaction, video capture,
    and automated testing. Use as a context manager for automatic cleanup:
    
    with ScrcpyClient() as client:
        client.tap(100, 200)
        img = client.get_frame()
    """

    def __init__(self, serial: Optional[str] = None, **kwargs):
        self.config = ScrcpyConfig(**kwargs)
        self.config.serial = serial
        self._adb = ADBManager(self.config)
        self._video = VideoStream()
        self._control: Optional[ControlChannel] = None
        self._connected = False
        self._disconnect_callback: Optional[Callable[[Optional[Exception]], None]] = None

    # ---------- Connection management ----------
    def connect(self, serial: Optional[str] = None):
        """Establish connection to the device."""
        if self._connected:
            return

        # Determine target serial
        if serial:
            self.config.serial = serial
        if not self.config.serial:
            devices = self._adb.list_devices()
            if not devices:
                raise DeviceNotFoundError("No Android device found")
            self.config.serial = devices[0]
            logger.info("Auto-selected device: %s", self.config.serial)

        # Ensure the selected device exists
        else:
            devices = self._adb.list_devices()
            if self.config.serial not in devices:
                raise DeviceNotFoundError(f"Device {self.config.serial} not found")

        logger.info("Connecting to device %s", self.config.serial)

        # Locate server jar
        server_jar = find_server_jar(self.config)

        # Stop any previous server (clean slate)
        self._adb.stop_server()
        time.sleep(0.5)

        # Start server and wait
        self._adb.start_server(server_jar)
        time.sleep(2.0)

        try:
            # Connect video socket
            video_sock = self._video.connect_socket(
                host="127.0.0.1",
                port=self.config.port,
                timeout=self.config.connection_timeout,
            )

            # Connect control socket if enabled
            if self.config.control_enabled:
                control_sock = None
                try:
                    control_sock = self._video.connect_socket(
                        host="127.0.0.1",
                        port=self.config.port,
                        timeout=self.config.connection_timeout,
                    )
                except Exception:
                    video_sock.close()
                    raise
                self._control = ControlChannel(control_sock, (0, 0))
                self._control.start()

            # Handshake video
            self._video.handshake(video_sock)

            if self._control:
                self._control.resolution = self._video.resolution

            self._connected = True
            logger.info("Connected to %s (%s) %dx%d",
                        self._video.device_name,
                        self.config.video_codec,
                        *self._video.resolution)

        except Exception as e:
            # Cleanup on failure
            if self._control:
                self._control.stop()
                self._control = None
            self._adb.stop_server()
            raise ConnectionError(f"Connection failed: {e}") from e

    def disconnect(self):
        """Release all resources."""
        if self._control:
            self._control.stop()
            self._control = None
        self._video.stop()
        self._adb.stop_server()
        self._connected = False
        if self._disconnect_callback:
            self._disconnect_callback(None)
        logger.info("Disconnected from %s", self.config.serial)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def serial(self) -> Optional[str]:
        return self.config.serial

    @property
    def device_name(self) -> str:
        self._check_connected()
        return self._video.device_name

    @property
    def resolution(self) -> Tuple[int, int]:
        self._check_connected()
        return self._video.resolution

    @property
    def codec_name(self) -> str:
        return self.config.video_codec

    # ---------- Video ----------
    def get_frame(self, timeout: float = 5.0) -> np.ndarray:
        """Wait for the next video frame and return it."""
        self._check_connected()
        return self._video.get_frame(timeout=timeout)

    @property
    def last_frame(self) -> Optional[np.ndarray]:
        """Return the most recent video frame without waiting."""
        self._check_connected()
        return self._video.last_frame

    def wait_for_frame(self, timeout: float = 10.0):
        """Block until the first video frame is received."""
        self._check_connected()
        self._video.wait_for_frame(timeout=timeout)

    # ---------- Basic touch ----------
    def _check_control(self):
        if not self._connected:
            raise ConnectionError("Not connected")
        if not self._control:
            raise ControlDisabledError("Control is disabled")

    def touch_down(self, x: int, y: int, pressure: float = 1.0, pointer_id: int = -1):
        self._check_control()
        self._control.touch(0, x, y, pressure=pressure, pointer_id=pointer_id)

    def touch_move(self, x: int, y: int, pressure: float = 1.0, pointer_id: int = -1):
        self._check_control()
        self._control.touch(2, x, y, pressure=pressure, pointer_id=pointer_id)

    def touch_up(self, pointer_id: int = -1):
        self._check_control()
        # Use (0,0) as x,y but they should be ignored by server for action=1? We'll pass 0,0.
        self._control.touch(1, 0, 0, pressure=0.0, pointer_id=pointer_id)

    def tap(self, x: int, y: int, pressure: float = 1.0):
        self._check_control()
        self.touch_down(x, y, pressure)
        time.sleep(0.05)
        self.touch_up()

    def double_tap(self, x: int, y: int, interval: float = 0.1, pressure: float = 1.0):
        self.tap(x, y, pressure)
        time.sleep(interval)
        self.tap(x, y, pressure)

    def long_press(self, x: int, y: int, duration: float = 1.0, pressure: float = 1.0):
        self._check_control()
        self.touch_down(x, y, pressure)
        time.sleep(duration)
        self.touch_up()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3, steps: int = 30):
        self._check_control()
        dt = duration / steps
        for i in range(steps + 1):
            x = int(x1 + (x2 - x1) * i / steps)
            y = int(y1 + (y2 - y1) * i / steps)
            action = 0 if i == 0 else (1 if i == steps else 2)
            pressure = 1.0 if i < steps else 0.0
            self._control.touch(action, x, y, pressure=pressure)
            if i < steps:
                time.sleep(dt)

    # ---------- Keys ----------
    def press_key(self, keycode: int):
        self._check_control()
        self._control.keycode(0, keycode)
        time.sleep(0.05)
        self._control.keycode(1, keycode)

    def key_down(self, keycode: int):
        self._check_control()
        self._control.keycode(0, keycode)

    def key_up(self, keycode: int):
        self._check_control()
        self._control.keycode(1, keycode)

    def input_text(self, text: str):
        self._check_control()
        self._control.text(text)

    # System key shortcuts
    def home(self): self.press_key(3)
    def back(self): self.press_key(4)
    def recent_apps(self): self.press_key(187)
    def volume_up(self): self.press_key(24)
    def volume_down(self): self.press_key(25)
    def power(self): self.press_key(26)
    def menu(self): self.press_key(82)
    def delete(self): self.press_key(67)
    def enter(self): self.press_key(66)

    # ---------- System control ----------
    def start_app(self, package_name: str):
        self._check_control()
        self._control.start_app(package_name)

    def screen_on(self):
        self._check_control()
        self._control.set_display_power(True)

    def screen_off(self):
        self._check_control()
        self._control.set_display_power(False)

    def rotate_device(self):
        self._check_control()
        self._control.rotate_device()

    def expand_notification_panel(self):
        self._check_control()
        self._control.expand_notification_panel()

    def expand_settings_panel(self):
        self._check_control()
        self._control.expand_settings_panel()

    def collapse_panels(self):
        self._check_control()
        self._control.collapse_panels()

    def set_clipboard(self, text: str, paste: bool = False):
        self._check_control()
        self._control.set_clipboard(text, paste)

    def get_clipboard_async(self, copy_key: int = 0):
        """Request clipboard content; result will be delivered to on_clipboard callback."""
        self._check_control()
        self._control.send_bytes(pack_get_clipboard(copy_key))

    def reset_video(self):
        self._check_control()
        self._control.reset_video()

    # ---------- Callbacks ----------
    def on_clipboard(self, callback: Callable[[str], None]):
        self._check_control()
        self._control.on_clipboard(callback)

    def on_clipboard_ack(self, callback: Callable[[int], None]):
        self._check_control()
        self._control.on_ack_clipboard(callback)

    def on_disconnect(self, callback: Callable[[Optional[Exception]], None]):
        self._disconnect_callback = callback

    def _check_connected(self):
        if not self._connected:
            raise ConnectionError("Not connected")


def connect(serial: Optional[str] = None, **kwargs) -> ScrcpyClient:
    """Create and connect a ScrcpyClient in one call."""
    client = ScrcpyClient(serial=serial, **kwargs)
    client.connect()
    return client