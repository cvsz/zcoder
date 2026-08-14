# ZCoder Compliance Evidence Collection Platform

## Evidence Freshness & Expiration
- Automated collectors populate `ComplianceCatalog` with real test execution evidence.
- Evidence records carry a Time-To-Live (TTL). Expired evidence transitions to `STALE` and alerts administrators.
- Statuses: `EFFECTIVE`, `PARTIAL`, `INEFFECTIVE`, `STALE`, `NOT_TESTED`.
