#!/usr/bin/env python
"""Debug portfolio returns calculations with detailed internal visibility.

Shows every intermediate step: period date mapping, daily portfolio values,
cash flows, XIRR cash flow schedule, and Newton-Raphson convergence.

Usage:
    python -m scripts.debug_returns                           # portfolio, all periods
    python -m scripts.debug_returns --scope portfolio         # portfolio only
    python -m scripts.debug_returns --scope all               # portfolio + all accounts
    python -m scripts.debug_returns --scope <account_id>      # single account
    python -m scripts.debug_returns --periods 1M,3M,YTD       # specific periods
    python -m scripts.debug_returns --period 1M --verbose     # full daily breakdown
    python -m scripts.debug_returns --list-accounts           # show account IDs
"""

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from database import get_session_local
from models import Account, DailyHoldingValue
from models.activity import Activity
from services.portfolio_returns_service import (
    DEFAULT_PERIODS,
    PortfolioReturnsService,
    _date_to_end_of_day,
    _date_to_start_of_day,
    _signed_cash_flow,
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_pct(val: Decimal | None) -> str:
    if val is None:
        return "  --  "
    pct = float(val) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.4f}%"


def _fmt_money(val: Decimal | None) -> str:
    if val is None:
        return "--"
    return f"${float(val):>14,.2f}"


def _fmt_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _separator(char: str = "-", width: int = 80) -> str:
    return char * width


@dataclass
class CashFlowDetail:
    """A single cash flow with account lineage."""
    cf_date: date
    signed_amount: Decimal  # positive = deposit, negative = withdrawal
    activity_type: str
    account_name: str
    account_id: str
    description: str | None


def _get_cash_flows_with_accounts(
    db, start: date, end: date, account_ids: list[str] | None,
) -> list[CashFlowDetail]:
    """Query cash-flow activities with account name for lineage tracking."""
    query = (
        db.query(Activity, Account.name)
        .join(Account, Activity.account_id == Account.id)
        .filter(
            Activity.type.in_(PortfolioReturnsService.CASH_FLOW_TYPES),
            Activity.amount.isnot(None),
            Activity.activity_date >= _date_to_start_of_day(start),
            Activity.activity_date <= _date_to_end_of_day(end),
        )
    )
    if account_ids:
        query = query.filter(Activity.account_id.in_(account_ids))

    query = query.order_by(Activity.activity_date)

    results = []
    for act, acct_name in query.all():
        results.append(CashFlowDetail(
            cf_date=act.activity_date.date(),
            signed_amount=_signed_cash_flow(act.type, act.amount),
            activity_type=act.type,
            account_name=acct_name,
            account_id=act.account_id,
            description=act.description,
        ))
    return results


# ---------------------------------------------------------------------------
# List accounts
# ---------------------------------------------------------------------------

def list_accounts(db):
    """Print all accounts with their IDs."""
    accounts = db.query(Account).order_by(Account.name).all()
    if not accounts:
        print("No accounts found.")
        return

    print(f"\n{'Account Name':<40} {'Status':<10} {'ID'}")
    print(_separator())
    for acc in accounts:
        status = "active" if acc.is_active else "inactive"
        print(f"{acc.name:<40} {status:<10} {acc.id}")

    # Also show DHV date ranges per account
    print(f"\n{'Account Name':<40} {'DHV Range':<30} {'Days'}")
    print(_separator())
    from sqlalchemy import func
    for acc in accounts:
        row = (
            db.query(
                func.min(DailyHoldingValue.valuation_date),
                func.max(DailyHoldingValue.valuation_date),
                func.count(func.distinct(DailyHoldingValue.valuation_date)),
            )
            .filter(DailyHoldingValue.account_id == acc.id)
            .first()
        )
        if row[0]:
            print(f"{acc.name:<40} {_fmt_date(row[0])} to {_fmt_date(row[1])}  {row[2]:>5}")
        else:
            print(f"{acc.name:<40} {'(no DHV data)':<30}")


# ---------------------------------------------------------------------------
# Debug a single period in detail
# ---------------------------------------------------------------------------

def debug_period_detailed(
    db,
    period: str,
    account_ids: list[str] | None,
    scope_name: str,
    verbose: bool,
):
    """Deep-dive into a single period's return calculation."""
    svc = PortfolioReturnsService

    today = date.today()
    end_date = today - timedelta(days=1)

    try:
        start, end = svc._get_period_dates(period, end_date)
    except ValueError as e:
        print(f"Error: {e}")
        return

    total_days = (end - start).days

    print(f"\n{'=' * 80}")
    print(f"  PERIOD: {period}   |   Scope: {scope_name}")
    print(f"{'=' * 80}")
    print(f"  Date range:  {_fmt_date(start)} to {_fmt_date(end)}  ({total_days} calendar days)")
    print()

    # ---- Daily Values ----
    daily_values = svc._get_daily_values(db, start, end, account_ids)
    days_with_data = len(daily_values)

    start_value = daily_values.get(start, Decimal("0"))
    end_value = daily_values.get(end, Decimal("0"))
    has_start = start in daily_values
    has_end = end in daily_values

    print("  Daily Values (DHV):")
    print(f"    Days with data:    {days_with_data} / {total_days + 1} calendar days")
    print(f"    Start ({_fmt_date(start)}):  {_fmt_money(start_value)}  {'[FOUND]' if has_start else '[MISSING]'}")
    print(f"    End   ({_fmt_date(end)}):  {_fmt_money(end_value)}  {'[FOUND]' if has_end else '[MISSING]'}")

    if has_start and has_end:
        naive_return = (end_value - start_value) / start_value if start_value else None
        print(f"    Naive return (no CF adjustment): {_fmt_pct(naive_return)}")

    # ---- Cash Flows ----
    # Use the service method for calculations (same as TWR/XIRR use)
    cash_flows = svc._get_external_cash_flows(db, start, end, account_ids)
    # Query again with account details for display
    cf_details = _get_cash_flows_with_accounts(db, start, end, account_ids)

    total_deposits = Decimal("0")
    total_withdrawals = Decimal("0")
    for cf in cf_details:
        if cf.signed_amount > 0:
            total_deposits += cf.signed_amount
        else:
            total_withdrawals += cf.signed_amount

    print("\n  External Cash Flows:")
    if not cf_details:
        print("    (none)")
    else:
        print(f"    Total flows:       {len(cf_details)}")
        print(f"    Total inflows:     {_fmt_money(total_deposits)}")
        print(f"    Total outflows:    {_fmt_money(abs(total_withdrawals))}")
        print(f"    Net cash flow:     {_fmt_money(total_deposits + total_withdrawals)}")
        print()
        print(f"    {'Date':<14} {'Type':<12} {'Direction':<6} {'Amount':>16}  {'Account':<30} {'Description'}")
        print(f"    {'-' * 108}")
        for cf in cf_details:
            direction = "IN" if cf.signed_amount > 0 else "OUT"
            desc = cf.description or ""
            if len(desc) > 40:
                desc = desc[:37] + "..."
            print(
                f"    {_fmt_date(cf.cf_date):<14} {cf.activity_type:<12} "
                f"{direction:<6} "
                f"{_fmt_money(abs(cf.signed_amount)):>16}  "
                f"{cf.account_name:<30} {desc}"
            )

    # ---- XIRR Calculation ----
    print("\n  IRR Calculation (Newton-Raphson):")

    if not has_start and not cash_flows:
        print("    SKIPPED: No start value and no cash flows")
    elif not has_end:
        print("    SKIPPED: No end value")
    else:
        # Build the XIRR cash flow schedule with account lineage
        flows: list[tuple[float, float, str]] = []  # (t, amount, label)

        if start_value != 0:
            flows.append((0.0, -float(start_value), f"Start value ({_fmt_date(start)})"))

        # Use cf_details (with account names) instead of the bare cash_flows dict
        for cf in cf_details:
            if cf.cf_date < start or cf.cf_date > end:
                continue
            days_from_start = (cf.cf_date - start).days
            t = days_from_start / total_days
            flow_type = "Deposit" if cf.signed_amount > 0 else "Withdrawal"
            flows.append((
                t,
                -float(cf.signed_amount),
                f"{flow_type} ({_fmt_date(cf.cf_date)}) @ {cf.account_name}",
            ))

        flows.append((1.0, float(end_value), f"End value ({_fmt_date(end)})"))

        print("\n    Cash Flow Schedule (IRR convention: investor outflow = negative):")
        print(f"    {'t (period)':<12} {'Amount':>16}  {'Description'}")
        print(f"    {'-' * 80}")
        for t, amt, label in flows:
            print(f"    {t:<12.6f} {amt:>16,.2f}  {label}")

        # Show NPV at rate=0 (sanity check: should be positive if portfolio gained)
        times = np.array([f[0] for f in flows])
        amounts = np.array([f[1] for f in flows])
        npv_at_zero = float(np.sum(amounts))
        print(f"\n    NPV at rate=0:  ${npv_at_zero:>14,.2f}  ({'gain' if npv_at_zero > 0 else 'loss'})")

        # Run Newton-Raphson with convergence trace
        print("\n    Newton-Raphson iterations:")
        print(f"    {'Iter':<6} {'Rate':>12} {'NPV':>16} {'dNPV':>16} {'Step':>12}")
        print(f"    {'-' * 62}")

        rate = 0.1
        converged = False
        for iteration in range(100):
            denom = (1 + rate) ** times
            if np.any(denom == 0):
                print(f"    {iteration:<6} {rate:>12.8f}  DENOM=0, aborting")
                break

            npv = float(np.sum(amounts / denom))
            d_npv = float(np.sum(-times * amounts / ((1 + rate) ** (times + 1))))

            if abs(d_npv) < 1e-14:
                print(f"    {iteration:<6} {rate:>12.8f} {npv:>16.6f} {d_npv:>16.6f}  dNPV~0, aborting")
                break

            step = npv / d_npv
            new_rate = rate - step

            if new_rate <= -1:
                new_rate = -0.99

            print(f"    {iteration:<6} {rate:>12.8f} {npv:>16.6f} {d_npv:>16.6f} {step:>12.8f}")

            if abs(new_rate - rate) < 1e-8:
                converged = True
                rate = new_rate
                print(f"    {iteration + 1:<6} {rate:>12.8f}  ** CONVERGED **")
                break

            rate = new_rate

        if converged:
            irr = Decimal(str(round(rate, 8)))
            print(f"\n    IRR (cumulative): {_fmt_pct(irr)}")
        else:
            print("\n    IRR did not converge after 100 iterations")

    print()


# ---------------------------------------------------------------------------
# Summary table (compact view)
# ---------------------------------------------------------------------------

def print_summary_table(db, scope: str, periods: list[str]):
    """Print a compact returns table (like a brokerage dashboard)."""
    svc = PortfolioReturnsService()
    result = svc.get_returns(db, scope=scope, periods=periods)

    scopes = []
    if result.portfolio:
        scopes.append(result.portfolio)
    scopes.extend(result.accounts)

    if not scopes:
        print("No data to display.")
        return

    # Header
    col_w = 12
    name_w = 30
    header = f"{'Scope':<{name_w}}"
    for p in periods:
        header += f"  {p:>{col_w}}"

    print(f"\n{'=' * len(header)}")
    print(f"{'IRR (Money-Weighted)':^{len(header)}}")
    print(header)
    print(_separator("=", len(header)))

    for scope_ret in scopes:
        line = f"{scope_ret.scope_name:<{name_w}}"

        period_map = {r.period: r for r in scope_ret.periods}
        for p in periods:
            r = period_map.get(p)
            if r and r.has_sufficient_data and r.irr is not None:
                line += f"  {_fmt_pct(r.irr):>{col_w}}"
            else:
                line += f"  {'--':>{col_w}}"

        print(line)

    print(_separator("=", len(header)))

    # Data availability note
    print("\nData availability per period:")
    if result.portfolio:
        for r in result.portfolio.periods:
            flag = "OK" if r.has_sufficient_data else "MISSING"
            print(
                f"  {r.period:<5} {_fmt_date(r.start_date)} to {_fmt_date(r.end_date)}  "
                f"start={_fmt_money(r.start_value)}  end={_fmt_money(r.end_value)}  [{flag}]"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Debug portfolio returns calculations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.debug_returns                             # summary table
  python -m scripts.debug_returns --list-accounts             # show account IDs
  python -m scripts.debug_returns --period 1M --verbose       # detailed 1M breakdown
  python -m scripts.debug_returns --scope <uuid> --period YTD # single account, YTD
  python -m scripts.debug_returns --periods 1D,1M,YTD         # specific periods
        """,
    )
    parser.add_argument(
        "--list-accounts", action="store_true",
        help="List all accounts with IDs and DHV date ranges",
    )
    parser.add_argument(
        "--scope", default="all",
        help="'all', 'portfolio', or an account UUID (default: all)",
    )
    parser.add_argument(
        "--periods",
        help="Comma-separated periods for summary table (default: 1D,1M,3M,YTD,1Y,3Y)",
    )
    parser.add_argument(
        "--period",
        help="Single period to debug in detail (e.g., 1M, YTD)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show full daily value breakdown in detailed mode",
    )

    args = parser.parse_args()

    SessionLocal = get_session_local()
    db = SessionLocal()

    try:
        if args.list_accounts:
            list_accounts(db)
            return

        periods = args.periods.split(",") if args.periods else DEFAULT_PERIODS

        if args.period:
            # Detailed single-period debug
            account_ids = None
            scope_name = "Portfolio (all accounts)"

            if args.scope not in ("all", "portfolio"):
                account_ids = [args.scope]
                acc = db.query(Account).filter(Account.id == args.scope).first()
                scope_name = acc.name if acc else f"Account {args.scope}"

            debug_period_detailed(db, args.period, account_ids, scope_name, args.verbose)
        else:
            # Summary table
            print_summary_table(db, args.scope, periods)

    finally:
        db.close()


if __name__ == "__main__":
    main()
