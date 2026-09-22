import unittest
from unittest.mock import Mock

from src.sleep_inhibitor import (
    InhibitorError,
    SystemdSleepInhibitor,
    UnsupportedSleepInhibitor,
    create_sleep_inhibitor,
)


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.terminate_called = False
        self.kill_called = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminate_called = True
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.kill_called = True
        self.returncode = -9


class SleepInhibitorTests(unittest.TestCase):
    def test_systemd_backend_holds_inhibitor_until_released(self):
        process = FakeProcess()
        popen_factory = Mock(return_value=process)
        inhibitor = SystemdSleepInhibitor(
            popen_factory=popen_factory,
            gnome_session_inhibit=True,
        )

        inhibitor.acquire()

        command = popen_factory.call_args.args[0]
        self.assertEqual(
            command,
            [
                "systemd-inhibit",
                "--what=idle:sleep",
                "--who=Prevent Sleep Tool",
                "--why=Prevent automatic sleep while monitoring",
                "--mode=block",
                "gnome-session-inhibit",
                "--inhibit",
                "idle:suspend",
                "--reason",
                "Prevent automatic sleep while monitoring",
                "--inhibit-only",
            ],
        )
        self.assertTrue(inhibitor.is_active)

        inhibitor.release()

        self.assertTrue(process.terminate_called)
        self.assertFalse(inhibitor.is_active)

    def test_systemd_backend_falls_back_without_gnome_session_inhibit(self):
        process = FakeProcess()
        popen_factory = Mock(return_value=process)
        inhibitor = SystemdSleepInhibitor(
            popen_factory=popen_factory,
            gnome_session_inhibit="",
        )

        inhibitor.acquire()

        command = popen_factory.call_args.args[0]
        self.assertEqual(command[-2:], ["sleep", "infinity"])

    def test_missing_systemd_inhibit_has_actionable_error(self):
        popen_factory = Mock(side_effect=FileNotFoundError)
        inhibitor = SystemdSleepInhibitor(popen_factory=popen_factory)

        with self.assertRaisesRegex(InhibitorError, "systemd-inhibit"):
            inhibitor.acquire()

    def test_linux_factory_uses_native_backend(self):
        inhibitor = create_sleep_inhibitor("Linux", popen_factory=Mock())

        self.assertIsInstance(inhibitor, SystemdSleepInhibitor)

    def test_unsupported_platform_reports_platform_name(self):
        inhibitor = create_sleep_inhibitor("FreeBSD")

        self.assertIsInstance(inhibitor, UnsupportedSleepInhibitor)
        with self.assertRaisesRegex(InhibitorError, "FreeBSD"):
            inhibitor.acquire()


if __name__ == "__main__":
    unittest.main()
