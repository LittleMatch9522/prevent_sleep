import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from build import build_arguments, cleanup, output_path


class BuildConfigurationTests(unittest.TestCase):
    def test_linux_build_uses_linux_data_separator_and_binary_name(self):
        arguments = build_arguments("Linux")

        self.assertIn("--name=prevent-sleep", arguments)
        self.assertIn(
            "--add-data={}:.".format(Path(__file__).parents[1] / "README.md"),
            arguments,
        )
        self.assertEqual(output_path("Linux"), "dist/prevent-sleep")

    def test_windows_build_keeps_windows_data_separator_and_name(self):
        arguments = build_arguments("Windows")

        self.assertIn("--name=防止睡眠工具", arguments)
        self.assertIn(
            "--add-data={};.".format(Path(__file__).parents[1] / "README.md"),
            arguments,
        )
        self.assertEqual(output_path("Windows"), "dist/防止睡眠工具.exe")

    def test_cleanup_preserves_unrelated_build_and_distribution_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            (project_root / "dist" / "packages").mkdir(parents=True)
            (project_root / "dist" / "packages" / "keep.deb").write_text(
                "artifact", encoding="utf-8"
            )
            (project_root / "dist" / "other.bin").write_text(
                "artifact", encoding="utf-8"
            )
            (project_root / "build" / "unrelated").mkdir(parents=True)
            (project_root / "build" / "unrelated" / "keep.txt").write_text(
                "artifact", encoding="utf-8"
            )
            (project_root / "build" / "prevent-sleep").mkdir(parents=True)
            (project_root / "build" / "prevent-sleep" / "generated.txt").write_text(
                "generated", encoding="utf-8"
            )
            (project_root / "dist" / "prevent-sleep").write_text(
                "generated", encoding="utf-8"
            )

            with patch("build.PROJECT_ROOT", project_root):
                cleanup()

            self.assertTrue(
                (project_root / "dist" / "packages" / "keep.deb").is_file()
            )
            self.assertTrue((project_root / "dist" / "other.bin").is_file())
            self.assertTrue(
                (project_root / "build" / "unrelated" / "keep.txt").is_file()
            )
            self.assertFalse((project_root / "build" / "prevent-sleep").exists())
            self.assertFalse((project_root / "dist" / "prevent-sleep").exists())


if __name__ == "__main__":
    unittest.main()
