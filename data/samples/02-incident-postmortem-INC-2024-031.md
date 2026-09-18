# Postmortem INC-2024-031: stale orders in the finance mart

Fictional sample data written for this demo. Ferrowind Supply is an invented
company; the incident, people, and systems are made up.

Severity: SEV-2. Duration: 19 hours from first stale row to full recovery.
Owner: Data Platform on-call. Status: closed, action items tracked below.

## Summary

For most of one business day the finance mart served order figures that were
frozen at 03:00. The hourly load into `stg_storefront__orders` had been
failing since the overnight run, the freshness monitor raised DQ-E417 on
every cycle, and nobody saw it because the alert was routed to a channel that
had been muted during an unrelated migration. Executive dashboards showed a
flat morning and a sudden catch-up spike once the load was repaired.

## Timeline (all times UTC)

- 02:40 The storefront platform team deployed a release that added a nullable
  column, `fulfilled_at_tz`, to `raw_storefront.orders`. The change was not
  announced to downstream consumers.
- 03:05 `orders_hourly_load` (JOB-4410) ran `INSERT INTO ... SELECT *` from the
  raw table into a typed staging table. The column count no longer matched
  and the job failed with PIPE-410 (target column mismatch).
- 03:06 The freshness monitor on `stg_storefront__orders` fired DQ-E417
  (freshness threshold exceeded: 65 minutes against a 60 minute threshold).
  The alert posted to `#dp-alerts-legacy`, a channel muted since the
  monitoring migration two weeks earlier.
- 03:06 to 21:15 DQ-E417 fired every hour. JOB-4410 retried and failed with
  the same error on each run.
- 20:50 A finance analyst noticed that gross merchandise value for the day
  had not moved since morning and asked in the support channel.
- 21:15 On-call confirmed the failing job, replaced `SELECT *` with an
  explicit column list, and reran JOB-4410 from the first failed hour.
- 22:00 All hourly partitions were rebuilt. Downstream marts refreshed on the
  next scheduled run and the dashboards caught up.

## Root cause

Two independent faults combined. First, the staging load relied on positional
column matching, so an additive, backwards-compatible change upstream became a
hard failure downstream. Second, the freshness alert existed and worked, but
its destination was a muted channel, so the signal never reached a person.
Neither fault alone would have produced a nineteen hour outage.

## What went well

- The freshness monitor detected the problem within one cycle.
- The failed job did not write partial data; the staging table stayed
  consistent, only stale.
- Reprocessing was idempotent, so the rerun needed no manual cleanup.

## What went badly

- The upstream team had no list of downstream consumers to notify.
- Alert routing was changed by the monitoring migration without a test that
  a synthetic failure reaches a human.
- Nobody owned a daily check that the finance mart had advanced.

## Action items

- AI-031-1 Replace every `SELECT *` load in the storefront pipeline with an
  explicit column list. Owner: Data Platform. Done.
- AI-031-2 Add a schema drift check (DQ-E205) that compares the raw table's
  columns against the staging contract before each load. Owner: Data
  Platform. Done.
- AI-031-3 Route DQ-E417 and PIPE-410 to the paging rotation, not to chat, and
  add a weekly synthetic alert that must be acknowledged. Owner: Platform
  Reliability. Done.
- AI-031-4 Publish a consumer registry so producing teams can see who reads
  each raw table. Owner: Storefront Platform. In progress.
- AI-031-5 Add a "mart advanced today" gate to the finance dashboard header
  that turns red when the latest partition is older than two hours. Owner:
  Finance Analytics. Done.

## Lessons

An alert that nobody receives is the same as no alert. Detection was fine;
delivery failed. The fix is not more monitors but a periodic proof that the
existing ones reach someone who will act.
