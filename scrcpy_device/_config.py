# scrcpy_device/_config.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class ScrcpyConfig:
    """Configuration for the scrcpy device client."""
    # Device selection (serial is set at connect time)
    serial: Optional[str] = None

    # ADB settings
    adb_host: str = ""
    adb_port: int = 0
    adb_path: str = "adb"

    # Server options
    server_version: str = "3.3.4"
    server_path: str = "/data/local/tmp/scrcpy-server.jar"
    jar_filename: Optional[str] = None   # e.g., "scrcpy-server-v3.3.4"

    # Video encoding
    max_size: int = 0          # 0 = keep original (max side length)
    bitrate: int = 8_000_000
    max_fps: int = 0            # 0 = unlimited
    video_codec: str = "h264"   # h264, hevc, av1

    # Device behavior
    stay_awake: bool = True
    lock_orientation: int = -1  # -1=unlocked, 0=0°,1=90°,2=180°,3=270°

    # Control & clipboard
    control_enabled: bool = True
    clipboard_autosync: bool = False   # not implemented yet

    # Connection
    port: int = 27183
    connection_timeout: float = 5.0

    # Optional display
    show_window: bool = False
    display_max_width: int = 800

    def __post_init__(self):
        if self.video_codec not in ("h264", "hevc", "av1"):
            raise ValueError(f"Unsupported video_codec: {self.video_codec}")
        if self.max_size < 0:
            raise ValueError("max_size must be >= 0")
        if self.bitrate < 0:
            raise ValueError("bitrate must be >= 0")
        if self.max_fps < 0:
            raise ValueError("max_fps must be >= 0")