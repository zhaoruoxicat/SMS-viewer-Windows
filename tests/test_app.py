import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from sms_client.core import ConfigStore, Settings
from sms_client.network import SmsApi
from sms_client.ui import MainWindow, MessageCard, SettingsDialog


APP = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def record(number, content=None):
    return dict(id=number, phone='10690000', device='测试手机',
                content=content or f'验证码 {number + 100000}，请勿泄露',
                received_at='2026-10-10 12:00:00')


class FixtureServer:
    def __init__(self):
        self.requests = []
        self.status = 200
        self.body = dict(success=True, action='list', total=2,
                         server_time='2026-10-10 12:00:01', records=[record(1), record(2)])
        self.delay = 0
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.requests.append((self.path, dict(self.headers)))
                status, body, delay = fixture.status, fixture.body, fixture.delay
                if delay:
                    time.sleep(delay)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                if status == 302:
                    self.send_header('Location', '/elsewhere')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}/sms'

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.server = FixtureServer()
        self.api = SmsApi()
        self.successes = []
        self.failures = []
        self.api.loaded.connect(self.successes.append)
        self.api.failed.connect(self.failures.append)

    def tearDown(self):
        self.api.cancel()
        self.api.deleteLater()
        APP.processEvents()
        self.server.close()

    def fetch_and_wait(self):
        self.api.fetch(Settings(self.server.url, 'test-secret'))
        self.assertTrue(wait_until(lambda: self.successes or self.failures))

    def test_auth_headers_and_list_endpoint_return_latest_first(self):
        self.fetch_and_wait()
        path, headers = self.server.requests[0]
        self.assertEqual(path, '/sms/appapi/index.php?action=list')
        self.assertEqual(headers['Authorization'], 'Bearer test-secret')
        # Qt normalizes header case; HTTP header names are case-insensitive.
        self.assertEqual({k.lower(): v for k, v in headers.items()}['x-api-token'], 'test-secret')
        self.assertNotIn('test-secret', path)
        self.assertEqual([r['id'] for r in self.successes[0]], [2, 1])

    def test_invalid_token_has_actionable_error(self):
        self.server.status = 403
        self.server.body = dict(success=False, error='invalid_token', message='Token is invalid or disabled.')
        self.fetch_and_wait()
        self.assertFalse(self.successes)
        self.assertIn('Token', self.failures[0])

    def test_html_response_is_reported_without_crash(self):
        self.server.body = b'<html>login</html>'
        self.fetch_and_wait()
        self.assertIn('JSON', self.failures[0])

    def test_redirect_is_not_followed_with_credentials(self):
        self.server.status = 302
        self.fetch_and_wait()
        self.assertEqual(len(self.server.requests), 1)
        self.assertIn('重定向', self.failures[0])

    def test_cancellation_discards_stale_result_and_allows_new_fetch(self):
        self.server.delay = 0.2
        self.api.fetch(Settings(self.server.url, 'first'))
        self.assertTrue(wait_until(lambda: len(self.server.requests) == 1))
        self.api.cancel()
        self.server.delay = 0
        self.server.body = dict(success=True, records=[record(5)])
        self.fetch_and_wait()
        wait_until(lambda: False, timeout=0.3)
        self.assertEqual(len(self.successes), 1)
        self.assertEqual(self.successes[0][0]['id'], 5)
        self.assertFalse(self.failures)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = ConfigStore(Path(self.directory.name) / 'config' / 'config.json')
        self.store.save(Settings('https://example.com', 'saved-token'))
        self.window = MainWindow(self.store)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self.directory.cleanup()

    def test_first_run_dialog_saves_and_masks_token(self):
        fresh = ConfigStore(Path(self.directory.name) / 'fresh' / 'config.json')
        dialog = SettingsDialog(fresh)
        dialog.server_edit.setText('https://example.com/sms')
        dialog.token_edit.setText('fresh-token')
        self.assertEqual(dialog.token_edit.echoMode(), dialog.token_edit.EchoMode.Password)
        dialog.accept_settings()
        self.assertEqual(fresh.load(), Settings('https://example.com/sms', 'fresh-token'))
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        dialog.deleteLater()

    def test_window_and_settings_edges_are_opaque_without_transparent_gaps(self):
        dialog = SettingsDialog(self.store)
        dialog.show()
        APP.processEvents()
        try:
            for window in (self.window, dialog):
                with self.subTest(window=type(window).__name__):
                    image = window.grab().toImage()
                    for x, y in ((0, 0), (image.width() - 1, 0),
                                 (0, image.height() - 1),
                                 (image.width() - 1, image.height() - 1),
                                 (16, image.height() // 2)):
                        self.assertEqual(image.pixelColor(x, y).alpha(), 255)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_invalid_settings_keep_dialog_open_and_do_not_save(self):
        dialog = SettingsDialog(self.store)
        dialog.server_edit.setText('invalid')
        dialog.token_edit.setText('new-token')
        dialog.accept_settings()
        self.assertEqual(dialog.result(), dialog.DialogCode.Rejected)
        self.assertTrue(dialog.error_label.text())
        self.assertEqual(self.store.load().token, 'saved-token')
        dialog.deleteLater()

    def test_newest_display_clipboard_and_highlight(self):
        from sms_client.core import parse_records
        self.window.receive_records(parse_records(dict(success=True, records=[record(1), record(2)])))
        cards = self.window.findChildren(MessageCard)
        self.assertEqual(cards[0].record['id'], 2)
        self.assertIn('background-color:', cards[0].content_label.toHtml())
        cards[0].code_button.click()
        self.assertEqual(APP.clipboard().text(), '100002')
        cards[0].full_button.click()
        self.assertEqual(APP.clipboard().text(), '验证码 100002，请勿泄露')

    def test_pagination_and_refresh_preserve_history_page(self):
        rows = [record(n) for n in range(110, 0, -1)]
        self.window.receive_records(rows)
        self.assertEqual(len(self.window.findChildren(MessageCard)), 50)
        self.window.next_button.click()
        APP.processEvents()
        self.assertEqual(self.window.page, 1)
        cards = self.window.findChildren(MessageCard)
        self.assertEqual(cards[0].record['id'], 60)
        self.window.receive_records([record(111)] + rows)
        self.assertEqual(self.window.page, 1)
        self.window.first_button.click()
        APP.processEvents()
        self.assertEqual(self.window.findChildren(MessageCard)[0].record['id'], 111)

    def test_error_preserves_visible_content_and_exposes_recovery(self):
        self.window.receive_records([record(1)])
        self.window.receive_error('Token 无效，请检查设置。')
        self.assertEqual(len(self.window.findChildren(MessageCard)), 1)
        self.assertIn('Token', self.window.status_label.text())
        self.assertTrue(self.window.refresh_button.isEnabled())
        self.window.receive_records([])
        self.assertIn('暂无短信', self.window.empty_label.text())

    def test_only_http_https_and_tel_links_are_opened(self):
        # The only mocked boundary is launching another desktop application.
        with patch('sms_client.ui.QDesktopServices.openUrl', return_value=True) as open_url:
            self.window.open_link('https://example.com/test')
            self.window.open_link('javascript:alert(1)')
            self.window.open_link('file:///etc/passwd')
            self.assertEqual(open_url.call_count, 1)
            self.assertEqual(open_url.call_args.args[0], QUrl('https://example.com/test'))

    def test_long_unbroken_url_wraps_without_losing_sms_text(self):
        content = '长链接 https://example.com/' + 'a' * 500 + '\n验证码 123456'
        self.window.resize(560, 600)
        self.window.receive_records([record(1, content)])
        APP.processEvents()
        view = self.window.findChildren(MessageCard)[0].content_label
        self.assertEqual(view.document().toPlainText(), content)
        layout = view.document().begin().layout()
        self.assertGreater(layout.lineCount(), 3)
        for index in range(layout.lineCount()):
            self.assertLessEqual(layout.lineAt(index).naturalTextWidth(), view.viewport().width() + 1)
        self.assertGreaterEqual(view.height(), view.document().size().height())

    def test_narrowing_window_keeps_all_wrapped_sms_lines_visible(self):
        content = ('【服务通知】您的账单已生成，详情请访问 '
                   'https://example.com/bill?id=202610。如有疑问，请联系 13800138000。')
        self.window.receive_records([record(number, content) for number in range(5, 0, -1)])
        for _ in range(10):
            APP.processEvents()
        self.window.resize(480, 760)
        for _ in range(10):
            APP.processEvents()
        for card in self.window.findChildren(MessageCard):
            view = card.content_label
            self.assertGreaterEqual(view.viewport().height(), view.document().size().height())

    def test_timer_automatically_loads_new_sms(self):
        server = FixtureServer()
        try:
            self.window.settings = Settings(server.url, 'auto-token')
            self.window.timer.setInterval(60)
            self.window.begin()
            self.assertTrue(wait_until(lambda: len(self.window.records) == 2))
            server.body = dict(success=True, records=[record(20)])
            self.assertTrue(wait_until(lambda: self.window.records[0]['id'] == 20))
        finally:
            self.window.timer.stop()
            self.window.api.cancel()
            server.close()

    def test_mouse_wheel_over_sms_scrolls_the_message_list(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtGui import QWheelEvent
        self.window.receive_records([record(number) for number in range(20, 0, -1)])
        self.assertTrue(wait_until(lambda: self.window.scroll.verticalScrollBar().maximum() > 0))
        view = self.window.findChildren(MessageCard)[0].content_label.viewport()
        event = QWheelEvent(QPointF(20, 20), QPointF(view.mapToGlobal(QPoint(20, 20))),
                            QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        APP.sendEvent(view, event)
        APP.processEvents()
        self.assertGreater(self.window.scroll.verticalScrollBar().value(), 0)

    def test_settings_switch_discards_inflight_old_server_response(self):
        from PySide6.QtCore import QTimer
        old_server, new_server = FixtureServer(), FixtureServer()
        try:
            old_server.delay = 0.25
            new_server.body = dict(success=True, records=[record(88)])
            self.window.settings = Settings(old_server.url, 'old-token')
            self.window.refresh()
            self.assertTrue(wait_until(lambda: bool(old_server.requests)))

            def save_new_settings():
                dialog = APP.activeModalWidget()
                dialog.server_edit.setText(new_server.url)
                dialog.token_edit.setText('new-token')
                dialog.accept_settings()

            QTimer.singleShot(0, save_new_settings)
            self.window.configure()
            self.assertTrue(wait_until(lambda: bool(self.window.records)))
            wait_until(lambda: False, timeout=0.3)
            self.assertEqual(self.window.records[0]['id'], 88)
            self.assertEqual(self.store.load().token, 'new-token')
        finally:
            self.window.timer.stop()
            self.window.api.cancel()
            old_server.close()
            new_server.close()

    def test_window_fetches_and_recovers_from_real_http_failure(self):
        server = FixtureServer()
        try:
            self.window.settings = Settings(server.url, 'window-token')
            self.window.refresh()
            self.assertTrue(wait_until(lambda: len(self.window.records) == 2))
            server.status = 403
            self.window.refresh()
            self.assertTrue(wait_until(lambda: 'Token' in self.window.status_label.text()))
            self.assertEqual(len(self.window.records), 2)
            server.status = 200
            server.body = dict(success=True, records=[record(9)])
            self.window.refresh()
            self.assertTrue(wait_until(lambda: self.window.records[0]['id'] == 9))
            self.assertTrue(self.window.refresh_button.isEnabled())
        finally:
            self.window.api.cancel()
            server.close()


if __name__ == '__main__':
    unittest.main()
