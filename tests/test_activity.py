import os
import tempfile
import unittest

from src.activity import ActivitySimulator, FileActivity


class FakeFileActivity:
    def __init__(self):
        self.calls = 0

    def perform(self):
        self.calls += 1


class FakeX11Activity:
    available = True

    def __init__(self):
        self.key_calls = 0
        self.mouse_calls = 0
        self.scroll_calls = 0

    def simulate_key_press(self):
        self.key_calls += 1

    def simulate_mouse_move(self):
        self.mouse_calls += 1

    def simulate_scroll(self):
        self.scroll_calls += 1


class ActivityTests(unittest.TestCase):
    def test_file_activity_reads_and_removes_its_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            FileActivity(directory=directory).perform()

            self.assertEqual(os.listdir(directory), [])

    def test_simulator_dispatches_file_scroll_and_key_strategies(self):
        file_activity = FakeFileActivity()
        x11_activity = FakeX11Activity()
        simulator = ActivitySimulator(
            file_activity=file_activity,
            x11_activity=x11_activity,
        )

        self.assertEqual(simulator.run("file"), "file")
        self.assertEqual(simulator.run("mouse"), "mouse")
        self.assertEqual(simulator.run("scroll"), "scroll")
        self.assertEqual(simulator.run("key"), "key")
        self.assertEqual(file_activity.calls, 1)
        self.assertEqual(x11_activity.mouse_calls, 1)
        self.assertEqual(x11_activity.scroll_calls, 1)
        self.assertEqual(x11_activity.key_calls, 1)


if __name__ == "__main__":
    unittest.main()
