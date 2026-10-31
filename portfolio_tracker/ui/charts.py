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
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStackedLayout,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from portfolio_tracker.ui.styles import SYSTEM_FONT, set_style_class

# Tailwind-inspired color palette for charts
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
]


class NativeChartView(QWidget):
    """High-DPI native Qt Chart widget supporting Donut, Capital Recovery, and Realized P&L views."""

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

        # 1-Click Segmented Pill Tab Buttons
        tabs_layout = QHBoxLayout()
        tabs_layout.setSpacing(4)
        self.btn_tab_donut = QPushButton("🍩 Asset Allocation")
        self.btn_tab_bar = QPushButton("📊 Capital Recovery")
        self.btn_tab_realized = QPushButton("📈 Realized Profit")

        for btn in (self.btn_tab_donut, self.btn_tab_bar, self.btn_tab_realized):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            set_style_class(btn, "chart-tab")

        self.btn_tab_donut.clicked.connect(lambda: self.set_mode("DONUT"))
        self.btn_tab_bar.clicked.connect(lambda: self.set_mode("BAR"))
        self.btn_tab_realized.clicked.connect(lambda: self.set_mode("REALIZED"))

        tabs_layout.addWidget(self.btn_tab_donut)
        tabs_layout.addWidget(self.btn_tab_bar)
        tabs_layout.addWidget(self.btn_tab_realized)
        header_layout.addLayout(tabs_layout)
        layout.addLayout(header_layout)

        # Internal Mode Selector helper (kept for programmatic compatibility, hidden from UI)
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Asset Allocation (Donut)", "DONUT")
        self.combo_mode.addItem("Capital Recovery (Bar)", "BAR")
        self.combo_mode.addItem("Realized Profit (Closed Stocks)", "REALIZED")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.combo_mode.hide()

        # Interactive Inspection Banner (guaranteed 100% visible, never clipped)
        banner_container = QHBoxLayout()
        banner_container.setContentsMargins(12, 0, 12, 4)
        self.lbl_hover_banner = QLabel("💡 Hover over any chart segment or bar to inspect details")
        self.lbl_hover_banner.setAlignment(Qt.AlignCenter)
        self._reset_hover_banner()
        banner_container.addWidget(self.lbl_hover_banner)
        layout.addLayout(banner_container)

        # Container with Stacked Layout (Chart View vs Empty State)
        self.stack = QStackedLayout()

        # 1. Native QChartView
        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.setMargins(QMargins(10, 10, 10, 10))
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.setTheme(QChart.ChartThemeLight)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setStyleSheet("background: transparent; border: none;")
        self.stack.addWidget(self.chart_view)

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

    def _on_empty_action_clicked(self):
        """Handler for clicking the return action button on empty states."""
        self.set_mode(self._empty_action_target)

    def _sync_tabs_ui(self, mode: str):
        """Update segmented pill tab styling to match active mode."""
        set_style_class(self.btn_tab_donut, "chart-tab-active" if mode == "DONUT" else "chart-tab")
        set_style_class(self.btn_tab_bar, "chart-tab-active" if mode == "BAR" else "chart-tab")
        set_style_class(self.btn_tab_realized, "chart-tab-active" if mode == "REALIZED" else "chart-tab")

    def set_mode(self, mode: str):
        """Programmatically switch chart mode and synchronize segmented tabs and dropdown."""
        if not mode:
            return
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
        # If there are no active holdings but there are closed positions, default to REALIZED mode
        active_count = len(holdings_df[(holdings_df["is_closed"] == False) & (holdings_df["is_anomalous"] == False)])
        closed_count = len(holdings_df[holdings_df["is_closed"] == True])

        if active_count == 0 and closed_count > 0 and self.current_mode == "DONUT":
            self.set_mode("REALIZED")
            return

        self._sync_tabs_ui(self.current_mode)
        self.render_chart()

    def render_chart(self):
        """Build and render the selected chart type using native QtCharts."""
        self._reset_hover_banner()
        QToolTip.hideText()
        self.chart.removeAllSeries()
        for ax in self.chart.axes():
            self.chart.removeAxis(ax)

        if self.holdings_df.empty:
            self._show_empty("Import tradebook or add manual trades to view analytics.")
            return

        if self.current_mode == "DONUT":
            self._render_donut()
        elif self.current_mode == "BAR":
            self._render_capital_recovery_bar()
        elif self.current_mode == "REALIZED":
            self._render_realized_profit_bar()

    def _show_empty(self, message: str, action_text: Optional[str] = None, action_target: Optional[str] = None):
        self.lbl_empty_msg.setText(message)
        if action_text and action_target:
            self.btn_empty_action.setText(action_text)
            self._empty_action_target = action_target
            self.btn_empty_action.show()
        else:
            self.btn_empty_action.hide()
        self.stack.setCurrentIndex(1)

    def _render_donut(self):
        active_mask = (self.holdings_df["is_closed"] == False) & (self.holdings_df["is_anomalous"] == False)
        active_df = self.holdings_df[active_mask].copy()

        if active_df.empty or active_df["total_buy_cost"].sum() <= 0:
            closed_count = len(self.holdings_df[self.holdings_df["is_closed"] == True])
            if closed_count > 0:
                self._show_empty(
                    "All positions in this view are closed.\nSwitch to Realized Profit to inspect performance.",
                    action_text="📈 View Realized Profit",
                    action_target="REALIZED",
                )
            else:
                self._show_empty("No active holdings found for this cutoff date.")
            return

        # Sort and take top 10 for clean readability
        active_df = active_df.sort_values(by="total_buy_cost", ascending=False)
        total_cost = active_df["total_buy_cost"].sum()

        series = QPieSeries()
        series.setHoleSize(0.48)
        series.setPieSize(0.70)

        for idx, (_, row) in enumerate(active_df.head(10).iterrows()):
            cost = float(row["total_buy_cost"])
            pct = (cost / total_cost) * 100.0 if total_cost > 0 else 0.0
            label = f"{row['symbol']} ({pct:.1f}%)"
            pie_slice = series.append(label, cost)
            pie_slice.setColor(CHART_COLORS[idx % len(CHART_COLORS)])
            pie_slice.setBorderColor(QColor("#FFFFFF"))
            pie_slice.setBorderWidth(2)

            # Interactive hover explosion + guaranteed visible header banner + top-level tooltip
            def make_hover_handler(s: QPieSlice, sym: str, c: float, p: float):
                def on_hover(hovered: bool):
                    s.setExploded(hovered)
                    if hovered:
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
                return on_hover

            pie_slice.hovered.connect(make_hover_handler(pie_slice, row["symbol"], cost, pct))

        self.chart.addSeries(series)
        self.chart.setTitle("Asset Allocation by Deployed Capital")
        self.chart.setTitleFont(QFont(SYSTEM_FONT, 12, QFont.Bold))
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        self.chart.legend().setFont(QFont(SYSTEM_FONT, 10))

        self.stack.setCurrentIndex(0)

    def _render_capital_recovery_bar(self):
        active_mask = (self.holdings_df["is_closed"] == False) & (self.holdings_df["is_anomalous"] == False)
        active_df = self.holdings_df[active_mask].copy()

        if active_df.empty:
            closed_count = len(self.holdings_df[self.holdings_df["is_closed"] == True])
            if closed_count > 0:
                self._show_empty(
                    "No active holdings for capital recovery.\n(All positions are closed).",
                    action_text="📈 View Realized Profit",
                    action_target="REALIZED",
                )
            else:
                self._show_empty(
                    "No active holdings found for capital recovery chart.",
                    action_text="🍩 View Asset Allocation",
                    action_target="DONUT",
                )
            return

        sort_col = "actual_exposure" if "actual_exposure" in active_df.columns else "total_buy_cost"
        active_df = active_df.sort_values(by=sort_col, ascending=False).head(8)

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

    def _render_realized_profit_bar(self):
        closed_df = self.holdings_df[self.holdings_df["is_closed"] == True].copy()
        if closed_df.empty:
            self._show_empty(
                "No closed/exited positions found in this cutoff date.\n(All positions are currently active).",
                action_text="🍩 View Asset Allocation",
                action_target="DONUT",
            )
            return

        closed_df = closed_df.sort_values(by="realized_pnl", ascending=False).head(8)

        set_pnl = QBarSet("Realized Profit / Loss")
        set_pnl.setColor(QColor("#059669"))
        set_pnl.setBorderColor(QColor("#FFFFFF"))

        categories = []
        pnls = []
        max_val = 0.0
        min_val = 0.0

        for _, row in closed_df.iterrows():
            categories.append(str(row["symbol"]))
            pnl = float(row["realized_pnl"])
            pnls.append(pnl)
            set_pnl.append(pnl)
            max_val = max(max_val, pnl)
            min_val = min(min_val, pnl)

        # Hover inspection handlers for realized profit bars
        def on_pnl_hovered(hovered: bool, idx: int):
            if 0 <= idx < len(categories):
                sym = categories[idx]
                pnl = pnls[idx]
                status = "Profit" if pnl >= 0 else "Loss"
                if hovered:
                    self.lbl_hover_banner.setText(
                        f"📌 <b>{sym}</b> &nbsp;•&nbsp; Realized {status}: <b>₹{abs(pnl):,.2f}</b>"
                    )
                    if pnl >= 0:
                        self.lbl_hover_banner.setStyleSheet(
                            "background-color: #F0FDF4; border: 1px solid #86EFAC; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500; color: #15803D;"
                        )
                    else:
                        self.lbl_hover_banner.setStyleSheet(
                            "background-color: #FEF2F2; border: 1px solid #FCA5A5; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 500; color: #DC2626;"
                        )
                    tip_html = f"<b>{sym} (Closed Position)</b><br/>Realized {status}: ₹{abs(pnl):,.2f}"
                    QToolTip.showText(QCursor.pos(), tip_html, self.chart_view)
                else:
                    self._reset_hover_banner()
                    QToolTip.hideText()

        set_pnl.hovered.connect(on_pnl_hovered)

        series = QBarSeries()
        series.append(set_pnl)
        self.chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsAngle(-30)
        axis_x.setLabelsFont(QFont(SYSTEM_FONT, 10))
        self.chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        top_range = max_val * 1.2 if max_val > 0 else 1000
        bottom_range = min_val * 1.2 if min_val < 0 else 0
        axis_y.setRange(bottom_range, top_range)
        axis_y.setLabelFormat("%d")
        axis_y.setTitleText("Profit (₹)")
        axis_y.setTitleFont(QFont(SYSTEM_FONT, 10, QFont.Bold))
        axis_y.setLabelsFont(QFont(SYSTEM_FONT, 10))
        self.chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        self.chart.setTitle("Realized Profit & Loss by Closed Position")
        self.chart.setTitleFont(QFont(SYSTEM_FONT, 12, QFont.Bold))
        self.chart.legend().setVisible(False)

        self.stack.setCurrentIndex(0)
