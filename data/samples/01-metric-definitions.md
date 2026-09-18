# Ferrowind Supply metric definitions (MD-2025.3)

Fictional sample data written for this demo. Ferrowind Supply is an invented
online retailer of workshop tools; nothing here describes a real company.

This guide is the single source of truth for the business metrics served from
the finance and growth marts. Every metric has a stable identifier (MTR-nnn),
an owning team, a defining SQL fragment, and the mart table it is read from.
Dashboards must reference the metric identifier, never a re-derived formula.

## MTR-001 Gross merchandise value

Owner: Finance Analytics. Source: `mart_finance.fct_orders_daily`, column
`gmv_gross_usd`.

Gross merchandise value is the sum of `order_total_gross_usd` over orders
whose `order_status` is not `cancelled` on the day the order was placed. Taxes
collected on behalf of a jurisdiction are excluded; shipping charged to the
buyer is included. Orders placed in a non-USD storefront are converted at the
daily reference rate stored in `mart_finance.dim_fx_rates`, keyed by
`rate_date` and `currency_code`.

## MTR-004 Net revenue

Owner: Finance Analytics. Source: `mart_finance.fct_orders_daily`, column
`net_revenue_usd`.

Net revenue is MTR-001 minus refunds recognized on the same calendar day,
minus promotional discounts, minus marketplace seller payouts. Refunds are
attributed to the day they are approved, not the day the original order was
placed, so net revenue for a past day never changes after the fact. The
finance close process relies on this property; do not backdate refunds.

## MTR-007 Repeat buyer

Owner: Growth Analytics. Source: `mart_growth.dim_buyers`, flag
`is_repeat_buyer`.

A repeat buyer is a buyer who comes back: a buyer account with at least two
delivered orders within the trailing 365 days, counted at the evaluation
date. Cancelled and refunded orders do not count. Guest checkouts are matched
to an account by verified email before evaluation; unmatched guest orders
never contribute. The flag is recomputed nightly.

## MTR-012 Order defect rate

Owner: Operations Analytics. Source: `mart_ops.fct_order_outcomes`, column
`is_defective`.

An order is defective when any of the following is true: a refund was
approved for any line, a payment dispute was opened, or the parcel was
delivered more than three days after the end of the promised delivery window.
The order defect rate is the count of defective orders divided by the count of
delivered orders in the same period. Orders still in transit are excluded from
both numerator and denominator until they are delivered or written off.

## MTR-019 Contribution margin

Owner: Finance Analytics. Source: `mart_finance.fct_orders_daily`, column
`contribution_margin_usd`.

Contribution margin is MTR-004 minus cost of goods, minus outbound shipping
paid by Ferrowind, minus payment processing fees. Marketing spend is not
deducted here; it is reported separately as MTR-022 so that the margin figure
stays comparable across channels with different acquisition costs.

## MTR-022 Blended acquisition cost

Owner: Growth Analytics. Source: `mart_growth.fct_acquisition_daily`.

Blended acquisition cost is total paid marketing spend for the day divided by
the number of first-order buyers on that day. Spend is taken from the
`raw_ads.spend_daily` feed after the DQ-E205 schema check passes. A buyer is a
first-order buyer on the day of their first delivered order, so the metric
lags spend by the delivery time.

## Change control

Changing a definition requires a pull request against this file, a new
version tag in the heading, and a note in the metric's `schema.yml`
description. The identifier never changes; a materially different definition
gets a new identifier and the old one is marked deprecated with its final
valid date.
