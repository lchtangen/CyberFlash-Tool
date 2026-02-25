"""cli.py — CyberFlash command-line interface.

Provides a non-Qt argparse CLI for scripted/headless use of CyberFlash
core operations: flash, root, backup, restore, device info, and journal.

Usage:
    cyberflash-cli flash --serial <serial> --rom <path>
    cyberflash-cli info --serial <serial>
    cyberflash-cli journal --list
    cyberflash-cli backup --serial <serial> --dest /tmp/backup
    cyberflash-cli root --serial <serial> detect
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _out(data: object, as_json: bool = False) -> None:
    """Print *data* as JSON or human-readable text."""
    if as_json:
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2, default=str))
        else:
            print(json.dumps({"result": str(data)}, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {v}")
        elif isinstance(data, list):
            for item in data:
                print(f"  {item}")
        else:
            print(str(data))


# ── Sub-command handlers ──────────────────────────────────────────────────────


def _cmd_info(args: argparse.Namespace) -> int:
    """Display device information."""
    from cyberflash.core.adb_manager import AdbManager

    if not args.serial:
        devices = AdbManager.list_devices()
        if not devices:
            _out("No ADB devices connected", args.json)
            return 1
        if len(devices) == 1:
            args.serial = devices[0][0]
        else:
            print("Multiple devices found. Use --serial to specify one:")
            for serial, state in devices:
                print(f"  {serial}  ({state})")
            return 1

    props = AdbManager.get_props_batch(args.serial, [
        "ro.product.model",
        "ro.product.manufacturer",
        "ro.product.device",
        "ro.build.version.release",
        "ro.build.version.security_patch",
        "ro.serialno",
        "ro.boot.flash.locked",
    ])
    _out(props, args.json)
    return 0


def _cmd_flash(args: argparse.Namespace) -> int:
    """Flash a ROM file to a device."""
    from cyberflash.core.flash_engine import FlashEngine

    if not args.serial:
        print("Error: --serial is required for flash", file=sys.stderr)
        return 1
    if not args.rom:
        print("Error: --rom is required for flash", file=sys.stderr)
        return 1

    rom_path = Path(args.rom)
    if not rom_path.exists():
        print(f"Error: ROM file not found: {rom_path}", file=sys.stderr)
        return 1

    log_lines: list[str] = []

    def log_cb(msg: str) -> None:
        log_lines.append(msg)
        if not args.json:
            print(f"  {msg}")

    engine = FlashEngine(
        serial=args.serial,
        rom_path=rom_path,
        dry_run=args.dry_run,
        log_cb=log_cb,
    )
    success = engine.run()

    if args.json:
        _out({"success": success, "log": log_lines}, args.json)
    else:
        status = "SUCCESS" if success else "FAILED"
        print(f"\n[{status}]")

    return 0 if success else 1


def _cmd_root(args: argparse.Namespace) -> int:
    """Detect or manage root on a device."""
    from cyberflash.core.root_manager import RootManager

    if not args.serial:
        print("Error: --serial is required for root command", file=sys.stderr)
        return 1

    action = args.root_action if hasattr(args, "root_action") else "detect"

    if action == "detect":
        state = RootManager.detect_root(args.serial)
        _out({"serial": args.serial, "root_state": str(state)}, args.json)
    else:
        print(f"Unknown root action: {action}", file=sys.stderr)
        return 1

    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    """Backup device data."""

    if not args.serial:
        print("Error: --serial is required for backup", file=sys.stderr)
        return 1
    if not args.dest:
        print("Error: --dest is required for backup", file=sys.stderr)
        return 1

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Basic contacts + media backup
    from cyberflash.core.contacts_manager import ContactsManager

    vcf = ContactsManager.backup_contacts(args.serial, dest)
    sms = ContactsManager.backup_sms(args.serial, dest)

    result = {
        "contacts": str(vcf) if vcf else None,
        "sms": str(sms) if sms else None,
    }
    _out(result, args.json)
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    """Restore device data from backup."""
    if not args.serial:
        print("Error: --serial is required for restore", file=sys.stderr)
        return 1
    _out({"status": "restore not implemented in CLI — use GUI"}, args.json)
    return 0


def _cmd_journal(args: argparse.Namespace) -> int:
    """View or export the flash journal."""
    from cyberflash.core.flash_journal import FlashJournal

    journal = FlashJournal.default()

    if args.journal_action == "export-csv":
        dest = Path(args.output or "journal.csv")
        ok = journal.export_csv(dest)
        _out({"exported": str(dest), "success": ok}, args.json)
    elif args.journal_action == "export-html":
        dest = Path(args.output or "journal.html")
        ok = journal.export_html(dest)
        _out({"exported": str(dest), "success": ok}, args.json)
    else:
        entries = journal.load_all()
        if args.json:
            _out([e.to_dict() for e in entries], args.json)
        else:
            if not entries:
                print("  (no journal entries)")
            for e in entries:
                status = "✓" if e.success else "✗"
                print(f"  [{status}] {e.timestamp[:19]}  {e.serial}  {e.operation}")
    return 0


# ── Parser ────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cyberflash-cli",
        description="CyberFlash CLI — Android ROM flash tool",
    )
    parser.add_argument("--serial", "-s", help="Target device serial")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Simulate operations")

    sub = parser.add_subparsers(dest="command", required=True)

    # info
    sub.add_parser("info", help="Show device information")

    # flash
    flash_p = sub.add_parser("flash", help="Flash a ROM to device")
    flash_p.add_argument("--rom", "-r", help="Path to ROM zip/image file")

    # root
    root_p = sub.add_parser("root", help="Root detection/management")
    root_p.add_argument(
        "root_action",
        nargs="?",
        default="detect",
        choices=["detect"],
    )

    # backup
    backup_p = sub.add_parser("backup", help="Backup device data")
    backup_p.add_argument("--dest", "-d", help="Destination directory")

    # restore
    restore_p = sub.add_parser("restore", help="Restore device data")
    restore_p.add_argument("--src", help="Source backup directory")

    # journal
    journal_p = sub.add_parser("journal", help="View/export flash journal")
    journal_p.add_argument(
        "journal_action",
        nargs="?",
        default="list",
        choices=["list", "export-csv", "export-html"],
    )
    journal_p.add_argument("--output", "-o", help="Output file path")

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> int:
    """Main entry point for ``cyberflash-cli``."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args()

    _handlers = {
        "info":    _cmd_info,
        "flash":   _cmd_flash,
        "root":    _cmd_root,
        "backup":  _cmd_backup,
        "restore": _cmd_restore,
        "journal": _cmd_journal,
    }

    handler = _handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        logger.debug("CLI exception", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
