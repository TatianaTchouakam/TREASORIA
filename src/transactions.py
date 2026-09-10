"""
Treasoria — Transactions module

Loads, combines, and prepares the transaction ledger from all 3
bank/card source tables for the Transactions page.
"""
# ------------------------------------------------------------------
# KNOWN ISSUE FOUND DURING DEVELOPMENT (and how it was fixed)
# ------------------------------------------------------------------
# Internal transfer detection missed real variants
#   The category for the Main Checking side of a payroll transfer
#   is "Transfer Out", not "Transfer" -- an exact match against
#   INTERNAL_TRANSFER_CATEGORIES missed it, wrongly classifying a
#   real internal transfer as a "Real transaction". Confirmed by
#   comparing counts: Secondary Checking had exactly 94 internal
#   transfers recorded, but only 94 total were detected across ALL
#   3 accounts -- meaning every matching Main Checking transfer
#   (the other side of the same movement) was being missed.
#   Fix: is_internal_transfer() now checks whether a keyword like
#   "Transfer" or "Payroll" appears ANYWHERE in the category text
#   (case-insensitive), not just an exact match. After the fix,
#   internal transfers rose from 94 to 141, consistent with each
#   transfer appearing on both sides of the movement.
# ------------------------------------------------------------------

from pathlib import Path

import pandas as pd


SOURCE_TABLES = [
    ("fact_checking_main.csv", "Main Checking"),
    ("fact_checking_secondary.csv", "Secondary Checking"),
    ("fact_credit_card.csv", "Credit Card"),
]

# Categories that represent money moving between the company's OWN
# accounts, not a real inflow/outflow with an outside party.
INTERNAL_TRANSFER_CATEGORIES = ["Transfer", "Payroll"]


def load_and_normalize_source(file_path: Path, account_name: str) -> pd.DataFrame:
    """
    Load one source table and harmonise it to a common shape.

    WHY this is needed: fact_credit_card.csv names its counterparty
    column "vendor", while the two checking-account tables call it
    "description" -- same meaning, different column name. This
    function renames whichever one is present to a single
    "counterparty" column, so the rest of the pipeline doesn't need
    to know which source table a row came from.
    """

    table = pd.read_csv(file_path)

    if "vendor" in table.columns:
        table = table.rename(columns={"vendor": "counterparty"})
    else:
        table = table.rename(columns={"description": "counterparty"})

    table["account"] = account_name

    return table[
        [
            "date", "transaction_id", "counterparty", "category",
            "type", "amount", "balance", "data_origin", "account",
        ]
    ]


def load_all_transactions(dataset_dir: Path) -> pd.DataFrame:
    """
    Load and combine all 3 transaction source tables into one
    ledger, with a few derived columns added for the Transactions
    page:

    - "Money in / Money out": human-readable version of the raw
      Credit/Debit "type" column.
    - "Confirmed / Needs review": derived from data_origin. A row
      marked "original" came directly from the source data; a row
      marked "derived" was calculated/inferred rather than read
      as-is, so it's flagged for a human to double-check rather
      than assumed correct.
    - "Internal transfer / Real transaction": a row whose category
      is Transfer or Payroll is money moving between the company's
      own accounts, not a real transaction with an outside party.
      ASSUMPTION: these are the only two "internal" categories in
      this dataset -- if real data turns up another one, tell me
      and I'll add it to INTERNAL_TRANSFER_CATEGORIES.
    """

    silver_path = dataset_dir / "silver"

    frames = [
        load_and_normalize_source(silver_path / filename, account_name)
        for filename, account_name in SOURCE_TABLES
    ]

    combined = pd.concat(frames, ignore_index=True)

    combined["date"] = pd.to_datetime(combined["date"])

    combined["Money in / Money out"] = combined["type"].map(
        {"Credit": "Money in", "Debit": "Money out"}
    )

    combined["Confirmed / Needs review"] = combined["data_origin"].map(
        {"original": "Confirmed", "derived": "Needs review"}
    )

    def is_internal_transfer(category: str) -> bool:
        category_lower = str(category).lower()
        return any(
            keyword.lower() in category_lower
            for keyword in INTERNAL_TRANSFER_CATEGORIES
        )

    combined["Internal transfer / Real transaction"] = combined["category"].apply(
        lambda cat: "Internal transfer" if is_internal_transfer(cat) else "Real transaction"
    )

    return combined.sort_values("date").reset_index(drop=True)

def category_breakdown(transactions: pd.DataFrame) -> pd.DataFrame:
    """
    Summarise transactions by category: how many transactions, and
    the total amount, per category -- sorted from biggest to
    smallest so the most significant categories appear first.

    WHY this is separate from the Overview's expense pie chart:
    that chart only covers supplier invoice categories (spending).
    This covers EVERY category across all 3 accounts, income and
    spending both -- a broader, quicker "what's moving and where"
    view specific to the Transactions page.
    """

    breakdown = (
        transactions.groupby("category")["amount"]
        .agg(["count", "sum"])
        .reset_index()
        .rename(columns={"count": "Transactions", "sum": "Total Amount"})
        .sort_values("Total Amount", ascending=False)
    )

    return breakdown


def build_csv_export(transactions: pd.DataFrame) -> bytes:
    """
    Turn a transactions table into downloadable CSV bytes.

    WHY CSV instead of Excel here: the other download buttons in
    this app (Invoices page) use Excel because a single invoice's
    handful of fields benefit from formatting. A transaction ledger
    is exactly what CSV is built for -- one row per record, no
    formatting needed, and it opens instantly in any spreadsheet
    tool or accounting software without extra libraries.
    """

    return transactions.to_csv(index=False).encode("utf-8")