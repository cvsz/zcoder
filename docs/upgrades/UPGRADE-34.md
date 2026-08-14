# UPGRADE-34: Bounded Maintenance Campaign Service

## Goal

Turn Upgrade-23 maintenance recommendations into a production-invokable, one-shot campaign over the bounded continuous-engineering runtime without creating another daemon loop or scheduler.

## Architecture

```text
maintenance signals
      |
      v
MaintenanceIntelligenceService (Upgrade-23)
      |
      v
MaintenanceCampaignService
  - generate recommendations once
  - stable recommendation work identity
  - dedupe equivalent recommendations
      |
      v
ContinuousEngineeringPipeline
      |
      +-- JSON compatibility backend
      +-- SQLite same-host backend
      +-- PostgreSQL fenced fleet backend (Upgrade-33)
```

Each campaign performs one bounded `pipeline.run()` call. Recurrence belongs to an external scheduler, worker platform, CronJob, or operator—not an unbounded loop inside this service.

## Stable recommendation identity

Upgrade-23 recommendation objects use UUID-backed IDs. Feeding those volatile IDs directly into an UpgradeWorkItem payload would create a new fingerprint every campaign even when the recommendation content is identical.

`maintenance_campaign_work()` therefore derives a stable SHA-256 recommendation key from:

- work kind;
- normalized recommendation reason/title;
- repository;
- recommendation type;
- priority;
- risk.

The volatile recommendation UUID is not stored in the work payload. Equivalent recommendation content therefore produces the same Upgrade-24 work fingerprint across process/campaign restarts and can be deduplicated by the durable ledger.

## Campaign report

`MaintenanceCampaignReport` exposes a secret-free operational summary:

- campaign ID;
- loop state;
- recommendations discovered;
- unique work seeded;
- iterations;
- completed/blocked/pending counts;
- halt reason;
- terminal ledger counts;
- start/finish/duration.

Recommendation evidence, repository snapshots, provider credentials, and `DATABASE_URL` are not emitted in the structured report.

## Signal input

The module CLI accepts an optional JSON array via `--signals-file`. Supported Upgrade-23 signal types are parsed through the existing `SignalType` enum. Invalid signal types or non-object evidence fail closed.

Example:

```json
[
  {
    "repository": "cvsz/zcoder",
    "type": "DEPENDENCY_OUTDATED",
    "source": "dependency-scan",
    "evidence": {"package": "demo"}
  },
  {
    "repository": "cvsz/zcoder",
    "type": "CI_FAILURE",
    "source": "github-actions"
  }
]
```

Production PostgreSQL invocation:

```bash
DATABASE_URL='postgresql://...' \
python -m zcoder.services.maintenance_campaign \
  --repository . \
  --state-backend postgres \
  --ledger-namespace production-maintenance \
  --signals-file maintenance-signals.json \
  --max-iterations 12
```

JSON remains the default backend. Automatic push remains disabled unless `--allow-push` is explicitly supplied.

## Verification

`tests/unit/test_maintenance_campaign.py` covers stable UUID-independent fingerprints, in-campaign deduplication, empty/resume campaigns, blocked/halt summaries, signal validation, JSON default behavior, PostgreSQL environment-secret routing, secret non-disclosure, and cleanup.

`tests/integration/test_maintenance_campaign_postgres_live.py` uses hosted `DATABASE_URL` when available and proves that two campaigns with equivalent recommendations but different volatile recommendation IDs execute the work only once across PostgreSQL-backed restarts.

## Safety invariants

- exactly one bounded pipeline invocation per campaign;
- no internal recurring/daemon loop;
- Upgrade-24 iteration, retry, no-progress, and regression budgets remain authoritative;
- Upgrade-20 remains the task executor;
- PostgreSQL campaign state reuses Upgrade-33 advisory exclusivity and fencing;
- equivalent recommendations deduplicate across campaign restarts;
- structured reports exclude credentials and evidence payloads;
- JSON/SQLite compatibility remains intact;
- no CI, security, coverage, or push-policy gate is weakened.

## Next slice

Add structured maintenance campaign metrics/events and a scheduler-friendly service entrypoint contract so CronJob/worker orchestration can consume results without scraping stdout, while keeping recurrence outside the campaign execution loop.
