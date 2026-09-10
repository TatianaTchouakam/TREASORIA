"""Small, tested examples for connecting Forecast to Risk and What-if.

These functions demonstrate the output contract. They are not the full simulator.
"""

import numpy as np
import pandas as pd
from .forecast_pipeline import forecast_to_cash_balance


def _check_forecast(forecast):
    if forecast.empty:
        raise ValueError("Forecast must not be empty.")
    required = {"date", "period_end", "forecasted_net_cash_flow", "projected_cash_balance",
                "starting_cash_balance", "frequency", "scenario_id", "company_id"}
    if not required.issubset(forecast.columns):
        raise ValueError(f"Missing forecast columns: {required - set(forecast.columns)}")
    if forecast.frequency.nunique() != 1 or forecast.company_id.nunique() != 1 or forecast.scenario_id.nunique() != 1:
        raise ValueError("Pass exactly one frequency, company and scenario.")
    frequency = forecast.frequency.iloc[0]
    if frequency not in {"MS", "D"}:
        raise ValueError("Unknown forecast frequency.")
    dates = pd.DatetimeIndex(pd.to_datetime(forecast.date))
    if not dates.equals(pd.date_range(dates[0], periods=len(dates), freq=frequency)):
        raise ValueError("Forecast dates must be ordered, unique and consecutive.")
    numeric = forecast[["forecasted_net_cash_flow", "projected_cash_balance", "starting_cash_balance"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or forecast.starting_cash_balance.nunique() != 1:
        raise ValueError("Cash values must be finite with one starting balance.")
    expected = forecast_to_cash_balance(forecast.forecasted_net_cash_flow, forecast.starting_cash_balance.iloc[0])
    if not np.allclose(expected, forecast.projected_cash_balance, atol=0.01, rtol=0):
        raise ValueError("Forecast cash balances do not reconcile.")


def apply_cash_flow_adjustments(baseline, adjustments, scenario_id):
    """Adjust dated NET flows in EUR; leave the baseline unchanged.

    Positive adjustment = more cash received / less cash paid.
    Negative adjustment = less cash received / more cash paid.
    For a delayed receipt, subtract it at the old date and add it at the new date.
    The caller must extend the horizon if the new date lies outside it.
    """
    _check_forecast(baseline)
    if not isinstance(scenario_id, str) or not scenario_id.strip() or scenario_id == "baseline":
        raise ValueError("Give the new scenario a non-empty name other than baseline.")
    if baseline.scenario_id.iloc[0] != "baseline":
        raise ValueError("Always apply adjustments to the immutable baseline scenario.")
    dates = pd.to_datetime(adjustments["date"], errors="raise")
    values = pd.to_numeric(adjustments["net_flow_delta_eur"], errors="raise")
    if dates.isna().any() or not np.isfinite(values).all():
        raise ValueError("Scenario adjustments need valid dates and finite EUR amounts.")
    scenario = baseline.copy(deep=True)
    scenario["date"] = pd.to_datetime(scenario.date)
    if not dates.isin(scenario.date).all():
        raise ValueError("An adjustment falls outside the forecast grid. Extend the forecast explicitly.")
    deltas = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(dates)).groupby(level=0).sum()
    scenario["net_flow_delta_eur"] = scenario.date.map(deltas).fillna(0.0)
    scenario["forecasted_net_cash_flow"] += scenario.net_flow_delta_eur
    cumulative_delta = scenario.net_flow_delta_eur.cumsum()
    scenario["projected_cash_balance"] = forecast_to_cash_balance(scenario.forecasted_net_cash_flow, scenario.starting_cash_balance.iloc[0])
    # This shift conditions on fixed scenario inputs; it adds no uncertainty for those inputs.
    for column in ["net_flow_lower", "net_flow_upper"]:
        if column in scenario:
            scenario[column] += scenario.net_flow_delta_eur
    for column in ["cash_balance_lower", "cash_balance_upper"]:
        if column in scenario:
            scenario[column] += cumulative_delta
    scenario["scenario_id"] = scenario_id
    scenario["scenario_uncertainty_note"] = "Baseline error envelope shifted by fixed deltas; scenario-input uncertainty excluded."
    return scenario


def summarize_cash_risk(forecast, threshold):
    """Summarize point forecasts at their actual frequency; threshold is user supplied."""
    _check_forecast(forecast)
    if not np.isfinite(threshold):
        raise ValueError("Supply a finite EUR threshold.")
    balance = forecast.projected_cash_balance
    lowest = balance.idxmin()
    result = {"scenario_id": forecast.scenario_id.iloc[0], "threshold_eur": float(threshold),
              "final_balance": float(balance.iloc[-1]), "minimum_projected_balance": float(balance.min()),
              "low_point_period_end": str(pd.Timestamp(forecast.loc[lowest, "period_end"]).date()),
              "periods_below_threshold": int((balance < threshold).sum()),
              "days_below_threshold": int((balance < threshold).sum()) if forecast.frequency.iloc[0] == "D" else None}
    # The first value is a future closing balance. Include opening cash separately if needed.
    result["starting_cash_balance"] = float(forecast.starting_cash_balance.iloc[0])
    return result
