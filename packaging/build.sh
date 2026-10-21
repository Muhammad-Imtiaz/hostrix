#!/usr/bin/env bash
# Build a self-contained binary (PyInstaller) and, on Linux, a .deb package.
#   packaging/build.sh   -> dist/ssh-manager/ (app folder) and, on Linux, dist/ssh-manager_<ver>_<arch>.deb
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(python3 -c 'import re;print(re.search(r"__version__ = \"(.+)\"", open("sshmgr/__init__.py").read())[1])')"

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e . pyinstaller

rm -rf build dist
# --onedir starts much faster than --onefile (nothing to unpack on every launch / Connect)
.venv/bin/pyinstaller --noconfirm --clean --onedir --windowed --name ssh-manager \
    --add-data "sshmgr/assets:sshmgr/assets" \
    --exclude-module tkinter \
    --paths "$ROOT" --hidden-import sshmgr.gui \
    packaging/launcher.py

[[ "$(uname -s)" == "Linux" ]] || { echo "Built dist/ssh-manager/"; exit 0; }

# ---- .deb ---------------------------------------------------------------
ARCH="$(dpkg --print-architecture)"
PKG="build/deb/ssh-manager_${VERSION}_${ARCH}"
mkdir -p "$PKG/DEBIAN" "$PKG/opt" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" "$PKG/usr/share/doc/ssh-manager"
cp -a dist/ssh-manager "$PKG/opt/ssh-manager"
ln -s /opt/ssh-manager/ssh-manager "$PKG/usr/bin/ssh-manager"
install -m 644 packaging/ssh-manager.desktop "$PKG/usr/share/applications/"
install -m 644 sshmgr/assets/ssh-manager.svg "$PKG/usr/share/icons/hicolor/scalable/apps/"
install -m 644 README.md "$PKG/usr/share/doc/ssh-manager/"
cat > "$PKG/DEBIAN/control" <<EOF
Package: ssh-manager
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Depends: openssh-client, libegl1, libxkbcommon0, libfontconfig1, libdbus-1-3
Recommends: libxcb-cursor0, libxkbcommon-x11-0
Maintainer: Muhammad Imtiaz <imtiaz9832@gmail.com>
Description: GUI inventory and launcher for SSH servers
 Keep a list of servers (IP, hostname, user, key, jump host, VPN flag,
 description) and open an SSH session in a new terminal with one click.
EOF
dpkg-deb --build --root-owner-group "$PKG" "dist/ssh-manager_${VERSION}_${ARCH}.deb"
echo "Built dist/ssh-manager/ and dist/ssh-manager_${VERSION}_${ARCH}.deb"
