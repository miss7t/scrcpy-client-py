# scrcpy_device/_video.py
import socket
import struct
import threading
import time
import traceback
import logging
from typing import Optional, Tuple

import av
import numpy as np

from ._constants import HEADER_SIZE, FLAG_CONFIG, FLAG_KEY_FRAME, PTS_MASK, CODECS
from ._exceptions import ConnectionError, FrameTimeoutError

logger = logging.getLogger(__name__)


class VideoStream:
    """Handles video socket connection, handshake, decoding, and frame buffering."""

    def __init__(self):
        self._sock: Optional[socket.socket] = None
        self._decoder: Optional[av.CodecContext] = None
        self._stop_event = threading.Event()
        self._recv_thread: Optional[threading.Thread] = None
        self._resolution: Optional[Tuple[int, int]] = None
        self._device_name: Optional[str] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_cond = threading.Condition()
        self._frame_count = 0

    @property
    def resolution(self) -> Tuple[int, int]:
        if self._resolution is None:
            raise ConnectionError("Not connected")
        return self._resolution

    @property
    def device_name(self) -> str:
        return self._device_name or "Unknown"

    def connect_socket(self, host: str = "127.0.0.1", port: int = 27183, timeout: float = 10.0) -> socket.socket:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
        return sock

    def handshake(self, sock: socket.socket):
        """Perform initial handshake and start decoding."""
        dummy = self._read_exact(sock, 1)
        if dummy != b"\x00":
            raise ConnectionError(f"Invalid dummy byte: {dummy}")

        name_data = self._read_exact(sock, 64)
        self._device_name = name_data.split(b"\0", 1)[0].decode("utf-8")

        codec_id = struct.unpack(">I", self._read_exact(sock, 4))[0]
        if codec_id not in CODECS:
            raise ConnectionError(f"Unsupported codec: {codec_id:#x}")
        codec_name = CODECS[codec_id]

        width = struct.unpack(">i", self._read_exact(sock, 4))[0]
        height = struct.unpack(">i", self._read_exact(sock, 4))[0]
        self._resolution = (width, height)

        logger.info("Connected to %s (%s) %dx%d", self._device_name, codec_name, width, height)

        self._decoder = av.CodecContext.create(codec_name, "r")
        self._sock = sock
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def _read_exact(self, sock: socket.socket, n: int) -> bytes:
        data = bytearray()
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise EOFError("Socket closed")
            data.extend(chunk)
        return bytes(data)

    def _recv_loop(self):
        logger.debug("Video receive loop started")
        config_data = b""
        try:
            while not self._stop_event.is_set():
                try:
                    header = self._read_exact(self._sock, HEADER_SIZE)
                    pts_flags, size = struct.unpack(">QI", header)
                    packet_data = self._read_exact(self._sock, size)
                except socket.timeout:
                    continue
                except (EOFError, OSError) as e:
                    if self._stop_event.is_set():
                        logger.debug("Socket closed during stop: %s", e)
                    else:
                        logger.error("Socket error in recv loop: %s", e)
                    break

                if pts_flags & FLAG_CONFIG:
                    config_data = packet_data
                    continue

                if config_data:
                    packet_data = config_data + packet_data
                    config_data = b""

                packet = av.Packet(packet_data)
                packet.pts = pts_flags & PTS_MASK
                if pts_flags & FLAG_KEY_FRAME:
                    packet.is_keyframe = True

                for frame in self._decoder.decode(packet):
                    img = frame.to_ndarray(format="rgb24")
                    with self._frame_cond:
                        self._latest_frame = img
                        self._frame_count += 1
                        self._frame_cond.notify_all()
                    logger.debug("Frame decoded (count=%d)", self._frame_count)
        except Exception:
            logger.error("Video decode error: %s", traceback.format_exc())
        finally:
            logger.debug("Video receive loop exited")
            self._stop_event.set()
            with self._frame_cond:
                self._frame_cond.notify_all()

    def get_frame(self, timeout: float = 5.0) -> np.ndarray:
        """Block until a new frame is available, then return it."""
        with self._frame_cond:
            start_count = self._frame_count
            deadline = time.time() + timeout
            while self._frame_count == start_count and not self._stop_event.is_set():
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise FrameTimeoutError(f"No new frame after {timeout}s")
                self._frame_cond.wait(timeout=remaining)
            if self._stop_event.is_set() or self._latest_frame is None:
                raise FrameTimeoutError("Stream stopped")
            return self._latest_frame.copy()

    @property
    def last_frame(self) -> Optional[np.ndarray]:
        """Return the most recent frame without blocking."""
        with self._frame_cond:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def wait_for_frame(self, timeout: float = 10.0):
        """Block until at least one frame has been received."""
        with self._frame_cond:
            deadline = time.time() + timeout
            while self._latest_frame is None and not self._stop_event.is_set():
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise FrameTimeoutError(f"No frame received within {timeout}s")
                self._frame_cond.wait(timeout=remaining)

    def stop(self):
        """Stop receiver and close socket."""
        logger.debug("VideoStream stopping...")
        self._stop_event.set()
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2)
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self._sock.close()
            self._sock = None
        self._decoder = None