"""module_compat.py — Magisk module compatibility matrix.

Checks whether a Magisk module is compatible with the current device's
Android version, architecture, and SELinux policy version.

All public methods are classmethods and return bool; never raise exceptions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_MIN_ANDROID_API = 26  # Android 8.0 required for Magisk v24+
_SUPPORTED_ARCHS: frozenset[str] = frozenset({"arm64-v8a", "armeabi-v7a", "x86_64", "x86"})


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class ModuleManifest:
    """Parsed module.prop / module metadata."""

    id: str
    name: str
    version: str
    version_code: int
    author: str
    description: str
    min_magisk: int = 0           # minimum Magisk version code
    min_api: int = 0              # minimum Android API level
    max_api: int = 999            # maximum Android API level
    support_archs: list[str] = field(default_factory=list)


@dataclass
class CompatResult:
    """Compatibility check result for one module."""

    module_id: str
    compatible: bool
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


# ── Parser ────────────────────────────────────────────────────────────────────


def _parse_module_prop(text: str) -> dict[str, str]:
    """Parse a key=value module.prop file into a dict."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


# ── Core class ────────────────────────────────────────────────────────────────


class ModuleCompat:
    """Static helpers for Magisk module compatibility checks.

    Usage::

        manifest = ModuleCompat.parse_manifest(prop_text)
        result = ModuleCompat.check(
            manifest,
            device_api=34,
            device_arch="arm64-v8a",
            magisk_version_code=26200,
        )
    """

    @classmethod
    def parse_manifest(cls, prop_text: str) -> ModuleManifest | None:
        """Parse module.prop text into a ModuleManifest.

        Returns ``None`` on failure.
        """
        try:
            data = _parse_module_prop(prop_text)
            archs_raw = data.get("supportedArchs", "")
            archs = [a.strip() for a in archs_raw.split(",") if a.strip()] if archs_raw else []
            return ModuleManifest(
                id=data.get("id", "unknown"),
                name=data.get("name", ""),
                version=data.get("version", ""),
                version_code=int(data.get("versionCode", "0")),
                author=data.get("author", ""),
                description=data.get("description", ""),
                min_magisk=int(data.get("minMagisk", "0")),
                min_api=int(data.get("minApi", "0")),
                max_api=int(data.get("maxApi", "999")),
                support_archs=archs,
            )
        except Exception:
            logger.exception("Failed to parse module.prop")
            return None

    @classmethod
    def parse_manifest_path(cls, path: Path) -> ModuleManifest | None:
        """Read and parse a module.prop file from ``path``."""
        try:
            return cls.parse_manifest(path.read_text(encoding="utf-8"))
        except OSError:
            logger.warning("Cannot read %s", path)
            return None

    @classmethod
    def check(
        cls,
        manifest: ModuleManifest,
        device_api: int,
        device_arch: str,
        magisk_version_code: int = 0,
        log_cb: Callable[[str], None] | None = None,
    ) -> CompatResult:
        """Return a :class:`CompatResult` for the given device context.

        Args:
            manifest: Parsed module manifest.
            device_api: Android API level of the target device (e.g. ``34``).
            device_arch: ABI string from ``ro.product.cpu.abi`` (e.g. ``arm64-v8a``).
            magisk_version_code: Installed Magisk versionCode (0 = unknown).
            log_cb: Optional logging callback.

        Returns:
            A :class:`CompatResult` with ``compatible=True`` iff no blockers.
        """
        def _log(msg: str) -> None:
            logger.debug(msg)
            if log_cb:
                log_cb(msg)

        blockers: list[str] = []
        warnings: list[str] = []

        _log(f"Checking module '{manifest.id}' against API={device_api} arch={device_arch}")

        # Android API level checks
        if manifest.min_api and device_api < manifest.min_api:
            blockers.append(
                f"Requires Android API {manifest.min_api}+; device is API {device_api}"
            )
        if manifest.max_api < 999 and device_api > manifest.max_api:
            blockers.append(
                f"Does not support Android API > {manifest.max_api}; device is API {device_api}"
            )

        # Global minimum API floor
        if device_api < _MIN_ANDROID_API:
            blockers.append(
                f"Magisk itself requires Android {_MIN_ANDROID_API}+; device is API {device_api}"
            )

        # Architecture checks
        if manifest.support_archs:
            normalised_arch = device_arch.lower()
            supported_lower = {a.lower() for a in manifest.support_archs}
            if normalised_arch not in supported_lower:
                blockers.append(
                    f"Module supports {manifest.support_archs}; device arch is {device_arch}"
                )
        elif device_arch not in _SUPPORTED_ARCHS:
            warnings.append(f"Unknown device arch '{device_arch}' — compatibility unverified")

        # Magisk version check
        if manifest.min_magisk and magisk_version_code and magisk_version_code < manifest.min_magisk:
            blockers.append(
                f"Requires Magisk versionCode {manifest.min_magisk}+; installed is {magisk_version_code}"
            )

        compatible = len(blockers) == 0
        _log(f"Module '{manifest.id}' compatible={compatible} blockers={blockers}")
        return CompatResult(
            module_id=manifest.id,
            compatible=compatible,
            warnings=warnings,
            blockers=blockers,
        )

    @classmethod
    def check_directory(
        cls,
        modules_dir: Path,
        device_api: int,
        device_arch: str,
        magisk_version_code: int = 0,
        log_cb: Callable[[str], None] | None = None,
    ) -> list[CompatResult]:
        """Check all module.prop files found under ``modules_dir``.

        Each top-level subdirectory that contains ``module.prop`` is treated as
        one module.

        Returns:
            List of :class:`CompatResult` (empty list if directory absent).
        """
        results: list[CompatResult] = []
        if not modules_dir.is_dir():
            logger.warning("Modules directory not found: %s", modules_dir)
            return results

        for prop_path in sorted(modules_dir.rglob("module.prop")):
            manifest = cls.parse_manifest_path(prop_path)
            if manifest is None:
                continue
            result = cls.check(
                manifest,
                device_api=device_api,
                device_arch=device_arch,
                magisk_version_code=magisk_version_code,
                log_cb=log_cb,
            )
            results.append(result)

        return results
