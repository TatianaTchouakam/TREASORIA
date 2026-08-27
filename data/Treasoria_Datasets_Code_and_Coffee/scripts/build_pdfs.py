import csv
import os

from pathlib import Path
from collections import defaultdict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib.enums import TA_RIGHT


BASE = str(Path(__file__).resolve().parents[1])

SILVER = f"{BASE}/silver"
DOCS = f"{BASE}/docs"

os.makedirs(
    f"{DOCS}/invoices_pdf",
    exist_ok=True,
)

os.makedirs(
    f"{DOCS}/customer_invoices_pdf",
    exist_ok=True,
)

os.makedirs(
    f"{DOCS}/bank_statements_pdf",
    exist_ok=True,
)


# ---------------------------------------------------------------
# DOCUMENT STYLES
# ---------------------------------------------------------------

styles = getSampleStyleSheet()

h1 = ParagraphStyle(
    "h1",
    parent=styles["Heading1"],
    fontSize=16,
    textColor=colors.HexColor("#0B1F3A"),
)

normal = styles["Normal"]

right = ParagraphStyle(
    "right",
    parent=normal,
    alignment=TA_RIGHT,
)


# ---------------------------------------------------------------
# COMPANY IDENTITY
# ---------------------------------------------------------------

COMPANY = "Code & Coffee GmbH"

COMPANY_OWNER = "Blue Jesus"

COMPANY_ADDR = (
    "Ravensberger Str. 22, "
    "33602 Bielefeld, Germany"
)

# Internal Treasoria reference only.
# It is not presented as a VAT number, tax ID,
# company registration number, or bank identifier.

COMPANY_REFERENCE = "TREASORIA-CC-2022-2023"


def load(path):

    with open(path) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------
# SUPPLIER INVOICES
# Company is the CLIENT / buyer
# ---------------------------------------------------------------

sup_inv = load(
    f"{SILVER}/fact_supplier_invoice.csv"
)


def make_supplier_pdf(inv, idx):

    fname = (
        f"{DOCS}/invoices_pdf/"
        f"supplier_invoice_{idx:04d}.pdf"
    )

    doc = SimpleDocTemplate(
        fname,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
    )

    elems = []

    elems.append(
        Paragraph(
            "INVOICE",
            h1,
        )
    )

    elems.append(
        Spacer(
            1,
            6 * mm,
        )
    )


    party_table = Table(
        [
            [
                Paragraph(
                    "<b>Seller:</b>",
                    normal,
                ),
                Paragraph(
                    "<b>Client:</b>",
                    normal,
                ),
            ],
            [
                Paragraph(
                    f"{inv['supplier_name']}<br/>"
                    f"Germany",
                    normal,
                ),
                Paragraph(
                    f"{COMPANY}<br/>"
                    f"Owner: {COMPANY_OWNER}<br/>"
                    f"{COMPANY_ADDR}<br/>"
                    f"Reference: {COMPANY_REFERENCE}",
                    normal,
                ),
            ],
        ],
        colWidths=[
            85 * mm,
            85 * mm,
        ],
    )

    elems.append(
        party_table
    )

    elems.append(
        Spacer(
            1,
            8 * mm,
        )
    )

    elems.append(
        Paragraph(
            f"<b>Invoice No.:</b> "
            f"{inv['invoice_id']}",
            normal,
        )
    )

    elems.append(
        Paragraph(
            f"<b>Invoice date:</b> "
            f"{inv['invoice_date']}    "
            f"<b>Due date:</b> "
            f"{inv['due_date']}",
            normal,
        )
    )

    elems.append(
        Spacer(
            1,
            6 * mm,
        )
    )


    net = (
        float(inv["amount"])
        / 1.19
    )

    vat = (
        float(inv["amount"])
        - net
    )


    small = ParagraphStyle(
        "small",
        parent=normal,
        fontSize=8,
        leading=10,
    )


    data = [
        [
            "Description",
            "Category",
            "Net",
            "VAT (19%)",
            "Total",
        ],
        [
            Paragraph(
                inv["supplier_name"],
                small,
            ),
            Paragraph(
                inv["category"],
                small,
            ),
            f"{net:.2f}",
            f"{vat:.2f}",
            f"{float(inv['amount']):.2f}",
        ],
    ]


    t = Table(
        data,
        colWidths=[
            55 * mm,
            30 * mm,
            25 * mm,
            25 * mm,
            25 * mm,
        ],
    )


    t.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#0B1F3A"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "ALIGN",
                    (2, 0),
                    (-1, -1),
                    "RIGHT",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
            ]
        )
    )


    elems.append(
        t
    )

    elems.append(
        Spacer(
            1,
            6 * mm,
        )
    )

    elems.append(
        Paragraph(
            f"<b>Total due: "
            f"EUR {float(inv['amount']):.2f}</b>",
            normal,
        )
    )

    elems.append(
        Paragraph(
            f"Status: {inv['status']}  |  "
            f"Paid on: {inv['payment_date']}",
            normal,
        )
    )


    doc.build(
        elems
    )


for i, inv in enumerate(sup_inv):

    make_supplier_pdf(
        inv,
        i,
    )


print(
    f"Supplier invoice PDFs: "
    f"{len(sup_inv)}"
)


# ---------------------------------------------------------------
# CUSTOMER B2B INVOICES
# Company is the SELLER
# ---------------------------------------------------------------

cust_inv = load(
    f"{SILVER}/fact_customer_invoice.csv"
)


def make_customer_pdf(inv, idx):

    fname = (
        f"{DOCS}/customer_invoices_pdf/"
        f"customer_invoice_{idx:04d}.pdf"
    )

    doc = SimpleDocTemplate(
        fname,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
    )

    elems = []

    elems.append(
        Paragraph(
            "INVOICE",
            h1,
        )
    )

    elems.append(
        Spacer(
            1,
            6 * mm,
        )
    )


    party_table = Table(
        [
            [
                Paragraph(
                    "<b>Seller:</b>",
                    normal,
                ),
                Paragraph(
                    "<b>Client:</b>",
                    normal,
                ),
            ],
            [
                Paragraph(
                    f"{COMPANY}<br/>"
                    f"Owner: {COMPANY_OWNER}<br/>"
                    f"{COMPANY_ADDR}<br/>"
                    f"Reference: {COMPANY_REFERENCE}",
                    normal,
                ),
                Paragraph(
                    f"{inv['customer_name']}<br/>"
                    f"{inv['customer_city']}, Germany",
                    normal,
                ),
            ],
        ],
        colWidths=[
            85 * mm,
            85 * mm,
        ],
    )


    elems.append(
        party_table
    )

    elems.append(
        Spacer(
            1,
            8 * mm,
        )
    )

    elems.append(
        Paragraph(
            f"<b>Invoice No.:</b> "
            f"{inv['invoice_id']}",
            normal,
        )
    )

    elems.append(
        Paragraph(
            f"<b>Issue date:</b> "
            f"{inv['issue_date']}    "
            f"<b>Due date:</b> "
            f"{inv['due_date']}",
            normal,
        )
    )

    elems.append(
        Spacer(
            1,
            6 * mm,
        )
    )


    net = (
        float(inv["amount"])
        / 1.19
    )

    vat = (
        float(inv["amount"])
        - net
    )


    data = [
        [
            "Description",
            "Net",
            "VAT (19%)",
            "Total",
        ],
        [
            "B2B catering / wholesale services",
            f"{net:.2f}",
            f"{vat:.2f}",
            f"{float(inv['amount']):.2f}",
        ],
    ]


    t = Table(
        data,
        colWidths=[
            75 * mm,
            30 * mm,
            30 * mm,
            25 * mm,
        ],
    )


    t.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#0B1F3A"),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (-1, -1),
                    "RIGHT",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
            ]
        )
    )


    elems.append(
        t
    )

    elems.append(
        Spacer(
            1,
            6 * mm,
        )
    )

    elems.append(
        Paragraph(
            f"<b>Total due: "
            f"EUR {float(inv['amount']):.2f}</b>",
            normal,
        )
    )


    status_label = {
        "paid_on_time":
            "Paid (on time)",
        "paid_late":
            "Paid (late)",
        "open":
            "Open (not yet due)",
        "open_overdue":
            "Open (overdue)",
    }.get(
        inv["status"],
        inv["status"],
    )


    status_text = (
        f"Status: {status_label}"
    )


    if inv["payment_date"]:

        status_text += (
            f"  |  Paid on: "
            f"{inv['payment_date']}"
        )


    elems.append(
        Paragraph(
            status_text,
            normal,
        )
    )


    doc.build(
        elems
    )


for i, inv in enumerate(cust_inv):

    make_customer_pdf(
        inv,
        i,
    )


print(
    f"Customer invoice PDFs: "
    f"{len(cust_inv)}"
)


# ---------------------------------------------------------------
# MONTHLY BANK / CARD STATEMENTS
# ---------------------------------------------------------------

accounts = [

    (
        "fact_checking_main.csv",
        "Checking Account - Main",
        "IBAN DE12 4801 0111 2233 4455 66",
    ),

    (
        "fact_checking_secondary.csv",
        "Checking Account - Secondary (Payroll)",
        "IBAN DE34 4801 0111 7788 9900 11",
    ),

    (
        "fact_credit_card.csv",
        "Business Credit Card",
        "Card ending 4471",
    ),
]


for fname, label, ident in accounts:

    rows = load(
        f"{SILVER}/{fname}"
    )

    by_month = defaultdict(list)


    for r in rows:

        by_month[
            r["date"][:7]
        ].append(r)


    for month, mrows in sorted(
        by_month.items()
    ):

        safe = (
            fname
            .replace("fact_", "")
            .replace(".csv", "")
        )


        out_fname = (
            f"{DOCS}/bank_statements_pdf/"
            f"{safe}_{month}.pdf"
        )


        doc = SimpleDocTemplate(
            out_fname,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=15 * mm,
        )


        elems = [

            Paragraph(
                "Treasoria Bank AG",
                h1,
            ),

            Paragraph(
                f"Account statement - "
                f"{label}",
                styles["Heading2"],
            ),

            Paragraph(
                f"{ident}   |   "
                f"Statement period: "
                f"{month}",
                normal,
            ),

            Paragraph(
                f"Account holder: "
                f"{COMPANY} "
                f"(Owner: {COMPANY_OWNER}), "
                f"{COMPANY_ADDR}",
                normal,
            ),

            Spacer(
                1,
                6 * mm,
            ),
        ]


        data = [
            [
                "Date",
                "Description",
                "Type",
                "Amount",
                "Balance",
            ]
        ]


        for r in mrows:

            desc = r.get(
                "description",
                r.get("vendor", ""),
            )


            data.append(
                [
                    r["date"],
                    desc[:40],
                    r["type"],
                    f"{float(r['amount']):.2f}",
                    f"{float(r['balance']):.2f}",
                ]
            )


        t = Table(
            data,
            colWidths=[
                22 * mm,
                75 * mm,
                20 * mm,
                25 * mm,
                25 * mm,
            ],
        )


        t.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#0B1F3A"),
                    ),
                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.white,
                    ),
                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.grey,
                    ),
                    (
                        "ALIGN",
                        (3, 0),
                        (-1, -1),
                        "RIGHT",
                    ),
                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        7.5,
                    ),
                ]
            )
        )


        elems.append(
            t
        )


        doc.build(
            elems
        )


n_statements = sum(

    len(
        set(
            r["date"][:7]
            for r in load(
                f"{SILVER}/{fn}"
            )
        )
    )

    for fn, _, _
    in accounts
)


print(
    f"Bank/card statement PDFs: "
    f"{n_statements}"
)