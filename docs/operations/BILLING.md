# ZCoder Billing Domain & Entitlements Boundary

## 1. Provider-Neutral Billing
ZCoder isolates its billing domain from third-party payment gateways:
- `BillingAccount`: Represents the customer billing profile and currency.
- `Plan`: Entitlement package (Developer, Team, Enterprise).
- `InvoicePeriod`: Deterministic UTC billing cycle boundaries.

## 2. Entitlement Checks
Application code checks capabilities, never plan strings:
```python
if ctx.has_permission("scim.manage"):
    ...
```
