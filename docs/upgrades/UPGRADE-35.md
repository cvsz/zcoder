# UPGRADE-35: Maintenance Campaign Events and Metrics

## Goal

Make one-shot maintenance campaigns scheduler/worker friendly and observable without introducing another recurring loop or a second observability stack.

Upgrade-35 reuses the existing `ZCoderMetrics` and OpenTelemetry tracing boundary and adds a finite, secret-free event contract around each Upgrade-34 campaign.

## Event contract

Every bounded campaign can emit at most three lifecycle events:

1. `campaign.started`
2. `campaign.recommendations_discovered`
3. `campaign.completed` or `campaign.halted`

`MaintenanceCampaignEvent` contains only operational summary fields such as campaign ID, state, recommendation/work counts, iterations, completed/blocked/pending counts, halt reason, duration, and observer-error count.

Recommendation evidence, UpgradeWorkItem payloads, repository snapshots, provider secrets, and `DATABASE_URL` are not part of the event schema.

## Scheduler-friendly runner

`run_maintenance_campaign_once()` returns `MaintenanceCampaignRunResult` containing:

- the structured `MaintenanceCampaignReport`;
- exit code `0` for `COMPLETED`;
- exit code `2` for bounded non-completed outcomes.

This contract can be called directly by CronJob, worker, scheduler, or service orchestration without parsing CLI stdout. Recurrence remains outside the campaign service.

## Observer failure semantics

Observability is best-effort and cannot change engineering truth.

If an event sink raises:

- the campaign continues;
- Upgrade-20/24 execution result is preserved;
- only the exception type, not its potentially sensitive message, is logged;
- `observer_error_count` is incremented in the final report;
- no unbounded telemetry retry loop is introduced.

## Metrics

The existing `ZCoderMetrics` registry gains bounded-cardinality metrics for:

- campaigns started;
- campaigns ending non-completed;
- recommendations discovered;
- unique maintenance work seeded;
- completed, blocked, and pending work items;
- observer delivery errors;
- campaign duration.

Campaign IDs are never metric labels. They may appear as trace attributes, consistent with the existing policy that high-cardinality correlation belongs in traces rather than Prometheus labels.

The metrics are included in the existing Prometheus exposition and continue to work with the repository's graceful no-op telemetry behavior when optional OpenTelemetry dependencies are unavailable.

## CLI behavior

The existing maintenance campaign CLI now installs `OtelMaintenanceCampaignEventSink` and delegates execution to `run_maintenance_campaign_once()`. JSON/SQLite/PostgreSQL backend behavior, `DATABASE_URL` handling, and local-only push default are unchanged.

## Verification

- `tests/unit/test_maintenance_observability.py` verifies secret-free event serialization, metric updates, halted counters, and Prometheus exposition.
- `tests/unit/test_maintenance_campaign_events.py` verifies finite event ordering, completed/halted scheduler exit codes, empty campaign behavior, and best-effort observer failure semantics.
- Existing Upgrade-34 PostgreSQL cross-campaign deduplication coverage remains authoritative for durable campaign behavior.
- Full hosted Ruff, Black, Bandit, Python 3.9-3.12, Docker, CodeQL, Dependency Review, Helm, SDK/TypeScript, and Release Gate workflows remain required.

## Safety invariants

- no internal recurring/daemon loop;
- no duplicate telemetry stack;
- no high-cardinality campaign IDs in metrics;
- observer failures cannot mutate campaign state or execution result;
- observer failure messages are not surfaced in structured reports;
- Upgrade-20 remains task execution authority;
- Upgrade-24 bounded retry/no-progress/regression policy remains authoritative;
- Upgrade-33 PostgreSQL advisory exclusivity/fencing remains unchanged;
- no security, coverage, CI, or push-policy gate is weakened.

## Next slice

Add a scheduler/worker adapter that consumes `MaintenanceCampaignRunResult` and persists/distributes run summaries through the existing worker/outbox boundaries, while keeping scheduling cadence external and bounded.
