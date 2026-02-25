"""Tests for payload.bin auto-extraction pipeline.

Covers:
- FlashEngine.detect_source_type() — source format detection
- FlashEngine.extract_payload() — dry-run extraction
- FlashWorker extract_payload step dispatch
- Flash page source detection and step insertion
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cyberflash.core.flash_engine import FlashEngine
from cyberflash.models.flash_task import FlashStep, FlashTask
from cyberflash.models.profile import BootloaderConfig, DeviceProfile, FlashConfig

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_profile() -> DeviceProfile:
    return DeviceProfile(
        codename="guacamole",
        name="OnePlus 7 Pro",
        brand="OnePlus",
        model="GM1913",
        ab_slots=True,
        bootloader=BootloaderConfig(
            unlock_command="fastboot oem unlock",
            requires_oem_unlock_menu=True,
            warn_data_wipe=True,
        ),
        flash=FlashConfig(
            method="fastboot",
            partitions=["boot", "dtbo", "vbmeta", "system", "vendor", "product", "odm"],
            vbmeta_disable_flags="--disable-verity --disable-verification",
        ),
        wipe_partitions={"data": "userdata", "cache": "cache"},
    )


def _make_engine() -> tuple[FlashEngine, list[str]]:
    log: list[str] = []
    engine = FlashEngine("ABC123", log_cb=log.append)
    return engine, log


# ── FlashEngine.detect_source_type ──────────────────────────────────────────


class TestDetectSourceType:
    def test_payload_bin_file(self, tmp_path: Path) -> None:
        payload = tmp_path / "payload.bin"
        payload.write_bytes(b"\x00" * 16)
        assert FlashEngine.detect_source_type(payload) == "payload_bin"

    def test_ota_zip_file(self, tmp_path: Path) -> None:
        zipfile = tmp_path / "firmware_11.0.6.1.zip"
        zipfile.write_bytes(b"PK\x03\x04")
        assert FlashEngine.detect_source_type(zipfile) == "ota_zip"

    def test_img_directory(self, tmp_path: Path) -> None:
        (tmp_path / "boot.img").write_bytes(b"\x00")
        (tmp_path / "system.img").write_bytes(b"\x00")
        assert FlashEngine.detect_source_type(tmp_path) == "img_dir"

    def test_directory_with_payload_bin(self, tmp_path: Path) -> None:
        (tmp_path / "payload.bin").write_bytes(b"\x00")
        assert FlashEngine.detect_source_type(tmp_path) == "payload_bin"

    def test_empty_directory_unknown(self, tmp_path: Path) -> None:
        assert FlashEngine.detect_source_type(tmp_path) == "unknown"

    def test_nonexistent_path_unknown(self) -> None:
        assert FlashEngine.detect_source_type(Path("/no/such/path/x.dat")) == "unknown"

    def test_single_img_file(self, tmp_path: Path) -> None:
        img = tmp_path / "recovery.img"
        img.write_bytes(b"\x00")
        assert FlashEngine.detect_source_type(img) == "img_dir"

    def test_random_file_unknown(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.txt"
        f.write_text("hello")
        assert FlashEngine.detect_source_type(f) == "unknown"

    def test_payload_bin_case_insensitive(self, tmp_path: Path) -> None:
        payload = tmp_path / "PAYLOAD.BIN"
        payload.write_bytes(b"\x00" * 16)
        assert FlashEngine.detect_source_type(payload) == "payload_bin"


# ── FlashEngine.extract_payload (dry-run) ───────────────────────────────────


class TestExtractPayloadDryRun:
    def test_dry_run_returns_all_partitions(self) -> None:
        engine, log = _make_engine()
        source = Path("/tmp/payload.bin")
        dest = Path("/tmp/extract")
        partitions = ["boot", "system", "vendor"]

        result = engine.extract_payload(source, dest, partitions, dry_run=True)

        assert len(result) == 3
        assert result["boot"] == dest / "boot.img"
        assert result["system"] == dest / "system.img"
        assert result["vendor"] == dest / "vendor.img"
        assert any("dry-run" in line.lower() for line in log)

    def test_dry_run_logs_each_partition(self) -> None:
        engine, log = _make_engine()
        partitions = ["boot", "dtbo", "system"]
        engine.extract_payload(Path("/tmp/payload.bin"), Path("/tmp/out"), partitions, dry_run=True)

        for p in partitions:
            assert any(p in line for line in log)

    def test_dry_run_empty_partitions(self) -> None:
        engine, _log = _make_engine()
        result = engine.extract_payload(
            Path("/tmp/payload.bin"), Path("/tmp/out"), [], dry_run=True
        )
        assert result == {}


# ── FlashEngine.extract_payload (mocked real run) ───────────────────────────


class TestExtractPayloadReal:
    def test_nonexistent_source_returns_empty(self) -> None:
        engine, log = _make_engine()
        result = engine.extract_payload(
            Path("/no/such/payload.bin"), Path("/tmp/out"), ["boot"], dry_run=False
        )
        assert result == {}
        assert any("not found" in line.lower() for line in log)

    def test_extracts_available_partitions(self, tmp_path: Path) -> None:
        """Mock PayloadDumper to simulate extraction."""
        engine, log = _make_engine()
        source = tmp_path / "payload.bin"
        source.write_bytes(b"CrAU")  # fake magic
        dest = tmp_path / "output"
        dest.mkdir()

        mock_dumper = MagicMock()
        mock_dumper.list_partitions.return_value = ["boot", "system", "vendor"]
        mock_dumper.__enter__ = MagicMock(return_value=mock_dumper)
        mock_dumper.__exit__ = MagicMock(return_value=False)

        boot_img = dest / "boot.img"
        boot_img.write_bytes(b"\x00" * 1024)
        system_img = dest / "system.img"
        system_img.write_bytes(b"\x00" * 2048)

        def fake_extract(partition: str, dest_dir: Path, progress_cb: object = None) -> Path:
            return dest_dir / f"{partition}.img"

        mock_dumper.extract.side_effect = fake_extract

        with patch("cyberflash.core.flash_engine.PayloadDumper", return_value=mock_dumper):
            result = engine.extract_payload(source, dest, ["boot", "system"], dry_run=False)

        assert "boot" in result
        assert "system" in result
        assert result["boot"] == dest / "boot.img"
        assert any("Extracted" in line for line in log)

    def test_skips_missing_partition(self, tmp_path: Path) -> None:
        engine, log = _make_engine()
        source = tmp_path / "payload.bin"
        source.write_bytes(b"CrAU")
        dest = tmp_path / "output"
        dest.mkdir()

        mock_dumper = MagicMock()
        mock_dumper.list_partitions.return_value = ["boot"]
        mock_dumper.__enter__ = MagicMock(return_value=mock_dumper)
        mock_dumper.__exit__ = MagicMock(return_value=False)

        boot_img = dest / "boot.img"
        boot_img.write_bytes(b"\x00" * 512)
        mock_dumper.extract.return_value = boot_img

        with patch("cyberflash.core.flash_engine.PayloadDumper", return_value=mock_dumper):
            result = engine.extract_payload(source, dest, ["boot", "radio"], dry_run=False)

        assert "boot" in result
        assert "radio" not in result
        assert any("not in payload" in line.lower() for line in log)

    def test_handles_extraction_exception(self, tmp_path: Path) -> None:
        engine, log = _make_engine()
        source = tmp_path / "payload.bin"
        source.write_bytes(b"CrAU")
        dest = tmp_path / "output"
        dest.mkdir()

        mock_dumper = MagicMock()
        mock_dumper.list_partitions.return_value = ["boot"]
        mock_dumper.__enter__ = MagicMock(return_value=mock_dumper)
        mock_dumper.__exit__ = MagicMock(return_value=False)
        mock_dumper.extract.side_effect = RuntimeError("decompression failed")

        with patch("cyberflash.core.flash_engine.PayloadDumper", return_value=mock_dumper):
            result = engine.extract_payload(source, dest, ["boot"], dry_run=False)

        assert result == {}
        assert any("failed to extract" in line.lower() for line in log)

    def test_directory_with_payload_inside(self, tmp_path: Path) -> None:
        """If source is a directory containing payload.bin, use it."""
        engine, _log = _make_engine()
        payload = tmp_path / "payload.bin"
        payload.write_bytes(b"CrAU")

        mock_dumper = MagicMock()
        mock_dumper.list_partitions.return_value = []
        mock_dumper.__enter__ = MagicMock(return_value=mock_dumper)
        mock_dumper.__exit__ = MagicMock(return_value=False)

        with patch("cyberflash.core.flash_engine.PayloadDumper", return_value=mock_dumper) as cls:
            engine.extract_payload(tmp_path, tmp_path / "out", ["boot"], dry_run=False)

        # Should have opened the payload.bin inside the directory
        cls.assert_called_once_with(payload)


# ── FlashWorker extract_payload step dispatch ────────────────────────────────


class TestFlashWorkerExtractStep:
    def test_extract_step_dispatches(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        extract_step = FlashStep(id="extract_payload", label="Extract payload")
        extract_step._source_path = Path("/tmp/payload.bin")  # type: ignore[attr-defined]
        flash_step = FlashStep(id="flash_boot", label="Flash boot")

        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=[extract_step, flash_step],
            dry_run=True,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)

        # Simulate dry-run extraction
        engine.extract_payload.return_value = {
            "boot": Path("/tmp/out/boot.img"),
        }

        ok = worker._execute_step(engine, extract_step, task)

        assert ok is True
        engine.extract_payload.assert_called_once()

    def test_extract_step_wires_image_paths(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        extract_step = FlashStep(id="extract_payload", label="Extract payload")
        extract_step._source_path = Path("/tmp/payload.bin")  # type: ignore[attr-defined]
        flash_boot = FlashStep(id="flash_boot", label="Flash boot")
        flash_sys = FlashStep(id="flash_system", label="Flash system")

        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=[extract_step, flash_boot, flash_sys],
            dry_run=True,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)
        engine.extract_payload.return_value = {
            "boot": Path("/tmp/out/boot.img"),
            "system": Path("/tmp/out/system.img"),
        }

        worker._do_extract_payload(engine, extract_step, task)

        # flash_boot should now have _image_path set
        assert getattr(flash_boot, "_image_path", None) == Path("/tmp/out/boot.img")
        assert getattr(flash_sys, "_image_path", None) == Path("/tmp/out/system.img")

    def test_extract_step_no_source_fails(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        step = FlashStep(id="extract_payload", label="Extract payload")
        # No _source_path set

        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=[step],
            dry_run=True,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)

        ok = worker._do_extract_payload(engine, step, task)
        assert ok is False

    def test_extract_step_real_fail_returns_false(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        step = FlashStep(id="extract_payload", label="Extract payload")
        step._source_path = Path("/tmp/payload.bin")  # type: ignore[attr-defined]

        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=[step],
            dry_run=False,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)
        engine.extract_payload.return_value = {}  # Nothing extracted

        ok = worker._do_extract_payload(engine, step, task)
        assert ok is False

    def test_dry_run_sets_fallback_image_paths(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        extract_step = FlashStep(id="extract_payload", label="Extract payload")
        extract_step._source_path = Path("/tmp/payload.bin")  # type: ignore[attr-defined]
        flash_boot = FlashStep(id="flash_boot", label="Flash boot")

        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=[extract_step, flash_boot],
            dry_run=True,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)
        engine.extract_payload.return_value = {}  # dry-run returns empty

        worker._do_extract_payload(engine, extract_step, task)

        # In dry-run mode, should set fallback paths
        img_path = getattr(flash_boot, "_image_path", None)
        assert img_path is not None
        assert img_path.name == "boot.img"


# ── Flash page source detection ─────────────────────────────────────────────


class TestFlashPageSourceDetection:
    """Test that the flash page step defs include extract_payload for payloads."""

    def test_clean_slate_no_extract_for_img_dir(self, qapp: object, tmp_path: Path) -> None:
        from cyberflash.ui.pages.flash_page import FlashPage

        page = FlashPage()
        page._profile = _make_profile()
        (tmp_path / "boot.img").write_bytes(b"\x00")
        page._source_path = tmp_path  # directory with .img files

        step_defs = page._build_clean_slate_step_defs()
        ids = [s[0] for s in step_defs]
        assert "extract_payload" not in ids

    def test_clean_slate_includes_extract_for_payload(self, qapp: object, tmp_path: Path) -> None:
        from cyberflash.ui.pages.flash_page import FlashPage

        page = FlashPage()
        page._profile = _make_profile()
        payload = tmp_path / "payload.bin"
        payload.write_bytes(b"\x00" * 16)
        page._source_path = payload

        step_defs = page._build_clean_slate_step_defs()
        ids = [s[0] for s in step_defs]
        assert "extract_payload" in ids
        # extract_payload should come right after reboot_bootloader
        assert ids.index("extract_payload") == 1

    def test_clean_slate_includes_extract_for_ota_zip(self, qapp: object, tmp_path: Path) -> None:
        from cyberflash.ui.pages.flash_page import FlashPage

        page = FlashPage()
        page._profile = _make_profile()
        zipfile = tmp_path / "firmware.zip"
        zipfile.write_bytes(b"PK\x03\x04")
        page._source_path = zipfile

        step_defs = page._build_clean_slate_step_defs()
        ids = [s[0] for s in step_defs]
        assert "extract_payload" in ids

    def test_clean_slate_no_source_no_extract(self, qapp: object) -> None:
        from cyberflash.ui.pages.flash_page import FlashPage

        page = FlashPage()
        page._profile = _make_profile()
        page._source_path = None

        step_defs = page._build_clean_slate_step_defs()
        ids = [s[0] for s in step_defs]
        assert "extract_payload" not in ids

    def test_build_steps_attaches_source_to_extract(self, qapp: object, tmp_path: Path) -> None:
        from cyberflash.ui.pages.flash_page import FlashPage

        page = FlashPage()
        page._profile = _make_profile()
        payload = tmp_path / "payload.bin"
        payload.write_bytes(b"\x00" * 16)
        page._source_path = payload

        steps = page._build_clean_slate_steps()
        extract = next(s for s in steps if s.id == "extract_payload")
        assert getattr(extract, "_source_path", None) == payload

    def test_build_steps_no_image_path_for_extraction_mode(
        self, qapp: object, tmp_path: Path
    ) -> None:
        """When using payload.bin, flash steps should not have _image_path
        pre-set — the worker sets them after extraction."""
        from cyberflash.ui.pages.flash_page import FlashPage

        page = FlashPage()
        page._profile = _make_profile()
        payload = tmp_path / "payload.bin"
        payload.write_bytes(b"\x00" * 16)
        page._source_path = payload

        steps = page._build_clean_slate_steps()
        flash_steps = [s for s in steps if s.id.startswith("flash_")]
        # No image path should be pre-set (worker fills them in)
        for fs in flash_steps:
            assert not hasattr(fs, "_image_path")

    def test_build_steps_img_dir_has_image_paths(self, qapp: object, tmp_path: Path) -> None:
        """When using a pre-extracted directory, flash steps get _image_path."""
        from cyberflash.ui.pages.flash_page import FlashPage

        page = FlashPage()
        page._profile = _make_profile()
        # Create some dummy image files
        for p in ["boot", "system", "vendor"]:
            (tmp_path / f"{p}.img").write_bytes(b"\x00" * 64)
        page._source_path = tmp_path

        steps = page._build_clean_slate_steps()
        flash_boot = next(s for s in steps if s.id == "flash_boot")
        assert getattr(flash_boot, "_image_path", None) == tmp_path / "boot.img"
