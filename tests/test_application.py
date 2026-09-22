import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.prevent_sleep import PreventSleepApp
from src.sleep_inhibitor import InhibitorError


class DesktopIntegrationTest(unittest.TestCase):
    def test_window_class_matches_desktop_entry(self):
        project_root = Path(__file__).parents[1]
        source = (project_root / "src" / "prevent_sleep.py").read_text(encoding="utf-8")
        desktop = (project_root / "prevent-sleep.desktop").read_text(encoding="utf-8")

        self.assertIn(
            "root = tk.Tk(className=WINDOW_CLASS)",
            source,
        )
        self.assertIn("StartupWMClass=prevent-sleep-tool", desktop)
        self.assertIn("Exec=prevent-sleep", desktop)
        self.assertIn("Icon=prevent-sleep", desktop)
        self.assertNotIn("/home/tsdl/", desktop)


class FakeInhibitor:
    def __init__(self):
        self.is_active = False
        self.acquire_called = False

    def acquire(self):
        self.acquire_called = True
        self.is_active = True

    def release(self):
        self.is_active = False

    def keep_awake(self):
        return None


class ApplicationTests(unittest.TestCase):
    def test_start_monitoring_acquires_native_inhibitor(self):
        inhibitor = FakeInhibitor()
        app = PreventSleepApp.__new__(PreventSleepApp)
        app.inhibitor = inhibitor
        app.is_monitoring = False
        app.stop_event = threading.Event()
        app.monitoring_thread = None
        app.start_button = Mock()
        app.stop_button = Mock()
        app.activity_checkbutton = Mock()
        app.simulate_activity_var = Mock()
        app.simulate_activity_var.get.return_value = False
        app.log_message = Mock()
        app.monitor_task = Mock()

        with patch("src.prevent_sleep.threading.Thread") as thread_class:
            thread = thread_class.return_value
            app.start_monitoring()

        self.assertTrue(inhibitor.acquire_called)
        self.assertTrue(app.is_monitoring)
        thread_class.assert_called_once()
        thread.start.assert_called_once_with()
        app.start_button.config.assert_called_once_with(state="disabled")
        app.stop_button.config.assert_called_once_with(state="normal")
        app.activity_checkbutton.config.assert_called_once_with(state="disabled")

    def test_monitor_task_runs_optional_activity_strategy(self):
        app = PreventSleepApp.__new__(PreventSleepApp)
        app.inhibitor = FakeInhibitor()
        app.stop_event = Mock()
        app.stop_event.wait.side_effect = [False, True]
        app.monitor_interval = 30
        app.simulate_activity_enabled = True
        app._run_activity = Mock()
        app.log_message = Mock()

        app.monitor_task()

        app._run_activity.assert_called_once_with()

    def test_monitor_task_releases_inhibitor_after_health_check_failure(self):
        inhibitor = Mock()
        inhibitor.keep_awake.side_effect = InhibitorError("helper exited")
        app = PreventSleepApp.__new__(PreventSleepApp)
        app.inhibitor = inhibitor
        app.stop_event = Mock()
        app.stop_event.wait.side_effect = [False]
        app.monitor_interval = 30
        app.simulate_activity_enabled = False
        app.log_message = Mock()

        app.monitor_task()

        inhibitor.release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
