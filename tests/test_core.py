import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from sms_client.core import (
    ConfigStore, Settings, api_url, content_html, extract_code, parse_records,
)


class CoreTests(unittest.TestCase):
    def test_api_url_preserves_subdirectory_and_accepts_endpoint(self):
        for address in ('https://example.com/sms', 'https://example.com/sms/',
                        'https://example.com/sms/appapi/',
                        'https://example.com/sms/appapi/index.php?action=list'):
            with self.subTest(address=address):
                self.assertEqual(api_url(address),
                                 'https://example.com/sms/appapi/index.php?action=list')

    def test_invalid_or_credential_bearing_urls_are_rejected(self):
        for address in ('', 'example.com', 'file:///tmp/a', 'https://a:b@example.com',
                        'https://example.com/?token=secret', 'https://example.com/#a',
                        'https://example.com:wrong', 'https://example.com/ bad'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                api_url(address)

    def test_config_roundtrip_permissions_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config' / 'config.json'
            store = ConfigStore(path)
            self.assertIsNone(store.load())
            settings = Settings('https://example.com/sms', 'token-测试')
            store.save(settings)
            self.assertEqual(ConfigStore(path).load(), settings)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            path.write_text('{broken')
            with self.assertRaises(ValueError):
                store.load()

    def test_configuration_rejects_empty_or_header_injecting_token(self):
        for token in ('', ' \t ', 'abc\r\nX-Other: value', 'abc\x00'):
            with self.subTest(token=token), self.assertRaises(ValueError):
                Settings('https://example.com', token)

    def test_extracts_codes_near_keyword_without_phone_or_url_digits(self):
        cases = (
            ('【银行】验证码：012345，请勿泄露。', '012345'),
            ('654321 是您的验证码。', '654321'),
            ('联系 13800138000，验证码 4567', '4567'),
            ('请访问 https://example.com/123456，验证码：876543', '876543'),
            ('订单号12345678' + '文' * 60 + '验证码 456789', '456789'),
            ('验证码：123456789', None),
            ('验证码请访问 www.example.com/123456', None),
            ('订单 123456 已发货', None),
        )
        for content, expected in cases:
            with self.subTest(content=content):
                self.assertEqual(extract_code(content), expected)

    def test_html_escapes_untrusted_text_and_keeps_links_and_code_separate(self):
        html = content_html('<script>alert(1)</script>\n验证码 012345。'
                            ' https://example.com/a?q=1&b=2。 www.example.com 13800138000')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('<br>', html)
        self.assertIn('background-color:', html)
        self.assertIn('>012345</span>', html)
        self.assertIn('href="https://example.com/a?q=1&amp;b=2"', html)
        self.assertIn('href="http://www.example.com"', html)
        self.assertIn('href="tel:13800138000"', html)
        self.assertNotIn('href="javascript:', content_html('javascript:alert(1)'))

    def test_parse_records_orders_timestamp_then_numeric_id(self):
        rows = [
            dict(id='9', content='较早', received_at='2026-10-09 12:00:00', phone='1', device=None),
            dict(id='10', content='新', received_at='2026-10-10 12:00:00', phone=None, device='手机'),
            dict(id='11', content='最新', received_at='2026-10-10 12:00:00', phone='2', device=''),
        ]
        parsed = parse_records(dict(success=True, records=rows, total=3))
        self.assertEqual([r['content'] for r in parsed], ['最新', '新', '较早'])
        self.assertEqual(parsed[1]['phone'], '')
        self.assertEqual(parsed[2]['device'], '')

    def test_url_keeps_balanced_parentheses_but_trims_surrounding_punctuation(self):
        html = content_html('参考 (https://example.com/Function_(math))。')
        self.assertIn('href="https://example.com/Function_(math)"', html)
        self.assertIn('</a>)。', html)

    def test_malformed_api_payload_is_rejected(self):
        for payload in ([], {}, {'success': False, 'message': 'invalid'},
                        {'success': True, 'records': 'bad'},
                        {'success': True, 'records': [None]},
                        {'success': True, 'records': [{'content': [], 'received_at': 'x'}]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_records(payload)


if __name__ == '__main__':
    unittest.main()
