# 防止睡眠工具 (Prevent Sleep Tool)

一个带图形界面的跨平台小工具，用于在工作期间阻止系统自动休眠或挂起。

## 本机适配情况

本项目已适配 Ubuntu/Linux：

- 通过 `systemd-inhibit` 向 systemd-logind 注册 `idle:sleep` 抑制锁；
- 在 GNOME 会话中同时通过 `gnome-session-inhibit` 抑制 `idle:suspend`，避免 GNOME
  屏保/会话空闲策略单独触发；
- 默认不模拟用户输入；勾选“启用模拟活动”后，可选执行文件、鼠标、滚轮和按键策略；
- 使用 X11 XTest 原生接口实现鼠标/滚轮/按键，不依赖 `pyautogui`、`keyboard` 或 root；
- 不需要 root 权限；
- 适用于当前 Ubuntu GNOME/X11 环境，运行时只需要 Python、Tk 和系统自带的
  `systemd-inhibit`；GNOME 桌面会额外使用 `gnome-session-inhibit`。

Windows 仍使用 `SetThreadExecutionState` 系统 API。

## 功能

- 一键开始/停止防止休眠；
- 每 30 秒检查一次原生系统抑制锁是否仍然有效；
- 实时显示运行日志；
- 关闭窗口前自动释放系统抑制锁；
- Linux 和 Windows 使用各自的原生机制，不修改系统电源配置。

## 环境准备

Ubuntu/Debian：

```bash
sudo apt install python3-tk libx11-6 libxtst6
```

确认系统提供 `systemd-inhibit`：

```bash
command -v systemd-inhibit
command -v gnome-session-inhibit
```

本项目在 Ubuntu GNOME、X11、Python 3.10 环境下验证过。源码运行不需要安装第三方
运行时依赖；只有打包时需要安装 PyInstaller：

```bash
python3 -m pip install -r requirements.txt
```

## 运行

```bash
python3 src/prevent_sleep.py
```

点击“不要睡觉”后，Linux 下可以在另一个终端查看抑制锁：

```bash
systemd-inhibit --list
```

如果需要兼容原项目的活动模拟策略，勾选窗口中的“启用模拟活动（文件/鼠标/滚轮/按键）”。
文件策略只在系统临时目录中写入、读取并删除临时文件；滚轮和按键策略会作用于当前
焦点窗口，可能影响正在使用的应用；鼠标移动会在小范围移动后复位，因此默认关闭。

点击“停止监听”或关闭窗口后，抑制锁会被释放。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

## 打包

### 构建 PyInstaller 可执行文件

```bash
python3 -m pip install -r requirements.txt
python3 build.py
```

生成的可执行文件为 `dist/prevent-sleep`。该文件运行时仍需要目标 Linux 系统提供
`systemd-inhibit` 和图形会话。

在 Windows 上运行同一脚本会生成 `dist/防止睡眠工具.exe`。

### 构建 Linux 安装包

三种 Linux 包使用同一个 PyInstaller 二进制，首发目标为 x86_64：

```bash
python3 -m linux_packaging.build_packages --format all
```

输出目录为 `dist/packages/`：

```text
prevent-sleep_1.2.0_amd64.deb
prevent-sleep-1.2.0-1.x86_64.rpm
prevent-sleep-1.2.0-x86_64.AppImage
```

也可以指定已有的可执行文件：

```bash
python3 -m linux_packaging.build_packages \
  --binary dist/prevent-sleep \
  --format deb \
  --output-dir dist/packages
```

构建 `.deb` 需要 `dpkg-deb`，构建 `.rpm` 需要 `rpmbuild`，三种格式都需要
`file` 校验输入二进制架构；构建 AppImage 还需要 `appimagetool`，并可通过
`APPIMAGETOOL=/path/to/appimagetool` 指定其路径。GitHub Actions 使用固定版本的
`appimagetool` 自动生成 AppImage。

安装方式：

```bash
# Debian/Ubuntu
sudo apt install ./prevent-sleep_1.2.0_amd64.deb

# Fedora/RHEL/openSUSE（具体命令按发行版选择）
sudo dnf install ./prevent-sleep-1.2.0-1.x86_64.rpm
sudo zypper install ./prevent-sleep-1.2.0-1.x86_64.rpm

# AppImage
chmod +x prevent-sleep-1.2.0-x86_64.AppImage
./prevent-sleep-1.2.0-x86_64.AppImage
```

`.deb` 和 `.rpm` 会安装到 `/usr/bin/prevent-sleep`，并注册桌面菜单项和 SVG 图标。
AppImage 不需要安装权限，但仍需要宿主系统提供图形会话、systemd 的
`systemd-inhibit` 以及基础 Linux 运行库；“Universal”表示主流 x86_64 Linux 发行版
之间可移植，不表示支持 ARM 或不带 systemd 的系统。

GitHub Actions 会在 Pull Request 中构建并检查三种包，在推送 `v1.2.0` 标签时生成
Release 资产和 `SHA256SUMS`。构建产物不会提交到 Git 仓库。

## 目录结构

```text
src/
  prevent_sleep.py       # Tk 图形界面与监控线程
  sleep_inhibitor.py     # Linux/Windows 原生防睡眠后端
  activity.py            # 文件、X11 鼠标/滚轮/按键模拟策略
  app_metadata.py        # 应用版本、包名和目标架构
tests/
  test_activity.py
  test_application.py
  test_build.py
  test_linux_packages.py
  test_sleep_inhibitor.py
build.py                 # 跨平台 PyInstaller 打包脚本
linux_packaging/build_packages.py # Debian、RPM、AppImage 打包入口
prevent-sleep.desktop    # 可重定位桌面入口
```

## 许可证

MIT License

## 作者

[snailuu](https://github.com/snailuu)
