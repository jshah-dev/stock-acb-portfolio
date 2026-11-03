"""Multi-tab formatted Excel workbook generator using openpyxl."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from portfolio_tracker.db import (
    get_accounts,
    get_dividends,
    get_dividends_summary,
    get_pnl_adjustments,
)
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


def _format_date_range_display(
    start_date: Optional[Union[str, date, datetime]],
    end_date: Optional[Union[str, date, datetime]],
) -> str:
    """Format start and end date into human-readable date range for reports."""
    s_str = None
    e_str = None
    if start_date:
        raw_s = str(start_date)[:10]
        try:
            s_str = datetime.strptime(raw_s, "%Y-%m-%d").strftime("%d-%m-%Y")
        except Exception:
            s_str = raw_s
    if end_date:
        raw_e = str(end_date)[:10]
        try:
            e_str = datetime.strptime(raw_e, "%Y-%m-%d").strftime("%d-%m-%Y")
        except Exception:
            e_str = raw_e

    if s_str and e_str:
        return f"Date Range: {s_str} to {e_str}"
    elif s_str:
        return f"Date Range: From {s_str} onwards"
    elif e_str:
        return f"Date Range: Up to {e_str}"
    else:
        return "Date Range: All Time (Historical)"


def _safe_sheet_title(name: str, existing_names: Optional[Set[str]] = None) -> str:
    """Clean and truncate worksheet titles to fit Excel 31-character limits without naming collisions."""
    cleaned = "".join(c for c in name if c not in r"\/*?:[]").strip()
    if not cleaned:
        cleaned = "Sheet"
    base = cleaned[:31]
    if existing_names is None:
        return base
    title = base
    counter = 1
    while title.lower() in {n.lower() for n in existing_names}:
        suffix = f"_{counter}"
        title = f"{base[:31 - len(suffix)]}{suffix}"
        counter += 1
    existing_names.add(title)
    return title


def _populate_dividend_ledger_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    title_text: str,
    subtitle_text: str,
    dividends: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> None:
    """Render a fully styled dividend transactions ledger sheet with summary cards and table."""
    ws.views.sheetView[0].showGridLines = True

    # Title Banner
    ws.cell(row=1, column=1, value=title_text).font = TITLE_FONT
    ws.cell(row=2, column=1, value=subtitle_text).font = SUBTITLE_FONT

    # KPI Summary Cards
    ws.cell(row=4, column=1, value="Total Dividends Received:").font = BOLD_DATA_FONT
    c_tot = ws.cell(row=4, column=2, value=summary.get("total_amount", 0.0))
    c_tot.font = BOLD_DATA_FONT
    c_tot.number_format = CURRENCY_FORMAT

    ws.cell(row=4, column=4, value="Payout Events:").font = BOLD_DATA_FONT
    ws.cell(row=4, column=5, value=summary.get("payout_count", 0)).font = BOLD_DATA_FONT

    ws.cell(row=5, column=1, value="Distinct Companies:").font = BOLD_DATA_FONT
    ws.cell(row=5, column=2, value=summary.get("unique_companies", 0)).font = BOLD_DATA_FONT

    ws.cell(row=5, column=4, value="Top Dividend Payer:").font = BOLD_DATA_FONT
    top_p_data = summary.get("top_payer", {})
    if top_p_data and top_p_data.get("symbol") != "N/A":
        top_p = f"{top_p_data['symbol']} (₹{top_p_data['amount']:,.2f})"
    else:
        top_p = "—"
    ws.cell(row=5, column=5, value=top_p).font = BOLD_DATA_FONT

    header_row = 7
    ledger_headers = [
        "Date",
        "Account",
        "Symbol",
        "Original Ticker",
        "Shares Held",
        "Dividend / Share (₹)",
        "Total Dividend (₹)",
        "Remarks",
    ]
    for col_idx, h in enumerate(ledger_headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=h)

    curr_row = header_row + 1
    for d in dividends:
        # Date dd-MM-yyyy
        raw_dt = str(d["dividend_date"])[:10]
        try:
            dt_obj = datetime.strptime(raw_dt, "%Y-%m-%d")
            formatted_date = dt_obj.strftime("%d-%m-%Y")
        except Exception:
            formatted_date = raw_dt
        ws.cell(row=curr_row, column=1, value=formatted_date).alignment = Alignment(horizontal="center", vertical="center")

        ws.cell(row=curr_row, column=2, value=d["user_name"]).alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=curr_row, column=3, value=d["canonical_symbol"]).alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=curr_row, column=4, value=d["original_symbol"] if d.get("is_mapped") else "—").alignment = Alignment(horizontal="left", vertical="center")

        # Shares
        c_q = ws.cell(row=curr_row, column=5, value=d["quantity"])
        c_q.number_format = INTEGER_FORMAT
        c_q.alignment = Alignment(horizontal="right", vertical="center")

        # DPS
        c_d = ws.cell(row=curr_row, column=6, value=d["dividend_per_share"])
        c_d.number_format = CURRENCY_FORMAT
        c_d.alignment = Alignment(horizontal="right", vertical="center")

        # Amount
        c_a = ws.cell(row=curr_row, column=7, value=d["amount"])
        c_a.number_format = CURRENCY_FORMAT
        c_a.alignment = Alignment(horizontal="right", vertical="center")
        c_a.font = BOLD_DATA_FONT

        ws.cell(row=curr_row, column=8, value=str(d.get("remarks") or "")).alignment = Alignment(horizontal="left", vertical="center")
        curr_row += 1

    _style_table(ws, start_row=header_row)


def _populate_company_wise_summary_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    title_text: str,
    subtitle_text: str,
    dividends: List[Dict[str, Any]],
) -> None:
    """Render a grouped company-wise dividend summary sheet with contribution percentages."""
    ws.views.sheetView[0].showGridLines = True

    ws.cell(row=1, column=1, value=title_text).font = TITLE_FONT
    ws.cell(row=2, column=1, value=subtitle_text).font = SUBTITLE_FONT

    comp_header_row = 4
    comp_headers = [
        "Company Symbol",
        "Total Dividends Received (₹)",
        "Payout Events",
        "Contribution (%)",
    ]
    for col_idx, h in enumerate(comp_headers, start=1):
        ws.cell(row=comp_header_row, column=col_idx, value=h)

    # Group records by canonical symbol
    comp_stats: Dict[str, Dict[str, Any]] = {}
    total_amount_all = sum(d["amount"] for d in dividends)

    for d in dividends:
        sym = d["canonical_symbol"]
        if sym not in comp_stats:
            comp_stats[sym] = {"amount": 0.0, "count": 0}
        comp_stats[sym]["amount"] += d["amount"]
        comp_stats[sym]["count"] += 1

    sorted_comps = sorted(comp_stats.items(), key=lambda x: x[1]["amount"], reverse=True)
    c_row = comp_header_row + 1
    for sym, st in sorted_comps:
        ws.cell(row=c_row, column=1, value=sym).alignment = Alignment(horizontal="left", vertical="center")
        c_tot_comp = ws.cell(row=c_row, column=2, value=st["amount"])
        c_tot_comp.number_format = CURRENCY_FORMAT
        c_tot_comp.alignment = Alignment(horizontal="right", vertical="center")
        c_tot_comp.font = BOLD_DATA_FONT

        c_cnt = ws.cell(row=c_row, column=3, value=st["count"])
        c_cnt.number_format = INTEGER_FORMAT
        c_cnt.alignment = Alignment(horizontal="right", vertical="center")

        pct = (st["amount"] / total_amount_all) if total_amount_all > 0 else 0.0
        c_pct = ws.cell(row=c_row, column=4, value=pct)
        c_pct.number_format = "0.00%"
        c_pct.alignment = Alignment(horizontal="right", vertical="center")

        c_row += 1

    # Total Summary Row
    if sorted_comps:
        ws.cell(row=c_row, column=1, value="TOTAL").alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=c_row, column=1).font = BOLD_DATA_FONT
        c_tot_all = ws.cell(row=c_row, column=2, value=total_amount_all)
        c_tot_all.number_format = CURRENCY_FORMAT
        c_tot_all.alignment = Alignment(horizontal="right", vertical="center")
        c_tot_all.font = BOLD_DATA_FONT

        c_cnt_all = ws.cell(row=c_row, column=3, value=len(dividends))
        c_cnt_all.number_format = INTEGER_FORMAT
        c_cnt_all.alignment = Alignment(horizontal="right", vertical="center")
        c_cnt_all.font = BOLD_DATA_FONT

        c_pct_all = ws.cell(row=c_row, column=4, value=1.0)
        c_pct_all.number_format = "0.00%"
        c_pct_all.alignment = Alignment(horizontal="right", vertical="center")
        c_pct_all.font = BOLD_DATA_FONT

    _style_table(ws, start_row=comp_header_row)


def export_dividends_to_excel(
    db_conn: sqlite3.Connection,
    file_path: Union[str, Path],
    account_id: Optional[str] = None,
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
    symbol: Optional[str] = None,
) -> Path:
    """Generate an Excel workbook with multi-page accounts breakdown, company-wise totals, and date range banner.

    Args:
        db_conn: Active SQLite connection.
        file_path: Destination file path for .xlsx workbook.
        account_id: Optional account filter. If None, exports Consolidated + one page per account.
        start_date: Optional range start date.
        end_date: Optional range end date.
        symbol: Optional stock symbol filter.

    Returns:
        Resolved Path to the saved .xlsx workbook.
    """
    target = Path(file_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    date_range_display = _format_date_range_display(start_date, end_date)
    timestamp_display = f"Generated: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"

    wb = openpyxl.Workbook()
    existing_sheet_names: Set[str] = set()

    if account_id is None:
        # ==========================================
        # 1. Consolidated Ledger Sheet
        # ==========================================
        ws_cons = wb.active
        ws_cons.title = _safe_sheet_title("Consolidated Ledger", existing_sheet_names)
        cons_divs = get_dividends(
            db_conn,
            account_id=None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        cons_summary = get_dividends_summary(
            db_conn,
            account_id=None,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        _populate_dividend_ledger_sheet(
            ws=ws_cons,
            title_text="Dividends Statement - Consolidated (All Accounts)",
            subtitle_text=f"{timestamp_display} | {date_range_display} | Scope: Consolidated (All Accounts)",
            dividends=cons_divs,
            summary=cons_summary,
        )

        # ==========================================
        # 2. One Sheet per Family Account
        # ==========================================
        accounts = get_accounts(db_conn)
        for acc in accounts:
            acc_id = acc["account_id"]
            acc_name = acc["user_name"]
            acc_divs = get_dividends(
                db_conn,
                account_id=acc_id,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            acc_summary = get_dividends_summary(
                db_conn,
                account_id=acc_id,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

            sheet_title = _safe_sheet_title(acc_name, existing_sheet_names)
            ws_acc = wb.create_sheet(title=sheet_title)
            _populate_dividend_ledger_sheet(
                ws=ws_acc,
                title_text=f"Dividends Statement - {acc_name} ({acc_id})",
                subtitle_text=f"{timestamp_display} | {date_range_display} | Account: {acc_name} ({acc_id})",
                dividends=acc_divs,
                summary=acc_summary,
            )

        # ==========================================
        # 3. Company Wise Total Sheet
        # ==========================================
        comp_sheet_title = _safe_sheet_title("Company Wise Total", existing_sheet_names)
        ws_comp = wb.create_sheet(title=comp_sheet_title)
        _populate_company_wise_summary_sheet(
            ws=ws_comp,
            title_text="Dividend Income - Company Wise Total",
            subtitle_text=f"{timestamp_display} | {date_range_display} | Scope: Consolidated (All Accounts)",
            dividends=cons_divs,
        )

    else:
        # ==========================================
        # Single Account Export
        # ==========================================
        single_divs = get_dividends(
            db_conn,
            account_id=account_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        single_summary = get_dividends_summary(
            db_conn,
            account_id=account_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

        # Retrieve user name
        accounts = get_accounts(db_conn)
        acc_name = account_id
        for a in accounts:
            if a["account_id"].upper() == account_id.upper():
                acc_name = a["user_name"]
                break

        ws_single = wb.active
        ws_single.title = _safe_sheet_title(f"{acc_name} Ledger", existing_sheet_names)
        _populate_dividend_ledger_sheet(
            ws=ws_single,
            title_text=f"Dividends Statement - {acc_name} ({account_id})",
            subtitle_text=f"{timestamp_display} | {date_range_display} | Account: {acc_name} ({account_id})",
            dividends=single_divs,
            summary=single_summary,
        )

        comp_sheet_title = _safe_sheet_title("Company Wise Total", existing_sheet_names)
        ws_comp = wb.create_sheet(title=comp_sheet_title)
        _populate_company_wise_summary_sheet(
            ws=ws_comp,
            title_text=f"Dividend Income - Company Wise Total ({acc_name})",
            subtitle_text=f"{timestamp_display} | {date_range_display} | Account: {acc_name} ({account_id})",
            dividends=single_divs,
        )

    wb.save(str(target))
    return target

