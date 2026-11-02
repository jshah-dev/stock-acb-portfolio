"""Tailwind Slate Modern Desktop Stylesheet (QSS) for senior-friendly high-contrast UX."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCalendarWidget,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSpinBox,
    QTableWidgetItem,
    QToolButton,
    QWidgetAction,
)

# Platform-native clean typography to eliminate font-alias search warnings
if sys.platform == "win32":
    SYSTEM_FONT = "Segoe UI"
    SYSTEM_MONO_FONT = "Consolas, 'Courier New'"
elif sys.platform == "darwin":
    SYSTEM_FONT = "Helvetica Neue"
    SYSTEM_MONO_FONT = "Menlo, Monaco, 'Courier New'"
else:
    SYSTEM_FONT = "Arial"
    SYSTEM_MONO_FONT = "'DejaVu Sans Mono', 'Liberation Mono', 'Courier New'"

# Resolved path to SVG chevron icon for comboboxes
CHEVRON_SVG_PATH = (Path(__file__).parent / "assets" / "chevron_down.svg").resolve().as_posix()
# Resolved path to SVG chevron up icon for table sorting
CHEVRON_UP_SVG_PATH = (Path(__file__).parent / "assets" / "chevron_up.svg").resolve().as_posix()
# Resolved path to SVG calendar icon for date pickers
CALENDAR_SVG_PATH = (Path(__file__).parent / "assets" / "calendar.svg").resolve().as_posix()


def get_main_stylesheet() -> str:
    """Build and return the application-wide QSS stylesheet with platform-aware fonts and assets."""
    return f"""
/* Global Application Reset */
QWidget {{
    font-family: "{SYSTEM_FONT}";
    font-size: 14px;
    color: #0F172A;
    background-color: #F8FAFC;
}}

QMainWindow, QDialog {{
    background-color: #F8FAFC;
}}

/* Tab Bar Styling */
QTabWidget::pane {{
    border: 1px solid #E2E8F0;
    background-color: #FFFFFF;
    border-radius: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background: #E2E8F0;
    color: #475569;
    padding: 10px 24px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    font-size: 14px;
    min-height: 24px;
}}

QTabBar::tab:selected {{
    background: #FFFFFF;
    color: #2563EB;
    border: 1px solid #E2E8F0;
    border-bottom: 2px solid #2563EB;
}}

QTabBar::tab:hover:!selected {{
    background: #CBD5E1;
}}

/* Card Panels */
QFrame[class="kpi-card"], QFrame.kpi-card {{
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 14px 18px;
}}

QLabel[class="kpi-title"], QLabel.kpi-title {{
    font-size: 12px;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: transparent;
}}

QLabel[class="kpi-value"], QLabel.kpi-value {{
    font-size: 24px;
    font-weight: 700;
    color: #0F172A;
    background: transparent;
    margin-top: 4px;
}}

QLabel[class="kpi-subtext"], QLabel.kpi-subtext {{
    font-size: 12px;
    color: #059669;
    font-weight: 500;
    background: transparent;
}}

/* Buttons */
QPushButton {{
    font-size: 13px;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 16px;
    min-height: 22px;
    border: 1px solid #CBD5E1;
    background-color: #FFFFFF;
    color: #334155;
}}

QPushButton:hover {{
    background-color: #F1F5F9;
    border-color: #94A3B8;
}}

QPushButton:pressed {{
    background-color: #E2E8F0;
}}

QPushButton[class="primary-btn"], QPushButton.primary-btn {{
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #2563EB;
}}

QPushButton[class="primary-btn"]:hover, QPushButton.primary-btn:hover {{
    background-color: #1D4ED8;
    color: #FFFFFF;
    border-color: #1D4ED8;
}}

QPushButton[class="primary-btn"]:pressed, QPushButton.primary-btn:pressed {{
    background-color: #1E40AF;
    color: #FFFFFF;
    border-color: #1E40AF;
}}

QPushButton[class="primary-btn"]:focus, QPushButton.primary-btn:focus {{
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
}}

QPushButton[class="success-btn"], QPushButton.success-btn {{
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #059669;
}}

QPushButton[class="success-btn"]:hover, QPushButton.success-btn:hover {{
    background-color: #047857;
    color: #FFFFFF;
    border-color: #047857;
}}

QPushButton[class="success-btn"]:pressed, QPushButton.success-btn:pressed {{
    background-color: #065F46;
    color: #FFFFFF;
    border-color: #065F46;
}}

QPushButton[class="success-btn"]:focus, QPushButton.success-btn:focus {{
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
}}

QPushButton[class="danger-btn"], QPushButton.danger-btn {{
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #DC2626;
}}

QPushButton[class="danger-btn"]:hover, QPushButton.danger-btn:hover {{
    background-color: #B91C1C;
    color: #FFFFFF;
    border-color: #B91C1C;
}}

QPushButton[class="danger-btn"]:pressed, QPushButton.danger-btn:pressed {{
    background-color: #991B1B;
    color: #FFFFFF;
    border-color: #991B1B;
}}

QPushButton[class="danger-btn"]:focus, QPushButton.danger-btn:focus {{
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #B91C1C;
}}

/* Modern QComboBox (Dropdown) */
QComboBox {{
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 36px 6px 12px;
    font-size: 14px;
    color: #0F172A;
    min-height: 26px;
}}

QComboBox:hover {{
    border-color: #94A3B8;
    background-color: #FFFFFF;
}}

QComboBox:focus, QComboBox:on {{
    border: 1.5px solid #2563EB;
    background-color: #FFFFFF;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 32px;
    border-left: none;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background: transparent;
}}

QComboBox::down-arrow {{
    image: url("{CHEVRON_SVG_PATH}");
    width: 12px;
    height: 8px;
    margin-right: 10px;
}}

/* QComboBox Popup List View */
QComboBox QAbstractItemView {{
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    outline: none;
    font-size: 14px;
    color: #0F172A;
}}

QComboBox QAbstractItemView::item {{
    min-height: 32px;
    padding: 6px 12px;
    border-radius: 4px;
    color: #0F172A;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: #F1F5F9;
    color: #0F172A;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: #EFF6FF;
    color: #1D4ED8;
    font-weight: 600;
}}

/* Input Fields & SpinBoxes */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 14px;
    color: #0F172A;
    min-height: 24px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1.5px solid #2563EB;
    background-color: #FFFFFF;
}}

/* Tooltip - Modern Dark Slate */
QToolTip {{
    background-color: #0F172A;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 500;
}}

/* Modern QDateEdit & QDateTimeEdit */
QDateEdit, QDateTimeEdit {{
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 30px 6px 10px;
    font-size: 13px;
    color: #0F172A;
    min-height: 24px;
    font-weight: 500;
}}

QDateEdit:hover, QDateTimeEdit:hover {{
    border-color: #94A3B8;
}}

QDateEdit:focus, QDateTimeEdit:focus, QDateEdit:on, QDateTimeEdit:on {{
    border: 1.5px solid #2563EB;
    background-color: #FFFFFF;
}}

QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border-left: none;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background: transparent;
}}

QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{
    image: url("{CALENDAR_SVG_PATH}");
    width: 14px;
    height: 14px;
    margin-right: 6px;
}}

QDateEdit::up-button, QDateEdit::down-button,
QDateTimeEdit::up-button, QDateTimeEdit::down-button {{
    width: 0px;
    height: 0px;
    border: none;
}}

/* Calendar Widget Popup */
QCalendarWidget {{
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 10px;
}}

QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: #F8FAFC;
    border-bottom: 1px solid #E2E8F0;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    min-height: 38px;
}}

QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {{
    font-size: 13px;
    font-weight: bold;
    color: #475569;
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    margin: 4px 6px;
}}

QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {{
    background-color: #F1F5F9;
    border-color: #94A3B8;
    color: #0F172A;
}}

QCalendarWidget QToolButton#qt_calendar_monthbutton,
QCalendarWidget QToolButton#qt_calendar_yearbutton {{
    font-size: 13px;
    font-weight: 700;
    color: #0F172A;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    margin: 3px 2px;
}}

QCalendarWidget QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget QToolButton#qt_calendar_yearbutton:hover {{
    background-color: #E2E8F0;
}}

QCalendarWidget QToolButton#qt_calendar_monthbutton::menu-indicator {{
    image: none;
    width: 0px;
}}

QCalendarWidget QMenu {{
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 4px;
    font-size: 13px;
    color: #0F172A;
}}

QCalendarWidget QMenu::item:selected {{
    background-color: #EFF6FF;
    color: #2563EB;
    font-weight: 600;
    border-radius: 4px;
}}

QCalendarWidget QSpinBox {{
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    font-size: 13px;
    color: #0F172A;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
}}

QCalendarWidget QTableView {{
    background-color: #FFFFFF;
    border: none;
    font-size: 13px;
    color: #1E293B;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
    outline: none;
}}

QCalendarWidget QTableView QHeaderView::section {{
    background-color: #F8FAFC;
    color: #64748B;
    font-weight: 600;
    font-size: 12px;
    border: none;
    border-bottom: 1px solid #E2E8F0;
    padding: 6px 0;
}}

/* Checkbox */
QCheckBox {{
    font-size: 13px;
    color: #334155;
    font-weight: 500;
    spacing: 8px;
    background: transparent;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1.5px solid #94A3B8;
    border-radius: 4px;
    background-color: #FFFFFF;
}}

QCheckBox::indicator:checked {{
    background-color: #2563EB;
    border-color: #2563EB;
}}

/* Modern High-DPI Table Widget */
QTableWidget {{
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    gridline-color: #F8FAFC;
    selection-background-color: #EFF6FF;
    selection-color: #1E40AF;
    font-size: 13px;
    outline: none;
}}

QHeaderView {{
    background-color: #F8FAFC;
    border: none;
    border-bottom: 2px solid #CBD5E1;
}}

QHeaderView::section {{
    background-color: #F8FAFC;
    color: #475569;
    padding: 8px 10px;
    border: none;
    border-right: 1px solid #E2E8F0;
    border-bottom: 2px solid #CBD5E1;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.2px;
    min-height: 32px;
}}

QHeaderView::section:hover {{
    background-color: #F1F5F9;
    color: #0F172A;
}}

QHeaderView::section:checked {{
    background-color: #EFF6FF;
    color: #2563EB;
}}

QHeaderView::down-arrow {{
    image: url("{CHEVRON_SVG_PATH}");
    width: 10px;
    height: 7px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
    margin-right: 8px;
}}

QHeaderView::up-arrow {{
    image: url("{CHEVRON_UP_SVG_PATH}");
    width: 10px;
    height: 7px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
    margin-right: 8px;
}}

/* Segmented Chart Tab Buttons */
QPushButton[class="chart-tab"], QPushButton.chart-tab {{
    background-color: #F1F5F9;
    color: #475569;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
    min-height: 22px;
    outline: none;
}}

QPushButton[class="chart-tab"]:hover, QPushButton.chart-tab:hover {{
    background-color: #E2E8F0;
    color: #0F172A;
    border-color: #94A3B8;
}}

QPushButton[class="chart-tab"]:focus, QPushButton.chart-tab:focus {{
    outline: none;
    border-color: #2563EB;
}}

QPushButton[class="chart-tab-active"], QPushButton.chart-tab-active {{
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #2563EB;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
    min-height: 22px;
    outline: none;
}}

QPushButton[class="chart-tab-active"]:hover, QPushButton.chart-tab-active:hover {{
    background-color: #1D4ED8;
    color: #FFFFFF;
    border-color: #1D4ED8;
}}

QPushButton[class="chart-tab-active"]:focus, QPushButton.chart-tab-active:focus {{
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #1D4ED8;
    outline: none;
}}

/* Scrollbars */
QScrollBar:vertical {{
    border: none;
    background: #F1F5F9;
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background: #CBD5E1;
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: #94A3B8;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Scroll Area */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

/* Upload Dropzone & Modern Import Components */
QFrame[class="drop-zone"], QFrame.drop-zone {{
    background-color: #F8FAFC;
    border: 2px dashed #CBD5E1;
    border-radius: 12px;
    padding: 30px 20px;
}}

QFrame[class="drop-zone"]:hover, QFrame.drop-zone:hover {{
    background-color: #EFF6FF;
    border-color: #3B82F6;
}}

QFrame[class="drop-zone-active"], QFrame.drop-zone-active {{
    background-color: #DBEAFE;
    border-color: #2563EB;
}}

QFrame[class="file-info-card"], QFrame.file-info-card {{
    background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 12px 16px;
}}

QLabel[class="step-number"], QLabel.step-number {{
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 12px;
    border-radius: 12px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    qproperty-alignment: AlignCenter;
}}

QFrame[class="step-card"], QFrame.step-card {{
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 20px;
}}
"""


MAIN_STYLESHEET = get_main_stylesheet()


def set_style_class(widget, class_name: str) -> None:
    """Assign a dynamic CSS class and re-polish the widget so Qt immediately renders it."""
    widget.setProperty("class", class_name)
    style = widget.style()
    if style:
        style.unpolish(widget)
        style.polish(widget)


def configure_modern_calendar(calendar: QCalendarWidget) -> None:
    """Apply modern, spacious styling, 2010-2040 year dropdown, and neutral weekend formatting."""
    if not calendar:
        return

    calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
    calendar.setGridVisible(False)
    calendar.setDateRange(QDate(2010, 1, 1), QDate(2040, 12, 31))

    # Neutral slate weekend formatting
    fmt = QTextCharFormat()
    fmt.setForeground(QColor("#64748B"))
    calendar.setWeekdayTextFormat(Qt.Sunday, fmt)
    calendar.setWeekdayTextFormat(Qt.Saturday, fmt)

    # Clean 2010-2040 scrollable year selection dropdown (compact bounded height, no huge list)
    year_btn = calendar.findChild(QToolButton, "qt_calendar_yearbutton")
    if year_btn:
        try:
            year_btn.clicked.disconnect()
        except Exception:
            pass

        year_menu = QMenu(year_btn)
        year_menu.setStyleSheet(
            """
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 2px;
            }
            """
        )

        action = QWidgetAction(year_menu)
        list_w = QListWidget()
        list_w.setFixedWidth(86)
        list_w.setFixedHeight(180)  # Compact bounded height (~5 visible items, smoothly scrollable)
        list_w.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        list_w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_w.setStyleSheet(
            """
            QListWidget {
                border: none;
                background-color: #FFFFFF;
                font-size: 13px;
                color: #0F172A;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #F1F5F9;
                color: #2563EB;
            }
            QListWidget::item:selected {
                background-color: #EFF6FF;
                color: #2563EB;
                font-weight: 600;
            }
            """
        )

        for yr in range(2010, 2041):
            item = QListWidgetItem(str(yr))
            item.setTextAlignment(Qt.AlignCenter)
            list_w.addItem(item)

        def _on_about_to_show():
            cur_yr = str(calendar.yearShown())
            matching = list_w.findItems(cur_yr, Qt.MatchExactly)
            if matching:
                list_w.setCurrentItem(matching[0])
                list_w.scrollToItem(matching[0], QAbstractItemView.PositionAtCenter)

        year_menu.aboutToShow.connect(_on_about_to_show)

        def _on_item_clicked(item: QListWidgetItem):
            y = int(item.text())
            cur = calendar.selectedDate()
            target_month = calendar.monthShown()
            target_day = min(cur.day(), 28)
            try:
                new_d = QDate(y, target_month, cur.day())
                if not new_d.isValid():
                    new_d = QDate(y, target_month, target_day)
            except Exception:
                new_d = QDate(y, target_month, target_day)

            calendar.setCurrentPage(y, target_month)
            calendar.setSelectedDate(new_d)
            year_btn.setText(str(y))
            year_menu.close()

        list_w.itemClicked.connect(_on_item_clicked)
        action.setDefaultWidget(list_w)
        year_menu.addAction(action)

        year_btn._year_list_widget = list_w
        year_btn.setMenu(year_menu)
        year_btn.setPopupMode(QToolButton.InstantPopup)

    # Sync year button text when user changes page (e.g. via prev/next month buttons)
    def _on_page_changed(year: int, month: int):
        if year_btn:
            year_btn.setText(str(year))

    try:
        calendar.currentPageChanged.connect(_on_page_changed)
    except Exception:
        pass

    # Completely disable and hide spinbox stepper buttons on year edit
    year_edit = calendar.findChild(QSpinBox, "qt_calendar_yearedit")
    if year_edit:
        year_edit.setButtonSymbols(QAbstractSpinBox.NoButtons)
        year_edit.setEnabled(False)
        year_edit.hide()


class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem supporting accurate numeric sorting for currencies, quantities, and metrics."""

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return False

        val1 = self.data(Qt.UserRole)
        val2 = other.data(Qt.UserRole)

        if val1 is not None and val2 is not None:
            try:
                return float(val1) < float(val2)
            except (ValueError, TypeError):
                return str(val1).upper() < str(val2).upper()

        return self.text().upper() < other.text().upper()



