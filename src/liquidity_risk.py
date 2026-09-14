"""
Treasoria — Liquidity Risk engine

Turns the forecast and known financial data into 6 concrete,
defined risk signals: Low Balance, Cash Running Out Soon,
Unexpected Big Expense, Negative Trend, High Uncertainty,
Relying on One Customer.

Per the forecast pipeline's own handoff notes: "There is no
invented universal risk limit." Every threshold here is explicit
and documented below, not arbitrary:

- Low Balance / Cash Running Out Soon: months of average monthly
  spending remaining -- a standard treasury/CFO practice, applied
  to Code & Coffee GmbH's own real average monthly outflow.
- Unexpected Big Expense: a z-score (how many standard deviations
  above its own category's historical average) -- a standard
  statistical anomaly-detection method, not a guessed EUR figure.
  Verified against this dataset's own documented events: the
  EUR 19,500 cooler replacement (z=8.69) and EUR 8,500 storm damage
  (z=3.62) both surface correctly with this method. The z-score
  itself is used only internally to decide severity -- the text
  shown to the user describes the finding in plain language, not
  the statistic.
- Negative Trend: comparing the most recent 3-month average net
  cash flow against the 3 months before that.
- High Uncertainty: the width of the forecast's own uncertainty
  band (cash_balance_upper minus cash_balance_lower), relative to
  the current balance -- reusing Aysenur's own forecast output
  rather than inventing a separate uncertainty measure.
- Relying on One Customer: the top customer's share of total
  invoice revenue from business customers.

Each signal reports: severity, amount, date (where applicable),
justification, and a suggested action. All user-facing text
(signal titles included) is written in plain, everyday language --
no financial or statistical jargon (no "z-score", "runway",
"outflow", "concentration", "credit line", "B2B", "critical
threshold", etc.) since this is read by a non-technical business
owner, not an analyst.
"""

import pandas as pd


ATTENTION_MONTHS = 3.0
RISK_MONTHS = 1.5

UNUSUAL_OUTFLOW_ATTENTION_Z = 2.0
UNUSUAL_OUTFLOW_RISK_Z = 3.5

UNCERTAINTY_ATTENTION_PCT = 10.0
UNCERTAINTY_RISK_PCT = 20.0

CONCENTRATION_ATTENTION_PCT = 25.0
CONCENTRATION_RISK_PCT = 40.0


def evaluate_low_balance(
    forecast_df: pd.DataFrame, average_monthly_outflow: float
) -> dict:
    """
    Compares the lowest balance expected over the forecast horizon
    against 3 months (Attention) and 1.5 months (Risk) of the
    company's own real average monthly spending.
    """

    min_row = forecast_df.loc[forecast_df["projected_cash_balance"].idxmin()]
    min_balance = float(min_row["projected_cash_balance"])
    min_date = min_row["date"]

    attention_threshold = average_monthly_outflow * ATTENTION_MONTHS
    risk_threshold = average_monthly_outflow * RISK_MONTHS

    if min_balance < risk_threshold:
        severity = "Risk"
        justification = (
            f"Your cash could drop to around EUR {min_balance:,.2f}, "
            f"which is less than {RISK_MONTHS} months of what you "
            "normally spend."
        )
        action = "Look at what you're about to pay, and consider putting off anything that isn't urgent."
    elif min_balance < attention_threshold:
        severity = "Attention"
        justification = (
            f"Your cash could drop to around EUR {min_balance:,.2f}, "
            f"which is less than {ATTENTION_MONTHS} months of what you "
            "normally spend."
        )
        action = "Keep an eye on this and think ahead about what you'd do if it gets tighter."
    else:
        severity = "Stable"
        justification = (
            f"Your cash stays comfortably above {ATTENTION_MONTHS} "
            "months of what you normally spend."
        )
        action = "No action needed."

    return {
        "signal": "Low Balance",
        "severity": severity,
        "amount": round(min_balance, 2),
        "date": min_date.strftime("%B %d, %Y"),
        "justification": justification,
        "suggested_action": action,
    }


def evaluate_short_runway(
    forecast_df: pd.DataFrame, average_monthly_outflow: float
) -> dict:
    """
    Counts how many days in the forecast horizon fall below the
    critical (Risk-level) threshold, and identifies the first date
    it happens.
    """

    risk_threshold = average_monthly_outflow * RISK_MONTHS
    below_threshold = forecast_df[
        forecast_df["projected_cash_balance"] < risk_threshold
    ]

    days_below = len(below_threshold)

    if days_below == 0:
        return {
            "signal": "Cash Running Out Soon",
            "severity": "Stable",
            "amount": 0,
            "date": None,
            "justification": "Your cash is not expected to run low at any point in the next 90 days.",
            "suggested_action": "No action needed.",
        }

    first_breach_date = below_threshold["date"].min()

    severity = "Risk" if days_below >= 14 else "Attention"

    return {
        "signal": "Cash Running Out Soon",
        "severity": severity,
        "amount": days_below,
        "date": first_breach_date.strftime("%B %d, %Y"),
        "justification": (
            f"Your cash is expected to run low for {days_below} day(s), "
            f"starting around this date."
        ),
        "suggested_action": "Follow up on unpaid invoices, or talk to your bank about extra support before this date.",
    }


def find_unusual_outflows(
    transactions_df: pd.DataFrame, z_threshold: float = UNUSUAL_OUTFLOW_ATTENTION_Z
) -> list[dict]:
    """
    Flags transactions that are unusually large relative to their
    own category's historical average. Uses a z-score internally
    (how many standard deviations above the category's normal
    range) purely as a detection method -- this technical detail is
    never shown to the end user, only the plain-language finding.
    """

    category_stats = (
        transactions_df.groupby("category")["amount"]
        .agg(["mean", "std"])
        .to_dict("index")
    )

    flagged = []

    for _, row in transactions_df.iterrows():
        stats = category_stats.get(row["category"])
        if stats is None or pd.isna(stats["std"]) or stats["std"] == 0:
            continue

        z_score = (row["amount"] - stats["mean"]) / stats["std"]

        if z_score > z_threshold:
            flagged.append(
                {
                    "date": row["date"],
                    "category": row["category"],
                    "amount": float(row["amount"]),
                    "z_score": round(float(z_score), 2),
                }
            )

    return sorted(flagged, key=lambda x: x["z_score"], reverse=True)


def evaluate_unusual_outflow(transactions_df: pd.DataFrame) -> dict:
    """
    Reports the single most unusual outflow found, as the
    Liquidity Risk signal for this category.
    """

    flagged = find_unusual_outflows(transactions_df)

    if not flagged:
        return {
            "signal": "Unexpected Big Expense",
            "severity": "Stable",
            "amount": 0,
            "date": None,
            "justification": "No unusually large expenses found.",
            "suggested_action": "No action needed.",
        }

    top = flagged[0]
    severity = "Risk" if top["z_score"] >= UNUSUAL_OUTFLOW_RISK_Z else "Attention"

    return {
        "signal": "Unexpected Big Expense",
        "severity": severity,
        "amount": round(top["amount"], 2),
        "date": top["date"].strftime("%B %d, %Y"),
        "justification": (
            f"Your {top['category']} spending on this date "
            f"(EUR {top['amount']:,.2f}) was much higher than usual "
            "for that category."
        ),
        "suggested_action": "Check that this was expected, and find out what caused it.",
    }


def evaluate_negative_trend(monthly_df: pd.DataFrame) -> dict:
    """
    Compares the most recent 3-month average net cash flow against
    the 3 months before that, to detect a worsening trend even if
    the recent average is still positive.
    """

    sorted_monthly = monthly_df.sort_values("month").tail(6)

    first_half_avg = float(sorted_monthly.iloc[:3]["net_cash_flow"].mean())
    second_half_avg = float(sorted_monthly.iloc[3:]["net_cash_flow"].mean())

    is_worsening = second_half_avg < first_half_avg
    change = abs(second_half_avg - first_half_avg)

    if second_half_avg < 0 and is_worsening:
        severity = "Risk"
        justification = (
            f"Your monthly cash flow is negative and getting worse — "
            f"down by about EUR {change:,.2f} a month compared to a "
            "few months ago."
        )
        action = "Look into what's causing this, and cut back on spending that isn't essential."
    elif is_worsening:
        severity = "Attention"
        justification = (
            f"Your monthly cash flow is weaker than it was — down by "
            f"about EUR {change:,.2f} a month compared to a few months "
            "ago, though still positive."
        )
        action = "Keep watching this over the next few months."
    else:
        severity = "Stable"
        justification = "Your monthly cash flow is steady or improving."
        action = "No action needed."

    return {
        "signal": "Negative Trend",
        "severity": severity,
        "amount": round(second_half_avg, 2),
        "date": sorted_monthly.iloc[-1]["month"].strftime("%B %Y"),
        "justification": justification,
        "suggested_action": action,
    }


def evaluate_high_uncertainty(forecast_df: pd.DataFrame) -> dict:
    """
    Measures the width of the forecast's own uncertainty band at
    the end of the horizon, relative to the current balance --
    reuses Aysenur's forecast output rather than a separate
    uncertainty calculation.
    """

    last_row = forecast_df.sort_values("date").iloc[-1]
    band_width = float(last_row["cash_balance_upper"] - last_row["cash_balance_lower"])
    starting_balance = float(forecast_df.iloc[0]["starting_cash_balance"])

    band_pct = (band_width / starting_balance) * 100 if starting_balance else 0

    if band_pct >= UNCERTAINTY_RISK_PCT:
        severity = "Risk"
        action = "Treat this forecast as a rough guide, not an exact number — avoid decisions that only work if it's precisely right."
    elif band_pct >= UNCERTAINTY_ATTENTION_PCT:
        severity = "Attention"
        action = "Check back on this forecast again as more recent numbers come in."
    else:
        severity = "Stable"
        action = "No action needed."

    return {
        "signal": "High Uncertainty",
        "severity": severity,
        "amount": round(band_width, 2),
        "date": last_row["date"].strftime("%B %d, %Y"),
        "justification": (
            f"Your future cash could end up as much as "
            f"EUR {band_width:,.2f} higher or lower than expected by "
            "the end of this period."
        ),
        "suggested_action": action,
    }


def evaluate_customer_concentration(customer_invoices_df: pd.DataFrame) -> dict:
    """
    Measures the top customer's share of total invoice revenue from
    business customers.
    """

    totals = (
        customer_invoices_df.groupby("customer_name")["amount"]
        .sum()
        .sort_values(ascending=False)
    )

    grand_total = totals.sum()
    top_customer = totals.index[0]
    top_amount = float(totals.iloc[0])
    top_share = (top_amount / grand_total) * 100 if grand_total else 0

    if top_share >= CONCENTRATION_RISK_PCT:
        severity = "Risk"
        action = f"Try to bring in more customers so you rely less on {top_customer}."
    elif top_share >= CONCENTRATION_ATTENTION_PCT:
        severity = "Attention"
        action = "Keep this relationship strong, and start looking for new customers too."
    else:
        severity = "Stable"
        action = "No action needed."

    return {
        "signal": "Relying on One Customer",
        "severity": severity,
        "amount": round(top_amount, 2),
        "date": None,
        "justification": (
            f"{top_customer} makes up {top_share:.1f}% of the money you "
            "get from business customers."
        ),
        "suggested_action": action,
    }


def run_all_liquidity_checks(
    forecast_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    transactions_df: pd.DataFrame,
    customer_invoices_df: pd.DataFrame,
    average_monthly_outflow: float,
) -> dict:
    """
    Runs all 6 liquidity risk signals and combines them into one
    overall status -- the worst individual severity found, since a
    single serious warning shouldn't be diluted by five calm ones.
    """

    signals = [
        evaluate_low_balance(forecast_df, average_monthly_outflow),
        evaluate_short_runway(forecast_df, average_monthly_outflow),
        evaluate_unusual_outflow(transactions_df),
        evaluate_negative_trend(monthly_df),
        evaluate_high_uncertainty(forecast_df),
        evaluate_customer_concentration(customer_invoices_df),
    ]

    severity_rank = {"Stable": 0, "Attention": 1, "Risk": 2}
    overall_severity = max(signals, key=lambda s: severity_rank[s["severity"]])["severity"]
    overall_icon = {"Stable": "🟢", "Attention": "🟠", "Risk": "🔴"}[overall_severity]

    return {
        "overall_severity": overall_severity,
        "overall_icon": overall_icon,
        "signals": signals,
    }