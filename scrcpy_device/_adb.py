# scrcpy_device/_adb.py
import logging
import subprocess
import threading
import time
from typing import Optional, List

from ._config import ScrcpyConfig
from ._exceptions import ServerStartError, ConnectionError

logger = logging.getLogger(__name__)


class ADBManager:
    """Manages scrcpy server lifecycle using system adb command."""

    def __init__(self, config: ScrcpyConfig):
        self.config = config
        self._proc: Optional[subprocess.Popen] = None
        self._log_thread: Optional[threading.Thread] = None

    def _adb_cmd(self, *args) -> list:
        """Build adb command with host, port, serial options."""
        cmd = [self.config.adb_path]
        if self.config.adb_host:
            cmd += ["-H", self.config.adb_host]
        if self.config.adb_port:
            cmd += ["-P", str(self.config.adb_port)]
        if self.config.serial:
            cmd += ["-s", self.config.serial]
        cmd.extend(args)
        return cmd

    def list_devices(self) -> List[str]:
        """Return list of connected device serials."""
        cmd = self._adb_cmd("devices")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except FileNotFoundError:
            raise RuntimeError("adb command not found. Please install Android SDK Platform Tools.")
        lines = result.stdout.strip().splitlines()[1:]  # skip header
        serials = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials

    def push_server_jar(self, local_jar: str):
        """Push the scrcpy server jar to device."""
        logger.info("Pushing %s to %s", local_jar, self.config.server_path)
        subprocess.run(self._adb_cmd("push", local_jar, self.config.server_path), check=True)

    def setup_forward(self, remove_before: bool = True):
        """Create port forwarding."""
        if remove_before:
            self.remove_forward()
        logger.info("Forwarding tcp:%d -> localabstract:scrcpy", self.config.port)
        subprocess.run(
            self._adb_cmd("forward", f"tcp:{self.config.port}", "localabstract:scrcpy"),
            check=True,
        )

    def remove_forward(self):
        """Remove port forwarding."""
        try:
            subprocess.run(
                self._adb_cmd("forward", "--remove", f"tcp:{self.config.port}"),
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

    def start_server(self, local_jar: str):
        """Start scrcpy server on device."""
        self.push_server_jar(local_jar)
        self.setup_forward()

        cmd = self._adb_cmd(
            "shell",
            f"CLASSPATH={self.config.server_path}",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            self.config.server_version,
            "tunnel_forward=true",
            "audio=false",
            f"control={'true' if self.config.control_enabled else 'false'}",
            "cleanup=false",
        )

        # Optional parameters
        if self.config.max_size > 0:
            cmd.append(f"max_size={self.config.max_size}")
        cmd.append(f"video_bit_rate={self.config.bitrate}")
        if self.config.max_fps > 0:
            cmd.append(f"max_fps={self.config.max_fps}")
        if self.config.video_codec:
            cmd.append(f"video_codec={self.config.video_codec}")
        if self.config.stay_awake:
            cmd.append("stay_awake=true")
        if self.config.lock_orientation != -1:
            angle = self.config.lock_orientation * 90
            cmd.append(f"capture_orientation=@{angle}")

        logger.debug("Starting server: %s", " ".join(cmd))

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )

        # Thread to log server output
        if self._proc.stdout:
            self._log_thread = threading.Thread(
                target=self._log_output,
                args=(self._proc.stdout,),
                daemon=True,
            )
            self._log_thread.start()

        time.sleep(2)  # Let server initialize

    def _log_output(self, pipe):
        """Read server output line by line."""
        try:
            for line in iter(pipe.readline, b""):
                line = line.decode(errors="ignore").strip()
                if line:
                    logger.debug("server: %s", line)
        finally:
            pipe.close()

    def stop_server(self):
        """Stop server process and clean up forwarding."""
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=2)
            self._proc = None

        if self._log_thread and self._log_thread.is_alive():
            self._log_thread.join(timeout=1)

        self.remove_forward()