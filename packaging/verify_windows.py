"""Install, exercise and uninstall the actual Windows package in a temporary directory."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import winreg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sms_client.core import ConfigStore, Settings


def main():
    installer = Path(sys.argv[1]).resolve()
    key = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4D82DB77-245D-48A6-BE7C-46C9F0AF7892}_is1'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise RuntimeError('An existing installation must not be overwritten by the smoke test')
    except FileNotFoundError:
        pass
    requests = []
    received = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization')))
            body = json.dumps({'success': True, 'records': [dict(
                id=1, phone='10690000', device='Windows test',
                content='验证码 012345', received_at='2026-10-10 12:00:00'
            )]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            received.set()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='windows-smoke-', dir=ROOT / 'build') as temporary:
            directory = Path(temporary)
            target = directory / 'installed'
            config = directory / 'config' / 'sms-forward-client' / 'config.json'
            store = ConfigStore(config)
            settings = Settings(f'http://127.0.0.1:{server.server_port}', 'packaging-test-token')
            store.save(settings)
            assert store.load() == settings
            store.save(settings)
            assert store.load() == settings
            config.write_text('{broken', encoding='utf-8')
            try:
                store.load()
                raise AssertionError('Corrupt config was accepted')
            except ValueError:
                pass
            store.save(settings)
            process = None
            try:
                subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                '/NORESTART', '/NOICONS', f'/DIR={target}',
                                f'/LOG={ROOT / "build/windows-install.log"}'],
                               check=True, timeout=120)
                source = ROOT / 'dist' / 'SmsForwardClient'
                for file in source.rglob('*'):
                    if file.is_file():
                        installed = target / file.relative_to(source)
                        assert hashlib.sha256(file.read_bytes()).digest() == hashlib.sha256(installed.read_bytes()).digest(), str(file)
                assert not list(target.rglob('config.json'))
                environment = dict(os.environ, XDG_CONFIG_HOME=str(directory / 'config'),
                                   QT_QPA_PLATFORM='offscreen')
                environment.pop('PYTHONPATH', None)
                environment.pop('PYTHONHOME', None)
                process = subprocess.Popen([str(target / 'SmsForwardClient.exe')],
                                           cwd=target, env=environment)
                assert received.wait(25), f'No API request; exit={process.poll()}'
                time.sleep(1)
                assert process.poll() is None, 'Application exited unexpectedly'
                assert requests[0] == ('/appapi/index.php?action=list', 'Bearer packaging-test-token'), requests
                print('PASS: config roundtrip, overwrite, corruption detection, installed payload hashes, bundled executable startup and authenticated HTTP request')
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                uninstaller = target / 'unins000.exe'
                if uninstaller.exists():
                    subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                    '/NORESTART', f'/LOG={ROOT / "build/windows-uninstall.log"}'],
                                   check=True, timeout=90)
                    deadline = time.monotonic() + 15
                    while (target / 'SmsForwardClient.exe').exists() and time.monotonic() < deadline:
                        time.sleep(0.2)
                    assert not (target / 'SmsForwardClient.exe').exists()
                    assert config.exists(), 'Uninstaller removed user config'
                    print('PASS: uninstall removes application and preserves user config')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
