"""Package application source and public assets, never private state."""
import argparse
from pathlib import Path
import re
import zipfile

SOURCE_FILES = (
    "app.py", "manage.py", "requirements.txt", "index.html",
    "wedding/__init__.py", "wedding/store.py",
    "templates/base.html", "templates/login.html", "templates/guest.html", "templates/error.html",
    "templates/admin.html", "templates/admin_login.html", "templates/admin_code.html",
)
ASSET_FILES = ("assets/site.css", "assets/site.js", "assets/favicon.svg")


def package(root, output, revision):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Expected a full Git commit SHA")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in SOURCE_FILES:
            if (root / name).is_symlink():
                raise ValueError("Source symlinks are not permitted")
            archive.write(root / name, name)
        for name in ASSET_FILES:
            if (root / name).is_symlink():
                raise ValueError("Asset symlinks are not permitted")
            archive.write(root / name, "public/"+name)
        archive.writestr("public/revision.txt", revision + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[1], args.output, args.revision)
