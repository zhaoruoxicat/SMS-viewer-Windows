"""Native desktop settings and PHP-inspired SMS conversation view."""

from datetime import datetime
from html import escape
import math

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextOption
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPushButton, QScrollArea, QSizePolicy,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .core import ConfigStore, Settings, content_html, extract_code
from .network import SmsApi


STYLE = """
QWidget { font-size: 14px; color: #263445; }
QMainWindow, QDialog { background: #f5f7fb; }
QWidget#scrollContents { background: #f5f7fb; }
QFrame#root { background: #f5f7fb; border: 1px solid #b8c6d9; }
QFrame#header { background: #ffffff; border-bottom: 1px solid #e4eaf2; }
QLabel#title { font-size: 24px; font-weight: 700; color: #172b4d; }
QLabel#subtitle, QLabel#count, QLabel#pageLabel { color: #6b7b90; }
QLabel#date { color: #8591a3; font-size: 12px; padding: 8px; }
QFrame#bubble { background: #ffffff; border: 1px solid #e4eaf2; border-radius: 14px; }
QTextBrowser#content { background: transparent; border: 0; font-size: 16px; }
QLabel#peer { color: #748195; font-size: 12px; }
QPushButton { background: #ffffff; border: 1px solid #d7e0ec;
    border-radius: 8px; padding: 8px 14px; color: #40536d; }
QPushButton:hover { background: #edf3fc; border-color: #b8cce8; }
QPushButton:pressed { background: #dceaff; }
QPushButton:disabled { background: #f2f4f7; color: #a0aab8; border-color: #e8ecf1; }
QPushButton#primary, QPushButton#copyCode { background: #1e88e5; color: white; border: 0; }
QPushButton#primary:hover, QPushButton#copyCode:hover { background: #1976d2; }
QPushButton#primary:disabled { background: #9fc5e9; }
QPushButton#copyCode, QPushButton#copyFull { font-size: 12px; padding: 6px 12px; }
QPushButton#copyFull { background: #f0f3f7; border: 0; color: #63758a; }
QLineEdit { background: white; border: 1px solid #d7e0ec;
    border-radius: 8px; padding: 10px; selection-background-color: #1e88e5; }
QLineEdit:focus { border-color: #1e88e5; }
QScrollArea { border: 0; background: #f5f7fb; }
QScrollBar:vertical { width: 10px; background: transparent; margin: 0; }
QScrollBar::handle:vertical { background: #c9d3df; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def plain_label(text='', parent=None):
    label = QLabel(text, parent)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class SettingsDialog(QDialog):
    def __init__(self, store: ConfigStore, settings: Settings | None = None, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.setWindowTitle('连接短信服务器')
        self.setMinimumWidth(480)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        title = plain_label('连接你的短信服务器')
        title.setObjectName('title')
        layout.addWidget(title)
        description = plain_label('输入 PHP 服务器地址和访问 Token。保存后将自动显示最新短信。')
        description.setObjectName('subtitle')
        layout.addWidget(description)
        layout.addSpacing(8)
        layout.addWidget(plain_label('服务器地址'))
        self.server_edit = QLineEdit(settings.server_url if settings else '')
        self.server_edit.setPlaceholderText('https://sms.example.com 或 https://example.com/sms/')
        self.server_edit.setClearButtonEnabled(True)
        layout.addWidget(self.server_edit)
        hint = plain_label('支持服务器根地址、子目录地址或 /appapi/index.php 接口地址。')
        hint.setObjectName('subtitle')
        layout.addWidget(hint)
        layout.addWidget(plain_label('访问 Token'))
        token_row = QHBoxLayout()
        self.token_edit = QLineEdit(settings.token if settings else '')
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText('输入服务器生成的 Token')
        token_row.addWidget(self.token_edit)
        self.show_token_button = QPushButton('显示')
        self.show_token_button.setCheckable(True)
        self.show_token_button.toggled.connect(self.toggle_token)
        token_row.addWidget(self.show_token_button)
        layout.addLayout(token_row)
        hint = plain_label('Token 将保存到本机用户配置文件，仅当前用户可读。')
        hint.setObjectName('subtitle')
        layout.addWidget(hint)
        self.error_label = plain_label()
        self.error_label.setStyleSheet('color: #c0392b;')
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                  QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存并连接')
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName('primary')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept_settings)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_token(self, visible):
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self.show_token_button.setText('隐藏' if visible else '显示')

    def accept_settings(self):
        try:
            settings = Settings(self.server_edit.text(), self.token_edit.text())
            self.store.save(settings)
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        except OSError:
            self.error_label.setText('无法保存配置，请检查配置目录的写入权限。')
            return
        self.settings = settings
        self.accept()


class MessageText(QTextBrowser):
    """Selectable rich text that wraps long links and expands inside the main scroll area."""

    def __init__(self, html, parent=None):
        super().__init__(parent)
        self.setObjectName('content')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.document().setDocumentMargin(0)
        option = self.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(option)
        self.document().contentsChanged.connect(self.fit_height)
        self.setHtml(html)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_height()

    def wheelEvent(self, event):
        # The text expands fully; let the surrounding SMS list handle scrolling.
        ancestor = self.parentWidget()
        while ancestor is not None and not isinstance(ancestor, QScrollArea):
            ancestor = ancestor.parentWidget()
        if ancestor is not None:
            QApplication.sendEvent(ancestor.viewport(), event)
        else:
            event.ignore()

    def fit_height(self):
        self.document().setTextWidth(max(1, self.viewport().width()))
        height = max(28, math.ceil(self.document().size().height()) + 2 * self.frameWidth())
        if self.height() != height:
            self.setFixedHeight(height)


class MessageCard(QWidget):
    copied = Signal(str)
    link_clicked = Signal(str)

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        peer = QLabel()
        peer.setObjectName('peer')
        peer.setTextFormat(Qt.TextFormat.RichText)
        peer.setWordWrap(True)
        peer.setText('<span style="color: #3b5bdb; font-weight: 600;">'
                     f'{escape(record["device"] or "设备")}</span>'
                     f' &nbsp; 来自 {escape(record["phone"] or "未知号码")}'
                     f' &nbsp; · {escape(record["received_at"])}')
        layout.addWidget(peer)
        bubble = QFrame()
        bubble.setObjectName('bubble')
        body = QVBoxLayout(bubble)
        body.setContentsMargins(18, 15, 18, 14)
        body.setSpacing(12)
        self.content_label = MessageText(content_html(record['content']))
        self.content_label.anchorClicked.connect(lambda url: self.link_clicked.emit(url.toString()))
        body.addWidget(self.content_label)
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.code_button = None
        code = extract_code(record['content'])
        if code:
            self.code_button = QPushButton(f'复制验证码  {code}')
            self.code_button.setObjectName('copyCode')
            self.code_button.clicked.connect(lambda: self.copy(code, '验证码已复制'))
            tools.addWidget(self.code_button)
        self.full_button = QPushButton('复制全文')
        self.full_button.setObjectName('copyFull')
        self.full_button.clicked.connect(lambda: self.copy(record['content'], '短信全文已复制'))
        tools.addWidget(self.full_button)
        tools.addStretch()
        body.addLayout(tools)
        layout.addWidget(bubble)

    def copy(self, value, message):
        QApplication.clipboard().setText(value)
        self.copied.emit(message)


class MainWindow(QMainWindow):
    PAGE_SIZE = 50

    def __init__(self, store=None):
        super().__init__()
        self.store = store or ConfigStore()
        self.settings = None
        self.config_error = ''
        try:
            self.settings = self.store.load()
        except ValueError as exc:
            self.config_error = str(exc)
        self.records = []
        self.page = 0
        self._render_version = 0
        self._status = '点击“设置”连接短信服务器。'
        self._status_error = False
        self.setWindowTitle('短信会话')
        self.resize(640, 760)
        self.setMinimumSize(480, 420)
        self.setStyleSheet(STYLE)
        root = QFrame()
        root.setObjectName('root')
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        titles = QVBoxLayout()
        title = plain_label('短信会话')
        title.setObjectName('title')
        titles.addWidget(title)
        subtitle = plain_label('最新短信 · 验证码一键复制')
        subtitle.setObjectName('subtitle')
        titles.addWidget(subtitle)
        header_layout.addLayout(titles, 1)
        self.refresh_button = QPushButton('立即刷新')
        self.refresh_button.setObjectName('primary')
        self.refresh_button.clicked.connect(self.refresh)
        header_layout.addWidget(self.refresh_button)
        self.settings_button = QPushButton('设置')
        self.settings_button.clicked.connect(self.configure)
        header_layout.addWidget(self.settings_button)
        layout.addWidget(header)
        info = QHBoxLayout()
        info.setContentsMargins(18, 14, 18, 8)
        self.count_label = plain_label('共 0 条短信')
        self.count_label.setObjectName('count')
        info.addWidget(self.count_label)
        info.addStretch()
        auto = plain_label('每 10 秒自动刷新 · 最新优先')
        auto.setObjectName('subtitle')
        auto.setWordWrap(False)
        info.addWidget(auto)
        layout.addLayout(info)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_contents = QWidget()
        scroll_contents.setObjectName('scrollContents')
        outer = QHBoxLayout(scroll_contents)
        outer.setContentsMargins(12, 0, 12, 12)
        outer.addStretch()
        self.messages = QWidget()
        self.messages.setMaximumWidth(760)
        self.messages.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.messages_layout = QVBoxLayout(self.messages)
        self.messages_layout.setContentsMargins(0, 0, 0, 0)
        self.messages_layout.setSpacing(16)
        outer.addWidget(self.messages, 1)
        outer.addStretch()
        self.scroll.setWidget(scroll_contents)
        layout.addWidget(self.scroll, 1)
        navigation = QHBoxLayout()
        navigation.setContentsMargins(12, 10, 12, 10)
        navigation.addStretch()
        self.first_button = QPushButton('最新短信')
        self.previous_button = QPushButton('上一页')
        self.next_button = QPushButton('下一页')
        self.page_label = plain_label()
        self.page_label.setObjectName('pageLabel')
        self.first_button.clicked.connect(lambda: self.change_page(0))
        self.previous_button.clicked.connect(lambda: self.change_page(self.page - 1))
        self.next_button.clicked.connect(lambda: self.change_page(self.page + 1))
        for widget in (self.first_button, self.previous_button, self.page_label, self.next_button):
            navigation.addWidget(widget)
        navigation.addStretch()
        layout.addLayout(navigation)
        self.status_label = plain_label()
        self.status_label.setContentsMargins(18, 4, 18, 16)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)
        self.api = SmsApi(self)
        self.api.loaded.connect(self.receive_records)
        self.api.failed.connect(self.receive_error)
        self.timer = QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self.refresh)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.restore_status)
        self.render()
        self.set_status(self.config_error or self._status, bool(self.config_error))

    def begin(self):
        if self.settings is None:
            self.configure()
        else:
            self.timer.start()
            self.refresh()

    def configure(self):
        self.timer.stop()
        dialog = SettingsDialog(self.store, self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.api.cancel()
            self.settings = dialog.settings
            self.records = []
            self.page = 0
            self.render()
            self.refresh()
        if self.settings is not None:
            self.timer.start()
        dialog.deleteLater()

    def refresh(self):
        if self.settings is None:
            self.set_status('请先点击“设置”，填写服务器地址和 Token。', True)
            return
        if self.api.busy:
            return
        self.refresh_button.setEnabled(False)
        self.set_status('正在加载短信…')
        self.api.fetch(self.settings)

    def receive_records(self, records):
        old = self.records
        scroll_position = self.scroll.verticalScrollBar().value()
        latest_changed = bool(records) and (not old or records[0] != old[0])
        self.records = records
        self.page = min(self.page, max(0, math.ceil(len(records) / self.PAGE_SIZE) - 1))
        if old != records or not records:
            self.render(0 if self.page == 0 and latest_changed else scroll_position)
        self.refresh_button.setEnabled(True)
        self.set_status(f'已同步 {len(records)} 条短信 · 更新于 {datetime.now():%H:%M:%S}')

    def receive_error(self, message):
        self.refresh_button.setEnabled(True)
        suffix = ' 已保留上次加载的短信。' if self.records else ''
        self.set_status(message + suffix, True)

    def change_page(self, page):
        total_pages = max(1, math.ceil(len(self.records) / self.PAGE_SIZE))
        self.page = max(0, min(page, total_pages - 1))
        self.render()

    def render(self, scroll_position=0):
        self._render_version += 1
        version = self._render_version
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.empty_label = None
        rows = self.records[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        last_date = None
        for record in rows:
            date = record['received_at'][:10]
            if date != last_date:
                divider = plain_label(date)
                divider.setObjectName('date')
                divider.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.messages_layout.addWidget(divider)
                last_date = date
            card = MessageCard(record)
            card.copied.connect(self.show_toast)
            card.link_clicked.connect(self.open_link)
            self.messages_layout.addWidget(card)
        if not rows:
            self.empty_label = plain_label('暂无短信记录' if self.settings else '连接服务器后，最新短信会显示在这里。')
            self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.empty_label.setStyleSheet('color: #8591a3; padding: 70px 0; font-size: 16px;')
            self.messages_layout.addWidget(self.empty_label)
        self.messages_layout.addStretch()
        pages = max(1, math.ceil(len(self.records) / self.PAGE_SIZE))
        self.count_label.setText(f'共 {len(self.records)} 条短信')
        self.page_label.setText(f'{self.page + 1} / {pages}')
        self.first_button.setEnabled(self.page > 0 or bool(rows))
        self.previous_button.setEnabled(self.page > 0)
        self.next_button.setEnabled(self.page + 1 < pages)

        def restore_scroll():
            if self._render_version == version:
                self.scroll.verticalScrollBar().setValue(scroll_position)

        QTimer.singleShot(0, restore_scroll)

    def set_status(self, text, error=False):
        self.toast_timer.stop()
        self._status, self._status_error = text, error
        self.restore_status()

    def restore_status(self):
        self.status_label.setText(self._status)
        self.status_label.setStyleSheet('color: #bd3b32;' if self._status_error else 'color: #748195;')

    def show_toast(self, message):
        self.status_label.setText(message)
        self.status_label.setStyleSheet('color: #218253;')
        self.toast_timer.start(1800)

    def open_link(self, link):
        url = QUrl(link)
        if not url.isValid() or url.scheme().lower() not in ('http', 'https', 'tel'):
            return
        if not QDesktopServices.openUrl(url):
            self.show_toast('无法打开链接，请检查系统默认浏览器或拨号程序。')

    def closeEvent(self, event):
        self.timer.stop()
        self.api.cancel()
        super().closeEvent(event)
