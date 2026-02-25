from __future__ import annotations

import shutil
from pathlib import Path

from cyberflash.utils.platform_utils import get_platform, get_tools_dir


class ToolManager:
    """Locates ADB and fastboot binaries: bundled resources → system PATH."""

    _cache: dict[str, Path | None] = {}

    @classmethod
    def find_adb(cls) -> Path | None:
        return cls._find_tool("adb")

    @classmethod
    def find_fastboot(cls) -> Path | None:
        return cls._find_tool("fastboot")

    @classmethod
    def adb_cmd(cls) -> list[str]:
        path = cls.find_adb()
        return [str(path)] if path else ["adb"]

    @classmethod
    def fastboot_cmd(cls) -> list[str]:
        path = cls.find_fastboot()
        return [str(path)] if path else ["fastboot"]

    @classmethod
    def _find_tool(cls, name: str) -> Path | None:
        if name in cls._cache:
            return cls._cache[name]

        platform = get_platform()
        ext = ".exe" if platform == "windows" else ""

        bundled = get_tools_dir() / f"{name}{ext}"
        if bundled.exists() and bundled.is_file():
            cls._cache[name] = bundled
            return bundled

        system = shutil.which(name)
        if system:
            result = Path(system)
            cls._cache[name] = result
            return result

        cls._cache[name] = None
        return None

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()

    @classmethod
    def find_edl(cls) -> Path | None:
        return cls._find_tool("edl")

    @classmethod
    def edl_cmd(cls) -> list[str]:
        path = cls.find_edl()
        return [str(path)] if path else ["edl"]

    @classmethod
    def is_adb_available(cls) -> bool:
        return cls.find_adb() is not None

    @classmethod
    def is_fastboot_available(cls) -> bool:
        return cls.find_fastboot() is not None

    @classmethod
    def is_edl_available(cls) -> bool:
        return cls.find_edl() is not None
