# Runbook: nightly warehouse refresh (JOB-7731)

Fictional sample data written for this demo. Ferrowind Supply is an invented
company; job identifiers, error codes, and rotations are made up.

## What this job does

`nightly_warehouse_refresh` (JOB-7731) starts at 01:00 UTC. It runs the
storefront and ads extractors, waits for the hourly order load to catch up,
executes `dbt build` for the intermediate and mart layers, runs the data
quality suite, and finally swaps the serving schema pointer so the reporting
layer reads the new snapshot. Expected duration is 70 to 95 minutes. The
finance close depends on it finishing before 04:00 UTC.

## The freshness gate

Between the mart build and the schema swap sits a gate. If any fact model
fails its freshness test or any primary key test, the swap does not happen.
The reporting layer keeps serving the previous snapshot, which is complete
and internally consistent even though it is a day old. Analysts see a banner
that the snapshot is held, with the failing test named. Holding a snapshot is
the intended behaviour, not an outage: a late but correct number is
preferable to an early wrong one. The gate is never bypassed by rerunning
with tests skipped.

## Error codes you will see

- PIPE-118 Late-arriving source file. The ads spend export has not landed by
  its deadline. The job waits up to 45 minutes, then continues without it and
  marks `fct_acquisition_daily` as partial. Action: none at night; the file
  is backfilled by the 09:00 catch-up run.
- PIPE-410 Target column mismatch. A raw table's columns no longer match the
  staging contract. Action: do not patch the contract at night. Page the
  producing team, hold the snapshot, and follow the schema drift procedure.
- PIPE-503 Warehouse connection pool exhausted. Too many concurrent model
  builds. Action: rerun the dbt step with `--threads 4`; if it recurs three
  nights running, open a capacity ticket.
- DQ-E417 Freshness threshold exceeded. See the gate section. Action:
  identify which upstream load stalled before rerunning anything.
- DQ-E205 Schema drift detected. The pre-load check found new, removed, or
  retyped columns. Action: same as PIPE-410.

## Rerunning safely

All steps are idempotent. To resume after a failure, rerun from the failed
task with the orchestrator's `--start-from <task_id>` option rather than
restarting the whole job, which would re-extract the sources and push the
finish time past the close deadline. Never run a full refresh of an
incremental fact at night; it takes several hours and is scheduled for
weekend maintenance windows with the runbook owner present.

## Escalation ladder

1. On-call data platform engineer (first responder, 15 minute
   acknowledgement).
2. Runbook owner, if the snapshot is still held at 03:30 UTC.
3. Head of Data, if the finance close deadline at 04:00 UTC will be missed.
   Finance is notified by the on-call engineer directly, before the deadline
   passes, with an estimated recovery time.

## On-call rotation

The rotation is weekly, handing over on Mondays at 10:00 UTC. Handover
includes the open incident list, any held snapshots, and the state of
capacity tickets. The person going off call writes a short summary in the
handover log even when nothing happened; an empty week is still a record.

## Checks before closing an incident

- The serving pointer references the newest snapshot.
- The "mart advanced today" gate on the finance dashboard is green.
- Every fired alert has been acknowledged and resolved in the paging tool.
- If a source contract changed, the consumer registry entry was updated and
  the producing team confirmed the change is permanent.
- A postmortem is opened for any hold longer than four hours, using the
  INC-2024-031 write-up as the template.
