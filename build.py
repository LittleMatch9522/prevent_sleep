import os
import platform
import shutil
import sys
from pathlib import Path

from src.app_metadata import APP_NAME, DISPLAY_NAME


PROJECT_ROOT = Path(__file__).resolve().parent
README_PATH = PROJECT_ROOT / "README.md"


def _system_name(system_name=None):
    return system_name or platform.system()


def _app_name(system_name):
    return DISPLAY_NAME if system_name == "Windows" else APP_NAME


def build_arguments(system_name=None):
    """Return PyInstaller arguments appropriate for the target platform."""
    system_name = _system_name(system_name)
    data_separator = ";" if system_name == "Windows" else ":"
    arguments = [
        "src/prevent_sleep.py",
        "--name={}".format(_app_name(system_name)),
        "--windowed",
        "--onefile",
        "--clean",
        "--noconfirm",
        "--workpath=build/{}".format(_app_name(system_name)),
        "--distpath=dist",
        "--specpath=build",
        "--add-data={}{}.".format(README_PATH, data_separator),
    ]
    if system_name == "Windows":
        arguments.append("--icon=assets/icon.ico")
    return arguments


def output_path(system_name=None):
    """Return the expected PyInstaller artifact path."""
    system_name = _system_name(system_name)
    filename = _app_name(system_name)
    if system_name == "Windows":
        filename += ".exe"
    return str(Path("dist") / filename)


def cleanup():
    """Remove only build artifacts created by this project."""
    for system_name in ("Linux", "Windows"):
        app_name = _app_name(system_name)
        work_path = PROJECT_ROOT / "build" / app_name
        spec_path = PROJECT_ROOT / "build" / "{}.spec".format(app_name)
        artifact_path = PROJECT_ROOT / "dist" / app_name
        if system_name == "Windows":
            artifact_path = artifact_path.with_suffix(".exe")

        if work_path.is_dir():
            shutil.rmtree(work_path)
        if spec_path.is_file():
            spec_path.unlink()
        if artifact_path.is_file():
            artifact_path.unlink()


def main():
    try:
        from PyInstaller.__main__ import run
    except ImportError:
        print(
            "未安装 PyInstaller，请先运行: python3 -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    cleanup()
    print("开始打包程序...")
    previous_directory = os.getcwd()
    os.chdir(PROJECT_ROOT)
    try:
        run(build_arguments())
    finally:
        os.chdir(previous_directory)
    print("打包完成！")
    print("可执行文件位置: {}".format(PROJECT_ROOT / output_path()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
