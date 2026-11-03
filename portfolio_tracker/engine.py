"""Stock ACB Analytical Engine: Adjusted Cost Basis (ACB), Actual Exposure, Booked P&L,
Net Exposure, symbol aliasing, and portfolio consolidation."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from portfolio_tracker.db import get_adjustments_summary


def _format_cutoff_date(cutoff_date: Optional[Union[str, date, datetime]]) -> Optional[str]:
    """Normalize cutoff date to ISO format YYYY-MM-DD 23:59:59 if time is not specified."""
    if cutoff_date is None:
        return None
    if isinstance(cutoff_date, datetime):
        return cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(cutoff_date, date):
        return f"{cutoff_date.strftime('%Y-%m-%d')} 23:59:59"

    s = str(cutoff_date).strip()
    if not s:
        return None
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s} 23:59:59"
    return s


def get_holdings(
    db_conn: sqlite3.Connection,
    cutoff_date: Optional[Union[str, date, datetime]] = None,
    account_id: Optional[str] = None,
    include_closed: bool = False,
) -> pd.DataFrame:
    """Calculate holdings and Adjusted Cost Basis (ACB) ledger metrics.

    Columns include:
    - symbol: Canonical stock symbol (accounting for ticker renames / corporate actions)
    - net_qty: Remaining shares held (Buy Qty - Sell Qty)
    - total_buy_cost: Cumulative capital deployed into purchases
    - total_proceeds: Cumulative revenue realized from sales
    - avg_buy_price: Weighted average purchase price per share
    - actual_exposure: Capital committed to remaining shares (Shares Held * Avg Buy Price)
    - booked_pnl: Realized profit or loss booked from sales so far
    - net_exposure: Adjusted Cost Basis (Actual Exposure - Booked P&L, floored at 0.0)
    - effective_avg: Effective cost per share after profit offsets (Net Exposure / Shares Held)
    - is_house_money: True if Net Exposure is 0.0 (all capital recovered + profit booked)
    - is_closed: True if Net Qty is 0
    - is_anomalous: True if Sell Qty > Buy Qty
    - mapped_sources: List of historical tickers mapped into this canonical symbol
    """
    cutoff_str = _format_cutoff_date(cutoff_date)

    query = """
        SELECT t.trade_id, t.account_id, a.user_name, 
               t.symbol AS original_symbol,
               COALESCE(m.target_symbol, t.symbol) AS symbol,
               t.transaction_type, t.quantity, t.price, t.trade_date
        FROM transactions t
        JOIN accounts a ON t.account_id = a.account_id
        LEFT JOIN symbol_mappings m ON UPPER(TRIM(t.symbol)) = UPPER(TRIM(m.source_symbol))
        WHERE 1=1
    """
    params: List[Any] = []

    if account_id:
        query += " AND t.account_id = ?"
        params.append(account_id)

    if cutoff_str:
        query += " AND t.trade_date <= ?"
        params.append(cutoff_str)

    query += " ORDER BY t.trade_date ASC;"

    df_trades = pd.read_sql_query(query, db_conn, params=params)

    # Fetch stock-specific adjustments up to cutoff_date
    adj_query = """
        SELECT adj.adjustment_id, adj.account_id,
               adj.symbol AS original_symbol,
               COALESCE(m.target_symbol, adj.symbol) AS symbol,
               adj.category, adj.direction, adj.amount,
               CASE WHEN adj.direction = 'PROFIT' THEN adj.amount ELSE -adj.amount END AS signed_amount
        FROM pnl_adjustments adj
        LEFT JOIN symbol_mappings m ON UPPER(TRIM(adj.symbol)) = UPPER(TRIM(m.source_symbol))
        WHERE adj.symbol IS NOT NULL AND TRIM(adj.symbol) != ''
    """
    adj_params: List[Any] = []
    if account_id:
        adj_query += " AND adj.account_id = ?"
        adj_params.append(account_id)
    if cutoff_str:
        adj_query += " AND adj.adjustment_date <= ?"
        adj_params.append(cutoff_str)

    try:
        df_adjs = pd.read_sql_query(adj_query, db_conn, params=adj_params)
    except Exception:
        df_adjs = pd.DataFrame()

    if df_trades.empty and df_adjs.empty:
        return pd.DataFrame(columns=[
            "symbol", "account_id", "user_name", "net_qty",
            "total_buy_qty", "total_buy_cost", "total_sell_qty", "total_proceeds",
            "avg_buy_price", "actual_exposure", "booked_pnl", "trade_booked_pnl",
            "stock_adj_pnl", "stock_carried_profit", "stock_charges",
            "net_exposure", "net_capital_at_risk", "effective_avg", "raw_effective_avg",
            "cash_extracted", "realized_pnl", "is_house_money", "is_closed",
            "is_anomalous", "status", "mapped_sources"
        ])

    # Grouping key: by canonical symbol only if consolidated, by (account_id, symbol) if single account
    group_cols = ["account_id", "user_name", "symbol"] if account_id else ["symbol"]

    records: List[Dict[str, Any]] = []
    seen_symbols = set()

    for group_key, grp in df_trades.groupby(group_cols):
        if account_id:
            grp_acc_id, grp_user_name, grp_symbol = group_key
        else:
            grp_symbol = group_key if isinstance(group_key, str) else group_key[0]
            grp_acc_id = "CONSOLIDATED"
            grp_user_name = "Family Consolidated View"

        seen_symbols.add(grp_symbol)

        # Track mapped source symbols (e.g. historical ticker names)
        raw_symbols = sorted(list({str(s).strip().upper() for s in grp["original_symbol"].dropna()}))
        mapped_sources = [s for s in raw_symbols if s != grp_symbol]

        # Calculate stock-specific adjustments for this symbol
        stock_adjs = df_adjs[df_adjs["symbol"] == grp_symbol] if not df_adjs.empty else pd.DataFrame()
        if not stock_adjs.empty and account_id:
            stock_adjs = stock_adjs[stock_adjs["account_id"] == grp_acc_id]

        stock_adj_pnl = float(stock_adjs["signed_amount"].sum()) if not stock_adjs.empty else 0.0
        stock_carried_profit = (
            float(stock_adjs.loc[stock_adjs["category"] == "CARRIED_FORWARD_PROFIT", "amount"].sum())
            if not stock_adjs.empty
            else 0.0
        )
        stock_charges = (
            float(stock_adjs.loc[stock_adjs["category"].isin(["BROKERAGE_CHARGES", "DP_CHARGES"]), "amount"].sum())
            if not stock_adjs.empty
            else 0.0
        )

        buy_mask = grp["transaction_type"] == "BUY"
        sell_mask = grp["transaction_type"] == "SELL"

        total_buy_qty = int(grp.loc[buy_mask, "quantity"].sum())
        total_buy_cost = float((grp.loc[buy_mask, "quantity"] * grp.loc[buy_mask, "price"]).sum())

        total_sell_qty = int(grp.loc[sell_mask, "quantity"].sum())
        total_proceeds = float((grp.loc[sell_mask, "quantity"] * grp.loc[sell_mask, "price"]).sum())

        net_qty = total_buy_qty - total_sell_qty
        avg_buy_price = (total_buy_cost / total_buy_qty) if total_buy_qty > 0 else 0.0

        # Position classifications
        is_anomalous = False
        is_closed = False
        is_house_money = False

        if net_qty < 0 or (total_sell_qty > 0 and total_buy_qty == 0):
            is_anomalous = True
            status = "ANOMALOUS (Sell > Buy)"
            actual_exposure = 0.0
            trade_booked_pnl = total_proceeds - total_buy_cost
            booked_pnl = trade_booked_pnl + stock_adj_pnl
            net_exposure = 0.0
            net_capital_at_risk = (total_buy_cost - total_proceeds) - stock_adj_pnl
            effective_avg: Optional[float] = 0.0
            raw_effective_avg: Optional[float] = 0.0
            cash_extracted = max(0.0, total_proceeds - total_buy_cost)
            realized_pnl = booked_pnl

        elif net_qty == 0:
            is_closed = True
            status = "CLOSED"
            actual_exposure = 0.0
            trade_booked_pnl = total_proceeds - total_buy_cost
            booked_pnl = trade_booked_pnl + stock_adj_pnl
            net_exposure = 0.0
            net_capital_at_risk = 0.0
            effective_avg = 0.0
            raw_effective_avg = 0.0
            cash_extracted = max(0.0, total_proceeds - total_buy_cost)
            realized_pnl = booked_pnl

        else:
            # Active Position: Shares held > 0
            # 1. Actual Exposure: Original purchase cost of currently held shares
            actual_exposure = net_qty * avg_buy_price

            # 2. Booked P&L: Realized profit from shares sold so far + stock-specific adjustments
            trade_booked_pnl = total_proceeds - (total_sell_qty * avg_buy_price)
            booked_pnl = trade_booked_pnl + stock_adj_pnl
            realized_pnl = booked_pnl

            # 3. Net Capital at Risk / Excess: Actual Exposure - Booked P&L
            # Notice the core identity:
            # When stock_adj_pnl == 0: actual_exposure - trade_booked_pnl == Total Buy Cost - Total Proceeds
            # When stock_adj_pnl != 0: net_diff = (Total Buy Cost - Total Proceeds) - stock_adj_pnl
            net_diff = actual_exposure - booked_pnl
            net_capital_at_risk = net_diff

            if net_diff <= 0:
                is_house_money = True
                status = "RISK_FREE (House Money)"
                net_exposure = 0.0  # Fully recovered, zero downside capital at risk
                effective_avg = 0.0
                raw_effective_avg = net_diff / net_qty if net_qty > 0 else 0.0
                cash_extracted = abs(net_diff)
            else:
                status = "ACTIVE"
                net_exposure = net_diff
                effective_avg = net_diff / net_qty
                raw_effective_avg = effective_avg
                cash_extracted = 0.0

        if not include_closed and is_closed:
            continue

        records.append({
            "symbol": grp_symbol,
            "account_id": grp_acc_id,
            "user_name": grp_user_name,
            "net_qty": int(net_qty),
            "total_buy_qty": int(total_buy_qty),
            "total_buy_cost": round(total_buy_cost, 2),
            "total_sell_qty": int(total_sell_qty),
            "total_proceeds": round(total_proceeds, 2),
            "avg_buy_price": round(avg_buy_price, 2),
            "actual_exposure": round(actual_exposure, 2),
            "trade_booked_pnl": round(trade_booked_pnl, 2),
            "stock_adj_pnl": round(stock_adj_pnl, 2),
            "stock_carried_profit": round(stock_carried_profit, 2),
            "stock_charges": round(stock_charges, 2),
            "booked_pnl": round(booked_pnl, 2),
            "net_exposure": round(net_exposure, 2),
            "net_capital_at_risk": round(net_capital_at_risk, 2),
            "effective_avg": round(effective_avg, 2) if effective_avg is not None else None,
            "raw_effective_avg": round(raw_effective_avg, 2) if raw_effective_avg is not None else None,
            "cash_extracted": round(cash_extracted, 2),
            "realized_pnl": round(realized_pnl, 2),
            "is_house_money": bool(is_house_money),
            "is_closed": bool(is_closed),
            "is_anomalous": bool(is_anomalous),
            "status": status,
            "mapped_sources": mapped_sources,
        })

    # Include any closed symbols that only have adjustments from an untracked account if include_closed is True
    if include_closed and not df_adjs.empty:
        extra_symbols = set(df_adjs["symbol"].dropna().unique()) - seen_symbols
        for extra_sym in sorted(extra_symbols):
            extra_adjs = df_adjs[df_adjs["symbol"] == extra_sym]
            extra_adj_pnl = float(extra_adjs["signed_amount"].sum())
            extra_carried = float(
                extra_adjs.loc[extra_adjs["category"] == "CARRIED_FORWARD_PROFIT", "amount"].sum()
            )
            extra_charges = float(
                extra_adjs.loc[extra_adjs["category"].isin(["BROKERAGE_CHARGES", "DP_CHARGES"]), "amount"].sum()
            )
            records.append({
                "symbol": extra_sym,
                "account_id": account_id or "CONSOLIDATED",
                "user_name": "Family Consolidated View" if not account_id else account_id,
                "net_qty": 0,
                "total_buy_qty": 0,
                "total_buy_cost": 0.0,
                "total_sell_qty": 0,
                "total_proceeds": 0.0,
                "avg_buy_price": 0.0,
                "actual_exposure": 0.0,
                "trade_booked_pnl": 0.0,
                "stock_adj_pnl": round(extra_adj_pnl, 2),
                "stock_carried_profit": round(extra_carried, 2),
                "stock_charges": round(extra_charges, 2),
                "booked_pnl": round(extra_adj_pnl, 2),
                "net_exposure": 0.0,
                "net_capital_at_risk": 0.0,
                "effective_avg": 0.0,
                "raw_effective_avg": 0.0,
                "cash_extracted": 0.0,
                "realized_pnl": round(extra_adj_pnl, 2),
                "is_house_money": False,
                "is_closed": True,
                "is_anomalous": False,
                "status": "CLOSED",
                "mapped_sources": [],
            })

    result_df = pd.DataFrame(records)
    if not result_df.empty:
        # Sort active holdings by Net Exposure descending, then Actual Exposure, closed at bottom
        result_df = result_df.sort_values(
            by=["is_closed", "net_exposure", "actual_exposure", "symbol"],
            ascending=[True, False, False, True],
        ).reset_index(drop=True)

    return result_df


def get_portfolio_summary(
    holdings_df: pd.DataFrame,
    db_conn: Optional[sqlite3.Connection] = None,
    account_id: Optional[str] = None,
    cutoff_date: Optional[Union[str, date, datetime]] = None,
) -> Dict[str, Any]:
    """Compute high-level executive KPI metric card values from a holdings DataFrame and P&L adjustments."""
    total_carried_profit = 0.0
    total_carried_loss = 0.0
    total_brokerage = 0.0
    total_dividend = 0.0
    total_net_adjustments = 0.0
    adjustments_count = 0

    if db_conn is not None:
        try:
            adj_summary = get_adjustments_summary(db_conn, account_id=account_id, cutoff_date=cutoff_date)
            total_carried_profit = adj_summary["total_carried_profit"]
            total_carried_loss = adj_summary["total_carried_loss"]
            total_brokerage = adj_summary["total_brokerage"]
            total_dividend = adj_summary["total_dividend"]
            total_net_adjustments = adj_summary["net_adjustments"]
            adjustments_count = adj_summary["adjustments_count"]
        except Exception:
            pass

    if holdings_df.empty:
        return {
            "total_net_exposure": 0.0,
            "total_actual_exposure": 0.0,
            "total_booked_profit": round(max(0.0, total_net_adjustments), 2),
            "total_booked_pnl": round(total_net_adjustments, 2),
            "total_trade_booked_pnl": 0.0,
            "total_carried_profit": total_carried_profit,
            "total_carried_loss": total_carried_loss,
            "total_brokerage": total_brokerage,
            "total_dividend": total_dividend,
            "total_net_adjustments": total_net_adjustments,
            "total_net_realized_pnl": round(total_net_adjustments, 2),
            "adjustments_count": adjustments_count,
            "total_net_capital_at_risk": 0.0,
            "total_realized_proceeds": 0.0,
            "total_realized_pnl_closed": 0.0,
            "total_cash_extracted": 0.0,
            "active_stocks_count": 0,
            "risk_free_stocks_count": 0,
            "closed_stocks_count": 0,
            "anomalous_stocks_count": 0,
        }

    active_mask = (holdings_df["is_closed"] == False) & (holdings_df["is_anomalous"] == False)
    risk_free_mask = holdings_df["is_house_money"] == True
    closed_mask = holdings_df["is_closed"] == True
    anomalous_mask = holdings_df["is_anomalous"] == True

    # Total Net Exposure (active capital at risk)
    total_net_exposure = float(
        holdings_df.loc[active_mask, "net_exposure"].sum()
    )

    # Total Actual Exposure (gross cost of currently held shares)
    total_actual_exposure = float(
        holdings_df.loc[active_mask, "actual_exposure"].sum()
    )

    # Total Booked Profit (all realized profits across both active and closed positions)
    booked_profits = holdings_df.loc[holdings_df["booked_pnl"] > 0, "booked_pnl"].sum()
    total_booked_profit = float(booked_profits)

    # Net Booked P&L (profits minus losses)
    total_booked_pnl = float(holdings_df["booked_pnl"].sum())

    # Trade Booked P&L (purely from trade executions)
    if "trade_booked_pnl" in holdings_df.columns:
        total_trade_booked_pnl = float(holdings_df["trade_booked_pnl"].sum())
    else:
        total_trade_booked_pnl = total_booked_pnl

    # Comprehensive Net Realized P&L = Trade Realized P&L + ALL Net Adjustments
    total_net_realized_pnl = total_trade_booked_pnl + total_net_adjustments

    # Backward compatibility
    capital_at_risk = float(
        holdings_df.loc[active_mask & (holdings_df["net_capital_at_risk"] > 0), "net_capital_at_risk"].sum()
    )
    total_realized_proceeds = float(holdings_df["total_proceeds"].sum())
    total_closed_pnl = float(holdings_df.loc[closed_mask, "realized_pnl"].sum())
    total_cash_extracted = float(holdings_df["cash_extracted"].sum())

    return {
        "total_net_exposure": round(total_net_exposure, 2),
        "total_actual_exposure": round(total_actual_exposure, 2),
        "total_booked_profit": round(total_booked_profit, 2),
        "total_booked_pnl": round(total_booked_pnl, 2),
        "total_trade_booked_pnl": round(total_trade_booked_pnl, 2),
        "total_carried_profit": round(total_carried_profit, 2),
        "total_carried_loss": round(total_carried_loss, 2),
        "total_brokerage": round(total_brokerage, 2),
        "total_dividend": round(total_dividend, 2),
        "total_net_adjustments": round(total_net_adjustments, 2),
        "total_net_realized_pnl": round(total_net_realized_pnl, 2),
        "adjustments_count": adjustments_count,
        "total_net_capital_at_risk": round(capital_at_risk, 2),
        "total_realized_proceeds": round(total_realized_proceeds, 2),
        "total_realized_pnl_closed": round(total_closed_pnl, 2),
        "total_cash_extracted": round(total_cash_extracted, 2),
        "active_stocks_count": int(active_mask.sum()),
        "risk_free_stocks_count": int(risk_free_mask.sum()),
        "closed_stocks_count": int(closed_mask.sum()),
        "anomalous_stocks_count": int(anomalous_mask.sum()),
    }
