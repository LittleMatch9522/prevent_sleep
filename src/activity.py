"""Optional user-activity simulation for Linux desktops."""

import ctypes
import ctypes.util
import os
import random
import tempfile
from datetime import datetime


class ActivityError(RuntimeError):
    """Raised when an activity strategy cannot be performed."""


class FileActivity:
    """Perform a harmless write/read/delete cycle in the system temp folder."""

    def __init__(self, directory=None):
        self.directory = directory or tempfile.gettempdir()

    def perform(self):
        file_descriptor, path = tempfile.mkstemp(
            prefix=".prevent-sleep-",
            suffix=".tmp",
            dir=self.directory,
            text=True,
        )
        try:
            with os.fdopen(file_descriptor, "w+", encoding="utf-8") as stream:
                stream.write(datetime.now().isoformat())
                stream.flush()
                stream.seek(0)
                stream.read()
        finally:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


class X11Activity:
    """Generate reversible key and scroll events through the XTest extension."""

    XK_SHIFT_L = 0xFFE1

    def __init__(self, display_name=None, x11=None, xtst=None):
        self.display_name = display_name
        self._x11 = x11
        self._xtst = xtst
        self._libraries_loaded = False

    @property
    def available(self):
        try:
            self._with_display(lambda _display: None)
        except ActivityError:
            return False
        return True

    def _load_libraries(self):
        if self._libraries_loaded:
            return

        x11_path = ctypes.util.find_library("X11")
        xtst_path = ctypes.util.find_library("Xtst")
        if not x11_path or not xtst_path:
            raise ActivityError("当前系统未提供 X11 XTest 扩展")

        try:
            self._x11 = self._x11 or ctypes.CDLL(x11_path)
            self._xtst = self._xtst or ctypes.CDLL(xtst_path)
        except OSError as exc:
            raise ActivityError("无法加载 X11 XTest 库: {}".format(exc)) from exc

        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._x11.XCloseDisplay.restype = ctypes.c_int
        self._x11.XFlush.argtypes = [ctypes.c_void_p]
        self._x11.XFlush.restype = ctypes.c_int
        self._x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._x11.XKeysymToKeycode.restype = ctypes.c_uint

        self._xtst.XTestFakeKeyEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeKeyEvent.restype = ctypes.c_int
        self._xtst.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeButtonEvent.restype = ctypes.c_int
        self._xtst.XTestFakeRelativeMotionEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeRelativeMotionEvent.restype = ctypes.c_int
        self._libraries_loaded = True

    def _with_display(self, operation):
        self._load_libraries()
        display_name = (
            self.display_name.encode("utf-8") if self.display_name else None
        )
        display = self._x11.XOpenDisplay(display_name)
        if not display:
            raise ActivityError("无法连接 X11 显示会话")
        try:
            return operation(display)
        finally:
            self._x11.XCloseDisplay(display)

    def simulate_key_press(self):
        def press_shift(display):
            keycode = self._x11.XKeysymToKeycode(
                display, ctypes.c_ulong(self.XK_SHIFT_L)
            )
            if not keycode:
                raise ActivityError("当前键盘布局没有可用的 Shift 键")
            if not self._xtst.XTestFakeKeyEvent(display, keycode, 1, 0):
                raise ActivityError("X11 模拟按键按下失败")
            if not self._xtst.XTestFakeKeyEvent(display, keycode, 0, 0):
                raise ActivityError("X11 模拟按键释放失败")
            self._x11.XFlush(display)

        self._with_display(press_shift)

    def simulate_scroll(self):
        def scroll_up_and_down(display):
            for button in (4, 5):
                if not self._xtst.XTestFakeButtonEvent(display, button, 1, 0):
                    raise ActivityError("X11 模拟滚轮按下失败")
                if not self._xtst.XTestFakeButtonEvent(display, button, 0, 0):
                    raise ActivityError("X11 模拟滚轮释放失败")
            self._x11.XFlush(display)

        self._with_display(scroll_up_and_down)

    def simulate_mouse_move(self):
        def move_and_return(display):
            offset_x = random.choice((-2, -1, 1, 2))
            offset_y = random.choice((-2, -1, 1, 2))
            for x_offset, y_offset in (
                (offset_x, offset_y),
                (-offset_x, -offset_y),
            ):
                if not self._xtst.XTestFakeRelativeMotionEvent(
                    display, x_offset, y_offset, 0
                ):
                    raise ActivityError("X11 模拟鼠标移动失败")
            self._x11.XFlush(display)

        self._with_display(move_and_return)


class ActivitySimulator:
    """Dispatch the original file, scroll, and key activity strategies."""

    def __init__(self, file_activity=None, x11_activity=None, chooser=None):
        self.file_activity = file_activity or FileActivity()
        self.x11_activity = x11_activity or X11Activity()
        self.chooser = chooser or random.choice
        self.available_strategies = ["file"]
        if getattr(self.x11_activity, "available", False):
            self.available_strategies.extend(["mouse", "scroll", "key"])

    def run(self, strategy):
        if strategy == "file":
            self.file_activity.perform()
            return strategy
        if strategy == "mouse" and "mouse" in self.available_strategies:
            self.x11_activity.simulate_mouse_move()
            return strategy
        if strategy == "scroll" and "scroll" in self.available_strategies:
            self.x11_activity.simulate_scroll()
            return strategy
        if strategy == "key" and "key" in self.available_strategies:
            self.x11_activity.simulate_key_press()
            return strategy
        raise ActivityError("当前环境不支持模拟活动策略: {}".format(strategy))

    def run_random(self):
        return self.run(self.chooser(self.available_strategies))
