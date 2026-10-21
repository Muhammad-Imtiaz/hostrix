"""Colours, stylesheet and icons for the web-style look."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

FONT_FAMILIES = ["Inter", "Ubuntu Sans", "Ubuntu", "Segoe UI", "SF Pro Text", "Helvetica Neue",
                 "Cantarell", "Noto Sans", "DejaVu Sans"]
MONO_FAMILIES = ["JetBrains Mono", "Ubuntu Sans Mono", "Ubuntu Mono", "Cascadia Mono", "Consolas",
                 "SF Mono", "Menlo", "DejaVu Sans Mono"]

LIGHT = dict(
    bg="#f3f5fa", surface="#ffffff", surface_alt="#f8fafc", border="#e3e8f0", border_strong="#cbd5e1",
    text="#0f172a", muted="#64748b", faint="#94a3b8",
    primary="#2563eb", primary_hover="#1d4ed8", primary_soft="#e8efff", primary_text="#ffffff",
    sidebar="#0f172a", sidebar_text="#cbd5e1", sidebar_muted="#64748b", sidebar_active="#1e293b",
    sidebar_accent="#60a5fa",
    success="#16a34a", danger="#dc2626", danger_soft="#fef2f2", warning="#d97706",
    code_bg="#0f172a", code_text="#e2e8f0",
    row_hover="#f5f8ff", selection="#e6eeff",
    pill_vpn=("#fef3c7", "#92400e"), pill_jump=("#ede9fe", "#5b21b6"),
    pill_direct=("#dcfce7", "#166534"), pill_group=("#eef2f7", "#334155"),
)

DARK = dict(
    bg="#0b1120", surface="#111827", surface_alt="#0f172a", border="#1f2a3d", border_strong="#334155",
    text="#e5e7eb", muted="#94a3b8", faint="#64748b",
    primary="#3b82f6", primary_hover="#2563eb", primary_soft="#172554", primary_text="#ffffff",
    sidebar="#020617", sidebar_text="#cbd5e1", sidebar_muted="#64748b", sidebar_active="#111c33",
    sidebar_accent="#60a5fa",
    success="#22c55e", danger="#f87171", danger_soft="#2a1215", warning="#f59e0b",
    code_bg="#020617", code_text="#e2e8f0",
    row_hover="#162036", selection="#1c2d52",
    pill_vpn=("#3a2a0a", "#fcd34d"), pill_jump=("#2a1f4a", "#c4b5fd"),
    pill_direct=("#0f2e1c", "#86efac"), pill_group=("#1e293b", "#cbd5e1"),
)


def resolve(theme: str) -> dict:
    if theme == "dark":
        return DARK
    if theme == "light":
        return LIGHT
    hints = QGuiApplication.styleHints()
    return DARK if hints.colorScheme() == Qt.ColorScheme.Dark else LIGHT


def ui_font(size: int) -> QFont:
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPointSize(size)
    return f


def mono_font(size: int) -> QFont:
    f = QFont()
    f.setFamilies(MONO_FAMILIES)
    f.setStyleHint(QFont.Monospace)
    f.setPointSize(size)
    return f


CHECK_SVG = (Path(__file__).with_name("assets") / "check.svg").as_posix()


def stylesheet(c: dict, size: int) -> str:
    big = size + 9
    mid = size + 3
    return f"""
* {{ outline: none; }}
QWidget {{ color: {c['text']}; font-size: {size}pt; }}
QMainWindow, #Main {{ background: {c['bg']}; }}
QToolTip {{ background: {c['code_bg']}; color: {c['code_text']}; border: none; padding: 6px 8px; border-radius: 6px; }}

/* ---- sidebar ---- */
#Sidebar {{ background: {c['sidebar']}; }}
#Sidebar QLabel {{ color: {c['sidebar_text']}; }}
#Brand {{ font-size: {mid}pt; font-weight: 700; color: #ffffff; }}
#BrandSub {{ color: {c['sidebar_muted']}; font-size: {size - 1}pt; }}
#SideHeading {{ color: {c['sidebar_muted']}; font-size: {size - 2}pt; font-weight: 700; }}
#GroupList {{ background: transparent; border: none; color: {c['sidebar_text']}; }}
#GroupList::item {{ padding: 9px 12px; border-radius: 8px; margin: 1px 0; }}
#GroupList::item:hover {{ background: {c['sidebar_active']}; }}
#GroupList::item:selected {{ background: {c['sidebar_active']}; color: #ffffff; border-left: 3px solid {c['sidebar_accent']}; }}
#SideButton {{ background: transparent; color: {c['sidebar_text']}; border: none; text-align: left;
               padding: 9px 12px; border-radius: 8px; }}
#SideButton:hover {{ background: {c['sidebar_active']}; color: #ffffff; }}
#SideButton::menu-indicator {{ image: none; }}

/* ---- header ---- */
#PageTitle {{ font-size: {big}pt; font-weight: 700; }}
#PageSub, QLabel[muted="true"] {{ color: {c['muted']}; }}
#Search {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px;
           padding: 9px 12px; selection-background-color: {c['primary']}; }}
#Search:focus {{ border: 1px solid {c['primary']}; }}

/* ---- cards ---- */
#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
#Card QLabel {{ background: transparent; }}
#DetailName {{ font-size: {mid + 2}pt; font-weight: 700; }}
#DetailHost {{ color: {c['muted']}; }}
#FieldLabel {{ color: {c['muted']}; font-size: {size - 1}pt; font-weight: 600; }}
#FieldValue {{ font-weight: 500; }}
#Code {{ background: {c['code_bg']}; color: {c['code_text']}; border: none; border-radius: 10px; padding: 10px; }}
#Empty {{ color: {c['muted']}; font-size: {mid}pt; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---- table ---- */
QTableView {{ background: {c['surface']}; border: none; border-radius: 14px; gridline-color: transparent;
              selection-background-color: {c['selection']}; selection-color: {c['text']}; }}
QTableView::item {{ border-bottom: 1px solid {c['border']}; padding: 0 8px; }}
QTableView::item:hover {{ background: {c['row_hover']}; }}
QTableView::item:selected {{ background: {c['selection']}; color: {c['text']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {c['surface']}; color: {c['muted']}; border: none;
                         border-bottom: 1px solid {c['border']}; padding: 12px 8px; font-weight: 700;
                         font-size: {size - 1}pt; }}
QTableCornerButton::section {{ background: {c['surface']}; border: none; }}

/* ---- buttons ---- */
QPushButton {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border_strong']};
               border-radius: 9px; padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {c['surface_alt']}; border-color: {c['primary']}; color: {c['primary']}; }}
QPushButton:pressed {{ background: {c['primary_soft']}; }}
QPushButton:disabled {{ color: {c['faint']}; border-color: {c['border']}; background: {c['surface']}; }}
QPushButton[variant="primary"] {{ background: {c['primary']}; color: {c['primary_text']}; border: 1px solid {c['primary']}; }}
QPushButton[variant="primary"]:hover {{ background: {c['primary_hover']}; border-color: {c['primary_hover']}; color: #ffffff; }}
QPushButton[variant="primary"]:disabled {{ background: {c['border']}; border-color: {c['border']}; color: {c['faint']}; }}
QPushButton[variant="success"] {{ background: {c['success']}; color: #ffffff; border: 1px solid {c['success']};
                                   font-size: {size + 1}pt; padding: 11px 16px; border-radius: 10px; }}
QPushButton[variant="success"]:hover {{ background: #15803d; border-color: #15803d; color: #ffffff; }}
QPushButton[variant="success"]:disabled {{ background: {c['border']}; border-color: {c['border']}; color: {c['faint']}; }}
QPushButton[variant="danger"] {{ color: {c['danger']}; border-color: {c['danger']}; background: transparent; }}
QPushButton[variant="danger"]:hover {{ background: {c['danger_soft']}; color: {c['danger']}; border-color: {c['danger']}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: none; color: {c['muted']}; padding: 6px 10px; }}
QPushButton[variant="ghost"]:hover {{ color: {c['primary']}; background: {c['primary_soft']}; }}

/* ---- forms / dialogs ---- */
QDialog {{ background: {c['bg']}; }}
QDialog QLabel {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QComboBox {{ background: {c['surface']}; border: 1px solid {c['border_strong']};
    border-radius: 8px; padding: 7px 10px; selection-background-color: {c['primary']}; selection-color: #ffffff; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {c['primary']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; padding: 4px;
    selection-background-color: {c['primary_soft']}; selection-color: {c['text']}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {c['border_strong']}; background: {c['surface']}; }}
QCheckBox::indicator:checked {{ background: {c['primary']}; border-color: {c['primary']}; image: url({CHECK_SVG}); }}
QCheckBox::indicator:disabled {{ background: {c['border']}; border-color: {c['border']}; }}
QCheckBox:disabled {{ color: {c['faint']}; }}
#SectionTitle {{ font-weight: 700; font-size: {size + 1}pt; }}
QMessageBox {{ background: {c['surface']}; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['primary_soft']}; color: {c['primary']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}

/* ---- scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 4px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}
QSplitter::handle {{ background: transparent; }}

/* ---- toast ---- */
#Toast {{ background: {c['code_bg']}; color: #ffffff; border-radius: 10px; padding: 10px 18px; font-weight: 600; }}
"""


# Lucide-style outline icons (24x24, stroke = currentColor)
_ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "terminal": '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    "trash": '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
    "duplicate": '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16V4a2 2 0 0 1 2-2h12"/>',
    "pulse": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "tag": '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8Z"/><circle cx="7" cy="7" r="1.5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    "more": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    "server": '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
}


def icon(name: str, color: str, size: int = 18) -> QIcon:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p, QRectF(0, 0, size * ratio, size * ratio))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return QIcon(pm)
