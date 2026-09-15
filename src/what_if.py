"""
Treasoria — What-if Simulator

Translates 6 plain-language business scenarios into dated cash-flow
adjustments, using Aysenur's own tested integration functions
(apply_cash_flow_adjustments, summarize_cash_risk) rather than
reimplementing the shifting logic.

Each scenario function returns a list of {"date", "net_flow_delta_eur"}
rows ready to pass into apply_cash_flow_adjustments -- the actual
simulation always goes through that one tested function.
"""

import pandas as pd


def scenario_customer_payment_delay(
    forecast: pd.DataFrame, amount: float, delay_days: int, original_date_index: int = 10
) -> pd.DataFrame:
    """
    A customer payment of `amount` EUR, expected around day
    `original_date_index` of the forecast, arrives `delay_days`
    later instead.
    """

    dates = forecast["date"].reset_index(drop=True)
    original_date = dates.iloc[original_date_index]

    new_index = min(original_date_index + delay_days, len(dates) - 1)
    new_date = dates.iloc[new_index]

    return pd.DataFrame(
        {
            "date": [original_date, new_date],
            "net_flow_delta_eur": [-amount, amount],
        }
    )


def scenario_expense_increase(
    forecast: pd.DataFrame, extra_monthly_amount: float, start_date_index: int = 0
) -> pd.DataFrame:
    """
    An extra recurring cost of `extra_monthly_amount` EUR per month,
    starting from `start_date_index` in the forecast, spread evenly
    across the remaining daily periods.
    """

    dates = forecast["date"].reset_index(drop=True).iloc[start_date_index:]
    daily_amount = extra_monthly_amount / 30.0

    return pd.DataFrame(
        {
            "date": dates,
            "net_flow_delta_eur": [-daily_amount] * len(dates),
        }
    )


def scenario_sales_decrease(
    forecast: pd.DataFrame, less_monthly_amount: float, start_date_index: int = 0
) -> pd.DataFrame:
    """
    Less money coming in, by `less_monthly_amount` EUR per month,
    starting from `start_date_index`.
    """

    return scenario_expense_increase(forecast, less_monthly_amount, start_date_index)


def scenario_new_hire(
    forecast: pd.DataFrame, monthly_salary: float, start_date_index: int = 0
) -> pd.DataFrame:
    """
    A new hire's monthly salary, starting from `start_date_index`.
    Same shape as a recurring extra expense.
    """

    return scenario_expense_increase(forecast, monthly_salary, start_date_index)


def scenario_equipment_purchase(
    forecast: pd.DataFrame, cost: float, purchase_date_index: int = 0
) -> pd.DataFrame:
    """
    A one-time equipment purchase of `cost` EUR, on a specific date.
    """

    dates = forecast["date"].reset_index(drop=True)
    purchase_date = dates.iloc[purchase_date_index]

    return pd.DataFrame(
        {
            "date": [purchase_date],
            "net_flow_delta_eur": [-cost],
        }
    )


def scenario_loan_repayment(
    forecast: pd.DataFrame, monthly_payment: float, start_date_index: int, num_months: int
) -> pd.DataFrame:
    """
    A loan repayment of `monthly_payment` EUR per month, for
    `num_months` months, starting from `start_date_index`.
    """

    dates = forecast["date"].reset_index(drop=True)
    end_index = min(start_date_index + num_months * 30, len(dates))
    active_dates = dates.iloc[start_date_index:end_index]

    daily_amount = monthly_payment / 30.0

    return pd.DataFrame(
        {
            "date": active_dates,
            "net_flow_delta_eur": [-daily_amount] * len(active_dates),
        }
    )

def scenario_product_change(
    forecast: pd.DataFrame,
    product_monthly_revenue: float,
    change_pct: float,
    start_date_index: int,
    num_months: int,
) -> pd.DataFrame:
    """
    A product's revenue changes by `change_pct` percent per month,
    for `num_months` months, starting from `start_date_index`.

    `product_monthly_revenue` is the product's average monthly
    revenue -- its total estimated revenue divided by the number
    of months represented in the historical dataset.
    """

    monthly_delta = product_monthly_revenue * (change_pct / 100.0)
    daily_delta = monthly_delta / 30.0

    dates = forecast["date"].reset_index(drop=True)
    end_index = min(start_date_index + num_months * 30, len(dates))
    active_dates = dates.iloc[start_date_index:end_index]

    return pd.DataFrame(
        {
            "date": active_dates,
            "net_flow_delta_eur": [daily_delta] * len(active_dates),
        }
    )

def build_summary_sentence(
    baseline_summary: dict, scenario_summary: dict
) -> str:
    """
    Turns the two numeric summaries into one plain-language sentence,
    for a non-technical reader.
    """

    balance_change = (
        scenario_summary["minimum_projected_balance"]
        - baseline_summary["minimum_projected_balance"]
    )

    direction = "tighter" if balance_change < 0 else "more comfortable"

    days_change = (
        scenario_summary["days_below_threshold"]
        - baseline_summary["days_below_threshold"]
    )

    if days_change > 0:
        risk_note = (
            f" You'd also spend {days_change} more day(s) below your "
            "safe cash level."
        )
    else:
        risk_note = " You'd stay within your safe cash level throughout."

    return (
        f"This would leave you about EUR {abs(balance_change):,.2f} "
        f"{direction} at your lowest point "
        f"(around {scenario_summary['low_point_period_end']})."
        f"{risk_note}"
    )