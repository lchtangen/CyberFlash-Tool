"""Tests for clean-slate erase + reflash workflow.

Covers:
- FlashEngine.erase_all_partitions (dry-run and mock modes)
- FlashEngine.clean_slate_reflash (full orchestration)
- FlashWorker erase_* step dispatch
- WorkflowEngine.plan_clean_slate workflow generation
- Flash page clean-slate step definitions
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from cyberflash.core.flash_engine import FlashEngine
from cyberflash.core.workflow_engine import WorkflowEngine
from cyberflash.models.device import DeviceInfo, DeviceState
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


def _make_device(state: DeviceState = DeviceState.FASTBOOT) -> DeviceInfo:
    return DeviceInfo(
        serial="ABC123",
        state=state,
        model="GM1913",
        brand="OnePlus",
        codename="guacamole",
        has_ab_slots=True,
        active_slot="a",
        bootloader_unlocked=True,
    )


def _make_engine() -> tuple[FlashEngine, list[str]]:
    log: list[str] = []
    engine = FlashEngine("ABC123", log_cb=log.append)
    return engine, log


# ── FlashEngine.erase_all_partitions ─────────────────────────────────────────


class TestEraseAllPartitions:
    def test_dry_run_erases_nothing(self) -> None:
        engine, log = _make_engine()
        with patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb:
            result = engine.erase_all_partitions(["boot", "system", "vendor"], dry_run=True)

        assert all(ok is True for ok in result.values())
        assert len(result) == 3
        mock_fb.erase.assert_not_called()
        assert any("clean slate" in line.lower() for line in log)

    def test_returns_dict_per_partition(self) -> None:
        engine, _log = _make_engine()
        with patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb:
            mock_fb.erase.return_value = True
            result = engine.erase_all_partitions(["boot", "system"], dry_run=False)

        assert result == {"boot": True, "system": True}

    def test_partial_failure(self) -> None:
        engine, log = _make_engine()
        with patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb:
            mock_fb.erase.side_effect = [True, False, True]
            result = engine.erase_all_partitions(["boot", "system", "vendor"], dry_run=False)

        assert result == {"boot": True, "system": False, "vendor": True}
        assert any("2/3" in line for line in log)

    def test_empty_partition_list(self) -> None:
        engine, _log = _make_engine()
        result = engine.erase_all_partitions([], dry_run=True)
        assert result == {}


# ── FlashEngine.clean_slate_reflash ──────────────────────────────────────────


class TestCleanSlateReflash:
    def test_dry_run_full_flow(self) -> None:
        engine, log = _make_engine()
        profile = _make_profile()
        images = {"boot": Path("/tmp/boot.img"), "system": Path("/tmp/system.img")}

        with (
            patch("cyberflash.core.flash_engine.FastbootManager"),
            patch("cyberflash.core.flash_engine.PartitionManager") as mock_pm,
        ):
            mock_pm.get_inactive_slot.return_value = "b"
            ok = engine.clean_slate_reflash(profile, images, wipe_userdata=True, dry_run=True)

        assert ok is True
        assert any("CLEAN SLATE REFLASH" in line for line in log)
        assert any("COMPLETE" in line for line in log)

    def test_adds_userdata_to_erase_list(self) -> None:
        engine, _log = _make_engine()
        profile = _make_profile()

        with (
            patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb,
            patch("cyberflash.core.flash_engine.PartitionManager") as mock_pm,
        ):
            mock_fb.erase.return_value = True
            mock_fb.flash.return_value = (True, "OK")
            mock_fb._run.return_value = (0, "", "")
            mock_pm.get_inactive_slot.return_value = "b"
            mock_pm.set_active_slot.return_value = True

            images = {p: Path(f"/tmp/{p}.img") for p in profile.flash.partitions}
            # Make the files "exist" by mocking Path.exists
            with patch.object(Path, "exists", return_value=True):
                engine.clean_slate_reflash(profile, images, wipe_userdata=True, dry_run=False)

        # userdata should be in the erase calls
        erase_calls = [c[0][1] for c in mock_fb.erase.call_args_list]
        assert "userdata" in erase_calls

    def test_skips_userdata_when_not_requested(self) -> None:
        engine, _log = _make_engine()
        profile = _make_profile()

        with (
            patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb,
            patch("cyberflash.core.flash_engine.PartitionManager") as mock_pm,
        ):
            mock_fb.erase.return_value = True
            mock_fb.flash.return_value = (True, "OK")
            mock_fb._run.return_value = (0, "", "")
            mock_pm.get_inactive_slot.return_value = "b"
            mock_pm.set_active_slot.return_value = True

            images = {p: Path(f"/tmp/{p}.img") for p in profile.flash.partitions}
            with patch.object(Path, "exists", return_value=True):
                engine.clean_slate_reflash(profile, images, wipe_userdata=False, dry_run=False)

        erase_calls = [c[0][1] for c in mock_fb.erase.call_args_list]
        assert "userdata" not in erase_calls

    def test_returns_false_on_flash_failure(self) -> None:
        engine, log = _make_engine()
        profile = _make_profile()

        with (
            patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb,
            patch("cyberflash.core.flash_engine.PartitionManager"),
        ):
            mock_fb.erase.return_value = True
            mock_fb.flash.return_value = (False, "I/O error")
            mock_fb._run.return_value = (0, "", "")

            images = {"boot": Path("/tmp/boot.img")}
            with patch.object(Path, "exists", return_value=True):
                ok = engine.clean_slate_reflash(profile, images, dry_run=False)

        assert ok is False
        assert any("CRITICAL" in line for line in log)

    def test_switches_to_inactive_slot(self) -> None:
        engine, _log = _make_engine()
        profile = _make_profile()

        with (
            patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb,
            patch("cyberflash.core.flash_engine.PartitionManager") as mock_pm,
        ):
            mock_fb.erase.return_value = True
            mock_fb.flash.return_value = (True, "OK")
            mock_fb._run.return_value = (0, "", "")
            mock_pm.get_inactive_slot.return_value = "b"
            mock_pm.set_active_slot.return_value = True

            images = {"boot": Path("/tmp/boot.img")}
            with patch.object(Path, "exists", return_value=True):
                engine.clean_slate_reflash(profile, images, wipe_userdata=False, dry_run=False)

        mock_pm.set_active_slot.assert_called_once_with("ABC123", "b", dry_run=False)

    def test_non_ab_device_skips_slot_switch(self) -> None:
        engine, _log = _make_engine()
        profile = _make_profile()
        profile.ab_slots = False

        with (
            patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb,
            patch("cyberflash.core.flash_engine.PartitionManager") as mock_pm,
        ):
            mock_fb.erase.return_value = True
            mock_fb.flash.return_value = (True, "OK")
            mock_fb._run.return_value = (0, "", "")

            images = {"boot": Path("/tmp/boot.img")}
            with patch.object(Path, "exists", return_value=True):
                ok = engine.clean_slate_reflash(profile, images, dry_run=False)

        assert ok is True
        mock_pm.get_inactive_slot.assert_not_called()


# ── FlashWorker erase dispatch ───────────────────────────────────────────────


class TestFlashWorkerEraseDispatch:
    def test_erase_step_calls_wipe_partition(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=[FlashStep(id="erase_boot", label="Erase boot")],
            dry_run=True,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)
        engine.wipe_partition.return_value = True

        step = task.steps[0]
        ok = worker._execute_step(engine, step, task)

        assert ok is True
        engine.wipe_partition.assert_called_once_with("boot", dry_run=True)

    def test_erase_userdata_step(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=[FlashStep(id="erase_userdata", label="Erase userdata")],
            dry_run=True,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)
        engine.wipe_partition.return_value = True

        step = task.steps[0]
        ok = worker._execute_step(engine, step, task)

        assert ok is True
        engine.wipe_partition.assert_called_once_with("userdata", dry_run=True)

    def test_erase_multiple_partitions_sequentially(self) -> None:
        from cyberflash.workers.flash_worker import FlashWorker

        profile = _make_profile()
        erase_steps = [
            FlashStep(id="erase_boot", label="Erase boot"),
            FlashStep(id="erase_system", label="Erase system"),
            FlashStep(id="erase_vendor", label="Erase vendor"),
        ]
        task = FlashTask(
            device_serial="ABC123",
            profile_codename="guacamole",
            steps=erase_steps,
            dry_run=True,
        )
        worker = FlashWorker(task, profile)
        engine = MagicMock(spec=FlashEngine)
        engine.wipe_partition.return_value = True

        for step in task.steps:
            ok = worker._execute_step(engine, step, task)
            assert ok is True

        assert engine.wipe_partition.call_count == 3
        partitions_erased = [c[0][0] for c in engine.wipe_partition.call_args_list]
        assert partitions_erased == ["boot", "system", "vendor"]


# ── WorkflowEngine.plan_clean_slate ──────────────────────────────────────────


class TestPlanCleanSlate:
    def test_generates_workflow_steps(self) -> None:
        device = _make_device()
        engine = WorkflowEngine()
        wf = engine.plan_clean_slate(device)

        assert wf.name == "Clean Slate Reflash"
        assert "unbrick" in wf.description.lower()
        assert len(wf.steps) >= 6  # preflight, load, erase, vbmeta, flash, slot, reboot

    def test_includes_slot_switch_for_ab_device(self) -> None:
        device = _make_device()
        engine = WorkflowEngine()
        wf = engine.plan_clean_slate(device)

        titles = [s.title for s in wf.steps]
        assert "Switch Active Slot" in titles

    def test_excludes_slot_switch_for_non_ab(self) -> None:
        device = _make_device()
        device.has_ab_slots = False
        engine = WorkflowEngine()
        wf = engine.plan_clean_slate(device)

        titles = [s.title for s in wf.steps]
        assert "Switch Active Slot" not in titles

    def test_erase_step_is_critical_risk(self) -> None:
        device = _make_device()
        engine = WorkflowEngine()
        wf = engine.plan_clean_slate(device)

        from cyberflash.core.ai_engine import RiskLevel

        erase_step = next(s for s in wf.steps if "erase" in s.title.lower())
        assert erase_step.risk == RiskLevel.CRITICAL

    def test_has_reboot_verify_step(self) -> None:
        device = _make_device()
        engine = WorkflowEngine()
        wf = engine.plan_clean_slate(device)

        titles = [s.title for s in wf.steps]
        assert "Reboot & Verify" in titles

    def test_workflow_not_complete_initially(self) -> None:
        device = _make_device()
        engine = WorkflowEngine()
        wf = engine.plan_clean_slate(device)

        assert not wf.is_complete
        assert wf.progress == 0.0


# ── Flash page clean-slate step definitions ──────────────────────────────────


class TestCleanSlateStepDefs:
    def test_clean_slate_step_list_constant(self) -> None:
        from cyberflash.ui.pages.flash_page import _FLASH_STEPS_CLEAN_SLATE

        ids = [s[0] for s in _FLASH_STEPS_CLEAN_SLATE]
        # Must have erase steps first, then flash steps
        erase_ids = [i for i in ids if i.startswith("erase_")]
        flash_ids = [i for i in ids if i.startswith("flash_")]
        assert len(erase_ids) >= 3  # at least boot, system, vendor erasure
        assert len(flash_ids) >= 3  # at least boot, system, vendor flash

        # erase comes before flash in the list
        first_erase_idx = ids.index(erase_ids[0])
        first_flash_idx = ids.index(flash_ids[0])
        assert first_erase_idx < first_flash_idx

    def test_clean_slate_has_vbmeta_disable(self) -> None:
        from cyberflash.ui.pages.flash_page import _FLASH_STEPS_CLEAN_SLATE

        ids = [s[0] for s in _FLASH_STEPS_CLEAN_SLATE]
        assert "disable_vbmeta" in ids

    def test_clean_slate_has_reboot_steps(self) -> None:
        from cyberflash.ui.pages.flash_page import _FLASH_STEPS_CLEAN_SLATE

        ids = [s[0] for s in _FLASH_STEPS_CLEAN_SLATE]
        assert "reboot_bootloader" in ids
        assert "reboot_system" in ids

    def test_clean_slate_has_slot_switch(self) -> None:
        from cyberflash.ui.pages.flash_page import _FLASH_STEPS_CLEAN_SLATE

        ids = [s[0] for s in _FLASH_STEPS_CLEAN_SLATE]
        assert "set_active_slot" in ids

    def test_clean_slate_erases_userdata(self) -> None:
        from cyberflash.ui.pages.flash_page import _FLASH_STEPS_CLEAN_SLATE

        ids = [s[0] for s in _FLASH_STEPS_CLEAN_SLATE]
        assert "erase_userdata" in ids


# ── Device profile model ─────────────────────────────────────────────────────


class TestGuacamoleProfile:
    def test_profile_model_is_gm1913(self) -> None:
        """Ensure the profile was updated to the correct GM1913 model."""
        import json

        profile_path = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "profiles"
            / "oneplus"
            / "guacamole.json"
        )
        data = json.loads(profile_path.read_text())
        assert data["model"] == "GM1913"

    def test_profile_has_model_variants(self) -> None:
        import json

        profile_path = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "profiles"
            / "oneplus"
            / "guacamole.json"
        )
        data = json.loads(profile_path.read_text())
        assert "model_variants" in data
        assert "GM1913" in data["model_variants"]
        assert "GM1917" in data["model_variants"]
        assert "GM1911" in data["model_variants"]
