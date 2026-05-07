# scrcpy_device/_exceptions.py
"""Custom exceptions for scrcpy_device"""

class ScrcpyError(Exception):
    """Base exception for all scrcpy device errors."""
    pass

class ConnectionError(ScrcpyError):
    """Failed to connect to the device or scrcpy server."""
    pass

class FrameTimeoutError(ScrcpyError):
    """Timeout while waiting for a video frame."""
    pass

class ServerStartError(ScrcpyError):
    """Failed to start scrcpy server on the device."""
    pass

class ControlDisabledError(ScrcpyError):
    """Control operations are disabled in configuration."""
    pass

class DeviceNotFoundError(ScrcpyError):
    """The specified device was not found."""
    pass