# Third-party software

Hostrix's own code is licensed under the [Apache License 2.0](LICENSE). The ready-to-run packages on the
releases page also bundle the following open-source components, each under its own license.

| Component | Used for | License | Source |
|---|---|---|---|
| [Qt 6](https://www.qt.io/) | User interface toolkit | GNU LGPL v3 | https://code.qt.io |
| [PySide6 / Shiboken6](https://wiki.qt.io/Qt_for_Python) | Python bindings for Qt | GNU LGPL v3 | https://code.qt.io/cgit/pyside/pyside-setup.git |
| [Python](https://www.python.org/) | Runtime | PSF License | https://github.com/python/cpython |
| [PyInstaller](https://pyinstaller.org/) bootloader | Starts the bundled app | GPL v2 with a bootloader exception that allows distributing it with any program | https://github.com/pyinstaller/pyinstaller |
| [Lucide](https://lucide.dev/) icons (adapted) | Icons in the app | ISC License | https://github.com/lucide-icons/lucide |

## Qt and PySide6 (LGPL v3)

The packages use Qt and PySide6 as separate shared libraries, unmodified. You may replace them with your own
compatible builds: they are the `PySide6` and `shiboken6` folders and the Qt libraries inside the app folder
(`_internal` on Linux and Windows, `Hostrix.app/Contents/Frameworks` on macOS). The LGPL v3 text is at
https://www.gnu.org/licenses/lgpl-3.0.html, and the complete source code of Qt and PySide6 is available from
the links above. Hostrix's own source code is in this repository.

The packages are built from this repository by
[`.github/workflows/release.yml`](.github/workflows/release.yml), so you can rebuild any release yourself.
