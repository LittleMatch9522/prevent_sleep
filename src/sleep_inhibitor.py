"""Platform-specific helpers for keeping the desktop awake."""

import ctypes
import platform
import shutil
import subprocess


class InhibitorError(RuntimeError):
    """Raised when the operating system cannot install an inhibitor."""


class SystemdSleepInhibitor:
    """Keep Linux idle and sleep actions inhibited by the desktop session."""

    _systemd_command = (
        "systemd-inhibit",
        "--what=idle:sleep",
        "--who=Prevent Sleep Tool",
        "--why=Prevent automatic sleep while monitoring",
        "--mode=block",
    )

    def __init__(self, popen_factory=None, gnome_session_inhibit=None):
        self._popen_factory = popen_factory or subprocess.Popen
        if gnome_session_inhibit is None:
            self._use_gnome_session_inhibit = (
                shutil.which("gnome-session-inhibit") is not None
            )
        else:
            self._use_gnome_session_inhibit = bool(gnome_session_inhibit)
        self._process = None

    def _build_command(self):
        command = list(self._systemd_command)
        if self._use_gnome_session_inhibit:
            command.extend(
                [
                    "gnome-session-inhibit",
                    "--inhibit",
                    "idle:suspend",
                    "--reason",
                    "Prevent automatic sleep while monitoring",
                    "--inhibit-only",
                ]
            )
        else:
            command.extend(["sleep", "infinity"])
        return command

    @property
    def is_active(self):
        return self._process is not None and self._process.poll() is None

    def acquire(self):
        """Start a child process that owns the logind inhibitor lock."""
        if self.is_active:
            return

        try:
            process = self._popen_factory(
                self._build_command(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise InhibitorError(
                "未找到 systemd-inhibit，请确认 systemd-logind 已安装并运行"
            ) from exc
        except OSError as exc:
            raise InhibitorError("启动 systemd-inhibit 失败: {}".format(exc)) from exc

        if process.poll() is not None:
            detail = ""
            stderr = getattr(process, "stderr", None)
            if stderr is not None:
                try:
                    detail = stderr.read().strip()
                except (OSError, AttributeError):
                    pass
            suffix = ": {}".format(detail) if detail else ""
            raise InhibitorError("systemd-inhibit 未能保持运行{}".format(suffix))

        self._process = process

    def keep_awake(self):
        """Verify that the helper process still owns the inhibitor lock."""
        if not self.is_active:
            self._process = None
            raise InhibitorError("systemd-inhibit 进程已退出，无法继续防止休眠")

    def release(self):
        """Release the inhibitor and clean up the helper process."""
        process = self._process
        self._process = None
        if process is None:
            return

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


class WindowsSleepInhibitor:
    """Use SetThreadExecutionState on Windows."""

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self, kernel32=None):
        self._kernel32 = kernel32
        self._active = False

    @property
    def is_active(self):
        return self._active

    def _set_execution_state(self, state):
        if self._kernel32 is None:
            try:
                self._kernel32 = ctypes.windll.kernel32
            except AttributeError as exc:
                raise InhibitorError("当前 Python 环境无法访问 Windows API") from exc

        result = self._kernel32.SetThreadExecutionState(state)
        if not result:
            raise InhibitorError("Windows SetThreadExecutionState 调用失败")

    def acquire(self):
        if self._active:
            return
        self._set_execution_state(
            self.ES_CONTINUOUS
            | self.ES_SYSTEM_REQUIRED
            | self.ES_DISPLAY_REQUIRED
        )
        self._active = True

    def keep_awake(self):
        if self._active:
            self._set_execution_state(
                self.ES_CONTINUOUS
                | self.ES_SYSTEM_REQUIRED
                | self.ES_DISPLAY_REQUIRED
            )

    def release(self):
        if not self._active:
            return
        try:
            self._set_execution_state(self.ES_CONTINUOUS)
        finally:
            self._active = False


class UnsupportedSleepInhibitor:
    """Make unsupported platforms fail with a clear, user-facing message."""

    def __init__(self, system_name):
        self.system_name = system_name

    @property
    def is_active(self):
        return False

    def acquire(self):
        raise InhibitorError(
            "暂不支持 {}，目前支持 Linux（systemd）和 Windows".format(
                self.system_name
            )
        )

    def keep_awake(self):
        raise InhibitorError("当前系统不支持防止休眠")

    def release(self):
        return None


def create_sleep_inhibitor(system_name=None, **kwargs):
    """Create the native sleep inhibitor for the current operating system."""
    system_name = system_name or platform.system()
    if system_name == "Linux":
        return SystemdSleepInhibitor(**kwargs)
    if system_name == "Windows":
        return WindowsSleepInhibitor(**kwargs)
    return UnsupportedSleepInhibitor(system_name)
