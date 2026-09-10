"""
Treasoria — OCR pipeline, PDF -> Image -> Raw Text

Goal: prove we can take a real invoice PDF and get readable text
out of it. Field extraction, confidence scores and CER/WER
evaluation all come later, once this foundation is solid.
"""
# ------------------------------------------------------------------
# KNOWN ISSUES ENCOUNTERED DURING DEVELOPMENT (and how they were fixed)
# ------------------------------------------------------------------
# 1. Label mismatch between invoice types
#    Supplier invoices use "Invoice date:", customer invoices use
#    "Issue date:" instead. A regex anchored to only one label
#    silently returned an empty string on the other invoice type.
#    Fix: extract_invoice_date() now matches EITHER label via
#    "(?:Invoice date|Issue date)".
#
# 2. Table row split across multiple lines by Tesseract
#    On some customer invoices, the third amount (the total) landed
#    on its own line instead of staying with the rest of the row --
#    sometimes with a BLANK line in between. A naive "check only the
#    next line" approach missed the amount entirely.
#    Fix: find_table_line() looks ahead up to 3 lines, skipping
#    blank lines, to find the missing amount.
#
# 3. Case-sensitive category matching hid real OCR errors
#    Tesseract read "COGS" as "coGs" on one invoice. Matching
#    against KNOWN_CATEGORIES was case-sensitive, so the category
#    was not recognised at all (silently returned "" instead of a
#    wrong-but-present value) -- and any CER/WER measurement on it
#    would have been meaningless.
#    Fix: category matching is now case-INsensitive (re.IGNORECASE),
#    but the function still returns the RAW text as OCR produced it
#    (e.g. "coGs"), not the canonical spelling. This is deliberate:
#    canonicalising the value at this stage would hide the very OCR
#    error CER/WER is meant to measure. Canonicalisation, if needed,
#    belongs in a later Data Quality step, not here.
#
# 4. Statement documents spanning multiple pages
#    Invoices are always a single page, so pdf_to_image() only reads
#    page 1 -- fast and sufficient for them. Bank/card statements
#    can span 2+ pages once a month has enough transactions:
#    confirmed on checking_main_2023-07.pdf, where reading only
#    page 1 silently dropped 13 transactions (stopped at July 22
#    instead of July 31).
#    Fix: pdf_to_images() / images_to_raw_text() read and OCR every
#    page for statement documents, joining the text before running
#    extract_statement_transactions() on it.
# ------------------------------------------------------------------


from pathlib import Path
import re
import pandas as pd

from pdf2image import convert_from_path
from PIL import Image
import pytesseract


def pdf_to_image(pdf_path: str) -> Image.Image:
    """
    Step 1a: turn the PDF's first page into an image.

    WHY: a PDF is not directly usable text — it's a set of drawing
    instructions. Tesseract (our OCR engine) can only "look at"
    pixels, so we must first render the PDF page as an image.
    """
    pages = convert_from_path(pdf_path, dpi=200)
    return pages[0]  # our invoices are always a single page

def load_image(image_path: str) -> Image.Image:
    """
    Load an already-image file (PNG/JPG) directly, for uploads that
    are a photo of an invoice rather than a PDF.

    WHY this is separate from pdf_to_image(): a PDF needs to be
    RENDERED into an image first (pdf_to_image does that). A file
    that's already a PNG/JPG is already an image -- there's nothing
    to render, we just open it. Keeping the two functions separate
    means the rest of the pipeline (image_to_raw_text, get_ocr_data,
    etc.) doesn't need to know or care which path the image came
    from -- both functions hand it the same kind of Image object.
    """
    return Image.open(image_path)

def image_to_raw_text(image: Image.Image) -> str:
    """
    Step 1b: run Tesseract on the image to get raw text.

    WHY: this is the actual "Optical Character Recognition" —
    Tesseract scans the image, predicts which letters are drawn,
    and reconstructs a text string.
    """
    return pytesseract.image_to_string(image)


def run_step1(pdf_path: str) -> str:
    """Glue function: PDF path in, raw OCR text out."""
    image = pdf_to_image(pdf_path)
    return image_to_raw_text(image)


def extract_invoice_number(raw_text: str) -> str:
    r"""
    Find the invoice number, e.g. "SINV_checking_main_TX00005".

    Pattern explained:
      "Invoice No\.?:?"  -> matches "Invoice No" then an optional
                            "." and an optional ":" (Tesseract
                            sometimes drops punctuation, so both
                            are marked optional with "?")
      \s*                -> any spaces after the colon
      ([A-Za-z0-9_\-]+)  -> the actual value we want: letters,
                            digits, underscores or dashes, captured
                            in parentheses so we can pull out just
                            that part with .group(1)
    """
    match = re.search(r"Invoice No\.?:?\s*([A-Za-z0-9_\-]+)", raw_text)
    return match.group(1) if match else ""


def extract_invoice_date(raw_text: str) -> str:
    r"""
    Find the invoice date, e.g. "2022-08-30".

    Pattern explained:
      "(?:Invoice date|Issue date):?"
                           -> matches EITHER "Invoice date" OR
                              "Issue date", followed by an optional
                              ":". Supplier invoices use "Invoice
                              date"; customer invoices use "Issue
                              date" instead — the "(?:...|...)"
                              syntax means "match one of these
                              options, but don't capture it as a
                              separate group" (we only want to
                              capture the date itself, in the next
                              part).
      \s*                  -> any spaces after the label
      (\d{4}-\d{2}-\d{2})  -> the date itself, same shape as before
    """
    match = re.search(
        r"(?:Invoice date|Issue date):?\s*(\d{4}-\d{2}-\d{2})", raw_text
    )
    return match.group(1) if match else ""


def extract_due_date(raw_text: str) -> str:
    """
    Find the due date, e.g. "2022-09-06".

    Pattern explained: identical logic to extract_invoice_date
    above, just anchored to the "Due date:" label instead of
    "Invoice date:" — both dates use the same YYYY-MM-DD shape.
    """
    match = re.search(r"Due date:?\s*(\d{4}-\d{2}-\d{2})", raw_text)
    return match.group(1) if match else ""


def extract_total_due(raw_text: str) -> str:
    r"""
    Find the total amount due, e.g. "416.00".

    Pattern explained:
      "Total due:?"       -> matches the label, ":" optional
      \s*EUR\s*           -> the currency code "EUR", with optional
                             spaces before and after it
      ([\d,]+\.\d{2})     -> the amount: one or more digits or
                             commas (to allow thousands separators
                             like "1,234"), then a literal dot,
                             then exactly 2 digits for the cents.
                             Captured so we get "416.00", not the
                             whole "EUR 416.00" string.
    """
    match = re.search(r"Total due:?\s*EUR\s*([\d,]+\.\d{2})", raw_text)
    return match.group(1) if match else ""


def extract_status(raw_text: str) -> str:
    r"""
    Find the payment status, e.g. "paid".

    Pattern explained:
      "Status:?"            -> matches the label, ":" optional
      \s*                   -> spaces after the label
      ([A-Za-z\s\(\)]+?)    -> the status text itself: letters,
                              spaces, and parentheses (to also
                              catch something like "Paid (on
                              time)"). The "+?" means "as few
                              characters as possible" — this stops
                              the match early instead of grabbing
                              everything up to the end of the text.
      \s*\|                 -> stops right before the "|" separator
                              that comes after the status on the
                              same line (see "Status: paid | Paid
                              on: ...")
    """
    match = re.search(r"Status:?\s*([A-Za-z\s\(\)]+?)\s*\|", raw_text)
    return match.group(1).strip() if match else ""


def extract_paid_on(raw_text: str) -> str:
    """
    Find the date the invoice was actually paid, e.g. "2022-08-31".

    Pattern explained: same YYYY-MM-DD date shape as the other two
    date functions, just anchored to the "Paid on:" label.
    """
    match = re.search(r"Paid on:?\s*(\d{4}-\d{2}-\d{2})", raw_text)
    return match.group(1) if match else ""


KNOWN_CATEGORIES = [
    "Operating Expense", "COGS", "Supplies", "Marketing", "Utilities", "Other",
]


def find_table_line(raw_text: str) -> str:
    r"""
    Find the single line in the OCR text that holds the invoice's
    line item: counterparty/description, optional category, and
    three amounts (net, VAT, total).

    WHY this is trickier than the other fields: unlike "Invoice
    No.:" or "Total due:", this line has no fixed label in front of
    it — we can only recognise it by its SHAPE (it's the line that
    contains money amounts).

    Two real OCR quirks we found by testing on your actual invoices:
    1. The third amount (the total) sometimes gets pushed onto a
       separate line instead of staying on the same line.
    2. Tesseract can also insert a BLANK line in between, so the
       amount isn't even on the very next line — it's one or two
       lines further down. We handle both by skipping blank lines
       while looking ahead, instead of only checking a single fixed
       next line.
    """
    lines = raw_text.splitlines()

    for i, line in enumerate(lines):
        amounts = re.findall(r"[\d,]+\.\d{2}", line)

        if len(amounts) >= 2:
            # Look ahead for the missing 3rd amount, skipping any
            # blank lines Tesseract may have inserted. We only look
            # up to 3 lines ahead -- enough to survive a stray blank
            # line, but not so far that we'd accidentally grab a
            # number from an unrelated line further down (like
            # "Total due: EUR ...").
            lookahead = 1
            while len(amounts) < 3 and i + lookahead < len(lines) and lookahead <= 3:
                next_line = lines[i + lookahead].strip()

                if next_line == "":
                    # Blank line: skip it and keep looking.
                    lookahead += 1
                    continue

                if re.fullmatch(r"[\d,]+\.\d{2}", next_line):
                    # Found the missing amount on its own line.
                    line = line + " " + next_line
                    amounts.append(next_line)

                # Whether we matched or not, a non-blank line means
                # we stop looking further -- if it wasn't a lone
                # number, it's unrelated text (e.g. "Total due:...").
                break

            return line

    return ""


def extract_line_item(raw_text: str) -> dict:
    """
    Parse the table line found by find_table_line() into its parts:
    counterparty name, category (if present), net amount, VAT
    amount, and total amount.

    Supplier invoices have a category column (e.g. "Operating
    Expense"); customer invoices don't. We detect the category by
    checking against a known list, rather than assuming it's always
    there -- this is what lets the SAME function handle both
    invoice types without needing two separate parsers.
    """
    line = find_table_line(raw_text)

    if not line:
        return {
            "counterparty": "", "category": "",
            "net_amount": "", "vat_amount": "", "total_amount": "",
        }

    amounts = re.findall(r"[\d,]+\.\d{2}", line)

    # Guard: if we somehow still don't have 3 amounts, don't guess.
    if len(amounts) < 3:
        net, vat, total = "", "", ""
    else:
        net, vat, total = amounts[-3], amounts[-2], amounts[-1]

    # Remove the amounts from the line, so whatever text is left is
    # the counterparty name (and possibly the category).
    remainder = line
    for amount in amounts:
        remainder = remainder.replace(amount, "")

        # Search case-insensitively (Tesseract can misread letter case,
    # e.g. "COGS" -> "coGs"), but keep the RAW text exactly as OCR
    # produced it, not the canonical spelling from KNOWN_CATEGORIES.
    # WHY this matters: if we returned the canonical "COGS" here, a
    # later CER/WER comparison against ground truth would score 0%
    # error even when Tesseract actually misread the category --
    # hiding the very mistake we're trying to measure. Case-
    # insensitive DETECTION and preserving the RAW OCR text are two
    # separate concerns, both handled here on purpose.
    found_category = ""
    for category in KNOWN_CATEGORIES:
        match = re.search(re.escape(category), remainder, re.IGNORECASE)
        if match:
            found_category = match.group()
            remainder = remainder.replace(found_category, "")
            break

    counterparty = remainder.strip()

    return {
        "counterparty": counterparty,
        "category": found_category,
        "net_amount": net,
        "vat_amount": vat,
        "total_amount": total,
    }


def get_ocr_data(image: Image.Image) -> dict:
    """
    Step 3a of confidence scoring: run Tesseract in "data" mode
    instead of "string" mode.

    WHY this is different from image_to_string(): that function
    only gives us the final text, with no idea of how sure Tesseract
    was about each word. image_to_data() gives us a dictionary where
    each detected word has its OWN confidence score (0-100), plus
    its position on the page. We only need the "text" and "conf"
    lists here, but the function also returns position data
    (left/top/width/height) that could be used later if we ever
    need to highlight fields on the image itself.

    A confidence of -1 means "this isn't a real recognized word"
    (e.g. Tesseract detected an empty region) — we filter those out
    wherever we use this data.
    """
    return pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)


def confidence_for_value(ocr_data: dict, value: str) -> float:
    """
    Step 3b: turn an extracted value (e.g. "490.88" or an invoice
    number) into a single confidence score, by averaging the
    confidence of the individual words that make it up.

    WHY we do it this way: our extracted fields (from extract_total_due,
    extract_invoice_number, etc.) are plain strings — they don't carry
    any confidence information themselves, because they came from
    regex matches on the ALREADY-ASSEMBLED text, not from Tesseract
    directly. To reconnect a value to its confidence, we split the
    value into words, then look up each of those words in the raw
    OCR data returned by get_ocr_data().

    Example: if value is "Nordbohnen Roastery", we look for a word
    "Nordbohnen" and a word "Roastery" in ocr_data, note each one's
    confidence, and average the two.
    """
    if not value:
        return 0.0

    # Split the value into individual words, stripping common
    # punctuation Tesseract sometimes attaches to a word (like a
    # trailing "." or ":"), so "Roastery." still matches "Roastery".
    target_words = {w.strip(".,:()") for w in value.split() if w.strip()}
    matched_confidences = []

    for i, word in enumerate(ocr_data["text"]):
        cleaned_word = word.strip(".,:()")
        if cleaned_word and cleaned_word in target_words:
            conf = float(ocr_data["conf"][i])
            if conf >= 0:  # -1 means "not a real recognized word"
                matched_confidences.append(conf)

    if matched_confidences:
        return round(sum(matched_confidences) / len(matched_confidences), 1)

    # No matching words found at all -- honest "we don't know",
    # never a made-up high number.
    return 0.0

# Which fields count toward the overall confidence. We deliberately
# do NOT average every single field: Counterparty and Category are
# useful context, but a slightly garbled supplier name shouldn't by
# itself block a document that has a perfectly readable invoice
# number, dates and amount. These four are the fields a human would
# actually need to trust before this invoice enters the accounting
# pipeline.
REQUIRED_FOR_CONFIDENCE = [
    "Invoice number", "Invoice date", "Due date", "Total due",
]


def compute_overall_confidence(fields: dict, ocr_data: dict) -> float:
    """
    Turn several per-field confidence scores into ONE overall score
    for the whole document, based only on the fields that actually
    matter for trusting this invoice (see REQUIRED_FOR_CONFIDENCE
    above).

    WHY not average ALL fields: some fields (like Counterparty) are
    nice-to-have context, not something we'd reject a whole invoice
    over if it's slightly misread. Mixing them into the average
    would let a bad Counterparty reading drag down an otherwise
    perfectly trustworthy invoice, or the reverse.
    """
    scores = [
        confidence_for_value(ocr_data, fields[label])
        for label in REQUIRED_FOR_CONFIDENCE
        if label in fields
    ]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 1)


def determine_review_status(overall_confidence: float) -> str:
    """
    Turn one overall confidence score into a human-readable status.

    These thresholds (85 / 60) aren't a universal law -- they're a
    judgment call we're making explicit and documenting, so it can
    be questioned and adjusted later if real-world testing shows
    they're too strict or too lenient:
      - >= 85%: Validated       -> safe to accept automatically
      - 60-84%: Needs review    -> a human should double-check
      - < 60%:  Rejected        -> too unreliable to use as-is
    """
    if overall_confidence >= 85:
        return "Validated"
    elif overall_confidence >= 60:
        return "Needs review"
    else:
        return "Rejected"

import jiwer


def compute_cer(ground_truth: str, prediction: str) -> float:
    """
    Character Error Rate: how many individual characters differ
    between the true value and what Tesseract actually read,
    relative to the length of the true value.

    WHY it matters: this is a forgiving metric. A single wrong
    letter in a long word barely moves the CER. It's useful for
    seeing "how close" the OCR got, even when it didn't get an
    exact match.

    Note: comparison is case-sensitive. "COGS" vs "coGs" scores
    75% CER (3 of 4 characters differ), not 0%, even though a
    human reading it would immediately understand it's the same
    word.
    """
    return jiwer.cer(ground_truth, prediction)


def compute_wer(ground_truth: str, prediction: str) -> float:
    """
    Word Error Rate: same idea as CER, but counted in whole words
    instead of characters.

    WHY it matters: this is a strict metric. Getting 9 letters out
    of 10 right in a word still counts as a FULL miss at the word
    level. WER answers a different question than CER: not "how
    close was it letter by letter" but "how many whole values can
    we actually trust as correct".
    """
    return jiwer.wer(ground_truth, prediction)

import io


def build_excel_download(fields: dict) -> bytes:
    """
    Turn the extracted fields into an Excel file, entirely in
    memory (no file written to disk on the server).

    WHY use io.BytesIO: normally pandas' to_excel() writes to a
    real file path. BytesIO acts like a fake file that lives in
    RAM instead -- Streamlit's download_button() needs raw bytes to
    hand to the browser, not a file path on our server (which the
    user's browser has no access to anyway).
    """
    dataframe = pd.DataFrame(list(fields.items()), columns=["Field", "Value"])
    buffer = io.BytesIO()
    dataframe.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def build_image_download(image: Image.Image) -> bytes:
    """
    Turn the PIL Image (the one Tesseract actually read) into PNG
    bytes, so the user can download exactly what the OCR engine saw
    -- useful for double-checking a low-confidence result by eye.
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def read_pdf_bytes(pdf_path: str) -> bytes:
    """
    Read the original invoice PDF as raw bytes, so the user can
    download the source document alongside the extracted data.
    """
    with open(pdf_path, "rb") as file:
        return file.read()

# ------------------------------------------------------------------
# BANK / CARD STATEMENT PARSER
# ------------------------------------------------------------------
# A separate document type from invoices: a statement has MANY
# transactions per document instead of one total, so it needs its
# own detection + extraction logic rather than reusing the
# single-invoice field extractors above.


def is_bank_statement(raw_text: str) -> bool:
    """
    Detect whether an uploaded document is a bank/card statement
    rather than an invoice, based on the wording Treasoria's own
    generated statements always contain.

    WHY this matters: running the invoice field extractors on a
    statement produces a misleading result (e.g. picking a random
    transaction line as "Counterparty") instead of an honest
    "this isn't an invoice" signal.
    """
    return "Account statement" in raw_text and "Statement period" in raw_text


def pdf_to_images(pdf_path: str) -> list[Image.Image]:
    """
    Convert EVERY page of a PDF into images, not just the first.

    WHY this exists separately from pdf_to_image(): invoices in this
    project are always a single page, so pdf_to_image() intentionally
    only reads page 1 -- fast and sufficient. But bank/card
    statements can span multiple pages once a month has enough
    transactions (confirmed on checking_main_2023-07.pdf: 2 pages).
    Reading only page 1 for a statement silently drops every
    transaction after the page break.
    """
    return convert_from_path(pdf_path, dpi=200)


def images_to_raw_text(images: list[Image.Image]) -> str:
    """
    Run OCR on every page and join the results into one continuous
    text blob, so extract_statement_transactions() can find
    transactions regardless of which page they landed on.
    """
    return "\n\n".join(pytesseract.image_to_string(img) for img in images)



def extract_statement_metadata(raw_text: str) -> dict:
    """
    Extract the header info of a bank/card statement: account type
    (e.g. "Checking Account - Main" or "Business Credit Card"),
    statement period, and either an IBAN (bank account) or the
    last digits of a card (credit card) -- whichever is present.
    """
    account_type_match = re.search(r"Account statement\s*-\s*(.+)", raw_text)
    account_type = (
        account_type_match.group(1).split("\n")[0].strip()
        if account_type_match else ""
    )

    period_match = re.search(r"Statement period:?\s*(\d{4}-\d{2})", raw_text)
    period = period_match.group(1) if period_match else ""

    iban_match = re.search(r"IBAN\s+([A-Z0-9\s]+?)\s*\|", raw_text)
    iban = iban_match.group(1).strip() if iban_match else ""

    card_match = re.search(r"Card ending\s+(\d+)", raw_text)
    card_last4 = card_match.group(1) if card_match else ""

    return {
        "account_type": account_type,
        "period": period,
        "iban": iban,
        "card_last4": card_last4,
    }


def extract_statement_transactions(raw_text: str) -> pd.DataFrame:
    r"""
    Extract every transaction line from a bank/card statement into
    a DataFrame: date, description, type (Credit/Debit), amount,
    running balance.

    WHY a single whole-text regex instead of splitting into lines
    first: real OCR output sometimes glues one transaction's ending
    balance directly onto the next transaction's date, with NO
    space or line break between them -- e.g.
        "...142098.322023-07-23 Daily Sales Deposit Credit ..."
    Splitting by line first would treat that as one broken line and
    silently lose the second transaction. Scanning the raw text as
    one continuous string with re.finditer finds every date
    correctly, glued or not, because the date pattern doesn't
    require a space or line break before it -- it just needs the
    four-digit/dash/two-digit/dash/two-digit shape to appear
    somewhere in the string.

    Pattern explained:
      (\d{4}-\d{2}-\d{2})   -> the transaction date
      \s+(.+?)\s+           -> the description, captured
                               non-greedily so it stops at the
                               first following Credit/Debit
                               keyword instead of swallowing the
                               rest of the statement
      (Credit|Debit)         -> the transaction type
      \s+([\d,]+\.\d{2})     -> the amount
      \s+([\d,]+\.\d{2})     -> the running balance
    """
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2})\s+(.+?)\s+(Credit|Debit)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})"
    )

    rows = []
    for match in pattern.finditer(raw_text):
        date, description, txn_type, amount, balance = match.groups()
        rows.append({
            "date": date,
            "description": description.strip(),
            "type": txn_type,
            "amount": amount,
            "balance": balance,
        })

    return pd.DataFrame(rows)


def build_excel_download_from_df(dataframe: pd.DataFrame) -> bytes:
    """
    Same purpose as build_excel_download(), but for a full
    transactions table instead of a single dict of invoice fields
    -- used for statement downloads.
    """
    buffer = io.BytesIO()
    dataframe.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


if __name__ == "__main__":
    sample_invoice = (
    "data/Treasoria_Datasets_Code_and_Coffee/docs/invoices_pdf/"
    "supplier_invoice_0050.pdf"
)

    if not Path(sample_invoice).exists():
        print(f"File not found: {sample_invoice}")
    else:
        image = pdf_to_image(sample_invoice)
        text = image_to_raw_text(image)
        ocr_data = get_ocr_data(image)  # NEW: word-level data for confidence

        print("=" * 60)
        print("RAW TEXT EXTRACTED FROM THE INVOICE:")
        print("=" * 60)
        print(text)

        fields = {
            "Invoice number": extract_invoice_number(text),
            "Invoice date": extract_invoice_date(text),
            "Due date": extract_due_date(text),
            "Total due": extract_total_due(text),
            "Status": extract_status(text),
            "Paid on": extract_paid_on(text),
        }

        line_item = extract_line_item(text)
        fields["Counterparty"] = line_item["counterparty"]
        fields["Category"] = line_item["category"]
        fields["Net amount"] = line_item["net_amount"]
        fields["VAT amount"] = line_item["vat_amount"]
        fields["Total amount"] = line_item["total_amount"]

        print("=" * 60)
        print("EXTRACTED FIELDS WITH CONFIDENCE:")
        print("=" * 60)
        for label, value in fields.items():
                    print("=" * 60)
        print("EXTRACTED FIELDS WITH CONFIDENCE:")
        print("=" * 60)
        for label, value in fields.items():
            confidence = confidence_for_value(ocr_data, value)
            print(f"{label:20s}: {value!r:30s}  confidence={confidence}%")

        overall = compute_overall_confidence(fields, ocr_data)
        status = determine_review_status(overall)

        print("=" * 60)
        print("OVERALL DOCUMENT STATUS:")
        print("=" * 60)
        print(f"Overall confidence (based on {REQUIRED_FOR_CONFIDENCE}): {overall}%")
        print(f"Status: {status}")
        
        print("=" * 60)
        print("CER / WER ON THE CATEGORY FIELD:")
        print("=" * 60)
        ground_truth_category = "COGS"  # what we KNOW is really on the invoice
        ocr_category = line_item["category"]  # what Tesseract actually read

        cer = compute_cer(ground_truth_category, ocr_category)
        wer = compute_wer(ground_truth_category, ocr_category)

        print(f"Ground truth: {ground_truth_category!r}")
        print(f"OCR reading:  {ocr_category!r}")
        print(f"CER: {cer:.1%}")
        print(f"WER: {wer:.1%}")