# Treasoria — Development Report

---

## Overview — one table, the full picture

| Module | Main tools | Result | Issues found |
|---|---|---|---|
| AI Financial Assistant | LlamaIndex, Groq LLM, sentence-transformers, SQLite | Hybrid assistant: exact structured answers (SQL) + document-based answers (RAG) | — |
| Streamlit interface | Streamlit | Navigation structure, base Overview page, custom visual theme | — |
| Invoices & OCR | Tesseract, pdf2image, regex, jiwer | Invoice and bank statement extraction, per-field confidence scoring, CER/WER evaluation | 4 real OCR bugs |
| Data Quality | pandas, datetime | 4 automated checks + bulk invoice import from spreadsheet | No major bugs |
| KPI Validation | pandas | 6 figures recomputed and verified against their source | No discrepancy detected |
| Dashboard Finalisation | pandas, Streamlit cache | Full export + manual refresh | — |
| Transactions | pandas, altair | Filterable ledger, 1,306 transactions, CSV export | 1 classification bug |
| Cash-Flow Forecast | statsmodels/Prophet/XGBoost (Aysenur's pipeline), pandas, altair | Daily 90-day forecast connected to the dashboard, with business-friendly summary and directional status | — |
| Liquidity Risk | pandas | 6 risk signals connected to the forecast, transaction history, and customer invoices | — |
| What-if Simulator | pandas | 7 combinable scenarios, connected to Liquidity Risk and the AI Assistant | 1 session-state bug |

---

## 1. AI Financial Assistant

### What this module does
A conversational assistant built to answer financial questions about Treasoria, combining two approaches depending on the question type — using **LlamaIndex** *(framework orchestrating document retrieval and response generation — RAG)*, **Groq LLM** *(the language model that generates the response)*, **sentence-transformers** *(converts text into numeric vectors for semantic search)*, and **SQLite** *(structured database, for exact numeric answers)*.

### Tools used and their role

| Tool | Exact role |
|---|---|
| **LlamaIndex** | Orchestrates document retrieval and answer construction (RAG — Retrieval-Augmented Generation) |
| **Groq LLM** | Generates the natural-language response |
| **sentence-transformers** | Converts text into numeric vectors, to retrieve the most relevant passages by similarity |
| **SQLite** | Stores structured financial data, enables exact numeric answers without going through the LLM |

### How it works
Each question is routed: if it matches a precise numeric query (e.g. "what is my current balance?"), the answer comes directly from a SQL query against the structured database — exact, not generated. Otherwise, the question goes through the RAG pipeline (document retrieval + LLM-generated response), for more open-ended or explanatory questions.

### Extended this session
Three new structured questions were added, to support the connection between the assistant and the upcoming Liquidity Risk / What-if modules: top expense category, top revenue category, and best-selling product. The last one reads from a new synthetic product-level table (see Section 8, Liquidity Risk, for the full data provenance note — the same table is described there since it was built alongside that work).

---

## 2. Invoices & OCR

### What this module does
Turns an invoice or bank statement (PDF, image, or Excel file) into structured, usable data, with a confidence score on every extracted field, combining **pdf2image** *(renders a PDF page as an image)*, **Tesseract** *(reads the text in the image)*, **regex** *(isolates specific fields)*, and **jiwer** *(measures the error rate)*.

### Tools used and their role

| Tool | Exact role |
|---|---|
| **pdf2image** | Converts a PDF page into an image, since Tesseract can only "read" pixels, not a PDF directly |
| **Pillow (PIL)** | Handles images in memory, the link between pdf2image and Tesseract |
| **Tesseract (via pytesseract)** | The character recognition engine — looks at the image and predicts which letters are drawn |
| **re (regex)** | Searches for specific patterns in the raw text ("Invoice No.:", amounts, dates) to extract values |
| **jiwer** | Computes CER (character error rate) and WER (word error rate) between the read text and the known-correct value |
| **pandas** | Structures the extracted fields into a table, reads/writes Excel files |
| **openpyxl** | The engine that actually writes the .xlsx format (used internally by pandas) |

### Key functions

| Function | Role |
|---|---|
| `pdf_to_image` / `pdf_to_images` | Converts one (or all) page(s) of a PDF into image(s) |
| `load_image` | Loads a photo/image directly, without going through a PDF |
| `image_to_raw_text` / `images_to_raw_text` | Runs Tesseract on the image to obtain raw text |
| `extract_invoice_number`, `extract_invoice_date`, `extract_due_date`, `extract_total_due`, `extract_status`, `extract_paid_on` | Each extracts one specific invoice field via regex |
| `extract_line_item` | Extracts the table row (counterparty, category, Net/VAT/Total amounts) |
| `get_ocr_data` | Retrieves Tesseract's word-level data, with a confidence score per word |
| `confidence_for_value` | Computes the average confidence of an extracted field from the words that make it up |
| `compute_overall_confidence` / `determine_review_status` | Compute an overall score and a status (Validated / Needs review / Rejected) |
| `compute_cer` / `compute_wer` | Measure the gap between the read text and the ground truth |
| `is_bank_statement` | Detects whether the document is a bank statement rather than an invoice |
| `extract_statement_metadata` / `extract_statement_transactions` | Extract the header and **all** transactions of a statement |
| `build_excel_download`, `build_image_download`, `build_excel_download_from_df`, `read_pdf_bytes` | Prepare downloadable files |

### Issues found and fixed

1. **Different label depending on invoice type** — supplier invoices say "Invoice date:", customer invoices say "Issue date:". A regex anchored to only one label returned an empty field on the other type.
   → *Fixed by matching either label.*

2. **Table row split across two lines by OCR** — the total amount sometimes landed on its own line, separated by a blank line, instead of staying on the same line as the rest of the row.
   → *Fixed by looking ahead up to 3 lines, skipping blank lines.*

3. **Case-sensitive category matching hid a real OCR error** — Tesseract had read "COGS" as "coGs"; an exact-match comparison didn't recognise it at all (returned empty), making any CER/WER measurement on it meaningless.
   → *Fixed with case-insensitive matching, while keeping the actual raw text (not the corrected version) so CER/WER measures the real error.*

4. **Multi-page bank statement truncated** — the reader only picked up the first page; a 2-page statement silently lost 13 transactions (stopped at July 22 instead of July 31).
   → *Fixed with dedicated functions that read and combine every page.*

---

## 3. Data Quality

### What this module does
Checks that an extracted invoice (or a batch of invoices imported from Excel) is consistent and usable before marking it "ready to integrate" — relying on **pandas** *(loads and compares data)* and **datetime** *(compares dates against each other)*.

### Tools used and their role

| Tool | Exact role |
|---|---|
| **pandas** | Loads already-known invoices (Silver) for duplicate detection, reads Excel imports |
| **datetime** | Compares dates against each other (Due date must be after Invoice date) |

### Key functions

| Function | Role |
|---|---|
| `check_missing_fields` | Checks that no required field is empty |
| `check_date_consistency` | Checks that the due date is on or after the invoice date |
| `check_amount_consistency` | Checks that Net + VAT = Total (within a 1-cent tolerance) |
| `load_existing_invoice_numbers` | Loads every invoice number already recorded |
| `check_duplicate` | Flags an invoice that has already been processed |
| `run_data_quality_checks` | Combines the 4 checks into one clear result |
| `process_excel_import` | Applies the same checks to several invoices at once, from an Excel file |

### Issues found
No major bugs — the main work was defining the exact **scope** of the checks (which fields are genuinely required, what tolerance to allow on amounts) rather than fixing code errors.

---

## 4. KPI Validation

### What this module does
Recomputes 6 figures shown on the dashboard **independently**, from raw data, to verify they match what's stored — instead of blindly trusting a pre-calculated file. Relies entirely on **pandas** *(loads source tables and performs the recalculations)*.

### Tools used and their role

| Tool | Exact role |
|---|---|
| **pandas** | Loads source tables (Gold/Silver) and performs the recalculations (sums, averages, latest value) |

### Key functions

| Function | Role |
|---|---|
| `parse_eur_value` | Converts a stored string like "234,549.89 EUR" into a usable number |
| `recompute_closing_cash_balance` | Recomputes the closing cash balance |
| `recompute_average_monthly_net_cash_flow` | Recomputes the average monthly net cash flow |
| `recompute_open_receivables` | Recomputes total unpaid customer receivables |
| `recompute_credit_card_debt` | Recomputes the credit card debt |
| `recompute_cash_collected_revenue` | Recomputes cash-collected revenue |
| `validate_kpi` | Compares a stored value against its recomputed version |
| `validate_runway` | Checks that the "Runway" text is consistent with the recomputed trend |
| `run_all_kpi_validations` | Combines the 6 checks into one result |
| `build_overview_export` | Assembles all 17 dashboard figures with their verification status |

### Issues found
No discrepancy detected — the 6 recomputed figures matched exactly what was stored, down to the cent, confirming the reliability of the Gold pipeline.

---

## 5. Dashboard Finalisation

### What this module does
Adds two practical features to the dashboard: refreshing data without restarting the app, and downloading the full set of figures (not just the 6 shown on screen) — via **pandas** *(assembles the export table)* and the **Streamlit cache** *(stores results in memory; the Refresh button clears it to force a recalculation)*.

### Tools used and their role

| Tool | Exact role |
|---|---|
| **pandas** | Assembles the full export table |
| **Streamlit cache** (`st.cache_data`) | Stores results in memory for speed; the "Refresh" button clears it to force a recalculation |

### Key functions

| Function | Role |
|---|---|
| `load_kpi_validation_results` | Loads validation results, cached |
| `render_kpi_validation_badge` | Displays the trust badge (🟢/🟠) on the dashboard |

---

## 6. Transactions

### What this module does
Combines 3 accounts (main checking, secondary checking, credit card) into one filterable ledger, with export and category breakdown — via **pandas** *(loads, combines, filters, and aggregates)* and **altair** *(draws the breakdown chart)*.

### Tools used and their role

| Tool | Exact role |
|---|---|
| **pandas** | Loads, combines, filters, and aggregates the 3 source tables |
| **altair** | Draws the category breakdown bar chart |

### Key functions

| Function | Role |
|---|---|
| `load_and_normalize_source` | Loads a source table and harmonises its column names |
| `load_all_transactions` | Combines the 3 accounts into one table, with derived columns (Money in/out, Confirmed/Needs review, Internal/Real) |
| `category_breakdown` | Summarises transaction count and total amount per category |
| `build_csv_export` | Prepares the filtered table for download |

### Issues found and fixed

**Incomplete internal-transfer detection** — exact category matching ("Transfer", "Payroll") missed real variants like "Transfer Out". Result: only one side of each transfer was being detected (94 out of ~188 expected).
→ *Confirmed by comparing counts*: Secondary Checking had exactly 94 internal transfers recorded, but only 94 were detected in total across all 3 accounts — proof that half were missing.
→ *Fixed* by matching on keyword presence anywhere in the category, instead of requiring an exact match. Result after the fix: 141 internal transfers detected.

---

## 7. Cash-Flow Forecast

### Purpose
Projects the company's cash balance over the next 90 days, based on a forecasting pipeline built by Aysenur — comparing multiple time-series models, selecting the best-performing one through cross-validation, and connecting the result to a business-friendly Streamlit page. Integration uses **pandas** *(loads and reshapes the forecast output)* and **altair** *(draws the Actual → Forecast chart with uncertainty band)*.

### Forecasting pipeline (built by Aysenur)

| Tool | Exact role |
|---|---|
| **statsmodels (SARIMA)**, **Prophet**, **XGBoost** (deferred) | Candidate time-series models compared against simple baselines (naive, seasonal naive, moving average) |
| **Expanding-window cross-validation** | Evaluates each candidate on multiple chronological train/validation splits, rather than a single split |
| **pandas** | Data preparation, reconciliation between daily and monthly cash-flow series |

Two tracks were built and evaluated independently: **monthly** (24 historical observations, 3-month forecast) and **daily** (730 historical observations, 90-day forecast). Six candidate models were compared per track; the selected models were:

| Track | Selected model | Validation MAE | Retrospective test MAE |
|---|---|---:|---:|
| Monthly | seasonal_naive_12m | 5,040.74 EUR/month | 2,104.78 EUR/month |
| Daily | Prophet_flat_calendar | 531.23 EUR/day | 513.96 EUR/day |

Only the **daily track** was connected to the app for this iteration (see "Decision" below).

### Streamlit integration (this session)

| Function | Role |
|---|---|
| `load_forecast` | Loads the evaluated forecast output for one track (daily or monthly) |
| `load_leaderboard` | Loads the full model comparison table for a track |
| `get_forecast_summary` | Extracts the handful of headline figures (model, reference date, starting/final balance) a page needs |

The Cash-Flow Forecast page shows: current balance, projected balance in 90 days, and the minimum expected balance with its date — followed by a combined Actual → Forecast chart with a shaded uncertainty band. A simple directional status (Stable / Attention / Risk) is shown, based purely on the shape of the forecast trend — **no fixed EUR risk threshold is used**, since the pipeline's own handoff notes explicitly state that policy thresholds are a business decision still to be made, not something to invent.

### Decision: daily track only, for now

The monthly track was not connected in this session. Two reasons:
1. The forecasting pipeline's own integration example indexes into day-level rows (`iloc[34]`), which only makes sense against the daily output.
2. Several upcoming Liquidity Risk signals (e.g. days below a threshold) and What-if scenarios (e.g. a payment delayed by a specific number of days) need day-level granularity; the monthly track (3 data points) cannot support them meaningfully.

This was confirmed correct once Liquidity Risk was built (Section 8): several signals depend directly on the daily forecast.

### What is explicitly not yet built
Per the forecasting pipeline's own handoff notes, the following remained open decisions for the next module (Liquidity Risk), not gaps in the forecast itself: policy thresholds, gross sales/expense scenario drivers, invoice-level payment delay scheduling, and detection of unusual outflows or customer concentration. All four are now addressed in Section 8.

### Issues found
None in the integration itself. One design correction was made along the way: the Overview page's "Negative Cash-Flow Months" card previously counted negative months across the full 24-month history and displayed only a fraction (e.g. "1 / 24"). This was changed to a rolling 12-month window with the actual month names shown directly, since a 2-year-old negative month is not actionable for a same-day decision and a bare fraction does not say *when* it occurred.

---

## 8. Liquidity Risk

### Purpose
Turns the forecast and known financial data into 6 concrete, defined risk signals a business owner can act on — built entirely with **pandas** *(loads source tables, performs the statistical and comparison logic behind each signal)*.

### The 6 signals

| Signal | Source data | What it checks |
|---|---|---|
| Low Balance | Daily forecast | Lowest projected balance vs. 3 / 1.5 months of real average monthly spending |
| Cash Running Out Soon | Daily forecast | Number of days in the 90-day forecast below the critical threshold, and the first date it happens |
| Unexpected Big Expense | Transaction history (`fact_checking_main.csv`) | Statistical anomaly detection (z-score) against each category's own historical average |
| Negative Trend | Monthly cash flow (Gold) | Recent 3-month average net cash flow vs. the 3 months before that |
| High Uncertainty | Daily forecast | Width of the forecast's own uncertainty band, relative to the current balance |
| Relying on One Customer | Customer invoices (`fact_customer_invoice.csv`) | Top customer's share of total business invoice revenue |

Each signal reports: severity (Stable / Attention / Risk), amount, date (where applicable), a plain-language justification, and a suggested action. An overall status is calculated as the most serious individual signal found.

### No invented thresholds
Per the forecast pipeline's own handoff notes ("There is no invented universal risk limit"), every threshold used is either a standard, citable practice or derived from the company's own real figures — never an arbitrary guess:
- **Low Balance / Cash Running Out Soon**: months of runway (3 / 1.5 months) is a standard small-business treasury guideline, applied to this company's own real average monthly outflow (not a bare EUR figure, which means nothing without knowing the real spending rate).
- **Unexpected Big Expense**: a z-score (how many standard deviations above a category's own average) is a standard statistical anomaly-detection method. Verified against this dataset's two documented real events — the EUR 19,500 cooler replacement (z=8.69) and EUR 8,500 storm damage (z=3.62) — both surface correctly.
- **High Uncertainty**: reuses the forecast's own uncertainty band directly, rather than inventing a separate uncertainty measure.
- **Relying on One Customer**: a percentage-of-revenue concentration check, a standard business-risk practice.

### Plain-language rewrite
All user-facing text (signal titles, justifications, suggested actions) was reviewed and rewritten for a non-technical reader after an initial pass still contained finance/stats jargon. Removed terms included "z-score", "runway", "outflow", "concentration", "B2B", and "critical threshold" — each replaced with an everyday equivalent (e.g. "Short Runway" → "Cash Running Out Soon"; "Customer Concentration" → "Relying on One Customer"). One awkward repeated-word phrasing ("This Operating Expense expense...") was also corrected to a category-name-agnostic sentence structure, since the original wording would have repeated on other category names too (e.g. "Credit Card Payment payment").

### New synthetic data: product-level sales
To support a "which product brings in the most money" question (for the AI Assistant, Section 1) and a Top-Selling Products chart on Overview, a new table was created: `fact_product_sales.csv` — 20 café products with revenue estimated by splitting the real, known total Sales Revenue (EUR 582,807.00) across them by plausible weight. The breakdown sums back exactly to that real total. Labelled `data_origin=synthetic` in the same column already used for this dataset's other synthetic records (e.g. B2B customer invoices), consistent with the existing provenance convention documented in the dataset's own README. The table was picked up automatically by the existing Gold/database rebuild script, with no script changes needed.

### Overview page: chart bug fix
While reviewing the dashboard, a real bug was found in the Monthly Net Cash Flow chart: months were displayed in alphabetical order (Apr, Aug, Dec, Feb...) instead of chronological order — caused by Streamlit's built-in `bar_chart` defaulting to alphabetical sort on text-typed axis labels. Fixed by replacing it with an explicit Altair chart with the correct chronological sort order passed directly.

### Issues found and fixed
No bugs in the risk logic itself. Two rounds of language review were needed before the signals were fully free of technical jargon (see "Plain-language rewrite" above) — the first pass looked correct in isolation but still read as written for an analyst, not a business owner.

---

## 9. What-if Simulator

### Purpose
Lets a business owner test how a decision would affect cash before making it — seven plain-language scenarios, combinable, closing the full Predict → Explain → Simulate → Decide loop by connecting directly to both the Liquidity Risk module and the AI Assistant. Built with **pandas** *(prepares the dated cash-flow adjustments)*.

### The 7 scenarios

| Scenario | What the user enters |
|---|---|
| Customer payment delay | Amount, expected date, days late |
| Expense increase | Extra monthly amount, start date |
| Sales decrease | Reduced monthly amount, start date |
| Product change | Product, sales volume or price, percent change, start date, duration |
| New hire | Monthly salary, start date |
| Equipment purchase | Cost, purchase date |
| Loan repayment | Monthly payment, start date, number of months |

Multiple scenarios can be selected and run together in a single simulation (e.g. a late payment and an expense increase tested at once).

### Built on Aysenur's tested integration layer, not reimplemented
Rather than writing new logic to shift cash-flow values, every scenario translates into a dated `net_flow_delta_eur` adjustment and is applied through `apply_cash_flow_adjustments()` and summarised through `summarize_cash_risk()` — both already written and tested by Aysenur in `src/forecast/integration.py` as part of the forecast handoff. This avoids duplicating validated logic and guarantees the same reconciliation guarantees (e.g. a delayed receipt cannot silently vanish from the scenario).

### Key functions (`src/what_if.py`)

| Function | Role |
|---|---|
| `scenario_customer_payment_delay`, `scenario_expense_increase`, `scenario_sales_decrease`, `scenario_new_hire`, `scenario_equipment_purchase`, `scenario_loan_repayment`, `scenario_product_change` | Each translates one plain-language scenario into a small table of dated EUR adjustments |
| `build_summary_sentence` | Turns the two numeric summaries (before/after) into one plain-English sentence |

### Connected to Liquidity Risk, not a separate risk logic
The result includes a fifth metric, "Liquidity status", computed by calling `evaluate_low_balance()` directly from the Liquidity Risk module on the scenario's resulting forecast — the same thresholds already validated (3 / 1.5 months of average spending), not a new or looser rule invented for this page.

### Connected to the AI Assistant
An "Ask Treasoria AI: Explain this scenario" button sends the actual computed figures (amounts, dates, lowest balance, liquidity status) as a pre-filled question to the existing chat engine, and displays the answer inline. This is the first point in the app where Forecast, Liquidity Risk, and the AI Assistant are used together in one user action, rather than as three separate features.

### Product change scenario — data provenance note
This scenario reads from `fact_product_sales.csv` (see Section 8's data provenance note) — a synthetic, illustrative revenue breakdown, not real per-product transaction history. Monthly revenue for a product is derived by dividing its total estimated revenue by the 24 months represented in the dataset.

### Issues found and fixed
**Result disappearing after asking the AI to explain it** — `st.button()` in Streamlit is only `True` on the exact page rerun it triggers. Clicking "Ask Treasoria AI" triggered a new rerun where the "Run simulation" button evaluated to `False` again, so the result and comparison chart — which were rendered inside that button's own `if` block — disappeared, even though the simulation itself was still valid.
→ *Fixed* by storing the full scenario result in `st.session_state` when the simulation runs, and rendering the result, metrics, and chart from that stored state outside the button's `if` block — so they persist across any later interaction on the page, including asking the AI to explain them.
