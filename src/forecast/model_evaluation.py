"""Time-based evaluation shared by the notebooks and the application pipeline."""

from time import perf_counter
import warnings
import numpy as np
import pandas as pd
from .data_utils import TARGET, rolling_splits, split_development_test
from .models import candidate_models, predict_model

BASELINE_FAMILIES = {"naive", "mean", "moving_average", "seasonal_naive"}


def metrics(actual, predicted):
    """MAE and RMSE use EUR. sMAPE uses percent and handles zero/zero as zero."""
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape or actual.ndim != 1 or not len(actual):
        raise ValueError("Metric inputs must be non-empty matching one-dimensional arrays.")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics require finite values.")
    error = actual - predicted
    denominator = np.abs(actual) + np.abs(predicted)
    ratios = np.divide(2 * np.abs(error), denominator, out=np.zeros_like(error), where=denominator != 0)
    return {"MAE": float(np.mean(np.abs(error))),
            "RMSE": float(np.sqrt(np.mean(error ** 2))),
            "sMAPE": float(100 * np.mean(ratios)),
            "bias_actual_minus_pred": float(error.mean())}


def evaluate_candidates(development, frequency="MS", horizon=3, folds=3, specs=None):
    """This function receives development data only; it cannot read the final test."""
    specs = specs if specs is not None else candidate_models(frequency)
    predictions, fold_rows = [], []
    for spec in specs:
        for fold, history, validation in rolling_splits(development, horizon, folds):
            start = perf_counter()
            row = {"model": spec.name, "family": spec.family, "fold": fold,
                   "train_start": history.index[0], "train_end": history.index[-1],
                   "validation_start": validation.index[0], "validation_end": validation.index[-1],
                   "train_n": len(history), "validation_n": len(validation)}
            captured = []
            try:
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter("always")
                    predicted = predict_model(spec, history, len(validation), frequency)
                row.update(status="ok", error="", **metrics(validation[TARGET], predicted))
                for step, (date, actual, estimate) in enumerate(zip(validation.index, validation[TARGET], predicted), 1):
                    predictions.append({"model": spec.name, "fold": fold, "origin": history.index[-1],
                                        "date": date, "horizon_step": step, "y_true": actual,
                                        "y_pred": estimate, "error": actual - estimate})
            except (ImportError, ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
                # Failures remain visible. A failed candidate is never silently renamed a baseline.
                row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            row["warnings"] = " | ".join(dict.fromkeys(str(w.message) for w in captured))
            row["fit_seconds"] = perf_counter() - start
            fold_rows.append(row)
    fold_scores = pd.DataFrame(fold_rows)
    cv_predictions = pd.DataFrame(predictions, columns=["model", "fold", "origin", "date", "horizon_step", "y_true", "y_pred", "error"])
    summary = []
    for spec in specs:
        rows = fold_scores.loc[fold_scores.model == spec.name]
        successful = rows.loc[rows.status == "ok"]
        item = {"model": spec.name, "family": spec.family, "successful_folds": len(successful),
                "required_folds": folds, "eligible": len(successful) == folds,
                "fit_seconds": float(rows.fit_seconds.sum())}
        if item["eligible"]:
            values = cv_predictions.loc[cv_predictions.model == spec.name]
            item.update(metrics(values.y_true, values.y_pred))
            item["fold_MAE_std"] = float(successful.MAE.std(ddof=0))
            item["worst_fold_MAE"] = float(successful.MAE.max())
        else:
            item.update({k: np.nan for k in ["MAE", "RMSE", "sMAPE", "bias_actual_minus_pred", "fold_MAE_std", "worst_fold_MAE"]})
        summary.append(item)
    leaderboard = pd.DataFrame(summary).sort_values(["eligible", "MAE", "fold_MAE_std"], ascending=[False, True, True], kind="stable").reset_index(drop=True)
    return leaderboard, fold_scores, cv_predictions


def select_best_model(leaderboard, minimum_improvement=0.05):
    """Prefer a baseline unless a complex model reduces validation MAE by >=5%."""
    eligible = leaderboard.loc[leaderboard.eligible].sort_values(["MAE", "fold_MAE_std"], kind="stable")
    if eligible.empty:
        raise RuntimeError("No model completed every validation fold.")
    baselines = eligible.loc[eligible.family.isin(BASELINE_FAMILIES)]
    best = eligible.iloc[0]
    if not baselines.empty:
        baseline = baselines.iloc[0]
        if best.family not in BASELINE_FAMILIES and best.MAE > baseline.MAE * (1 - minimum_improvement):
            return baseline.model, f"Complex model improvement was below {minimum_improvement:.0%}; keep the baseline."
    return best.model, "Lowest validation MAE; complex models must beat the best baseline by at least 5%."


def error_bands(cv_predictions, model_name, level=0.8):
    """An exploratory error envelope, not a calibrated probability guarantee.

    Preserve each fold's whole error path when evaluating cumulative cash error.
    Adding individual monthly interval endpoints would not produce a valid cash band.
    With only three folds, each horizon has only three error paths.
    """
    chosen = cv_predictions.loc[cv_predictions.model == model_name]
    paths = chosen.pivot(index="fold", columns="horizon_step", values="error").sort_index(axis=1)
    if paths.empty or paths.isna().any().any():
        raise ValueError("Complete validation error paths are required.")
    errors = paths.to_numpy()
    return pd.DataFrame({
        "horizon_step": paths.columns,
        "flow_radius": np.quantile(np.abs(errors), level, axis=0, method="higher"),
        "balance_radius": np.quantile(np.abs(np.cumsum(errors, axis=1)), level, axis=0, method="higher"),
        "calibration_paths": len(paths),
        "nominal_level": level,
    })


def evaluate_protocol(frame, frequency="MS", specs=None):
    """Select on rolling validation, report on the final block, then stop.

    Monthly: 21 development months, three 3-month folds, final 3-month test.
    Daily: 640 development days, three 90-day folds, final 90-day test.
    The earlier project already inspected 2023 Q4, so this is a retrospective
    holdout demonstration, not a brand-new blind experiment.
    """
    horizon = 3 if frequency == "MS" else 90
    development, test = split_development_test(frame, horizon)
    specs = specs if specs is not None else candidate_models(frequency)
    leaderboard, folds, cv = evaluate_candidates(development, frequency, horizon, specs=specs)
    selected, reason = select_best_model(leaderboard)
    best_baseline = leaderboard.loc[leaderboard.eligible & leaderboard.family.isin(BASELINE_FAMILIES)]
    test_names = [selected]
    if not best_baseline.empty and best_baseline.iloc[0].model != selected:
        test_names.append(best_baseline.iloc[0].model)
    test_rows, test_predictions = [], []
    for name in test_names:
        spec = next(s for s in specs if s.name == name)
        predicted = predict_model(spec, development, len(test), frequency)
        bands = error_bands(cv, name)
        lower, upper = predicted - bands.flow_radius.to_numpy(), predicted + bands.flow_radius.to_numpy()
        actual = test[TARGET].to_numpy()
        cash_error = np.cumsum(actual - predicted)
        cash_radius = bands.balance_radius.to_numpy()
        test_rows.append({"model": name, "selected_on_validation": name == selected,
                          **metrics(actual, predicted), "flow_band_coverage": float(np.mean((actual >= lower) & (actual <= upper))),
                          "balance_band_coverage": float(np.mean(np.abs(cash_error) <= cash_radius)),
                          "balance_path_MAE": float(np.mean(np.abs(cash_error))),
                          "end_balance_error_actual_minus_pred": float(cash_error[-1]),
                          "test_n": len(test), "test_start": test.index[0], "test_end": test.index[-1]})
        test_predictions.append(pd.DataFrame({"model": name, "date": test.index, "y_true": actual,
                                              "y_pred": predicted, "flow_lower": lower, "flow_upper": upper,
                                              "cumulative_actual_flow": np.cumsum(actual),
                                              "cumulative_predicted_flow": np.cumsum(predicted),
                                              "balance_error_radius": cash_radius}))
    return {"selected_model": selected, "selection_reason": reason,
            "leaderboard": leaderboard, "fold_scores": folds, "cv_predictions": cv,
            "test_metrics": pd.DataFrame(test_rows), "test_predictions": pd.concat(test_predictions, ignore_index=True),
            "bands": error_bands(cv, selected), "development": development, "test": test,
            "spec": next(s for s in specs if s.name == selected)}
