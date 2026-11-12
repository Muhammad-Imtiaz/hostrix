# Changelog

All notable changes to Hostrix (called SSH Manager before the rename). Each version has full release
notes on the [releases page](https://github.com/Muhammad-Imtiaz/hostrix/releases).

## 0.5.2

- Packages include THIRD-PARTY-NOTICES for the bundled Qt, PySide6, Python and PyInstaller
- First start: the empty list suggests importing ~/.ssh/config, and no warning when the settings folder is new
- CI on every push and pull request, and Dependabot for dependency updates
- README: tarball path, log location on each OS, the `hostrix` command on macOS

## 0.5.1

- Fix the macOS build (the app bundle was removed while being renamed to Hostrix.app)

## 0.5.0

- **Renamed to Hostrix:** the app, the `hostrix` command, the packages and the repository
  (github.com/Muhammad-Imtiaz/hostrix)
- On first start, your servers and settings are copied from the old `ssh-manager` folder into the new
  `hostrix` folder; the old folder is left as it was
- Start-on-login moves over to Hostrix automatically; `SSH_MANAGER_HOME` still works as an alias for
  the new `HOSTRIX_HOME`
- The Ubuntu/Debian package replaces an installed `ssh-manager` package
- Open source under the Apache License 2.0, with a NOTICE file crediting the author
- **About** in the sidebar: version, author, license, and links to star the repo or report an issue
- Releases include version-free file names, so the README's download buttons always fetch the latest build
- Installers carry the author and license: the Windows installer shows the license, the macOS app and the
  Linux package include the copyright
- Contributing guide, security policy, code of conduct, issue templates and citation file

## 0.4.1

- Public IP column next to IP / Host, included in search, the details panel and Add / Edit server
- Columns size to their content until you resize one

## 0.4.0

- Downloadable packages for Ubuntu (`.deb`, `.tar.gz`), macOS (`.dmg`) and Windows (installer and portable `.zip`),
  built automatically for every release
- Windows support: sessions use the built-in OpenSSH in Windows Terminal or a console window
- App icons

## 0.3.x

- Clear "Terminal didn't open" error with a "Use auto and retry" button (0.3.2)
- Dialogs scroll at large font sizes (0.3.1)
- Layout scales with the font size, resizable panels, close button quits, Check all shows its results (0.3.0)

## 0.2.0

- Dashboard-style interface with light and dark themes and adjustable font size
- Background mode: run in the background, single instance, `ssh-manager show` and `quit`

## 0.1.0

- First version: server inventory, one-click connect, jump hosts, reachability checks, hostname fetching,
  `ssh_config` export and import, CLI
