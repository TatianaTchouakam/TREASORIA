"""Read Gold data without changing it, and check the cash-flow identities."""

from pathlib import Path
import numpy as np
import pandas as pd

TARGET = "net_cash_flow"
GOLD_RELATIVE = Path("data/Treasoria_Datasets_Code_and_Coffee/gold")


def find_project_root(start=None):
    """Find the project from a notebook or a Python script on any computer."""
    start = Path(start or __file__).resolve()
    if start.is_file():
        start = start.parent
    for folder in [start, *start.parents]:
        if (folder / GOLD_RELATIVE / "gold_monthly_cash_flow.csv").is_file():
            return folder
    raise FileNotFoundError("Cannot find Gold data. Pass the TREASORIA project root.")


def _read_table(path, date_column, frequency, company_id=None):
    frame = pd.read_csv(path)
    required = {date_column, "company_id"}
    if not required.issubset(frame.columns):
        raise ValueError(f"{path.name}: missing columns {required - set(frame.columns)}")
    if company_id is not None:
        frame = frame.loc[frame.company_id == company_id].copy()
    # Never mix two companies into one time series.
    if frame.empty or frame.company_id.isna().any() or frame.company_id.nunique() != 1:
        raise ValueError("Select exactly one non-empty company with company_id.")
    dates = pd.to_datetime(frame.pop(date_column), errors="raise")
    if dates.isna().any() or dates.dt.tz is not None:
        raise ValueError("Dates must be non-null and timezone-naive.")
    if frequency == "MS":
        dates = dates.dt.to_period("M").dt.to_timestamp()
    elif not dates.eq(dates.dt.normalize()).all():
        raise ValueError("Daily balances must have one date per calendar day.")
    frame.index = pd.DatetimeIndex(dates, name=date_column)
    frame = frame.sort_index()
    expected = pd.date_range(frame.index.min(), frame.index.max(), freq=frequency)
    if frame.index.has_duplicates or not frame.index.equals(expected):
        raise ValueError(f"{path.name}: duplicate or missing periods. Do not fill with zero silently.")
    return frame.asfreq(frequency)


def _numeric(frame, columns):
    for column in columns:
        if column not in frame:
            raise ValueError(f"Missing required column: {column}")
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column]).all():
            raise ValueError(f"{column} contains missing or infinite values.")


def load_monthly(project_root=None, company_id=None):
    root = find_project_root(project_root)
    frame = _read_table(root / GOLD_RELATIVE / "gold_monthly_cash_flow.csv", "month", "MS", company_id)
    outflow_columns = ["cash_out_operating", "cash_out_card_payments", "cash_out_payroll"]
    _numeric(frame, ["cash_in", "cash_out_total", TARGET, *outflow_columns])
    if (frame[["cash_in", "cash_out_total", *outflow_columns]] < 0).any().any():
        raise ValueError("Gold inflow and outflow columns must be positive amounts.")
    if not np.allclose(frame.cash_out_total, frame[outflow_columns].sum(axis=1), atol=0.01, rtol=0):
        raise ValueError("Cash-out components do not add up to cash_out_total.")
    if not np.allclose(frame.cash_in - frame.cash_out_total, frame[TARGET], atol=0.01, rtol=0):
        raise ValueError("net_cash_flow must equal cash_in minus cash_out_total.")
    return frame


def load_daily(project_root=None, company_id=None):
    root = find_project_root(project_root)
    frame = _read_table(root / GOLD_RELATIVE / "gold_daily_cash_position.csv", "date", "D", company_id)
    columns = ["checking_main_balance", "checking_secondary_balance", "consolidated_cash_balance"]
    _numeric(frame, columns)
    if not np.allclose(frame[columns[:2]].sum(axis=1), frame[columns[2]], atol=0.01, rtol=0):
        raise ValueError("Bank balances do not add up to consolidated cash.")
    return frame


def daily_net_flow(daily, opening_balance=None):
    """A balance is a stock. Its day-to-day change is a net cash flow."""
    result = daily[["company_id"]].copy()
    result[TARGET] = daily.consolidated_cash_balance.diff()
    # The first day's flow needs the balance BEFORE that day.
    # Without it, leave that day out; do not invent a zero flow.
    if opening_balance is None:
        return result.iloc[1:].asfreq("D")
    if not np.isfinite(opening_balance):
        raise ValueError("Opening balance must be finite.")
    result.iloc[0, result.columns.get_loc(TARGET)] = daily.consolidated_cash_balance.iloc[0] - opening_balance
    return result.asfreq("D")


def reconcile_cash(monthly, daily, opening_balance=None):
    """Compare independent monthly totals with daily balance movements."""
    if monthly.company_id.iloc[0] != daily.company_id.iloc[0]:
        raise ValueError("Monthly and daily data belong to different companies.")
    if daily.index.min() != monthly.index.min() or daily.index.max() != monthly.index.max() + pd.offsets.MonthEnd(0):
        raise ValueError("Monthly and daily sources must cover the same complete months.")
    flow = daily_net_flow(daily, opening_balance)
    totals = flow[TARGET].resample("MS").sum()
    report = monthly[[TARGET]].join(totals.rename("daily_net_flow_sum"))
    report["difference_eur"] = report.daily_net_flow_sum - report[TARGET]
    report["checked"] = True
    if opening_balance is None:
        report.iloc[0, report.columns.get_loc("checked")] = False
    checked = report.loc[report.checked, "difference_eur"]
    if checked.empty or checked.abs().max() > 0.01:
        raise ValueError("Daily balance movements do not reconcile to monthly flows.")
    report["note"] = np.where(report.checked, "reconciled", "first-day opening balance unavailable")
    return report


def split_development_test(frame, test_periods):
    """Keep the final block outside model selection. Never shuffle dates."""
    if not isinstance(test_periods, int) or test_periods < 1 or test_periods >= len(frame):
        raise ValueError("test_periods must leave a non-empty development set.")
    return frame.iloc[:-test_periods].copy(), frame.iloc[-test_periods:].copy()


def rolling_splits(development, horizon, folds=3):
    """Use three non-overlapping validation blocks with expanding history."""
    initial = len(development) - folds * horizon
    if initial < 2:
        raise ValueError("Not enough data for the requested validation folds.")
    for fold in range(folds):
        end = initial + fold * horizon
        yield fold + 1, development.iloc[:end].copy(), development.iloc[end:end + horizon].copy()


def future_index(last_date, horizon, frequency):
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
        raise ValueError("horizon must be a positive integer.")
    if frequency not in {"MS", "D"}:
        raise ValueError("Supported frequencies: MS (monthly) and D (daily).")
    start = pd.Timestamp(last_date) + (pd.offsets.MonthBegin(1) if frequency == "MS" else pd.Timedelta(days=1))
    return pd.date_range(start, periods=horizon, freq=frequency, name="date")
