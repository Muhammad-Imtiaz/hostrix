"""Server inventory: data model, JSON persistence and ssh_config export.

The inventory lives in a single JSON file (default
``~/.config/ssh-manager/inventory.json``). Every save also regenerates an
OpenSSH-compatible ``ssh_config`` next to it, so the same servers can be used
from any terminal with ``ssh <name>`` after adding one ``Include`` line to
``~/.ssh/config``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def config_dir() -> Path:
    override = os.environ.get("SSH_MANAGER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ssh-manager"


@dataclass
class Server:
    name: str                      # unique alias, also used as the ssh_config Host
    host: str                      # IP address or DNS name ssh connects to
    public_ip: str = ""            # public address, shown in the list and searchable (informational)
    user: str = ""
    port: int = 22
    hostname: str = ""             # the machine's own hostname (informational)
    key_path: str = ""
    jump: str = ""                 # name of another server used as a jump host
    requires_vpn: bool = False
    group: str = ""
    description: str = ""
    extra_options: list[str] = field(default_factory=list)  # e.g. ["ServerAliveInterval=30"]

    @classmethod
    def from_dict(cls, data: dict) -> "Server":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        clean["port"] = int(clean.get("port") or 22)
        return cls(**clean)


@dataclass
class Settings:
    default_user: str = ""
    default_key: str = ""
    # "auto" or a command template containing {cmd} (shell-quoted command) or
    # {args} (argument list appended), e.g. "gnome-terminal -- {args}".
    terminal: str = "auto"
    theme: str = "system"              # system | light | dark
    font_size: int = 11                # points
    keep_running_on_close: bool = False  # closing the window hides it instead of quitting
    background_hint_shown: bool = False


class InventoryError(ValueError):
    pass


class Inventory:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config_dir() / "inventory.json"
        self.servers: list[Server] = []
        self.settings = Settings()
        self.load()

    # ---- persistence -------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            self.servers, self.settings = [], Settings()
            return
        data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        self.servers = [Server.from_dict(s) for s in data.get("servers", [])]
        known = {f.name for f in fields(Settings)}
        self.settings = Settings(**{k: v for k, v in data.get("settings", {}).items() if k in known})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "settings": asdict(self.settings),
            "servers": [asdict(s) for s in sorted(self.servers, key=lambda s: (s.group.lower(), s.name.lower()))],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        self.write_ssh_config()

    # ---- queries -----------------------------------------------------
    def get(self, name: str) -> Server | None:
        return next((s for s in self.servers if s.name == name), None)

    def groups(self) -> list[str]:
        return sorted({s.group for s in self.servers if s.group}, key=str.lower)

    def effective_user(self, s: Server) -> str:
        return s.user or self.settings.default_user

    def effective_key(self, s: Server) -> str:
        return s.key_path or self.settings.default_key

    # ---- mutations ---------------------------------------------------
    def validate(self, server: Server, original_name: str | None = None) -> None:
        if not NAME_RE.match(server.name or ""):
            raise InventoryError("Name may only contain letters, digits, '.', '_' and '-'.")
        if not server.host.strip():
            raise InventoryError("Host / IP is required.")
        if not (0 < int(server.port) < 65536):
            raise InventoryError("Port must be between 1 and 65535.")
        clash = self.get(server.name)
        if clash is not None and server.name != original_name:
            raise InventoryError(f"A server named '{server.name}' already exists.")
        if server.jump:
            if server.jump in (server.name, original_name):
                raise InventoryError("A server cannot be its own jump host.")
            jump = self.get(server.jump)
            if jump is None:
                raise InventoryError(f"Jump host '{server.jump}' is not in the inventory.")
            if jump.jump:
                raise InventoryError(f"Jump host '{server.jump}' itself uses a jump host; only one hop is supported.")

    def upsert(self, server: Server, original_name: str | None = None) -> None:
        self.validate(server, original_name)
        if original_name and original_name != server.name:
            # keep references from other servers pointing at the renamed one
            for s in self.servers:
                if s.jump == original_name:
                    s.jump = server.name
        target = original_name or server.name
        for i, s in enumerate(self.servers):
            if s.name == target:
                self.servers[i] = server
                break
        else:
            self.servers.append(server)

    def dependents(self, name: str) -> list[str]:
        return [s.name for s in self.servers if s.jump == name]

    def delete(self, name: str) -> None:
        deps = self.dependents(name)
        if deps:
            raise InventoryError(f"'{name}' is the jump host for: {', '.join(deps)}")
        self.servers = [s for s in self.servers if s.name != name]

    # ---- ssh_config export ------------------------------------------
    @property
    def ssh_config_path(self) -> Path:
        return self.path.parent / "ssh_config"

    def render_ssh_config(self) -> str:
        lines = [
            "# Generated by SSH Manager - edits here are overwritten.",
            "# Use it from any terminal by adding this line to the TOP of ~/.ssh/config:",
            f"#   Include {self.ssh_config_path}",
            "",
        ]
        for s in sorted(self.servers, key=lambda s: s.name.lower()):
            if s.description:
                lines.append(f"# {s.description}")
            lines.append(f"Host {s.name}")
            lines.append(f"    HostName {s.host}")
            if self.effective_user(s):
                lines.append(f"    User {self.effective_user(s)}")
            if s.port != 22:
                lines.append(f"    Port {s.port}")
            if self.effective_key(s):
                lines.append(f'    IdentityFile "{self.effective_key(s)}"')
                lines.append("    IdentitiesOnly yes")
            if s.jump:
                lines.append(f"    ProxyJump {s.jump}")
            for opt in s.extra_options:
                key, _, value = opt.partition("=")
                lines.append(f"    {key.strip()} {value.strip()}")
            lines.append("")
        return "\n".join(lines)

    def write_ssh_config(self) -> None:
        self.ssh_config_path.write_text(self.render_ssh_config(), encoding="utf-8")


# ---- import from an existing ~/.ssh/config ---------------------------
def parse_ssh_config(text: str) -> list[Server]:
    """Parse concrete Host blocks (no wildcards) from OpenSSH config text."""
    servers: list[Server] = []
    current: list[Server] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\s*=\s*|\s+", line, maxsplit=1)
        key = parts[0].lower()
        value = parts[1].strip().strip('"') if len(parts) > 1 else ""
        if key == "host":
            current = [Server(name=h, host=h) for h in value.split() if not any(c in h for c in "*?!")]
            servers.extend(current)
        elif key == "match":
            current = []
        for s in current:
            if key == "hostname":
                s.host = value
            elif key == "user":
                s.user = value
            elif key == "port":
                s.port = int(value)
            elif key == "identityfile":
                s.key_path = value
            elif key == "proxyjump" and value.lower() != "none":
                s.jump = value.split(",")[0].split("@")[-1].split(":")[0]
            elif key not in ("host", "hostname", "user", "port", "identityfile", "proxyjump", "identitiesonly"):
                s.extra_options.append(f"{parts[0]}={value}")
    return servers
