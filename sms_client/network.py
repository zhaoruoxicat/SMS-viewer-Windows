"""Non-blocking authenticated access to the existing PHP list API."""

import json

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .core import Settings, api_url, parse_records


class SmsApi(QObject):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self._reply = None

    @property
    def busy(self):
        return self._reply is not None

    def fetch(self, settings: Settings):
        if self.busy:
            return
        request = QNetworkRequest(QUrl(api_url(settings.server_url)))
        request.setRawHeader(b'Authorization', ('Bearer ' + settings.token).encode('utf-8'))
        request.setRawHeader(b'X-API-Token', settings.token.encode('utf-8'))
        request.setRawHeader(b'Accept', b'application/json')
        request.setRawHeader(b'Cache-Control', b'no-cache')
        request.setRawHeader(b'User-Agent', b'UbuntuSmsClient/1.0')
        # Do not forward credentials to redirects, even when same-origin.
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setTransferTimeout(12000)
        reply = self.manager.get(request)
        self._reply = reply
        reply.finished.connect(lambda: self._finish(reply))

    def cancel(self):
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.abort()

    def _finish(self, reply):
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        try:
            if status in (401, 403):
                raise ValueError('Token 无效、已禁用或未传入，请在设置中检查。')
            if status is not None and 300 <= status < 400:
                raise ValueError('接口发生重定向，请在设置中填写最终服务器地址。')
            if status is not None and status != 200:
                raise ValueError(f'服务器返回 HTTP {status}，请检查接口地址和服务器状态。')
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError('连接失败或超时，请检查网络、服务器地址和 HTTPS 证书。')
            try:
                payload = json.loads(bytes(reply.readAll()).decode('utf-8-sig'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError('接口未返回有效 JSON，请确认服务器地址对应短信 API。') from None
            records = parse_records(payload)
        except ValueError as exc:
            self.failed.emit(str(exc))
        else:
            self.loaded.emit(records)
        finally:
            reply.deleteLater()
