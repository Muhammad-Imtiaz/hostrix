# Contributing to SSH Manager

Thanks for helping make SSH Manager better. Bug reports, ideas, docs fixes and code are all welcome.

## Reporting bugs and asking for features

- **Bugs:** open a [bug report](https://github.com/imtiaz9832/ssh-manager/issues/new?template=bug_report.yml).
  Include your OS and version, the SSH Manager version (**About** in the sidebar), and the steps to reproduce.
  Remove real IP addresses, hostnames and usernames from anything you paste.
- **Ideas:** open a [feature request](https://github.com/imtiaz9832/ssh-manager/issues/new?template=feature_request.yml)
  and describe the problem you're trying to solve.
- **Security issues:** please don't open a public issue. See [SECURITY.md](SECURITY.md).

## Setting up for development

You need Python 3.10 or newer and an OpenSSH client.

```bash
git clone https://github.com/imtiaz9832/ssh-manager.git
cd ssh-manager
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m sshmgr --foreground
```

To work with a throwaway inventory instead of your real one, point the app at another folder:

```bash
SSH_MANAGER_HOME=/tmp/ssh-manager-dev .venv/bin/python -m sshmgr --foreground
```

`ssh-manager selftest` builds the main window off-screen and exits, a quick check that the app still starts.

## Code layout

| File | What it does |
|---|---|
| `sshmgr/inventory.py` | Server and settings model, JSON load/save, `ssh_config` export and import |
| `sshmgr/connect.py` | Builds ssh commands, reachability checks, opening terminals on each OS |
| `sshmgr/gui.py` | The Qt user interface |
| `sshmgr/theme.py` | Colours, stylesheet and icons |
| `sshmgr/background.py` | Background mode, single instance, autostart |
| `packaging/` | Release builds (`build.py`), the Windows installer script, icons |

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Keep each pull request to one change, and match the style of the surrounding code.
3. Check that the app starts and that what you changed works, in both light and dark theme if it's visual.
4. Describe what changed and why. Screenshots help for anything visual; use sample data, not real servers.

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
