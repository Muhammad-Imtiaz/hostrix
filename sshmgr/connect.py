"""Build ssh command lines, probe reachability and open terminals."""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from .inventory import Inventory, Server

COMMON_OPTS = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]


def _expand(path: str) -> str:
    return os.path.expanduser(path) if path else path


def _target(inv: Inventory, s: Server) -> str:
    user = inv.effective_user(s)
    return f"{user}@{s.host}" if user else s.host


def _base_args(inv: Inventory, s: Server) -> list[str]:
    args = ["ssh"]
    key = inv.effective_key(s)
    if key:
        args += ["-i", _expand(key), "-o", "IdentitiesOnly=yes"]
    if s.port != 22:
        args += ["-p", str(s.port)]
    for opt in s.extra_options:
        args += ["-o", opt]
    return args


def ssh_args(inv: Inventory, s: Server, batch: bool = False, remote_cmd: str | None = None) -> list[str]:
    """Return the argv that connects to *s* (through its jump host, if any)."""
    args = _base_args(inv, s) + COMMON_OPTS
    if batch:
        args += ["-o", "BatchMode=yes"]
    if s.jump:
        jump = inv.get(s.jump)
        if jump is None:
            raise ValueError(f"Jump host '{s.jump}' not found")
        proxy = _base_args(inv, jump) + COMMON_OPTS
        if batch:
            proxy += ["-o", "BatchMode=yes"]
        proxy += ["-W", "%h:%p", _target(inv, jump)]
        args += ["-o", "ProxyCommand=" + shlex.join(proxy)]
    args.append(_target(inv, s))
    if remote_cmd:
        args.append(remote_cmd)
    return args


def display_command(inv: Inventory, s: Server) -> str:
    """Copy-pasteable command, keeping ~ unexpanded for readability."""
    home = str(Path.home())
    return shlex.join(ssh_args(inv, s)).replace(home + "/", "~/")


def key_exists(inv: Inventory, s: Server) -> bool | None:
    key = inv.effective_key(s)
    return Path(_expand(key)).is_file() if key else None


def tcp_reachable(inv: Inventory, s: Server, timeout: float = 3.0) -> tuple[bool, str]:
    """TCP check of port 22 on the first hop (jump host if one is used)."""
    hop = inv.get(s.jump) if s.jump else s
    hop = hop or s
    try:
        with socket.create_connection((hop.host, hop.port), timeout=timeout):
            return True, f"{hop.host}:{hop.port} reachable"
    except OSError as e:
        hint = " (VPN connected?)" if s.requires_vpn else ""
        return False, f"{hop.host}:{hop.port} {e.strerror or e}{hint}"


def fetch_hostname(inv: Inventory, s: Server, timeout: int = 20) -> tuple[bool, str]:
    """Log in non-interactively and return the server's `hostname`."""
    try:
        out = subprocess.run(
            ssh_args(inv, s, batch=True, remote_cmd="hostname"),
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    if out.returncode == 0 and out.stdout.strip():
        return True, out.stdout.strip().splitlines()[-1]
    return False, (out.stderr.strip().splitlines() or ["ssh failed"])[-1]


# ---- terminal launching ----------------------------------------------
def self_command() -> list[str]:
    """argv that re-invokes this program (frozen binary or python module)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "sshmgr"]


def is_wsl() -> bool:
    return sys.platform.startswith("linux") and "microsoft" in os.uname().release.lower()


# (binary, args placed before the command)
LINUX_TERMINALS = [
    ("gnome-terminal", ["--"]),
    ("ptyxis", ["--"]),
    ("kgx", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("tilix", ["-e"]),
    ("mate-terminal", ["-x"]),
    ("terminator", ["-x"]),
    ("kitty", []),
    ("alacritty", ["-e"]),
    ("wezterm", ["start", "--"]),
    ("foot", []),
    ("x-terminal-emulator", ["-e"]),
    ("xterm", ["-e"]),
]


def terminal_argv(cmd: list[str], title: str, template: str = "auto") -> list[str]:
    """Wrap *cmd* so it runs in a new terminal window."""
    if template and template != "auto":
        if "{args}" in template:
            head = template.replace("{args}", "").replace("{title}", title)
            return shlex.split(head) + cmd
        return shlex.split(template.replace("{title}", shlex.quote(title)).replace("{cmd}", shlex.quote(shlex.join(cmd))))

    if sys.platform == "win32":
        if shutil.which("wt"):
            return ["wt", "-w", "0", "new-tab", "--title", title] + cmd
        return ["cmd", "/c", "start", title, "cmd", "/k", subprocess.list2cmdline(cmd)]

    if sys.platform == "darwin":
        script = f'tell application "Terminal" to do script "{shlex.join(cmd)}"'
        return ["osascript", "-e", script, "-e", 'tell application "Terminal" to activate']

    if is_wsl() and shutil.which("wt.exe"):
        distro = os.environ.get("WSL_DISTRO_NAME", "")
        wsl = ["wsl.exe"] + (["-d", distro] if distro else []) + ["--cd", "~", "--"]
        return ["wt.exe", "-w", "0", "new-tab", "--title", title] + wsl + cmd

    for binary, prefix in LINUX_TERMINALS:
        if shutil.which(binary):
            return [binary] + prefix + cmd
    raise RuntimeError("No terminal emulator found. Set one in Settings (e.g. 'xterm -e {args}').")


def open_in_terminal(inv: Inventory, s: Server) -> list[str]:
    """Open a new terminal window running `ssh-manager connect <name>`."""
    argv = terminal_argv(self_command() + ["connect", s.name], s.name, inv.settings.terminal)
    subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return argv


def run_interactive(inv: Inventory, name: str) -> int:
    """Used inside the spawned terminal: run ssh and keep errors visible."""
    s = inv.get(name)
    if s is None:
        print(f"Unknown server: {name}")
        input("Press Enter to close...")
        return 1
    banner = f"{s.name}  ({s.hostname or s.host})"
    print(f"\033]0;{s.name}\007", end="")  # terminal title
    print(f"Connecting to {banner}" + (" via " + s.jump if s.jump else ""))
    if s.requires_vpn:
        print("Note: this server requires VPN.")
    rc = subprocess.call(ssh_args(inv, s))
    if rc not in (0, 130):
        print(f"\nssh exited with code {rc}.")
        try:
            input("Press Enter to close...")
        except EOFError:
            pass
    return rc
