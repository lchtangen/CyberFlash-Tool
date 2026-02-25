"""health_scorer.py — Android device health scoring via ADB.

Computes per-category health scores (0-100) based on device diagnostics
gathered through ADB shell commands.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.root_manager import RootManager, RootState

logger = logging.getLogger(__name__)

# ── Category weights for overall score ───────────────────────────────────────
_WEIGHTS: dict[str, float] = {
    "BATTERY": 0.25,
    "STORAGE": 0.20,
    "CPU":     0.15,
    "MEMORY":  0.20,
    "ROOT":    0.10,
    "BOOT":    0.10,
}


# ── Enums ────────────────────────────────────────────────────────────────────


class HealthCategory(StrEnum):
    BATTERY = "BATTERY"
    STORAGE = "STORAGE"
    CPU     = "CPU"
    MEMORY  = "MEMORY"
    ROOT    = "ROOT"
    BOOT    = "BOOT"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class CategoryScore:
    """Health score for a single device category."""

    category: HealthCategory
    score: int                  # 0-100
    detail: str = ""
    recommendation: str = ""


@dataclass
class HealthReport:
    """Full device health report."""

    serial: str
    overall: int                # 0-100 weighted average
    categories: list[CategoryScore] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


# ── Main class ────────────────────────────────────────────────────────────────


class HealthScorer:
    """Classmethod-only device health scorer."""

    # ── Battery ───────────────────────────────────────────────────────────────

    @classmethod
    def score_battery(cls, serial: str) -> CategoryScore:
        """Score battery health from dumpsys battery output."""
        output = AdbManager.shell(serial, "dumpsys battery", timeout=10)
        score = 80
        details: list[str] = []
        recs: list[str] = []

        # Level
        m = re.search(r"level:\s*(\d+)", output)
        if m:
            level = int(m.group(1))
            details.append(f"Level: {level}%")
            if level < 15:
                score -= 30
                recs.append("Charge device immediately")
            elif level < 30:
                score -= 10

        # Temperature
        m = re.search(r"temperature:\s*(\d+)", output)
        if m:
            temp_c = int(m.group(1)) / 10
            details.append(f"Temp: {temp_c:.1f}°C")
            if temp_c > 45:
                score -= 20
                recs.append(f"Temperature {temp_c:.1f}°C is dangerously high")
            elif temp_c > 40:
                score -= 10

        # Health status
        m = re.search(r"health:\s*(\d+)", output)
        if m:
            health = int(m.group(1))
            # health=2 → good; 1=unknown, 3=overheat, 4=dead, 5=overvoltage, 6=unspec, 7=cold
            if health == 4:
                score -= 40
                recs.append("Battery reported as DEAD — replace battery")
            elif health in (3, 5):
                score -= 20

        return CategoryScore(
            category=HealthCategory.BATTERY,
            score=max(0, min(100, score)),
            detail="; ".join(details) if details else "No data",
            recommendation="; ".join(recs) if recs else "Battery health looks good",
        )

    # ── Storage ───────────────────────────────────────────────────────────────

    @classmethod
    def score_storage(cls, serial: str) -> CategoryScore:
        """Score storage from df /data output."""
        output = AdbManager.shell(serial, "df /data", timeout=10)
        score = 90
        details: list[str] = []
        recs: list[str] = []

        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                used_pct_str = parts[4].rstrip("%")
                try:
                    used_pct = int(used_pct_str)
                    details.append(f"Used: {used_pct}%")
                    if used_pct >= 95:
                        score -= 40
                        recs.append("Storage almost full — free up space")
                    elif used_pct >= 80:
                        score -= 20
                        recs.append("Storage usage high")
                    elif used_pct >= 65:
                        score -= 5
                except ValueError:
                    pass
                break

        return CategoryScore(
            category=HealthCategory.STORAGE,
            score=max(0, min(100, score)),
            detail="; ".join(details) if details else "No data",
            recommendation="; ".join(recs) if recs else "Storage levels healthy",
        )

    # ── CPU ───────────────────────────────────────────────────────────────────

    @classmethod
    def score_cpu(cls, serial: str) -> CategoryScore:
        """Score CPU from cpuinfo and scaling governor."""
        cpuinfo = AdbManager.shell(serial, "cat /proc/cpuinfo", timeout=10)
        governor_output = AdbManager.shell(
            serial,
            "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null",
            timeout=5,
        )
        score = 85
        details: list[str] = []
        recs: list[str] = []

        # Processor count
        cpu_count = cpuinfo.count("processor")
        if cpu_count:
            details.append(f"Cores: {cpu_count}")

        # Governor
        governor = governor_output.strip()
        if governor:
            details.append(f"Governor: {governor}")
            if governor == "powersave":
                score -= 10
                recs.append("CPU in powersave mode — performance limited")
            elif governor == "performance":
                score += 5

        return CategoryScore(
            category=HealthCategory.CPU,
            score=max(0, min(100, score)),
            detail="; ".join(details) if details else "No data",
            recommendation="; ".join(recs) if recs else "CPU performance normal",
        )

    # ── Memory ────────────────────────────────────────────────────────────────

    @classmethod
    def score_memory(cls, serial: str) -> CategoryScore:
        """Score memory from /proc/meminfo."""
        output = AdbManager.shell(serial, "cat /proc/meminfo", timeout=10)
        score = 85
        details: list[str] = []
        recs: list[str] = []

        mem_total = mem_available = 0
        for line in output.splitlines():
            m = re.match(r"MemTotal:\s+(\d+)", line)
            if m:
                mem_total = int(m.group(1))
            m = re.match(r"MemAvailable:\s+(\d+)", line)
            if m:
                mem_available = int(m.group(1))

        if mem_total > 0:
            used_pct = (1 - mem_available / mem_total) * 100
            details.append(
                f"Total: {mem_total // 1024}MB, "
                f"Available: {mem_available // 1024}MB ({100 - used_pct:.0f}% free)"
            )
            if used_pct > 90:
                score -= 30
                recs.append("Memory critically low — close background apps")
            elif used_pct > 75:
                score -= 15

        return CategoryScore(
            category=HealthCategory.MEMORY,
            score=max(0, min(100, score)),
            detail="; ".join(details) if details else "No data",
            recommendation="; ".join(recs) if recs else "Memory usage acceptable",
        )

    # ── Root ──────────────────────────────────────────────────────────────────

    @classmethod
    def score_root(cls, serial: str) -> CategoryScore:
        """Score root status using RootManager detection."""
        state = RootManager.detect_root_state(serial)
        if state == RootState.NOT_ROOTED:
            return CategoryScore(
                category=HealthCategory.ROOT,
                score=100,
                detail="Not rooted",
                recommendation="Device is stock — maximum security",
            )
        return CategoryScore(
            category=HealthCategory.ROOT,
            score=60,
            detail=f"Root detected: {state.label}",
            recommendation="Root grants elevated risk — ensure Magisk Hide / DenyList is configured",
        )

    # ── Boot ──────────────────────────────────────────────────────────────────

    @classmethod
    def score_boot(cls, serial: str) -> CategoryScore:
        """Score boot health from dmesg error count."""
        output = AdbManager.shell(serial, "dmesg 2>/dev/null | grep -i ' error' | wc -l", timeout=15)
        score = 90
        details: list[str] = []
        recs: list[str] = []

        try:
            error_count = int(output.strip())
            details.append(f"Kernel errors: {error_count}")
            if error_count > 100:
                score -= 30
                recs.append(f"{error_count} kernel errors detected — inspect dmesg")
            elif error_count > 20:
                score -= 15
            elif error_count > 5:
                score -= 5
        except ValueError:
            details.append("Could not parse dmesg")

        return CategoryScore(
            category=HealthCategory.BOOT,
            score=max(0, min(100, score)),
            detail="; ".join(details) if details else "No data",
            recommendation="; ".join(recs) if recs else "Boot log looks healthy",
        )

    # ── Aggregate ─────────────────────────────────────────────────────────────

    @classmethod
    def compute(cls, serial: str) -> HealthReport:
        """Compute a full HealthReport for *serial*."""
        categories = [
            cls.score_battery(serial),
            cls.score_storage(serial),
            cls.score_cpu(serial),
            cls.score_memory(serial),
            cls.score_root(serial),
            cls.score_boot(serial),
        ]

        overall = 0.0
        for cat in categories:
            weight = _WEIGHTS.get(cat.category, 1.0 / len(categories))
            overall += cat.score * weight

        return HealthReport(
            serial=serial,
            overall=round(overall),
            categories=categories,
        )
