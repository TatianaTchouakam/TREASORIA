"""Small, fixed model candidates. All use only the history passed to them."""

from dataclasses import asdict, dataclass
import warnings
import numpy as np
import pandas as pd
from .data_utils import TARGET, future_index


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str
    window: int = 3
    season: int = 12
    growth: str = "flat"
    yearly: int = 0
    anomaly: bool = False
    order: tuple = (1, 0, 0)
    seasonal_order: tuple = (0, 0, 0, 0)

    def to_dict(self):
        return asdict(self)


def candidate_models(frequency="MS"):
    """Declare candidates before scores are calculated; no test-driven search."""
    if frequency == "MS":
        return [
            ModelSpec("naive", "naive"),
            ModelSpec("mean", "mean"),
            ModelSpec("moving_average_3m", "moving_average", window=3),
            ModelSpec("seasonal_naive_12m", "seasonal_naive", season=12),
            ModelSpec("ARIMA_100", "sarima"),
            # With 24 months, avoid automatic seasonal unit-root tests and large grids.
            ModelSpec("SARIMA_100_100_12", "sarima", seasonal_order=(1, 0, 0, 12)),
            ModelSpec("Prophet_flat", "prophet"),
            ModelSpec("Prophet_flat_yearly1", "prophet", yearly=1),
            # This is a sensitivity candidate, not proof that shocks are predictable.
            ModelSpec("Prophet_flat_yearly1_pulse", "prophet", yearly=1, anomaly=True),
        ]
    if frequency == "D":
        return [
            ModelSpec("naive", "naive"),
            ModelSpec("mean", "mean"),
            ModelSpec("moving_average_28d", "moving_average", window=28),
            ModelSpec("seasonal_naive_7d", "seasonal_naive", season=7),
            ModelSpec("SARIMA_100_100_7", "sarima", seasonal_order=(1, 0, 0, 7)),
            ModelSpec("Prophet_flat_calendar", "prophet", yearly=1),
        ]
    raise ValueError("Use MS or D.")


def training_anomaly_flags(values):
    """Learn the IQR threshold inside THIS training fold, never on future rows."""
    values = pd.Series(values)
    q1, q3 = values.quantile([0.25, 0.75])
    width = q3 - q1
    return ((values < q1 - 1.5 * width) | (values > q3 + 1.5 * width)).astype(float).to_numpy()


def fit_prophet(history, spec, frequency="MS"):
    from prophet import Prophet
    data = pd.DataFrame({"ds": history.index, "y": history[TARGET].to_numpy()})
    model = Prophet(
        growth=spec.growth,
        yearly_seasonality=spec.yearly or False,
        weekly_seasonality=3 if frequency == "D" else False,
        daily_seasonality=False,
        seasonality_prior_scale=1.0,
        # Shared backtest-error bands are built outside the model for all candidates.
        uncertainty_samples=0,
    )
    if frequency == "D":
        # Day-of-month flags are known in advance and describe scheduled payment timing.
        # They are calendar features, not future observed cash values.
        for day in (1, 15, 28):
            column = f"day_{day}"
            data[column] = (history.index.day == day).astype(float)
            model.add_regressor(column, standardize=False, prior_scale=1.0)
    if spec.anomaly:
        flags = training_anomaly_flags(history[TARGET])
        if np.unique(flags).size > 1:
            data["is_anomaly"] = flags
            model.add_regressor("is_anomaly", standardize=False, prior_scale=1.0)
    model.fit(data, seed=42)
    return model


def predict_prophet(model, dates):
    future = pd.DataFrame({"ds": dates})
    for column in model.extra_regressors:
        # Future shocks are unknown. Zero means a normal/reference scenario.
        future[column] = 0.0 if column == "is_anomaly" else (dates.day == int(column.split("_")[1])).astype(float)
    return model.predict(future)["yhat"].to_numpy()


def predict_model(spec, history, horizon, frequency="MS"):
    values = history[TARGET].to_numpy(dtype=float)
    dates = future_index(history.index[-1], horizon, frequency)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Models need at least two finite training values.")
    if spec.family == "naive":
        prediction = np.full(horizon, values[-1])
    elif spec.family == "mean":
        prediction = np.full(horizon, values.mean())
    elif spec.family == "moving_average":
        prediction = np.full(horizon, values[-spec.window:].mean())
    elif spec.family == "seasonal_naive":
        if len(values) < spec.season:
            raise ValueError(f"Need at least {spec.season} periods for seasonal naive.")
        prediction = np.resize(values[-spec.season:], horizon)
    elif spec.family == "prophet":
        prediction = predict_prophet(fit_prophet(history, spec, frequency), dates)
    elif spec.family == "sarima":
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        if spec.seasonal_order[3] and len(values) < 2 * spec.seasonal_order[3]:
            raise ValueError("Seasonal AR parameters need at least two cycles under this protocol.")
        # Scaling improves numerical optimization. Convert the prediction back to EUR.
        scale = max(float(np.std(values)), 1.0)
        model = SARIMAX(values / scale, order=spec.order, seasonal_order=spec.seasonal_order,
                        trend="c", enforce_stationarity=True, enforce_invertibility=True)
        fit = model.fit(disp=False, maxiter=200)
        if not fit.mle_retvals.get("converged", False):
            raise RuntimeError("SARIMA did not converge; do not label it a successful model.")
        prediction = np.asarray(fit.forecast(horizon)) * scale
    else:
        raise ValueError(f"Unknown model family: {spec.family}")
    prediction = np.asarray(prediction, dtype=float)
    if prediction.shape != (horizon,) or not np.isfinite(prediction).all():
        raise RuntimeError("Model returned invalid forecast values.")
    return prediction
