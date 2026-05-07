# scrcpy_device/display.py
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Display:
    """Optional pygame window to show video and forward input events.

    Requires pygame to be installed: pip install pygame
    """

    def __init__(self, client, max_width: int = 800):
        """
        :param client: ScrcpyClient instance (must be connected)
        :param max_width: Maximum window width (height scales accordingly)
        """
        self.client = client
        self.max_width = max_width
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the display window in a separate thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the display window."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        try:
            import pygame
        except ImportError:
            logger.error("pygame not installed, cannot show window")
            return

        pygame.init()
        screen = None
        clock = pygame.time.Clock()

        ANDROID_KEYCODES = {
            pygame.K_a: 29, pygame.K_b: 30, pygame.K_c: 31,
            pygame.K_d: 32, pygame.K_e: 33, pygame.K_f: 34,
            pygame.K_g: 35, pygame.K_h: 36, pygame.K_i: 37,
            pygame.K_j: 38, pygame.K_k: 39, pygame.K_l: 40,
            pygame.K_m: 41, pygame.K_n: 42, pygame.K_o: 43,
            pygame.K_p: 44, pygame.K_q: 45, pygame.K_r: 46,
            pygame.K_s: 47, pygame.K_t: 48, pygame.K_u: 49,
            pygame.K_v: 50, pygame.K_w: 51, pygame.K_x: 52,
            pygame.K_y: 53, pygame.K_z: 54,
            pygame.K_0: 7, pygame.K_1: 8, pygame.K_2: 9,
            pygame.K_3: 10, pygame.K_4: 11, pygame.K_5: 12,
            pygame.K_6: 13, pygame.K_7: 14, pygame.K_8: 15,
            pygame.K_9: 16,
            pygame.K_SPACE: 62, pygame.K_RETURN: 66,
            pygame.K_BACKSPACE: 67, pygame.K_TAB: 61,
            pygame.K_ESCAPE: 111,
            pygame.K_LEFT: 21, pygame.K_RIGHT: 22,
            pygame.K_UP: 19, pygame.K_DOWN: 20,
            pygame.K_F1: 3, pygame.K_F2: 4, pygame.K_F3: 187,
            pygame.K_F4: 82, pygame.K_F5: 26,
        }
        MOUSE_BUTTON_MAP = {
            1: 1 << 0,
            2: 1 << 2,
            3: 1 << 1,
        }
        mouse_buttons = 0
        scale = 1.0

        while not self._stop_event.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop_event.set()
                    break

                if event.type in (pygame.KEYDOWN, pygame.KEYUP):
                    action = 0 if event.type == pygame.KEYDOWN else 1
                    mods = pygame.key.get_mods()
                    if mods & (pygame.KMOD_LALT | pygame.KMOD_LMETA) and not (mods & pygame.KMOD_SHIFT) and not event.repeat:
                        if event.key == pygame.K_h:
                            self.client.home()
                            continue
                        if event.key in (pygame.K_b, pygame.K_BACKSPACE):
                            self.client.back()
                            continue
                        if event.key == pygame.K_s:
                            self.client.recent_apps()
                            continue
                        if event.key == pygame.K_m:
                            self.client.menu()
                            continue
                        if event.key == pygame.K_p:
                            self.client.power()
                            continue
                        if event.key == pygame.K_n:
                            if event.type == pygame.KEYDOWN:
                                if mods & pygame.KMOD_SHIFT:
                                    self.client.collapse_panels()
                                else:
                                    self.client.expand_notification_panel()
                            continue
                    keycode = ANDROID_KEYCODES.get(event.key)
                    if keycode is not None:
                        if action == 0:
                            self.client.key_down(keycode)
                        else:
                            self.client.key_up(keycode)

                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                    button = MOUSE_BUTTON_MAP.get(event.button)
                    if button is not None:
                        down = event.type == pygame.MOUSEBUTTONDOWN
                        if down:
                            mouse_buttons |= button
                        else:
                            mouse_buttons &= ~button
                        x, y = event.pos
                        dw, dh = screen.get_size() if screen else (1, 1)
                        w, h = self.client.resolution
                        dev_x = int(x * w / dw)
                        dev_y = int(y * h / dh)
                        if down:
                            self.client.touch_down(dev_x, dev_y)
                        else:
                            self.client.touch_up()

                if event.type == pygame.MOUSEMOTION and mouse_buttons:
                    x, y = event.pos
                    dw, dh = screen.get_size() if screen else (1, 1)
                    w, h = self.client.resolution
                    dev_x = int(x * w / dw)
                    dev_y = int(y * h / dh)
                    self.client.touch_move(dev_x, dev_y)

            frame = self.client.last_frame
            if frame is not None:
                h, w, _ = frame.shape
                if self.max_width and w > self.max_width:
                    scale = self.max_width / w
                    dw, dh = self.max_width, int(h * scale)
                else:
                    dw, dh = w, h
                surf = pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB")
                if (dw, dh) != (w, h):
                    surf = pygame.transform.scale(surf, (dw, dh))
                if not screen or screen.get_size() != (dw, dh):
                    screen = pygame.display.set_mode((dw, dh))
                screen.blit(surf, (0, 0))
                pygame.display.flip()
            clock.tick(60)

        pygame.quit()