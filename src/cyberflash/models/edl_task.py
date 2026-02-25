from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EdlTask:
    device_serial: str        # "edl:0" (as assigned by EdlManager)
    profile_codename: str     # "guacamole" etc.
    package_dir: Path         # directory containing rawprogram0.xml, .bin images
    programmer: Path          # .elf programmer absolute path
    rawprogram_xml: Path      # absolute path
    patch_xml: Path | None    # absolute path or None
    dry_run: bool = False
    log_lines: list[str] = field(default_factory=list)
