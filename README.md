# SMS Viewer Windows

Windows 短信会话客户端，连接现有 PHP 短信转发服务器，支持自动刷新、分页和验证码复制。
本项目独立维护 Windows 版本。使用 Python 3.14 + PyInstaller 收集应用及 PySide6，
再通过 Inno Setup 6 生成 Windows 10/11 x64 安装程序。

安装包：`dist/sms-forward-client-1.0.3-windows-x64-setup.exe`。
安装到当前用户目录，无需预装 Python，也无需管理员权限。
开始菜单名称为“短信会话”，桌面快捷方式可在安装时勾选。
可通过 Windows 的“已安装的应用”卸载。

配置沿用现有逻辑：`%USERPROFILE%\.config\sms-forward-client\config.json`；
如设置 `XDG_CONFIG_HOME` 则使用该目录。卸载保留配置。
打包输入仅为程序依赖和 `logo.png`，不包含本机服务器配置或 Token。

## 重新构建

安装 Python 3.14 x64 和 Inno Setup 6，然后执行：

```powershell
git clone https://github.com/zhaoruoxicat/SMS-viewer-Windows.git
cd SMS-viewer-Windows
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.21.0 pillow==12.3.0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
```

脚本默认从 `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` 查找编译器，
可通过 `-ISCC` 指定其他路径，通过 `-Python` 指定 Python 解释器。
本次使用 Python 3.14.6、PySide6 6.12.0、PyInstaller 6.21.0。
Python 3.14 提供应用需要的 Windows `os.fchmod` 支持，不要使用更旧版本打包。

`dist/SmsForwardClient/` 是可直接运行的完整程序目录；必须保留整个目录。
同名 `.exe.sha256` 文件用于校验安装包。安装包未进行代码签名。

## 测试说明

原有测试可通过 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 运行。
现有核心测试包含 Linux 权限位断言，在 Windows 上该断言会失败。
Windows 上配置的保存读取可通过安装包烟雾测试另外验证：

```powershell
.\.venv\Scripts\python.exe packaging\verify_windows.py dist\sms-forward-client-1.0.3-windows-x64-setup.exe
```

烟雾测试会临时安装应用、连接本机测试接口并卸载；如已安装同一应用，测试会拒绝覆盖。

## 上传 GitHub 的文件

本仓库包含以下源码、构建文件和测试：

```text
.gitignore
README.md
requirements.txt
logo.png
sms_client/                  # 全部 .py 源文件，不含 __pycache__
build_windows.ps1
packaging/windows_entry.py
packaging/windows.iss
packaging/verify_windows.py
tests/test_core.py
tests/test_app.py
```

Ubuntu 的构建脚本和 Debian 打包测试不包含在本仓库中。

不要上传 `.venv/`、`build/`、`dist/`、`__pycache__/` 或真实 `config.json`。
安装包 `.exe` 及其 `.sha256` 校验文件可作为 GitHub Release 附件分发。
`.gitignore` 仅防止未跟踪文件被加入，不会自动移除已经跟踪的文件。
