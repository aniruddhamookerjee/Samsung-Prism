#!/usr/bin/env python3
"""Builds and checks bundle/SAM.zip for the Track 3 submission.

    python tools/build_submission.py

Every file is taken from the last commit (git show HEAD:<path>), not from the
working folder: on Windows with core.autocrlf the working copies have CRLF
line endings, the committed ones LF. So commit first, then build, then commit
the zip. Without git it falls back to the working folder.
"""

import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP = "bundle/SAM.zip"
REQUIRED_FILES = [
    "src/main.py",
    "src/README.md",
    "estimated_trajectory.txt",
    "metadata.json",
    "requirements.txt",
    "Dockerfile",
    "presentation/SRMIST_KTR_SAM_Presentation.md",
    "presentation/SRMIST_KTR_SAM.pptx",
]


def committed(rel_path):
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:" + rel_path], capture_output=True, check=True)
        return r.stdout
    except (OSError, subprocess.CalledProcessError):
        p = ROOT / rel_path
        if not p.exists():
            raise FileNotFoundError(f"missing required submission file: {rel_path}")
        return p.read_bytes()


def build_bundle(zip_path=ZIP):
    out = ROOT / zip_path
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for rel in REQUIRED_FILES:
        data[rel] = committed(rel)
        print(f"  [OK] {rel} ({len(data[rel])} bytes)")

    for line in data["Dockerfile"].decode().splitlines():
        parts = line.split()
        if parts and parts[0] == "COPY":
            for src in parts[1:-1]:
                src = src.rstrip("/")
                if not any(rel == src or rel.startswith(src + "/") for rel in data):
                    raise ValueError(f"Dockerfile copies {src}, which is not in the bundle")
    print("  [OK] every Dockerfile COPY source is in the bundle")

    rows = [l.split() for l in data["estimated_trajectory.txt"].decode().splitlines()
            if l.strip() and not l.startswith("#")]
    if not rows or any(len(r) != 8 for r in rows):
        raise ValueError("estimated_trajectory.txt: every row must have 8 columns")
    print(f"  [OK] estimated_trajectory.txt: {len(rows)} rows of 8 columns")

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rel, b in data.items():
            z.writestr(rel, b)
    with zipfile.ZipFile(out) as z:
        assert all(z.read(rel) == b for rel, b in data.items())
    print(f"\nBuilt {out} ({out.stat().st_size >> 10} KB), contents checked against the last commit")


if __name__ == "__main__":
    build_bundle()
