import argparse
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __version__
from .ui import MainWindow


def main():
    parser = argparse.ArgumentParser(description='Ubuntu 短信会话客户端')
    parser.add_argument('--version', action='version', version=__version__)
    parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName('sms-forward-client')
    app.setApplicationDisplayName('短信会话')
    app.setOrganizationName('SmsForwardClient')
    app.setDesktopFileName('sms-forward-client')
    app.setStyle('Fusion')
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / 'logo.png')))
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.begin)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
