"""Unit tests for TokenVault — encrypted credential storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from cyberflash.core.token_vault import (
    DeviceCredential,
    TokenVault,
    _decode_stored,
    _decrypt,
    _derive_key,
    _encode_stored,
    _encrypt,
)

# ── Crypto primitives ─────────────────────────────────────────────────────────

class TestCryptoPrimitives:
    def test_derive_key_length(self) -> None:
        import os
        salt = os.urandom(32)
        key = _derive_key("my_password", salt)
        assert len(key) == 32

    def test_different_salts_give_different_keys(self) -> None:
        import os
        salt1 = os.urandom(32)
        salt2 = os.urandom(32)
        k1 = _derive_key("password", salt1)
        k2 = _derive_key("password", salt2)
        assert k1 != k2

    def test_same_input_gives_same_key(self) -> None:
        import os
        salt = os.urandom(32)
        k1 = _derive_key("password", salt)
        k2 = _derive_key("password", salt)
        assert k1 == k2

    def test_encrypt_decrypt_round_trip(self) -> None:
        import os
        key = os.urandom(32)
        plaintext = "super_secret_token_value_12345"
        encrypted = _encrypt(plaintext, key)
        decrypted = _decrypt(encrypted, key)
        assert decrypted == plaintext

    def test_wrong_key_raises(self) -> None:
        import os
        key   = os.urandom(32)
        wrong = os.urandom(32)
        enc = _encrypt("secret", key)
        with pytest.raises(ValueError):
            _decrypt(enc, wrong)

    def test_too_short_blob_raises(self) -> None:
        import os
        key = os.urandom(32)
        with pytest.raises(ValueError):
            _decrypt(b"\x00" * 5, key)

    def test_encode_decode_round_trip(self) -> None:
        import os
        salt = os.urandom(32)
        blob = os.urandom(50)
        stored = _encode_stored(salt, blob)
        s2, b2 = _decode_stored(stored)
        assert s2 == salt
        assert b2 == blob


# ── TokenVault lifecycle ──────────────────────────────────────────────────────

class TestTokenVaultLifecycle:
    def _make_vault(self, tmp_path: Path) -> TokenVault:
        vault = TokenVault(tmp_path / "vault")
        return vault

    def test_unlock_with_password(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        ok = vault.unlock(password="test_pass", use_keychain=False)
        assert ok is True
        assert vault.is_unlocked() is True

    def test_lock_clears_state(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        vault.unlock(password="pass", use_keychain=False)
        vault.lock()
        assert vault.is_unlocked() is False

    def test_store_and_retrieve(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        vault.unlock(password="pass", use_keychain=False)

        cred = DeviceCredential(
            serial="device_001",
            brand="xiaomi",
            label="Mi Unlock Token",
            token="secret_mi_token_abc123",
        )
        assert vault.store(cred) is True

        retrieved = vault.retrieve("device_001")
        assert retrieved is not None
        assert retrieved.token == "secret_mi_token_abc123"
        assert retrieved.label == "Mi Unlock Token"
        assert retrieved.brand == "xiaomi"

    def test_retrieve_nonexistent_returns_none(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        vault.unlock(password="pass", use_keychain=False)
        assert vault.retrieve("nonexistent_serial") is None

    def test_delete_removes_entry(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        vault.unlock(password="pass", use_keychain=False)
        cred = DeviceCredential(serial="s1", token="tok")
        vault.store(cred)
        assert vault.delete("s1") is True
        assert vault.retrieve("s1") is None

    def test_delete_nonexistent_returns_false(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        vault.unlock(password="pass", use_keychain=False)
        assert vault.delete("ghost") is False

    def test_list_serials(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        vault.unlock(password="pass", use_keychain=False)
        for s in ("s1", "s2", "s3"):
            vault.store(DeviceCredential(serial=s, token=f"tok_{s}"))
        serials = vault.list_serials()
        assert "s1" in serials
        assert "s2" in serials
        assert "s3" in serials

    def test_stats_shows_count(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        vault.unlock(password="pass", use_keychain=False)
        vault.store(DeviceCredential(serial="x1", token="t"))
        vault.store(DeviceCredential(serial="x2", token="t"))
        stats = vault.stats()
        assert stats.total_entries == 2

    def test_store_requires_unlock(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        # Never unlocked
        assert vault.store(DeviceCredential(serial="s", token="t")) is False

    def test_retrieve_requires_unlock(self, tmp_path: Path) -> None:
        vault = self._make_vault(tmp_path)
        assert vault.retrieve("s") is None


# ── Persistence ───────────────────────────────────────────────────────────────

class TestTokenVaultPersistence:
    def test_survives_reload(self, tmp_path: Path) -> None:
        vault_dir = tmp_path / "vault"
        password  = "reload_test_password"

        # Store credential
        v1 = TokenVault(vault_dir)
        v1.unlock(password=password, use_keychain=False)
        v1.store(DeviceCredential(serial="persist_me", token="persistent_token"))

        # Re-open vault
        v2 = TokenVault(vault_dir)
        v2.unlock(password=password, use_keychain=False)
        cred = v2.retrieve("persist_me")
        assert cred is not None
        assert cred.token == "persistent_token"

    def test_wrong_password_corrupts_nothing(self, tmp_path: Path) -> None:
        vault_dir = tmp_path / "vault"

        v1 = TokenVault(vault_dir)
        v1.unlock(password="correct", use_keychain=False)
        v1.store(DeviceCredential(serial="s1", token="real_token"))

        # Open with wrong password — should still unlock (key derived from password)
        # but decrypt should fail
        v2 = TokenVault(vault_dir)
        v2.unlock(password="wrong_password", use_keychain=False)
        cred = v2.retrieve("s1")
        # With wrong key, decrypt raises → returns None
        assert cred is None or cred.token != "real_token"


# ── Export ────────────────────────────────────────────────────────────────────

class TestTokenVaultExport:
    def test_export_creates_file(self, tmp_path: Path) -> None:
        vault_dir = tmp_path / "vault"
        vault = TokenVault(vault_dir)
        vault.unlock(password="pass", use_keychain=False)
        vault.store(DeviceCredential(serial="s1", token="t"))

        export_path = tmp_path / "vault_backup.json"
        assert vault.export_encrypted(export_path) is True
        assert export_path.exists()

    def test_export_empty_vault_returns_false(self, tmp_path: Path) -> None:
        vault = TokenVault(tmp_path / "empty_vault")
        vault.unlock(password="pass", use_keychain=False)
        # No entries stored, so file doesn't exist yet
        assert vault.export_encrypted(tmp_path / "out.json") is False
