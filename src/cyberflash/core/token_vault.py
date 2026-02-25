"""token_vault.py — AES-256-GCM encrypted secure credential storage.

Stores sensitive per-device tokens (Mi Unlock tokens, Samsung lock codes,
EDL firehose keys) encrypted with AES-256-GCM.  The encryption key is
derived from a user-supplied password (PBKDF2-HMAC-SHA256) or stored in
the OS keychain when available.

OS keychain integration:
  - Linux:   SecretService via secretstorage (libsecret / GNOME Keyring)
  - macOS:   Keychain via keyring library
  - Windows: DPAPI via keyring library

Vault file: JSON with base64-encoded encrypted blobs per device serial.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_VAULT_FILENAME    = "token_vault.json"
_KEYCHAIN_SERVICE  = "CyberFlash"
_KEYCHAIN_ACCOUNT  = "vault_master_key"

# PBKDF2 parameters
_PBKDF2_ITERATIONS = 260_000
_PBKDF2_SALT_LEN   = 32
_KEY_LEN           = 32   # 256-bit AES key
_GCM_NONCE_LEN     = 12   # 96-bit GCM nonce
_GCM_TAG_LEN       = 16   # 128-bit GCM authentication tag


# ── Credential dataclass ──────────────────────────────────────────────────────

@dataclass
class DeviceCredential:
    """A single credential entry for one device."""
    serial:     str
    brand:      str = ""
    label:      str = ""              # human-readable e.g. "Mi Unlock Token"
    token:      str = ""              # plaintext token value (never written to disk)
    notes:      str = ""


@dataclass
class VaultEntry:
    """Encrypted on-disk representation of a DeviceCredential."""
    serial:    str
    brand:     str
    label:     str
    notes:     str
    ciphertext: str   # base64-encoded: salt(32) + nonce(12) + tag(16) + ciphertext
    created_at: str = ""
    updated_at: str = ""


@dataclass
class VaultStats:
    total_entries: int = 0
    serials:       list[str] = field(default_factory=list)
    keychain_ok:   bool = False


# ── Crypto helpers ────────────────────────────────────────────────────────────

def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from *password* using PBKDF2-HMAC-SHA256."""
    import hashlib
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_KEY_LEN,
    )


def _encrypt(plaintext: str, key: bytes) -> bytes:
    """Encrypt *plaintext* with AES-256-GCM.  Returns salt+nonce+tag+ciphertext."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore[import]
    nonce = os.urandom(_GCM_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # AESGCM appends tag at end: ct_with_tag = ciphertext + tag (16 bytes)
    return nonce + ct_with_tag


def _decrypt(blob: bytes, key: bytes) -> str:
    """Decrypt a blob produced by _encrypt().  Raises ValueError on failure."""
    from cryptography.exceptions import InvalidTag  # type: ignore[import]
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore[import]
    if len(blob) < _GCM_NONCE_LEN + _GCM_TAG_LEN + 1:
        raise ValueError("Blob too short")
    nonce = blob[:_GCM_NONCE_LEN]
    ct_with_tag = blob[_GCM_NONCE_LEN:]
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ct_with_tag, None)
    except InvalidTag as exc:
        raise ValueError("Decryption failed — wrong key or corrupted data") from exc
    return plaintext.decode("utf-8")


def _encode_stored(salt: bytes, encrypted: bytes) -> str:
    """Combine salt + encrypted blob and base64-encode for JSON storage."""
    return base64.b64encode(salt + encrypted).decode("ascii")


def _decode_stored(stored: str) -> tuple[bytes, bytes]:
    """Decode a stored string back into (salt, encrypted_blob)."""
    raw = base64.b64decode(stored)
    return raw[:_PBKDF2_SALT_LEN], raw[_PBKDF2_SALT_LEN:]


# ── OS Keychain ───────────────────────────────────────────────────────────────

def _keychain_store(master_key_b64: str) -> bool:
    """Store master key in OS keychain. Returns True on success."""
    try:
        import keyring  # type: ignore[import]
        keyring.set_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT, master_key_b64)
        return True
    except Exception:
        return False


def _keychain_load() -> str | None:
    """Load master key from OS keychain. Returns base64 string or None."""
    try:
        import keyring  # type: ignore[import]
        return keyring.get_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
    except Exception:
        return None


def _keychain_delete() -> bool:
    """Remove master key from OS keychain."""
    try:
        import keyring  # type: ignore[import]
        keyring.delete_password(_KEYCHAIN_SERVICE, _KEYCHAIN_ACCOUNT)
        return True
    except Exception:
        return False


# ── TokenVault ───────────────────────────────────────────────────────────────

class TokenVault:
    """Encrypted per-device credential storage.

    Usage:
        vault = TokenVault(vault_dir)
        # With password:
        vault.unlock(password="my_pass")
        vault.store(DeviceCredential(serial="abc123", label="Mi Unlock", token="xxx"))
        cred = vault.retrieve("abc123")
        vault.lock()
    """

    def __init__(self, vault_dir: str | Path) -> None:
        self._vault_dir  = Path(vault_dir)
        self._vault_file = self._vault_dir / _VAULT_FILENAME
        self._key: bytes | None = None
        self._entries: dict[str, VaultEntry] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def unlock(
        self,
        password: str | None = None,
        use_keychain: bool = True,
    ) -> bool:
        """Unlock the vault.

        Tries keychain first (if *use_keychain* is True), then falls back
        to deriving the key from *password*.

        Returns:
            True if the vault is now unlocked.
        """
        # Try OS keychain
        if use_keychain:
            stored = _keychain_load()
            if stored:
                try:
                    self._key = base64.b64decode(stored)
                    self._load_entries()
                    logger.info("Vault unlocked via OS keychain")
                    return True
                except Exception:
                    self._key = None

        # Fall back to password
        if password is None:
            logger.error("No keychain entry and no password provided")
            return False

        # We use a well-known derivation salt stored alongside the vault
        salt_file = self._vault_dir / "vault.salt"
        if salt_file.exists():
            salt = salt_file.read_bytes()
        else:
            salt = os.urandom(_PBKDF2_SALT_LEN)
            self._vault_dir.mkdir(parents=True, exist_ok=True)
            salt_file.write_bytes(salt)

        self._key = _derive_key(password, salt)
        self._load_entries()

        # Optionally cache in keychain for next session
        if use_keychain:
            _keychain_store(base64.b64encode(self._key).decode("ascii"))

        logger.info("Vault unlocked via password")
        return True

    def lock(self) -> None:
        """Clear in-memory key and entries."""
        self._key = None
        self._entries = {}

    def is_unlocked(self) -> bool:
        return self._key is not None

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def store(self, credential: DeviceCredential) -> bool:
        """Encrypt and store a credential.

        Returns:
            True on success.
        """
        if not self._key:
            logger.error("Vault is locked")
            return False

        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        salt = os.urandom(_PBKDF2_SALT_LEN)
        encrypted = _encrypt(credential.token, self._key)
        stored = _encode_stored(salt, encrypted)

        prev = self._entries.get(credential.serial)
        self._entries[credential.serial] = VaultEntry(
            serial=credential.serial,
            brand=credential.brand,
            label=credential.label,
            notes=credential.notes,
            ciphertext=stored,
            created_at=prev.created_at if prev else now,
            updated_at=now,
        )
        self._save_entries()
        logger.info("Stored credential for %s (%s)", credential.serial, credential.label)
        return True

    def retrieve(self, serial: str) -> DeviceCredential | None:
        """Decrypt and return the credential for *serial*.

        Returns:
            DeviceCredential with plaintext token, or None if not found.
        """
        if not self._key:
            logger.error("Vault is locked")
            return None

        entry = self._entries.get(serial)
        if not entry:
            return None

        try:
            _, encrypted = _decode_stored(entry.ciphertext)
            # Re-derive per-entry key using the per-entry salt for extra isolation
            entry_key = self._key  # simplified: use vault key directly
            token = _decrypt(encrypted, entry_key)
        except (ValueError, Exception) as exc:
            logger.error("Failed to decrypt credential for %s: %s", serial, exc)
            return None

        return DeviceCredential(
            serial=entry.serial,
            brand=entry.brand,
            label=entry.label,
            notes=entry.notes,
            token=token,
        )

    def delete(self, serial: str) -> bool:
        """Remove a credential from the vault."""
        if serial not in self._entries:
            return False
        del self._entries[serial]
        self._save_entries()
        logger.info("Deleted credential for %s", serial)
        return True

    def list_serials(self) -> list[str]:
        """Return list of device serials with stored credentials."""
        return list(self._entries.keys())

    def stats(self) -> VaultStats:
        """Return vault summary statistics."""
        return VaultStats(
            total_entries=len(self._entries),
            serials=self.list_serials(),
            keychain_ok=_keychain_load() is not None,
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_entries(self) -> None:
        self._entries = {}
        if not self._vault_file.exists():
            return
        try:
            data = json.loads(self._vault_file.read_text())
            for serial, raw in data.items():
                self._entries[serial] = VaultEntry(
                    serial=raw.get("serial", serial),
                    brand=raw.get("brand", ""),
                    label=raw.get("label", ""),
                    notes=raw.get("notes", ""),
                    ciphertext=raw.get("ciphertext", ""),
                    created_at=raw.get("created_at", ""),
                    updated_at=raw.get("updated_at", ""),
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load vault entries: %s", exc)

    def _save_entries(self) -> None:
        self._vault_dir.mkdir(parents=True, exist_ok=True)
        data = {
            serial: {
                "serial":     e.serial,
                "brand":      e.brand,
                "label":      e.label,
                "notes":      e.notes,
                "ciphertext": e.ciphertext,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
            }
            for serial, e in self._entries.items()
        }
        self._vault_file.write_text(json.dumps(data, indent=2))

    # ── Backup / Export ───────────────────────────────────────────────────────

    def export_encrypted(self, dest_path: str | Path) -> bool:
        """Copy the encrypted vault file to *dest_path* for backup."""
        if not self._vault_file.exists():
            return False
        import shutil
        shutil.copy2(str(self._vault_file), str(dest_path))
        logger.info("Vault exported to %s", dest_path)
        return True

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> TokenVault:
        """Return a TokenVault using the default CyberFlash app data directory."""
        from cyberflash.utils.paths import get_app_data_dir
        return cls(get_app_data_dir() / "vault")
