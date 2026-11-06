"""Build the release packages for the OS this runs on.

    python packaging/build.py

Output goes to dist/release/:
    Linux    ssh-manager_<ver>_<arch>.deb  and  ssh-manager-<ver>-linux-<arch>.tar.gz
    macOS    ssh-manager-<ver>-macos-<arch>.dmg  (contains "SSH Manager.app")
    Windows  ssh-manager-<ver>-windows-x64-setup.exe  (needs Inno Setup)  and  ...-portable.zip

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
VERSION = re.search(r'__version__ = "(.+)"', (ROOT / "sshmgr" / "__init__.py").read_text())[1]
APP_NAME = "SSH Manager"
BUNDLE_ID = "io.github.imtiaz9832.ssh-manager"


def run(cmd: list[str], **kwargs):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, **kwargs)


def pyinstaller():
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
            "--name", "ssh-manager",
            "--add-data", f"{ROOT / 'sshmgr' / 'assets'}{os.pathsep}sshmgr/assets",
            "--add-data", f"{ROOT / 'LICENSE'}{os.pathsep}.",
            "--add-data", f"{ROOT / 'NOTICE'}{os.pathsep}.",
            "--paths", str(ROOT), "--hidden-import", "sshmgr.gui",
            "--exclude-module", "tkinter",
            "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "pyinstaller"),
            "--specpath", str(ROOT / "build")]
    if sys.platform == "win32":
        args += ["--icon", str(ICONS / "ssh-manager.ico")]
    elif sys.platform == "darwin":
        args += ["--icon", str(ICONS / "ssh-manager.icns"), "--osx-bundle-identifier", BUNDLE_ID]
    run(args + [str(ROOT / "packaging" / "launcher.py")])


# ---- Linux -----------------------------------------------------------
def linux():
    arch = subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True).stdout.strip() \
        if shutil.which("dpkg") else platform.machine()
    app = DIST / "ssh-manager"

    # portable tarball: ssh-manager-<ver>/ with the app, desktop file and icon
    tar_name = f"ssh-manager-{VERSION}-linux-{platform.machine()}.tar.gz"
    with tarfile.open(RELEASE / tar_name, "w:gz") as tar:
        top = f"ssh-manager-{VERSION}"
        tar.add(app, arcname=f"{top}/ssh-manager")
        tar.add(ROOT / "packaging" / "ssh-manager.desktop", arcname=f"{top}/ssh-manager.desktop")
        tar.add(ROOT / "sshmgr" / "assets" / "ssh-manager.svg", arcname=f"{top}/ssh-manager.svg")
        for doc in ("README.md", "LICENSE", "NOTICE"):
            tar.add(ROOT / doc, arcname=f"{top}/{doc}")

    if not shutil.which("dpkg-deb"):
        print("dpkg-deb not found: skipping .deb")
        return
    pkg = ROOT / "build" / "deb" / f"ssh-manager_{VERSION}_{arch}"
    shutil.rmtree(pkg, ignore_errors=True)
    for d in ("DEBIAN", "opt", "usr/bin", "usr/share/applications", "usr/share/icons/hicolor/scalable/apps",
              "usr/share/icons/hicolor/256x256/apps", "usr/share/doc/ssh-manager"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
    shutil.copytree(app, pkg / "opt" / "ssh-manager", symlinks=True)
    (pkg / "usr/bin/ssh-manager").symlink_to("/opt/ssh-manager/ssh-manager")
    shutil.copy(ROOT / "packaging" / "ssh-manager.desktop", pkg / "usr/share/applications/")
    shutil.copy(ROOT / "sshmgr" / "assets" / "ssh-manager.svg", pkg / "usr/share/icons/hicolor/scalable/apps/")
    from_png = ICONS / "ssh-manager.png"
    if from_png.exists():
        shutil.copy(from_png, pkg / "usr/share/icons/hicolor/256x256/apps/ssh-manager.png")
    shutil.copy(ROOT / "README.md", pkg / "usr/share/doc/ssh-manager/")
    shutil.copy(ROOT / "NOTICE", pkg / "usr/share/doc/ssh-manager/")
    (pkg / "usr/share/doc/ssh-manager/copyright").write_text(
        "SSH Manager\nCopyright 2026 Muhammad Imtiaz <https://github.com/imtiaz9832>\n"
        "License: Apache-2.0\n\n" + (ROOT / "LICENSE").read_text())
    (pkg / "DEBIAN" / "control").write_text(f"""Package: ssh-manager
Version: {VERSION}
Section: net
Priority: optional
Architecture: {arch}
Depends: openssh-client, libegl1, libxkbcommon0, libfontconfig1, libdbus-1-3
Recommends: libxcb-cursor0, libxkbcommon-x11-0
Maintainer: Muhammad Imtiaz <imtiaz9832@gmail.com>
Homepage: https://github.com/imtiaz9832/ssh-manager
Description: GUI inventory and launcher for SSH servers
 Keep a list of servers (IP, hostname, user, key, jump host, VPN flag,
 description) and open an SSH session in a new terminal with one click.
""")
    run(["dpkg-deb", "--build", "--root-owner-group", str(pkg), str(RELEASE / f"ssh-manager_{VERSION}_{arch}.deb")])


# ---- macOS -----------------------------------------------------------
def macos():
    built = DIST / "ssh-manager.app"
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
    dmg = RELEASE / f"ssh-manager-{VERSION}-macos-{platform.machine()}.dmg"
    run(["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(staging), "-ov", "-format", "UDZO", str(dmg)])


# ---- Windows ---------------------------------------------------------
def windows():
    app = DIST / "ssh-manager"
    base = f"ssh-manager-{VERSION}-windows-x64"
    for doc in ("LICENSE", "NOTICE"):
        shutil.copy(ROOT / doc, app / f"{doc}.txt")
    shutil.make_archive(str(RELEASE / f"{base}-portable"), "zip", root_dir=DIST, base_dir="ssh-manager")

    iscc = shutil.which("iscc") or next(
        (p for p in (Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
                     Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe") if p.exists()), None)
    if not iscc:
        print("Inno Setup (iscc) not found: skipping the installer, portable .zip only")
        return
    run([str(iscc), f"/DAppVersion={VERSION}", f"/DSourceDir={app}", f"/DOutputDir={RELEASE}",
         f"/DIconFile={ICONS / 'ssh-manager.ico'}", f"/DOutputBase={base}-setup",
         f"/DLicenseFile={ROOT / 'LICENSE'}",
         str(ROOT / "packaging" / "windows" / "ssh-manager.iss")])


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
