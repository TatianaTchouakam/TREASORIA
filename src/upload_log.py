"""
Treasoria — Upload activity log

Keeps a small, persistent record of documents processed through the
Invoices page (invoices, bank statements, and spreadsheet imports),
so a returning user can see what's happened recently without
re-uploading anything.

This log lives on disk (data/_upload_log.csv), NOT in Git -- it's
local activity history for whoever is running the app, not project
data to share. See .gitignore.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd


LOG_COLUMNS = ["timestamp", "file_name", "document_type", "result"]


def log_upload(
    log_path: Path, file_name: str, document_type: str, result: str
) -> None:
    """
    Append one row to the upload log, creating the file if it
    doesn't exist yet.
    """

    new_row = pd.DataFrame(
        [
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "file_name": file_name,
                "document_type": document_type,
                "result": result,
            }
        ]
    )

    if log_path.exists():
        existing = pd.read_csv(log_path)
        combined = pd.concat([existing, new_row], ignore_index=True)
    else:
        combined = new_row

    log_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(log_path, index=False)


def load_recent_uploads(log_path: Path, n: int = 15) -> pd.DataFrame:
    """
    Load the n most recent uploads, most recent first.

    Returns an empty (but correctly-shaped) table if nothing has
    been logged yet, rather than raising an error -- a brand new
    installation with no upload history yet is a normal state, not
    a failure.
    """

    if not log_path.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)

    log = pd.read_csv(log_path)
    return log.tail(n).iloc[::-1].reset_index(drop=True)