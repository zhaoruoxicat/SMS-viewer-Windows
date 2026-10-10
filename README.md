# Windows 安装包

应用源码保持不变。使用 Python 3.14 + PyInstaller 收集应用及 PySide6，
再通过 Inno Setup 6 生成 Windows 10/11 x64 安装程序。

安装包：`dist/sms-forward-client-1.0.3-windows-x64-setup.exe`。
安装到当前用户目录，无需预装 Python，也无需管理员权限。
开始菜单名称为“短信会话”，桌面快捷方式可在安装时勾选。
可通过 Windows 的“已安装的应用”卸载。

配置沿用现有逻辑：`%USERPROFILE%\.config\sms-forward-client\config.json`；
如设置 `XDG_CONFIG_HOME` 则使用该目录。卸载保留配置。
打包输入仅为程序依赖和 `logo.png`，不包含本机服务器配置或 Token。

## 重新构建

安装 Python 3.14 x64 和 Inno Setup 6，然后在项目根目录执行：

```powershell
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
Linux 权限位断言不适用于 Windows；Debian 打包测试需要 `dpkg-deb`。
Windows 上配置的保存读取由安装包烟雾测试另外验证。

## 上传 GitHub 的文件

Windows 与 Ubuntu 共享 `sms_client/` 源码。建议在当前仓库一并维护两种平台，
新增 Windows 打包文件即可，不必移除已经跟踪的 Ubuntu 文件。

如果单独建立 Windows 仓库，至少复制以下文件，并保留目录结构：

```text
.gitignore
requirements.txt
logo.png
sms_client/                  # 全部 .py 源文件，不含 __pycache__
build_windows.ps1
packaging/windows_entry.py
packaging/windows.iss
packaging/verify_windows.py
packaging/README-windows.md
tests/test_core.py
tests/test_app.py
```

独立仓库可将本说明复制为根目录 `README.md`。
Ubuntu 的 `build_deb.py`、`run.sh`、`install-desktop.sh`、
`tests/test_packaging.py` 不是 Windows 构建所必需的。

不要上传 `.venv/`、`build/`、`dist/`、`__pycache__/` 或真实 `config.json`。
安装包 `.exe` 及其 `.sha256` 校验文件可作为 GitHub Release 附件分发。
`.gitignore` 仅防止未跟踪文件被加入，不会自动移除已经跟踪的文件。
