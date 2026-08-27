"""Rebuild Treasoria Gold tables and the canonical SQLite database.

The script is deterministic: it reads the curated Silver CSV files and
recreates all Gold outputs and ``treasoria.db``. Internal transfers are
neutralised; credit-card repayments remain external cash outflows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / "silver"
GOLD = ROOT / "gold"
DB_PATH = ROOT / "treasoria.db"

COMPANY_ID = "code_and_coffee"
COMPANY_NAME = "Code & Coffee GmbH"
COMPANY_OWNER = "Blue Jesus"
COMPANY_ADDRESS = "Ravensberger Str. 22"
COMPANY_POSTAL_CODE = "33602"
COMPANY_CITY = "Bielefeld"
COMPANY_COUNTRY = "Germany"
COMPANY_SECTOR = "International Café & Gastronomy"


def load(name: str, date_columns: list[str]) -> pd.DataFrame:
    df = pd.read_csv(SILVER / name)

    for column in date_columns:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce",
        )

    return df


def money(value: float) -> str:
    return f"{value:,.2f} EUR"


def build() -> None:

    # -----------------------------------------------------------
    # LOAD SILVER TABLES
    # -----------------------------------------------------------

    main = load(
        "fact_checking_main.csv",
        ["date"],
    )

    secondary = load(
        "fact_checking_secondary.csv",
        ["date"],
    )

    card = load(
        "fact_credit_card.csv",
        ["date"],
    )

    payroll = load(
        "fact_payroll.csv",
        ["pay_date"],
    )

    customer = load(
        "fact_customer_invoice.csv",
        [
            "issue_date",
            "due_date",
            "payment_date",
        ],
    )

    supplier = load(
        "fact_supplier_invoice.csv",
        [
            "invoice_date",
            "due_date",
            "payment_date",
        ],
    )


    # -----------------------------------------------------------
    # DAILY CONSOLIDATED CASH POSITION
    # -----------------------------------------------------------

    # Consolidated cash contains the two bank-account balances.
    # Credit-card debt is reported separately as a liability.

    start = min(
        main["date"].min(),
        secondary["date"].min(),
    )

    end = max(
        main["date"].max(),
        secondary["date"].max(),
    )

    calendar = pd.date_range(
        start,
        end,
        freq="D",
    )


    def end_of_day(df: pd.DataFrame) -> pd.Series:

        ordered = df.sort_values(
            ["date", "transaction_id"]
        )

        return (
            ordered
            .groupby("date")
            .tail(1)
            .set_index("date")["balance"]
        )


    main_balance = (
        end_of_day(main)
        .reindex(calendar)
        .ffill()
    )

    secondary_balance = (
        end_of_day(secondary)
        .reindex(calendar)
        .ffill()
    )


    daily = pd.DataFrame(
        {
            "date": calendar,
            "checking_main_balance":
                main_balance.to_numpy(),
            "checking_secondary_balance":
                secondary_balance.to_numpy(),
        }
    )


    daily["consolidated_cash_balance"] = (
        daily["checking_main_balance"]
        + daily["checking_secondary_balance"]
    )


    # -----------------------------------------------------------
    # MONTHLY CONSOLIDATED CASH FLOW
    # -----------------------------------------------------------

    # Internal transfers between the two bank accounts are
    # excluded from consolidated cash flow.
    #
    # Credit-card repayments remain external cash outflows
    # because cash leaves the company's main bank account.

    main_work = main.copy()

    main_work["month"] = (
        main_work["date"]
        .dt.to_period("M")
        .astype(str)
    )


    secondary_work = secondary.copy()

    secondary_work["month"] = (
        secondary_work["date"]
        .dt.to_period("M")
        .astype(str)
    )


    months = pd.period_range(
        start=start,
        end=end,
        freq="M",
    ).astype(str)


    monthly = pd.DataFrame(
        index=months
    )

    monthly.index.name = "month"


    monthly["cash_in"] = (
        main_work.loc[
            main_work["type"].eq("Credit")
        ]
        .groupby("month")["amount"]
        .sum()
        .reindex(
            months,
            fill_value=0.0,
        )
    )


    monthly["cash_out_operating"] = (
        main_work.loc[
            main_work["type"].eq("Debit")
            & main_work["category"].isin(
                [
                    "COGS",
                    "Operating Expense",
                ]
            )
        ]
        .groupby("month")["amount"]
        .sum()
        .reindex(
            months,
            fill_value=0.0,
        )
    )


    monthly["cash_out_card_payments"] = (
        main_work.loc[
            main_work["type"].eq("Debit")
            & main_work["category"].eq(
                "Credit Card Payment"
            )
        ]
        .groupby("month")["amount"]
        .sum()
        .reindex(
            months,
            fill_value=0.0,
        )
    )


    monthly["cash_out_payroll"] = (
        secondary_work.loc[
            secondary_work["type"].eq("Debit")
            & secondary_work["category"].eq(
                "Payroll"
            )
        ]
        .groupby("month")["amount"]
        .sum()
        .reindex(
            months,
            fill_value=0.0,
        )
    )


    monthly["cash_out_total"] = monthly[
        [
            "cash_out_operating",
            "cash_out_card_payments",
            "cash_out_payroll",
        ]
    ].sum(axis=1)


    monthly["net_cash_flow"] = (
        monthly["cash_in"]
        - monthly["cash_out_total"]
    )


    monthly = monthly.reset_index()


    # -----------------------------------------------------------
    # RECEIVABLES AGING
    # -----------------------------------------------------------

    receivables = customer.copy()


    receivables["days_late"] = (
        receivables["payment_date"]
        - receivables["due_date"]
    ).dt.days


    receivables = receivables[
        [
            "invoice_id",
            "customer_name",
            "issue_date",
            "due_date",
            "amount",
            "status",
            "payment_date",
            "days_late",
        ]
    ].sort_values(
        [
            "due_date",
            "invoice_id",
        ]
    )


    # -----------------------------------------------------------
    # PAYABLES AGING
    # -----------------------------------------------------------

    payables = supplier.copy()


    payables["days_late_or_early"] = (
        payables["payment_date"]
        - payables["due_date"]
    ).dt.days


    payables = payables[
        [
            "invoice_id",
            "supplier_name",
            "category",
            "invoice_date",
            "due_date",
            "amount",
            "status",
            "payment_date",
            "days_late_or_early",
        ]
    ].sort_values(
        [
            "due_date",
            "invoice_id",
        ]
    )


    # -----------------------------------------------------------
    # PAYROLL SUMMARY
    # -----------------------------------------------------------

    payroll_work = payroll.copy()


    payroll_work["month"] = (
        payroll_work["pay_date"]
        .dt.to_period("M")
        .astype(str)
    )


    payroll_summary = (
        payroll_work
        .groupby(
            "month",
            as_index=False,
        )
        .agg(
            employees_paid=(
                "employee_id",
                "nunique",
            ),
            total_gross=(
                "gross_pay",
                "sum",
            ),
            total_net=(
                "net_pay",
                "sum",
            ),
            total_employer_cost=(
                "employer_total_cost",
                "sum",
            ),
        )
        .sort_values("month")
    )


    # -----------------------------------------------------------
    # KPI CALCULATIONS
    # -----------------------------------------------------------

    revenue = float(
        monthly["cash_in"].sum()
    )


    retail_revenue = float(
        main.loc[
            main["category"].eq(
                "Sales Revenue"
            ),
            "amount",
        ].sum()
    )


    b2b_revenue = float(
        main.loc[
            main["category"].eq(
                "B2B Sales Revenue"
            ),
            "amount",
        ].sum()
    )


    cogs = float(
        main.loc[
            main["category"].eq("COGS"),
            "amount",
        ].sum()
    )


    start_main_credit = (
        main.loc[
            main["date"].eq(start)
            & main["type"].eq("Credit"),
            "amount",
        ].sum()
    )


    start_main_debit = (
        main.loc[
            main["date"].eq(start)
            & main["type"].eq("Debit"),
            "amount",
        ].sum()
    )


    start_secondary_credit = (
        secondary.loc[
            secondary["date"].eq(start)
            & secondary["type"].eq("Credit"),
            "amount",
        ].sum()
    )


    start_secondary_debit = (
        secondary.loc[
            secondary["date"].eq(start)
            & secondary["type"].eq("Debit"),
            "amount",
        ].sum()
    )


    opening_cash = float(
        daily.iloc[0][
            "consolidated_cash_balance"
        ]
        - (
            (
                start_main_credit
                - start_main_debit
            )
            + (
                start_secondary_credit
                - start_secondary_debit
            )
        )
    )


    ending_cash = float(
        daily.iloc[-1][
            "consolidated_cash_balance"
        ]
    )


    net_total = float(
        monthly[
            "net_cash_flow"
        ].sum()
    )


    observed_outflow_avg = float(
        monthly[
            "cash_out_total"
        ].mean()
    )


    analytical_operating_avg = float(
        (
            cogs
            + main.loc[
                main["category"].eq(
                    "Operating Expense"
                ),
                "amount",
            ].sum()
            + card.loc[
                card["type"].eq("Debit"),
                "amount",
            ].sum()
            + payroll[
                "employer_total_cost"
            ].sum()
        )
        / len(monthly)
    )


    paid_customer = customer.loc[
        customer[
            "payment_date"
        ].notna()
    ].copy()


    average_collection_time = float(
        (
            paid_customer[
                "payment_date"
            ]
            - paid_customer[
                "issue_date"
            ]
        )
        .dt.days
        .mean()
    )


    late_rate = float(
        customer[
            "status"
        ]
        .eq("paid_late")
        .mean()
        * 100
    )


    open_receivables = float(
        customer.loc[
            customer[
                "payment_date"
            ].isna(),
            "amount",
        ].sum()
    )


    supplier_payment_time = float(
        (
            supplier[
                "payment_date"
            ]
            - supplier[
                "invoice_date"
            ]
        )
        .dt.days
        .mean()
    )


    card_liability = float(
        card
        .sort_values(
            [
                "date",
                "transaction_id",
            ]
        )
        .iloc[-1]["balance"]
    )


    # -----------------------------------------------------------
    # RUNWAY
    # -----------------------------------------------------------

    # Runway is calculated dynamically using the recent
    # three-month average net cash flow.
    #
    # If recent average net flow is negative, runway expresses
    # how many months the current cash position could support.
    #
    # If recent average net flow is positive, the business is
    # reported as not currently burning cash.

    recent_net = (
        monthly
        .tail(3)[
            "net_cash_flow"
        ]
    )


    recent_avg_net = float(
        recent_net.mean()
    )


    if recent_avg_net < 0:

        runway_value = (
            f"{ending_cash / abs(recent_avg_net):.1f} "
            f"months "
            f"(based on recent 3-month burn)"
        )

    else:

        runway_value = (
            "Not burning cash "
            "(positive 3-month average net flow)"
        )


    # -----------------------------------------------------------
    # KPI SUMMARY
    # -----------------------------------------------------------

    kpis = pd.DataFrame(
        [
            (
                "Cash-Collected Revenue (24 months)",
                money(revenue),
            ),
            (
                "of which retail sales",
                money(retail_revenue),
            ),
            (
                "of which B2B sales collected",
                money(b2b_revenue),
            ),
            (
                "Indicative Gross Margin "
                "(Cash-Collected Revenue - COGS)",
                f"{(revenue - cogs) / revenue:.1%}",
            ),
            (
                "Total Analytical Employer Cost "
                "(23 months)",
                money(
                    payroll[
                        "employer_total_cost"
                    ].sum()
                ),
            ),
            (
                "Opening Cash Balance "
                "(two accounts)",
                money(opening_cash),
            ),
            (
                "Consolidated Cash Balance "
                "(end of period)",
                money(ending_cash),
            ),
            (
                "Credit Card Debt "
                "(end of period)",
                money(card_liability),
            ),
            (
                "Average Observed Monthly "
                "Cash Outflows",
                money(observed_outflow_avg),
            ),
            (
                "Average Monthly Analytical "
                "Operating Costs",
                money(analytical_operating_avg),
            ),
            (
                "Cumulative Net Cash Flow",
                money(net_total),
            ),
            (
                "Average Monthly Net Cash Flow",
                money(
                    monthly[
                        "net_cash_flow"
                    ].mean()
                ),
            ),
            (
                "Runway",
                runway_value,
            ),
            (
                "Average Customer Collection "
                "Time (B2B)",
                f"{average_collection_time:.1f} days",
            ),
            (
                "Late Customer Invoice "
                "Payment Rate",
                f"{late_rate:.1f} %",
            ),
            (
                "Open Receivables",
                money(open_receivables),
            ),
            (
                "Average Supplier Payment Time",
                f"{supplier_payment_time:.1f} days",
            ),
        ],
        columns=[
            "kpi",
            "value",
        ],
    )


    # -----------------------------------------------------------
    # COMPANY IDENTITY
    # -----------------------------------------------------------

    # Attach the fictional company identity to every Gold output.
    # This creates an explicit semantic link for BI, SQL and
    # RAG retrieval.

    for frame in [
        daily,
        monthly,
        receivables,
        payables,
        payroll_summary,
        kpis,
    ]:

        frame.insert(
            0,
            "company_name",
            COMPANY_NAME,
        )

        frame.insert(
            0,
            "company_id",
            COMPANY_ID,
        )


    # -----------------------------------------------------------
    # WRITE GOLD TABLES
    # -----------------------------------------------------------

    GOLD.mkdir(
        exist_ok=True
    )


    daily.to_csv(
        GOLD / "gold_daily_cash_position.csv",
        index=False,
        float_format="%.2f",
    )


    monthly.to_csv(
        GOLD / "gold_monthly_cash_flow.csv",
        index=False,
        float_format="%.2f",
    )


    receivables.to_csv(
        GOLD / "gold_receivables_aging.csv",
        index=False,
        float_format="%.2f",
    )


    payables.to_csv(
        GOLD / "gold_payables_aging.csv",
        index=False,
        float_format="%.2f",
    )


    payroll_summary.to_csv(
        GOLD / "gold_payroll_summary.csv",
        index=False,
        float_format="%.2f",
    )


    kpis.to_csv(
        GOLD / "gold_kpi_summary.csv",
        index=False,
    )


    # -----------------------------------------------------------
    # REBUILD SQLITE DATABASE
    # -----------------------------------------------------------

    # Recreate one canonical Treasoria database containing:
    # Silver tables, Gold tables, dimensions and metadata.

    if DB_PATH.exists():
        DB_PATH.unlink()


    with sqlite3.connect(
        DB_PATH
    ) as connection:

        silver_tables = {
            path.stem:
                pd.read_csv(path)
            for path
            in sorted(
                SILVER.glob("*.csv")
            )
        }


        gold_tables = {
            path.stem:
                pd.read_csv(path)
            for path
            in sorted(
                GOLD.glob("*.csv")
            )
        }


        for table_name, frame in {
            **silver_tables,
            **gold_tables,
        }.items():

            frame.to_sql(
                table_name,
                connection,
                if_exists="replace",
                index=False,
            )


        # -------------------------------------------------------
        # COMPANY DIMENSION
        # -------------------------------------------------------

        pd.DataFrame(
            [
                (
                    COMPANY_ID,
                    COMPANY_NAME,
                    COMPANY_OWNER,
                    COMPANY_ADDRESS,
                    COMPANY_POSTAL_CODE,
                    COMPANY_CITY,
                    COMPANY_COUNTRY,
                    COMPANY_SECTOR,
                )
            ],
            columns=[
                "company_id",
                "name",
                "owner",
                "address",
                "postal_code",
                "city",
                "country",
                "sector",
            ],
        ).to_sql(
            "dim_company",
            connection,
            if_exists="replace",
            index=False,
        )


        # -------------------------------------------------------
        # ACCOUNT DIMENSION
        # -------------------------------------------------------

        pd.DataFrame(
            [
                (
                    1,
                    "Checking Main",
                    "checking",
                ),
                (
                    2,
                    "Checking Secondary",
                    "checking",
                ),
                (
                    3,
                    "Credit Card",
                    "credit_card",
                ),
            ],
            columns=[
                "account_id",
                "account_name",
                "account_type",
            ],
        ).to_sql(
            "dim_account",
            connection,
            if_exists="replace",
            index=False,
        )


        # -------------------------------------------------------
        # EMPLOYEE DIMENSION
        # -------------------------------------------------------

        payroll[
            [
                "employee_id",
                "employee_name",
                "role",
            ]
        ].drop_duplicates().to_sql(
            "dim_employee",
            connection,
            if_exists="replace",
            index=False,
        )


        # -------------------------------------------------------
        # CUSTOMER DIMENSION
        # -------------------------------------------------------

        customer[
            [
                "customer_name",
                "customer_city",
            ]
        ].drop_duplicates().rename(
            columns={
                "customer_city":
                    "city"
            }
        ).to_sql(
            "dim_customer",
            connection,
            if_exists="replace",
            index=False,
        )


        # -------------------------------------------------------
        # SUPPLIER DIMENSION
        # -------------------------------------------------------

        supplier[
            [
                "supplier_name",
                "category",
            ]
        ].drop_duplicates().to_sql(
            "dim_supplier",
            connection,
            if_exists="replace",
            index=False,
        )


        # -------------------------------------------------------
        # CATEGORY DIMENSION
        # -------------------------------------------------------

        category_values = sorted(
            set(
                main["category"]
            ).union(
                set(
                    card["category"]
                )
            )
        )


        nature_map = {

            "Sales Revenue":
                "revenue",

            "B2B Sales Revenue":
                "revenue",

            "COGS":
                "expense",

            "Operating Expense":
                "expense",

            "Supplies":
                "expense",

            "Marketing":
                "expense",

            "Utilities":
                "expense",

            "Other":
                "expense",

            "Payment":
                "internal_transfer",

            "Transfer Out":
                "internal_transfer",

            "Credit Card Payment":
                "cash_settlement",
        }


        pd.DataFrame(
            [
                (
                    category,
                    nature_map.get(
                        category,
                        "other",
                    ),
                )
                for category
                in category_values
            ],
            columns=[
                "category",
                "nature",
            ],
        ).to_sql(
            "dim_category",
            connection,
            if_exists="replace",
            index=False,
        )


        # -------------------------------------------------------
        # DATASET METADATA
        # -------------------------------------------------------

        connection.execute(
            """
            CREATE TABLE dataset_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


        connection.executemany(
            """
            INSERT INTO dataset_metadata(key, value)
            VALUES (?, ?)
            """,
            [
                (
                    "notable_event_1",
                    "2023-02: storm damage roof repair, "
                    "EUR 8,500 (derived)",
                ),
                (
                    "notable_event_2",
                    "2023-06/07: equipment failure + "
                    "energy surcharge + delayed B2B "
                    "collection (derived)",
                ),
                (
                    "cost_model_note",
                    "Recurring ingredient-cost layer, "
                    "~29% COGS ratio, fixed suppliers "
                    "for rent, utilities and maintenance "
                    "(derived)",
                ),
                (
                    "period",
                    "2022-01-01 to 2023-12-31",
                ),
                (
                    "company_id",
                    COMPANY_ID,
                ),
                (
                    "company",
                    COMPANY_NAME,
                ),
                (
                    "company_owner",
                    COMPANY_OWNER,
                ),
                (
                    "company_address",
                    f"{COMPANY_ADDRESS}, "
                    f"{COMPANY_POSTAL_CODE} "
                    f"{COMPANY_CITY}, "
                    f"{COMPANY_COUNTRY}",
                ),
                (
                    "company_sector",
                    COMPANY_SECTOR,
                ),
                (
                    "payroll_note",
                    "January 2022 payroll debit is an "
                    "opening/legacy payment outside the "
                    "available Gusto extract.",
                ),
                (
                    "employer_cost_note",
                    "Employer social contributions are "
                    "analytical only and are not added "
                    "to observed bank cash outflows.",
                ),
            ],
        )


        assert (
            connection
            .execute(
                "PRAGMA integrity_check"
            )
            .fetchone()[0]
            == "ok"
        )


    # -----------------------------------------------------------
    # FINAL ACCOUNTING CONTROL
    # -----------------------------------------------------------

    # Opening cash + cumulative external net cash flow
    # must equal ending consolidated cash.

    assert np.isclose(
        opening_cash + net_total,
        ending_cash,
        atol=0.01,
    )


if __name__ == "__main__":
    build()