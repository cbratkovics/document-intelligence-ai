# Ferrowind dbt modeling style guide

Fictional sample data written for this demo. Ferrowind Supply is an invented
company. This guide governs the `ferrowind_warehouse` dbt project.

## Layers and prefixes

Models live in four layers. The prefix is mandatory and the folder must match.

| Layer | Prefix | Folder | Purpose |
|---|---|---|---|
| Staging | `stg_` | `models/staging/<source>/` | One model per source table |
| Intermediate | `int_` | `models/intermediate/` | Reusable joins and derivations |
| Facts | `fct_` | `models/marts/<domain>/` | Event or transaction grain |
| Dimensions | `dim_` | `models/marts/<domain>/` | Entity grain |

Staging models are named `stg_<source>__<table>` with a double underscore,
for example `stg_storefront__orders`. Marts are named for what they contain,
not for who asked for them: `fct_orders`, never `fct_orders_for_finance`.

## What each layer may do

A staging model does exactly one thing: it reads one source table, renames
columns to the warehouse convention, casts types, and applies light cleanup
such as trimming whitespace and standardizing timestamps to UTC. It performs
no joins, no filtering of rows beyond removing hard deletes, and no
calculations that encode a business rule. If you find yourself writing a
CASE expression that a finance person would have an opinion about, it does
not belong in staging.

Intermediate models hold the joins and derivations that more than one mart
needs. They are not exposed to dashboards and carry no service level
objective. Business rules that define a metric belong in intermediate or
mart models, next to the tests that prove them, and must cite the metric
identifier from the metric definitions guide in the model description.

Mart models are the only models dashboards may read. Every mart model has a
declared grain in its description ("one row per order per day"), a primary
key test, and an owner.

## Materializations

- Staging: `view`, unless the source table exceeds 50 million rows, in which
  case `incremental` with the source's updated-at column as the cursor.
- Intermediate: `ephemeral` by default; `table` when reused by three or more
  models or when a query plan shows repeated scans.
- Facts: `incremental` on the event timestamp with a three day lookback to
  absorb late arrivals. Full refresh is a deliberate action recorded in the
  runbook, never a scheduled default.
- Dimensions: `table`, rebuilt nightly.

## Required tests

Every model must declare in `schema.yml`: `unique` and `not_null` on the
primary key, `accepted_values` on any status column, and `relationships`
from every foreign key to its dimension. Facts additionally carry a
freshness test with a threshold agreed with the consuming team; the finance
marts use 60 minutes, growth marts use 24 hours.

Tests are not optional documentation. A pull request that adds a model
without tests is rejected by CI regardless of who approves it.

## Naming and SQL style

- Snake case everywhere. Booleans start with `is_` or `has_`. Timestamps end
  with `_at`; dates end with `_date`; amounts end with the unit, such as
  `_usd` or `_cents`.
- Select columns explicitly. `SELECT *` is forbidden in every layer since
  INC-2024-031.
- One CTE per logical step, named for what it produces, and a final CTE named
  `final` that is selected from without further transformation.
- Prefer `coalesce` and explicit casts over database-specific shorthands so
  the project stays portable across engines.

## Slim CI

Pull requests build only modified models and their descendants using
`dbt build --select state:modified+ --defer --state prod-artifacts/`. The
production manifest is fetched from the artifact store before the run. A
change to a staging model therefore rebuilds every mart downstream, which is
the point: the cost of the build is proportional to the blast radius of the
change.

## Documentation

Every model, column, and metric has a description. Descriptions explain what
a thing means to the business, not how the SQL computes it. Generated docs
are published on every merge to main and are the first place an analyst
should look before asking a question in chat.
