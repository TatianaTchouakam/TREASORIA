"""Run: python -m unittest src.forecast.test_forecast -v

These tests protect time order, accounting, leakage boundaries and the handoff API.
They use small synthetic fixtures; end-to-end notebook runs separately use Gold.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from .data_utils import (TARGET, GOLD_RELATIVE, daily_net_flow, future_index, load_monthly,
                         reconcile_cash, rolling_splits, split_development_test)
from .models import ModelSpec, predict_model, training_anomaly_flags
from .model_evaluation import error_bands, evaluate_candidates, evaluate_protocol, metrics
from .forecast_pipeline import build_forecast, forecast_to_cash_balance
from .integration import apply_cash_flow_adjustments, summarize_cash_risk


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.monthly = pd.DataFrame({"company_id": "demo", TARGET: np.arange(1, 25, dtype=float)},
                                    index=pd.date_range("2022-01-01", periods=24, freq="MS"))

    def test_temporal_splits_never_overlap(self):
        development, test = split_development_test(self.monthly, 3)
        for fold, history, validation in rolling_splits(development, 3):
            self.assertEqual(len(history), 9 + fold * 3)
            self.assertLess(history.index[-1], validation.index[0])
            self.assertLess(validation.index[-1], test.index[0])

    def test_seasonal_naive_repeats_correct_pattern_beyond_one_year(self):
        actual = predict_model(ModelSpec("seasonal", "seasonal_naive"), self.monthly, 15)
        np.testing.assert_array_equal(actual, [*range(13, 25), 13, 14, 15])

    def test_future_calendar_handles_month_end_and_leap_year(self):
        self.assertEqual(future_index("2023-12-31", 3, "MS")[0], pd.Timestamp("2024-01-01"))
        self.assertEqual(future_index("2024-02-28", 2, "D")[0], pd.Timestamp("2024-02-29"))
        for value in [0, -1, 2.5, True]:
            with self.assertRaises(ValueError):
                future_index("2023-12-31", value, "MS")

    def test_first_daily_flow_requires_opening_balance(self):
        daily = pd.DataFrame({"company_id": "demo", "consolidated_cash_balance": [110., 105., 130.]},
                             index=pd.date_range("2022-01-01", periods=3))
        np.testing.assert_array_equal(daily_net_flow(daily)[TARGET], [-5, 25])
        np.testing.assert_array_equal(daily_net_flow(daily, 100)[TARGET], [10, -5, 25])

    def test_reconciliation_catches_wrong_opening_or_changed_cash(self):
        daily = pd.DataFrame({"company_id": "demo", "consolidated_cash_balance": 100 + np.arange(1, 60)},
                             index=pd.date_range("2022-01-01", "2022-02-28"))
        monthly = pd.DataFrame({"company_id": "demo", TARGET: [31., 28.]},
                               index=pd.date_range("2022-01-01", periods=2, freq="MS"))
        self.assertTrue(reconcile_cash(monthly, daily, 100).checked.all())
        self.assertFalse(reconcile_cash(monthly, daily).checked.iloc[0])
        with self.assertRaises(ValueError):
            reconcile_cash(monthly, daily, 99)
        daily.iloc[-1, daily.columns.get_loc("consolidated_cash_balance")] += 2
        with self.assertRaises(ValueError):
            reconcile_cash(monthly, daily, 100)

    def test_metrics_handle_zero_and_negative_cash(self):
        self.assertEqual(metrics([0, -10], [0, -10])["sMAPE"], 0)
        self.assertEqual(metrics([-10], [10])["sMAPE"], 200)
        with self.assertRaises(ValueError):
            metrics([1, 2], [1])

    def test_data_validation_rejects_duplicate_missing_and_wrong_equations(self):
        frame = self.monthly.copy()
        frame["cash_out_operating"] = 1.
        frame["cash_out_payroll"] = 2.
        frame["cash_out_card_payments"] = 3.
        frame["cash_out_total"] = 6.
        frame["cash_in"] = frame[TARGET] + 6
        frame.index.name = "month"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / GOLD_RELATIVE / "gold_monthly_cash_flow.csv"
            path.parent.mkdir(parents=True)
            frame.to_csv(path)
            self.assertEqual(len(load_monthly(folder)), 24)
            for bad in [pd.concat([frame, frame.iloc[[0]]]), frame.drop(frame.index[2]),
                        frame.assign(net_cash_flow=999), frame.assign(cash_in=np.nan)]:
                bad.to_csv(path)
                with self.assertRaises(ValueError):
                    load_monthly(folder)

    def test_selection_is_unchanged_when_only_test_targets_change(self):
        specs = [ModelSpec("naive", "naive"), ModelSpec("mean", "mean")]
        a = evaluate_protocol(self.monthly, specs=specs)
        altered = self.monthly.copy()
        altered.iloc[-3:, altered.columns.get_loc(TARGET)] = -1e9
        b = evaluate_protocol(altered, specs=specs)
        self.assertEqual(a["selected_model"], b["selected_model"])
        pd.testing.assert_frame_equal(a["cv_predictions"], b["cv_predictions"])
        self.assertNotEqual(a["test_metrics"].MAE.iloc[0], b["test_metrics"].MAE.iloc[0])

    def test_pulse_and_prediction_fit_use_only_each_history(self):
        development, _ = split_development_test(self.monthly, 3)
        received_lengths = []
        def spy(spec, history, horizon, frequency):
            received_lengths.append(len(history))
            flags = training_anomaly_flags(history[TARGET])
            self.assertEqual(len(flags), len(history))
            return np.zeros(horizon)
        with patch("src.forecast.model_evaluation.predict_model", side_effect=spy):
            evaluate_candidates(development, specs=[ModelSpec("spy", "prophet", anomaly=True)])
        self.assertEqual(received_lengths, [12, 15, 18])

    def test_failed_model_is_not_eligible(self):
        dev, _ = split_development_test(self.monthly, 3)
        specs = [ModelSpec("naive", "naive"), ModelSpec("too_long", "seasonal_naive", season=100)]
        board, folds, _ = evaluate_candidates(dev, specs=specs)
        self.assertFalse(board.set_index("model").loc["too_long", "eligible"])
        self.assertTrue((folds.loc[folds.model == "too_long", "status"] == "failed").all())

    def test_balance_envelope_uses_joint_error_paths(self):
        # Each path cancels at step 2; adding marginal absolute errors would be wrong.
        cv = pd.DataFrame({"model": ["x"] * 6, "fold": [1, 1, 2, 2, 3, 3],
                           "horizon_step": [1, 2] * 3, "error": [10., -10., -20., 20., 5., -5.]})
        bands = error_bands(cv, "x")
        self.assertGreater(bands.flow_radius.sum(), 0)
        self.assertEqual(bands.balance_radius.iloc[-1], 0)

    def make_forecast(self, frequency="D"):
        history = self.monthly if frequency == "MS" else self.monthly.set_axis(pd.date_range("2023-12-08", periods=24, freq="D"))
        bands = pd.DataFrame({"horizon_step": [1, 2, 3], "flow_radius": [1, 2, 3],
                              "balance_radius": [1, 3, 6], "nominal_level": [.8] * 3, "calibration_paths": [3] * 3})
        return build_forecast(history, ModelSpec("mean", "mean"), frequency, 3, 100., "2023-12-31", bands)

    def test_delay_changes_path_not_final_cash_or_baseline(self):
        base = self.make_forecast()
        before = base.copy(deep=True)
        adjustments = pd.DataFrame({"date": [base.date.iloc[0], base.date.iloc[2]], "net_flow_delta_eur": [-50., 50.]})
        scenario = apply_cash_flow_adjustments(base, adjustments, "delayed_receipt")
        pd.testing.assert_frame_equal(base, before)
        self.assertEqual(scenario.projected_cash_balance.iloc[0], base.projected_cash_balance.iloc[0] - 50.)
        self.assertEqual(scenario.projected_cash_balance.iloc[-1], base.projected_cash_balance.iloc[-1])
        self.assertGreater(summarize_cash_risk(scenario, 100.)["days_below_threshold"], 0)
        adjustments.loc[1, "date"] = pd.Timestamp("2030-01-01")
        with self.assertRaises(ValueError):
            apply_cash_flow_adjustments(base, adjustments, "outside")

    def test_monthly_risk_does_not_claim_daily_counts(self):
        result = summarize_cash_risk(self.make_forecast("MS"), 1000.)
        self.assertIsNone(result["days_below_threshold"])
        self.assertEqual(result["periods_below_threshold"], 3)

    def test_cash_rollforward_and_bad_inputs(self):
        np.testing.assert_array_equal(forecast_to_cash_balance([10, -20, 5], 100), [110, 90, 95])
        with self.assertRaises(ValueError):
            forecast_to_cash_balance([np.inf], 100)
        bad = self.make_forecast().iloc[::-1]
        with self.assertRaises(ValueError):
            summarize_cash_risk(bad, 100)


if __name__ == "__main__":
    unittest.main()
