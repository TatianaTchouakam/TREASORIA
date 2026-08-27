# Code & Coffee GmbH — Data Sources and Licensing

## Fictional Company Identity

Code & Coffee GmbH, owned by Blue Jesus and located at Ravensberger Str. 22, 33602 Bielefeld, Germany, is the fictional company identity assigned to this dataset for the Treasoria project.

This identity was not supplied by Kaggle and must not be interpreted as a real registered business.

## Main Treasoria Company Dataset

- **Title:** Small Business Financial Dataset (2022–2023)
- **Publisher:** Gabrielle Charlton
- **Platform:** Kaggle
- **URL:** https://www.kaggle.com/datasets/gabriellecharlton/coffee-shop-financial-dataset-synthetic-2022-2023
- **Licence:** MIT License
- **Description:** The source simulates the financial records of a small-town coffee shop from January 2022 through December 2023. It is intended for data-science, bookkeeping, and analytics projects such as dashboards, revenue forecasting, and expense tracking.
- **Files used:** `checking_account_main.csv`, `checking_account_secondary.csv`, `credit_card_account.csv`, `gusto_payroll.csv`, `gusto_payroll_bc.csv`.
- **Treatment in Treasoria:** The five source files are preserved unchanged in the Bronze layer. Silver contains cleaned and traceable enrichments assigned to Code & Coffee GmbH. Supplier invoices are derived from source transactions, while the B2B activity and customer invoices are synthetic Treasoria additions. PDF documents are generated artifacts used for document-processing and OCR workflows.

## Licence

The source dataset is distributed under the **MIT License**.

The original Bronze files are preserved unchanged in Treasoria and the source dataset is credited to its original publisher.

The MIT License permits reuse, modification, distribution, and commercial use subject to its licence conditions. When the Bronze source files are redistributed, the applicable copyright and licence notice should be retained.

## Data Provenance in Treasoria

Treasoria distinguishes between three types of data provenance:

- **`original`** — Values preserved unchanged from the Kaggle source files. The Kaggle dataset itself contains synthetic financial data and does not represent the accounting records of a real company.
- **`derived`** — Values calculated, reconstructed, or enriched from existing financial facts in order to build the analytical dataset.
- **`synthetic`** — New records generated specifically for the Treasoria use case, including the B2B customer activity required for receivables and payment-delay analysis.

This distinction is preserved in the Silver layer through the `data_origin` field wherever applicable.

## External Late-Payment Model Dataset

The external invoice dataset intended for the separate late-payment prediction model is not included in this package.

When incorporated, its exact title, creator, source URL, and licence must be documented separately.

The external dataset must remain clearly separated from the Code & Coffee GmbH financial dataset so that its provenance, licence, purpose, and modelling role remain traceable.