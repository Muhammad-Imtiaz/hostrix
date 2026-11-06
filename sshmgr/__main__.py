"""Entry point: GUI by default, plus a few CLI helpers.

    ssh-manager                      open the GUI (detaches from the terminal)
    ssh-manager --hidden             start in the background without a window
    ssh-manager --foreground         keep the GUI attached to the terminal
    ssh-manager show | quit          show / stop the running instance
    ssh-manager connect NAME         ssh into NAME in the current terminal
    ssh-manager list                 print the inventory
    ssh-manager command NAME         print the full ssh command for NAME
    ssh-manager fetch-hostnames [NAME...]  log in and record each server's hostname
    ssh-manager import FILE.json     merge servers from a JSON file
    ssh-manager import-ssh-config [PATH]   merge hosts from an OpenSSH config
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import AUTHOR, __version__
from .inventory import Inventory, InventoryError, Server, parse_ssh_config


def _merge(inv: Inventory, servers: list[Server]) -> None:
    added = skipped = 0
    # jump hosts first so references validate
    for s in sorted(servers, key=lambda s: bool(s.jump)):
        if inv.get(s.name):
            skipped += 1
            continue
        try:
            inv.upsert(s)
            added += 1
        except InventoryError as e:
            print(f"skip {s.name}: {e}", file=sys.stderr)
            skipped += 1
    inv.save()
    print(f"Added {added}, skipped {skipped}. Inventory: {inv.path}")


def _fetch_hostnames(inv: Inventory, names: list[str], refresh: bool) -> int:
    from concurrent.futures import ThreadPoolExecutor

    from .connect import fetch_hostname, tcp_reachable

    unknown = [n for n in names if not inv.get(n)]
    if unknown:
        print(f"Unknown server(s): {', '.join(unknown)}", file=sys.stderr)
        return 1
    targets = [inv.get(n) for n in names] if names else [s for s in inv.servers if refresh or not s.hostname]

    def work(s: Server):
        ok, msg = tcp_reachable(inv, s)
        return (s, *fetch_hostname(inv, s)) if ok else (s, False, msg)

    failed = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        for s, ok, msg in pool.map(work, targets):
            print(f"{'OK  ' if ok else 'FAIL'} {s.name:28} {msg}")
            if ok:
                s.hostname = msg
            else:
                failed += 1
    inv.save()
    print(f"\n{len(targets) - failed}/{len(targets)} hostnames updated.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ssh-manager", description="SSH server inventory and launcher")
    p.add_argument("--version", action="version", version=f"ssh-manager {__version__} by {AUTHOR}")
    p.add_argument("--inventory", type=Path, help="path to inventory.json")
    p.add_argument("--hidden", action="store_true", help="start in the background without showing the window")
    p.add_argument("--foreground", action="store_true", help="do not detach from the terminal")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("gui")
    sub.add_parser("show")
    sub.add_parser("quit")
    sub.add_parser("selftest", help="build the main window off-screen and exit (used by CI)")
    c = sub.add_parser("connect")
    c.add_argument("name")
    sub.add_parser("list")
    c = sub.add_parser("command")
    c.add_argument("name")
    c = sub.add_parser("fetch-hostnames")
    c.add_argument("names", nargs="*", help="default: all servers")
    c.add_argument("--all", action="store_true", help="also refresh servers that already have a hostname")
    c = sub.add_parser("import")
    c.add_argument("file", type=Path)
    c = sub.add_parser("import-ssh-config")
    c.add_argument("file", type=Path, nargs="?", default=Path.home() / ".ssh" / "config")
    args = p.parse_args(argv)

    inv = Inventory(args.inventory)

    if args.cmd == "selftest":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from .gui import build_window, make_app
        app = make_app()
        win = build_window(inv)
        win.reload()
        print(f"selftest ok: {__version__}, {len(inv.servers)} servers, Qt platform {app.platformName()}")
        return 0
    if args.cmd in ("show", "quit"):
        from .background import send_command
        if send_command(args.cmd):
            return 0
        if args.cmd == "quit":
            print("SSH Manager is not running.")
            return 0
        args.cmd = None  # nothing to show: start it
    if args.cmd in (None, "gui"):
        if not args.foreground and sys.stdin is not None and sys.stdin.isatty():
            # started from a terminal: give the prompt back immediately
            from .background import detach
            gui_args = (["--inventory", str(inv.path)] if args.inventory else []) + (
                ["--hidden"] if args.hidden else [])
            return detach(gui_args)
        from .gui import run
        return run(inv, hidden=args.hidden)

    from .connect import display_command, run_interactive

    if args.cmd == "connect":
        return run_interactive(inv, args.name)
    if args.cmd == "list":
        for s in sorted(inv.servers, key=lambda s: (s.group, s.name)):
            print(f"{s.name:28} {s.host:17} {s.public_ip or '-':17} {inv.effective_user(s):10} {s.group:14} "
                  f"{s.description}")
        return 0
    if args.cmd == "command":
        s = inv.get(args.name)
        if not s:
            print(f"Unknown server: {args.name}", file=sys.stderr)
            return 1
        print(display_command(inv, s))
        return 0
    if args.cmd == "fetch-hostnames":
        return _fetch_hostnames(inv, args.names, args.all)
    if args.cmd == "import":
        data = json.loads(args.file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # fill in defaults that are not set yet
            for key, value in data.get("settings", {}).items():
                if hasattr(inv.settings, key) and getattr(inv.settings, key) in ("", "auto"):
                    setattr(inv.settings, key, value)
        _merge(inv, [Server.from_dict(d) for d in data.get("servers", data if isinstance(data, list) else [])])
        return 0
    if args.cmd == "import-ssh-config":
        _merge(inv, parse_ssh_config(args.file.read_text(encoding="utf-8")))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
