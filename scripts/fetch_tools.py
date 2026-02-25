#!/usr/bin/env python3
"""Download platform-tools (adb, fastboot) from Google's official URL."""

from __future__ import annotations

import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

import requests

PLATFORM_TOOLS_URLS = {
    "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
    "macos": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
    "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
}

RESOURCES_DIR = Path(__file__).parent.parent / "resources" / "tools"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_platform_tools(platform: str) -> None:
    url = PLATFORM_TOOLS_URLS.get(platform)
    if url is None:
        print(f"Unknown platform: {platform}")
        sys.exit(1)

    dest_dir = RESOURCES_DIR / platform
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dest_dir / "platform-tools.zip"
    print(f"Downloading platform-tools for {platform}...")
    print(f"  URL: {url}")

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0

    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded / total * 100
                print(f"\r  {pct:.1f}% ({downloaded // 1024 // 1024} MB)", end="", flush=True)

    print(f"\n  SHA-256: {sha256_file(zip_path)}")
    print("  Extracting...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    # Move platform-tools/* up one level
    extracted = dest_dir / "platform-tools"
    if extracted.exists():
        for item in extracted.iterdir():
            shutil.move(str(item), str(dest_dir / item.name))
        extracted.rmdir()

    zip_path.unlink()
    print(f"  Done. Tools installed to: {dest_dir}")


def main() -> None:
    platforms = sys.argv[1:] if len(sys.argv) > 1 else list(PLATFORM_TOOLS_URLS)
    for platform in platforms:
        download_platform_tools(platform)


if __name__ == "__main__":
    main()
