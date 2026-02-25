#!/usr/bin/env python3
"""Scan resources/ and generate resources/resources.qrc for Qt resource system."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

RESOURCES_DIR = Path(__file__).parent.parent / "resources"
OUTPUT_PATH = RESOURCES_DIR / "resources.qrc"

SKIP_DIRS = {".git", "__pycache__"}
SKIP_EXTENSIONS = {".pyc", ".qrc"}


def generate_qrc() -> None:
    root = ET.Element("RCC")
    root.set("version", "1.0")

    qresource = ET.SubElement(root, "qresource")
    qresource.set("prefix", "/")

    count = 0
    for path in sorted(RESOURCES_DIR.rglob("*")):
        if path.is_file() and path.suffix not in SKIP_EXTENSIONS:
            if not any(part in SKIP_DIRS for part in path.parts):
                rel = path.relative_to(RESOURCES_DIR)
                file_elem = ET.SubElement(qresource, "file")
                file_elem.text = str(rel)
                count += 1

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")

    with open(OUTPUT_PATH, "wb") as f:
        f.write(b'<!DOCTYPE RCC>\n')
        tree.write(f, encoding="utf-8", xml_declaration=False)

    print(f"Generated {OUTPUT_PATH} with {count} files.")


if __name__ == "__main__":
    generate_qrc()
