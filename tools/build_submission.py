#!/usr/bin/env python3
"""Builds and validates team_name.zip bundle for Samsung PRISM Hackathon Track 3 submission."""

import json
import zipfile
from pathlib import Path

REQUIRED_FILES = [
    "src/main.py",
    "src/README.md",
    "estimated_trajectory.txt",
    "metadata.json",
    "requirements.txt",
    "Dockerfile",
    "presentation/CollegeName_TeamName_Presentation.md",
    "presentation/CollegeName_TeamName.pptx",
]

def build_bundle(zip_path="bundle/team_name.zip"):
    root = Path(__file__).resolve().parent.parent
    zip_out = root / zip_path
    zip_out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Validating required submission assets in {root}...")
    for rel_path in REQUIRED_FILES:
        target = root / rel_path
        if not target.exists():
            raise FileNotFoundError(f"Missing required submission file: {rel_path}")
        print(f"  [OK] Found {rel_path} ({target.stat().st_size} bytes)")

    # Verify estimated_trajectory.txt formatting
    est_path = root / "estimated_trajectory.txt"
    with open(est_path, "r") as f:
        first_line = f.readline()
        second_line = f.readline().split()
        if len(second_line) != 8:
            raise ValueError(f"estimated_trajectory.txt row has {len(second_line)} columns, expected 8")
    print("  [OK] Validated estimated_trajectory.txt structure (8 space-separated columns)")

    # Build zip archive
    with zipfile.ZipFile(zip_out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rel_path in REQUIRED_FILES:
            file_path = root / rel_path
            z.write(file_path, arcname=rel_path)
            print(f"  [ARCHIVED] {rel_path}")

    print(f"\nSuccessfully generated submission bundle: {zip_out} ({zip_out.stat().st_size >> 10} KB)")

if __name__ == "__main__":
    build_bundle()
