"""Running in the background: detaching, single instance and autostart."""

from __future__ import annotations

import getpass
import hashlib
import os
import shlex
import subprocess
import sys
from pathlib import Path

from .connect import child_env, is_wsl, self_command
from .inventory import config_dir

# one running instance per user and inventory folder (a test copy with HOSTRIX_HOME won't collide)
SOCKET_NAME = f"hostrix-{getpass.getuser()}-{hashlib.sha1(str(config_dir()).encode()).hexdigest()[:8]}"
AUTOSTART_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "hostrix.desktop"
LEGACY_AUTOSTART_FILE = AUTOSTART_DIR / "ssh-manager.desktop"   # from before the rename to Hostrix


def log_path() -> Path:
    return config_dir() / "hostrix.log"


def detach(gui_args: list[str]) -> int:
    """Re-launch the GUI as a background process and return immediately."""
    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        kwargs = dict(stdin=subprocess.DEVNULL, stdout=out, stderr=out, env=child_env())
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(self_command() + gui_args + ["--foreground"], **kwargs)
    print(f"Hostrix is running in the background (pid {proc.pid}).")
    print("  hostrix        show the window again")
    print("  hostrix quit   stop it")
    return 0


def send_command(message: str, timeout_ms: int = 500) -> bool:
    """Send *message* to a running instance. Returns False if none is running."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtNetwork import QLocalSocket

    _app = QCoreApplication.instance() or QCoreApplication([])
    sock = QLocalSocket()
    sock.connectToServer(SOCKET_NAME)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(message.encode())
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


# ---- start on login (Linux desktops) ---------------------------------
def autostart_supported() -> bool:
    return sys.platform.startswith("linux") and not is_wsl()


def autostart_enabled() -> bool:
    return AUTOSTART_FILE.exists()


def migrate_legacy_autostart() -> None:
    """If the pre-rename app started on login, start Hostrix on login instead."""
    if autostart_supported() and LEGACY_AUTOSTART_FILE.exists():
        set_autostart(True)
        LEGACY_AUTOSTART_FILE.unlink(missing_ok=True)


def set_autostart(enabled: bool) -> None:
    if not enabled:
        AUTOSTART_FILE.unlink(missing_ok=True)
        return
    AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART_FILE.write_text(
        "[Desktop Entry]\nType=Application\nName=Hostrix\n"
        f"Exec={shlex.join(self_command() + ['--hidden'])}\n"
        "Icon=hostrix\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
