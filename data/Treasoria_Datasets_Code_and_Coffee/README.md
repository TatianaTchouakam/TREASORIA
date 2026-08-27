# Code & Coffee GmbH — Treasoria Dataset

*Where Coffee Meets Data.*

Fictional identity used by Treasoria: **Code & Coffee GmbH**, owned by **Blue Jesus**, Ravensberger Str. 22, 33602 Bielefeld, Germany.

Business: international café and gastronomy, with a secondary B2B activity in catering and wholesale.

> **Important:** The company name, owner, address, and business identity are synthetic and do not describe a real registered business or real accounting records.

4 employees. Period covered: 01/01/2022 - 31/12/2023 (24 months).

## What This Dataset Contains

This package builds a complete and internally consistent 24-month financial history for a small café business.

It starts from a public synthetic Kaggle source and enriches it into a realistic small-business treasury use case covering transactions, payroll, supplier and customer invoices, cash positions, financial KPIs, a canonical SQLite database, and matching PDF documents for OCR testing.

Two elements were deliberately added to provide meaningful signals for Treasoria's forecasting and liquidity-risk features rather than producing a smooth, always-positive cash trajectory.

### 1. Recurring Ingredient-Cost Layer

A recurring, sales-proportional ingredient-cost layer covers coffee beans, dairy, and bakery inputs.

The analytical target brings cost of goods sold to approximately 29% of retail sales, resulting in a gross margin of 73.0%.

Rent, utilities, and maintenance each use one fixed recurring supplier, reflecting the structure of ongoing business contracts. Rent, for example, is associated with one landlord and one invoice per month across the 24-month period.

### 2. Dated Business Events

Two documented business events are included:

- **February 2023:** Storm damage requiring an emergency roof and awning repair of EUR 8,500. Net cash flow for the month was approximately +EUR 2,798.
- **June–July 2023:** An emergency walk-in cooler replacement of EUR 19,500 and kitchen equipment repair of EUR 4,200, combined with a three-month energy price surcharge and delayed payments from a large B2B client.

June 2023 produced the only negative net cash-flow month in the 24-month period at approximately -EUR 15,957. July recovered to approximately +EUR 2,019.

Every added record remains traceable through its provenance classification.

## Data Transparency (`data_origin`)

- **`original`** — Value unchanged from the Kaggle source files. The Kaggle dataset itself contains synthetic financial data and does not represent the real accounting records of a business.
- **`derived`** — Value calculated or reconstructed from an existing financial fact, including supplier invoices, payroll analytics, recurring ingredient costs, treasury reconciliations, and documented business events.
- **`synthetic`** — New records generated specifically for the Treasoria use case, including B2B customer invoices and their collection activity.

## Folder Structure

- `bronze/` — The five Kaggle source files, preserved unchanged.

- `silver/` — Cleaned and enriched tables:
  - `fact_checking_main.csv`
  - `fact_checking_secondary.csv`
  - `fact_credit_card.csv`
  - `fact_payroll.csv`
  - `fact_supplier_invoice.csv`
  - `fact_customer_invoice.csv`

- `gold/` — Tables prepared for analytics and dashboards:
  - `gold_daily_cash_position.csv`
  - `gold_monthly_cash_flow.csv`
  - `gold_receivables_aging.csv`
  - `gold_payables_aging.csv`
  - `gold_payroll_summary.csv`
  - `gold_kpi_summary.csv`

- `docs/` — Generated PDF documents used for document-processing and OCR workflows:
  - 330 supplier invoices
  - 51 B2B customer invoices
  - 72 monthly bank/card statements
  - 453 PDF documents in total

- `treasoria.db` — Canonical SQLite database containing dimensions, Silver tables, Gold tables, and dataset metadata.

- `scripts/build_dataset.py` — Deterministically rebuilds the Silver tables from Bronze.

- `scripts/rebuild_gold_and_database.py` — Recalculates the Gold tables, creates SQL dimensions, and rebuilds SQLite.

- `scripts/build_pdfs.py` — Regenerates the 453 PDF documents.

- `scripts/validate_dataset.py` — Runs reconciliation, relationship, SQLite, identity, and document-coverage checks.

- `docs/DATA_DICTIONARY.md` — Table definitions, provenance, and KPI definitions.

- `docs/VALIDATION_REPORT.md` — Accounting controls and validation results.

- `docs/SOURCES.md` — Source attribution and licensing information.

- `docs/DATASET_METHODOLOGY.md` — Cost-model methodology and documented business events.

- `company_profile.json` — Canonical fictional company identity used across the project.

## Quick Start

From the dataset root:

```bash
python scripts/build_dataset.py
python scripts/rebuild_gold_and_database.py
python scripts/build_pdfs.py
python scripts/validate_dataset.py
```

The scripts automatically resolve the dataset root from their own location. No manual path configuration is required.

## Dimensions Present in SQLite

The canonical SQLite database includes:

- `dim_company`
- `dim_account`
- `dim_employee`
- `dim_customer`
- `dim_supplier`
- `dim_category`

These dimensions complement the fact tables and support SQL exploration, Power BI modelling, and Treasoria analytics.

## Reconciliation Notes

### Payroll Funding

Derived top-up transfers reconcile payroll debited from the secondary account with funding from the main account.

The January 2022 payroll debit of EUR 2,688 is documented as an opening/legacy payment outside the available Gusto extract, which begins in February 2022.

### Transfers and Credit-Card Repayment

Transfers from the main account to the secondary account total EUR 175,348.

Credit-card repayment from the main account totals EUR 15,146.

These derived outflows mirror entries already present on the secondary account and credit-card side.

## Key KPIs

See `gold/gold_kpi_summary.csv` for the complete KPI table.

- Total cash-collected revenue: EUR 625,759.90
- Retail sales: EUR 582,807.00
- B2B sales collected: EUR 42,952.90
- Gross margin: 73.0%
- Consolidated cash balance at end of period: EUR 234,549.89
- Credit-card debt at end of period: EUR 21,651.00
- Consolidated opening cash: EUR 17,000.00
- Cumulative net cash flow: EUR 217,549.89
- Average monthly net cash flow: EUR 9,064.58
- Average observed monthly cash outflows: EUR 17,008.75
- Average monthly analytical operating costs: EUR 19,111.01
- Runway: Not burning cash at period end based on the recent three-month average net cash flow
- Negative net cash-flow months: 1 out of 24
- Average Customer Collection Time: 45.8 days
- Late Customer Invoice Payment Rate: 41.2%
- Open receivables: EUR 1,153.95
- Average Supplier Payment Time: 4.0 days

## Known Simplification

Credit-card spending in the Marketing, Utilities, Supplies, and Other categories uses a randomised supplier selection from a short candidate list rather than one fixed supplier per category.

This represents a relatively small portion of the ledger compared with recurring rent, payroll, and cost of goods sold.

## Limitations

The short supplier payment time of approximately 4.0 days reflects the fact that payment dates are anchored to the transaction dates available in the source data.

It is therefore presented as **Average Supplier Payment Time** rather than a statutory accounting DPO.

Similarly, the customer metric is presented as **Average Customer Collection Time** rather than statutory DSO because it is reconstructed from the synthetic B2B flow.

Employer contributions in the payroll table are analytical costs. They are not added to observed bank outflows because corresponding source payments are unavailable.

Observed cash flow therefore uses the payroll actually debited from the secondary account.