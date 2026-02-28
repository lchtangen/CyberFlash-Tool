"""privacy_scanner_worker.py — App privacy & tracking SDK scanner.

Scans installed third-party apps via dumpsys package to detect
known tracking SDKs and dangerous permissions, scoring each app 0-100
(lower = worse privacy).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from PySide6.QtCore import Signal, Slot

from cyberflash.core.adb_manager import AdbManager
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


# ── Known tracking SDK fingerprints ──────────────────────────────────────────
# Each entry: (display_name, package_hint_pattern, risk_level 1-5)

_KNOWN_SDKS: list[tuple[str, str, int]] = [
    ("Google Analytics",    r"com\.google\.android\.gms\.analytics",   3),
    ("Firebase Analytics",  r"com\.google\.firebase",                   2),
    ("Facebook SDK",        r"com\.facebook\.(ads|analytics|appevents)",4),
    ("Adjust",              r"com\.adjust\.sdk",                         4),
    ("AppsFlyer",           r"com\.appsflyer",                           4),
    ("Branch.io",           r"io\.branch\.referral",                     3),
    ("Kochava",             r"com\.kochava",                             4),
    ("Singular",            r"com\.singular\.sdk",                       3),
    ("Mixpanel",            r"com\.mixpanel\.android",                   2),
    ("Amplitude",           r"com\.amplitude\.api",                      2),
    ("OneSignal",           r"com\.onesignal",                           2),
    ("Crashlytics",         r"com\.crashlytics\b",                       1),
    ("AdMob",               r"com\.google\.android\.gms\.ads",           3),
    ("MoPub",               r"com\.mopub",                               3),
    ("InMobi",              r"com\.inmobi",                              4),
    ("Unity Ads",           r"com\.unity3d\.ads",                        2),
    ("Vungle",              r"com\.vungle",                              3),
    ("AppLovin",            r"com\.applovin",                            3),
    ("IronSource",          r"com\.ironsource\.mediationsdk",            3),
    ("Chartboost",          r"com\.chartboost",                          2),
]

# Dangerous permissions that reduce score
_DANGEROUS_PERMS: list[tuple[str, int]] = [
    ("android.permission.ACCESS_FINE_LOCATION",   15),
    ("android.permission.ACCESS_BACKGROUND_LOCATION", 20),
    ("android.permission.RECORD_AUDIO",           15),
    ("android.permission.CAMERA",                 10),
    ("android.permission.READ_CONTACTS",          10),
    ("android.permission.READ_SMS",               20),
    ("android.permission.SEND_SMS",               20),
    ("android.permission.PROCESS_OUTGOING_CALLS", 15),
    ("android.permission.READ_CALL_LOG",          15),
    ("android.permission.WRITE_EXTERNAL_STORAGE",  5),
    ("com.google.android.gms.permission.AD_ID",   10),
]


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class TrackingSDK:
    """A detected tracking SDK."""

    name: str
    package_hint: str
    risk_level: int          # 1 (low) - 5 (high)


@dataclass
class AppPrivacyScore:
    """Privacy analysis result for one app."""

    package: str
    score: int                   # 0-100, lower = worse
    sdks: list[TrackingSDK] = field(default_factory=list)
    dangerous_perms: list[str] = field(default_factory=list)


# ── Worker ────────────────────────────────────────────────────────────────────


class PrivacyScannerWorker(BaseWorker):
    """Scan third-party apps for privacy-affecting SDKs and permissions.

    Signals:
        app_scanned(AppPrivacyScore)  — emitted after each app
        scan_complete(list)           — emitted with full list at end
    """

    app_scanned    = Signal(object)  # AppPrivacyScore
    scan_complete  = Signal(list)    # list[AppPrivacyScore]

    def __init__(self, serial: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._aborted = False

    @Slot()
    def start(self) -> None:
        results: list[AppPrivacyScore] = []
        try:
            packages = self._list_third_party_packages()
            for pkg in packages:
                if self._aborted:
                    break
                score = self._scan_package(pkg)
                results.append(score)
                self.app_scanned.emit(score)
        except Exception as exc:
            logger.exception("PrivacyScannerWorker error")
            self.error.emit(str(exc))
        finally:
            self.scan_complete.emit(results)
            self.finished.emit()

    def abort(self) -> None:
        """Stop scanning after the current app."""
        self._aborted = True

    def _list_third_party_packages(self) -> list[str]:
        output = AdbManager.shell(self._serial, "pm list packages -3", timeout=20)
        return [
            line.replace("package:", "").strip()
            for line in output.splitlines()
            if line.startswith("package:")
        ]

    def _scan_package(self, package: str) -> AppPrivacyScore:
        """Scan a single package and return its privacy score."""
        dump = AdbManager.shell(
            self._serial,
            f"dumpsys package {package} 2>/dev/null",
            timeout=10,
        )

        detected_sdks: list[TrackingSDK] = []
        for sdk_name, pattern, risk in _KNOWN_SDKS:
            if re.search(pattern, dump, re.IGNORECASE):
                detected_sdks.append(TrackingSDK(
                    name=sdk_name,
                    package_hint=pattern,
                    risk_level=risk,
                ))

        dangerous_granted: list[str] = []
        score = 100

        for perm, penalty in _DANGEROUS_PERMS:
            # Check if permission is granted
            pattern = re.escape(perm) + r".*granted=true"
            if re.search(pattern, dump, re.IGNORECASE):
                dangerous_granted.append(perm)
                score -= penalty

        for sdk in detected_sdks:
            score -= sdk.risk_level * 3

        return AppPrivacyScore(
            package=package,
            score=max(0, score),
            sdks=detected_sdks,
            dangerous_perms=dangerous_granted,
        )
