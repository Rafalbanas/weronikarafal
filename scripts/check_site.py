"""Check local assets, fragments and inline JavaScript without external APIs."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit


class Site(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.urls = []
        self.scripts = []
        self.script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            if attrs["id"] in self.ids:
                raise ValueError("Duplicate HTML id: " + attrs["id"])
            self.ids.add(attrs["id"])
        for name in ("src", "href"):
            if attrs.get(name):
                self.urls.append(attrs[name])
        if tag == "script" and not attrs.get("src"):
            self.script = []

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append("".join(self.script))
            self.script = None


def check(root):
    site = Site()
    site.feed((root / "index.html").read_text())
    for url in site.urls:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc:
            continue
        if parsed.path:
            if not (root / unquote(parsed.path).lstrip("/")).is_file():
                raise ValueError("Missing asset: " + url)
        elif parsed.fragment and parsed.fragment not in site.ids:
            raise ValueError("Missing fragment: " + url)
    with tempfile.TemporaryDirectory() as directory:
        for index, script in enumerate(site.scripts):
            path = Path(directory) / f"inline-{index}.js"
            path.write_text(script)
            subprocess.run(["node", "--check", str(path)], check=True)
    print("HTML assets, anchors and inline JavaScript OK")


if __name__ == "__main__":
    check(Path(__file__).resolve().parents[1])
