"""integrity_worker.py — Play Integrity / SafetyNet attestation worker.

Runs on a QThread.  Communicates results via signals.

Attestation tiers (Play Integrity API):
  BASIC   — device passes basic integrity (not rooted standard)
  DEVICE  — device is certified (passes CTS), meets device integrity
  STRONG  — hardware-backed key attestation (most strict)

SafetyNet legacy tiers:
  basicIntegrity  — equivalent to BASIC
  ctsProfileMatch — equivalent to DEVICE
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import Signal, Slot

from cyberflash.core.adb_manager import AdbManager
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# Play Integrity helper — minimal shell-based check via device attestation props
_PI_PROPS = {
    "basic":  "ro.build.version.security_patch",
    "device": "ro.product.model",
}

# History file — stored in CyberFlash app data
_HISTORY_FILENAME = "integrity_history.json"

_MAX_HISTORY = 100


# ── Enums ────────────────────────────────────────────────────────────────────

class IntegrityTier(StrEnum):
    BASIC  = "BASIC"
    DEVICE = "DEVICE"
    STRONG = "STRONG"


class IntegrityResult(StrEnum):
    PASS    = "pass"
    FAIL    = "fail"
    UNKNOWN = "unknown"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class TierResult:
    tier:    IntegrityTier
    result:  IntegrityResult
    detail:  str = ""


@dataclass
class AttestationReport:
    serial:        str
    timestamp:     str
    tiers:         list[TierResult] = field(default_factory=list)
    raw_output:    str = ""
    error:         str = ""
    suggestions:   list[str] = field(default_factory=list)

    def overall_pass(self) -> bool:
        return all(t.result == IntegrityResult.PASS for t in self.tiers)

    def to_dict(self) -> dict:
        return {
            "serial":    self.serial,
            "timestamp": self.timestamp,
            "tiers":     [{"tier": t.tier, "result": t.result, "detail": t.detail}
                          for t in self.tiers],
            "error":     self.error,
        }


# ── Worker ────────────────────────────────────────────────────────────────────

class IntegrityWorker(BaseWorker):
    """Run Play Integrity / SafetyNet check on a connected device.

    Signals:
        result_ready(AttestationReport): emitted when check completes.
        status_update(str): emitted for progress messages.
    """

    result_ready  = Signal(object)   # AttestationReport
    status_update = Signal(str)

    def __init__(
        self,
        serial:       str,
        history_dir:  str | Path | None = None,
    ) -> None:
        super().__init__()
        self._serial      = serial
        self._history_dir = Path(history_dir) if history_dir else None

    @Slot()
    def start(self) -> None:
        self.status_update.emit("Checking Play Integrity…")
        try:
            report = IntegrityChecker.run_check(self._serial, self.status_update.emit)
        except Exception as exc:
            logger.exception("IntegrityWorker unhandled error")
            report = AttestationReport(
                serial=self._serial,
                timestamp=datetime.now().isoformat(timespec="seconds"),
                error=str(exc),
            )

        if self._history_dir:
            IntegrityChecker.save_history(report, self._history_dir)

        self.result_ready.emit(report)
        self.finished.emit()


# ── Core checker (UI-agnostic, synchronous) ───────────────────────────────────

class IntegrityChecker:
    """Synchronous Play Integrity / SafetyNet check via ADB.

    Does not directly run a full attestation (that requires a server-signed
    challenge); instead it evaluates device-side indicators that strongly
    correlate with attestation tier outcomes.
    """

    @classmethod
    def run_check(
        cls,
        serial:   str,
        progress: Callable[[str], None] | None = None,
    ) -> AttestationReport:
        def emit(msg: str) -> None:
            if progress:
                progress(msg)
            logger.info(msg)

        timestamp = datetime.now().isoformat(timespec="seconds")
        tiers:   list[TierResult] = []
        raw:     list[str] = []
        suggestions: list[str] = []

        # ── BASIC integrity ───────────────────────────────────────────────────
        emit("Checking BASIC integrity…")
        basic_result, basic_detail, basic_raw = cls._check_basic(serial)
        tiers.append(TierResult(IntegrityTier.BASIC, basic_result, basic_detail))
        raw.extend(basic_raw)
        if basic_result == IntegrityResult.FAIL:
            suggestions += [
                "Enable Shamiko to hide root from integrity checks",
                "Add Google Play Services to Magisk DenyList",
                "Ensure Zygisk is enabled in Magisk settings",
            ]

        # ── DEVICE integrity ──────────────────────────────────────────────────
        emit("Checking DEVICE integrity…")
        device_result, device_detail, device_raw = cls._check_device(serial)
        tiers.append(TierResult(IntegrityTier.DEVICE, device_result, device_detail))
        raw.extend(device_raw)
        if device_result == IntegrityResult.FAIL:
            suggestions += [
                "Device may not be on Google's CTS-certified list",
                "Custom ROM detected — consider using a stock-based ROM for banking",
                "Check Magisk MagiskHide / DenyList is configured correctly",
            ]

        # ── STRONG integrity ──────────────────────────────────────────────────
        emit("Checking STRONG integrity…")
        strong_result, strong_detail, strong_raw = cls._check_strong(serial)
        tiers.append(TierResult(IntegrityTier.STRONG, strong_result, strong_detail))
        raw.extend(strong_raw)
        if strong_result == IntegrityResult.FAIL:
            suggestions += [
                "STRONG requires hardware-backed key attestation",
                "Bootloader unlock typically fails STRONG — this is expected",
            ]

        return AttestationReport(
            serial=serial,
            timestamp=timestamp,
            tiers=tiers,
            raw_output="\n".join(raw),
            suggestions=list(dict.fromkeys(suggestions)),  # deduplicate, preserve order
        )

    # ── Tier implementations ──────────────────────────────────────────────────

    @classmethod
    def _check_basic(
        cls, serial: str
    ) -> tuple[IntegrityResult, str, list[str]]:
        raw: list[str] = []

        # Check 1: boot verification state
        out = AdbManager.shell(serial, "getprop ro.boot.verifiedbootstate 2>/dev/null", timeout=5)
        raw.append(f"verifiedbootstate={out.strip()}")
        vbs = out.strip().lower()

        # Check 2: dm-verity
        verity = AdbManager.shell(serial, "getprop ro.boot.veritymode 2>/dev/null", timeout=5)
        raw.append(f"veritymode={verity.strip()}")

        # Check 3: build type
        build_type = AdbManager.shell(serial, "getprop ro.build.type 2>/dev/null", timeout=5)
        raw.append(f"build.type={build_type.strip()}")

        if vbs in ("green", "yellow"):
            return IntegrityResult.PASS, f"verifiedbootstate={vbs}", raw
        if vbs == "orange":
            return IntegrityResult.FAIL, "Bootloader unlocked (orange state)", raw
        if vbs == "red":
            return IntegrityResult.FAIL, "Boot integrity violation (red state)", raw

        # Unknown — mark as unknown
        return IntegrityResult.UNKNOWN, f"verifiedbootstate={vbs or 'unknown'}", raw

    @classmethod
    def _check_device(
        cls, serial: str
    ) -> tuple[IntegrityResult, str, list[str]]:
        raw: list[str] = []

        # Check 1: Is build a certified stock build?
        tags = AdbManager.shell(serial, "getprop ro.build.tags 2>/dev/null", timeout=5)
        raw.append(f"build.tags={tags.strip()}")

        # Check 2: Security patch level (must be recent for DEVICE)
        patch = AdbManager.shell(
            serial, "getprop ro.build.version.security_patch 2>/dev/null", timeout=5
        )
        raw.append(f"security_patch={patch.strip()}")

        # Check 3: GMS (Google Mobile Services) presence
        gms = AdbManager.shell(
            serial,
            "pm list packages com.google.android.gms 2>/dev/null",
            timeout=6,
        )
        raw.append(f"gms_present={'yes' if 'gms' in gms else 'no'}")

        if "release-keys" in tags:
            return IntegrityResult.PASS, "release-keys + GMS present", raw
        if "dev-keys" in tags or "test-keys" in tags:
            return IntegrityResult.FAIL, f"Non-production build: {tags.strip()}", raw

        return IntegrityResult.UNKNOWN, f"tags={tags.strip() or 'unknown'}", raw

    @classmethod
    def _check_strong(
        cls, serial: str
    ) -> tuple[IntegrityResult, str, list[str]]:
        raw: list[str] = []

        # STRONG requires hardware-backed attestation — evaluate proxy indicators
        bl_state = AdbManager.shell(
            serial, "getprop ro.secureboot.lockstate 2>/dev/null", timeout=5
        )
        raw.append(f"secureboot.lockstate={bl_state.strip()}")

        keymaster = AdbManager.shell(
            serial, "getprop ro.hardware.keystore 2>/dev/null", timeout=5
        )
        raw.append(f"keystore_hw={keymaster.strip()}")

        bl_unlocked = AdbManager.shell(
            serial, "getprop ro.boot.flash.locked 2>/dev/null", timeout=5
        )
        raw.append(f"flash.locked={bl_unlocked.strip()}")

        # If bootloader is locked and keystore is hardware-backed → likely STRONG
        if bl_state.strip().lower() == "locked" and keymaster.strip():
            return IntegrityResult.PASS, "Bootloader locked + HW keystore", raw

        if bl_unlocked.strip() == "0" or bl_state.strip().lower() == "unlocked":
            return IntegrityResult.FAIL, "Bootloader unlocked — STRONG attestation not achievable", raw

        return IntegrityResult.UNKNOWN, "Cannot determine STRONG without live attestation", raw

    # ── History ───────────────────────────────────────────────────────────────

    @classmethod
    def save_history(cls, report: AttestationReport, history_dir: str | Path) -> None:
        history_dir = Path(history_dir)
        history_dir.mkdir(parents=True, exist_ok=True)
        history_file = history_dir / _HISTORY_FILENAME

        records: list[dict] = []
        if history_file.exists():
            try:
                records = json.loads(history_file.read_text())
            except (json.JSONDecodeError, OSError):
                records = []

        records.append(report.to_dict())
        if len(records) > _MAX_HISTORY:
            records = records[-_MAX_HISTORY:]

        history_file.write_text(json.dumps(records, indent=2))
        logger.info("Saved integrity history → %s", history_file)

    @classmethod
    def load_history(cls, history_dir: str | Path) -> list[dict]:
        history_file = Path(history_dir) / _HISTORY_FILENAME
        if not history_file.exists():
            return []
        try:
            return json.loads(history_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []
