"""Build the static release, excluding Git, credentials and deployment tools."""
import argparse
from pathlib import Path
import re
import zipfile


def package(root, output, revision):
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Expected a full Git commit SHA")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(root / "index.html", "public/index.html")
        archive.writestr("public/revision.txt", revision + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[1], args.output, args.revision)
