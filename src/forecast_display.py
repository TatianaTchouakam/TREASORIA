"""
Treasoria — Forecast display helpers for Streamlit

Reads Aysenur's evaluated forecast output (monthly or daily track)
and prepares it for display, respecting the interpretation limits
documented in src/forecast/HANDOFF.md:

- The uncertainty band is an exploratory backtest-error envelope,
  NOT a calibrated probability interval (uncertainty_is_calibrated
  is always False in this output).
- Test metrics are retrospective holdout results, not a blind
  final test.
- The forecast horizon (Jan-Mar 2024) is a HISTORICAL demo period
  relative to the synthetic dataset's 2022-2023 timeline -- not a
  live forecast for the actual current date. The UI must never
  imply this is "today's" forecast.
"""

from pathlib import Path

import pandas as pd


def load_forecast(dataset_dir: Path, frequency: str = "daily") -> pd.DataFrame:
    """
    Load the evaluated forecast output for one track.

    frequency: "daily" or "monthly" -- HANDOFF.md is explicit that
    the two should not be mixed in one analysis (they don't
    necessarily reconcile against each other), so the caller must
    pick one, not both at once.
    """

    file_path = Path("results") / "forecast" / frequency / "forecast_output.csv"
    forecast = pd.read_csv(file_path)
    forecast["date"] = pd.to_datetime(forecast["date"])
    forecast["period_end"] = pd.to_datetime(forecast["period_end"])

    return forecast


def load_leaderboard(frequency: str = "daily") -> pd.DataFrame:
    """
    Load the model comparison leaderboard for one track -- shows
    every candidate model that was evaluated, including ones that
    were not selected, for an honest "model comparison" view.
    """

    file_path = Path("results") / "forecast" / frequency / "leaderboard.csv"
    return pd.read_csv(file_path)


def get_forecast_summary(forecast: pd.DataFrame) -> dict:
    """
    Extract the handful of headline facts a Streamlit page needs,
    without repeating the raw column-parsing logic on every page.
    """

    first_row = forecast.iloc[0]

    return {
        "model": first_row["model"],
        "as_of_date": first_row["as_of_date"],
        "starting_balance": float(first_row["starting_cash_balance"]),
        "frequency": first_row["frequency"],
        "horizon_periods": len(forecast),
        "final_projected_balance": float(forecast.iloc[-1]["projected_cash_balance"]),
    }