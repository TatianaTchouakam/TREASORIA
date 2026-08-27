import csv
import random
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

random.seed(42)

BASE = str(Path(__file__).resolve().parents[1])
BRONZE = f"{BASE}/bronze"
SILVER = f"{BASE}/silver"
GOLD = f"{BASE}/gold"

os.makedirs(SILVER, exist_ok=True)
os.makedirs(GOLD, exist_ok=True)

COMPANY_ID = "code_and_coffee"
COMPANY_NAME = "Code & Coffee GmbH"


def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def d(s):
    return datetime.strptime(s, "%Y-%m-%d")


def dstr(dt):
    return dt.strftime("%Y-%m-%d")


# ---------------------------------------------------------------
# 1. LOAD BRONZE
# ---------------------------------------------------------------

main = load_csv(f"{BRONZE}/checking_account_main.csv")
sec = load_csv(f"{BRONZE}/checking_account_secondary.csv")
cc = load_csv(f"{BRONZE}/credit_card_account.csv")
payroll = load_csv(f"{BRONZE}/gusto_payroll.csv")

print(
    "Loaded:",
    len(main), "main /",
    len(sec), "secondary /",
    len(cc), "cc /",
    len(payroll), "payroll"
)


# ---------------------------------------------------------------
# 2. TREASURY CORRECTIONS (derived)
# Close the reconciliation gaps
# ---------------------------------------------------------------

# 2a. Payroll funding gap:
# gusto_payroll total paid vs secondary "Payroll" debits funded

paid_by_date = defaultdict(float)

for r in payroll:
    paid_by_date[r["pay_date"]] += float(r["amount"])

funded_by_date = defaultdict(float)

for r in sec:
    if r["category"] == "Payroll":
        funded_by_date[r["date"]] += float(r["amount"])

gap_by_date = {}

for dt_, paid in paid_by_date.items():
    funded = funded_by_date.get(dt_, 0.0)
    gap = round(paid - funded, 2)

    if gap > 0:
        gap_by_date[dt_] = gap

total_gap = round(sum(gap_by_date.values()), 2)

print("Total payroll funding gap to close:", total_gap)


# New paired rows for secondary:
# Transfer from Main (credit) + Payroll (debit),
# same date and same amount.

new_sec_rows = []
tid_counter = 1000

for dt_, gap in sorted(gap_by_date.items()):

    new_sec_rows.append({
        "date": dt_,
        "transaction_id": f"SC{tid_counter}",
        "description": "Transfer from Main (funding top-up)",
        "category": "Transfer",
        "type": "Credit",
        "amount": str(gap),
        "data_origin": "derived",
    })

    tid_counter += 1

    new_sec_rows.append({
        "date": dt_,
        "transaction_id": f"SC{tid_counter}",
        "description": "Payroll Funding (top-up)",
        "category": "Payroll",
        "type": "Debit",
        "amount": str(gap),
        "data_origin": "derived",
    })

    tid_counter += 1


# 2b. Checking main needs matching outflows:
# Transfer to Secondary account, mirroring ALL secondary
# "Transfer" credits (original + new top-up).

sec_transfers = (
    [r for r in sec if r["category"] == "Transfer"]
    + [r for r in new_sec_rows if r["category"] == "Transfer"]
)

total_transfer_out = round(
    sum(float(r["amount"]) for r in sec_transfers),
    2
)

print(
    "Total transfer-out needed from main to secondary:",
    total_transfer_out
)


# 2c. Checking main needs matching outflow:
# Credit Card Payment, mirroring cc "Payment" rows.

cc_payments = [
    r for r in cc
    if r["category"] == "Payment"
]

total_cc_payment = round(
    sum(float(r["amount"]) for r in cc_payments),
    2
)

print(
    "Total CC payment-out needed from main:",
    total_cc_payment
)


new_main_rows = []
mid_counter = 2000

for r in sec_transfers:

    new_main_rows.append({
        "date": r["date"],
        "transaction_id": f"TXD{mid_counter}",
        "description": "Transfer to Secondary Account (payroll funding)",
        "category": "Transfer Out",
        "type": "Debit",
        "amount": r["amount"],
        "data_origin": "derived",
    })

    mid_counter += 1


for r in cc_payments:

    new_main_rows.append({
        "date": r["date"],
        "transaction_id": f"TXD{mid_counter}",
        "description": "Credit Card Bill Payment",
        "category": "Credit Card Payment",
        "type": "Debit",
        "amount": r["amount"],
        "data_origin": "derived",
    })

    mid_counter += 1


print(
    "New derived rows: main +",
    len(new_main_rows),
    " / secondary +",
    len(new_sec_rows)
)

print(
    "Sum new main outflows:",
    round(
        sum(float(r["amount"]) for r in new_main_rows),
        2
    )
)


# ---------------------------------------------------------------
# 3. CUSTOMER B2B INVOICES (synthetic)
# Adds a secondary revenue stream so collection and aging
# KPIs are testable.
# ---------------------------------------------------------------

B2B_CLIENTS = [
    ("Nordwelle Consulting GmbH", "Bielefeld"),
    ("Ostpark Buero Services", "Herford"),
    ("Katering Vier Jahreszeiten", "Guetersloh"),
    ("Rheinstadt Event GmbH", "Bielefeld"),
    ("Solid Office Supplies eK", "Detmold"),
]


# ---------------------------------------------------------------
# BUSINESS EVENTS
# Mid-2023 liquidity tension
# ---------------------------------------------------------------

# A purely linear, always-positive cash trajectory would not give
# Forecast/Liquidity Risk enough meaningful signal to detect.
#
# This block adds one bounded and fully documented business event
# using `derived` and `synthetic` records on top of the untouched
# Bronze files. Original transactions are never altered.
#
# Narrative:
# A large B2B client places bigger orders in May-July 2023 but
# pays them very late, while emergency equipment costs and an
# energy-price increase affect operating cash flow.

STRESS_WINDOW_START = d("2023-05-01")
STRESS_WINDOW_END = d("2023-07-15")

START = d("2022-01-01")
END = d("2023-12-31")

customer_invoices = []

inv_counter = 5000
cur = START + timedelta(days=20)


while cur <= END - timedelta(days=8):

    # Roughly biweekly-to-monthly invoicing cadence.

    client_name, city = random.choice(B2B_CLIENTS)

    in_stress_window = (
        STRESS_WINDOW_START
        <= cur
        <= STRESS_WINDOW_END
    )

    if in_stress_window:

        # Bigger seasonal catering orders,
        # while collection slows significantly.

        amount = round(
            random.uniform(1400, 4300),
            2
        )

    else:

        amount = round(
            random.uniform(280, 950),
            2
        )

    issue = cur
    due = issue + timedelta(days=30)

    roll = random.random()

    if in_stress_window:

        candidate_paid = (
            due
            + timedelta(
                days=random.randint(70, 110)
            )
        )

        candidate_status = "paid_late"

    elif roll < 0.65:

        candidate_paid = (
            due
            - timedelta(
                days=random.randint(0, 4)
            )
        )

        candidate_status = "paid_on_time"

    elif roll < 0.90:

        candidate_paid = (
            due
            + timedelta(
                days=random.randint(5, 25)
            )
        )

        candidate_status = "paid_late"

    else:

        candidate_paid = (
            due
            + timedelta(
                days=random.randint(30, 60)
            )
        )

        candidate_status = "paid_late"


    # Observation window ends at END.
    # Anything paid after END, or not yet due by END,
    # remains open at the snapshot date.

    if candidate_paid > END or due > END:

        paid = None

        status = (
            "open_overdue"
            if due < END
            else "open"
        )

    else:

        paid = candidate_paid
        status = candidate_status


    customer_invoices.append({

        "invoice_id": f"CINV{inv_counter}",

        "customer_name": client_name,

        "customer_city": city,

        "issue_date": dstr(issue),

        "due_date": dstr(due),

        "amount": amount,

        "payment_date": (
            dstr(paid)
            if paid
            else ""
        ),

        "status": status,

        "data_origin": "synthetic",
    })

    inv_counter += 1

    cur += timedelta(
        days=random.randint(10, 18)
    )


total_b2b_revenue = round(
    sum(c["amount"] for c in customer_invoices),
    2
)

total_retail_revenue = round(
    sum(
        float(r["amount"])
        for r in main
        if r["category"] == "Sales Revenue"
    ),
    2
)


print(
    f"\nB2B invoices generated: "
    f"{len(customer_invoices)}  "
    f"total={total_b2b_revenue}  "
    f"({round(100 * total_b2b_revenue / total_retail_revenue, 1)}% "
    f"of retail revenue)"
)


# Matching cash inflow in checking_main
# for every PAID B2B invoice.

b2b_cash_rows = []
bcid = 3000

for c in customer_invoices:

    if c["payment_date"]:

        b2b_cash_rows.append({

            "date": c["payment_date"],

            "transaction_id": f"TXB{bcid}",

            "description":
                f"B2B Invoice Payment - "
                f"{c['customer_name']} "
                f"({c['invoice_id']})",

            "category": "B2B Sales Revenue",

            "type": "Credit",

            "amount": str(c["amount"]),

            "data_origin": "synthetic",
        })

        bcid += 1


print(
    "Matching B2B cash-in rows for main:",
    len(b2b_cash_rows),
    "total=",
    round(
        sum(
            float(r["amount"])
            for r in b2b_cash_rows
        ),
        2
    )
)


# ---------------------------------------------------------------
# 4. SUPPLIER INVOICES (derived)
# Decompose expense transactions into invoices.
# ---------------------------------------------------------------

# Recurring costs such as rent, energy, maintenance,
# coffee and bakery purchases use one fixed supplier each.
#
# The mapping is based on transaction descriptions already
# present in Bronze. This creates consistent recurring
# supplier relationships instead of random reassignment.

DESCRIPTION_SUPPLIER_MAP = {

    "Rent Payment":
        (
            "Immobilien Bielefeld Mitte (Miete)",
            "Operating Expense",
            0,
            30
        ),

    "Utility Bill Payment":
        (
            "Stadtwerke Bielefeld (Energie)",
            "Operating Expense",
            5,
            21
        ),

    "Maintenance Payment":
        (
            "Buero- und Ladenausstattung Krause",
            "Operating Expense",
            7,
            14
        ),

    "Coffee Supplier Payment":
        (
            "Nordbohnen Roastery",
            "COGS",
            3,
            7
        ),

    "Bakery Payment":
        (
            "Gebaeck Grosshandel OWL",
            "COGS",
            1,
            7
        ),
}


# Fallback for categories/sources without
# a fixed-description mapping.
#
# Credit-card transactions use a random choice
# among a small list of plausible suppliers.

SUPPLIER_MAP = {

    "Supplies": [
        ("Gastro Einweg GmbH", 4),
        ("Kaffeezubehoer Handel Weber", 3)
    ],

    "Marketing": [
        ("Social Ads Agentur Bielefeld", 2),
        ("Print & Flyer Muller", 6)
    ],

    "Utilities": [
        ("Telekom Business", 3),
        ("Stadtwerke Bielefeld (Energie)", 5)
    ],

    "Other": [
        ("Buerobedarf Krause", 4),
        ("IT Service OWL", 6)
    ],
}


TERM_DAYS = {

    "COGS": 7,

    "Operating Expense": 30,

    "Supplies": 14,

    "Marketing": 21,

    "Utilities": 21,

    "Other": 14,
}


def build_supplier_invoices(rows, source):

    out = []

    for r in rows:

        cat = r["category"]

        desc = r.get(
            "description",
            ""
        )

        tx_date = d(r["date"])

        if desc in DESCRIPTION_SUPPLIER_MAP:

            supplier, inv_cat, lead, term = (
                DESCRIPTION_SUPPLIER_MAP[desc]
            )

        elif cat in SUPPLIER_MAP:

            supplier, lead = random.choice(
                SUPPLIER_MAP[cat]
            )

            inv_cat = cat
            term = TERM_DAYS[cat]

        else:

            continue


        invoice_date = (
            tx_date
            - timedelta(days=lead)
        )

        due_date = (
            invoice_date
            + timedelta(days=term)
        )


        out.append({

            "invoice_id":
                f"SINV_{source}_{r['transaction_id']}",

            "supplier_name":
                supplier,

            "category":
                inv_cat,

            "invoice_date":
                dstr(invoice_date),

            "due_date":
                dstr(due_date),

            "payment_date":
                r["date"],

            "amount":
                r["amount"],

            "status":
                "paid",

            "source_transaction_id":
                r["transaction_id"],

            "source_account":
                source,

            "data_origin":
                "derived",
        })

    return out


supplier_invoices = build_supplier_invoices(

    [
        r for r in main
        if r["category"]
        in ("COGS", "Operating Expense")
    ],

    "checking_main"
)


supplier_invoices += build_supplier_invoices(

    [
        r for r in cc
        if r["category"] in SUPPLIER_MAP
    ],

    "credit_card"
)


print(
    f"\nSupplier invoices generated: "
    f"{len(supplier_invoices)}  "
    f"total="
    f"{round(sum(float(x['amount']) for x in supplier_invoices), 2)}"
)


# ---------------------------------------------------------------
# 4b. RECURRING INGREDIENT-COST LAYER (derived)
# ---------------------------------------------------------------

# The Bronze source contains only episodic coffee and bakery
# supplier transactions. On its own, this produces a cost
# structure that does not adequately represent recurring
# ingredient expenditure for the Treasoria financial use case.
#
# This layer adds recurring coffee beans, dairy and bakery
# ingredient costs proportional to monthly retail sales.

TARGET_COGS_RATIO = 0.29
# Analytical target used for the recurring COGS layer.


monthly_retail_sales = defaultdict(float)

for r in main:

    if r["category"] == "Sales Revenue":

        monthly_retail_sales[
            r["date"][:7]
        ] += float(r["amount"])


existing_cogs_total = sum(

    float(r["amount"])

    for r in main

    if r["category"] == "COGS"
)


total_retail_sales = sum(
    monthly_retail_sales.values()
)


additional_cogs_ratio = max(

    0.0,

    TARGET_COGS_RATIO
    - (
        existing_cogs_total
        / total_retail_sales
    )
)


INGREDIENT_SPLIT = [

    (
        "Nordbohnen Roastery",
        0.45,
        "Coffee bean restock"
    ),

    (
        "Milchhof Bielefeld",
        0.25,
        "Dairy restock"
    ),

    (
        "Gebaeck Grosshandel OWL",
        0.30,
        "Bakery ingredient restock"
    ),
]


ingredient_rows = []

ing_id = 6000


for month, sales in sorted(
    monthly_retail_sales.items()
):

    year, mon = map(
        int,
        month.split("-")
    )

    month_cogs_addon = (
        sales
        * additional_cogs_ratio
    )


    for i, (
        supplier,
        share,
        label
    ) in enumerate(INGREDIENT_SPLIT):

        amount = round(
            month_cogs_addon
            * share,
            2
        )

        if amount <= 0:
            continue

        day = [8, 15, 22][i]


        ingredient_rows.append({

            "date":
                f"{year:04d}-{mon:02d}-{day:02d}",

            "transaction_id":
                f"TXI{ing_id}",

            "description":
                label,

            "category":
                "COGS",

            "type":
                "Debit",

            "amount":
                str(amount),

            "data_origin":
                "derived",
        })


        supplier_invoices.append({

            "invoice_id":
                f"SINV_ingredient_TXI{ing_id}",

            "supplier_name":
                supplier,

            "category":
                "COGS",

            "invoice_date":
                f"{year:04d}-{mon:02d}-{max(1, day - 5):02d}",

            "due_date":
                f"{year:04d}-{mon:02d}-{min(28, day + 7):02d}",

            "payment_date":
                f"{year:04d}-{mon:02d}-{day:02d}",

            "amount":
                amount,

            "status":
                "paid",

            "source_transaction_id":
                f"TXI{ing_id}",

            "source_account":
                "checking_main",

            "data_origin":
                "derived",
        })

        ing_id += 1


new_cogs_total = sum(

    float(r["amount"])

    for r in ingredient_rows
)


print(
    f"Recurring ingredient-cost layer: "
    f"{len(ingredient_rows)} rows, "
    f"total={round(new_cogs_total, 2)}  "
    f"(resulting COGS ratio ~"
    f"{round(100 * (existing_cogs_total + new_cogs_total) / total_retail_sales, 1)}% "
    f"of retail sales)"
)


# ---------------------------------------------------------------
# 4c. COST-SHOCK EVENTS (derived)
# ---------------------------------------------------------------

# Emergency business costs are added as derived cash outflows
# with matching supplier invoices.
#
# Each event has a clear date, supplier and business cause.

stress_outflows = [

    {
        "date": "2023-02-14",
        "id": "TXS9000",
        "amount": 8500.00,
        "description":
            "Storm damage - emergency roof and awning repair",
        "supplier":
            "Buero- und Ladenausstattung Krause",
        "invoice_date":
            "2023-02-10",
        "due_date":
            "2023-03-12",
    },

    {
        "date": "2023-06-12",
        "id": "TXS9001",
        "amount": 19500.00,
        "description":
            "Emergency walk-in cooler replacement",
        "supplier":
            "Kaeltetechnik Ostwestfalen GmbH",
        "invoice_date":
            "2023-06-05",
        "due_date":
            "2023-07-05",
    },

    {
        "date": "2023-07-08",
        "id": "TXS9002",
        "amount": 4200.00,
        "description":
            "Kitchen equipment emergency repair",
        "supplier":
            "Buero- und Ladenausstattung Krause",
        "invoice_date":
            "2023-07-01",
        "due_date":
            "2023-07-31",
    },

    {
        "date": "2023-06-20",
        "id": "TXS9003",
        "amount": 950.00,
        "description":
            "Energy price surcharge - Stadtwerke Bielefeld",
        "supplier":
            "Stadtwerke Bielefeld (Energie)",
        "invoice_date":
            "2023-06-15",
        "due_date":
            "2023-07-15",
    },

    {
        "date": "2023-07-20",
        "id": "TXS9004",
        "amount": 1050.00,
        "description":
            "Energy price surcharge - Stadtwerke Bielefeld",
        "supplier":
            "Stadtwerke Bielefeld (Energie)",
        "invoice_date":
            "2023-07-15",
        "due_date":
            "2023-08-14",
    },

    {
        "date": "2023-08-20",
        "id": "TXS9005",
        "amount": 1100.00,
        "description":
            "Energy price surcharge - Stadtwerke Bielefeld",
        "supplier":
            "Stadtwerke Bielefeld (Energie)",
        "invoice_date":
            "2023-08-15",
        "due_date":
            "2023-09-14",
    },
]


stress_main_rows = []


for row in stress_outflows:

    stress_main_rows.append({

        "date":
            row["date"],

        "transaction_id":
            row["id"],

        "description":
            row["description"],

        "category":
            "Operating Expense",

        "type":
            "Debit",

        "amount":
            str(row["amount"]),

        "data_origin":
            "derived",
    })


    supplier_invoices.append({

        "invoice_id":
            f"SINV_stress_{row['id']}",

        "supplier_name":
            row["supplier"],

        "category":
            "Operating Expense",

        "invoice_date":
            row["invoice_date"],

        "due_date":
            row["due_date"],

        "payment_date":
            row["date"],

        "amount":
            row["amount"],

        "status":
            "paid",

        "source_transaction_id":
            row["id"],

        "source_account":
            "checking_main",

        "data_origin":
            "derived",
    })


print(
    f"Stress-episode outflows added: "
    f"{len(stress_main_rows)}  "
    f"total="
    f"{round(sum(r['amount'] for r in stress_outflows), 2)}"
)


# ---------------------------------------------------------------
# 5. GERMAN PAYROLL BREAKDOWN (derived)
# ---------------------------------------------------------------

# The original payroll gross amounts are retained.
# The employee and employer components below are analytical
# approximations used for the Treasoria financial model.

RATES = {

    "rentenv": 0.093,

    "krankenv": 0.081,

    "arbeitslosenv": 0.013,

    "pflegev": 0.018,

    "rentenv_er": 0.093,

    "krankenv_er": 0.073,

    "arbeitslosenv_er": 0.013,

    "pflegev_er": 0.018,
}


def lohnsteuer_rate(
    gross_monthly,
    role
):

    # Simplified progressive approximation
    # for analytical purposes.

    if gross_monthly < 1200:
        return 0.06

    elif gross_monthly < 2000:
        return 0.11

    elif gross_monthly < 2800:
        return 0.16

    else:
        return 0.20


fact_payroll = []


for r in payroll:

    gross = float(r["amount"])


    ee_soc = gross * (

        RATES["rentenv"]

        + RATES["krankenv"]

        + RATES["arbeitslosenv"]

        + RATES["pflegev"]
    )


    tax = gross * lohnsteuer_rate(
        gross,
        r["role"]
    )


    net = (
        gross
        - ee_soc
        - tax
    )


    er_soc = gross * (

        RATES["rentenv_er"]

        + RATES["krankenv_er"]

        + RATES["arbeitslosenv_er"]

        + RATES["pflegev_er"]
    )


    employer_cost = (
        gross
        + er_soc
    )


    fact_payroll.append({

        "pay_date":
            r["pay_date"],

        "employee_id":
            r["employee_id"],

        "employee_name":
            r["employee_name"],

        "role":
            r["role"],

        "type":
            r["type"],

        "gross_pay":
            round(gross, 2),

        "employee_social_contrib":
            round(ee_soc, 2),

        "income_tax":
            round(tax, 2),

        "net_pay":
            round(net, 2),

        "employer_social_contrib":
            round(er_soc, 2),

        "employer_total_cost":
            round(employer_cost, 2),

        "account":
            r["account"],

        "data_origin":
            "derived",
    })


print(
    f"\nPayroll (German structure) rows: "
    f"{len(fact_payroll)}  "
    f"total gross="
    f"{round(sum(p['gross_pay'] for p in fact_payroll), 2)}  "
    f"total employer cost="
    f"{round(sum(p['employer_total_cost'] for p in fact_payroll), 2)}"
)


# ---------------------------------------------------------------
# 6. MERGE + RECOMPUTE RUNNING BALANCES
# ---------------------------------------------------------------

def merge_and_rebalance(
    original_rows,
    new_rows,
    opening_balance=0.0
):

    all_rows = []

    for r in original_rows:

        rr = dict(r)

        rr.setdefault(
            "data_origin",
            "original"
        )

        all_rows.append(rr)


    all_rows += new_rows


    # Stable sort by date.
    # Original rows remain before derived/synthetic rows
    # when several transactions share the same date.

    all_rows.sort(

        key=lambda r: (

            r["date"],

            0
            if r.get("data_origin") == "original"
            else 1
        )
    )


    bal = opening_balance


    for r in all_rows:

        amt = float(
            r["amount"]
        )

        signed = (
            amt
            if r["type"] == "Credit"
            else -amt
        )

        bal += signed

        r["balance"] = round(
            bal,
            2
        )


    return all_rows


def opening_balance_of(rows):

    first = rows[0]

    amt = float(
        first["amount"]
    )

    signed = (
        amt
        if first["type"] == "Credit"
        else -amt
    )

    return round(
        float(first["balance"])
        - signed,
        2
    )


main_opening = opening_balance_of(main)

sec_opening = opening_balance_of(sec)


print(
    f"\nDetected opening balances -> "
    f"main: {main_opening}, "
    f"secondary: {sec_opening}"
)


main_final = merge_and_rebalance(

    main,

    new_main_rows
    + b2b_cash_rows
    + stress_main_rows
    + ingredient_rows,

    opening_balance=main_opening
)


sec_final = merge_and_rebalance(

    sec,

    new_sec_rows,

    opening_balance=sec_opening
)


print(
    f"\nFinal checking_main: "
    f"{len(main_final)} rows, "
    f"ending balance = "
    f"{main_final[-1]['balance']}"
)


print(
    f"Final checking_secondary: "
    f"{len(sec_final)} rows, "
    f"ending balance = "
    f"{sec_final[-1]['balance']}"
)


# Credit-card balance is recomputed as well.
# Transactions themselves remain unchanged.

cc_final = []

bal = 0.0


for r in cc:

    rr = dict(r)

    rr["data_origin"] = "original"

    amt = float(
        r["amount"]
    )

    signed = (
        amt
        if r["type"] == "Debit"
        else -amt
    )

    bal += signed

    rr["balance"] = round(
        bal,
        2
    )

    cc_final.append(rr)


print(
    f"Credit card: "
    f"{len(cc_final)} rows, "
    f"ending balance owed = "
    f"{cc_final[-1]['balance']}"
)


# ---------------------------------------------------------------
# 7. WRITE SILVER CSVs
# ---------------------------------------------------------------

def write_csv(
    path,
    rows,
    fieldnames=None
):

    if not rows:
        return


    # Add the fictional company identity to every curated
    # Silver record while preserving the five immutable
    # Bronze source files unchanged.

    rows = [

        {

            "company_id":
                COMPANY_ID,

            "company_name":
                COMPANY_NAME,

            **row,
        }

        for row in rows
    ]


    fieldnames = (
        fieldnames
        or list(rows[0].keys())
    )


    with open(
        path,
        "w",
        newline=""
    ) as f:

        w = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        w.writeheader()

        w.writerows(rows)


write_csv(
    f"{SILVER}/fact_checking_main.csv",
    main_final
)

write_csv(
    f"{SILVER}/fact_checking_secondary.csv",
    sec_final
)

write_csv(
    f"{SILVER}/fact_credit_card.csv",
    cc_final
)

write_csv(
    f"{SILVER}/fact_payroll.csv",
    fact_payroll
)

write_csv(
    f"{SILVER}/fact_supplier_invoice.csv",
    supplier_invoices
)

write_csv(
    f"{SILVER}/fact_customer_invoice.csv",
    customer_invoices
)


print(
    "\nSilver CSVs written to",
    SILVER
)