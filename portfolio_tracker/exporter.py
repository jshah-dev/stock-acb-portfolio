"""Multi-tab formatted Excel workbook generator using openpyxl."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, List, Optional, Union

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from portfolio_tracker.db import get_accounts, get_pnl_adjustments
from portfolio_tracker.engine import get_holdings

# Style definitions (Tailwind Slate palette)
FONT_FAMILY = "Segoe UI"
HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")  # Slate 800
HEADER_FONT = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name=FONT_FAMILY, size=14, bold=True, color="0F172A")
SUBTITLE_FONT = Font(name=FONT_FAMILY, size=10, italic=True, color="64748B")

DATA_FONT = Font(name=FONT_FAMILY, size=11, color="1E293B")
MUTED_FONT = Font(name=FONT_FAMILY, size=10, italic=True, color="64748B")
BOLD_DATA_FONT = Font(name=FONT_FAMILY, size=11, bold=True, color="0F172A")

RISK_FREE_FILL = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")  # Emerald 100
ANOMALY_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")    # Amber 100
CLOSED_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")     # Slate 100

THIN_BORDER_SIDE = Side(border_style="thin", color="CBD5E1")
DATA_BORDER = Border(
    left=THIN_BORDER_SIDE, right=THIN_BORDER_SIDE, top=THIN_BORDER_SIDE, bottom=THIN_BORDER_SIDE
)

CURRENCY_FORMAT = "₹#,##0.00"
INTEGER_FORMAT = "#,##0"


def _style_table(ws: openpyxl.worksheet.worksheet.Worksheet, start_row: int) -> None:
    """Apply styling, borders, formatting, and auto-column width adjustments."""
    max_col = ws.max_column
    max_row = ws.max_row

    # Style Header Row
    for col in range(1, max_col + 1):
        cell = ws.cell(row=start_row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = DATA_BORDER
    ws.row_dimensions[start_row].height = 28

    # Style Data Rows
    for row in range(start_row + 1, max_row + 1):
        ws.row_dimensions[row].height = 22
        status_val = str(ws.cell(row=row, column=2).value or "")

        row_fill = None
        if "RISK_FREE" in status_val:
            row_fill = RISK_FREE_FILL
        elif "ANOMALOUS" in status_val:
            row_fill = ANOMALY_FILL
        elif "CLOSED" in status_val:
            row_fill = CLOSED_FILL

        for col in range(1, max_col + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = DATA_BORDER
            if row_fill:
                cell.fill = row_fill

    # Auto-adjust column widths with padding
    for col in range(1, max_col + 1):
        col_letter = get_column_letter(col)
        max_len = 0
        for row in range(start_row, max_row + 1):
            val = ws.cell(row=row, column=col).value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col_letter].width = max(max_len + 5, 14)

    # Freeze header
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)


def export_portfolio_to_excel(
    db_conn: sqlite3.Connection,
    file_path: Union[str, Path],
    cutoff_date: Optional[Union[str, date, datetime]] = None,
    include_closed: bool = True,
) -> Path:
    """Generate a multi-tab styled Excel workbook (.xlsx) with Consolidated Family and Account breakdowns.

    Args:
        db_conn: Active SQLite connection.
        file_path: Target .xlsx filepath.
        cutoff_date: Optional historical cutoff date.
        include_closed: Whether to include closed positions.

    Returns:
        Resolved Path to the created workbook.
    """
    target = Path(file_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()

    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cutoff_display = str(cutoff_date) if cutoff_date else "All Dates (Latest)"

    # ==========================================
    # Tab 1: Consolidated Family View
    # ==========================================
    ws_fam = wb.active
    ws_fam.title = "Consolidated Family View"
    ws_fam.views.sheetView[0].showGridLines = True

    # Title block
    ws_fam.cell(row=1, column=1, value="Stock ACB Portfolio Tracker - Consolidated Family View").font = TITLE_FONT
    ws_fam.cell(row=2, column=1, value=f"Generated: {timestamp_str} | Cutoff Date: {cutoff_display}").font = SUBTITLE_FONT

    fam_headers = [
        "Stock Symbol",
        "Shares Held",
        "Total Buy Cost (₹)",
        "Total Proceeds (₹)",
        "Actual Exposure (₹)",
        "Booked P&L (₹)",
        "Net Exposure (₹)",
        "Effective Avg Price (₹)",
        "Status / Flag",
    ]

    header_row_fam = 4
    for c_idx, h_text in enumerate(fam_headers, start=1):
        ws_fam.cell(row=header_row_fam, column=c_idx, value=h_text)

    df_family = get_holdings(db_conn, cutoff_date=cutoff_date, account_id=None, include_closed=include_closed)

    current_row = header_row_fam + 1
    for _, row in df_family.iterrows():
        # Stock Symbol (with mapping indicator if applicable)
        sym_val = str(row["symbol"])
        mapped = row.get("mapped_sources", [])
        if mapped and len(mapped) > 0:
            sym_val = f"{sym_val} (mapped from {', '.join(mapped)})"

        ws_fam.cell(row=current_row, column=1, value=sym_val).font = BOLD_DATA_FONT
        ws_fam.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")

        # Total Shares Held
        c_qty = ws_fam.cell(row=current_row, column=2, value=row["net_qty"])
        c_qty.number_format = INTEGER_FORMAT
        c_qty.alignment = Alignment(horizontal="right", vertical="center")

        # Total Buy Cost
        c_cost = ws_fam.cell(row=current_row, column=3, value=row["total_buy_cost"])
        c_cost.number_format = CURRENCY_FORMAT
        c_cost.alignment = Alignment(horizontal="right", vertical="center")

        # Total Proceeds
        c_proc = ws_fam.cell(row=current_row, column=4, value=row["total_proceeds"])
        c_proc.number_format = CURRENCY_FORMAT
        c_proc.alignment = Alignment(horizontal="right", vertical="center")

        # Actual Exposure
        c_actual = ws_fam.cell(row=current_row, column=5, value=row.get("actual_exposure", 0.0))
        c_actual.number_format = CURRENCY_FORMAT
        c_actual.alignment = Alignment(horizontal="right", vertical="center")

        # Booked P&L
        c_pnl = ws_fam.cell(row=current_row, column=6, value=row.get("booked_pnl", row.get("realized_pnl", 0.0)))
        c_pnl.number_format = CURRENCY_FORMAT
        c_pnl.alignment = Alignment(horizontal="right", vertical="center")

        # Net Exposure
        c_net = ws_fam.cell(row=current_row, column=7, value=row.get("net_exposure", 0.0))
        c_net.number_format = CURRENCY_FORMAT
        c_net.alignment = Alignment(horizontal="right", vertical="center")

        # Effective Avg Price
        eff_val = row.get("effective_avg")
        eff_num = float(eff_val) if eff_val is not None and not pd.isna(eff_val) else 0.0
        c_eff = ws_fam.cell(row=current_row, column=8, value=eff_num)
        c_eff.number_format = CURRENCY_FORMAT
        c_eff.alignment = Alignment(horizontal="right", vertical="center")

        # Status / Flag
        status_str = row["status"]
        if row["is_house_money"]:
            status_str = "RISK_FREE (House Money)"
        elif row["is_anomalous"]:
            status_str = "⚠️ ANOMALOUS (Sell > Buy)"
        elif row["is_closed"]:
            status_str = "CLOSED"

        ws_fam.cell(row=current_row, column=9, value=status_str).alignment = Alignment(horizontal="center", vertical="center")

        current_row += 1

    _style_table(ws_fam, start_row=header_row_fam)

    # ==========================================
    # Tab 2: Account-Wise Breakdown
    # ==========================================
    ws_acc = wb.create_sheet(title="Account-Wise Breakdown")
    ws_acc.views.sheetView[0].showGridLines = True

    ws_acc.cell(row=1, column=1, value="Stock ACB Portfolio Tracker - Account-Wise Breakdown").font = TITLE_FONT
    ws_acc.cell(row=2, column=1, value=f"Generated: {timestamp_str} | Cutoff Date: {cutoff_display}").font = SUBTITLE_FONT

    acc_headers = [
        "Account Name",
        "Stock Symbol",
        "Shares Held",
        "Total Buy Cost (₹)",
        "Total Proceeds (₹)",
        "Actual Exposure (₹)",
        "Booked P&L (₹)",
        "Net Exposure (₹)",
        "Effective Avg Price (₹)",
        "Status / Flags",
    ]

    header_row_acc = 4
    for c_idx, h_text in enumerate(acc_headers, start=1):
        ws_acc.cell(row=header_row_acc, column=c_idx, value=h_text)

    accounts = get_accounts(db_conn)
    current_row_acc = header_row_acc + 1

    for acc in accounts:
        acc_id = acc["account_id"]
        user_name = acc["user_name"]
        df_single = get_holdings(db_conn, cutoff_date=cutoff_date, account_id=acc_id, include_closed=include_closed)

        for _, row in df_single.iterrows():
            ws_acc.cell(row=current_row_acc, column=1, value=user_name).alignment = Alignment(horizontal="left", vertical="center")

            # Stock Symbol
            sym_val = str(row["symbol"])
            mapped = row.get("mapped_sources", [])
            if mapped and len(mapped) > 0:
                sym_val = f"{sym_val} (mapped from {', '.join(mapped)})"

            ws_acc.cell(row=current_row_acc, column=2, value=sym_val).font = BOLD_DATA_FONT
            ws_acc.cell(row=current_row_acc, column=2).alignment = Alignment(horizontal="left", vertical="center")

            # Shares Held
            c_qty = ws_acc.cell(row=current_row_acc, column=3, value=row["net_qty"])
            c_qty.number_format = INTEGER_FORMAT
            c_qty.alignment = Alignment(horizontal="right", vertical="center")

            # Total Buy Cost
            c_cost = ws_acc.cell(row=current_row_acc, column=4, value=row["total_buy_cost"])
            c_cost.number_format = CURRENCY_FORMAT
            c_cost.alignment = Alignment(horizontal="right", vertical="center")

            # Proceeds
            c_proc = ws_acc.cell(row=current_row_acc, column=5, value=row["total_proceeds"])
            c_proc.number_format = CURRENCY_FORMAT
            c_proc.alignment = Alignment(horizontal="right", vertical="center")

            # Actual Exposure
            c_act = ws_acc.cell(row=current_row_acc, column=6, value=row.get("actual_exposure", 0.0))
            c_act.number_format = CURRENCY_FORMAT
            c_act.alignment = Alignment(horizontal="right", vertical="center")

            # Booked P&L
            c_pnl = ws_acc.cell(row=current_row_acc, column=7, value=row.get("booked_pnl", row.get("realized_pnl", 0.0)))
            c_pnl.number_format = CURRENCY_FORMAT
            c_pnl.alignment = Alignment(horizontal="right", vertical="center")

            # Net Exposure
            c_risk = ws_acc.cell(row=current_row_acc, column=8, value=row.get("net_exposure", 0.0))
            c_risk.number_format = CURRENCY_FORMAT
            c_risk.alignment = Alignment(horizontal="right", vertical="center")

            # Effective Avg Price
            eff_val = row.get("effective_avg")
            eff_num = float(eff_val) if eff_val is not None and not pd.isna(eff_val) else 0.0
            c_eff = ws_acc.cell(row=current_row_acc, column=9, value=eff_num)
            c_eff.number_format = CURRENCY_FORMAT
            c_eff.alignment = Alignment(horizontal="right", vertical="center")

            # Flags
            flag_str = "⚠️ Sell without Buy in this account" if row["is_anomalous"] else ("Risk Free" if row["is_house_money"] else ("Closed" if row["is_closed"] else "Active"))
            ws_acc.cell(row=current_row_acc, column=10, value=flag_str).alignment = Alignment(horizontal="center", vertical="center")

            current_row_acc += 1

    _style_table(ws_acc, start_row=header_row_acc)

    # ==========================================
    # Tab 3: P&L Adjustments & Brokerage Ledger
    # ==========================================
    ws_adj = wb.create_sheet(title="P&L Adjustments & Brokerage")
    ws_adj.views.sheetView[0].showGridLines = True

    ws_adj.cell(row=1, column=1, value="Stock ACB Portfolio Tracker - P&L Adjustments & Brokerage Ledger").font = TITLE_FONT
    ws_adj.cell(row=2, column=1, value=f"Generated: {timestamp_str} | Cutoff Date: {cutoff_display}").font = SUBTITLE_FONT

    adj_headers = [
        "Adjustment ID",
        "Account",
        "Stock Symbol",
        "Category",
        "Direction",
        "Amount (₹)",
        "Effective Date",
        "Notes",
    ]

    header_row_adj = 4
    for c_idx, h_text in enumerate(adj_headers, start=1):
        ws_adj.cell(row=header_row_adj, column=c_idx, value=h_text)

    try:
        adjs = get_pnl_adjustments(db_conn, cutoff_date=cutoff_date)
    except Exception:
        adjs = []

    current_row_adj = header_row_adj + 1
    for a in adjs:
        # ID
        ws_adj.cell(row=current_row_adj, column=1, value=a["adjustment_id"]).alignment = Alignment(horizontal="left", vertical="center")

        # Account
        ws_adj.cell(row=current_row_adj, column=2, value=a["user_name"]).alignment = Alignment(horizontal="left", vertical="center")

        # Symbol / Scope
        sym_scope = str(a.get("canonical_symbol") or a.get("symbol") or "—")
        ws_adj.cell(row=current_row_adj, column=3, value=sym_scope).alignment = Alignment(horizontal="left", vertical="center")

        # Category
        cat_str = str(a["category"]).replace("_", " ").title()
        ws_adj.cell(row=current_row_adj, column=4, value=cat_str).alignment = Alignment(horizontal="left", vertical="center")

        # Direction
        dir_str = "+ PROFIT" if a["direction"] == "PROFIT" else "- LOSS / CHG"
        c_dir = ws_adj.cell(row=current_row_adj, column=5, value=dir_str)
        c_dir.alignment = Alignment(horizontal="center", vertical="center")

        # Amount
        amt_val = float(a["amount"])
        signed_amt = amt_val if a["direction"] == "PROFIT" else -amt_val
        c_amt = ws_adj.cell(row=current_row_adj, column=6, value=signed_amt)
        c_amt.number_format = CURRENCY_FORMAT
        c_amt.alignment = Alignment(horizontal="right", vertical="center")

        # Date
        ws_adj.cell(row=current_row_adj, column=7, value=str(a["adjustment_date"])[:19]).alignment = Alignment(horizontal="center", vertical="center")

        # Notes
        ws_adj.cell(row=current_row_adj, column=8, value=str(a.get("notes") or "")).alignment = Alignment(horizontal="left", vertical="center")

        current_row_adj += 1

    _style_table(ws_adj, start_row=header_row_adj)

    wb.save(str(target))
    return target

