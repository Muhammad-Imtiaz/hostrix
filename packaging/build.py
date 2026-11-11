"""Build the release packages for the OS this runs on.

    python packaging/build.py

Output goes to dist/release/:
    Linux    hostrix_<ver>_<arch>.deb  and  hostrix-<ver>-linux-<arch>.tar.gz
    macOS    hostrix-<ver>-macos-<arch>.dmg  (contains "Hostrix.app")
    Windows  hostrix-<ver>-windows-x64-setup.exe  (needs Inno Setup)  and  ...-portable.zip

Needs PyInstaller and the app's dependencies in the running Python (pip install -e . pyinstaller).
"""

from __future__ import annotations

import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
RELEASE = DIST / "release"
ICONS = ROOT / "packaging" / "icons"
VERSION = re.search(r'__version__ = "(.+)"', (ROOT / "hostrix" / "__init__.py").read_text())[1]
APP_NAME = "Hostrix"
BUNDLE_ID = "io.github.muhammad-imtiaz.hostrix"


def run(cmd: list[str], **kwargs):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, **kwargs)


def pyinstaller():
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
            "--name", "hostrix",
            "--add-data", f"{ROOT / 'hostrix' / 'assets'}{os.pathsep}hostrix/assets",
            "--add-data", f"{ROOT / 'LICENSE'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'NOTICE'}{os.pathsep}.",
            "--paths", str(ROOT), "--hidden-import", "hostrix.gui",
            "--exclude-module", "tkinter",
            "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "pyinstaller"),
            "--specpath", str(ROOT / "build")]
    if sys.platform == "win32":
        args += ["--icon", str(ICONS / "hostrix.ico")]
    elif sys.platform == "darwin":
        args += ["--icon", str(ICONS / "hostrix.icns"), "--osx-bundle-identifier", BUNDLE_ID]
    run(args + [str(ROOT / "packaging" / "launcher.py")])


# ---- Linux -----------------------------------------------------------
def linux():
    arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True).stdout.strip() \
        if shutil.which("dpkg") else platform.machine()
    app = DIST / "hostrix"

    # portable tarball: hostrix-<ver>/ with the app, desktop file and icon
    tar_name = f"hostrix-{VERSION}-linux-{platform.machine()}.tar.gz"
    with tarfile.open(RELEASE / tar_name, "w:gz") as tar:
        top = f"hostrix-{VERSION}"
        tar.add(app, arcname=f"{top}/hostrix")
        tar.add(ROOT / "packaging" / "hostrix.desktop", arcname=f"{top}/hostrix.desktop")
        tar.add(ROOT / "hostrix" / "assets" / "hostrix.svg", arcname=f"{top}/hostrix.svg")
        for doc in ("README.md", "LICENSE", "NOTICE"):
            tar.add(ROOT / doc, arcname=f"{top}/{doc}")

    if not shutil.which("dpkg-deb"):
        print("dpkg-deb not found: skipping .deb")
        return
    pkg = ROOT / "build" / "deb" / f"hostrix_{VERSION}_{arch}"
    shutil.rmtree(pkg, ignore_errors=True)
    for d in ("DEBIAN", "opt", "usr/bin", "usr/share/applications", "usr/share/icons/hicolor/scalable/apps",
              "usr/share/icons/hicolor/256x256/apps", "usr/share/doc/hostrix"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
    shutil.copytree(app, pkg / "opt" / "hostrix", symlinks=True)
    (pkg / "usr/bin/hostrix").symlink_to("/opt/hostrix/hostrix")
    shutil.copy(ROOT / "packaging" / "hostrix.desktop", pkg / "usr/share/applications/")
    shutil.copy(ROOT / "hostrix" / "assets" / "hostrix.svg", pkg / "usr/share/icons/hicolor/scalable/apps/")
    from_png = ICONS / "hostrix.png"
    if from_png.exists():
        shutil.copy(from_png, pkg / "usr/share/icons/hicolor/256x256/apps/hostrix.png")
    shutil.copy(ROOT / "README.md", pkg / "usr/share/doc/hostrix/")
    shutil.copy(ROOT / "NOTICE", pkg / "usr/share/doc/hostrix/")
    (pkg / "usr/share/doc/hostrix/copyright").write_text(
        "Hostrix\nCopyright 2026 Muhammad Imtiaz <https://github.com/Muhammad-Imtiaz>\n"
        "License: Apache-2.0\n\n" + (ROOT / "LICENSE").read_text())
    (pkg / "DEBIAN" / "control").write_text(f"""Package: hostrix
Version: {VERSION}
Section: net
Priority: optional
Architecture: {arch}
Depends: openssh-client, libegl1, libxkbcommon0, libfontconfig1, libdbus-1-3
Recommends: libxcb-cursor0, libxkbcommon-x11-0
Conflicts: ssh-manager
Replaces: ssh-manager
Maintainer: Muhammad Imtiaz <imtiaz9832@gmail.com>
Homepage: https://github.com/Muhammad-Imtiaz/hostrix
Description: GUI inventory and launcher for SSH servers
 Keep a list of servers (IP, hostname, user, key, jump host, VPN flag,
 description) and open an SSH session in a new terminal with one click.
""")
    run(["dpkg-deb", "--build", "--root-owner-group", str(pkg), str(RELEASE / f"hostrix_{VERSION}_{arch}.deb")])


# ---- macOS -----------------------------------------------------------
def macos():
    built = DIST / "hostrix.app"
    app = DIST / f"{APP_NAME}.app"
    shutil.rmtree(app, ignore_errors=True)
    built.rename(app)
    plist_path = app / "Contents" / "Info.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    plist.update({
        "CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
        "NSHighResolutionCapable": True, "LSApplicationCategoryType": "public.app-category.developer-tools",
        "NSHumanReadableCopyright": "Copyright 2026 Muhammad Imtiaz. Apache License 2.0.",
    })
    plist_path.write_bytes(plistlib.dumps(plist))
    # Info.plist changed after PyInstaller signed it: re-sign ad hoc, or Apple Silicon refuses to start it
    run(["codesign", "--force", "--deep", "--sign", "-", str(app)])

    staging = ROOT / "build" / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    shutil.copytree(app, staging / app.name, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")
    dmg = RELEASE / f"hostrix-{VERSION}-macos-{platform.machine()}.dmg"
    run(["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg)])


# ---- Windows ---------------------------------------------------------
def windows():
    app = DIST / "hostrix"
    base = f"hostrix-{VERSION}-windows-x64"
    for doc in ("LICENSE", "NOTICE"):
        shutil.copy(ROOT / doc, app / f"{doc}.txt")
    shutil.make_archive(str(RELEASE / f"{base}-portable"), "zip", root_dir=DIST, base_dir="hostrix")

    iscc = shutil.which("iscc") or next(
        (p for p in (Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
                     Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe") if p.exists()), None)
    if not iscc:
        print("Inno Setup (iscc) not found: skipping the installer, portable .zip only")
        return
    run([str(iscc), f"/DAppVersion={VERSION}", f"/DSourceDir={app}", f"/DOutputDir={RELEASE}",
         f"/DIconFile={ICONS / 'hostrix.ico'}", f"/DOutputBase={base}-setup",
         f"/DLicenseFile={ROOT / 'LICENSE'}",
         str(ROOT / "packaging" / "windows" / "hostrix.iss")])


def main():
    shutil.rmtree(DIST, ignore_errors=True)
    RELEASE.mkdir(parents=True)
    pyinstaller()
    {"linux": linux, "darwin": macos, "win32": windows}.get(sys.platform, linux)()
    print("\nRelease files:")
    for f in sorted(RELEASE.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
