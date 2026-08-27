# Code & Coffee GmbH — Data Dictionary

## Company scope

All Silver and Gold records belong to the fictional company used in Treasoria, `code_and_coffee` (**Code & Coffee GmbH**), owned by **Blue Jesus** and located at Ravensberger Str. 22, 33602 Bielefeld, Germany. Bronze files remain unchanged source snapshots and therefore do not receive company columns.

## Provenance

| Value | Meaning |
|---|---|
| `original` | Value retained unchanged from the public Kaggle source file. This does not mean real-world accounting data: the Kaggle source is itself synthetic. |
| `derived` | Value calculated or reconstructed from an original financial fact. |
| `synthetic` | New, transparently generated B2B activity used to complete the Treasoria use case. |

## Silver tables

| Table | Grain | Primary identifier | Purpose |
|---|---|---|---|
| `fact_checking_main` | One main-bank transaction | `transaction_id` | Retail/B2B receipts, operating payments, card repayments and internal transfers. |
| `fact_checking_secondary` | One payroll-bank transaction | `transaction_id` | Payroll funding and payroll payments. |
| `fact_credit_card` | One card transaction | `transaction_id` | Business card purchases and repayments. |
| `fact_payroll` | One employee payment per pay date | employee + `pay_date` | German-style analytical split of the original gross payroll. |
| `fact_supplier_invoice` | One reconstructed supplier invoice | `invoice_id` | Supplier, due-date and payment analysis linked to a source transaction. |
| `fact_customer_invoice` | One synthetic B2B invoice | `invoice_id` | Receivables, collection delays, late-payment rate and concentration analysis. |

All Silver tables include `company_id` and `company_name` for tenant traceability.

## Gold tables

| Table | Grain | Main measures |
|---|---|---|
| `gold_daily_cash_position` | One calendar day | Main balance, secondary balance, consolidated cash. |
| `gold_monthly_cash_flow` | One month | Cash-in, operating outflows, card repayments, payroll, total outflows, net cash flow. |
| `gold_receivables_aging` | One customer invoice | Status and days late. |
| `gold_payables_aging` | One supplier invoice | Status and days early/late. |
| `gold_payroll_summary` | One month in available Gusto extract | Employees, gross, net and analytical employer cost. |
| `gold_kpi_summary` | One KPI | Human-readable summary value. |

All Gold tables include `company_id` and `company_name`, which lets Streamlit, Power BI and the RAG assistant connect the financial values to Code & Coffee GmbH without relying on filenames.

## Important definitions

- **Consolidated cash** = main checking balance + secondary checking balance. Credit-card debt is reported separately as a liability.
- **Net cash flow** excludes transfers between the two bank accounts and includes credit-card repayments when cash leaves the main account.
- **Observed payroll cash-out** uses secondary-account debits. Employer social contributions are analytical only because no matching bank payments exist.
- **Average Customer Collection Time** is the average number of days from invoice issue to payment for paid B2B invoices; it is not labelled statutory DSO.
- **Average Supplier Payment Time** is the average number of days from supplier invoice date to payment; it is not labelled statutory DPO.

## Known source limitation

The secondary bank account contains a payroll debit of EUR 2,688 on 15 January 2022. The available `gusto_payroll.csv` extract starts in February 2022, so this row is documented as an opening/legacy payroll payment outside the payroll extract. It remains in observed cash flow and is not fabricated in the payroll fact table.
