from __future__ import annotations

import contextlib
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from cyberflash.core.tool_manager import ToolManager

logger = logging.getLogger(__name__)


class EdlEngine:
    """Wraps bkerler/edl CLI via subprocess for Firehose EDL operations.

    All methods call self._log(), return False on failure, never raise.
    No Qt imports — safe to instantiate in worker threads.
    """

    EDL_TIMEOUT = 600  # seconds for full restore

    def __init__(
        self,
        device_serial: str,
        log_cb: Callable[[str], None] | None = None,
    ) -> None:
        self.device_serial = device_serial
        self._log_cb = log_cb

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logger.info("[%s] %s", self.device_serial, msg)
        if self._log_cb:
            self._log_cb(msg)

    def _run_edl(
        self, args: list[str], timeout: int = EDL_TIMEOUT
    ) -> tuple[int, str, str]:
        """Run edl CLI with the given args, streaming output line-by-line via _log.

        Returns (returncode, full_stdout, "").
        """
        cmd = ToolManager.edl_cmd() + args
        self._log(f"Running: {' '.join(str(a) for a in cmd)}")
        full_output: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip("\n")
                if line:
                    self._log(line)
                    full_output.append(line)
            proc.wait(timeout=timeout)
            return proc.returncode, "\n".join(full_output), ""
        except subprocess.TimeoutExpired:
            self._log(f"EDL command timed out after {timeout}s")
            with contextlib.suppress(Exception):
                proc.kill()
            return -1, "\n".join(full_output), "timeout"
        except FileNotFoundError:
            self._log("edl tool not found — install with: pip install edl")
            return -1, "", "edl not found"
        except Exception as exc:
            self._log(f"EDL subprocess error: {exc}")
            return -1, "\n".join(full_output), str(exc)

    # ── Tool availability ─────────────────────────────────────────────────────

    def is_edl_tool_available(self) -> bool:
        return ToolManager.is_edl_available()

    # ── Device info ───────────────────────────────────────────────────────────

    def get_device_info(self, dry_run: bool = False) -> dict[str, str]:
        """Query basic device info via 'edl info'. Returns parsed key-value dict."""
        self._log("Querying EDL device info…")
        if dry_run:
            self._log("[dry-run] Would run: edl info")
            return {"dry_run": "true"}

        rc, stdout, _ = self._run_edl(["info"], timeout=30)
        result: dict[str, str] = {}
        if rc != 0:
            self._log("EDL info failed")
            return result

        for line in stdout.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip()
        return result

    # ── Primary automated restore ─────────────────────────────────────────────

    def flash_with_rawprogram(
        self,
        programmer: Path,
        rawprogram_xml: Path,
        patch_xml: Path | None,
        package_dir: Path,
        dry_run: bool = False,
    ) -> bool:
        """Fully automated EDL restore using rawprogram.xml — equivalent to MSM Download Tool.

        Runs: edl qfil <rawprogram_xml> [<patch_xml>] --loader <programmer>
        bkerler/edl automatically:
          1. Sends programmer.elf to device via Sahara protocol
          2. Initializes UFS/eMMC storage
          3. Parses rawprogram_xml → flashes each partition image sequentially
          4. Applies patch_xml patches
          5. Reboots device to system

        Returns True only when edl exits with rc==0.
        """
        self._log("Starting automated EDL restore (rawprogram method)…")

        if not programmer.exists():
            self._log(f"Programmer not found: {programmer}")
            return False
        if not rawprogram_xml.exists():
            self._log(f"rawprogram XML not found: {rawprogram_xml}")
            return False

        if dry_run:
            self._log(f"[dry-run] Would run: edl qfil {rawprogram_xml.name}"
                      f"{' ' + patch_xml.name if patch_xml else ''}"
                      f" --loader {programmer.name}")
            self._log(f"[dry-run] Working directory: {package_dir}")
            self._log("[dry-run] Steps: Sahara programmer upload → storage init → "
                      "partition flash → patches → reboot")
            return True

        args = ["qfil", str(rawprogram_xml)]
        if patch_xml and patch_xml.exists():
            args.append(str(patch_xml))
        args += ["--loader", str(programmer)]

        # Run from package_dir so edl can find partition .bin images by relative path
        self._log(f"Working directory: {package_dir}")
        self._log("Sending programmer to device (Sahara)…")

        rc, _, _ = self._run_edl(args, timeout=self.EDL_TIMEOUT)
        if rc == 0:
            self._log("EDL restore completed successfully.")
            return True
        else:
            self._log(f"EDL restore FAILED (exit code {rc})")
            return False

    # ── Individual partition operations ──────────────────────────────────────

    def flash_partition(
        self, partition: str, image: Path, dry_run: bool = False
    ) -> bool:
        """Flash a single partition: edl -w <partition> <image>."""
        self._log(f"Flashing partition {partition} ← {image.name}")
        if dry_run:
            self._log(f"[dry-run] Would run: edl -w {partition} {image}")
            return True
        if not image.exists():
            self._log(f"Image not found: {image}")
            return False
        rc, _, _ = self._run_edl(["-w", partition, str(image)])
        if rc != 0:
            self._log(f"Flash {partition} FAILED")
            return False
        self._log(f"Flash {partition} OK")
        return True

    def dump_partition(
        self, partition: str, output: Path, dry_run: bool = False
    ) -> bool:
        """Dump a partition to a file: edl -r <partition> <output>."""
        self._log(f"Dumping partition {partition} → {output.name}")
        if dry_run:
            self._log(f"[dry-run] Would run: edl -r {partition} {output}")
            return True
        rc, _, _ = self._run_edl(["-r", partition, str(output)])
        if rc != 0:
            self._log(f"Dump {partition} FAILED")
            return False
        self._log(f"Dump {partition} OK: {output}")
        return True

    def erase_partition(self, partition: str, dry_run: bool = False) -> bool:
        """Erase a partition: edl -e <partition>."""
        self._log(f"Erasing partition {partition}")
        if dry_run:
            self._log(f"[dry-run] Would run: edl -e {partition}")
            return True
        rc, _, _ = self._run_edl(["-e", partition])
        if rc != 0:
            self._log(f"Erase {partition} FAILED")
            return False
        self._log(f"Erase {partition} OK")
        return True
