"""Run compact integrity and reconciliation checks for Code & Coffee GmbH."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

COMPANY_ID = "code_and_coffee"
COMPANY_NAME = "Code & Coffee GmbH"


def read(layer: str, name: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / layer / name)


def main() -> None:
    # -----------------------------------------------------------
    # LOAD CURATED TABLES
    # -----------------------------------------------------------

    checking_main = read(
        "silver",
        "fact_checking_main.csv",
    )

    checking_secondary = read(
        "silver",
        "fact_checking_secondary.csv",
    )

    card = read(
        "silver",
        "fact_credit_card.csv",
    )

    payroll = read(
        "silver",
        "fact_payroll.csv",
    )

    customer = read(
        "silver",
        "fact_customer_invoice.csv",
    )

    supplier = read(
        "silver",
        "fact_supplier_invoice.csv",
    )

    daily = read(
        "gold",
        "gold_daily_cash_position.csv",
    )

    monthly = read(
        "gold",
        "gold_monthly_cash_flow.csv",
    )


    # -----------------------------------------------------------
    # COMPANY IDENTITY
    # -----------------------------------------------------------

    # Every curated Silver table must be explicitly assigned
    # to the same fictional company.

    for path in sorted(
        (ROOT / "silver").glob("*.csv")
    ):
        frame = pd.read_csv(path)

        assert set(frame["company_id"]) == {
            COMPANY_ID
        }

        assert set(frame["company_name"]) == {
            COMPANY_NAME
        }


    # Every Gold table must use the same company identity.

    for path in sorted(
        (ROOT / "gold").glob("*.csv")
    ):
        frame = pd.read_csv(path)

        assert set(frame["company_id"]) == {
            COMPANY_ID
        }

        assert set(frame["company_name"]) == {
            COMPANY_NAME
        }


    # -----------------------------------------------------------
    # BASIC DATASET STRUCTURE
    # -----------------------------------------------------------

    assert len(daily) == 730
    assert len(monthly) == 24


    # -----------------------------------------------------------
    # DATA PROVENANCE
    # -----------------------------------------------------------

    allowed_origins = {
        "original",
        "derived",
        "synthetic",
    }


    assert set(
        checking_main["data_origin"]
    ) <= allowed_origins


    assert set(
        checking_secondary["data_origin"]
    ) <= allowed_origins


    assert set(
        card["data_origin"]
    ) <= allowed_origins


    assert set(
        payroll["data_origin"]
    ) <= allowed_origins


    assert set(
        customer["data_origin"]
    ) == {
        "synthetic"
    }


    assert set(
        supplier["data_origin"]
    ) == {
        "derived"
    }


    # -----------------------------------------------------------
    # UNIQUENESS CONTROLS
    # -----------------------------------------------------------

    assert customer[
        "invoice_id"
    ].is_unique


    assert supplier[
        "invoice_id"
    ].is_unique


    assert (
        payroll[
            [
                "employee_id",
                "pay_date",
            ]
        ]
        .duplicated()
        .sum()
        == 0
    )


    # -----------------------------------------------------------
    # TRANSFER SYMMETRY
    # -----------------------------------------------------------

    main_transfer = (
        checking_main.loc[
            checking_main[
                "category"
            ].eq("Transfer Out"),
            "amount",
        ]
        .sum()
    )


    secondary_transfer = (
        checking_secondary.loc[
            checking_secondary[
                "category"
            ].eq("Transfer"),
            "amount",
        ]
        .sum()
    )


    assert np.isclose(
        main_transfer,
        secondary_transfer,
        atol=0.01,
    )


    # -----------------------------------------------------------
    # SUPPLIER INVOICE TRACEABILITY
    # -----------------------------------------------------------

    # Every supplier invoice must point to an existing source
    # transaction with the same monetary value.

    sources = pd.concat(
        [
            checking_main[
                [
                    "transaction_id",
                    "amount",
                ]
            ].assign(
                source_account="checking_main"
            ),

            card[
                [
                    "transaction_id",
                    "amount",
                ]
            ].assign(
                source_account="credit_card"
            ),
        ],
        ignore_index=True,
    )


    linked = supplier.merge(
        sources,
        left_on=[
            "source_transaction_id",
            "source_account",
        ],
        right_on=[
            "transaction_id",
            "source_account",
        ],
        how="left",
        suffixes=(
            "_invoice",
            "_source",
        ),
    )


    assert linked[
        "transaction_id"
    ].notna().all()


    assert np.allclose(
        linked["amount_invoice"],
        linked["amount_source"],
        atol=0.01,
    )


    # -----------------------------------------------------------
    # GOLD ACCOUNTING CONTROLS
    # -----------------------------------------------------------

    assert np.isclose(
        monthly["cash_in"].sum(),
        625_759.90,
        atol=0.01,
    )


    assert np.isclose(
        monthly["cash_out_total"].sum(),
        408_210.01,
        atol=0.01,
    )


    assert np.isclose(
        monthly["net_cash_flow"].sum(),
        217_549.89,
        atol=0.01,
    )


    assert np.isclose(
        daily.iloc[-1][
            "consolidated_cash_balance"
        ],
        234_549.89,
        atol=0.01,
    )


    # Core accounting identity:
    #
    # Opening consolidated cash
    # + cumulative external net cash flow
    # = ending consolidated cash

    assert np.isclose(
        17_000.00
        + monthly[
            "net_cash_flow"
        ].sum(),
        234_549.89,
        atol=0.01,
    )


    # -----------------------------------------------------------
    # SQLITE DATABASE
    # -----------------------------------------------------------

    with sqlite3.connect(
        ROOT / "treasoria.db"
    ) as connection:

        assert (
            connection
            .execute(
                "PRAGMA integrity_check"
            )
            .fetchone()[0]
            == "ok"
        )


        tables = {
            row[0]
            for row
            in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                """
            )
        }


        # Validate company dimension.

        company_row = connection.execute(
            """
            SELECT
                company_id,
                name,
                sector
            FROM dim_company
            LIMIT 1
            """
        ).fetchone()


        assert company_row is not None

        assert company_row[0] == COMPANY_ID

        assert company_row[1] == COMPANY_NAME

        assert company_row[2] == (
            "International Café & Gastronomy"
        )


        # Validate metadata identity.

        metadata = dict(
            connection.execute(
                """
                SELECT key, value
                FROM dataset_metadata
                """
            ).fetchall()
        )


        assert metadata[
            "company_id"
        ] == COMPANY_ID


        assert metadata[
            "company"
        ] == COMPANY_NAME


    # -----------------------------------------------------------
    # REQUIRED SQLITE TABLES
    # -----------------------------------------------------------

    required = {
        path.stem
        for path
        in (
            ROOT / "silver"
        ).glob("*.csv")
    }


    required |= {
        path.stem
        for path
        in (
            ROOT / "gold"
        ).glob("*.csv")
    }


    required |= {
        "dim_company",
        "dim_account",
        "dim_employee",
        "dim_customer",
        "dim_supplier",
        "dim_category",
        "dataset_metadata",
    }


    assert required <= tables


    # -----------------------------------------------------------
    # PDF DOCUMENT COVERAGE
    # -----------------------------------------------------------

    pdf_counts = {
        folder.name:
            len(
                list(
                    folder.glob("*.pdf")
                )
            )
        for folder
        in (
            ROOT / "docs"
        ).iterdir()
        if folder.is_dir()
    }


    assert pdf_counts == {
        "invoices_pdf": 330,
        "customer_invoices_pdf": 51,
        "bank_statements_pdf": 72,
    }


    # -----------------------------------------------------------
    # FINAL VALIDATION SUMMARY
    # -----------------------------------------------------------

    print("VALIDATED")

    print(
        f"Company: "
        f"{COMPANY_NAME}"
    )

    print(
        "Ending consolidated cash: "
        "EUR 234,549.89"
    )

    print(
        "Cumulative net cash flow: "
        "EUR 217,549.89"
    )

    print(
        f"Average monthly net cash flow: "
        f"EUR "
        f"{monthly['net_cash_flow'].mean():,.2f}"
    )

    print(
        f"Negative months: "
        f"{(monthly['net_cash_flow'] < 0).sum()} "
        f"/ {len(monthly)}"
    )

    print(
        f"PDF documents: "
        f"{sum(pdf_counts.values())}"
    )


if __name__ == "__main__":
    main()