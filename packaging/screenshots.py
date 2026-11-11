"""Regenerate the README screenshots in docs/screenshots from the sample inventory.

    python packaging/screenshots.py

Runs the real app off-screen with examples/inventory.example.json in a throwaway folder, so your own
inventory is never shown or touched.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
TMP = Path(tempfile.mkdtemp(prefix="hostrix-shots-"))

# a throwaway home: the sample inventory, and the key files it names so none show "file not found"
os.environ["HOSTRIX_HOME"] = str(TMP / "config")
os.environ["HOME"] = str(TMP / "home")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
(TMP / "config").mkdir()
(TMP / "home" / ".ssh").mkdir(parents=True)
for key in ("id_ed25519", "db_key"):
    (TMP / "home" / ".ssh" / key).touch()
shutil.copy(ROOT / "examples" / "inventory.example.json", TMP / "config" / "inventory.json")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

from hostrix import gui  # noqa: E402
from hostrix.inventory import Inventory  # noqa: E402

app = gui.make_app()


def settle():
    for _ in range(6):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


def window(theme):
    inv = Inventory()
    inv.settings.theme = theme
    win = gui.build_window(inv)
    win.run_jobs = lambda *a, **k: None   # the sample hosts don't exist; statuses are set below
    win.resize(1640, 860)
    win.show()
    settle()
    win.select_name("vpc-db-01")
    settle()
    return inv, win


def save(widget, name):
    widget.grab().save(str(OUT / f"{name}.png"))
    print("wrote", OUT / f"{name}.png")


for theme in ("light", "dark"):
    inv, win = window(theme)
    save(win, f"main-{theme}")
    if theme == "light":
        names = []
        for s in inv.servers:
            hop = inv.get(s.jump) if s.jump else s
            if s.requires_vpn:
                win.model.set_status(s.name, False, f"{s.host}:{s.port} timed out (VPN connected?)")
            else:
                win.model.set_status(s.name, True, f"{hop.host}:{hop.port} reachable")
            names.append(s.name)
        win._refresh_details()
        win._update_summary()
        win._finish_batch("check", {"quiet": False, "names": names, "pending": set()})
        settle()
        save(win, "check-all")

        dlg = gui.ServerDialog(win, inv, inv.get("vpc-db-01"), title="Edit server")
        dlg.resize(640, 720)
        dlg.show()
        settle()
        save(dlg, "edit-server")
        dlg.close()

        dlg = gui.SettingsDialog(win, inv)
        dlg.resize(660, 720)
        dlg.show()
        settle()
        save(dlg, "settings")
        dlg.close()
    win.close()
    win.deleteLater()
    settle()

shutil.rmtree(TMP, ignore_errors=True)
