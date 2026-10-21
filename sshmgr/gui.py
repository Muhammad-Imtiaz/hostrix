"""Qt (PySide6) user interface."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QFileSystemWatcher, QModelIndex, QObject, QRunnable,
                            QSortFilterProxyModel, Qt, QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QSplitter, QTableView, QToolBar, QVBoxLayout, QWidget)

from . import APP_NAME, __version__
from .connect import display_command, fetch_hostname, key_exists, open_in_terminal, tcp_reachable
from .inventory import Inventory, InventoryError, Server, parse_ssh_config

ICON_PATH = Path(__file__).with_name("assets") / "ssh-manager.svg"
ALL_GROUPS = "All servers"


def access_label(s: Server) -> str:
    parts = []
    if s.requires_vpn:
        parts.append("VPN")
    if s.jump:
        parts.append(f"via {s.jump}")
    return " + ".join(parts) or "Direct"


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
    COLUMNS = ["", "Name", "Hostname", "IP / Host", "User", "Group", "Access", "Description"]

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
        return None

    def data(self, index, role=Qt.DisplayRole):
        s = self.inv.servers[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == 0:
                ok = self.status.get(s.name, (None, ""))[0]
                return "●" if ok is not None else "○"
            return [None, s.name, s.hostname, s.host, self.inv.effective_user(s), s.group,
                    access_label(s), s.description][col]
        if role == Qt.ForegroundRole and col == 0:
            ok = self.status.get(s.name, (None, ""))[0]
            return QColor("#2e9d4f") if ok else QColor("#d64545") if ok is False else QColor("#9aa0a6")
        if role == Qt.ToolTipRole:
            if col == 0:
                return self.status.get(s.name, (None, "Not checked yet"))[1]
            if col == 7:
                return s.description
        if role == Qt.TextAlignmentRole and col == 0:
            return Qt.AlignCenter
        if role == Qt.UserRole:
            # searchable text
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
            hay = model.data(model.index(row, 0), Qt.UserRole)
            return all(word in hay for word in self.text.split())
        return True


# ---- dialogs ---------------------------------------------------------
class ServerDialog(QDialog):
    def __init__(self, parent, inv: Inventory, server: Server | None = None, title="Add server"):
        super().__init__(parent)
        self.inv = inv
        self.original = server
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        s = server or Server(name="", host="")

        self.name = QLineEdit(s.name)
        self.name.setPlaceholderText("unique alias, e.g. bd-prod-db-01")
        self.host = QLineEdit(s.host)
        self.host.setPlaceholderText("IP address or DNS name")
        self.hostname = QLineEdit(s.hostname)
        self.hostname.setPlaceholderText("machine hostname (optional, can be fetched)")
        self.user = QLineEdit(s.user)
        self.user.setPlaceholderText(f"default: {inv.settings.default_user or '(none)'}")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(s.port)

        self.key = QLineEdit(s.key_path)
        self.key.setPlaceholderText(f"default: {inv.settings.default_key or '(ssh default)'}")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_key)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key)
        key_row.addWidget(browse)

        self.jump = QComboBox()
        self.jump.addItem("(none)", "")
        for other in sorted(inv.servers, key=lambda x: x.name.lower()):
            if server is None or other.name != server.name:
                self.jump.addItem(f"{other.name}  ({other.host})", other.name)
        idx = self.jump.findData(s.jump)
        self.jump.setCurrentIndex(max(idx, 0))

        self.vpn = QCheckBox("Requires VPN")
        self.vpn.setChecked(s.requires_vpn)
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItems([""] + inv.groups())
        self.group.setCurrentText(s.group)
        self.description = QPlainTextEdit(s.description)
        self.description.setFixedHeight(70)
        self.extra = QLineEdit(", ".join(s.extra_options))
        self.extra.setPlaceholderText("ssh -o options, comma separated, e.g. ServerAliveInterval=30")

        form = QFormLayout()
        form.addRow("Name *", self.name)
        form.addRow("Host / IP *", self.host)
        form.addRow("Hostname", self.hostname)
        form.addRow("User", self.user)
        form.addRow("Port", self.port)
        form.addRow("Key path", key_row)
        form.addRow("Jump host", self.jump)
        form.addRow("", self.vpn)
        form.addRow("Group", self.group)
        form.addRow("Description", self.description)
        form.addRow("Extra options", self.extra)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
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
            port=self.port.value(),
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
        self.setMinimumWidth(560)
        st = inv.settings
        self.user = QLineEdit(st.default_user)
        self.key = QLineEdit(st.default_key)
        self.terminal = QComboBox()
        self.terminal.setEditable(True)
        self.terminal.addItems(["auto", "gnome-terminal -- {args}", "konsole -e {args}",
                                "xfce4-terminal -x {args}", "xterm -T {title} -e {args}",
                                "x-terminal-emulator -e {args}"])
        self.terminal.setCurrentText(st.terminal or "auto")
        help_ = QLabel("<small>'auto' picks Windows Terminal on WSL, otherwise the first terminal found. "
                       "Templates: <b>{args}</b> = ssh-manager argv appended, <b>{cmd}</b> = one quoted "
                       "shell string, <b>{title}</b> = server name.</small>")
        help_.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Default user", self.user)
        form.addRow("Default key path", self.key)
        form.addRow("Terminal", self.terminal)
        form.addRow("", help_)
        form.addRow("Inventory file", QLabel(str(inv.path)))
        cfg = QLabel(f"<code>Include {inv.ssh_config_path}</code>")
        cfg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("Use in ~/.ssh/config", cfg)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def apply(self):
        self.inv.settings.default_user = self.user.text().strip()
        self.inv.settings.default_key = self.key.text().strip()
        self.inv.settings.terminal = self.terminal.currentText().strip() or "auto"


# ---- details panel ---------------------------------------------------
class Details(QGroupBox):
    def __init__(self):
        super().__init__("Details")
        self.fields: dict[str, QLabel] = {}
        form = QFormLayout()
        for key in ["Name", "Hostname", "IP / Host", "Port", "User", "Key path", "Jump host",
                    "Access", "Group", "Description", "Status"]:
            lbl = QLabel("—")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.fields[key] = lbl
            form.addRow(f"<b>{key}</b>", lbl)
        self.command = QPlainTextEdit()
        self.command.setReadOnly(True)
        self.command.setFont(QFont("monospace"))
        self.command.setFixedHeight(90)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setDefault(True)
        self.connect_btn.setMinimumHeight(34)
        self.copy_btn = QPushButton("Copy command")
        self.test_btn = QPushButton("Test")
        self.fetch_btn = QPushButton("Fetch hostname")
        self.edit_btn = QPushButton("Edit")
        self.dup_btn = QPushButton("Duplicate")
        self.delete_btn = QPushButton("Delete")

        row1 = QHBoxLayout()
        row1.addWidget(self.copy_btn)
        row1.addWidget(self.test_btn)
        row1.addWidget(self.fetch_btn)
        row2 = QHBoxLayout()
        row2.addWidget(self.edit_btn)
        row2.addWidget(self.dup_btn)
        row2.addWidget(self.delete_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("<b>SSH command</b>"))
        layout.addWidget(self.command)
        layout.addWidget(self.connect_btn)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addStretch()
        self.show_server(None, None, None)

    def show_server(self, inv: Inventory | None, s: Server | None, status):
        enabled = s is not None
        for b in (self.connect_btn, self.copy_btn, self.test_btn, self.fetch_btn,
                  self.edit_btn, self.dup_btn, self.delete_btn):
            b.setEnabled(enabled)
        if not enabled:
            for lbl in self.fields.values():
                lbl.setText("—")
            self.command.setPlainText("")
            return
        key = inv.effective_key(s)
        exists = key_exists(inv, s)
        key_text = key or "(ssh default keys)"
        if exists is False:
            key_text += "  <span style='color:#d64545'>(file not found)</span>"
        user = inv.effective_user(s)
        values = {
            "Name": s.name,
            "Hostname": s.hostname or "<i>unknown — use Fetch hostname</i>",
            "IP / Host": s.host,
            "Port": str(s.port),
            "User": (user + ("" if s.user else " <i>(default)</i>")) if user else "<i>(local user)</i>",
            "Key path": key_text + ("" if s.key_path or not key else " <i>(default)</i>"),
            "Jump host": s.jump or "—",
            "Access": access_label(s),
            "Group": s.group or "—",
            "Description": s.description or "—",
            "Status": (status or (None, "not checked"))[1],
        }
        for k, v in values.items():
            self.fields[k].setText(v)
        try:
            self.command.setPlainText(display_command(inv, s))
        except ValueError as e:
            self.command.setPlainText(f"error: {e}")


# ---- main window -----------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, inv: Inventory):
        super().__init__()
        self.inv = inv
        self.setWindowTitle(f"{APP_NAME}  —  {inv.path}")
        self.resize(1320, 760)
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(16)
        self.job_signals = _JobSignals()
        self.job_signals.done.connect(self._job_done)

        self.model = ServerModel(inv)
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)

        # left: groups
        self.groups = QListWidget()
        self.groups.setMaximumWidth(220)
        self.groups.setSpacing(2)
        self.groups.currentItemChanged.connect(
            lambda item, _prev: self.proxy.set_filter(group=item.data(Qt.UserRole)) if item else None)

        # center: search + table
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, IP, hostname, user, description…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda t: self.proxy.set_filter(text=t))
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for col, width in enumerate([26, 190, 130, 115, 75, 95, 140]):
            self.table.setColumnWidth(col, width)
        self.table.doubleClicked.connect(lambda _: self.connect_selected())
        self.table.selectionModel().currentRowChanged.connect(lambda *_: self._refresh_details())

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.search)
        cl.addWidget(self.table)

        # right: details
        self.details = Details()
        self.details.setMinimumWidth(380)
        d = self.details
        d.connect_btn.clicked.connect(self.connect_selected)
        d.copy_btn.clicked.connect(self.copy_command)
        d.test_btn.clicked.connect(lambda: self.run_jobs("check", self.selected_servers()))
        d.fetch_btn.clicked.connect(lambda: self.run_jobs("hostname", self.selected_servers()))
        d.edit_btn.clicked.connect(self.edit_server)
        d.dup_btn.clicked.connect(self.duplicate_server)
        d.delete_btn.clicked.connect(self.delete_servers)

        splitter = QSplitter()
        splitter.addWidget(self.groups)
        splitter.addWidget(center)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([150, 840, 380])
        self.setCentralWidget(splitter)

        self._build_actions()
        self.reload()

        # pick up edits made outside the GUI (CLI, text editor, another window).
        # Watch the folder: saves replace the file, which drops a file watch.
        self._own_mtime = self._inventory_mtime()
        self.watcher = QFileSystemWatcher([str(inv.path.parent)] if inv.path.parent.exists() else [])
        self._reload_timer = QTimer(self, singleShot=True, interval=300, timeout=self._reload_from_disk)
        self.watcher.directoryChanged.connect(lambda _: self._reload_timer.start())
        self.statusBar().showMessage(f"{len(inv.servers)} servers loaded")

    # ---- setup -------------------------------------------------------
    def _act(self, text, slot, shortcut=None, tip=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
        return a

    def _build_actions(self):
        add = self._act("Add", self.add_server, "Ctrl+N", "Add a server (Ctrl+N)")
        edit = self._act("Edit", self.edit_server, "F2")
        delete = self._act("Delete", self.delete_servers, QKeySequence.Delete)
        conn = self._act("Connect", self.connect_selected, None, "Open an SSH session (Enter / double-click)")
        check_all = self._act("Check all", lambda: self.run_jobs("check", self.visible_servers()),
                              "Ctrl+T", "TCP check port 22 on every visible server")
        fetch = self._act("Fetch hostnames", lambda: self.run_jobs("hostname", self.selected_servers()),
                          None, "Log in to selected servers and read their hostname")
        settings = self._act("Settings", self.open_settings, "Ctrl+,")

        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for a in (conn, None, add, edit, delete, None, check_all, fetch, None, settings):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(tb)

        m = self.menuBar().addMenu("&File")
        m.addAction(self._act("Import ~/.ssh/config…", self.import_ssh_config))
        m.addAction(self._act("Import JSON…", self.import_json))
        m.addAction(self._act("Export JSON…", self.export_json))
        m.addSeparator()
        m.addAction(self._act("Open config folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.inv.path.parent)))))
        m.addAction(settings)
        m.addSeparator()
        m.addAction(self._act("Quit", self.close, "Ctrl+Q"))
        m = self.menuBar().addMenu("&Server")
        for a in (conn, add, edit, delete, check_all, fetch):
            m.addAction(a)
        m = self.menuBar().addMenu("&Help")
        m.addAction(self._act("About", lambda: QMessageBox.about(
            self, APP_NAME, f"<b>{APP_NAME}</b> {__version__}<br>Inventory: {self.inv.path}<br>"
                            f"ssh_config: {self.inv.ssh_config_path}")))

        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence(Qt.Key_Return), self.table, activated=self.connect_selected)
        QShortcut(QKeySequence(Qt.Key_Enter), self.table, activated=self.connect_selected)
        QShortcut(QKeySequence(Qt.Key_Escape), self.search, activated=self.search.clear)
        self.search.returnPressed.connect(self._search_enter)

    # ---- helpers -----------------------------------------------------
    def reload(self, select: str | None = None):
        current_group = self.groups.currentItem().data(Qt.UserRole) if self.groups.currentItem() else ALL_GROUPS
        self.model.reload()
        self.groups.blockSignals(True)
        self.groups.clear()
        names = [ALL_GROUPS] + self.inv.groups()
        if any(not s.group for s in self.inv.servers):
            names.append("Ungrouped")
        for g in names:
            count = len(self.inv.servers) if g == ALL_GROUPS else sum(
                1 for s in self.inv.servers if (s.group or "Ungrouped") == g)
            item = QListWidgetItem(f"{g}  ({count})")
            item.setData(Qt.UserRole, g)
            self.groups.addItem(item)
            if g == current_group:
                self.groups.setCurrentItem(item)
        if not self.groups.currentItem():
            self.groups.setCurrentRow(0)
        self.groups.blockSignals(False)
        self.proxy.set_filter(group=self.groups.currentItem().data(Qt.UserRole))
        if select:
            self.select_name(select)
        elif self.proxy.rowCount() and not self.table.currentIndex().isValid():
            self.table.selectRow(0)
        self._refresh_details()

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
            self.statusBar().showMessage(f"Could not reload inventory: {e}", 8000)
            return
        self.reload(select=current.name if current and self.inv.get(current.name) else None)
        self.statusBar().showMessage("Inventory changed on disk, reloaded", 5000)

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

    # ---- actions -----------------------------------------------------
    def connect_selected(self):
        servers = self.selected_servers()
        if len(servers) > 5 and QMessageBox.question(
                self, "Connect", f"Open {len(servers)} terminal windows?") != QMessageBox.Yes:
            return
        for s in servers:
            try:
                open_in_terminal(self.inv, s)
                self.statusBar().showMessage(f"Opened terminal for {s.name}", 5000)
            except Exception as e:
                QMessageBox.critical(self, "Could not open terminal", str(e))
                return

    def copy_command(self):
        s = self.current_server()
        if s:
            QApplication.clipboard().setText(display_command(self.inv, s))
            self.statusBar().showMessage("SSH command copied to clipboard", 4000)

    def add_server(self):
        dlg = ServerDialog(self, self.inv, None, "Add server")
        if self.proxy.group not in (ALL_GROUPS, "Ungrouped"):
            dlg.group.setCurrentText(self.proxy.group)
        if dlg.exec() and dlg.result_server:
            self.inv.upsert(dlg.result_server)
            if self._save():
                self.reload(select=dlg.result_server.name)

    def edit_server(self):
        s = self.current_server()
        if not s:
            return
        dlg = ServerDialog(self, self.inv, s, f"Edit {s.name}")
        if dlg.exec() and dlg.result_server:
            self.inv.upsert(dlg.result_server, original_name=s.name)
            self.model.status.pop(s.name, None)
            if self._save():
                self.reload(select=dlg.result_server.name)

    def duplicate_server(self):
        s = self.current_server()
        if not s:
            return
        copy = replace(s, name=s.name + "-copy", hostname="", extra_options=list(s.extra_options))
        dlg = ServerDialog(self, self.inv, copy, "Duplicate server")
        dlg.original = None
        if dlg.exec() and dlg.result_server:
            self.inv.upsert(dlg.result_server)
            if self._save():
                self.reload(select=dlg.result_server.name)

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

    def run_jobs(self, kind: str, servers: list[Server]):
        if not servers:
            return
        for s in servers:
            self.model.set_status(s.name, None, "checking…" if kind == "check" else "fetching hostname…")
            self.pool.start(Job(kind, self.inv, s, self.job_signals))
        verb = "Checking" if kind == "check" else "Fetching hostname for"
        self.statusBar().showMessage(f"{verb} {len(servers)} server(s)…")
        self._refresh_details()

    def _job_done(self, kind: str, name: str, ok: bool, msg: str):
        s = self.inv.get(name)
        if s is None:
            return
        if kind == "hostname":
            if ok:
                s.hostname = msg
                self._save()
                self.model.set_status(name, True, f"logged in, hostname {msg}")
            else:
                self.model.set_status(name, False, f"login failed: {msg}")
        else:
            self.model.set_status(name, ok, msg)
        self.statusBar().showMessage(f"{name}: {msg}", 6000)
        self._refresh_details()

    def open_settings(self):
        dlg = SettingsDialog(self, self.inv)
        if dlg.exec():
            dlg.apply()
            if self._save():
                self.reload()

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
            self.statusBar().showMessage(f"Exported to {path}", 5000)


def run(inv: Inventory) -> int:
    if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ:
        # prefer native Wayland (also what WSLg offers), fall back to X11
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb" if os.environ.get("WAYLAND_DISPLAY") else "xcb"
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("ssh-manager")
    app.setStyle("Fusion")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    win = MainWindow(inv)
    win.show()
    return app.exec()
