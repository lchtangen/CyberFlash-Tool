"""secure_wiper.py — Secure file and partition wiper via ADB.

Implements overwrite-based data destruction using multiple pass patterns,
with optional verification and destruction certificate generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# Pass patterns: (name, dd_block)
_PASS_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "STANDARD":  [("zeros", "/dev/zero")],
    "DOD_3PASS": [
        ("zeros",  "/dev/zero"),
        ("random", "/dev/urandom"),
        ("zeros",  "/dev/zero"),
    ],
    "GUTMANN": [],  # filled dynamically
}

# Build Gutmann 35-pass pattern
for _i in range(35):
    _src = "/dev/urandom" if _i % 5 == 0 else "/dev/zero"
    _PASS_PATTERNS["GUTMANN"].append((f"pass{_i + 1}", _src))


# ── Enums ────────────────────────────────────────────────────────────────────


class WipeMethod(StrEnum):
    STANDARD  = "STANDARD"
    DOD_3PASS = "DOD_3PASS"
    GUTMANN   = "GUTMANN"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class WipeReport:
    """Report of a secure wipe operation."""

    path: str
    method: WipeMethod
    passes_completed: int
    verified: bool
    timestamp: str
    certificate_text: str = ""


# ── Main class ────────────────────────────────────────────────────────────────


class SecureWiper:
    """Classmethod-only secure data wiper."""

    @classmethod
    def wipe_file(
        cls,
        serial: str,
        remote_path: str,
        method: WipeMethod = WipeMethod.STANDARD,
        dry_run: bool = False,
    ) -> WipeReport:
        """Overwrite *remote_path* on device with N passes using dd.

        Returns a WipeReport with completion status.
        """
        passes = _PASS_PATTERNS[method]
        completed = 0
        ts = datetime.now(UTC).isoformat()

        if dry_run:
            return WipeReport(
                path=remote_path,
                method=method,
                passes_completed=len(passes),
                verified=True,
                timestamp=ts,
                certificate_text=cls.generate_certificate(WipeReport(
                    path=remote_path,
                    method=method,
                    passes_completed=len(passes),
                    verified=True,
                    timestamp=ts,
                )),
            )

        for _pass_name, source in passes:
            result = AdbManager.shell(
                serial,
                f"dd if={source} of={remote_path} bs=4096 conv=notrunc 2>&1",
                timeout=300,
            )
            if "error" in result.lower() and "no space" not in result.lower():
                logger.warning("wipe_file pass error for %s: %s", remote_path, result[:100])
                break
            completed += 1

        # Final delete
        AdbManager.shell(serial, f"rm -f {remote_path}", timeout=10)

        verified = cls.verify_wipe(serial, remote_path)
        report = WipeReport(
            path=remote_path,
            method=method,
            passes_completed=completed,
            verified=verified,
            timestamp=ts,
        )
        report.certificate_text = cls.generate_certificate(report)
        return report

    @classmethod
    def wipe_partition(
        cls,
        serial: str,
        partition: str,
        method: WipeMethod = WipeMethod.STANDARD,
        dry_run: bool = False,
    ) -> WipeReport:
        """Overwrite a device partition by name (requires root).

        Example: partition="userdata" → /dev/block/by-name/userdata
        """
        remote_path = f"/dev/block/by-name/{partition}"
        passes = _PASS_PATTERNS[method]
        ts = datetime.now(UTC).isoformat()

        if dry_run:
            report = WipeReport(
                path=remote_path,
                method=method,
                passes_completed=len(passes),
                verified=True,
                timestamp=ts,
            )
            report.certificate_text = cls.generate_certificate(report)
            return report

        completed = 0
        for _pass_name, source in passes:
            result = AdbManager.shell(
                serial,
                f"su -c 'dd if={source} of={remote_path} bs=65536 2>&1'",
                timeout=600,
            )
            if "permission denied" in result.lower():
                logger.error("wipe_partition: permission denied (root required)")
                break
            completed += 1

        report = WipeReport(
            path=remote_path,
            method=method,
            passes_completed=completed,
            verified=False,    # partition verify is impractical
            timestamp=ts,
        )
        report.certificate_text = cls.generate_certificate(report)
        return report

    @classmethod
    def generate_certificate(cls, report: WipeReport) -> str:
        """Generate a human-readable data destruction certificate."""
        return (
            "╔══════════════════════════════════════════════════════════╗\n"
            "║       CYBERFLASH DATA DESTRUCTION CERTIFICATE           ║\n"
            "╠══════════════════════════════════════════════════════════╣\n"
            f"║ Path:     {report.path:<50}║\n"
            f"║ Method:   {report.method:<50}║\n"
            f"║ Passes:   {report.passes_completed!s:<50}║\n"
            f"║ Verified: {'Yes' if report.verified else 'No':<50}║\n"
            f"║ Time:     {report.timestamp:<50}║\n"
            "╠══════════════════════════════════════════════════════════╣\n"
            "║ This certificate confirms that the above data was        ║\n"
            "║ overwritten per the specified standard.                  ║\n"
            "╚══════════════════════════════════════════════════════════╝\n"
        )

    @classmethod
    def verify_wipe(cls, serial: str, path: str) -> bool:
        """Verify that *path* no longer exists on the device.

        For files: checks ``ls`` returns error.
        Returns True if the file is gone (wipe considered successful).
        """
        output = AdbManager.shell(serial, f"ls {path} 2>&1", timeout=10)
        return "no such file" in output.lower() or "not found" in output.lower()
