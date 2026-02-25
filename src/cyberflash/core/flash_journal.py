"""flash_journal.py — Persistent flash operation history journal.

Records every flash/root/backup operation with timing, device info, and
outcome.  Supports search, filtering, and CSV/HTML export.

All file I/O uses a simple read-modify-write with an optional file lock.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_JOURNAL_DIR = Path.home() / ".cyberflash"
_DEFAULT_JOURNAL_FILE = _DEFAULT_JOURNAL_DIR / "flash_journal.json"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class JournalEntry:
    """A single recorded flash operation."""

    id: str
    timestamp: str          # ISO-8601
    serial: str
    model: str
    operation: str          # e.g. "flash", "root", "backup"
    steps: list[str] = field(default_factory=list)
    success: bool = False
    duration_s: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "serial": self.serial,
            "model": self.model,
            "operation": self.operation,
            "steps": self.steps,
            "success": self.success,
            "duration_s": self.duration_s,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> JournalEntry:
        return cls(
            id=str(d.get("id", "")),
            timestamp=str(d.get("timestamp", "")),
            serial=str(d.get("serial", "")),
            model=str(d.get("model", "")),
            operation=str(d.get("operation", "")),
            steps=list(d.get("steps", [])),  # type: ignore[arg-type]
            success=bool(d.get("success", False)),
            duration_s=float(d.get("duration_s", 0.0)),
            notes=str(d.get("notes", "")),
        )


# ── Main class ────────────────────────────────────────────────────────────────


class FlashJournal:
    """Persistent flash operation journal backed by a JSON file."""

    def __init__(self, journal_path: Path) -> None:
        self._path = journal_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Class method constructor ──────────────────────────────────────────────

    @classmethod
    def default(cls) -> FlashJournal:
        """Return a FlashJournal instance using the default path."""
        return cls(_DEFAULT_JOURNAL_FILE)

    # ── I/O helpers ───────────────────────────────────────────────────────────

    def _load_raw(self) -> list[dict[str, object]]:
        """Load raw JSON list from disk, returning [] on any error."""
        if not self._path.exists():
            return []
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("FlashJournal: could not load %s: %s", self._path, exc)
            return []

    def _save_raw(self, entries: list[dict[str, object]]) -> None:
        """Atomically write *entries* as JSON (write tmp then rename)."""
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except OSError as exc:
            logger.error("FlashJournal: write failed: %s", exc)
            tmp.unlink(missing_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def append(self, entry: JournalEntry) -> None:
        """Append *entry* to the journal (atomic read-modify-write)."""
        entries = self._load_raw()
        entries.append(entry.to_dict())
        self._save_raw(entries)

    def load_all(self) -> list[JournalEntry]:
        """Load all journal entries, newest-first."""
        raw = self._load_raw()
        result = []
        for d in raw:
            try:
                result.append(JournalEntry.from_dict(d))
            except Exception as exc:
                logger.debug("Skipping malformed journal entry: %s", exc)
        result.sort(key=lambda e: e.timestamp, reverse=True)
        return result

    def search(
        self,
        serial: str | None = None,
        operation: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[JournalEntry]:
        """Return entries matching all provided filters."""
        entries = self.load_all()
        if serial:
            entries = [e for e in entries if e.serial == serial]
        if operation:
            entries = [e for e in entries if e.operation == operation]
        if date_from:
            entries = [e for e in entries if e.timestamp >= date_from]
        if date_to:
            # Inclusive end: add one day's width if only date portion
            entries = [e for e in entries if e.timestamp <= date_to + "Z"]
        return entries

    def export_csv(self, dest: Path) -> bool:
        """Export journal to *dest* as CSV.  Returns True on success."""
        entries = self.load_all()
        try:
            with open(dest, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "id", "timestamp", "serial", "model",
                        "operation", "success", "duration_s", "notes",
                    ],
                )
                writer.writeheader()
                for e in entries:
                    writer.writerow({
                        "id": e.id,
                        "timestamp": e.timestamp,
                        "serial": e.serial,
                        "model": e.model,
                        "operation": e.operation,
                        "success": e.success,
                        "duration_s": e.duration_s,
                        "notes": e.notes,
                    })
            return True
        except OSError as exc:
            logger.error("export_csv failed: %s", exc)
            return False

    def export_html(self, dest: Path) -> bool:
        """Export journal to *dest* as a styled HTML file.  No external deps."""
        entries = self.load_all()
        rows = "\n".join(
            f"<tr>"
            f"<td>{e.timestamp[:19]}</td>"
            f"<td>{e.serial}</td>"
            f"<td>{e.model}</td>"
            f"<td>{e.operation}</td>"
            f"<td class=\"{'ok' if e.success else 'fail'}\">"
            f"{'✓' if e.success else '✗'}</td>"
            f"<td>{e.duration_s:.1f}s</td>"
            f"<td>{e.notes}</td>"
            f"</tr>"
            for e in entries
        )
        html = textwrap.dedent(f"""\
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <title>CyberFlash Journal</title>
              <style>
                body {{ font-family: monospace; background: #0a0a0a; color: #00ff88; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #00ff8855; padding: 6px 10px; text-align: left; }}
                th {{ background: #00ff8822; }}
                .ok {{ color: #00ff88; }} .fail {{ color: #ff4444; }}
              </style>
            </head>
            <body>
              <h1>CyberFlash Flash Journal</h1>
              <p>Generated: {datetime.utcnow().isoformat()}Z</p>
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th><th>Serial</th><th>Model</th>
                    <th>Operation</th><th>Result</th><th>Duration</th><th>Notes</th>
                  </tr>
                </thead>
                <tbody>
            {rows}
                </tbody>
              </table>
            </body>
            </html>
        """)
        try:
            dest.write_text(html, encoding="utf-8")
            return True
        except OSError as exc:
            logger.error("export_html failed: %s", exc)
            return False

    @staticmethod
    def make_id() -> str:
        """Generate a unique ID string for a journal entry."""
        return f"jrn_{uuid.uuid4().hex[:16]}"
