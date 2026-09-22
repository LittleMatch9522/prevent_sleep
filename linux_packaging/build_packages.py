"""Build Debian, RPM, and AppImage artifacts from one PyInstaller binary."""

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from build import output_path
from src.app_metadata import APP_NAME, APP_VERSION, DISPLAY_NAME, PACKAGE_ARCH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_FILE = PROJECT_ROOT / "prevent-sleep.desktop"
ICON_FILE = PROJECT_ROOT / "assets" / "prevent-sleep.svg"
APP_RUN_FILE = PROJECT_ROOT / "linux_packaging" / "appimage" / "AppRun"
DEBIAN_ARCH = "amd64"
PACKAGE_FORMATS = ("deb", "rpm", "appimage")


class PackageError(RuntimeError):
    """Raised when a Linux package cannot be built."""


def package_filename(format_name):
    """Return the stable artifact filename for a package format."""
    format_name = format_name.lower()
    names = {
        "deb": "{}_{}_{}.deb".format(APP_NAME, APP_VERSION, DEBIAN_ARCH),
        "rpm": "{}-{}-1.{}.rpm".format(APP_NAME, APP_VERSION, PACKAGE_ARCH),
        "appimage": "{}-{}-{}.AppImage".format(
            APP_NAME, APP_VERSION, PACKAGE_ARCH
        ),
    }
    try:
        return names[format_name]
    except KeyError as exc:
        raise ValueError("unsupported package format: {}".format(format_name)) from exc


def render_debian_control():
    """Render Debian package metadata for the supported x86_64 build."""
    return """Package: {name}
Version: {version}
Section: utils
Priority: optional
Architecture: {architecture}
Depends: systemd, libx11-6, libxtst6
Maintainer: snailuu
Description: {display_name}
 A graphical utility that prevents automatic system sleep.
""".format(
        name=APP_NAME,
        version=APP_VERSION,
        architecture=DEBIAN_ARCH,
        display_name=DISPLAY_NAME,
    )


def render_rpm_spec():
    """Render the RPM spec used for the prebuilt x86_64 executable."""
    return """Name: {name}
Version: {version}
Release: 1%{{?dist}}
Summary: {display_name}
License: MIT
URL: https://github.com/snailuu/prevent_sleep
Source0: {name}
Source1: {name}.desktop
Source2: {name}.svg
BuildArch: {architecture}
Requires: systemd
Requires: libX11.so.6()(64bit)
Requires: libXtst.so.6()(64bit)

%description
A graphical utility that prevents automatic system sleep.

%prep

%build

%install
rm -rf %{{buildroot}}
install -Dpm 0755 %{{SOURCE0}} %{{buildroot}}%{{_bindir}}/{name}
install -Dpm 0644 %{{SOURCE1}} %{{buildroot}}%{{_datadir}}/applications/{name}.desktop
install -Dpm 0644 %{{SOURCE2}} %{{buildroot}}%{{_datadir}}/icons/hicolor/scalable/apps/{name}.svg

%files
%{{_bindir}}/{name}
%{{_datadir}}/applications/{name}.desktop
%{{_datadir}}/icons/hicolor/scalable/apps/{name}.svg

%changelog
* Tue Sep 22 2026 snailuu - {version}-1
- Add Linux desktop packages.
""".format(
        name=APP_NAME,
        version=APP_VERSION,
        display_name=DISPLAY_NAME,
        architecture=PACKAGE_ARCH,
    )


def render_appimage_desktop():
    """Add AppImage metadata to the relocatable desktop entry."""
    if not DESKTOP_FILE.is_file():
        raise PackageError("missing desktop file: {}".format(DESKTOP_FILE))

    desktop = DESKTOP_FILE.read_text(encoding="utf-8").rstrip()
    validate_desktop_entry(desktop)
    return "{}\nX-AppImage-Version={}\nX-AppImage-Arch={}\n".format(
        desktop, APP_VERSION, PACKAGE_ARCH
    )


def validate_desktop_entry(desktop):
    """Reject launcher fields that would make a package machine-specific."""
    launcher_keys = {"Exec", "TryExec", "Icon", "Path"}
    for line in desktop.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in launcher_keys:
            continue
        if value.strip().startswith("/"):
            raise PackageError(
                "desktop entry contains an absolute launcher path: {}".format(key)
            )


def validate_binary_architecture(binary_path):
    """Verify that a prebuilt input is a real 64-bit x86_64 ELF executable."""
    binary_path = Path(binary_path)
    if not os.access(binary_path, os.X_OK):
        raise PackageError("package binary is not an executable x86_64 file")

    try:
        header = binary_path.read_bytes()[:20]
    except OSError as exc:
        raise PackageError("cannot read package binary: {}".format(binary_path)) from exc

    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise PackageError("package binary is not an ELF x86_64 executable")
    if header[4] != 2 or header[5] != 1:
        raise PackageError(
            "package binary is not a 64-bit little-endian x86_64 executable"
        )

    machine = int.from_bytes(header[18:20], byteorder="little")
    if machine != 62:
        raise PackageError(
            "package binary architecture is not x86_64 (ELF machine {})".format(
                machine
            )
        )

    file_tool = shutil.which("file")
    if file_tool is None:
        raise PackageError("file is required to validate the package binary")
    try:
        description = subprocess.run(
            [file_tool, "-b", str(binary_path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PackageError("cannot identify package binary: {}".format(binary_path)) from exc
    if not (
        description.startswith("ELF 64-bit LSB")
        and "x86-64" in description
        and "executable" in description
    ):
        raise PackageError(
            "package binary is not a valid x86_64 executable: {}".format(description)
        )


def _ensure_x86_64():
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64"):
        raise PackageError(
            "x86_64 packages must be built on x86_64, got {}".format(machine)
        )


def _ensure_input_files(binary_path):
    paths = (binary_path, DESKTOP_FILE, ICON_FILE, APP_RUN_FILE)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise PackageError("missing packaging input: {}".format(", ".join(missing)))
    validate_desktop_entry(DESKTOP_FILE.read_text(encoding="utf-8"))


def _prepare_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_with_parent(source, destination):
    _prepare_directory(destination.parent)
    shutil.copy2(source, destination)


def _write_executable(source, destination):
    _prepare_directory(destination.parent)
    shutil.copy2(source, destination)
    destination.chmod(
        destination.stat().st_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )


def _write_install_payload(binary_path, package_root):
    """Install the common payload into a Debian/RPM package root."""
    _write_executable(binary_path, package_root / "usr" / "bin" / APP_NAME)
    _copy_with_parent(
        DESKTOP_FILE,
        package_root / "usr" / "share" / "applications" / DESKTOP_FILE.name,
    )
    _copy_with_parent(
        ICON_FILE,
        package_root
        / "usr"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / ICON_FILE.name,
    )


def _run(command, **kwargs):
    try:
        return subprocess.run(command, check=True, **kwargs)
    except FileNotFoundError as exc:
        raise PackageError(
            "required packaging tool is not installed: {}".format(command[0])
        ) from exc
    except OSError as exc:
        raise PackageError("cannot execute packaging tool: {}".format(exc)) from exc
    except subprocess.CalledProcessError as exc:
        raise PackageError(
            "packaging command failed with exit code {}: {}".format(
                exc.returncode, command
            )
        ) from exc


def build_deb(binary_path, output_dir):
    """Build a Debian package with dpkg-deb."""
    dpkg_deb = shutil.which("dpkg-deb")
    if dpkg_deb is None:
        raise PackageError("dpkg-deb is required to build a Debian package")

    output_dir = _prepare_directory(Path(output_dir))
    with tempfile.TemporaryDirectory(prefix="prevent-sleep-deb-") as temporary:
        package_root = Path(temporary) / APP_NAME
        _write_install_payload(binary_path, package_root)
        control_dir = package_root / "DEBIAN"
        _prepare_directory(control_dir)
        (control_dir / "control").write_text(
            render_debian_control(), encoding="utf-8"
        )
        output_path = output_dir / package_filename("deb")
        _run(
            [
                dpkg_deb,
                "--build",
                "--root-owner-group",
                str(package_root),
                str(output_path),
            ]
        )
    return output_path


def build_rpm(binary_path, output_dir):
    """Build an RPM package with rpmbuild."""
    rpmbuild = shutil.which("rpmbuild")
    if rpmbuild is None:
        raise PackageError("rpmbuild is required to build an RPM package")

    output_dir = _prepare_directory(Path(output_dir))
    with tempfile.TemporaryDirectory(prefix="prevent-sleep-rpm-") as temporary:
        topdir = Path(temporary) / "rpmbuild"
        for directory in (
            "BUILD",
            "BUILDROOT",
            "RPMS",
            "SOURCES",
            "SPECS",
            "SRPMS",
        ):
            _prepare_directory(topdir / directory)

        _copy_with_parent(binary_path, topdir / "SOURCES" / APP_NAME)
        _copy_with_parent(DESKTOP_FILE, topdir / "SOURCES" / DESKTOP_FILE.name)
        _copy_with_parent(ICON_FILE, topdir / "SOURCES" / ICON_FILE.name)
        spec_path = topdir / "SPECS" / "prevent-sleep.spec"
        spec_path.write_text(render_rpm_spec(), encoding="utf-8")

        _run(
            [
                rpmbuild,
                "-bb",
                "--define",
                "_topdir {}".format(topdir),
                str(spec_path),
            ]
        )
        built_packages = list((topdir / "RPMS" / PACKAGE_ARCH).glob("*.rpm"))
        if len(built_packages) != 1:
            raise PackageError("rpmbuild did not produce exactly one RPM")
        output_path = output_dir / package_filename("rpm")
        shutil.copy2(built_packages[0], output_path)
    return output_path


def _prepare_appimage(binary_path, appdir):
    _write_executable(binary_path, appdir / "usr" / "bin" / APP_NAME)
    _copy_with_parent(
        ICON_FILE,
        appdir
        / "usr"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / ICON_FILE.name,
    )
    _copy_with_parent(APP_RUN_FILE, appdir / "AppRun")
    (appdir / "AppRun").chmod(
        (appdir / "AppRun").stat().st_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )
    _copy_with_parent(ICON_FILE, appdir / ICON_FILE.name)
    (appdir / "prevent-sleep.desktop").write_text(
        render_appimage_desktop(), encoding="utf-8"
    )


def build_appimage(binary_path, output_dir):
    """Build a Type 2 AppImage with appimagetool."""
    appimagetool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not appimagetool:
        raise PackageError("appimagetool is required to build an AppImage")

    output_dir = _prepare_directory(Path(output_dir))
    with tempfile.TemporaryDirectory(prefix="prevent-sleep-appimage-") as temporary:
        appdir = Path(temporary) / "PreventSleep.AppDir"
        _prepare_directory(appdir)
        _prepare_appimage(binary_path, appdir)
        output_path = output_dir / package_filename("appimage")
        environment = os.environ.copy()
        environment["ARCH"] = PACKAGE_ARCH
        command = [appimagetool]
        runtime_file = os.environ.get("APPIMAGE_RUNTIME_FILE")
        if runtime_file:
            command.extend(["--runtime-file", runtime_file])
        command.extend([str(appdir), str(output_path)])
        _run(command, env=environment)
    return output_path


def build_binary():
    """Build the shared PyInstaller executable and return its path."""
    _run([sys.executable, str(PROJECT_ROOT / "build.py")], cwd=str(PROJECT_ROOT))
    binary_path = PROJECT_ROOT / output_path("Linux")
    if not binary_path.is_file():
        raise PackageError("PyInstaller did not produce {}".format(binary_path))
    return binary_path


def build_packages(formats, output_dir, binary_path=None):
    """Build the selected package formats from one executable."""
    formats = tuple(formats)
    _ensure_x86_64()
    binary_path = Path(binary_path) if binary_path else build_binary()
    if not binary_path.is_file():
        raise PackageError("binary does not exist: {}".format(binary_path))
    validate_binary_architecture(binary_path)
    _ensure_input_files(binary_path)

    builders = {
        "deb": build_deb,
        "rpm": build_rpm,
        "appimage": build_appimage,
    }
    unsupported = set(formats) - set(builders)
    if unsupported:
        raise PackageError(
            "unsupported package format(s): {}".format(", ".join(sorted(unsupported)))
        )
    return [builders[format_name](binary_path, output_dir) for format_name in formats]


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        dest="formats",
        action="append",
        choices=("all",) + PACKAGE_FORMATS,
        default=None,
        help="package format; repeat for multiple formats (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "dist" / "packages"),
        help="directory for generated artifacts",
    )
    parser.add_argument(
        "--binary",
        help="use an existing PyInstaller executable instead of building one",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    selected = args.formats or ["all"]
    formats = PACKAGE_FORMATS if "all" in selected else tuple(dict.fromkeys(selected))
    try:
        artifacts = build_packages(formats, args.output_dir, args.binary)
    except PackageError as exc:
        print("打包失败: {}".format(exc), file=sys.stderr)
        return 1

    for artifact in artifacts:
        print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
