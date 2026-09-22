import os
import tempfile
import unittest
from pathlib import Path

from linux_packaging.build_packages import (
    _write_install_payload,
    package_filename,
    render_appimage_desktop,
    render_debian_control,
    render_rpm_spec,
    validate_desktop_entry,
    validate_binary_architecture,
)
from src.app_metadata import APP_NAME, APP_VERSION, DISPLAY_NAME, PACKAGE_ARCH


class AppMetadataTests(unittest.TestCase):
    def test_linux_package_metadata_is_stable(self):
        self.assertEqual(APP_NAME, "prevent-sleep")
        self.assertEqual(DISPLAY_NAME, "防止睡眠工具")
        self.assertEqual(APP_VERSION, "1.2.0")
        self.assertEqual(PACKAGE_ARCH, "x86_64")


class PackageFilenameTests(unittest.TestCase):
    def test_package_filename_uses_linux_package_conventions(self):
        expected_filenames = {
            "deb": "prevent-sleep_1.2.0_amd64.deb",
            "rpm": "prevent-sleep-1.2.0-1.x86_64.rpm",
            "appimage": "prevent-sleep-1.2.0-x86_64.AppImage",
        }

        for format_name, expected in expected_filenames.items():
            with self.subTest(format_name=format_name):
                self.assertEqual(package_filename(format_name), expected)


class PackageMetadataRenderingTests(unittest.TestCase):
    def test_render_debian_control_contains_package_dependencies(self):
        control = render_debian_control()

        self.assertIn("Package: prevent-sleep", control)
        self.assertIn("Version: 1.2.0", control)
        self.assertIn("Architecture: amd64", control)
        self.assertIn("Depends: systemd, libx11-6, libxtst6", control)

    def test_render_rpm_spec_contains_version_and_dependencies(self):
        spec = render_rpm_spec()

        self.assertIn("Version: 1.2.0", spec)
        self.assertIn("Requires: systemd", spec)
        self.assertIn("Requires: libX11.so.6()(64bit)", spec)
        self.assertIn("Requires: libXtst.so.6()(64bit)", spec)

    def test_render_appimage_desktop_is_relocatable(self):
        desktop = render_appimage_desktop()

        self.assertIn("Exec=prevent-sleep", desktop)
        self.assertIn("Icon=prevent-sleep", desktop)
        self.assertIn("X-AppImage-Version=1.2.0", desktop)
        self.assertIn("X-AppImage-Arch=x86_64", desktop)
        self.assertNotIn("/home/tsdl/", desktop)

    def test_desktop_validator_rejects_absolute_launcher_paths(self):
        absolute_desktop = "[Desktop Entry]\nExec=/tmp/prevent-sleep\nIcon=/tmp/icon.svg\n"

        with self.assertRaisesRegex(RuntimeError, "absolute"):
            validate_desktop_entry(absolute_desktop)


class SourceDesktopTests(unittest.TestCase):
    def test_source_desktop_entry_is_relocatable(self):
        project_root = Path(__file__).parents[1]
        desktop = (project_root / "prevent-sleep.desktop").read_text(encoding="utf-8")

        self.assertIn("Exec=prevent-sleep", desktop)
        self.assertIn("Icon=prevent-sleep", desktop)
        self.assertNotIn("/home/tsdl/", desktop)


class PackagePayloadTests(unittest.TestCase):
    def test_common_payload_creates_the_deb_and_rpm_install_layout(self):
        project_root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            binary = temporary / "prevent-sleep"
            binary.write_bytes(b"fake executable")
            package_root = temporary / "package-root"

            _write_install_payload(binary, package_root)

            self.assertTrue((package_root / "usr/bin/prevent-sleep").is_file())
            self.assertTrue(
                (package_root / "usr/share/applications/prevent-sleep.desktop").is_file()
            )
            self.assertTrue(
                (
                    package_root
                    / "usr/share/icons/hicolor/scalable/apps/prevent-sleep.svg"
                ).is_file()
            )
            self.assertEqual(
                (package_root / "usr/share/applications/prevent-sleep.desktop").read_text(
                    encoding="utf-8"
                ),
                (project_root / "prevent-sleep.desktop").read_text(encoding="utf-8"),
            )

    def test_appimage_entrypoint_runs_the_installed_binary(self):
        project_root = Path(__file__).parents[1]
        app_run = (
            project_root / "linux_packaging" / "appimage" / "AppRun"
        ).read_text(encoding="utf-8")

        self.assertIn('"$APPDIR/usr/bin/prevent-sleep"', app_run)


class BinaryArchitectureTests(unittest.TestCase):
    def test_rejects_non_x86_64_elf_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "arm64-binary"
            elf_header = bytearray(20)
            elf_header[:4] = b"\x7fELF"
            elf_header[4] = 2
            elf_header[5] = 1
            elf_header[18:20] = (183).to_bytes(2, byteorder="little")
            binary.write_bytes(elf_header)

            with self.assertRaisesRegex(RuntimeError, "x86_64"):
                validate_binary_architecture(binary)

    def test_rejects_truncated_x86_64_elf_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "truncated-binary"
            elf_header = bytearray(20)
            elf_header[:4] = b"\x7fELF"
            elf_header[4] = 2
            elf_header[5] = 1
            elf_header[18:20] = (62).to_bytes(2, byteorder="little")
            binary.write_bytes(elf_header)
            binary.chmod(binary.stat().st_mode | os.X_OK)

            with self.assertRaisesRegex(RuntimeError, "executable"):
                validate_binary_architecture(binary)


if __name__ == "__main__":
    unittest.main()
