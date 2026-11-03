"""Native, zero-dependency, high-DPI Qt Charts for Portfolio Tracker."""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
from PySide6.QtCore import QMargins, Qt, Signal
from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QPieSlice,
    QValueAxis,
)
from PySide6.QtGui import QColor, QCursor, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.ui.styles import SYSTEM_FONT, set_style_class

# Tailwind & modern financial palette for charts
CHART_COLORS = [
    QColor("#2563EB"),  # Blue 600
    QColor("#059669"),  # Emerald 600
    QColor("#D97706"),  # Amber 600
    QColor("#7C3AED"),  # Violet 600
    QColor("#DB2777"),  # Pink 600
    QColor("#0891B2"),  # Cyan 600
    QColor("#4F46E5"),  # Indigo 600
    QColor("#EA580C"),  # Orange 600
    QColor("#16A34A"),  # Green 600
    QColor("#9333EA"),  # Purple 600
    QColor("#10B981"),  # Emerald 500
    QColor("#3B82F6"),  # Blue 500
    QColor("#F59E0B"),  # Amber 500
    QColor("#8B5CF6"),  # Violet 500
    QColor("#EC4899"),  # Pink 500
    QColor("#06B6D4"),  # Cyan 500
    QColor("#F97316"),  # Orange 500
    QColor("#14B8A6"),  # Teal 500
    QColor("#6366F1"),  # Indigo 500
    QColor("#84CC16"),  # Lime 500
]


class HoldingsLegendItemWidget(QFrame):
    """Interactive multi-column legend item for asset allocation donut chart."""

    hovered = Signal(bool)

    def __init__(
        self,
        slice_obj: QPieSlice,
        symbol: str,
        cost: float,
        pct: float,
        color: QColor,
        parent=None,
    ):
        super().__init__(parent)
        self.slice_obj = slice_obj
        self.symbol = symbol
        self.cost = cost
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

        cost_str = f"₹{cost:,.0f}" if cost >= 1 else f"₹{cost:.2f}"
        lbl_text = QLabel(
            f"<span style='font-weight: 700; color: #1E293B;'>{symbol}</span> "
            f"<span style='color: #2563EB; font-weight: 600; font-size: 10px;'>{cost_str}</span>"
        )
        lbl_text.setStyleSheet("font-size: 11px;")
        layout.addWidget(lbl_text)
        layout.addStretch()

        self.setToolTip(f"<b>{symbol}</b><br/>Deployed: ₹{cost:,.2f}<br/>Allocation: {pct:.1f}%")

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


class NativeChartView(QWidget):
    """High-DPI native Qt Chart widget supporting Donut and Capital Recovery views with side legend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.holdings_df = pd.DataFrame()
        self.current_mode = "DONUT"
        self._empty_action_target = "DONUT"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Header controls
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(12, 10, 12, 4)
        header_layout.setSpacing(10)

        self.lbl_chart_title = QLabel("Portfolio Analytics")
        self.lbl_chart_title.setStyleSheet("font-weight: 700; color: #1E293B; font-size: 14px;")
        header_layout.addWidget(self.lbl_chart_title)
        header_layout.addStretch()

        # Top N selector for asset allocation & capital recovery
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
        self.combo_top_n.currentIndexChanged.connect(self.render_chart)
        header_layout.addWidget(self.combo_top_n)

        header_layout.addSpacing(6)

        # 1-Click Segmented Pill Tab Buttons
        tabs_layout = QHBoxLayout()
        tabs_layout.setSpacing(4)
        self.btn_tab_donut = QPushButton("🍩 Asset Allocation")
        self.btn_tab_bar = QPushButton("📊 Capital Recovery")

        for btn in (self.btn_tab_donut, self.btn_tab_bar):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            set_style_class(btn, "chart-tab")

        self.btn_tab_donut.clicked.connect(lambda: self.set_mode("DONUT"))
        self.btn_tab_bar.clicked.connect(lambda: self.set_mode("BAR"))

        tabs_layout.addWidget(self.btn_tab_donut)
        tabs_layout.addWidget(self.btn_tab_bar)
        header_layout.addLayout(tabs_layout)
        layout.addLayout(header_layout)

        # Internal Mode Selector helper (kept for programmatic compatibility, hidden from UI)
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Asset Allocation (Donut)", "DONUT")
        self.combo_mode.addItem("Capital Recovery (Bar)", "BAR")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.combo_mode.hide()

        # Interactive Inspection Banner
        banner_container = QHBoxLayout()
        banner_container.setContentsMargins(12, 0, 12, 4)
        self.lbl_hover_banner = QLabel("💡 Hover over any chart segment or bar to inspect details")
        self.lbl_hover_banner.setAlignment(Qt.AlignCenter)
        self._reset_hover_banner()
        banner_container.addWidget(self.lbl_hover_banner)
        layout.addLayout(banner_container)

        # Container with Stacked Layout (Chart View vs Empty State)
        self.stack = QStackedLayout()

        # 1. Native QChartView & Right-side Multi-Column Legend container
        self.chart_hlayout = QHBoxLayout()
        self.chart_hlayout.setContentsMargins(0, 0, 0, 0)
        self.chart_hlayout.setSpacing(12)

        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.setMargins(QMargins(10, 10, 10, 10))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setTheme(QChart.ChartThemeLight)
        self.chart.legend().setVisible(False)

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

        # Legend Header
        lhdr = QHBoxLayout()
        self.lbl_legend_title = QLabel("Asset Allocation Legend")
        self.lbl_legend_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155;")
        lhdr.addWidget(self.lbl_legend_title)
        lhdr.addStretch()
        self.lbl_legend_count = QLabel("")
        self.lbl_legend_count.setStyleSheet(
            "font-size: 11px; font-weight: 600; color: #64748B; background: #EDF2F7; border-radius: 4px; padding: 1px 6px;"
        )
        lhdr.addWidget(self.lbl_legend_count)
        lp_layout.addLayout(lhdr)

        # Scroll Area for legend items
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

        chart_wrapper = QWidget()
        cw_layout = QVBoxLayout(chart_wrapper)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.addLayout(self.chart_hlayout)
        self.stack.addWidget(chart_wrapper)

        # 2. Empty State Placeholder with Action Button
        self.empty_card = QFrame()
        self.empty_card.setStyleSheet("background: transparent;")
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(10)

        self.lbl_empty_icon = QLabel("📊")
        self.lbl_empty_icon.setStyleSheet("font-size: 40px; color: #94A3B8;")
        self.lbl_empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.lbl_empty_icon)

        self.lbl_empty_msg = QLabel("No holdings data available for chart")
        self.lbl_empty_msg.setStyleSheet("color: #64748B; font-size: 14px; font-weight: 500;")
        self.lbl_empty_msg.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.lbl_empty_msg)

        self.btn_empty_action = QPushButton("← Switch to Asset Allocation")
        set_style_class(self.btn_empty_action, "primary-btn")
        self.btn_empty_action.setCursor(Qt.PointingHandCursor)
        self.btn_empty_action.clicked.connect(self._on_empty_action_clicked)
        self.btn_empty_action.hide()
        empty_layout.addWidget(self.btn_empty_action, alignment=Qt.AlignCenter)

        self.stack.addWidget(self.empty_card)
        layout.addLayout(self.stack, 1)

        # Set initial visual state on segmented buttons
        self._sync_tabs_ui("DONUT")

    def _clear_legend_panel(self):
        while self.legend_grid.count():
            item = self.legend_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.lbl_legend_count.setText("")

    def _on_empty_action_clicked(self):
        """Handler for clicking the return action button on empty states."""
        self.set_mode(self._empty_action_target)

    def _sync_tabs_ui(self, mode: str):
        """Update segmented pill tab styling to match active mode."""
        set_style_class(self.btn_tab_donut, "chart-tab-active" if mode == "DONUT" else "chart-tab")
        set_style_class(self.btn_tab_bar, "chart-tab-active" if mode == "BAR" else "chart-tab")
        is_donut = (mode == "DONUT")
        self.legend_panel.setVisible(is_donut)

    def set_mode(self, mode: str):
        """Programmatically switch chart mode and synchronize segmented tabs and dropdown."""
        if not mode or mode == "REALIZED":
            mode = "DONUT"
        self.current_mode = mode
        self._sync_tabs_ui(mode)

        idx = self.combo_mode.findData(mode)
        if idx >= 0 and self.combo_mode.currentIndex() != idx:
            self.combo_mode.blockSignals(True)
            self.combo_mode.setCurrentIndex(idx)
            self.combo_mode.blockSignals(False)

        self.render_chart()

    def _reset_hover_banner(self):
        self.lbl_hover_banner.setText("💡 Hover over any chart segment or bar to inspect details")
        self.lbl_hover_banner.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500; color: #475569;"
        )

    def _on_mode_changed(self):
        mode = self.combo_mode.currentData()
        if mode:
            self.current_mode = mode
            self._sync_tabs_ui(mode)
            self.render_chart()

    def update_data(self, holdings_df: pd.DataFrame):
        """Update dataset and automatically refresh the chart."""
        self.holdings_df = holdings_df
        self._sync_tabs_ui(self.current_mode)
        self.render_chart()

    def render_chart(self):
        """Build and render the selected chart type using native QtCharts."""
        self._reset_hover_banner()
        QToolTip.hideText()
        self.chart.removeAllSeries()
        for ax in list(self.chart.axes()):
            self.chart.removeAxis(ax)

        self._clear_legend_panel()

        if self.holdings_df.empty:
            self.legend_panel.setVisible(False)
            self._show_empty("Import tradebook or add manual trades to view analytics.")
            return

        if self.current_mode == "DONUT":
            self.legend_panel.setVisible(True)
            self._render_donut()
        elif self.current_mode == "BAR":
            self.legend_panel.setVisible(False)
            self._render_capital_recovery_bar()

    def _show_empty(self, message: str, action_text: Optional[str] = None, action_target: Optional[str] = None):
        self.lbl_empty_msg.setText(message)
        if action_text and action_target:
            self.btn_empty_action.setText(action_text)
            self._empty_action_target = action_target
            self.btn_empty_action.show()
        else:
            self.btn_empty_action.hide()
        self.stack.setCurrentIndex(1)

    def _on_slice_hovered(self, slice_obj: QPieSlice, sym: str, c: float, p: float, state: bool):
        slice_obj.setExploded(state)

        legend_w = getattr(slice_obj, "legend_widget", None)
        if legend_w:
            legend_w.set_highlighted(state)

        if state:
            self.lbl_hover_banner.setText(
                f"📌 <b>{sym}</b> &nbsp;•&nbsp; Deployed Capital: <b>₹{c:,.2f}</b> &nbsp;•&nbsp; Portfolio Allocation: <b>{p:.1f}%</b>"
            )
            self.lbl_hover_banner.setStyleSheet(
                "background-color: #EFF6FF; border: 1px solid #93C5FD; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500; color: #1D4ED8;"
            )
            tip_html = f"<b>{sym}</b><br/>Deployed: ₹{c:,.2f}<br/>Allocation: {p:.1f}%"
            QToolTip.showText(QCursor.pos(), tip_html, self.chart_view)
        else:
            self._reset_hover_banner()
            QToolTip.hideText()

    def _render_donut(self):
        active_mask = (self.holdings_df["is_closed"] == False) & (self.holdings_df["is_anomalous"] == False)
        active_df = self.holdings_df[active_mask].copy()

        if active_df.empty or active_df["total_buy_cost"].sum() <= 0:
            self._clear_legend_panel()
            self.legend_panel.setVisible(False)
            self._show_empty("No active holdings found for this cutoff date.")
            return

        self._clear_legend_panel()
        self.legend_panel.setVisible(True)

        # Sort descending by total_buy_cost
        active_df = active_df.sort_values(by="total_buy_cost", ascending=False)
        total_cost = active_df["total_buy_cost"].sum()

        top_n = self.combo_top_n.currentData() if self.combo_top_n else 10
        if not top_n:
            top_n = 10

        top_df = active_df.head(top_n)
        other_df = active_df.iloc[top_n:]
        other_cost = float(other_df["total_buy_cost"].sum()) if len(other_df) > 0 else 0.0

        total_slices = len(top_df) + (1 if other_cost > 0 else 0)
        num_cols = 3 if total_slices > 24 else 2
        self.lbl_legend_count.setText(f"{total_slices} stocks")

        series = QPieSeries()
        series.setHoleSize(0.48)
        series.setPieSize(0.70)

        legend_items = []

        for idx, (_, row) in enumerate(top_df.iterrows()):
            cost = float(row["total_buy_cost"])
            pct = (cost / total_cost) * 100.0 if total_cost > 0 else 0.0
            label = f"{row['symbol']} ({pct:.1f}%)"
            pie_slice = series.append(label, cost)
            color = CHART_COLORS[idx % len(CHART_COLORS)]
            pie_slice.setColor(color)
            pie_slice.setBorderColor(QColor("#FFFFFF"))
            pie_slice.setBorderWidth(2)

            pie_slice.hovered.connect(
                lambda state, s=pie_slice, sym=row["symbol"], c=cost, p=pct: self._on_slice_hovered(s, sym, c, p, state)
            )
            legend_items.append((pie_slice, row["symbol"], cost, pct, color))

        if other_cost > 0:
            other_count = len(other_df)
            pct = (other_cost / total_cost) * 100.0 if total_cost > 0 else 0.0
            label = f"Other ({other_count} stocks: ₹{other_cost:,.0f})"
            pie_slice = series.append(label, other_cost)
            color = QColor("#94A3B8")
            pie_slice.setColor(color)
            pie_slice.setBorderColor(QColor("#FFFFFF"))
            pie_slice.setBorderWidth(2)

            sym_name = f"Other ({other_count} stocks)"
            pie_slice.hovered.connect(
                lambda state, s=pie_slice, sym=sym_name, c=other_cost, p=pct: self._on_slice_hovered(s, sym, c, p, state)
            )
            legend_items.append((pie_slice, sym_name, other_cost, pct, color))

        self.chart.addSeries(series)
        self.chart.setTitle("Asset Allocation by Deployed Capital")
        self.chart.setTitleFont(QFont(SYSTEM_FONT, 12, QFont.Bold))
        self.chart.legend().setVisible(False)

        # Populate right-side multi-column legend panel
        for idx, (slice_, symbol, cost, pct, color) in enumerate(legend_items):
            row = idx // num_cols
            col = idx % num_cols
            item_widget = HoldingsLegendItemWidget(slice_, symbol, cost, pct, color, self.legend_content)
            slice_.legend_widget = item_widget  # type: ignore
            item_widget.hovered.connect(
                lambda state, s=slice_, sym=symbol, c=cost, p=pct: self._on_slice_hovered(s, sym, c, p, state)
            )
            self.legend_grid.addWidget(item_widget, row, col)

        self.stack.setCurrentIndex(0)

    def _render_capital_recovery_bar(self):
        self._clear_legend_panel()
        self.legend_panel.setVisible(False)

        active_mask = (self.holdings_df["is_closed"] == False) & (self.holdings_df["is_anomalous"] == False)
        active_df = self.holdings_df[active_mask].copy()

        if active_df.empty:
            self._show_empty(
                "No active holdings found for capital recovery chart.",
                action_text="🍩 View Asset Allocation",
                action_target="DONUT",
            )
            return

        top_n = self.combo_top_n.currentData() if self.combo_top_n else 10
        if not top_n:
            top_n = 10

        sort_col = "actual_exposure" if "actual_exposure" in active_df.columns else "total_buy_cost"
        active_df = active_df.sort_values(by=sort_col, ascending=False).head(top_n)

        set_cost = QBarSet("Actual Exposure")
        set_cost.setColor(QColor("#94A3B8"))
        set_cost.setBorderColor(QColor("#FFFFFF"))

        set_risk = QBarSet("Net Exposure")
        set_risk.setColor(QColor("#2563EB"))
        set_risk.setBorderColor(QColor("#FFFFFF"))

        categories: List[str] = []
        actual_costs: List[float] = []
        net_risks: List[float] = []
        booked_pnls: List[float] = []
        max_val = 0.0

        for _, row in active_df.iterrows():
            sym_str = str(row["symbol"])
            cost = float(row.get("actual_exposure", row["total_buy_cost"]))
            risk = float(row.get("net_exposure", max(0.0, float(row["net_capital_at_risk"]))))
            pnl = float(row.get("booked_pnl", row.get("realized_pnl", 0.0)))
            categories.append(sym_str)
            actual_costs.append(cost)
            net_risks.append(risk)
            booked_pnls.append(pnl)
            set_cost.append(cost)
            set_risk.append(risk)
            max_val = max(max_val, cost, risk)

        # Hover inspection handlers for bars
        def on_bar_hovered(hovered: bool, idx: int):
            if 0 <= idx < len(categories):
                sym = categories[idx]
                cost = actual_costs[idx]
                risk = net_risks[idx]
                pnl = booked_pnls[idx]
                if hovered:
                    self.lbl_hover_banner.setText(
                        f"📌 <b>{sym}</b> &nbsp;•&nbsp; Actual Exposure: <b>₹{cost:,.2f}</b> &nbsp;•&nbsp; "
                        f"Booked P&L: <b>₹{pnl:,.2f}</b> &nbsp;•&nbsp; Net Exposure: <b>₹{risk:,.2f}</b>"
                    )
                    self.lbl_hover_banner.setStyleSheet(
                        "background-color: #EFF6FF; border: 1px solid #93C5FD; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500; color: #1D4ED8;"
                    )
                    tip_html = (
                        f"<b>{sym}</b><br/>"
                        f"Actual Exposure: ₹{cost:,.2f}<br/>"
                        f"Booked P&L: ₹{pnl:,.2f}<br/>"
                        f"Net Exposure: ₹{risk:,.2f}"
                    )
                    QToolTip.showText(QCursor.pos(), tip_html, self.chart_view)
                else:
                    self._reset_hover_banner()
                    QToolTip.hideText()

        set_cost.hovered.connect(on_bar_hovered)
        set_risk.hovered.connect(on_bar_hovered)

        series = QBarSeries()
        series.append(set_cost)
        series.append(set_risk)
        self.chart.addSeries(series)

        # Axes
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsAngle(-30)
        axis_x.setLabelsFont(QFont(SYSTEM_FONT, 10))
        self.chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.15 if max_val > 0 else 1000)
        axis_y.setLabelFormat("%d")
        axis_y.setTitleText("Amount (₹)")
        axis_y.setTitleFont(QFont(SYSTEM_FONT, 10, QFont.Bold))
        axis_y.setLabelsFont(QFont(SYSTEM_FONT, 10))
        self.chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        self.chart.setTitle("Capital Exposure: Actual Exposure vs. Net Exposure")
        self.chart.setTitleFont(QFont(SYSTEM_FONT, 12, QFont.Bold))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)

        self.stack.setCurrentIndex(0)
