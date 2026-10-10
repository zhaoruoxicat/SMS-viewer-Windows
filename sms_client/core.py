"""Server contract, local settings and safe SMS presentation."""

from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import parse_qsl, urlsplit, urlunsplit


def api_url(address: str) -> str:
    """Accept a server root or appapi endpoint, retaining deployment subpaths."""
    address = address.strip()
    if not address or any(ch.isspace() or ord(ch) < 32 for ch in address):
        raise ValueError('请输入完整服务器地址，例如 https://sms.example.com')
    try:
        parts = urlsplit(address)
        _ = parts.port  # Also validate the port syntax/range.
        if (parts.scheme not in ('http', 'https') or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.fragment or '\\' in address):
            raise ValueError
        if parts.query and parse_qsl(parts.query, keep_blank_values=True) != [('action', 'list')]:
            raise ValueError
    except ValueError:
        raise ValueError('地址需使用 http:// 或 https://，不能包含账号、Token 或锚点。') from None
    path = parts.path.rstrip('/')
    if path.endswith('/appapi/index.php'):
        pass
    elif path.endswith('/appapi'):
        path += '/index.php'
    else:
        path += '/appapi/index.php'
    return urlunsplit((parts.scheme, parts.netloc, path, 'action=list', ''))


@dataclass(frozen=True)
class Settings:
    server_url: str
    token: str

    def __post_init__(self):
        object.__setattr__(self, 'server_url', self.server_url.strip())
        api_url(self.server_url)
        token = self.token.strip()
        if not token or any(ord(ch) < 32 or ord(ch) == 127 for ch in self.token):
            raise ValueError('请输入有效 Token，不能包含换行或控制字符。')
        object.__setattr__(self, 'token', token)


class ConfigStore:
    def __init__(self, path: Path | None = None):
        root = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
        self.path = Path(path) if path is not None else root / 'sms-forward-client' / 'config.json'

    def load(self) -> Settings | None:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise ValueError('配置文件无法读取，请重新设置服务器地址和 Token。') from exc
        try:
            return Settings(data['server_url'], data['token'])
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            raise ValueError('配置文件内容无效，请重新设置服务器地址和 Token。') from exc

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=self.path.parent, delete=False) as file:
                temporary = Path(file.name)
                os.fchmod(file.fileno(), 0o600)
                json.dump({'server_url': settings.server_url, 'token': settings.token},
                          file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


URL_PATTERN = re.compile(r'(?:https?://|www\.)[^\s<>"\'，。；！？、【】《》]+', re.I)
PHONE_PATTERN = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
CODE_PATTERN = re.compile(r'(?<!\d)[0-9]{4,8}(?!\d)')


def url_spans(text: str):
    for match in URL_PATTERN.finditer(text):
        value = match.group()
        closing = {')': '(', ']': '[', '}': '{', '）': '（'}
        while value:
            tail = value[-1]
            if tail in '.,;:!?':
                value = value[:-1]
            elif tail in closing and value.count(tail) > value.count(closing[tail]):
                value = value[:-1]
            else:
                break
        if value:
            yield match.start(), match.start() + len(value), value


def extract_code(text: str) -> str | None:
    """PHP's keyword/4–8 digit rule, excluding codes embedded in URLs."""
    keyword = text.find('验证码')
    if keyword < 0:
        return None
    links = list(url_spans(text))
    candidates = [m for m in CODE_PATTERN.finditer(text)
                  if not any(start <= m.start() < end for start, end, _ in links)]
    start = max(0, keyword - 50)
    nearby = [m for m in candidates if start <= m.start() and m.end() <= start + 100]
    selected = nearby or candidates
    return selected[0].group() if selected else None


def content_html(text: str) -> str:
    """Tokenize before escaping so generated HTML cannot be re-matched."""
    code = extract_code(text)
    tokens = [(start, end, 'url', value) for start, end, value in url_spans(text)]
    for match in PHONE_PATTERN.finditer(text):
        if not any(start <= match.start() < end for start, end, _, _ in tokens):
            tokens.append((match.start(), match.end(), 'phone', match.group()))
    if code:
        for match in CODE_PATTERN.finditer(text):
            if match.group() == code and not any(
                    start <= match.start() < end for start, end, _, _ in tokens):
                tokens.append((match.start(), match.end(), 'code', code))
    fragments = []
    cursor = 0
    for start, end, kind, value in sorted(tokens):
        fragments.append(escape(text[cursor:start]))
        safe = escape(value, quote=True)
        if kind == 'code':
            fragments.append('<span style="background-color: #fff0b3; color: #9a5400; '
                             f'font-weight: 700;">{safe}</span>')
        else:
            target = ('tel:' + value if kind == 'phone' else
                      value if value.lower().startswith(('http://', 'https://')) else 'http://' + value)
            fragments.append(f'<a href="{escape(target, quote=True)}" '
                             f'style="color: #1976d2;">{safe}</a>')
        cursor = end
    fragments.append(escape(text[cursor:]))
    return ''.join(fragments).replace('\n', '<br>')


def parse_records(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or payload.get('success') is not True:
        raise ValueError('服务器返回失败，请检查接口地址和 Token。')
    rows = payload.get('records')
    if not isinstance(rows, list):
        raise ValueError('服务器响应格式不正确：缺少短信列表。')
    result = []
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('content'), str)
                or not isinstance(row.get('received_at'), str)):
            raise ValueError('服务器响应中存在无效短信记录。')
        item = {}
        for field in ('phone', 'device'):
            value = row.get(field)
            if value is not None and not isinstance(value, (str, int)):
                raise ValueError('服务器响应中存在无效短信记录。')
            item[field] = '' if value is None else str(value)
        try:
            item['id'] = int(row.get('id', 0))
        except (TypeError, ValueError, OverflowError):
            raise ValueError('服务器响应中存在无效短信编号。') from None
        item.update(content=row['content'], received_at=row['received_at'])
        result.append(item)
    result.sort(key=lambda r: (r['received_at'], r['id']), reverse=True)
    return result
