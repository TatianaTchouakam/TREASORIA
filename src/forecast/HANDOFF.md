# Forecast handoff for Tatiana and Aysenur

## Status and scope

The Forecast module now runs end-to-end from the existing Gold CSVs, without
manual notebook state. It produces a monthly forecast and an independently
evaluated daily experiment, both connected to the last observed consolidated
cash balance. It includes source reconciliation, fixed candidate models,
expanding-window validation, retrospective holdout reporting, future refitting,
uncertainty caveats, CSV outputs and a tested integration example.

This completes the forecast-side MVP handoff. It does **not** implement the full
Liquidity Risk Engine, the What-if interface, a gross sales/expense forecast,
invoice scheduling, or Streamlit wiring. The existing app pages remain placeholders.
No repository pull, commit, push, SQL rebuild, deployment or message
was performed. The source data and unrelated repository edits are preserved.

## How the two inputs are used

- Monthly Gold: 24 observations, January 2022-December 2023, target `net_cash_flow`.
- Daily Gold: 730 end-of-day consolidated cash balances over the same period.
- Daily target: difference between consecutive consolidated balances. With the
  documented EUR 17,000 opening cash, first-day flow is EUR 802.
- All 24 daily-to-monthly net-flow sums reconcile within EUR 0.01.
- Forecast starting balance: **EUR 234,549.89 at 2023-12-31**.
- Monthly forecast: January-March 2024. Daily forecast: January 1-March 30, 2024.

The presentation describes day/week forecasting; The monthly track preserves that starting point; the daily track addresses daily timing separately. No monthly rows are duplicated into days.
These are historical demo forecasts, not current 2026 forecasts.

## Evaluation design

Monthly development is 21 months, with three expanding training sizes of 12, 15,
and 18 months and three non-overlapping 3-month validation blocks. The final
3 months are reserved for reporting by the current code. Daily development is
640 days, with training sizes 370, 460 and 550, three 90-day validation blocks,
and a final 90-day report from 2023-10-03 through 2023-12-31.

Candidate sets are fixed in `models.py`. Every candidate must succeed on every
fold to be eligible. Failed fits and warnings are recorded. Selection minimizes
validation MAE; a complex model must improve the best baseline by at least 5%.
Fold variability, worst-fold MAE and fit time are also exposed for review, although
they are not an additional weighted score. This small sample does not support
claims of statistically significant superiority.

Only the selected model and, if different, the best validation baseline are
reported on the final block. Test metrics never enter the selection function.
The earlier notebooks already inspected the last quarter, so these scores are
**retrospective holdout results**, not a newly blind final test. A fresh experiment
needs new unseen observations.

After reporting, the selected specification is refit to all available observations
and forecasts start immediately after the source cutoff. No future actual values
are used as regressors. Anomaly thresholds, where used, are fitted inside each
training fold. Future anomaly pulses are zero, a conditional normal-event assumption.

## Results from the verified run

| Track | Selected model | Validation MAE | Retrospective test MAE | Test RMSE | Test sMAPE |
| --- | --- | ---: | ---: | ---: | ---: |
| Monthly | seasonal_naive_12m | 5,040.74 EUR/month | 2,104.78 EUR/month | 3,007.22 EUR/month | 14.31% |
| Daily | Prophet_flat_calendar | 531.23 EUR/day | 513.96 EUR/day | 952.57 EUR/day | 47.07% |

Do not compare monthly and daily MAE numerically as if they measured the same
period. Daily selection improved validation MAE by about 36.19% over its best
baseline (naive, EUR 832.54/day). Monthly Prophet with the pulse feature scored
EUR 5,127.70/month in validation, so it did not beat seasonal naive.

The annual seasonal AR candidate is ineligible because the monthly folds contain
fewer than two cycles. Nonseasonal ARIMA was evaluated. Daily weekly SARIMA was
also evaluated. XGBoost is deferred: it is not needed to make the MVP work, and
monthly lag features would leave even fewer examples. This is an explicit scope
choice, not a claim that XGBoost cannot ever work here.

The selected monthly seasonal naive repeats past calendar-month outcomes,
including one-off events. Its low February forecast repeats the February 2023
shock; it does not model the cause of that shock. Retain this limitation in the UI.

## Files the next module should read

Use either `results/forecast/monthly/forecast_output.csv` or
`results/forecast/daily/forecast_output.csv`. Identical convenience copies live
under `data/processed/forecast/{monthly,daily}/`. Choose **one frequency** for an
analysis. Independent daily forecasts do not necessarily sum to monthly forecasts;
future temporal reconciliation is not implemented.

| Field | Meaning / contract |
| --- | --- |
| `date` | Period label, month-start for MS or calendar date for D |
| `period_end` | Date of the projected closing balance; month-end for MS |
| `company_id`, `currency` | Company traceability; this demo uses EUR |
| `frequency` | `MS` or `D`; do not mix in one risk calculation |
| `scenario_id` | `baseline` for the reference forecast |
| `model` | Frozen validation-selected model name |
| `as_of_date` | Last actual daily balance date, not the execution date |
| `horizon_step` | 1-based number of months/days ahead |
| `forecasted_net_cash_flow` | Signed EUR received minus paid during that period |
| `starting_cash_balance` | Last actual balance, repeated as the common anchor |
| `projected_cash_balance` | Anchor plus cumulative forecasted net cash flow |
| `net_flow_lower`, `net_flow_upper` | Exploratory flow-error envelope |
| `cash_balance_lower`, `cash_balance_upper` | Exploratory cumulative-path error envelope |
| `uncertainty_method`, `nominal_level` | Descriptive error method and nominal 0.8 level |
| `calibration_paths` | Only 3 historical validation paths at each horizon |
| `uncertainty_is_calibrated` | False; do not turn the envelope into a failure probability |

Amounts are kept at model precision for calculations. Round to two decimals for
display; do not round each predicted flow before summing if you want exact agreement
with the stored unrounded cash path. CSV dates use ISO representations and no index
column is included in forecast files.

Other files in each result directory:

- `leaderboard.csv`: validation selection only; failed candidates remain visible.
- `fold_scores.csv`: training/validation dates, scores, warnings, status and timing.
- `cv_predictions.csv`: dated out-of-fold predictions and errors.
- `test_metrics.csv`, `test_predictions.csv`: retrospective final-block reporting.
- `bands.csv`: flow and cumulative-error radii by forecast horizon.
- `cash_reconciliation.csv`: monthly reconciliation against daily balance movements.
- `run_metadata.json`: data/code hashes, source cutoff, parameters, library versions,
  selection rule, actual starting balance and limitations.

## Uncertainty interpretation

All shared-pipeline candidates use the same empirical error-envelope method.
For each horizon, we take the upper empirical 80th percentile of absolute validation
errors. For cash balance, we first cumulatively sum each fold's signed error path,
then take the absolute-error percentile. We do **not** add marginal lower bounds.

There are only three validation paths. The nominal percentile often selects the
sample maximum; it is not an 80% calibrated predictive interval, simultaneous band
or guarantee. Validation is also used for model selection, not independent
calibration. Flow-envelope holdout coverage was 100% on three monthly observations
and 74.44% on 90 daily observations; cash-path coverage was 100% and 96.67%.
These are diagnostic observations, not reliable long-run coverage estimates.

The learning template separately illustrates Prophet's native intervals. Those
are model-based intervals and are not interchangeable with the pipeline envelopes.

## Python integration example

Run from the repository root:

```python
import pandas as pd
from src.forecast.forecast_pipeline import run_forecast_pipeline
from src.forecast.integration import apply_cash_flow_adjustments, summarize_cash_risk

# In an app, read the saved CSV or cache this expensive fit outside the UI rerender.
result = run_forecast_pipeline(frequency="D", horizon=90, opening_balance=17000.0)
baseline = result["forecast"]

# This threshold is illustrative; the business owner must define the real policy.
base_summary = summarize_cash_risk(baseline, threshold=240000.0)

# Example only: a known EUR 5,000 receipt is delayed by 30 calendar days.
# Both dates must belong to the forecast horizon.
deltas = pd.DataFrame({
    "date": [baseline.date.iloc[4], baseline.date.iloc[34]],
    "net_flow_delta_eur": [-5000.0, 5000.0],
})
scenario = apply_cash_flow_adjustments(baseline, deltas, "receipt_delayed_30d")
scenario_summary = summarize_cash_risk(scenario, threshold=240000.0)
```

The reference frame remains unchanged. Within-horizon payment delays preserve
final cumulative cash while changing the path. Dates outside the forecast are
rejected, so a delayed receipt cannot silently vanish from the scenario.
The envelope is shifted conditionally by fixed scenario deltas; no additional
uncertainty in scenario assumptions is modeled.

`run_forecast_pipeline()` now returns a dictionary with `forecast`, `evaluation`,
`reconciliation` and `metadata`. The earlier nonfunctional script returned a
DataFrame; use `result['forecast']` in new integration code. The old placeholder
`last_known_balance=50000` was removed. The actual anchor comes from Gold.

## What the Risk / What-if owner still needs to define

1. **Frequency and horizon:** monthly overview or daily timing. Do not count days
   from monthly rows. `summarize_cash_risk` returns `days_below_threshold=None`
   for monthly input. It describes future closing balances, not intraday lows.
2. **Policy thresholds:** approved EUR threshold, alert categories, runway period
   and treatment of positive net inflows. There is no invented universal risk limit.
3. **Gross scenario drivers:** net flow alone cannot support Sales -15% or Costs
   +10%. Define separate future receipt/payment references and timing. Sales are
   not automatically same-period cash collections. Apply `delta_cash_in - delta_cash_out`
   to the baseline net flow, with clearly stated assumptions.
4. **Invoice delays:** identify the affected invoice/receipt amount and expected
   cash date, then subtract/add at dated periods. Extend the validated horizon or
   report outstanding cash beyond the horizon explicitly.
5. **Additional risks:** unusual gross outflow and customer concentration require
   gross flow/customer tables, not only the net-flow CSV. Monthly/day-level net
   projections cannot identify those sources by themselves.
6. **User interface:** choose a track, label the source cutoff and uncertainty,
   display baseline/scenario paths, and avoid presenting forecasts as certain.

These are integration inputs and next-module decisions. The forecast artifact
already provides the baseline contract and tested EUR-delta connection.

## Verification and preservation

- Both pipelines completed using the local `treasoria-env` and original Gold copies.
- All seven current notebooks were executed cell-by-cell, each in a fresh Python
  process, with plots rendered and outputs saved. Execution does not depend on
  a notebook previously being run. Notebook structure was validated with nbformat.
- 14 unit tests cover time boundaries, first-day opening balance, reconciliation,
  invalid data, zero/negative metrics, test-target selection isolation, failed
  model visibility, error-path bands, scenario immutability and cash identities.
- Original forecast files are archived before replacement. Existing Gold files,
  unrelated app code and repository-wide dependency edits are preserved.

## Suggested explanation to the Tatiana

> The Forecast side is ready for integration. I compared baselines, ARIMA and
> Prophet with chronological expanding validation. Seasonal naive was selected
> for the 24-month series; a separate daily net-flow experiment selected Prophet.
> Daily movements reconcile with monthly flows, and both outputs start from the
> actual EUR 234,549.89 balance at 2023-12-31. I included model/parameter metadata,
> retrospective test results and explicit uncertainty limitations. The CSV/API
> contract is documented. Next we can choose the display frequency and define
> the gross receipt/cost assumptions and invoice timing for percentage/delay scenarios.


## References

- Supplied Treasoria presentation, pages 11-14 and 19-22.
- Dataset README, Data Dictionary, Methodology and Validation Report.
- [Prophet monthly-data guidance](https://facebook.github.io/prophet/docs/non-daily_data.html).
- [Prophet diagnostics](https://facebook.github.io/prophet/docs/diagnostics.html).
- [Prophet seasonality and regressors](https://facebook.github.io/prophet/docs/seasonality%2C_holiday_effects%2C_and_regressors.html).
- [Statsmodels SARIMAX](https://www.statsmodels.org/stable/generated/statsmodels.tsa.statespace.sarimax.SARIMAX.html).
