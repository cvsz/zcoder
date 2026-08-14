# ZCoder Evidence Model & Single Source of Truth

## Evidence Tiers
- **E0 (Implementation)**: Source code written and structurally complete.
- **E1 (Unit)**: Function-level logic verified in isolation.
- **E2 (Integration)**: Multi-component workflows verified against mock/embedded stores.
- **E3 (System)**: Multi-process concurrency and live database constraints verified.
- **E4 (Live External)**: Live external provider or infrastructure integration tested.
- **E5 (Production Observed)**: Live telemetry metrics observed under operational production load.

## Status Classifications
- `PASS`: Complete requirements fulfilled with matching evidence tier.
- `PASS_WITH_LIMITATIONS`: Core architecture and automation proven; documented environmental boundaries remain.
- `FAIL`: Requirement unmet or broken.
- `STALE`: Previously valid evidence that has exceeded its TTL.
