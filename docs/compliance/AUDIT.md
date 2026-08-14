# ZCoder Enterprise Audit & SIEM Export

## 1. Audit Event Schema
Every administrative, identity, and security decision produces an append-only audit event:
```json
{
  "event_id": "evt_99182a",
  "organization_id": "org_corp_1",
  "actor": "alice@corp.com",
  "actor_type": "user",
  "action": "policy.update",
  "resource": "rule_prod_approval",
  "result": "SUCCESS",
  "timestamp": 1723580000.0,
  "schema_version": "1.0"
}
```

## 2. Export & Integrations
- JSONL and CSV streaming export via `zcoder audit export --org <org_id>`.
- Zero sensitive data: secrets, bearer tokens, and private keys are stripped prior to write.
