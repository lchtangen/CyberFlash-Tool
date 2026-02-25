#!/usr/bin/env python3
"""Interactive CLI to scaffold a new device JSON profile."""

from __future__ import annotations

import json
from pathlib import Path


PROFILES_DIR = Path(__file__).parent.parent / "resources" / "profiles"


def prompt(question: str, default: str = "") -> str:
    if default:
        answer = input(f"{question} [{default}]: ").strip()
        return answer or default
    return input(f"{question}: ").strip()


def main() -> None:
    print("CyberFlash — Device Profile Creator")
    print("=" * 40)

    codename = prompt("Device codename (e.g. guacamole)").lower().replace(" ", "_")
    name = prompt("Device full name (e.g. OnePlus 7 Pro)")
    brand = prompt("Brand (e.g. OnePlus)")
    model = prompt("Model number (e.g. GM1917)")
    android_versions = prompt("Supported Android versions (comma-separated, e.g. 11,12,13)")
    bootloader_cmd = prompt("Bootloader unlock command", "fastboot oem unlock")
    notes = prompt("Notes (optional)", "")

    profile = {
        "codename": codename,
        "name": name,
        "brand": brand,
        "model": model,
        "android_versions": [v.strip() for v in android_versions.split(",") if v.strip()],
        "bootloader": {
            "unlock_command": bootloader_cmd,
            "requires_oem_unlock": True,
        },
        "flash": {
            "method": "fastboot",
            "partitions": [],
        },
        "notes": notes,
    }

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROFILES_DIR / f"{codename}.json"

    if output_path.exists():
        overwrite = prompt(f"Profile {output_path.name} already exists. Overwrite? (y/n)", "n")
        if overwrite.lower() != "y":
            print("Aborted.")
            return

    with open(output_path, "w") as f:
        json.dump(profile, f, indent=2)
        f.write("\n")

    print(f"\nProfile created: {output_path}")


if __name__ == "__main__":
    main()
