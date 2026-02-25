"""ai_error_analyzer.py — Local pattern-based flash/ADB error analyzer.

Analyzes flash and ADB log text against a library of known error patterns
to suggest root causes and fixes.  No external AI calls — purely regex.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class ErrorPattern:
    """A single error pattern with associated diagnosis."""

    pattern_id: str
    regex: str
    description: str
    cause: str
    fixes: list[str]
    severity: str    # "critical" | "high" | "medium" | "low"


@dataclass
class AnalysisResult:
    """Result of analyzing a log text against all patterns."""

    matched_patterns: list[ErrorPattern] = field(default_factory=list)
    root_cause: str = ""
    suggested_fixes: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ── Pattern library (30+ patterns) ───────────────────────────────────────────

_PATTERNS: list[ErrorPattern] = [
    ErrorPattern(
        pattern_id="fastboot_failed",
        regex=r"FAILED\s*\(remote:?\s*['\"]?(.+?)['\"]?\)",
        description="fastboot command failed with remote error",
        cause="Fastboot operation rejected by bootloader",
        fixes=[
            "Check bootloader is unlocked: fastboot oem unlock",
            "Verify correct partition name for your device",
            "Try reflashing with --disable-verity --disable-verification",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="verity_mismatch",
        regex=r"(verity|dm-verity).*(fail|error|mismatch|corrupt)",
        description="dm-verity verification failure",
        cause="System partition hash does not match expected value",
        fixes=[
            "Flash a verity-disabled boot image",
            "Add disable-verity to avb_custom_key or use --disable-verity",
            "Flash stock boot.img to restore verified boot",
        ],
        severity="critical",
    ),
    ErrorPattern(
        pattern_id="signature_error",
        regex=r"(signature|verify).*(fail|invalid|error|mismatch)",
        description="Image signature verification failed",
        cause="ROM signature does not match device keys",
        fixes=[
            "Use a ROM built for your exact device variant",
            "Ensure you are not mixing build types (user/userdebug)",
            "Try factory image from official source",
        ],
        severity="critical",
    ),
    ErrorPattern(
        pattern_id="bootloader_locked",
        regex=r"(bootloader|unlock).*(lock|require|must|not allowed)",
        description="Operation blocked by locked bootloader",
        cause="Bootloader must be unlocked before flashing",
        fixes=[
            "Unlock bootloader: fastboot flashing unlock",
            "For OEM devices: fastboot oem unlock",
            "WARNING: unlocking wipes device data",
        ],
        severity="critical",
    ),
    ErrorPattern(
        pattern_id="partition_not_found",
        regex=r"(partition|slot).*(not found|doesn't exist|invalid|unknown)",
        description="Target partition does not exist on device",
        cause="Wrong partition name or A/B slot mismatch",
        fixes=[
            "List available partitions: fastboot getvar all",
            "Use correct slot suffix (_a or _b) for A/B devices",
            "Check device-specific flash guide for partition names",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="insufficient_space",
        regex=r"(no space|not enough space|insufficient space|ENOSPC)",
        description="Insufficient storage space",
        cause="Device partition or storage is full",
        fixes=[
            "Free up space: adb shell pm clear <package>",
            "Wipe cache partition from recovery",
            "Ensure image size is correct for target partition",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="device_offline",
        regex=r"(device offline|no devices|error: no.*device)",
        description="ADB device not found or offline",
        cause="ADB connection lost or device not recognized",
        fixes=[
            "Check USB cable and port",
            "Authorize USB debugging on device",
            "Run: adb kill-server && adb start-server",
            "Check device is in the correct mode (normal/recovery)",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="unauthorized",
        regex=r"(unauthorized|permission denied|error: 1 unauthorized)",
        description="ADB unauthorized — device not trusted",
        cause="USB debugging authorization not granted on device",
        fixes=[
            "Accept RSA fingerprint on device screen",
            "Check Settings > Developer Options > USB Debugging",
            "Try: adb kill-server, reconnect USB",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="adb_timeout",
        regex=r"(timeout|timed out|connection reset|broken pipe)",
        description="ADB command timed out",
        cause="Device unresponsive or connection dropped",
        fixes=[
            "Reboot device and retry",
            "Use shorter timeout operations",
            "Check for USB driver issues",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="format_failed",
        regex=r"(format|wipe).*(fail|error|unable)",
        description="Partition format/wipe failed",
        cause="Partition may be mounted or access denied",
        fixes=[
            "Boot into recovery and wipe from there",
            "Ensure device is in fastboot mode for fastboot format",
            "Some partitions require root to wipe",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="bad_zip",
        regex=r"(bad zip|invalid zip|zip.*corrupt|zipfile.*error)",
        description="ROM ZIP file is corrupted",
        cause="Download incomplete or file corrupted",
        fixes=[
            "Re-download the ROM ZIP",
            "Verify SHA256/MD5 checksum",
            "Check disk space before downloading",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="md5_mismatch",
        regex=r"(md5|sha256|sha1|checksum).*(mismatch|fail|invalid|wrong)",
        description="Checksum verification failed",
        cause="File is corrupted or download was incomplete",
        fixes=[
            "Re-download the file from official source",
            "Check for storage errors on download media",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="recovery_not_found",
        regex=r"(recovery).*(not found|missing|flash.*fail)",
        description="Recovery partition flash failed",
        cause="Recovery image incompatible or wrong slot",
        fixes=[
            "Use recovery image built for exact device model",
            "Flash to correct slot: fastboot flash recovery_a recovery.img",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="kernel_panic",
        regex=r"(kernel panic|BUG: |OOPS:|NULL pointer dereference)",
        description="Kernel panic detected in logs",
        cause="Kernel crash — incompatible kernel or driver issue",
        fixes=[
            "Flash stock kernel to test",
            "Check kernel compatibility with your Android version",
            "Inspect full dmesg for crash context",
        ],
        severity="critical",
    ),
    ErrorPattern(
        pattern_id="selinux_denial",
        regex=r"avc:\s+denied\s+\{",
        description="SELinux policy denial",
        cause="SELinux blocking an operation",
        fixes=[
            "Set permissive mode temporarily: adb shell setenforce 0",
            "Investigate audit2allow for permanent policy fix",
        ],
        severity="low",
    ),
    ErrorPattern(
        pattern_id="magisk_install_fail",
        regex=r"(magisk).*(install|patch|fail|error)",
        description="Magisk installation failed",
        cause="Incompatible boot image or Magisk version",
        fixes=[
            "Use latest Magisk from github.com/topjohnwu/Magisk",
            "Ensure boot.img is for exact device build",
            "Try direct install from Magisk app",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="adb_install_failed",
        regex=r"(Failure|INSTALL_FAILED|adb install.*error)",
        description="APK installation failed",
        cause="APK incompatible with device or ADB error",
        fixes=[
            "Check minimum SDK requirement of APK",
            "Enable Install from Unknown Sources",
            "Try: adb install -r to reinstall",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="fastboot_not_found",
        regex=r"(fastboot|adb).*(not found|no such file|command not found)",
        description="ADB or fastboot binary not found",
        cause="Platform tools not installed or not in PATH",
        fixes=[
            "Install Android Platform Tools",
            "Add platform-tools to system PATH",
            "On Linux: apt install android-tools-adb android-tools-fastboot",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="usb_driver",
        regex=r"(driver|usbsub|WinUSB|no permissions)",
        description="USB driver issue",
        cause="ADB USB driver not installed or no permissions",
        fixes=[
            "Install ADB USB drivers from device manufacturer",
            "On Linux: add udev rules for device vendor ID",
            "Try different USB port or cable",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="avb_error",
        regex=r"(avb|android verified boot).*(fail|error|reject)",
        description="Android Verified Boot (AVB) error",
        cause="Boot image rejected by AVB2 policy",
        fixes=[
            "Flash vbmeta with: fastboot flash vbmeta vbmeta.img",
            "Disable AVB: fastboot flash vbmeta --disable-verity --disable-verification",
            "Use a ROM that matches your AVB configuration",
        ],
        severity="critical",
    ),
    ErrorPattern(
        pattern_id="slot_error",
        regex=r"(slot|active.slot|set.active).*(fail|error|invalid)",
        description="A/B slot switching failed",
        cause="Slot metadata corrupted or bootloader issue",
        fixes=[
            "Try: fastboot set_active other",
            "Flash both slots: append _a and _b to partition names",
            "Factory reset via recovery if both slots are corrupt",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="data_wipe_required",
        regex=r"(data.*(wipe|format|required)|(wipe|format).*data)",
        description="Data partition wipe required",
        cause="ROM encryption/format change requires clean data",
        fixes=[
            "Wipe data/factory reset from recovery before flashing",
            "fastboot -w format:ext4:userdata",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="edl_stuck",
        regex=r"(edl|9008|qualcomm.*(emergency|download)).*(fail|stuck|no response)",
        description="Device stuck in EDL/9008 mode",
        cause="Qualcomm EDL flashing issue",
        fixes=[
            "Use QFIL or bkerler/edl tool with correct firehose",
            "Check USB cable — EDL is very cable-sensitive",
            "Ensure Qualcomm USB driver is installed",
        ],
        severity="critical",
    ),
    ErrorPattern(
        pattern_id="ota_downgrade",
        regex=r"(downgrade|older.*(version|build)|can.t.downgrade)",
        description="OTA downgrade attempt blocked",
        cause="Device anti-rollback (ARB) protection active",
        fixes=[
            "Do not downgrade below anti-rollback security level",
            "Use same version or newer",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="boot_loop",
        regex=r"(boot.?loop|stuck.*boot|rebooting.*loop|failed.*boot.*\d+ times)",
        description="Device is boot-looping",
        cause="Incompatible ROM, kernel, or corrupted system",
        fixes=[
            "Boot into recovery and wipe cache + dalvik",
            "Flash stock firmware to recover",
            "Check if ROM supports your exact device variant",
        ],
        severity="critical",
    ),
    ErrorPattern(
        pattern_id="permission_denied_adb",
        regex=r"(Permission denied|EPERM|Operation not permitted).*adb",
        description="ADB permission denied on device",
        cause="Root not granted or SELinux blocking operation",
        fixes=[
            "Grant root access in Magisk",
            "Try with su -c prefix for rooted operations",
            "Check SELinux mode: adb shell getenforce",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="mount_failed",
        regex=r"(mount|mounting).*(fail|error|unable|can.t)",
        description="Partition mount failed",
        cause="Filesystem error or wrong format",
        fixes=[
            "Run fsck on partition",
            "Format partition before mounting",
            "Check partition table integrity",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="heimdall_error",
        regex=r"(heimdall|odin).*(fail|error|disconnect|pit.*error)",
        description="Heimdall/Odin flash error (Samsung)",
        cause="Samsung flash protocol error",
        fixes=[
            "Use correct PIT file for your device",
            "Try Odin instead of Heimdall or vice versa",
            "Enable/disable MTP mode before flashing",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="adb_protocol",
        regex=r"(protocol fault|protocol error|out of sync)",
        description="ADB protocol communication error",
        cause="ADB protocol version mismatch",
        fixes=[
            "Update ADB platform tools",
            "Restart ADB server: adb kill-server && adb start-server",
        ],
        severity="medium",
    ),
    ErrorPattern(
        pattern_id="no_battery",
        regex=r"(battery.*low|charge.*battery|insufficient.*power)",
        description="Battery too low for operation",
        cause="Device requires minimum battery level to flash",
        fixes=[
            "Charge device to at least 30% before flashing",
        ],
        severity="high",
    ),
    ErrorPattern(
        pattern_id="flash_success",
        regex=r"(Finished|flash.*complete|OKAY.*\d+ms|Success)",
        description="Flash operation completed successfully",
        cause="Operation succeeded",
        fixes=["No action required"],
        severity="low",
    ),
]


# ── Main class ────────────────────────────────────────────────────────────────


class AiErrorAnalyzer:
    """Classmethod-only local error pattern analyzer."""

    _PATTERNS: list[ErrorPattern] = _PATTERNS

    @classmethod
    def analyze(cls, log_text: str) -> AnalysisResult:
        """Scan *log_text* for known error patterns.

        Returns an AnalysisResult with matched patterns ranked by severity.
        """
        matched: list[ErrorPattern] = []
        for pattern in cls._PATTERNS:
            try:
                if re.search(pattern.regex, log_text, re.IGNORECASE | re.MULTILINE):
                    matched.append(pattern)
            except re.error as exc:
                logger.debug("Pattern %s regex error: %s", pattern.pattern_id, exc)

        # Sort: critical first
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        matched.sort(key=lambda p: severity_order.get(p.severity, 4))

        # Exclude success pattern from root cause if errors also present
        error_matched = [p for p in matched if p.severity != "low"]
        primary = error_matched[0] if error_matched else (matched[0] if matched else None)

        root_cause = primary.cause if primary else "No known error pattern detected"
        fixes = primary.fixes[:] if primary else []
        confidence = min(1.0, len(matched) / 3) if matched else 0.0

        return AnalysisResult(
            matched_patterns=matched,
            root_cause=root_cause,
            suggested_fixes=fixes,
            confidence=round(confidence, 2),
        )

    @classmethod
    def analyze_adb_logcat(cls, serial: str, max_lines: int = 500) -> AnalysisResult:
        """Fetch recent logcat lines and analyze them."""
        output = AdbManager.shell(
            serial,
            f"logcat -d -t {max_lines} *:W 2>/dev/null",
            timeout=20,
        )
        return cls.analyze(output)
