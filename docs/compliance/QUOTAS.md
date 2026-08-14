# ZCoder Quotas and Budgeting

## Quota Dimensions
- `monthly_spend_usd`: Total dollar cap per billing period.
- `concurrent_jobs`: Simultaneous running agent workloads.
- `managed_agents`: Number of active managed agent sessions.

## Atomic Reservation Pattern
Before worker execution:
```sql
SELECT current_value, limit_value FROM tenant_quotas
WHERE organization_id = $1 AND metric = $2
FOR UPDATE;
```
If `current_value + requested_amount <= limit_value`, the capacity is reserved atomically.
