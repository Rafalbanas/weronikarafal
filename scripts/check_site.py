"""Render the public page and validate routes, assets, fragments and JavaScript."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app


class Site(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                raise ValueError('Duplicate HTML id: '+attrs['id'])
            self.ids.add(attrs['id'])
        for name in ('src', 'href'):
            if attrs.get(name):
                self.urls.append(attrs[name])


def check(root):
    with tempfile.TemporaryDirectory() as directory:
        app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only-'+'x'*40,
            'DATABASE': str(Path(directory)/'guests.sqlite3'),
            'DETAILS': str(Path(directory)/'details.json'), 'TRUSTED_HOSTS': ['localhost'], 'TRUST_PROXY': False})
        client = app.test_client()
        response = client.get('/', base_url='https://localhost')
        if response.status_code != 200:
            raise ValueError('Public page failed to render')
        site = Site()
        site.feed(response.text)
        for url in site.urls:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc:
                continue
            if parsed.path:
                asset = client.get(parsed.path, base_url='https://localhost')
                if asset.status_code != 200:
                    raise ValueError('Missing local asset or route: '+url)
            elif parsed.fragment and parsed.fragment not in site.ids:
                raise ValueError('Missing fragment: '+url)
        for script in (root/'assets').glob('*.js'):
            subprocess.run(['node', '--check', str(script)], check=True)
    print('Rendered public page, local assets, anchors and JavaScript OK')


if __name__ == '__main__':
    check(ROOT)
