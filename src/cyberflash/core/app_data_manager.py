"""app_data_manager.py — App backup, restore, and differential backup via ADB.

Encrypts backups using AES-256-GCM via TokenVault's key derivation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

_BACKUP_MANIFEST = "cyberflash_backup_manifest.json"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class AppBackup:
    """Metadata for a single app backup."""

    package: str
    version: str
    backup_path: Path
    created_at: str
    size_bytes: int
    encrypted: bool
    extra: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "package": self.package,
            "version": self.version,
            "backup_path": str(self.backup_path),
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
            "encrypted": self.encrypted,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> AppBackup:
        return cls(
            package=str(d.get("package", "")),
            version=str(d.get("version", "")),
            backup_path=Path(str(d.get("backup_path", "."))),
            created_at=str(d.get("created_at", "")),
            size_bytes=int(d.get("size_bytes", 0)),
            encrypted=bool(d.get("encrypted", False)),
        )


# ── Main class ────────────────────────────────────────────────────────────────


class AppDataManager:
    """Classmethod-only app data backup/restore manager."""

    @classmethod
    def backup_app(
        cls,
        serial: str,
        package: str,
        dest_dir: Path,
        encrypt: bool = True,
    ) -> AppBackup:
        """Backup *package* data to *dest_dir* using ``adb backup``.

        Returns an AppBackup descriptor.
        Encryption is performed post-backup using TokenVault if available.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = str(int(time.time()))
        backup_filename = f"{package}_{ts}.ab"
        local_path = dest_dir / backup_filename

        # Fetch app version
        version = cls._get_app_version(serial, package)

        # adb backup (apk + data, no shared)
        rc, _, stderr = AdbManager._run(
            ["-s", serial, "backup", "-apk", "-noshared", package,
             "-f", str(local_path)],
            timeout=120,
        )
        if rc != 0:
            logger.warning("adb backup failed for %s: %s", package, stderr.strip())

        size = local_path.stat().st_size if local_path.exists() else 0

        backup = AppBackup(
            package=package,
            version=version,
            backup_path=local_path,
            created_at=ts,
            size_bytes=size,
            encrypted=False,
        )

        if encrypt and local_path.exists() and size > 0:
            encrypted_path = cls._encrypt_backup(local_path)
            if encrypted_path:
                local_path.unlink(missing_ok=True)
                backup.backup_path = encrypted_path
                backup.encrypted = True
                backup.size_bytes = encrypted_path.stat().st_size

        return backup

    @classmethod
    def _get_app_version(cls, serial: str, package: str) -> str:
        """Return installed version name of *package*."""
        output = AdbManager.shell(
            serial,
            f"dumpsys package {package} 2>/dev/null | grep versionName",
            timeout=10,
        )
        for line in output.splitlines():
            if "versionName=" in line:
                return line.strip().split("versionName=")[-1].split()[0]
        return "unknown"

    @classmethod
    def _encrypt_backup(cls, path: Path) -> Path | None:
        """Encrypt *path* in-place using AES-256-GCM via TokenVault."""
        try:
            from cyberflash.core.token_vault import TokenVault

            data = path.read_bytes()
            encrypted = TokenVault.encrypt_bytes(data, "backup_key")
            enc_path = path.with_suffix(".aes")
            enc_path.write_bytes(encrypted)
            return enc_path
        except Exception as exc:
            logger.warning("_encrypt_backup: %s", exc)
            return None

    @classmethod
    def restore_app(cls, serial: str, backup: AppBackup, password: str = "") -> bool:
        """Restore an app from *backup* using ``adb restore``."""
        src = backup.backup_path
        if not src.exists():
            logger.error("restore_app: backup file not found: %s", src)
            return False

        restore_path = src
        tmp_path: Path | None = None

        if backup.encrypted:
            try:
                from cyberflash.core.token_vault import TokenVault
                data = src.read_bytes()
                decrypted = TokenVault.decrypt_bytes(data, "backup_key")
                tmp_path = src.with_suffix(".ab.tmp")
                tmp_path.write_bytes(decrypted)
                restore_path = tmp_path
            except Exception as exc:
                logger.error("restore_app: decrypt failed: %s", exc)
                return False

        rc, _, stderr = AdbManager._run(
            ["-s", serial, "restore", str(restore_path)],
            timeout=180,
        )

        if tmp_path:
            tmp_path.unlink(missing_ok=True)

        if rc != 0:
            logger.warning("adb restore failed: %s", stderr.strip())
        return rc == 0

    @classmethod
    def list_backups(cls, backup_dir: Path) -> list[AppBackup]:
        """List all .ab and .aes backup files in *backup_dir*."""
        if not backup_dir.exists():
            return []
        backups: list[AppBackup] = []
        for f in backup_dir.iterdir():
            if f.suffix not in (".ab", ".aes"):
                continue
            # Parse package name from filename: <package>_<ts>.<ext>
            stem = f.stem
            parts = stem.rsplit("_", 1)
            package = parts[0] if len(parts) >= 2 else stem
            ts = parts[1] if len(parts) >= 2 else "0"
            backups.append(AppBackup(
                package=package,
                version="",
                backup_path=f,
                created_at=ts,
                size_bytes=f.stat().st_size,
                encrypted=f.suffix == ".aes",
            ))
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    @classmethod
    def differential_backup(
        cls,
        serial: str,
        package: str,
        last_backup: AppBackup,
        dest_dir: Path,
    ) -> AppBackup:
        """Create a new backup; returns it (currently full backup).

        A true differential requires comparing file modification times via
        ADB which is device-root-dependent.  This implementation creates
        a full backup but notes the reference in extra metadata.
        """
        new_backup = cls.backup_app(serial, package, dest_dir)
        new_backup.extra["reference_backup"] = str(last_backup.backup_path)
        return new_backup
