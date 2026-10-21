# SSH Manager

A desktop app for keeping an inventory of SSH servers and opening a session with one click,
so you don't have to remember IPs, hostnames, users, keys or jump hosts.

- Table of servers: name, hostname, IP, user, group, access (Direct / VPN / via jump host), description
- Details panel: key path (warns if the file is missing), jump host, full `ssh` command
- Add, edit, duplicate and delete servers; group filter and instant search
- **Connect** (double-click / Enter) opens a new terminal tab running ssh
- **Test** / **Check all**: TCP check of port 22 on the first hop (hints "VPN connected?" for VPN servers)
- **Fetch hostname(s)**: logs in non-interactively and fills in each server's real hostname
- Import from `~/.ssh/config` or JSON, export to JSON
- Web-dashboard style UI: light / dark / system theme, adjustable font size, right-click menu, toasts
- Runs in the background: closing the window keeps it running; run `ssh-manager` again to bring it back

## Install (Ubuntu)

```bash
packaging/build.sh                                   # builds dist/ssh-manager/ + .deb
sudo apt install ./dist/ssh-manager_0.2.0_amd64.deb
ssh-manager                                          # or launch "SSH Manager" from the app menu
```

The `.deb` installs a self-contained app (Python and Qt bundled) to `/opt/ssh-manager`,
with `ssh-manager` on the PATH, so nothing else is needed.

## Background mode

- `ssh-manager` started from a terminal detaches right away and gives you the prompt back.
- Closing the window keeps it running (turn off in Settings). Run `ssh-manager` again, or open it from the
  app menu, to bring the same window back. Only one instance runs at a time.
- `ssh-manager --hidden` starts it without a window; `ssh-manager quit` stops it.
- On desktops with a system tray, a tray icon shows/hides the window and has a quick-connect menu.
  On Linux desktops (not WSL), Settings can start it in the background when you log in.
- `--foreground` keeps it attached to the terminal (useful for debugging); otherwise logs go to
  `~/.config/ssh-manager/ssh-manager.log`.

## Inventory

All servers live in one JSON file. Its location depends on the OS:

| OS | Inventory file |
|---|---|
| Linux / WSL | `~/.config/ssh-manager/inventory.json` |
| macOS | `~/Library/Application Support/ssh-manager/inventory.json` |
| Windows | `%APPDATA%\ssh-manager\inventory.json` |

Set `SSH_MANAGER_HOME` to use a different folder. The file is created on the first save, so it's fine
if it doesn't exist yet.

### Start from the sample

[`examples/inventory.example.json`](examples/inventory.example.json) shows every kind of entry: a jump host,
servers behind it, a server with its own user and key, a VPN-only server, and one with a custom port and
extra ssh options. Edit it with your servers, then use it in one of two ways.

Copy it into place. This replaces any existing inventory:

```bash
mkdir -p ~/.config/ssh-manager
cp examples/inventory.example.json ~/.config/ssh-manager/inventory.json
```

Or merge it into the inventory you already have. Servers whose `name` already exists are skipped, and
settings are only filled in where they're still empty:

```bash
ssh-manager import examples/inventory.example.json
```

A running app picks up changes to the file automatically. You can also add servers in the app with
**Add server**, or with **Import / Export → Import ~/.ssh/config**.

### Server fields

Only `name` and `host` are required.

| Field | Example | Meaning |
|---|---|---|
| `name` | `vpc-app-01` | Unique alias: letters, digits, `.`, `_`, `-`. Also used as `ssh <name>` |
| `host` | `10.0.1.11` | IP address or DNS name to connect to |
| `hostname` | `app-01` | The machine's own hostname, shown in the list. **Fetch hostname** fills it in |
| `user` | `dbadmin` | Login user. Empty = `default_user` |
| `port` | `2222` | SSH port. Default `22` |
| `key_path` | `~/.ssh/db_key` | Private key. Empty = `default_key` |
| `jump` | `bastion` | `name` of another server to use as the jump host (one hop) |
| `requires_vpn` | `true` | Shows a VPN badge and a "VPN connected?" hint when unreachable |
| `group` | `Production` | Groups in the sidebar |
| `description` | `Primary database` | Free text, searchable |
| `extra_options` | `["ServerAliveInterval=30"]` | Extra `ssh -o` options |

### Settings

| Setting | Default | Meaning |
|---|---|---|
| `default_user` | `""` | User for servers without one |
| `default_key` | `""` | Key for servers without one (empty = ssh's own defaults) |
| `terminal` | `"auto"` | Terminal to open sessions in (see [Terminal](#terminal)) |
| `theme` | `"system"` | `system`, `light` or `dark` |
| `font_size` | `11` | UI font size in points |
| `close_to_background` | `true` | Closing the window keeps the app running |

### Use the servers outside the app

Every save also writes `~/.config/ssh-manager/ssh_config`. To use the same servers from any terminal
(`ssh vpc-app-01`, `scp`, VS Code Remote-SSH...), add this line at the **top** of `~/.ssh/config`:

```
Include ~/.config/ssh-manager/ssh_config
```

## Terminal

In Settings, `auto` uses Windows Terminal on WSL, Terminal.app on macOS, Windows Terminal or cmd on Windows,
and otherwise the first Linux terminal it finds (gnome-terminal, konsole, xfce4-terminal, kitty, xterm...).
You can also set a custom template, such as `gnome-terminal -- {args}` or `xterm -T {title} -e {args}`.

## CLI

```bash
ssh-manager show | quit           # show / stop the background instance
ssh-manager connect NAME          # ssh in the current terminal
ssh-manager list
ssh-manager command NAME          # print the full ssh command
ssh-manager fetch-hostnames [NAME...]   # log in and record hostnames (skips ones already known)
ssh-manager import FILE.json
ssh-manager import-ssh-config [~/.ssh/config]
```

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python -m sshmgr --foreground
```

macOS / Windows: run `packaging/build.sh` on that OS (on Windows use Git Bash, or run the
`pyinstaller` line by hand with `--add-data "sshmgr/assets;sshmgr/assets"`).
