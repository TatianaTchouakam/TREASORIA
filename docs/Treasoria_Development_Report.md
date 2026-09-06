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

---

## 1. AI Financial Assistant

### Purpose
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

---

## 2. Invoices & OCR

### Purpose
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

### Purpose
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

### Purpose
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

### Purpose
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

### Purpose
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
