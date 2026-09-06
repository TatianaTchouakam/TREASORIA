"""
Treasoria — KPI validation

Goal: don't just trust gold_kpi_summary.csv blindly. Recompute a
handful of KPIs directly from the raw Gold tables they should be
derived from, and compare the recomputed value against what's
actually stored. A mismatch reveals a real bug somewhere in the
pipeline that generates gold_kpi_summary.csv -- exactly the same
spirit as CER/WER for OCR, but here the "ground truth" is a fresh
recalculation instead of a human-annotated answer.

Only 3 KPIs are validated here (Closing cash balance, Average
Monthly Net Cash Flow, Open Receivables) -- the ones we can
recompute with confidence from tables whose exact columns are
already known and used elsewhere in this app. The other 14 KPIs in
gold_kpi_summary.csv (Gross Margin, Employer Cost, Runway, etc.)
would need source tables whose schema isn't confirmed yet -- adding
them is a future step, not a gap in this one.
"""

import pandas as pd


def parse_eur_value(value_str: str) -> float:
    """
    Turn a stored KPI string like "234,549.89 EUR" into a plain
    float (234549.89), so it can be compared numerically against a
    recomputed value.
    """

    cleaned = value_str.replace("EUR", "").replace(",", "").strip()
    return float(cleaned)


def recompute_closing_cash_balance(daily: pd.DataFrame) -> float:
    """
    Recompute the closing cash balance directly: it's simply the
    consolidated balance on the very last date in the daily cash
    position table, sorted chronologically.
    """

    last_row = daily.sort_values("date").iloc[-1]
    return float(last_row["consolidated_cash_balance"])


def recompute_average_monthly_net_cash_flow(monthly: pd.DataFrame) -> float:
    """
    Recompute the average monthly net cash flow: the mean of the
    net_cash_flow column across every month in the table.
    """

    return float(monthly["net_cash_flow"].mean())


def recompute_open_receivables(receivables: pd.DataFrame) -> float | None:
    """
    Recompute total open receivables: the sum of amounts for every
    row whose status indicates it's still open (not yet collected).

    ASSUMPTION: status values that mean "not yet paid" start with
    "open" (we've already seen "open_overdue" used elsewhere in
    this app). If the real data also has an "open_current" or
    similar status for invoices not yet overdue, this correctly
    includes them too, since we match on the "open" prefix rather
    than one exact status string.

    Returns None (not a crash) if no recognisable amount column is
    found, so the caller can report "could not verify" instead of
    a Python traceback.
    """

    amount_column = next(
        (
            c for c in [
                "amount", "open_amount", "invoice_amount",
                "amount_due", "balance",
            ]
            if c in receivables.columns
        ),
        None,
    )

    if amount_column is None:
        return None

    open_mask = receivables["status"].astype(str).str.startswith("open")
    return float(receivables.loc[open_mask, amount_column].sum())

def recompute_credit_card_debt(credit_card: pd.DataFrame) -> float:
    """
    Recompute the closing credit-card debt: the running balance on
    the most recent transaction date in the credit card table --
    same logic as the checking account's closing balance, since
    both tables track a running "balance" column the same way.
    """

    last_row = credit_card.sort_values("date").iloc[-1]
    return float(last_row["balance"])


def recompute_cash_collected_revenue(checking_main: pd.DataFrame) -> float:
    """
    Recompute total cash-collected revenue: the sum of every Credit
    (money coming in) transaction categorised as sales revenue.

    ASSUMPTION: every sales-related inflow (retail AND B2B) is
    tagged with a category containing "sales" (case-insensitive) --
    confirmed present as "Sales Revenue" in the data. If B2B
    collections use a differently worded category elsewhere, the
    recomputed total will come out lower than the stored value --
    tell me the real category name if that happens and I'll widen
    the match.
    """

    mask = (
        (checking_main["type"] == "Credit")
        & (checking_main["category"].str.contains("sales", case=False, na=False))
    )

    return float(checking_main.loc[mask, "amount"].sum())


def validate_kpi(
    label: str, stored_value_str: str, recomputed_value: float | None,
    tolerance: float = 1.0,
) -> dict:
    """
    Compare one stored KPI value against its recomputed value and
    report whether they match.

    WHY a tolerance (default 1 EUR) instead of exact equality: the
    stored value may have gone through its own rounding somewhere
    in the pipeline. A 1 EUR tolerance is tight enough to catch a
    real bug, generous enough to absorb harmless rounding noise.
    """

    if recomputed_value is None:
        return {
            "label": label,
            "stored": stored_value_str,
            "recomputed": None,
            "match": None,  # could not verify, not a pass or fail
        }

    stored_value = parse_eur_value(stored_value_str)
    match = abs(stored_value - recomputed_value) <= tolerance

    return {
        "label": label,
        "stored": stored_value,
        "recomputed": round(recomputed_value, 2),
        "match": match,
    }


def validate_runway(monthly: pd.DataFrame, stored_runway_text: str) -> dict:
    """
    Runway is stored as descriptive text, not a plain number -- but
    it's still derived from something computable: whether the
    recent 3-month average net cash flow is positive or negative
    (the same logic already used for the "3-Month Cash Trend" card
    on Overview).

    We can't compare an exact figure here, but we CAN check that
    the stored wording is logically consistent with what the
    underlying trend actually says -- e.g. text mentioning "not
    burning cash" should only appear when the recomputed trend is
    genuinely positive.
    """

    recent_avg = float(
        monthly.sort_values("month").tail(3)["net_cash_flow"].mean()
    )
    is_positive_trend = recent_avg >= 0

    text_says_not_burning = "not burning" in stored_runway_text.lower()

    consistent = is_positive_trend == text_says_not_burning

    return {
        "label": "Runway",
        "stored": stored_runway_text,
        "recomputed_trend": "Positive" if is_positive_trend else "Negative",
        "recomputed_avg": round(recent_avg, 2),
        "match": consistent,
    }
    
        
    
def run_all_kpi_validations(dataset_dir) -> list[dict]:
    """
    Recompute and validate every KPI we have a trusted source table
    for, and return one result per KPI.

    WHY this exists: the Streamlit page needs one function to call,
    not six separate recompute+compare calls scattered through the
    page code.
    """

    gold_path = dataset_dir / "gold"
    silver_path = dataset_dir / "silver"

    kpi_summary = pd.read_csv(gold_path / "gold_kpi_summary.csv")
    kpi_map = dict(zip(kpi_summary["kpi"], kpi_summary["value"]))

    daily = pd.read_csv(gold_path / "gold_daily_cash_position.csv", parse_dates=["date"])
    monthly = pd.read_csv(gold_path / "gold_monthly_cash_flow.csv")
    receivables = pd.read_csv(gold_path / "gold_receivables_aging.csv")
    credit_card = pd.read_csv(silver_path / "fact_credit_card.csv", parse_dates=["date"])
    checking_main = pd.read_csv(silver_path / "fact_checking_main.csv")

    results = [
        validate_kpi(
            "Closing cash balance",
            kpi_map.get("Consolidated Cash Balance (end of period)", ""),
            recompute_closing_cash_balance(daily),
        ),
        validate_kpi(
            "Average Monthly Net Cash Flow",
            kpi_map.get("Average Monthly Net Cash Flow", ""),
            recompute_average_monthly_net_cash_flow(monthly),
        ),
        validate_kpi(
            "Open Receivables",
            kpi_map.get("Open Receivables", ""),
            recompute_open_receivables(receivables),
        ),
        validate_kpi(
            "Credit Card Debt",
            kpi_map.get("Credit Card Debt (end of period)", ""),
            recompute_credit_card_debt(credit_card),
        ),
        validate_kpi(
            "Cash-Collected Revenue (24 months)",
            kpi_map.get("Cash-Collected Revenue (24 months)", ""),
            recompute_cash_collected_revenue(checking_main),
        ),
        validate_runway(
            monthly,
            kpi_map.get("Runway", ""),
        ),
    ]

    return results