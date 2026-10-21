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

Stored as JSON at `~/.config/ssh-manager/inventory.json` (macOS: `~/Library/Application Support/ssh-manager`,
Windows: `%APPDATA%\ssh-manager`). Set `SSH_MANAGER_HOME` to use a different folder.

Every save also writes `~/.config/ssh-manager/ssh_config`. To use the same servers from any terminal
(`ssh my-server`, `scp`, VS Code Remote-SSH...), add this line at the **top** of `~/.ssh/config`:

```
Include ~/.config/ssh-manager/ssh_config
```

Each server has: `name` (unique alias), `host` (IP/DNS), `hostname`, `user`, `port`, `key_path`, `jump`
(name of another server used as the jump host, one hop), `requires_vpn`, `group`, `description`,
`extra_options` (`ssh -o` values). Empty `user` and `key_path` fall back to the defaults in **Settings**.

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
