# scrcpy_device/_control.py
import socket
import struct
import threading
import logging
from typing import Optional, Callable, Tuple

from . import _constants as const
from ._exceptions import ConnectionError

logger = logging.getLogger(__name__)


# ---------- Packing functions ----------

def pack_inject_keycode(action: int, keycode: int, repeat: int = 0, meta_state: int = 0) -> bytes:
    return struct.pack(">BBiii", const.TYPE_INJECT_KEYCODE, action, keycode, repeat, meta_state)

def pack_inject_text(text: str) -> bytes:
    encoded = text.encode("utf-8")
    length = len(encoded)
    if length > 300:
        raise ValueError("Text too long (max 300 chars)")
    return struct.pack(">Bi", const.TYPE_INJECT_TEXT, length) + encoded

def pack_inject_touch_event(action: int, pointer_id: int, x: int, y: int,
                            screen_width: int, screen_height: int,
                            pressure: float, action_button: int, buttons: int) -> bytes:
    pressure_raw = int(max(0.0, min(1.0, pressure)) * const.MAX_PRESSURE)
    return struct.pack(">BBqiiHHHii",
                       const.TYPE_INJECT_TOUCH_EVENT,
                       action,
                       pointer_id,
                       x, y,
                       screen_width & 0xFFFF, screen_height & 0xFFFF,
                       pressure_raw,
                       action_button,
                       buttons)

def pack_inject_scroll_event(x: int, y: int, screen_width: int, screen_height: int,
                             h_scroll: float, v_scroll: float, buttons: int) -> bytes:
    def encode_scroll(scroll: float) -> int:
        v = max(-16.0, min(16.0, scroll))
        return int(v / 16.0 * const.MAX_SCROLL)
    hs = encode_scroll(h_scroll)
    vs = encode_scroll(v_scroll)
    return struct.pack(">BiiHHhh i",
                       const.TYPE_INJECT_SCROLL_EVENT,
                       x, y,
                       screen_width & 0xFFFF, screen_height & 0xFFFF,
                       hs, vs,
                       buttons)

def pack_back_or_screen_on(action: int) -> bytes:
    return struct.pack(">BB", const.TYPE_BACK_OR_SCREEN_ON, action)

def pack_expand_notification_panel() -> bytes:
    return struct.pack(">B", const.TYPE_EXPAND_NOTIFICATION_PANEL)

def pack_expand_settings_panel() -> bytes:
    return struct.pack(">B", const.TYPE_EXPAND_SETTINGS_PANEL)

def pack_collapse_panels() -> bytes:
    return struct.pack(">B", const.TYPE_COLLAPSE_PANELS)

def pack_get_clipboard(copy_key: int = const.COPY_KEY_NONE) -> bytes:
    return struct.pack(">BB", const.TYPE_GET_CLIPBOARD, copy_key)

def pack_set_clipboard(sequence: int, text: str, paste: bool = False) -> bytes:
    encoded = text.encode("utf-8")
    length = len(encoded)
    if length > 262126:
        raise ValueError("Clipboard text too large")
    return struct.pack(">Bq?i", const.TYPE_SET_CLIPBOARD, sequence, paste, length) + encoded

def pack_set_display_power(on: bool) -> bytes:
    return struct.pack(">BB", const.TYPE_SET_DISPLAY_POWER, 1 if on else 0)

def pack_rotate_device() -> bytes:
    return struct.pack(">B", const.TYPE_ROTATE_DEVICE)

def pack_reset_video() -> bytes:
    return struct.pack(">B", const.TYPE_RESET_VIDEO)

def pack_uhid_create(dev_id: int, vendor_id: int, product_id: int, name: str, report_desc: bytes) -> bytes:
    name_bytes = name.encode("utf-8")
    if len(name_bytes) > 255:
        raise ValueError("UHID name too long (max 255)")
    if len(report_desc) > 65535:
        raise ValueError("UHID report descriptor too long (max 65535)")
    return struct.pack(">BHHHB", const.TYPE_UHID_CREATE,
                       dev_id, vendor_id, product_id,
                       len(name_bytes)) + name_bytes + \
           struct.pack(">H", len(report_desc)) + report_desc

def pack_uhid_input(dev_id: int, data: bytes) -> bytes:
    if len(data) > 65535:
        raise ValueError("UHID input data too long")
    return struct.pack(">BHH", const.TYPE_UHID_INPUT, dev_id, len(data)) + data

def pack_uhid_destroy(dev_id: int) -> bytes:
    return struct.pack(">BH", const.TYPE_UHID_DESTROY, dev_id)

def pack_start_app(name: str) -> bytes:
    name_bytes = name.encode("utf-8")
    if len(name_bytes) > 255:
        raise ValueError("App name too long (max 255)")
    return struct.pack(">BB", const.TYPE_START_APP, len(name_bytes)) + name_bytes

def pack_open_hard_keyboard_settings() -> bytes:
    return struct.pack(">B", const.TYPE_OPEN_HARD_KEYBOARD_SETTINGS)


# ---------- ControlChannel ----------

class ControlChannel:
    """Bidirectional control socket with message sending and receiving."""

    def __init__(self, sock: socket.socket, resolution: Tuple[int, int]):
        self.sock = sock
        self.resolution = resolution
        self._stop_event = threading.Event()
        self._recv_thread: Optional[threading.Thread] = None
        self._clipboard_cb: Optional[Callable[[str], None]] = None
        self._ack_clipboard_cb: Optional[Callable[[int], None]] = None
        self._uhid_cb: Optional[Callable[[int, bytes], None]] = None

    def start(self):
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def stop(self):
        self._stop_event.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            self.sock.close()
        if self._recv_thread:
            self._recv_thread.join(timeout=1)

    def _recv_exact(self, n: int) -> Optional[bytes]:
        data = bytearray()
        while len(data) < n and not self._stop_event.is_set():
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return None
                data.extend(chunk)
            except socket.timeout:
                continue
            except (OSError, EOFError):
                return None
        return bytes(data)

    def _recv_loop(self):
        while not self._stop_event.is_set():
            try:
                msg_type = self._recv_exact(1)
                if not msg_type:
                    break
                typ = msg_type[0]
                if typ == const.DEVICE_MSG_TYPE_CLIPBOARD:
                    length_data = self._recv_exact(4)
                    if not length_data:
                        break
                    length = struct.unpack(">i", length_data)[0]
                    text_data = self._recv_exact(length)
                    if text_data is None:
                        break
                    text = text_data.decode("utf-8")
                    if self._clipboard_cb:
                        self._clipboard_cb(text)
                elif typ == const.DEVICE_MSG_TYPE_ACK_CLIPBOARD:
                    seq_data = self._recv_exact(8)
                    if seq_data:
                        seq = struct.unpack(">q", seq_data)[0]
                        if self._ack_clipboard_cb:
                            self._ack_clipboard_cb(seq)
                elif typ == const.DEVICE_MSG_TYPE_UHID_OUTPUT:
                    id_len = self._recv_exact(4)
                    if not id_len:
                        break
                    dev_id, data_len = struct.unpack(">HH", id_len)
                    data = self._recv_exact(data_len)
                    if data is None:
                        break
                    if self._uhid_cb:
                        self._uhid_cb(dev_id, data)
                else:
                    pass
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.exception("Control receive error: %s", e)
                break

    # ---------- Send methods ----------
    def send_bytes(self, data: bytes):
        try:
            self.sock.sendall(data)
        except (socket.error, OSError):
            logger.debug("Failed to send control message")

    def keycode(self, action: int, keycode: int, repeat: int = 0, meta_state: int = 0):
        self.send_bytes(pack_inject_keycode(action, keycode, repeat, meta_state))

    def text(self, text: str):
        self.send_bytes(pack_inject_text(text))

    def touch(self, action: int, x: int, y: int, pressure: float = 1.0,
              action_button: int = 0, buttons: int = 0, pointer_id: int = const.SC_POINTER_ID_MOUSE):
        w, h = self.resolution
        x = max(0, min(x, w-1))
        y = max(0, min(y, h-1))
        self.send_bytes(pack_inject_touch_event(action, pointer_id, x, y, w, h,
                                                pressure, action_button, buttons))

    def scroll(self, x: int, y: int, h_scroll: float, v_scroll: float, buttons: int = 0):
        w, h = self.resolution
        x = max(0, min(x, w-1))
        y = max(0, min(y, h-1))
        self.send_bytes(pack_inject_scroll_event(x, y, w, h, h_scroll, v_scroll, buttons))

    def back_or_screen_on(self, action: int):
        self.send_bytes(pack_back_or_screen_on(action))

    def expand_notification_panel(self):
        self.send_bytes(pack_expand_notification_panel())

    def expand_settings_panel(self):
        self.send_bytes(pack_expand_settings_panel())

    def collapse_panels(self):
        self.send_bytes(pack_collapse_panels())

    def set_clipboard(self, text: str, paste: bool = False, sequence: int = 0):
        self.send_bytes(pack_set_clipboard(sequence, text, paste))

    def set_display_power(self, on: bool):
        self.send_bytes(pack_set_display_power(on))

    def rotate_device(self):
        self.send_bytes(pack_rotate_device())

    def reset_video(self):
        self.send_bytes(pack_reset_video())

    def uhid_create(self, dev_id: int, vendor_id: int, product_id: int, name: str, report_desc: bytes):
        self.send_bytes(pack_uhid_create(dev_id, vendor_id, product_id, name, report_desc))

    def uhid_input(self, dev_id: int, data: bytes):
        self.send_bytes(pack_uhid_input(dev_id, data))

    def uhid_destroy(self, dev_id: int):
        self.send_bytes(pack_uhid_destroy(dev_id))

    def start_app(self, name: str):
        self.send_bytes(pack_start_app(name))

    def open_hard_keyboard_settings(self):
        self.send_bytes(pack_open_hard_keyboard_settings())

    # ---------- Callbacks ----------
    def on_clipboard(self, callback: Callable[[str], None]):
        self._clipboard_cb = callback

    def on_ack_clipboard(self, callback: Callable[[int], None]):
        self._ack_clipboard_cb = callback

    def on_uhid_output(self, callback: Callable[[int, bytes], None]):
        self._uhid_cb = callback