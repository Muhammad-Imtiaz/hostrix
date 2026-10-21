"""Qt (PySide6) user interface with a web-dashboard look."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QFileSystemWatcher, QModelIndex, QObject, QRect, QRunnable, QSize,
                            QSortFilterProxyModel, Qt, QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import QColor, QIntValidator, QDesktopServices, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QShortcut
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QSystemTrayIcon, QTableView, QVBoxLayout, QWidget)

from . import APP_NAME, __version__, background, theme
from .connect import display_command, fetch_hostname, key_exists, open_in_terminal, tcp_reachable
from .inventory import Inventory, InventoryError, Server, parse_ssh_config

ICON_PATH = Path(__file__).with_name("assets") / "ssh-manager.svg"
ALL_GROUPS = "All servers"
SEARCH_ROLE = Qt.UserRole
SERVER_ROLE = Qt.UserRole + 1


def access_badges(s: Server) -> list[tuple[str, str]]:
    """(text, colour key) pills describing how the server is reached."""
    badges = []
    if s.requires_vpn:
        badges.append(("VPN", "pill_vpn"))
    if s.jump:
        badges.append((f"via {s.jump}", "pill_jump"))
    return badges or [("Direct", "pill_direct")]


def button(text: str, variant: str = "", icon_name: str | None = None, colors: dict | None = None) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if variant:
        b.setProperty("variant", variant)
    if icon_name and colors:
        tint = {"primary": "#ffffff", "success": "#ffffff", "danger": colors["danger"]}.get(variant, colors["muted"])
        b.setIcon(theme.icon(icon_name, tint))
        b.setIconSize(QSize(17, 17))
    return b


def label(text="", name="", muted=False, wrap=False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    if muted:
        lbl.setProperty("muted", True)
    lbl.setWordWrap(wrap)
    return lbl


def derived_font(size_delta: int = 0, weight: QFont.Weight | None = None) -> QFont:
    f = QFont(QApplication.font())
    f.setPointSize(max(f.pointSize() + size_delta, 8))
    if weight is not None:
        f.setWeight(weight)
    return f


# ---- background jobs -------------------------------------------------
class _JobSignals(QObject):
    done = Signal(str, str, bool, str)  # kind, server name, ok, message


class Job(QRunnable):
    def __init__(self, kind: str, inv: Inventory, server: Server, signals: _JobSignals):
        super().__init__()
        self.kind, self.inv, self.server, self.signals = kind, inv, server, signals

    def run(self):
        try:
            fn = tcp_reachable if self.kind == "check" else fetch_hostname
            ok, msg = fn(self.inv, self.server)
        except Exception as e:  # never let a worker crash the app
            ok, msg = False, str(e)
        self.signals.done.emit(self.kind, self.server.name, ok, msg)


# ---- table model ------------------------------------------------------
class ServerModel(QAbstractTableModel):
    COLUMNS = ["", "SERVER", "IP / HOST", "USER", "GROUP", "ACCESS", "DESCRIPTION"]

    def __init__(self, inv: Inventory):
        super().__init__()
        self.inv = inv
        self.status: dict[str, tuple[bool | None, str]] = {}

    def reload(self):
        self.beginResetModel()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.inv.servers)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def server(self, row: int) -> Server:
        return self.inv.servers[row]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section]
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def data(self, index, role=Qt.DisplayRole):
        s = self.inv.servers[index.row()]
        col = index.column()
        if role == SERVER_ROLE:
            return s
        if role == Qt.DisplayRole:
            if col == 0:  # sort order: reachable, unknown, unreachable
                return {True: 0, None: 1, False: 2}[self.status.get(s.name, (None, ""))[0]]
            return [None, s.name, s.host, self.inv.effective_user(s), s.group,
                    " ".join(t for t, _ in access_badges(s)), s.description][col]
        if role == Qt.ToolTipRole:
            if col == 0:
                return self.status.get(s.name, (None, "Not checked yet"))[1]
            if col == 6:
                return s.description
        if role == SEARCH_ROLE:
            return " ".join([s.name, s.hostname, s.host, self.inv.effective_user(s), s.group,
                             s.description, s.jump, "vpn" if s.requires_vpn else ""]).lower()
        return None

    def set_status(self, name: str, ok: bool | None, msg: str):
        self.status[name] = (ok, msg)
        for row, s in enumerate(self.inv.servers):
            if s.name == name:
                self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))


class FilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.group = ALL_GROUPS
        self.text = ""
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def set_filter(self, group: str | None = None, text: str | None = None):
        if group is not None:
            self.group = group
        if text is not None:
            self.text = text.lower().strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        model: ServerModel = self.sourceModel()
        s = model.server(row)
        if self.group != ALL_GROUPS and (s.group or "Ungrouped") != self.group:
            return False
        if self.text:
            hay = model.data(model.index(row, 0), SEARCH_ROLE)
            return all(word in hay for word in self.text.split())
        return True


class CellDelegate(QStyledItemDelegate):
    """Paints status dots, two-line server names, monospace IPs and coloured pills."""

    CUSTOM = (0, 1, 2, 4, 5)

    def __init__(self, parent, colors: dict, status: dict):
        super().__init__(parent)
        self.c = colors
        self.status = status

    def _pill(self, p: QPainter, x: int, cy: int, text: str, kind: str, font: QFont) -> int:
        bg, fg = self.c[kind]
        fm = QFontMetrics(font)
        w, h = fm.horizontalAdvance(text) + 18, fm.height() + 6
        rect = QRect(x, cy - h // 2, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(rect, h / 2, h / 2)
        p.setPen(QColor(fg))
        p.setFont(font)
        p.drawText(rect, Qt.AlignCenter, text)
        return w + 6

    def paint(self, p: QPainter, option, index):
        col = index.column()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if col in self.CUSTOM:
            opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, p, opt.widget)
        if col not in self.CUSTOM:
            return

        s: Server = index.data(SERVER_ROLE)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setClipRect(option.rect)
        r = option.rect.adjusted(12, 0, -8, 0)
        cy = r.center().y()
        if col == 0:
            ok = self.status.get(s.name, (None, ""))[0]
            color = QColor(self.c["success"] if ok else self.c["danger"] if ok is False else self.c["border_strong"])
            p.setPen(Qt.NoPen)
            if ok is not None:
                halo = QColor(color)
                halo.setAlpha(55)
                p.setBrush(halo)
                p.drawEllipse(r.left(), cy - 8, 16, 16)
            p.setBrush(color)
            p.drawEllipse(r.left() + 4, cy - 4, 8, 8)
        elif col == 1:
            bold, small = derived_font(0, QFont.DemiBold), derived_font(-1)
            fm, fms = QFontMetrics(bold), QFontMetrics(small)
            top = cy - (fm.height() + fms.height()) // 2
            p.setFont(bold)
            p.setPen(QColor(self.c["text"]))
            p.drawText(QRect(r.left(), top, r.width(), fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(s.name, Qt.ElideRight, r.width()))
            p.setFont(small)
            p.setPen(QColor(self.c["muted"] if s.hostname else self.c["faint"]))
            p.drawText(QRect(r.left(), top + fm.height(), r.width(), fms.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fms.elidedText(s.hostname or "hostname unknown", Qt.ElideRight, r.width()))
        elif col == 2:
            p.setFont(theme.mono_font(derived_font(-1).pointSize()))
            p.setPen(QColor(self.c["text"]))
            p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, s.host)
        else:
            small = derived_font(-2, QFont.DemiBold)
            pills = ([(s.group, "pill_group")] if s.group else []) if col == 4 else access_badges(s)
            x = r.left()
            for text, kind in pills:
                x += self._pill(p, x, cy, text, kind, small)
        p.restore()


# ---- small widgets ---------------------------------------------------
class Card(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Card")


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.hide()
        self.timer = QTimer(self, singleShot=True, timeout=self.hide)

    def show_message(self, text: str, ms: int = 2600):
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, par.height() - self.height() - 28)
        self.raise_()
        self.show()
        self.timer.start(ms)


def form_section(title: str, rows: list, note: str | None = None) -> Card:
    card = Card()
    lay = QVBoxLayout(card)
    lay.setContentsMargins(20, 16, 20, 18)
    lay.setSpacing(10)
    lay.addWidget(label(title, "SectionTitle"))
    form = QFormLayout()
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(10)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for row in rows:
        form.addRow(*row)
    lay.addLayout(form)
    if note:
        lay.addWidget(label(note, muted=True, wrap=True))
    return card


def dialog_buttons(dialog: QDialog, save_text: str, on_save) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addStretch()
    cancel = button("Cancel")
    cancel.clicked.connect(dialog.reject)
    save = button(save_text, "primary")
    save.setDefault(True)
    save.clicked.connect(on_save)
    row.addWidget(cancel)
    row.addWidget(save)
    return row


# ---- dialogs ---------------------------------------------------------
class ServerDialog(QDialog):
    def __init__(self, parent, inv: Inventory, server: Server | None = None, title="Add server"):
        super().__init__(parent)
        self.inv = inv
        self.original = server
        self.setWindowTitle(title)
        self.setMinimumWidth(640)
        s = server or Server(name="", host="")

        self.name = QLineEdit(s.name)
        self.name.setPlaceholderText("unique alias, e.g. bd-prod-db-01")
        self.host = QLineEdit(s.host)
        self.host.setPlaceholderText("IP address or DNS name")
        self.hostname = QLineEdit(s.hostname)
        self.hostname.setPlaceholderText("machine hostname (optional, can be fetched)")
        self.user = QLineEdit(s.user)
        self.user.setPlaceholderText(f"default: {inv.settings.default_user or '(local user)'}")
        self.port = QLineEdit(str(s.port))
        self.port.setValidator(QIntValidator(1, 65535, self.port))
        self.port.setMaximumWidth(120)

        self.key = QLineEdit(s.key_path)
        self.key.setPlaceholderText(f"default: {inv.settings.default_key or '(ssh default)'}")
        browse = button("Browse…")
        browse.clicked.connect(self._browse_key)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        key_row.addWidget(browse)

        self.jump = QComboBox()
        self.jump.addItem("No jump host", "")
        for other in sorted(inv.servers, key=lambda x: x.name.lower()):
            if server is None or other.name != server.name:
                self.jump.addItem(f"{other.name}  ({other.host})", other.name)
        self.jump.setCurrentIndex(max(self.jump.findData(s.jump), 0))
        self.vpn = QCheckBox("Requires VPN")
        self.vpn.setChecked(s.requires_vpn)
        self.extra = QLineEdit(", ".join(s.extra_options))
        self.extra.setPlaceholderText("ssh -o options, comma separated, e.g. ServerAliveInterval=30")

        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems([""] + inv.groups())
        self.group.setCurrentText(s.group)
        self.description = QPlainTextEdit(s.description)
        self.description.setFixedHeight(84)
        self.description.setPlaceholderText("What runs here, environment, owner…")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(label(title, "PageTitle"))
        layout.addWidget(form_section("Connection", [("Name *", self.name), ("Host / IP *", self.host),
                                                     ("User", self.user), ("Port", self.port),
                                                     ("Key path", key_row)]))
        layout.addWidget(form_section("Access", [("Jump host", self.jump), ("", self.vpn),
                                                 ("Extra options", self.extra)]))
        layout.addWidget(form_section("Details", [("Hostname", self.hostname), ("Group", self.group),
                                                  ("Description", self.description)]))
        layout.addLayout(dialog_buttons(self, "Save server", self._accept))
        self.result_server: Server | None = None

    def _browse_key(self):
        start = os.path.expanduser(self.key.text() or "~/.ssh")
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", start)
        if path:
            home = str(Path.home())
            self.key.setText("~" + path[len(home):] if path.startswith(home + os.sep) else path)

    def _accept(self):
        s = Server(
            name=self.name.text().strip(),
            host=self.host.text().strip(),
            hostname=self.hostname.text().strip(),
            user=self.user.text().strip(),
            port=int(self.port.text() or 22),
            key_path=self.key.text().strip(),
            jump=self.jump.currentData() or "",
            requires_vpn=self.vpn.isChecked(),
            group=self.group.currentText().strip(),
            description=self.description.toPlainText().strip(),
            extra_options=[o.strip() for o in self.extra.text().split(",") if o.strip()],
        )
        original = self.original.name if self.original else None
        try:
            self.inv.validate(s, original)
        except InventoryError as e:
            QMessageBox.warning(self, "Invalid server", str(e))
            return
        self.result_server = s
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, parent, inv: Inventory):
        super().__init__(parent)
        self.inv = inv
        self.setWindowTitle("Settings")
        self.setMinimumWidth(660)
        st = inv.settings

        self.theme = QComboBox()
        for text, value in (("Match system", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme.addItem(text, value)
        self.theme.setCurrentIndex(max(self.theme.findData(st.theme), 0))
        self.font_size = QComboBox()
        for pt in range(9, 19):
            self.font_size.addItem(f"{pt} pt" + ("  (default)" if pt == 11 else ""), pt)
        self.font_size.setCurrentIndex(max(self.font_size.findData(st.font_size), 0))

        self.user = QLineEdit(st.default_user)
        self.key = QLineEdit(st.default_key)
        self.terminal = QComboBox()
        self.terminal.setEditable(True)
        self.terminal.addItems(["auto", "gnome-terminal -- {args}", "konsole -e {args}",
                                "xfce4-terminal -x {args}", "xterm -T {title} -e {args}",
                                "x-terminal-emulator -e {args}"])
        self.terminal.setCurrentText(st.terminal or "auto")

        self.background = QCheckBox("Keep running in the background when the window is closed")
        self.background.setChecked(st.close_to_background)
        self.autostart = QCheckBox("Start in the background when I log in")
        self.autostart.setChecked(background.autostart_enabled())
        if not background.autostart_supported():
            self.autostart.setEnabled(False)
            self.autostart.setToolTip("Available on Linux desktops (not WSL)")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(label("Settings", "PageTitle"))
        layout.addWidget(form_section("Appearance", [("Theme", self.theme), ("Font size", self.font_size)]))
        layout.addWidget(form_section(
            "Defaults", [("Default user", self.user), ("Default key", self.key), ("Terminal", self.terminal)],
            "“auto” uses Windows Terminal on WSL, otherwise the first terminal found. Templates: {args} = "
            "command appended, {cmd} = one quoted string, {title} = server name."))
        layout.addWidget(form_section(
            "Background", [("", self.background), ("", self.autostart)],
            "While in the background, run ssh-manager again (or open it from the app menu) to bring the "
            "window back. “ssh-manager quit” stops it."))
        info = label(f"Inventory: {inv.path}\nFor ~/.ssh/config:  Include {inv.ssh_config_path}", muted=True, wrap=True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(info)
        layout.addLayout(dialog_buttons(self, "Save settings", self.accept))

    def apply(self):
        st = self.inv.settings
        st.theme = self.theme.currentData()
        st.font_size = self.font_size.currentData()
        st.default_user = self.user.text().strip()
        st.default_key = self.key.text().strip()
        st.terminal = self.terminal.currentText().strip() or "auto"
        st.close_to_background = self.background.isChecked()
        if background.autostart_supported() and self.autostart.isChecked() != background.autostart_enabled():
            background.set_autostart(self.autostart.isChecked())


# ---- details panel ---------------------------------------------------
class Details(Card):
    FIELDS = ["IP / Host", "Port", "User", "Jump host", "Key path", "Description"]

    def __init__(self, colors: dict):
        super().__init__()
        self.c = colors
        self.setFixedWidth(400)

        self.name = label("", "DetailName", wrap=True)
        self.host_line = label("", "DetailHost", wrap=True)
        self.badges = QHBoxLayout()
        self.badges.setSpacing(6)
        self.status = label("", wrap=True)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(14)
        self.values: dict[str, QLabel] = {}
        for i, key in enumerate(self.FIELDS):
            value = label("—", "FieldValue", wrap=True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.values[key] = value
            cell = QVBoxLayout()
            cell.setSpacing(3)
            cell.addWidget(label(key.upper(), "FieldLabel"))
            cell.addWidget(value)
            if i < 4:
                grid.addLayout(cell, i // 2, i % 2)
            else:  # full-width rows
                grid.addLayout(cell, i - 2, 0, 1, 2)

        self.command = QPlainTextEdit()
        self.command.setObjectName("Code")
        self.command.setReadOnly(True)
        self.command.setFont(theme.mono_font(derived_font(-1).pointSize()))
        self.command.setFixedHeight(136)
        self.copy_btn = button("Copy", "ghost", "copy", colors)

        self.connect_btn = button("Connect", "success", "terminal", colors)
        self.connect_btn.setToolTip("Open an SSH session in a new terminal (Enter / double-click)")
        self.test_btn = button("Test", "", "pulse", colors)
        self.fetch_btn = button("Fetch hostname", "", "tag", colors)
        self.edit_btn = button("Edit", "", "edit", colors)
        self.dup_btn = button("Duplicate", "", "duplicate", colors)
        self.delete_btn = button("Delete", "danger", "trash", colors)

        cmd_head = QHBoxLayout()
        cmd_head.addWidget(label("SSH COMMAND", "FieldLabel"))
        cmd_head.addStretch()
        cmd_head.addWidget(self.copy_btn)
        row1 = QHBoxLayout()
        row1.addWidget(self.test_btn)
        row1.addWidget(self.fetch_btn)
        row2 = QHBoxLayout()
        row2.addWidget(self.edit_btn)
        row2.addWidget(self.dup_btn)
        row2.addWidget(self.delete_btn)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {colors['border']};")

        self.body = QWidget()
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(12)
        for item in (self.name, self.host_line, self.badges, self.status, sep, grid, cmd_head, self.command,
                     self.connect_btn, row1, row2):
            if item is self.connect_btn:
                lay.addSpacing(4)
            lay.addWidget(item) if isinstance(item, QWidget) else lay.addLayout(item)
        lay.addStretch()

        self.empty = label("Select a server to see its details", "Empty", wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 18, 22)
        outer.addWidget(scroll)
        outer.addWidget(self.empty)
        self.show_server(None, None, None)

    def _set_badges(self, items: list[tuple[str, str]]):
        while self.badges.count():
            w = self.badges.takeAt(0).widget()
            if w:
                w.deleteLater()
        for text, kind in items:
            bg, fg = self.c[kind]
            pill = QLabel(text)
            pill.setStyleSheet(f"background:{bg}; color:{fg}; border-radius: 11px; padding: 3px 11px; "
                               "font-weight: 600;")
            self.badges.addWidget(pill)
        self.badges.addStretch()

    def show_server(self, inv: Inventory | None, s: Server | None, status):
        self.body.setVisible(s is not None)
        self.empty.setVisible(s is None)
        if s is None:
            return
        c = self.c
        self.name.setText(s.name)
        self.host_line.setText(s.hostname or "Hostname unknown — use Fetch hostname")
        self._set_badges(access_badges(s) + ([(s.group, "pill_group")] if s.group else []))

        ok, msg = status or (None, "Not checked yet")
        color = c["success"] if ok else c["danger"] if ok is False else c["faint"]
        self.status.setText(f"<span style='color:{color}'>●</span>&nbsp; <span style='color:{c['muted']}'>{msg}</span>")

        default = f" <span style='color:{c['faint']}'>(default)</span>"
        key = inv.effective_key(s)
        key_text = (key or "ssh default keys") + (default if key and not s.key_path else "")
        if key_exists(inv, s) is False:
            key_text += f"<br><span style='color:{c['danger']}'>file not found</span>"
        user = inv.effective_user(s)
        user_text = (user or "local user") + (default if user and not s.user else "")
        values = {"IP / Host": s.host, "Port": str(s.port), "User": user_text, "Jump host": s.jump or "—",
                  "Key path": key_text, "Description": s.description or "—"}
        for k, v in values.items():
            self.values[k].setText(v)
        try:
            self.command.setPlainText(display_command(inv, s))
        except ValueError as e:
            self.command.setPlainText(f"error: {e}")


# ---- main window -----------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, inv: Inventory, colors: dict):
        super().__init__()
        self.inv = inv
        self.c = colors
        self._quitting = False
        self.setWindowTitle(APP_NAME)
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1640, int(screen.width() * 0.92)), min(920, int(screen.height() * 0.9)))
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(16)
        self.job_signals = _JobSignals()
        self.job_signals.done.connect(self._job_done)

        self.model = ServerModel(inv)
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)

        root = QWidget()
        root.setObjectName("Main")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        h.addWidget(self._build_content(), 1)
        self.setCentralWidget(root)
        self.toast = Toast(root)

        self._build_shortcuts()
        self.tray = self._build_tray()
        self.reload()

        # pick up edits made outside the GUI (CLI, text editor, another window).
        # Watch the folder: saves replace the file, which drops a file watch.
        self._own_mtime = self._inventory_mtime()
        self.watcher = QFileSystemWatcher([str(inv.path.parent)] if inv.path.parent.exists() else [])
        self._reload_timer = QTimer(self, singleShot=True, interval=300, timeout=self._reload_from_disk)
        self.watcher.directoryChanged.connect(lambda _: self._reload_timer.start())

        # fill the status dots right away (a quick TCP check, no login)
        QTimer.singleShot(400, lambda: self.run_jobs("check", self.inv.servers, quiet=True))

    # ---- layout ------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(260)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 22, 16, 16)
        lay.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QIcon(str(ICON_PATH)).pixmap(38, 38))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label(APP_NAME, "Brand"))
        names.addWidget(label(f"Version {__version__}", "BrandSub"))
        brand.addLayout(names)
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(24)
        lay.addWidget(label("GROUPS", "SideHeading"))

        self.groups = QListWidget()
        self.groups.setObjectName("GroupList")
        self.groups.setCursor(Qt.PointingHandCursor)
        self.groups.setFocusPolicy(Qt.NoFocus)
        self.groups.currentItemChanged.connect(self._group_changed)
        lay.addWidget(self.groups, 1)

        def side_button(text, icon_name, slot=None):
            b = QPushButton(f"  {text}")
            b.setObjectName("SideButton")
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(theme.icon(icon_name, self.c["sidebar_text"]))
            if slot:
                b.clicked.connect(slot)
            return b

        more = side_button("Import / Export", "more")
        menu = QMenu(more)
        menu.addAction("Import ~/.ssh/config…", self.import_ssh_config)
        menu.addAction("Import JSON…", self.import_json)
        menu.addAction("Export JSON…", self.export_json)
        menu.addSeparator()
        menu.addAction("Open config folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.inv.path.parent))))
        more.setMenu(menu)
        lay.addWidget(more)
        lay.addWidget(side_button("Settings", "settings", self.open_settings))
        lay.addWidget(side_button("Quit", "power", self.quit_app))
        return side

    def _build_content(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = label(ALL_GROUPS, "PageTitle")
        self.subtitle = label("", "PageSub")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search servers…   (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(theme.icon("search", self.c["faint"]), QLineEdit.LeadingPosition)
        self.search.setMinimumWidth(380)
        self.search.textChanged.connect(self._search_changed)
        self.search.returnPressed.connect(self._search_enter)
        header.addWidget(self.search)
        check = button("Check all", "", "pulse", self.c)
        check.setToolTip("Check port 22 on every visible server (Ctrl+T)")
        check.clicked.connect(lambda: self.run_jobs("check", self.visible_servers()))
        add = button("Add server", "primary", "plus", self.c)
        add.setToolTip("Ctrl+N")
        add.clicked.connect(self.add_server)
        header.addWidget(check)
        header.addWidget(add)
        lay.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)
        table_card = Card()
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(4, 4, 4, 4)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setItemDelegate(CellDelegate(self.table, self.c, self.model.status))
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setMouseTracking(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(58)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        hh = self.table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        hh.setMinimumSectionSize(40)
        for col, width in enumerate([40, 220, 138, 88, 118, 170]):
            self.table.setColumnWidth(col, width)
        self.table.doubleClicked.connect(lambda _: self.connect_selected())
        self.table.selectionModel().currentRowChanged.connect(lambda *_: self._refresh_details())
        tl.addWidget(self.table)
        self.empty = label("", "Empty", wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        tl.addWidget(self.empty)
        body.addWidget(table_card, 1)

        self.details = d = Details(self.c)
        d.connect_btn.clicked.connect(self.connect_selected)
        d.copy_btn.clicked.connect(self.copy_command)
        d.test_btn.clicked.connect(lambda: self.run_jobs("check", self.selected_servers()))
        d.fetch_btn.clicked.connect(lambda: self.run_jobs("hostname", self.selected_servers()))
        d.edit_btn.clicked.connect(self.edit_server)
        d.dup_btn.clicked.connect(self.duplicate_server)
        d.delete_btn.clicked.connect(self.delete_servers)
        body.addWidget(d)
        lay.addLayout(body, 1)
        return content

    def _build_shortcuts(self):
        bindings = [
            ("Ctrl+N", self.add_server), ("F2", self.edit_server), ("Ctrl+E", self.edit_server),
            (QKeySequence.Delete, self.delete_servers), ("Ctrl+,", self.open_settings),
            ("Ctrl+T", lambda: self.run_jobs("check", self.visible_servers())),
            ("Ctrl+Q", self.quit_app), ("Ctrl+W", self.close),
            ("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll())),
        ]
        for keys, slot in bindings:
            QShortcut(QKeySequence(keys), self, activated=slot)
        QShortcut(QKeySequence(Qt.Key_Return), self.table, activated=self.connect_selected)
        QShortcut(QKeySequence(Qt.Key_Enter), self.table, activated=self.connect_selected)
        QShortcut(QKeySequence(Qt.Key_Escape), self.search, activated=self.search.clear)
        QShortcut(QKeySequence(Qt.Key_Down), self.search,
                  activated=lambda: (self.table.setFocus(), self.table.selectRow(0)))

    def _build_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(QIcon(str(ICON_PATH)), self)
        tray.setToolTip(APP_NAME)
        self.tray_menu = QMenu()
        tray.setContextMenu(self.tray_menu)
        tray.activated.connect(lambda reason: self.toggle_window() if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        return tray

    def _rebuild_tray_menu(self):
        """Tray menu doubles as a quick launcher: group -> server -> connect."""
        if not self.tray:
            return
        m = self.tray_menu
        m.clear()
        m.addAction(f"Open {APP_NAME}", self.bring_to_front)
        m.addSeparator()
        groups: dict[str, list[Server]] = {}
        for s in sorted(self.inv.servers, key=lambda x: x.name.lower()):
            groups.setdefault(s.group or "Ungrouped", []).append(s)
        for g in sorted(groups, key=str.lower):
            sub = m.addMenu(g)
            for s in groups[g]:
                sub.addAction(f"{s.name}   {s.hostname or s.host}", lambda s=s: self._open_terminal(s))
        m.addSeparator()
        m.addAction("Quit", self.quit_app)

    # ---- helpers -----------------------------------------------------
    def _group_changed(self, item, _prev=None):
        if item:
            group = item.data(Qt.UserRole)
            self.proxy.set_filter(group=group)
            self.title.setText(group)
            self._update_summary()
            if self.proxy.rowCount() and not self.table.currentIndex().isValid():
                self.table.selectRow(0)
            self._refresh_details()

    def _search_changed(self, text):
        self.proxy.set_filter(text=text)
        self._update_summary()
        if self.proxy.rowCount() and not self.table.currentIndex().isValid():
            self.table.selectRow(0)
        self._refresh_details()

    def _update_summary(self):
        visible = self.visible_servers()
        states = [self.model.status.get(s.name, (None,))[0] for s in visible]
        parts = [f"{len(visible)} server{'s' if len(visible) != 1 else ''}"]
        if any(st is not None for st in states):
            parts += [f"{states.count(True)} reachable", f"{states.count(False)} unreachable"]
        self.subtitle.setText("   ·   ".join(parts))
        empty = not visible
        self.table.setVisible(not empty)
        self.empty.setVisible(empty)
        if empty:
            self.empty.setText("No servers yet.\nClick “Add server” to create one." if not self.inv.servers
                               else "No servers match your search.")

    def reload(self, select: str | None = None):
        item = self.groups.currentItem()
        current_group = item.data(Qt.UserRole) if item else ALL_GROUPS
        self.model.reload()
        self.groups.blockSignals(True)
        self.groups.clear()
        names = [ALL_GROUPS] + self.inv.groups()
        if any(not s.group for s in self.inv.servers):
            names.append("Ungrouped")
        for g in names:
            count = len(self.inv.servers) if g == ALL_GROUPS else sum(
                1 for s in self.inv.servers if (s.group or "Ungrouped") == g)
            it = QListWidgetItem(f"{g}   ·   {count}")
            it.setData(Qt.UserRole, g)
            self.groups.addItem(it)
            if g == current_group:
                self.groups.setCurrentItem(it)
        if not self.groups.currentItem():
            self.groups.setCurrentRow(0)
        self.groups.blockSignals(False)
        self._group_changed(self.groups.currentItem())
        if select:
            self.select_name(select)
        self._refresh_details()
        self._rebuild_tray_menu()

    def select_name(self, name: str):
        for row, s in enumerate(self.inv.servers):
            if s.name == name:
                idx = self.proxy.mapFromSource(self.model.index(row, 1))
                if not idx.isValid():  # hidden by filter: clear filters
                    self.search.clear()
                    self.groups.setCurrentRow(0)
                    idx = self.proxy.mapFromSource(self.model.index(row, 1))
                self.table.setCurrentIndex(idx)
                self.table.selectRow(idx.row())
                self.table.scrollTo(idx)
                return

    def current_server(self) -> Server | None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        return self.model.server(self.proxy.mapToSource(idx).row())

    def selected_servers(self) -> list[Server]:
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        servers = [self.model.server(r) for r in sorted(rows)]
        if not servers and self.current_server():
            servers = [self.current_server()]
        return servers

    def visible_servers(self) -> list[Server]:
        return [self.model.server(self.proxy.mapToSource(self.proxy.index(r, 0)).row())
                for r in range(self.proxy.rowCount())]

    def _refresh_details(self):
        s = self.current_server()
        self.details.show_server(self.inv, s, self.model.status.get(s.name) if s else None)

    def _inventory_mtime(self) -> float:
        try:
            return self.inv.path.stat().st_mtime
        except OSError:
            return 0.0

    def _reload_from_disk(self):
        mtime = self._inventory_mtime()
        if mtime == self._own_mtime:
            return
        self._own_mtime = mtime
        current = self.current_server()
        try:
            self.inv.load()
        except (OSError, ValueError) as e:
            self.toast.show_message(f"Could not reload inventory: {e}", 6000)
            return
        self.reload(select=current.name if current and self.inv.get(current.name) else None)
        self.toast.show_message("Inventory changed on disk — reloaded")

    def _save(self) -> bool:
        try:
            self.inv.save()
            self._own_mtime = self._inventory_mtime()
            return True
        except OSError as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return False

    def _search_enter(self):
        if self.proxy.rowCount() == 1:
            self.table.selectRow(0)
            self.connect_selected()
        elif self.proxy.rowCount():
            self.table.setFocus()
            self.table.selectRow(0)

    def _context_menu(self, pos):
        if not self.table.indexAt(pos).isValid():
            return
        ic = lambda name, key="muted": theme.icon(name, self.c[key])  # noqa: E731
        m = QMenu(self)
        m.addAction(ic("terminal"), "Connect", self.connect_selected)
        m.addAction(ic("copy"), "Copy SSH command", self.copy_command)
        m.addAction(ic("copy"), "Copy IP address",
                    lambda: self._copy(self.current_server().host, "IP address copied"))
        m.addSeparator()
        m.addAction(ic("pulse"), "Test connection", lambda: self.run_jobs("check", self.selected_servers()))
        m.addAction(ic("tag"), "Fetch hostname", lambda: self.run_jobs("hostname", self.selected_servers()))
        m.addSeparator()
        m.addAction(ic("edit"), "Edit", self.edit_server)
        m.addAction(ic("duplicate"), "Duplicate", self.duplicate_server)
        m.addAction(ic("trash", "danger"), "Delete", self.delete_servers)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _copy(self, text: str, message: str):
        QApplication.clipboard().setText(text)
        self.toast.show_message(message)

    # ---- background / window state ----------------------------------
    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.bring_to_front()

    def quit_app(self):
        self._quitting = True
        QApplication.quit()

    def closeEvent(self, event):
        if self._quitting or not self.inv.settings.close_to_background:
            event.accept()
            QApplication.quit()
            return
        event.ignore()
        if not self.inv.settings.background_hint_shown:
            where = "the tray icon" if self.tray else "the app menu, or run  ssh-manager  in a terminal"
            QMessageBox.information(
                self, "Still running",
                f"{APP_NAME} keeps running in the background.\n\n"
                f"To bring it back, use {where}.\n"
                "To stop it, use Quit (Ctrl+Q) or run  ssh-manager quit.\n\n"
                "You can change this in Settings.")
            self.inv.settings.background_hint_shown = True
            self._save()
        self.hide()

    # ---- actions -----------------------------------------------------
    def _open_terminal(self, s: Server) -> bool:
        try:
            open_in_terminal(self.inv, s)
        except Exception as e:
            QMessageBox.critical(self, "Could not open terminal", str(e))
            return False
        self.toast.show_message(f"Opening session to {s.name}…")
        return True

    def connect_selected(self):
        servers = self.selected_servers()
        if len(servers) > 5 and QMessageBox.question(
                self, "Connect", f"Open {len(servers)} terminal windows?") != QMessageBox.Yes:
            return
        for s in servers:
            if not self._open_terminal(s):
                return

    def copy_command(self):
        s = self.current_server()
        if s:
            self._copy(display_command(self.inv, s), "SSH command copied")

    def _edit_dialog(self, server: Server | None, title: str, original: str | None):
        dlg = ServerDialog(self, self.inv, server, title)
        dlg.original = self.inv.get(original) if original else None
        if server is None and self.proxy.group not in (ALL_GROUPS, "Ungrouped"):
            dlg.group.setCurrentText(self.proxy.group)
        if dlg.exec() and dlg.result_server:
            self.inv.upsert(dlg.result_server, original_name=original)
            if original:
                self.model.status.pop(original, None)
            if self._save():
                self.reload(select=dlg.result_server.name)
                self.toast.show_message(f"Saved {dlg.result_server.name}")

    def add_server(self):
        self._edit_dialog(None, "Add server", None)

    def edit_server(self):
        s = self.current_server()
        if s:
            self._edit_dialog(s, f"Edit {s.name}", s.name)

    def duplicate_server(self):
        s = self.current_server()
        if s:
            copy = replace(s, name=s.name + "-copy", hostname="", extra_options=list(s.extra_options))
            self._edit_dialog(copy, "Duplicate server", None)

    def delete_servers(self):
        servers = self.selected_servers()
        if not servers:
            return
        names = ", ".join(s.name for s in servers[:6]) + ("…" if len(servers) > 6 else "")
        if QMessageBox.question(self, "Delete", f"Delete {len(servers)} server(s)?\n\n{names}") != QMessageBox.Yes:
            return
        # delete dependents first so jump hosts in the same selection can go too
        for s in sorted(servers, key=lambda x: not x.jump):
            try:
                self.inv.delete(s.name)
            except InventoryError as e:
                QMessageBox.warning(self, "Cannot delete", str(e))
        if self._save():
            self.reload()
            self.toast.show_message(f"Deleted {len(servers)} server(s)")

    def run_jobs(self, kind: str, servers: list[Server], quiet: bool = False):
        if not servers:
            return
        for s in servers:
            self.model.set_status(s.name, None, "Checking…" if kind == "check" else "Fetching hostname…")
            self.pool.start(Job(kind, self.inv, s, self.job_signals))
        if not quiet:
            verb = "Checking" if kind == "check" else "Fetching hostname for"
            self.toast.show_message(f"{verb} {len(servers)} server(s)…")
        self._refresh_details()

    def _job_done(self, kind: str, name: str, ok: bool, msg: str):
        s = self.inv.get(name)
        if s is None:
            return
        if kind == "hostname":
            if ok:
                s.hostname = msg
                self._save()
                self.model.set_status(name, True, f"Logged in — hostname {msg}")
            else:
                self.model.set_status(name, False, f"Login failed: {msg}")
        else:
            self.model.set_status(name, ok, msg)
        self._update_summary()
        cur = self.current_server()
        if cur and cur.name == name:
            self._refresh_details()

    def open_settings(self):
        dlg = SettingsDialog(self, self.inv)
        if dlg.exec():
            before = (self.inv.settings.theme, self.inv.settings.font_size)
            dlg.apply()
            if self._save():
                self.reload()
                changed = before != (self.inv.settings.theme, self.inv.settings.font_size)
                self.toast.show_message("Theme and font size apply after restarting the app" if changed
                                        else "Settings saved", 4000)

    def _merge(self, servers: list[Server]):
        added, skipped = [], []
        for s in sorted(servers, key=lambda s: bool(s.jump)):
            try:
                if self.inv.get(s.name):
                    raise InventoryError("already exists")
                self.inv.upsert(s)
                added.append(s.name)
            except InventoryError as e:
                skipped.append(f"{s.name}: {e}")
        if added and self._save():
            self.reload()
        msg = f"Imported {len(added)} server(s)."
        if skipped:
            msg += f"\n\nSkipped {len(skipped)}:\n" + "\n".join(skipped[:15])
        QMessageBox.information(self, "Import", msg)

    def import_ssh_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import OpenSSH config", str(Path.home() / ".ssh" / "config"))
        if path:
            self._merge(parse_ssh_config(Path(path).read_text(encoding="utf-8")))

    def import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import JSON", str(Path.home()), "JSON (*.json)")
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._merge([Server.from_dict(d) for d in (data.get("servers", []) if isinstance(data, dict) else data)])

    def export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON", str(Path.home() / "ssh-inventory.json"),
                                              "JSON (*.json)")
        if path:
            Path(path).write_text(json.dumps({"servers": [asdict(s) for s in self.inv.servers]}, indent=2),
                                  encoding="utf-8")
            self.toast.show_message(f"Exported to {path}")


def make_app() -> QApplication:
    if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ:
        # prefer native Wayland (also what WSLg offers), fall back to X11
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb" if os.environ.get("WAYLAND_DISPLAY") else "xcb"
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("ssh-manager")
    app.setStyle("Fusion")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    return app


def build_window(inv: Inventory) -> MainWindow:
    """Apply theme and font, then create the main window (QApplication must exist)."""
    app = QApplication.instance()
    colors = theme.resolve(inv.settings.theme)
    app.setFont(theme.ui_font(inv.settings.font_size))
    app.setStyleSheet(theme.stylesheet(colors, inv.settings.font_size))
    return MainWindow(inv, colors)


def run(inv: Inventory, hidden: bool = False) -> int:
    app = make_app()

    # single instance: if one is already running, ask it to show its window
    if background.send_command("noop" if hidden else "show"):
        return 0
    server = QLocalServer()
    QLocalServer.removeServer(background.SOCKET_NAME)
    server.listen(background.SOCKET_NAME)

    app.setQuitOnLastWindowClosed(False)
    win = build_window(inv)

    def on_connection():
        sock = server.nextPendingConnection()
        if sock is None:
            return

        def handle():
            msg = bytes(sock.readAll()).decode(errors="ignore").strip()
            if msg == "show":
                win.bring_to_front()
            elif msg == "quit":
                win.quit_app()

        sock.readyRead.connect(handle)
        sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_connection)
    if not hidden:
        win.show()
    return app.exec()
