"""
Treasoria — Data Quality checks for extracted invoice data

Goal: before an OCR-extracted invoice is shown as "Ready for
integration", run a few honest sanity checks on it. This does NOT
write anything to Silver/Gold -- it only validates the data already
sitting in memory after OCR extraction, and reports what it finds.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd


REQUIRED_FIELDS = ["Invoice number", "Invoice date", "Due date", "Total due"]


def check_missing_fields(fields: dict) -> list[str]:
    """
    Check that the fields a human actually needs to trust this
    invoice are present and non-empty.

    WHY these 4 and not all of them: Counterparty and Category are
    useful context, but an invoice missing its number, dates or
    total amount can't be trusted or matched to anything -- these
    are the fields where "empty" is a real problem, not a minor
    gap.

    Returns a list of the field names that are missing (an empty
    list means everything required is present).
    """

    return [
        field_name
        for field_name in REQUIRED_FIELDS
        if not fields.get(field_name)
    ]


def check_date_consistency(fields: dict) -> list[str]:
    """
    Check that the Due date comes on or after the Invoice date.

    WHY this matters: a due date before the invoice date makes no
    business sense -- it usually means one of the two dates was
    misread by OCR (e.g. day and month swapped), or the wrong value
    landed in the wrong field.

    If either date is missing, this check is silently skipped --
    check_missing_fields() already reports a missing date on its
    own, so we don't want to report the same problem twice under
    two different messages.
    """

    issues = []
    invoice_date = fields.get("Invoice date", "")
    due_date = fields.get("Due date", "")

    if invoice_date and due_date:
        try:
            invoice_dt = datetime.strptime(invoice_date, "%Y-%m-%d")
            due_dt = datetime.strptime(due_date, "%Y-%m-%d")

            if due_dt < invoice_dt:
                issues.append(
                    f"Due date ({due_date}) is before "
                    f"Invoice date ({invoice_date})"
                )

        except ValueError:
            issues.append(
                "Could not parse Invoice date or Due date "
                "as YYYY-MM-DD"
            )

    return issues


def check_amount_consistency(
    line_item: dict, tolerance: float = 0.01
) -> list[str]:
    """
    Check that Net amount + VAT amount = Total amount, within a
    small tolerance.

    WHY a tolerance instead of exact equality: rounding to 2
    decimal places can introduce a difference of a fraction of a
    cent between "net + vat" computed here and the "total" printed
    on the invoice, even when the invoice is completely correct.
    0.01 EUR (one cent) is generous enough to absorb that without
    hiding a real mismatch.

    If any of the three amounts is missing or not a real number,
    this check is skipped rather than guessing -- a genuinely
    incomplete line item is already flagged by
    check_missing_fields()-style logic elsewhere, not this one.
    """

    issues = []

    try:
        net = float(line_item.get("net_amount", "") or 0)
        vat = float(line_item.get("vat_amount", "") or 0)
        total = float(line_item.get("total_amount", "") or 0)

        if net and vat and total:
            computed_total = net + vat

            if abs(computed_total - total) > tolerance:
                issues.append(
                    f"Net ({net}) + VAT ({vat}) = "
                    f"{computed_total:.2f}, but Total is {total}"
                )

    except ValueError:
        issues.append("Could not parse Net/VAT/Total as numbers")

    return issues


def load_existing_invoice_numbers(dataset_dir: Path) -> set[str]:
    """
    Load every invoice number already recorded in the Silver layer,
    from both supplier and customer invoice tables.

    WHY this exists: to detect a duplicate upload (someone
    re-uploading a facture that's already been processed), we need
    something to compare the new invoice number against. This
    builds that comparison set from the trusted Silver data.

    Returns an empty set (not an error) if the Silver files can't
    be found or read -- duplicate detection is a nice-to-have on
    top of the other checks, not something that should crash the
    whole Data Quality pass if the dataset layout changes.
    """

    existing_ids: set[str] = set()
    silver_path = dataset_dir / "silver"

    for filename, id_column in [
        ("fact_supplier_invoice.csv", "invoice_id"),
        ("fact_customer_invoice.csv", "invoice_id"),
    ]:
        file_path = silver_path / filename

        try:
            table = pd.read_csv(file_path)
            if id_column in table.columns:
                existing_ids.update(table[id_column].astype(str))
        except Exception:
            # Missing file or unexpected column name: skip this
            # source rather than failing the whole function.
            continue

    return existing_ids


def check_duplicate(invoice_number: str, existing_ids: set[str]) -> list[str]:
    """
    Check whether this invoice number already exists in the trusted
    dataset -- a likely sign the same invoice is being uploaded
    twice.
    """

    if invoice_number and invoice_number in existing_ids:
        return [
            f"This invoice ({invoice_number}) appears to have "
            "already been processed before."
        ]

    return []


def run_data_quality_checks(
    fields: dict,
    line_item: dict,
    existing_invoice_ids: set[str] | None = None,
) -> dict:
    """
    Run every Data Quality check on one OCR-extracted invoice and
    return a single consolidated result.

    WHY one combined function: the Streamlit page needs one clear
    answer -- "PASSED" or "here's what's wrong" -- not four separate
    results to piece together itself. This is the only function the
    app needs to call.
    """

    issues: list[str] = []

    missing = check_missing_fields(fields)
    if missing:
        issues.append(f"Missing required field(s): {', '.join(missing)}")

    issues += check_date_consistency(fields)
    issues += check_amount_consistency(line_item)

    if existing_invoice_ids is not None:
        issues += check_duplicate(
            fields.get("Invoice number", ""), existing_invoice_ids
        )

    return {
        "passed": len(issues) == 0,
        "issues": issues,
    }
    
    
def process_excel_import(
    file_path: str, existing_invoice_ids: set[str] | None = None
) -> pd.DataFrame:
    """
    Bulk-import multiple invoices at once from an Excel file, and
    run Data Quality checks on every row.

    WHY this is completely separate from the OCR path: an Excel
    file is already structured data (real columns, not a photo of
    text) -- there's nothing for Tesseract to read here. This
    function skips OCR entirely and goes straight to validation,
    which is also what makes bulk import genuinely useful: dozens
    of invoices checked in one pass, instead of one PDF at a time.

    Expected columns (case-sensitive, matching what OCR would have
    extracted): "Invoice number", "Invoice date", "Due date",
    "Total due", "Net amount", "VAT amount". Missing columns are
    treated as empty values rather than crashing the import --
    a row with genuinely missing data will fail the "missing
    required field" check anyway.

    Returns a summary DataFrame: one row per invoice, with its
    Data Quality status and a human-readable list of issues, if
    any.
    """

    imported_table = pd.read_excel(file_path, dtype=str).fillna("")

    results = []

    for _, row in imported_table.iterrows():
        fields = {
            "Invoice number": row.get("Invoice number", ""),
            "Invoice date": row.get("Invoice date", ""),
            "Due date": row.get("Due date", ""),
            "Total due": row.get("Total due", ""),
        }
        line_item = {
            "net_amount": row.get("Net amount", ""),
            "vat_amount": row.get("VAT amount", ""),
            "total_amount": row.get("Total due", ""),
        }

        check_result = run_data_quality_checks(
            fields, line_item, existing_invoice_ids
        )

        results.append(
            {
                "Invoice number": fields["Invoice number"],
                "Status": "PASSED" if check_result["passed"] else "Issues found",
                "Issues": "; ".join(check_result["issues"]),
            }
        )

    return pd.DataFrame(results)