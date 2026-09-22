import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext

try:
    from .sleep_inhibitor import InhibitorError, create_sleep_inhibitor
except ImportError:
    # Allows ``python src/prevent_sleep.py`` when src is not installed as a package.
    from sleep_inhibitor import InhibitorError, create_sleep_inhibitor

try:
    from .activity import ActivityError, ActivitySimulator
except ImportError:
    from activity import ActivityError, ActivitySimulator

try:
    from .app_metadata import DISPLAY_NAME
except ImportError:
    from app_metadata import DISPLAY_NAME


MONITOR_INTERVAL_SECONDS = 30
WINDOW_CLASS = "prevent-sleep-tool"
ACTIVITY_LABELS = {
    "file": "文件",
    "mouse": "鼠标",
    "scroll": "滚轮",
    "key": "按键",
}


class PreventSleepApp:
    def __init__(
        self,
        root,
        inhibitor=None,
        activity_simulator=None,
        monitor_interval=MONITOR_INTERVAL_SECONDS,
    ):
        self.root = root
        self.root.title(DISPLAY_NAME)
        self.root.geometry("600x400")
        self.root.resizable(True, True)
        self.root.minsize(400, 300)

        self.inhibitor = (
            inhibitor if inhibitor is not None else create_sleep_inhibitor()
        )
        self.activity_simulator = (
            activity_simulator
            if activity_simulator is not None
            else ActivitySimulator()
        )
        self.monitor_interval = monitor_interval
        self.monitoring_thread = None
        self.stop_event = threading.Event()
        self.is_monitoring = False
        self.simulate_activity_enabled = False
        self._controls_active = False
        self._closing = False
        self._log_queue = queue.Queue()
        self._log_after_id = None

        self._build_controls()
        self.log_message("程序已启动，点击【不要睡觉】开始防止屏幕休眠")
        self._log_after_id = self.root.after(100, self._drain_log_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _build_controls(self):
        control_frame = tk.Frame(self.root, pady=10)
        control_frame.pack(fill=tk.X)

        self.start_button = tk.Button(
            control_frame,
            text="不要睡觉",
            command=self.start_monitoring,
            width=15,
            height=2,
        )
        self.start_button.pack(side=tk.LEFT, padx=10)

        self.stop_button = tk.Button(
            control_frame,
            text="停止监听",
            command=self.stop_monitoring,
            width=15,
            height=2,
            state=tk.DISABLED,
        )
        self.stop_button.pack(side=tk.LEFT, padx=10)

        self.simulate_activity_var = tk.BooleanVar(value=False)
        self.activity_checkbutton = tk.Checkbutton(
            control_frame,
            text="启用模拟活动（文件/鼠标/滚轮/按键）",
            variable=self.simulate_activity_var,
        )
        self.activity_checkbutton.pack(side=tk.LEFT, padx=10)

        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            height=15,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _drain_log_queue(self):
        if self._closing:
            return

        try:
            while True:
                self.log_area.insert(tk.END, self._log_queue.get_nowait())
                self.log_area.see(tk.END)
        except queue.Empty:
            pass
        except tk.TclError:
            return

        # If the helper process exits unexpectedly, the worker marks monitoring
        # as stopped and this main-thread callback restores the button states.
        if not self.is_monitoring and self._controls_active:
            self._set_stopped_controls()

        if not self._closing:
            self._log_after_id = self.root.after(100, self._drain_log_queue)

    def _set_stopped_controls(self):
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.activity_checkbutton.config(state=tk.NORMAL)
        self._controls_active = False

    def log_message(self, message):
        """Queue a timestamped message for safe display on Tk's main thread."""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log_queue.put("[{}] {}\n".format(current_time, message))

    def start_monitoring(self):
        """Acquire the native OS inhibitor and start its health monitor."""
        if self.is_monitoring:
            return

        try:
            self.inhibitor.acquire()
        except InhibitorError as exc:
            self.log_message("无法启动防止休眠: {}".format(exc))
            return

        self.simulate_activity_enabled = bool(self.simulate_activity_var.get())
        self.stop_event.clear()
        self.is_monitoring = True
        self._controls_active = True
        self.monitoring_thread = threading.Thread(
            target=self.monitor_task,
            name="prevent-sleep-monitor",
            daemon=True,
        )
        self.monitoring_thread.start()

        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.activity_checkbutton.config(state=tk.DISABLED)
        self.log_message("防止睡眠监控已启动")

    def _run_activity(self):
        strategy = self.activity_simulator.run_random()
        self.log_message("已模拟{}操作".format(ACTIVITY_LABELS[strategy]))

    def stop_monitoring(self):
        """Stop monitoring and release the native OS inhibitor."""
        was_active = self.is_monitoring or self.inhibitor.is_active
        self.is_monitoring = False
        self.stop_event.set()

        try:
            self.inhibitor.release()
        except InhibitorError as exc:
            self.log_message("恢复系统休眠状态时出错: {}".format(exc))

        thread = self.monitoring_thread
        self.monitoring_thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

        self._set_stopped_controls()
        if was_active:
            self.log_message("防止睡眠监控已停止")

    def _release_after_monitor_failure(self):
        try:
            self.inhibitor.release()
        except InhibitorError as exc:
            self.log_message("监控中断后释放防止休眠状态时出错: {}".format(exc))

    def monitor_task(self):
        """Periodically verify that the OS inhibitor is still active."""
        try:
            while not self.stop_event.wait(self.monitor_interval):
                if self.simulate_activity_enabled:
                    try:
                        self._run_activity()
                    except ActivityError as exc:
                        self.log_message("模拟活动失败: {}".format(exc))
                self.inhibitor.keep_awake()
                self.log_message("防止睡眠状态正常")
        except InhibitorError as exc:
            self.is_monitoring = False
            self.stop_event.set()
            self._release_after_monitor_failure()
            self.log_message("防止睡眠监控已中断: {}".format(exc))
        except Exception as exc:
            self.is_monitoring = False
            self.stop_event.set()
            self._release_after_monitor_failure()
            self.log_message("监控任务发生错误: {}".format(exc))

    def on_closing(self):
        """Release the inhibitor before closing the window."""
        self.stop_monitoring()
        self._closing = True
        if self._log_after_id is not None:
            try:
                self.root.after_cancel(self._log_after_id)
            except tk.TclError:
                pass
        self.root.destroy()


def main():
    root = tk.Tk(className=WINDOW_CLASS)
    PreventSleepApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
