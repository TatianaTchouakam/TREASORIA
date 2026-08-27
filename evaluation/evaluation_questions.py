# ============================================================
# TREASORIA RAG EVALUATION QUESTIONS
# ============================================================

# These questions evaluate the African Kaffeehaus demo dataset.
#
# They are deliberately written in natural, sometimes informal,
# language to test whether HyDE helps bridge the vocabulary gap
# between user questions and Treasoria's financial documents.

EVALUATION_DATA: list[dict[str, str]] = [
    {
        # Tests retrieval of validation rules and accounting
        # treatments from the Treasoria documentation.
        "question": (
            "How did Treasoria make sure the money numbers "
            "for African Kaffeehaus were trustworthy?"
        ),
        "ground_truth": (
            "Treasoria validated the African Kaffeehaus dataset "
            "by checking that opening consolidated cash plus "
            "cumulative external net cash flow equals closing "
            "consolidated cash. The expected figures are EUR "
            "17,000.00 opening cash, EUR 392,052.90 cumulative "
            "net cash flow and EUR 409,052.90 closing cash. "
            "Internal transfers were eliminated from consolidated "
            "cash flow, credit-card repayments were retained as "
            "external cash outflows, and employer contributions "
            "were treated as analytical costs without creating "
            "corresponding bank payments."
        ),
    },
    {
        # Tests retrieval of several Gold KPIs using a broad
        # business question rather than exact KPI terminology.
        "question": (
            "Is African Kaffeehaus in a positive financial "
            "position, and which figures support the conclusion?"
        ),
        "ground_truth": (
            "African Kaffeehaus has a positive cash-flow position. "
            "Its closing consolidated cash is EUR 409,052.90, "
            "its cumulative net cash flow is EUR 392,052.90 and "
            "its average monthly net cash flow is EUR 16,335.54. "
            "The Gold KPI summary describes its cash runway as "
            "infinite because cash flow is positive. Revenue "
            "collected over 24 months is EUR 612,939.90. The "
            "closing credit-card debt is EUR 21,651.00."
        ),
    },
    {
        # Tests whether the retriever can identify financial
        # warning signals even when the query does not name
        # the exact KPIs.
        "question": (
            "What should the owner of African Kaffeehaus monitor "
            "even though the café is generating positive cash flow?"
        ),
        "ground_truth": (
            "The owner should monitor customer payment behaviour "
            "and outstanding liabilities. The average B2B customer "
            "collection time is 36.3 days, 33.3 percent of customer "
            "invoices were paid late, and open customer receivables "
            "are EUR 1,153.95. The closing credit-card debt is EUR "
            "21,651.00. These indicators should be monitored even "
            "though the business has positive cumulative and "
            "average monthly net cash flow."
        ),
    },
]