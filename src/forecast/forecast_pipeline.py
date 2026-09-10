"""Run with: python -m src.forecast.forecast_pipeline --frequency both

Other modules can import run_forecast_pipeline(). No notebook imports are needed.
Gold inputs are read-only. Outputs live in results/forecast and data/processed/forecast.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .data_utils import (GOLD_RELATIVE, TARGET, daily_net_flow, find_project_root,
                         future_index, load_daily, load_monthly, reconcile_cash)
from .models import candidate_models, predict_model
from .model_evaluation import evaluate_protocol

PIPELINE_VERSION = "1.0.0"


def forecast_to_cash_balance(forecast_values, last_known_balance):
    values = np.asarray(forecast_values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or not np.isfinite(last_known_balance):
        raise ValueError("Cash calculations need finite, one-dimensional inputs.")
    return float(last_known_balance) + np.cumsum(values)


def build_forecast(frame, spec, frequency, horizon, last_balance, as_of, bands):
    """Refit on ALL observed rows only after the validation choice is frozen."""
    validated_horizon = int(bands.horizon_step.max())
    if horizon > validated_horizon:
        raise ValueError(f"Only horizons up to {validated_horizon} are evaluated. Extend validation first.")
    dates = future_index(frame.index[-1], horizon, frequency)
    prediction = predict_model(spec, frame, horizon, frequency)
    future = pd.DataFrame({
        "date": dates,
        "period_end": dates + pd.offsets.MonthEnd(0) if frequency == "MS" else dates,
        "company_id": frame.company_id.iloc[0], "currency": "EUR", "frequency": frequency,
        "scenario_id": "baseline", "model": spec.name, "as_of_date": pd.Timestamp(as_of),
        "horizon_step": np.arange(1, horizon + 1),
        "forecasted_net_cash_flow": prediction,
        "starting_cash_balance": float(last_balance),
        "projected_cash_balance": forecast_to_cash_balance(prediction, last_balance),
    })
    selected_bands = bands.set_index("horizon_step").loc[np.arange(1, horizon + 1)]
    future["net_flow_lower"] = prediction - selected_bands.flow_radius.to_numpy()
    future["net_flow_upper"] = prediction + selected_bands.flow_radius.to_numpy()
    future["cash_balance_lower"] = future.projected_cash_balance - selected_bands.balance_radius.to_numpy()
    future["cash_balance_upper"] = future.projected_cash_balance + selected_bands.balance_radius.to_numpy()
    future["uncertainty_method"] = "absolute_backtest_error_envelope_exploratory"
    future["nominal_level"] = selected_bands.nominal_level.to_numpy()
    future["calibration_paths"] = selected_bands.calibration_paths.to_numpy()
    # This is an explicit warning field for the next module, not a hidden assumption.
    future["uncertainty_is_calibrated"] = False
    return future


def run_forecast_pipeline(horizon=None, frequency="MS", project_root=None, opening_balance=None,
                          output_dir=None, save=True):
    """Return forecast, evaluation, reconciliation and metadata as a dictionary.

    opening_balance means cash before the FIRST historical day. It is optional;
    the actual forecast anchor is always read from the LAST daily Gold row.
    For the documented Code & Coffee demo, opening cash was EUR 17,000.
    Do not use that number for another dataset.
    """
    if frequency not in {"MS", "D"}:
        raise ValueError("frequency must be MS or D.")
    horizon = (3 if frequency == "MS" else 90) if horizon is None else horizon
    if not isinstance(horizon, int) or isinstance(horizon, bool) or not 1 <= horizon <= (3 if frequency == "MS" else 90):
        raise ValueError("Use an integer horizon from 1 to 3 months or 1 to 90 days.")
    root = find_project_root(project_root)
    monthly, daily = load_monthly(root), load_daily(root)
    reconciliation = reconcile_cash(monthly, daily, opening_balance)
    frame = monthly if frequency == "MS" else daily_net_flow(daily, opening_balance)
    evaluation = evaluate_protocol(frame, frequency)
    forecast = build_forecast(frame, evaluation["spec"], frequency, horizon,
                              daily.consolidated_cash_balance.iloc[-1], daily.index[-1], evaluation["bands"])
    versions = {}
    for package in ["numpy", "pandas", "prophet", "statsmodels"]:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    source_hashes = {name: hashlib.sha256((root / GOLD_RELATIVE / name).read_bytes()).hexdigest()
                     for name in ["gold_monthly_cash_flow.csv", "gold_daily_cash_position.csv"]}
    code_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
    metadata = {
        "pipeline_version": PIPELINE_VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_files_sha256": source_hashes, "code_files_sha256": code_hashes, "package_versions": versions,
        "frequency": frequency, "horizon": horizon, "as_of_date": str(daily.index[-1].date()),
        "source_period_start": str(frame.index[0].date()), "history_n": len(frame),
        "opening_balance_for_first_day": opening_balance,
        "starting_cash_balance": float(daily.consolidated_cash_balance.iloc[-1]),
        "selected_model": evaluation["selected_model"], "selected_parameters": evaluation["spec"].to_dict(),
        "all_candidate_parameters": [s.to_dict() for s in candidate_models(frequency)],
        "selection_rule": evaluation["selection_reason"],
        "development_n": len(evaluation["development"]), "test_n": len(evaluation["test"]),
        "test_start": str(evaluation["test"].index[0].date()), "test_end": str(evaluation["test"].index[-1].date()),
        "uncertainty": "80% empirical absolute-error envelope from 3 validation paths; not calibrated; not a simultaneous interval.",
        "limitations": [
            "Synthetic demonstration data ending in 2023; this is not a current 2026 forecast.",
            "Only two years of calendar history, even for the daily data.",
            "The final quarter had already been inspected in earlier notebooks; holdout scores are retrospective.",
            "Daily and monthly forecasts are separate experiments. Do not add them or expect future sums to agree.",
            "Monthly outputs cannot identify days below a cash threshold.",
            "Net flow alone does not identify sales, gross costs, customer concentration or invoice delays.",
            "Three validation paths are too few for reliable probability calibration or rare-shock prediction.",
        ],
    }
    result = {"forecast": forecast, "evaluation": evaluation, "reconciliation": reconciliation, "metadata": metadata}
    if save:
        label = "monthly" if frequency == "MS" else "daily"
        # An explicit output_dir keeps tests and experiments out of shared results.
        destination = Path(output_dir) if output_dir else root / "results/forecast" / label
        destination.mkdir(parents=True, exist_ok=True)
        forecast.to_csv(destination / "forecast_output.csv", index=False)
        reconciliation.to_csv(destination / "cash_reconciliation.csv")
        for key in ["leaderboard", "fold_scores", "cv_predictions", "test_metrics", "test_predictions", "bands"]:
            evaluation[key].to_csv(destination / f"{key}.csv", index=False)
        (destination / "run_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
        if output_dir is None:
            processed = root / "data/processed/forecast" / label
            processed.mkdir(parents=True, exist_ok=True)
            evaluation["development"].to_csv(processed / "development.csv")
            evaluation["test"].to_csv(processed / "test.csv")
            frame.to_csv(processed / "full_history.csv")
            forecast.to_csv(processed / "forecast_output.csv", index=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frequency", choices=["monthly", "daily", "both"], default="monthly")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--opening-balance", type=float, default=None,
                        help="Historical opening cash before day 1; documented demo value: 17000.")
    args = parser.parse_args()
    frequencies = ["MS", "D"] if args.frequency == "both" else ["MS" if args.frequency == "monthly" else "D"]
    for frequency in frequencies:
        result = run_forecast_pipeline(frequency=frequency, project_root=args.project_root, opening_balance=args.opening_balance)
        print(f"\n{frequency}: selected {result['metadata']['selected_model']} on validation")
        print(result["evaluation"]["leaderboard"].to_string(index=False))
        print("\nRetrospective holdout metrics:")
        print(result["evaluation"]["test_metrics"].to_string(index=False))
        print("\nForecast preview:")
        print(result["forecast"][["date", "forecasted_net_cash_flow", "projected_cash_balance"]].head().to_string(index=False))


if __name__ == "__main__":
    main()
