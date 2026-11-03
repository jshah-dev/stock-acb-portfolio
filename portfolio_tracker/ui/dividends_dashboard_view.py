"""Dividends Dashboard: multi-account filter, Indian FY quick filters, KPI cards, Qt charts, and dividend ledger."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QDate, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QPieSeries,
    QPieSlice,
    QValueAxis,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.db import (
    delete_dividend,
    get_accounts,
    get_all_symbols,
    get_dividends,
    get_dividends_summary,
)
from portfolio_tracker.exporter import export_dividends_to_excel
from portfolio_tracker.ui.charts import CHART_COLORS
from portfolio_tracker.ui.manual_dividend_dialog import ManualDividendDialog
from portfolio_tracker.ui.styles import (
    SYSTEM_FONT,
    NumericTableWidgetItem,
    configure_modern_calendar,
    set_style_class,
)

DONUT_PALETTE = [
    QColor("#059669"),
    QColor("#2563EB"),
    QColor("#D97706"),
    QColor("#7C3AED"),
    QColor("#DB2777"),
    QColor("#0891B2"),
    QColor("#EA580C"),
    QColor("#10B981"),
    QColor("#3B82F6"),
    QColor("#F59E0B"),
    QColor("#8B5CF6"),
    QColor("#EC4899"),
    QColor("#06B6D4"),
    QColor("#F97316"),
    QColor("#14B8A6"),
    QColor("#6366F1"),
    QColor("#84CC16"),
    QColor("#A855F7"),
    QColor("#E11D48"),
    QColor("#0EA5E9"),
]


class LegendItemWidget(QFrame):
    """Interactive multi-column legend item with color indicator, symbol, and total dividend."""

    hovered = Signal(bool)

    def __init__(
        self,
        slice_obj: QPieSlice,
        label: str,
        amount: float,
        pct: float,
        color: QColor,
        parent=None,
    ):
        super().__init__(parent)
        self.slice_obj = slice_obj
        self.label = label
        self.amount = amount
        self.pct = pct
        self.setCursor(Qt.PointingHandCursor)
        self.set_highlighted(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        bullet = QLabel()
        bullet.setFixedSize(9, 9)
        bullet.setStyleSheet(
            f"background-color: {color.name()}; border-radius: 4px; border: none;"
        )
        layout.addWidget(bullet)

        amt_str = f"₹{amount:,.0f}" if amount >= 1 else f"₹{amount:.2f}"
        lbl_text = QLabel(
            f"<span style='font-weight: 700; color: #1E293B;'>{label}</span> "
            f"<span style='color: #059669; font-weight: 600; font-size: 10px;'>{amt_str}</span>"
        )
        lbl_text.setStyleSheet("font-size: 11px;")
        layout.addWidget(lbl_text)
        layout.addStretch()

        self.setToolTip(f"<b>{label}</b><br/>Total Dividend: ₹{amount:,.2f}<br/>Share: {pct:.1f}%")

    def set_highlighted(self, active: bool):
        if active:
            self.setStyleSheet(
                "QFrame {"
                "  background-color: #EDE9FE;"
                "  border: 1px solid #7C3AED;"
                "  border-radius: 5px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QFrame {"
                "  background-color: #FFFFFF;"
                "  border: 1px solid #E2E8F0;"
                "  border-radius: 5px;"
                "}"
                "QFrame:hover {"
                "  background-color: #F1F5F9;"
                "  border-color: #CBD5E1;"
                "}"
            )

    def enterEvent(self, event):
        super().enterEvent(event)
        self.hovered.emit(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hovered.emit(False)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.slice_obj.setExploded(not self.slice_obj.isExploded())


class DividendChartsView(QWidget):
    """High-DPI native Qt Chart widget showing Monthly/Yearly trend and Top Dividend stocks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.summary_data: Dict = {}
        self.current_mode = "DONUT"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header controls
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 10, 12, 4)
        header_layout.setSpacing(10)

        self.lbl_chart_title = QLabel("Dividend Income Analytics")
        self.lbl_chart_title.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 14px;")
        header_layout.addWidget(self.lbl_chart_title)

        # Dynamic inspection info banner
        self.lbl_hover_info = QLabel("")
        self.lbl_hover_info.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #0F172A; "
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; "
            "border-radius: 6px; padding: 3px 10px;"
        )
        self.lbl_hover_info.setVisible(False)
        header_layout.addWidget(self.lbl_hover_info)

        header_layout.addStretch()

        # Top N selector for Top Contributors
        self.lbl_top_n = QLabel("Show:")
        self.lbl_top_n.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569;")
        header_layout.addWidget(self.lbl_top_n)

        self.combo_top_n = QComboBox()
        self.combo_top_n.setView(QListView())
        self.combo_top_n.setMinimumWidth(95)
        self.combo_top_n.addItem("Top 5", 5)
        self.combo_top_n.addItem("Top 10", 10)
        self.combo_top_n.addItem("Top 20", 20)
        self.combo_top_n.addItem("Top 50", 50)
        self.combo_top_n.setCurrentIndex(1)  # Default Top 10
        self.combo_top_n.currentIndexChanged.connect(lambda: self.refresh_chart(self.summary_data))
        header_layout.addWidget(self.combo_top_n)

        header_layout.addSpacing(6)

        # Tab Mode buttons
        self.btn_tab_donut = QPushButton("🍩 Top Contributors")
        self.btn_tab_bar = QPushButton("📊 Bar Trend")
        self.btn_tab_line = QPushButton("📈 Trend Line")

        for btn in (self.btn_tab_donut, self.btn_tab_bar, self.btn_tab_line):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            set_style_class(btn, "chart-tab")

        self.btn_tab_donut.clicked.connect(lambda: self.set_mode("DONUT"))
        self.btn_tab_bar.clicked.connect(lambda: self.set_mode("BAR"))
        self.btn_tab_line.clicked.connect(lambda: self.set_mode("LINE"))

        header_layout.addWidget(self.btn_tab_donut)
        header_layout.addWidget(self.btn_tab_bar)
        header_layout.addWidget(self.btn_tab_line)
        layout.addLayout(header_layout)

        # Chart View and Right-Side Multi-Column Legend container
        self.chart_hlayout = QHBoxLayout()
        self.chart_hlayout.setContentsMargins(0, 0, 0, 0)
        self.chart_hlayout.setSpacing(12)

        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
        self.chart.legend().setVisible(False)
        self.chart.setMargins(self.chart.margins())

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setStyleSheet("background: transparent; border: none;")
        self.chart_view.setMinimumHeight(450)
        self.chart_hlayout.addWidget(self.chart_view, stretch=3)

        # Right-side Multi-Column Legend Panel
        self.legend_panel = QFrame()
        self.legend_panel.setStyleSheet(
            "QFrame {"
            "  background-color: #F8FAFC;"
            "  border: 1px solid #E2E8F0;"
            "  border-radius: 8px;"
            "}"
        )
        self.legend_panel.setMinimumWidth(320)
        lp_layout = QVBoxLayout(self.legend_panel)
        lp_layout.setContentsMargins(10, 8, 10, 8)
        lp_layout.setSpacing(6)

        # Legend Panel Header
        lhdr = QHBoxLayout()
        self.lbl_legend_title = QLabel("Top Contributors Legend")
        self.lbl_legend_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        lhdr.addWidget(self.lbl_legend_title)
        lhdr.addStretch()
        self.lbl_legend_count = QLabel("")
        self.lbl_legend_count.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #64748B; background: #EDF2F7; border-radius: 4px; padding: 1px 6px;"
        )
        lhdr.addWidget(self.lbl_legend_count)
        lp_layout.addLayout(lhdr)

        # Scroll Area for multi-column legend items
        self.legend_scroll = QScrollArea()
        self.legend_scroll.setWidgetResizable(True)
        self.legend_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.legend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.legend_content = QWidget()
        self.legend_content.setStyleSheet("background: transparent;")
        self.legend_grid = QGridLayout(self.legend_content)
        self.legend_grid.setContentsMargins(2, 2, 2, 2)
        self.legend_grid.setSpacing(5)
        self.legend_scroll.setWidget(self.legend_content)
        lp_layout.addWidget(self.legend_scroll)

        self.chart_hlayout.addWidget(self.legend_panel, stretch=2)
        layout.addLayout(self.chart_hlayout)

        self._update_tab_buttons()

    def set_mode(self, mode: str):
        self.current_mode = mode
        self._update_tab_buttons()
        self.refresh_chart(self.summary_data)

    def _update_tab_buttons(self):
        active_css = "background-color: #059669; color: #FFFFFF; font-weight: 700; border-radius: 6px; padding: 4px 12px;"
        inactive_css = "background-color: #F1F5F9; color: #475569; font-weight: 500; border-radius: 6px; padding: 4px 12px;"
        self.btn_tab_donut.setStyleSheet(active_css if self.current_mode == "DONUT" else inactive_css)
        self.btn_tab_bar.setStyleSheet(active_css if self.current_mode == "BAR" else inactive_css)
        self.btn_tab_line.setStyleSheet(active_css if self.current_mode == "LINE" else inactive_css)

        is_donut = (self.current_mode == "DONUT")
        self.lbl_top_n.setVisible(is_donut)
        self.combo_top_n.setVisible(is_donut)
        self.legend_panel.setVisible(is_donut)

    def _clear_legend_panel(self):
        while self.legend_grid.count():
            item = self.legend_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.lbl_legend_count.setText("")

    def _format_cat_label(self, cat_key: str) -> str:
        """Format 'YYYY-MM' as 'Mon 'YY' for clean categorical axis display."""
        if len(cat_key) == 7 and cat_key[4] == "-":
            try:
                return datetime.strptime(cat_key, "%Y-%m").strftime("%b '%y")
            except Exception:
                pass
        return cat_key

    def _format_cat_full(self, cat_key: str) -> str:
        """Format 'YYYY-MM' as 'Month YYYY' for descriptive hover tooltips."""
        if len(cat_key) == 7 and cat_key[4] == "-":
            try:
                return datetime.strptime(cat_key, "%Y-%m").strftime("%B %Y")
            except Exception:
                pass
        return cat_key

    def refresh_chart(self, summary_data: Dict):
        self.summary_data = summary_data
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)

        self._clear_legend_panel()
        self.lbl_hover_info.setText("")
        self.lbl_hover_info.setVisible(False)
        QToolTip.hideText()

        if not summary_data or summary_data.get("payout_count", 0) == 0:
            self.chart.setTitle("No dividend data available for the selected period.")
            self.legend_panel.setVisible(False)
            return

        self.chart.setTitle("")

        if self.current_mode == "DONUT":
            self.legend_panel.setVisible(True)
            self._build_donut_chart(summary_data)
        elif self.current_mode == "BAR":
            self.legend_panel.setVisible(False)
            self._build_trend_chart(summary_data)
        elif self.current_mode == "LINE":
            self.legend_panel.setVisible(False)
            self._build_line_chart(summary_data)

    def _build_donut_chart(self, summary_data: Dict):
        contributors = summary_data.get("top_contributors", [])
        if not contributors:
            self._clear_legend_panel()
            return

        self._clear_legend_panel()

        series = QPieSeries()
        series.setHoleSize(0.45)

        top_n = self.combo_top_n.currentData() if self.combo_top_n else 10
        if not top_n:
            top_n = 10

        top_items = contributors[:top_n]
        other_amt = sum(c["amount"] for c in contributors[top_n:])
        total_amt = summary_data.get("total_amount") or sum(c["amount"] for c in contributors) or 1.0

        total_slices = len(top_items) + (1 if other_amt > 0 else 0)
        num_cols = 3 if total_slices > 24 else 2

        self.lbl_legend_count.setText(f"{total_slices} contributors")

        legend_items_data = []

        for idx, item in enumerate(top_items):
            pct = (item["amount"] / total_amt) * 100.0
            slice_ = series.append(f"{item['symbol']} (₹{item['amount']:,.0f})", item["amount"])
            color = DONUT_PALETTE[idx % len(DONUT_PALETTE)]
            slice_.setBrush(color)
            slice_.hovered.connect(
                lambda state, s=slice_, sym=item["symbol"], amt=item["amount"], p=pct: self._on_slice_hovered(s, sym, amt, p, state)
            )
            legend_items_data.append((slice_, item["symbol"], item["amount"], pct, color))

        if other_amt > 0:
            other_count = len(contributors) - top_n
            pct = (other_amt / total_amt) * 100.0
            other_label = f"Other ({other_count} stocks: ₹{other_amt:,.0f})"
            slice_ = series.append(other_label, other_amt)
            color = QColor("#94A3B8")
            slice_.setBrush(color)
            sym_name = f"Other ({other_count} stocks)"
            slice_.hovered.connect(
                lambda state, s=slice_, sym=sym_name, amt=other_amt, p=pct: self._on_slice_hovered(s, sym, amt, p, state)
            )
            legend_items_data.append((slice_, sym_name, other_amt, pct, color))

        self.chart.addSeries(series)
        self.chart.legend().setVisible(False)

        # Populate right-side multi-column legend panel
        for idx, (slice_, label, amount, pct, color) in enumerate(legend_items_data):
            row = idx // num_cols
            col = idx % num_cols
            item_widget = LegendItemWidget(slice_, label, amount, pct, color, self.legend_content)
            slice_.legend_widget = item_widget  # type: ignore
            item_widget.hovered.connect(
                lambda state, s=slice_, l=label, a=amount, p=pct: self._on_slice_hovered(s, l, a, p, state)
            )
            self.legend_grid.addWidget(item_widget, row, col)

    def _on_slice_hovered(self, slice_obj: QPieSlice, label: str, amount: float, pct: float, state: bool):
        slice_obj.setExploded(state)
        slice_obj.setLabelVisible(state)

        legend_w = getattr(slice_obj, "legend_widget", None)
        if legend_w:
            legend_w.set_highlighted(state)

        if state:
            tip = f"<b>{label}</b><br/>Total Dividend: ₹{amount:,.2f}<br/>Share: {pct:.1f}%"
            QToolTip.showText(QCursor.pos(), tip, self.chart_view)
            self.lbl_hover_info.setText(f"🍩 {label}: ₹{amount:,.2f} ({pct:.1f}%)")
            self.lbl_hover_info.setVisible(True)
        else:
            QToolTip.hideText()
            self.lbl_hover_info.setText("")
            self.lbl_hover_info.setVisible(False)

    def _get_trend_data(self, summary_data: Dict):
        monthly = summary_data.get("monthly_totals", {})
        fy_totals = summary_data.get("fy_totals", {})

        if len(monthly) > 0 and len(monthly) <= 18:
            categories = list(monthly.keys())
            values = [monthly[k] for k in categories]
            series_name = "Monthly Dividends"
        else:
            categories = sorted(list(fy_totals.keys()))
            values = [fy_totals[k] for k in categories]
            series_name = "Financial Year Dividends"
        return categories, values, series_name

    def _build_trend_chart(self, summary_data: Dict):
        categories, values, series_name = self._get_trend_data(summary_data)
        if not categories:
            return

        display_categories = [self._format_cat_label(c) for c in categories]

        bar_set = QBarSet(series_name)
        bar_set.setColor(QColor("#059669"))
        for v in values:
            bar_set.append(v)

        bar_set.hovered.connect(
            lambda state, idx, cats=categories, vals=values: self._on_bar_hovered(state, idx, cats, vals)
        )

        series = QBarSeries()
        series.append(bar_set)
        self.chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(display_categories)
        self.chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max(values) if values else 100
        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.15)
        axis_y.setLabelFormat("%d")
        axis_y.setTitleText("Dividends (₹)")
        self.chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        self.chart.legend().setVisible(False)

    def _on_bar_hovered(self, state: bool, index: int, categories: List[str], values: List[float]):
        if state and 0 <= index < len(categories):
            cat = categories[index]
            amt = values[index]
            disp = self._format_cat_full(cat)
            tip = f"<b>{disp}</b><br/>Total Dividends: ₹{amt:,.2f}"
            QToolTip.showText(QCursor.pos(), tip, self.chart_view)
            self.lbl_hover_info.setText(f"📊 {disp}: ₹{amt:,.2f}")
            self.lbl_hover_info.setVisible(True)
        else:
            QToolTip.hideText()
            self.lbl_hover_info.setText("")
            self.lbl_hover_info.setVisible(False)

    def _build_line_chart(self, summary_data: Dict):
        categories, values, series_name = self._get_trend_data(summary_data)
        if not categories:
            return

        display_categories = [self._format_cat_label(c) for c in categories]

        series = QLineSeries()
        series.setName(series_name)
        for idx, v in enumerate(values):
            series.append(float(idx), float(v))

        pen = QPen(QColor("#059669"))
        pen.setWidth(3)
        series.setPen(pen)
        series.setPointsVisible(True)

        series.hovered.connect(
            lambda pt, state, cats=categories, vals=values: self._on_line_hovered(pt, state, cats, vals)
        )

        self.chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(display_categories)
        self.chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max(values) if values else 100
        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.15)
        axis_y.setLabelFormat("%d")
        axis_y.setTitleText("Dividends (₹)")
        self.chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        self.chart.legend().setVisible(False)

    def _on_line_hovered(self, point: QPointF, state: bool, categories: List[str], values: List[float]):
        if state:
            idx = int(round(point.x()))
            if 0 <= idx < len(categories):
                cat = categories[idx]
                amt = values[idx]
                disp = self._format_cat_full(cat)
                tip = f"<b>{disp}</b><br/>Dividend Income: ₹{amt:,.2f}"
                QToolTip.showText(QCursor.pos(), tip, self.chart_view)
                self.lbl_hover_info.setText(f"📈 {disp}: ₹{amt:,.2f}")
                self.lbl_hover_info.setVisible(True)
        else:
            QToolTip.hideText()
            self.lbl_hover_info.setText("")
            self.lbl_hover_info.setVisible(False)


class DividendsDashboardView(QWidget):
    """Full-featured Dividends Dashboard with KPIs, native charts, Indian FY filter, and sortable ledger."""

    data_changed = Signal()

    def __init__(self, db_conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.db_conn = db_conn
        self._init_ui()
        self.refresh_accounts()
        self.refresh_data()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(18, 16, 18, 24)
        main_layout.setSpacing(16)

        # ----------------------------------------------------
        # 1. Top Filter Controls Bar
        # ----------------------------------------------------
        controls_frame = QFrame()
        controls_frame.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(10)

        # Row 1: Account, FY filter, and Action buttons
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        lbl_acc = QLabel("Portfolio:")
        lbl_acc.setStyleSheet("font-weight: 600; color: #334155;")
        row1.addWidget(lbl_acc)

        self.combo_account = QComboBox()
        self.combo_account.setView(QListView())
        self.combo_account.setMinimumWidth(210)
        self.combo_account.currentIndexChanged.connect(self.refresh_data)
        row1.addWidget(self.combo_account)

        row1.addSpacing(6)

        lbl_fy = QLabel("Financial Year:")
        lbl_fy.setStyleSheet("font-weight: 600; color: #334155;")
        row1.addWidget(lbl_fy)

        self.combo_fy = QComboBox()
        self.combo_fy.setView(QListView())
        self.combo_fy.setMinimumWidth(150)
        self.combo_fy.addItem("All Time", None)
        self.combo_fy.addItem("FY 2026-27", ("2026-04-01", "2027-03-31"))
        self.combo_fy.addItem("FY 2025-26", ("2025-04-01", "2026-03-31"))
        self.combo_fy.addItem("FY 2024-25", ("2024-04-01", "2025-03-31"))
        self.combo_fy.addItem("FY 2023-24", ("2023-04-01", "2024-03-31"))
        self.combo_fy.addItem("FY 2022-23", ("2022-04-01", "2023-03-31"))
        self.combo_fy.addItem("Custom Dates", "CUSTOM")
        self.combo_fy.currentIndexChanged.connect(self._on_fy_changed)
        row1.addWidget(self.combo_fy)

        # Date Pickers (dd-MM-yyyy format)
        self.lbl_from = QLabel("From:")
        self.lbl_from.setStyleSheet("font-weight: 600; color: #334155;")
        row1.addWidget(self.lbl_from)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        configure_modern_calendar(self.date_from.calendarWidget())
        self.date_from.setDisplayFormat("dd-MM-yyyy")
        self.date_from.setDate(QDate.currentDate().addYears(-1))
        self.date_from.dateChanged.connect(self._on_custom_date_changed)
        row1.addWidget(self.date_from)

        self.lbl_to = QLabel("To:")
        self.lbl_to.setStyleSheet("font-weight: 600; color: #334155;")
        row1.addWidget(self.lbl_to)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        configure_modern_calendar(self.date_to.calendarWidget())
        self.date_to.setDisplayFormat("dd-MM-yyyy")
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self._on_custom_date_changed)
        row1.addWidget(self.date_to)

        # By default (All Time), disable custom date inputs
        self.date_from.setEnabled(False)
        self.date_to.setEnabled(False)

        row1.addStretch()

        self.btn_add_dividend = QPushButton("+ Add Dividend")
        set_style_class(self.btn_add_dividend, "primary-btn")
        self.btn_add_dividend.clicked.connect(self._open_manual_dividend)
        row1.addWidget(self.btn_add_dividend)

        self.btn_export = QPushButton("📥 Export to Excel")
        self.btn_export.clicked.connect(self._export_excel)
        row1.addWidget(self.btn_export)

        controls_layout.addLayout(row1)
        main_layout.addWidget(controls_frame)

        # ----------------------------------------------------
        # 2. Executive KPI Cards Banner
        # ----------------------------------------------------
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(14)

        # Card 1: Total Dividends
        self.card_total = self._create_kpi_card("TOTAL DIVIDENDS", "₹0.00", "#059669", "#D1FAE5")
        kpi_layout.addWidget(self.card_total)

        # Card 2: Payout Count
        self.card_count = self._create_kpi_card("PAYOUT EVENTS", "0", "#2563EB", "#DBEAFE")
        kpi_layout.addWidget(self.card_count)

        # Card 3: Unique Companies
        self.card_companies = self._create_kpi_card("DIVIDEND STOCKS", "0", "#7C3AED", "#EDE9FE")
        kpi_layout.addWidget(self.card_companies)

        # Card 4: Top Payer
        self.card_top_payer = self._create_kpi_card("TOP PAYER", "—", "#D97706", "#FEF3C7")
        kpi_layout.addWidget(self.card_top_payer)

        main_layout.addLayout(kpi_layout)

        # ----------------------------------------------------
        # 3. Dividends Ledger Table
        # ----------------------------------------------------
        table_frame = QFrame()
        table_frame.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        tf_layout = QVBoxLayout(table_frame)
        tf_layout.setContentsMargins(12, 12, 12, 12)
        tf_layout.setSpacing(8)

        # Table Header Bar (matching Holdings Dashboard)
        tbl_hdr = QHBoxLayout()
        tbl_hdr.setSpacing(8)

        lbl_tbl_title = QLabel("Dividends Transaction Ledger")
        lbl_tbl_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        tbl_hdr.addWidget(lbl_tbl_title)

        self.lbl_ledger_count = QLabel("")
        self.lbl_ledger_count.setStyleSheet(
            "background-color: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 10px; "
            "padding: 2px 8px; font-size: 11px; font-weight: 600; color: #475569; margin-left: 6px;"
        )
        tbl_hdr.addWidget(self.lbl_ledger_count)

        tbl_hdr.addStretch()

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 Search symbol, account, remarks...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setFixedWidth(240)
        self.txt_search.textChanged.connect(self._filter_ledger_table)
        tbl_hdr.addWidget(self.txt_search)

        self.btn_autofit = QPushButton("↔ Auto-Fit")
        self.btn_autofit.setToolTip("Auto-fit column widths to fit content")
        self.btn_autofit.clicked.connect(self._auto_fit_columns)
        tbl_hdr.addWidget(self.btn_autofit)

        self._load_symbols_completer()
        tf_layout.addLayout(tbl_hdr)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Date",
            "Account",
            "Stock Symbol",
            "Shares Held",
            "Dividend / Share (₹)",
            "Total Dividend (₹)",
            "Remarks",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        self.table.setMinimumHeight(350)
        tf_layout.addWidget(self.table)

        main_layout.addWidget(table_frame)

        # ----------------------------------------------------
        # 4. Collapsible Analytics Chart (Closed by Default)
        # ----------------------------------------------------
        self.btn_toggle_charts = QPushButton("▶ Show Visual Charts & Analytics (Donut, Bar & Trend Line)")
        self.btn_toggle_charts.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_charts.setStyleSheet(
            "QPushButton {"
            "  text-align: left;"
            "  padding: 10px 14px;"
            "  font-size: 13px;"
            "  font-weight: 700;"
            "  color: #1E293B;"
            "  background-color: #F8FAFC;"
            "  border: 1px solid #CBD5E1;"
            "  border-radius: 8px;"
            "}"
            "QPushButton:hover {"
            "  background-color: #F1F5F9;"
            "  color: #059669;"
            "  border-color: #94A3B8;"
            "}"
        )
        self.btn_toggle_charts.clicked.connect(self._toggle_charts)
        main_layout.addWidget(self.btn_toggle_charts)

        self.chart_body = QFrame()
        self.chart_body.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        cb_layout = QVBoxLayout(self.chart_body)
        cb_layout.setContentsMargins(12, 10, 12, 10)

        self.chart_view = DividendChartsView(self)
        cb_layout.addWidget(self.chart_view)
        main_layout.addWidget(self.chart_body)

        # Collapsed by default as requested
        self.chart_body.setVisible(False)

        self.scroll_area.setWidget(content_widget)
        root_layout.addWidget(self.scroll_area)

    def _create_kpi_card(self, title: str, initial_val: str, text_color: str, bg_color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {bg_color}; border: 1px solid {text_color}33; border-radius: 8px; padding: 10px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {text_color}; letter-spacing: 0.5px;")
        layout.addWidget(lbl_title)

        lbl_val = QLabel(initial_val)
        lbl_val.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {text_color};")
        layout.addWidget(lbl_val)
        card.lbl_val = lbl_val  # type: ignore
        return card

    def _load_symbols_completer(self):
        symbols = get_all_symbols(self.db_conn)
        completer = QCompleter(symbols, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer_popup = QListView()
        completer.setPopup(completer_popup)
        self.txt_search.setCompleter(completer)

    def refresh_accounts(self):
        current = self.combo_account.currentData()
        self.combo_account.clear()
        self.combo_account.addItem("📊 Consolidated (All Accounts)", None)

        accounts = get_accounts(self.db_conn)
        for acc in accounts:
            label = f"{acc['user_name']} ({acc['account_id']})"
            self.combo_account.addItem(label, acc["account_id"])

        if current:
            idx = self.combo_account.findData(current)
            if idx >= 0:
                self.combo_account.setCurrentIndex(idx)

    def _on_fy_changed(self):
        data = self.combo_fy.currentData()
        if data == "CUSTOM":
            self.date_from.setEnabled(True)
            self.date_to.setEnabled(True)
        elif data is None:
            # All time
            self.date_from.setEnabled(False)
            self.date_to.setEnabled(False)
        else:
            # Preset FY tuple (start_str, end_str)
            self.date_from.setEnabled(False)
            self.date_to.setEnabled(False)
            s_dt = datetime.strptime(data[0], "%Y-%m-%d")
            e_dt = datetime.strptime(data[1], "%Y-%m-%d")
            self.date_from.setDate(QDate(s_dt.year, s_dt.month, s_dt.day))
            self.date_to.setDate(QDate(e_dt.year, e_dt.month, e_dt.day))

        self.refresh_data()

    def _on_custom_date_changed(self):
        if self.combo_fy.currentData() == "CUSTOM":
            self.refresh_data()

    def refresh_data(self):
        acc_id = self.combo_account.currentData()

        fy_data = self.combo_fy.currentData()
        start_date: Optional[str] = None
        end_date: Optional[str] = None

        if fy_data == "CUSTOM":
            start_date = self.date_from.date().toString("yyyy-MM-dd")
            end_date = self.date_to.date().toString("yyyy-MM-dd")
        elif fy_data is not None:
            start_date, end_date = fy_data

        dividends = get_dividends(
            conn=self.db_conn,
            account_id=acc_id,
            symbol=None,
            start_date=start_date,
            end_date=end_date,
        )
        summary = get_dividends_summary(
            conn=self.db_conn,
            account_id=acc_id,
            symbol=None,
            start_date=start_date,
            end_date=end_date,
        )

        # 1. Update KPI Cards
        self.card_total.lbl_val.setText(f"₹{summary['total_amount']:,.2f}")  # type: ignore
        self.card_count.lbl_val.setText(str(summary["payout_count"]))  # type: ignore
        self.card_companies.lbl_val.setText(str(summary["unique_companies"]))  # type: ignore

        top_payer = summary.get("top_payer", {})
        if top_payer and top_payer.get("symbol") != "N/A":
            self.card_top_payer.lbl_val.setText(f"{top_payer['symbol']} (₹{top_payer['amount']:,.0f})")  # type: ignore
        else:
            self.card_top_payer.lbl_val.setText("—")  # type: ignore

        # 2. Update Charts
        self._last_summary = summary
        self.chart_view.refresh_chart(summary)

        # 3. Update Table
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(dividends))

        for row_idx, d in enumerate(dividends):
            # Column 0: Date (dd-MM-yyyy format)
            raw_dt = str(d["dividend_date"])[:10]
            try:
                dt_obj = datetime.strptime(raw_dt, "%Y-%m-%d")
                formatted_date = dt_obj.strftime("%d-%m-%Y")
                sort_key = dt_obj.strftime("%Y%m%d")
            except Exception:
                formatted_date = raw_dt
                sort_key = raw_dt

            item_date = NumericTableWidgetItem(formatted_date)
            item_date.setData(Qt.UserRole, float(sort_key) if str(sort_key).isdigit() else 0.0)
            item_date.setData(Qt.UserRole + 1, d["dividend_id"])
            item_date.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 0, item_date)

            # Column 1: Account
            item_acc = QTableWidgetItem(d["user_name"])
            self.table.setItem(row_idx, 1, item_acc)

            # Column 2: Stock Symbol
            canonical_sym = d["canonical_symbol"]
            orig_sym = d["original_symbol"]
            item_sym = QTableWidgetItem(canonical_sym)
            if d.get("is_mapped"):
                item_sym.setToolTip(f"Mapped from legacy ticker: {orig_sym}")
                item_sym.setForeground(QColor("#2563EB"))
            self.table.setItem(row_idx, 2, item_sym)

            # Column 3: Shares Held
            qty = d["quantity"]
            qty_text = f"{qty:,}" if qty > 0 else "—"
            item_qty = NumericTableWidgetItem(qty_text)
            item_qty.setData(Qt.UserRole, float(qty))
            item_qty.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 3, item_qty)

            # Column 4: Dividend Per Share
            dps = d["dividend_per_share"]
            dps_text = f"₹{dps:.2f}" if dps > 0 else "—"
            item_dps = NumericTableWidgetItem(dps_text)
            item_dps.setData(Qt.UserRole, float(dps))
            item_dps.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, item_dps)

            # Column 5: Total Dividend (Bold Green)
            amt = d["amount"]
            item_amt = NumericTableWidgetItem(f"₹{amt:,.2f}")
            item_amt.setData(Qt.UserRole, float(amt))
            item_amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_amt.setFont(QFont(SYSTEM_FONT, 9, QFont.Bold))
            item_amt.setForeground(QColor("#059669"))
            self.table.setItem(row_idx, 5, item_amt)

            # Column 6: Remarks
            remarks_text = d.get("remarks") or ""
            item_rem = QTableWidgetItem(remarks_text)
            self.table.setItem(row_idx, 6, item_rem)

        self.table.setSortingEnabled(True)
        self._filter_ledger_table()

    def _filter_ledger_table(self):
        """Filter table rows by search query without re-querying the database."""
        query = self.txt_search.text().strip().lower()
        total_rows = self.table.rowCount()
        visible_count = 0

        for r in range(total_rows):
            acc_item = self.table.item(r, 1)
            sym_item = self.table.item(r, 2)
            rem_item = self.table.item(r, 6)

            acc = acc_item.text().lower() if acc_item else ""
            sym = sym_item.text().lower() if sym_item else ""
            rem = rem_item.text().lower() if rem_item else ""

            match = (not query) or (query in sym) or (query in acc) or (query in rem)
            self.table.setRowHidden(r, not match)
            if match:
                visible_count += 1

        if query:
            self.lbl_ledger_count.setText(f"Showing {visible_count} of {total_rows} payouts")
        else:
            self.lbl_ledger_count.setText(f"{total_rows} payouts" if total_rows > 0 else "")

    def _auto_fit_columns(self):
        """Auto-fit table column widths to content."""
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def _toggle_charts(self):
        """Toggle visibility of the collapsible charts & analytics section."""
        is_visible = self.chart_body.isVisible()
        new_state = not is_visible
        self.chart_body.setVisible(new_state)
        if new_state:
            self.btn_toggle_charts.setText("▼ Hide Visual Charts & Analytics")
            if hasattr(self, "_last_summary") and self._last_summary:
                self.chart_view.refresh_chart(self._last_summary)
        else:
            self.btn_toggle_charts.setText("▶ Show Visual Charts & Analytics (Donut, Bar & Trend Line)")

    def _open_manual_dividend(self):
        acc_id = self.combo_account.currentData()
        dlg = ManualDividendDialog(self.db_conn, default_account_id=acc_id, parent=self)
        dlg.dividend_saved.connect(self.refresh_data)
        dlg.exec()

    def _on_table_double_clicked(self):
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            div_id = self.table.item(curr_row, 0).data(Qt.UserRole + 1)
            if div_id:
                dlg = ManualDividendDialog(self.db_conn, editing_dividend_id=div_id, parent=self)
                dlg.dividend_saved.connect(self.refresh_data)
                dlg.exec()

    def _show_context_menu(self, pos):
        curr_row = self.table.currentRow()
        if curr_row < 0:
            return

        div_id = self.table.item(curr_row, 0).data(Qt.UserRole + 1)
        sym = self.table.item(curr_row, 2).text()
        amt = self.table.item(curr_row, 5).text()

        menu = QMenu(self)
        action_edit = menu.addAction(f"✏️ Edit Dividend ({sym} {amt})")
        action_del = menu.addAction("🗑️ Delete Dividend Record")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == action_edit:
            dlg = ManualDividendDialog(self.db_conn, editing_dividend_id=div_id, parent=self)
            dlg.dividend_saved.connect(self.refresh_data)
            dlg.exec()
        elif chosen == action_del:
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete this dividend of {amt} for {sym}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                delete_dividend(self.db_conn, div_id)
                self.refresh_data()

    def _export_excel(self):
        fpath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Dividends to Excel",
            str(Path.home() / f"Dividends_Statement_{datetime.now().strftime('%Y%m%d')}.xlsx"),
            "Excel Workbook (*.xlsx);;All Files (*.*)",
        )
        if not fpath:
            return

        acc_id = self.combo_account.currentData()
        sym_query = self.txt_search.text().strip().upper() or None
        fy_data = self.combo_fy.currentData()
        start_date = None
        end_date = None
        if fy_data == "CUSTOM":
            start_date = self.date_from.date().toString("yyyy-MM-dd")
            end_date = self.date_to.date().toString("yyyy-MM-dd")
        elif fy_data is not None:
            start_date, end_date = fy_data

        try:
            saved_path = export_dividends_to_excel(
                db_conn=self.db_conn,
                file_path=fpath,
                account_id=acc_id,
                start_date=start_date,
                end_date=end_date,
                symbol=sym_query,
            )
            QMessageBox.information(
                self,
                "Export Successful",
                f"Dividends statement exported successfully to:\n\n{saved_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export dividends:\n\n{str(e)}")
