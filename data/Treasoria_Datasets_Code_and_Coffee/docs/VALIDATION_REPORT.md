# Code & Coffee GmbH — Treasoria Validation Report

Status: **Validated for the Treasoria MVP**.

## Company Identity

- **Company:** Code & Coffee GmbH
- **Company ID:** `code_and_coffee`
- **Owner:** Blue Jesus
- **Address:** Ravensberger Str. 22, 33602 Bielefeld, Germany
- **Sector:** International Café & Gastronomy
- **Financial period:** January 2022 to December 2023

The company identity and address are fictional. The underlying Kaggle financial records are synthetic data and do not represent the accounting records of a real business.

## Accounting Validation

The validation process checks the core accounting identity:

`opening consolidated cash + cumulative external net cash flow = ending consolidated cash`

Expected control totals:

- **Opening consolidated cash:** EUR 17,000.00
- **Cumulative net cash flow:** EUR 217,549.89
- **Ending consolidated cash:** EUR 234,549.89
- **Average monthly net cash flow:** EUR 9,064.58
- **Main-account ending balance:** EUR 219,743.89
- **Secondary-account ending balance:** EUR 14,806.00
- **Credit-card ending liability:** EUR 21,651.00
- **Negative cash-flow months:** 1 out of 24

The accounting identity reconciles:

`EUR 17,000.00 + EUR 217,549.89 = EUR 234,549.89`

## Key Financial Controls

- **Cash-collected revenue:** EUR 625,759.90
- **Retail sales:** EUR 582,807.00
- **B2B sales collected:** EUR 42,952.90
- **Gross margin:** 73.0%
- **Average observed monthly cash outflows:** EUR 17,008.75
- **Average monthly analytical operating costs:** EUR 19,111.01
- **Open receivables:** EUR 1,153.95
- **Average Customer Collection Time:** 45.8 days
- **Late Customer Invoice Payment Rate:** 41.2%
- **Average Supplier Payment Time:** 4.0 days

## Document Coverage

The generated document layer contains:

- **330 supplier invoices**
- **51 B2B customer invoices**
- **72 bank and card statements**
- **453 PDF documents in total**

These documents support Treasoria's document-processing and OCR workflows.

## Documented Accounting Treatments

- Internal transfers between the main and secondary bank accounts are eliminated from consolidated cash flow.
- Credit-card repayments are retained as external cash outflows when cash leaves the main bank account.
- The January 2022 payroll debit is retained as an opening/legacy payment outside the February 2022–December 2023 Gusto extract.
- Employer contributions remain an analytical cost and are not inserted into bank cash flows because corresponding source payments are unavailable.
- Supplier payment time and customer collection time use explicit operational names rather than statutory DPO/DSO labels.
- Consolidated cash includes the main and secondary checking accounts. Credit-card debt is reported separately as a liability.

## Validation Result

The dataset passes the Treasoria integrity and reconciliation checks and is suitable for the MVP's financial analytics, dashboard, forecasting, liquidity-risk analysis, OCR workflows, and AI Financial Assistant.