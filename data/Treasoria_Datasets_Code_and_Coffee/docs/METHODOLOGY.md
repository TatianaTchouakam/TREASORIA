# Methodology — Cost Model & Business Events

This note documents two aspects of Code & Coffee GmbH's financial data that are not directly visible in the Bronze source files, so that anyone reviewing the dataset can understand how they were constructed and why.

## Cost of Goods Sold

The dataset includes a recurring, sales-proportional ingredient-cost layer covering coffee beans, dairy, and bakery inputs. This layer is sized to bring cost of goods sold to approximately 29% of retail sales, resulting in a gross margin of 73.0%.

The ingredient costs are allocated across three supplier categories already used elsewhere in the dataset:

- Coffee beans → Nordbohnen Roastery
- Dairy → Milchhof Bielefeld
- Bakery ingredients → Gebaeck Grosshandel OWL

Recurring operating costs such as rent, utilities, and maintenance are each associated with one fixed, consistent supplier, reflecting the structure of ongoing business contracts. Rent, for example, is invoiced by a single landlord once per month across the 24-month period rather than being distributed randomly across several suppliers.

## Business Events

Two dated business events are included so that the dataset provides meaningful signals for Treasoria's forecasting and liquidity-risk detection:

- **February 2023** — Storm damage requiring an emergency roof and awning repair (EUR 8,500). Net cash flow for the month: +EUR 2,798, remaining positive but markedly reduced.

- **June–July 2023** — An emergency walk-in cooler replacement (EUR 19,500) and kitchen equipment repair (EUR 4,200), combined with a three-month energy price surcharge and delayed payments from a large B2B client. Net cash flow reached -EUR 15,957 in June, the only negative month in the 24-month period, before recovering to +EUR 2,019 in July.

These events are recorded as `derived` transactions with named suppliers, exact dates, and documented business causes rather than unexplained financial adjustments.

## Known Simplification

Credit-card spending in the Marketing, Utilities, Supplies, and Other categories uses a randomised supplier selection from a short candidate list rather than one fixed supplier per category.

This represents a relatively small portion of the ledger, approximately EUR 15,000 over the two-year period, compared with recurring rent, payroll, and cost of goods sold.