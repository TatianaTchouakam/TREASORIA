"""
Structured SQL query engine for Treasoria.

This module handles financial questions that require exact
calculations over the Code & Coffee GmbH SQLite database.

The SQL layer complements the RAG system:
- SQL -> exact structured calculations
- RAG -> explanations and documentary context
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


# ============================================================
# PATH CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_PATH = PROJECT_ROOT / "data"

DATASET_PATH = (
    DATA_PATH
    / "Treasoria_Datasets_Code_and_Coffee"
)

DATABASE_PATH = DATASET_PATH / "treasoria.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection() -> sqlite3.Connection:
    """
    Return a read-only connection to the Treasoria database.

    Read-only mode prevents the Financial Assistant from
    accidentally modifying the underlying financial data.
    """

    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "Treasoria SQLite database not found at: "
            f"{DATABASE_PATH}"
        )

    database_uri = (
        f"file:{DATABASE_PATH.as_posix()}?mode=ro"
    )

    connection = sqlite3.connect(
        database_uri,
        uri=True,
    )

    return connection


# ============================================================
# SAFE SQL EXECUTION
# ============================================================

def execute_query(
    query: str,
    params: tuple = (),
) -> pd.DataFrame:
    """
    Execute a read-only SELECT query.

    Parameters
    ----------
    query:
        SQL SELECT statement.

    params:
        Optional SQL parameters.

    Returns
    -------
    pandas.DataFrame
        Query result.
    """

    cleaned_query = query.strip().lower()

    if not cleaned_query.startswith("select"):
        raise ValueError(
            "Treassoria SQL engine only allows SELECT queries."
        )

    with get_connection() as connection:
        result = pd.read_sql_query(
            query,
            connection,
            params=params,
        )

    return result


# ============================================================
# DATABASE INFORMATION
# ============================================================

def get_table_names() -> list[str]:
    """
    Return all tables available in treasoria.db.
    """

    query = """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
    """

    result = execute_query(query)

    return result["name"].tolist()


# ============================================================
# CUSTOMER RECEIVABLES
# ============================================================

def get_overdue_customer_invoice_count() -> int:
    """
    Return the number of currently overdue customer invoices.
    """

    query = """
        SELECT COUNT(*) AS overdue_invoice_count
        FROM fact_customer_invoice
        WHERE status = 'open_overdue'
    """

    result = execute_query(query)

    return int(
        result.iloc[0]["overdue_invoice_count"]
    )


def get_open_customer_invoice_count() -> int:
    """
    Return the number of customer invoices that remain unpaid.
    """

    query = """
        SELECT COUNT(*) AS open_invoice_count
        FROM fact_customer_invoice
        WHERE payment_date IS NULL
    """

    result = execute_query(query)

    return int(
        result.iloc[0]["open_invoice_count"]
    )


def get_open_receivables() -> float:
    """
    Return the total amount of unpaid customer invoices.
    """

    query = """
        SELECT COALESCE(
            SUM(amount),
            0
        ) AS open_receivables
        FROM fact_customer_invoice
        WHERE payment_date IS NULL
    """

    result = execute_query(query)

    return float(
        result.iloc[0]["open_receivables"]
    )


def get_average_customer_collection_time() -> float:
    """
    Calculate the average number of days between invoice
    issue and payment for paid B2B customer invoices.
    """

    query = """
        SELECT AVG(
            julianday(payment_date)
            - julianday(issue_date)
        ) AS average_collection_days
        FROM fact_customer_invoice
        WHERE payment_date IS NOT NULL
    """

    result = execute_query(query)

    value = result.iloc[0][
        "average_collection_days"
    ]

    return float(value)


def get_late_customer_invoice_count() -> int:
    """
    Return the number of customer invoices paid late.
    """

    query = """
        SELECT COUNT(*) AS late_invoice_count
        FROM fact_customer_invoice
        WHERE status = 'paid_late'
    """

    result = execute_query(query)

    return int(
        result.iloc[0]["late_invoice_count"]
    )


# ============================================================
# CASH FLOW
# ============================================================

def get_ending_cash_balance() -> float:
    """
    Return the most recent consolidated cash balance.
    """

    query = """
        SELECT consolidated_cash_balance
        FROM gold_daily_cash_position
        ORDER BY date DESC
        LIMIT 1
    """

    result = execute_query(query)

    return float(
        result.iloc[0][
            "consolidated_cash_balance"
        ]
    )


def get_total_net_cash_flow() -> float:
    """
    Return cumulative net cash flow for the entire period.
    """

    query = """
        SELECT SUM(net_cash_flow)
            AS cumulative_net_cash_flow
        FROM gold_monthly_cash_flow
    """

    result = execute_query(query)

    return float(
        result.iloc[0][
            "cumulative_net_cash_flow"
        ]
    )


def get_average_monthly_net_cash_flow() -> float:
    """
    Return average monthly net cash flow.
    """

    query = """
        SELECT AVG(net_cash_flow)
            AS average_net_cash_flow
        FROM gold_monthly_cash_flow
    """

    result = execute_query(query)

    return float(
        result.iloc[0][
            "average_net_cash_flow"
        ]
    )


def get_negative_cash_flow_month_count() -> int:
    """
    Return the number of months with negative net cash flow.
    """

    query = """
        SELECT COUNT(*) AS negative_months
        FROM gold_monthly_cash_flow
        WHERE net_cash_flow < 0
    """

    result = execute_query(query)

    return int(
        result.iloc[0]["negative_months"]
    )


def get_lowest_cash_flow_month() -> pd.Series:
    """
    Return the month with the lowest net cash flow.
    """

    query = """
        SELECT
            month,
            cash_in,
            cash_out_total,
            net_cash_flow
        FROM gold_monthly_cash_flow
        ORDER BY net_cash_flow ASC
        LIMIT 1
    """

    result = execute_query(query)

    return result.iloc[0]

def get_liquidity_risk_summary() -> dict:
    """
    Computes the full liquidity risk assessment on demand, reusing
    exactly the same logic as the Liquidity Risk page -- not a
    separate or simplified version.
    """

    from src.forecast_display import load_forecast
    from src.liquidity_risk import run_all_liquidity_checks

    forecast = load_forecast(Path("."), "daily")

    monthly = pd.read_csv(DATASET_PATH / "gold" / "gold_monthly_cash_flow.csv")
    monthly["month"] = pd.to_datetime(monthly["month"])

    transactions = pd.read_csv(
        DATASET_PATH / "silver" / "fact_checking_main.csv",
        parse_dates=["date"],
    )
    customer_invoices = pd.read_csv(
        DATASET_PATH / "silver" / "fact_customer_invoice.csv"
    )

    return run_all_liquidity_checks(
        forecast_df=forecast,
        monthly_df=monthly,
        transactions_df=transactions,
        customer_invoices_df=customer_invoices,
        average_monthly_outflow=17008.75,
    )




def get_top_expense_category() -> pd.Series:
    """
    Return the expense category with the highest total spending,
    based on supplier invoices.
    """

    query = """
        SELECT category, SUM(amount) AS total
        FROM fact_supplier_invoice
        GROUP BY category
        ORDER BY total DESC
        LIMIT 1
    """

    result = execute_query(query)

    return result.iloc[0]


def get_top_revenue_category() -> pd.Series:
    """
    Return the category bringing in the most money, based on
    incoming (Credit) transactions in the main checking account.
    """

    query = """
        SELECT category, SUM(amount) AS total
        FROM fact_checking_main
        WHERE type = 'Credit'
        GROUP BY category
        ORDER BY total DESC
        LIMIT 1
    """

    result = execute_query(query)

    return result.iloc[0]

def get_top_selling_product() -> pd.Series:
    """
    Return the best-selling product by estimated revenue.

    NOTE: this table (fact_product_sales) is synthetic -- a
    plausible revenue breakdown estimated from the real, known
    total Sales Revenue figure, not actual per-product transaction
    history. See data_origin column.
    """

    query = """
        SELECT product_name, category, estimated_revenue
        FROM fact_product_sales
        ORDER BY estimated_revenue DESC
        LIMIT 1
    """

    result = execute_query(query)

    return result.iloc[0]


# ============================================================
# KPI LOOKUP
# ============================================================

def get_kpi_summary() -> pd.DataFrame:
    """
    Return the complete Treasoria KPI summary table.
    """

    query = """
        SELECT *
        FROM gold_kpi_summary
    """

    return execute_query(query)


# ============================================================
# SIMPLE INTENT ROUTER
# ============================================================

def detect_sql_intent(
    question: str,
) -> str | None:
    """
    Detect structured financial questions that should be
    answered through SQLite instead of document retrieval.

    This first version intentionally uses deterministic rules.
    """

    q = question.lower().strip()

    if (
        "how many" in q
        and "invoice" in q
        and "overdue" in q
    ):
        return "overdue_customer_invoices"

    if (
        "how many" in q
        and "invoice" in q
        and (
            "unpaid" in q
            or "open" in q
        )
    ):
        return "open_customer_invoices"

    if (
        "open receivables" in q
        or "unpaid receivables" in q
        or "outstanding receivables" in q
    ):
        return "open_receivables"

    if (
        "average customer collection time"
        in q
        or "average collection time" in q
    ):
        return "average_collection_time"

    if (
        "how many" in q
        and "invoice" in q
        and "paid late" in q
    ):
        return "late_customer_invoices"

    if (
        "current cash balance" in q
        or "ending cash balance" in q
        or "current consolidated cash" in q
    ):
        return "ending_cash_balance"

    if (
        "average monthly net cash flow" in q
    ):
        return "average_monthly_cash_flow"

    if (
        "cumulative net cash flow" in q
        or "total net cash flow" in q
    ):
        return "cumulative_cash_flow"

    if (
        "how many" in q
        and "negative" in q
        and "month" in q
    ):
        return "negative_cash_flow_months"

    if (
        "lowest cash flow" in q
        or "worst cash flow" in q
        or "worst month" in q
    ):
        return "lowest_cash_flow_month"

    if (
        "cost" in q
        and ("most" in q or "highest" in q)
        and (
            "category" in q
            or "product" in q
            or "expense" in q
        )
    ):
        return "top_expense_category"

    if (
        ("bring" in q or "earn" in q or "make" in q)
        and ("most" in q or "highest" in q)
        and (
            "money" in q
            or "revenue" in q
            or "category" in q
            or "product" in q
        )
    ):
        return "top_revenue_category"
    
    if (
        "product" in q
        and ("best" in q or "top" in q or "most" in q)
        and ("sell" in q or "selling" in q or "popular" in q)
    ):
        return "top_selling_product"
    if (
        "liquidity risk" in q
        or "cash risk" in q
        or "am i at risk" in q
        or "financial risk" in q
    ):
        return "liquidity_risk_summary"
    return None   
    


# ============================================================
# STRUCTURED ANSWER GENERATION
# ============================================================

def answer_sql_question(
    question: str,
) -> str | None:
    """
    Answer a recognised structured financial question.

    Returns None when the question should fall back to RAG.
    """

    intent = detect_sql_intent(question)

    if intent is None:
        return None

    if intent == "overdue_customer_invoices":
        count = get_overdue_customer_invoice_count()

        noun = (
            "invoice"
            if count == 1
            else "invoices"
        )

        return (
            "Code & Coffee GmbH currently has "
            f"{count} overdue customer {noun}."
        )

    if intent == "open_customer_invoices":
        count = get_open_customer_invoice_count()

        noun = (
            "invoice"
            if count == 1
            else "invoices"
        )

        return (
            "Code & Coffee GmbH currently has "
            f"{count} unpaid customer {noun}."
        )

    if intent == "open_receivables":
        amount = get_open_receivables()

        return (
            "Code & Coffee GmbH has "
            f"EUR {amount:,.2f} in open receivables."
        )

    if intent == "average_collection_time":
        days = (
            get_average_customer_collection_time()
        )

        return (
            "The average customer collection time "
            f"is {days:.1f} days."
        )

    if intent == "late_customer_invoices":
        count = get_late_customer_invoice_count()

        noun = (
            "invoice"
            if count == 1
            else "invoices"
        )

        return (
            f"{count} customer {noun} "
            "were paid late."
        )

    if intent == "ending_cash_balance":
        balance = get_ending_cash_balance()

        return (
            "The current consolidated cash balance "
            "for Code & Coffee GmbH is "
            f"EUR {balance:,.2f}."
        )

    if intent == "average_monthly_cash_flow":
        value = (
            get_average_monthly_net_cash_flow()
        )

        return (
            "The average monthly net cash flow is "
            f"EUR {value:,.2f}."
        )

    if intent == "cumulative_cash_flow":
        value = get_total_net_cash_flow()

        return (
            "Cumulative net cash flow is "
            f"EUR {value:,.2f}."
        )

    if intent == "negative_cash_flow_months":
        count = (
            get_negative_cash_flow_month_count()
        )

        return (
            f"{count} out of 24 months had "
            "negative net cash flow."
        )

    if intent == "lowest_cash_flow_month":
        row = get_lowest_cash_flow_month()

        return (
            "The month with the lowest net cash flow "
            f"was {row['month']}, with net cash flow "
            f"of EUR {row['net_cash_flow']:,.2f}."
        )
    if intent == "top_expense_category":
        row = get_top_expense_category()

        return (
            f"Your biggest expense category is {row['category']}, "
            f"at EUR {row['total']:,.2f} total."
        )

    if intent == "top_revenue_category":
        row = get_top_revenue_category()

        return (
            f"Your top revenue category is {row['category']}, "
            f"bringing in EUR {row['total']:,.2f} total."
        )
    if intent == "top_selling_product":
        row = get_top_selling_product()

        return (
            f"Your best-selling product is {row['product_name']} "
            f"({row['category']}), with an estimated "
            f"EUR {row['estimated_revenue']:,.2f} in revenue."
        )
    if intent == "liquidity_risk_summary":
        result = get_liquidity_risk_summary()

        lines = [f"Your overall liquidity status is {result['overall_severity']} {result['overall_icon']}."]
        concerning = [s for s in result["signals"] if s["severity"] != "Stable"]

        if concerning:
            lines.append("Here's what's worth your attention:")
            for s in concerning:
                lines.append(f"- {s['signal']}: {s['justification']}")
        else:
            lines.append("Everything looks stable right now.")

        return "\n".join(lines)
    return None
   


# ============================================================
# MANUAL TEST
# ============================================================

if __name__ == "__main__":

    print(
        "Database:",
        DATABASE_PATH,
    )

    print(
        "Tables:",
        get_table_names(),
    )

    test_questions = [
        "How many customer invoices are overdue?",
        "What are the open receivables?",
        "What is the average customer collection time?",
        "What is the current cash balance?",
        "How many months had negative cash flow?",
        "Which month had the lowest cash flow?",
    ]

    print("\n--- SQL ENGINE TEST ---")

    for question in test_questions:

        print(
            f"\nQuestion: {question}"
        )

        print(
            "Answer:",
            answer_sql_question(question),
        )