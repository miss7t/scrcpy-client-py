# scrcpy_device/__init__.py
"""scrcpy_device - A generic Python client for scrcpy 3.x"""

from .api import ScrcpyClient, connect
from ._exceptions import (
    ConnectionError,
    FrameTimeoutError,
    ServerStartError,
    ControlDisabledError,
    DeviceNotFoundError,
    ScrcpyError,
)

__version__ = "0.1.0"

__all__ = [
    "ScrcpyClient",
    "connect",
    "ScrcpyError",
    "ConnectionError",
    "FrameTimeoutError",
    "ServerStartError",
    "ControlDisabledError",
    "DeviceNotFoundError",
]