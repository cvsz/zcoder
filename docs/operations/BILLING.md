# Billing Provider Operations

## Provider selection

`FakeBillingProvider` is the deterministic adapter for local development and
CI. It does not contact a payment service. `StripeBillingProvider` sends
customer, subscription, usage, and reconciliation requests only when an
application explicitly constructs it and invokes an operation. Missing API
credentials, plan prices, meter mappings, invalid responses, and provider
errors fail explicitly; the adapter does not generate fake Stripe IDs or
pretend an unperformed operation succeeded.

The application does not automatically select Stripe at startup. Keep the
provider optional for SQLite/local installations. Do not place credentials in
source files, command-line arguments, logs, or example configuration.

## Required Stripe configuration

Provide `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` through the deployment
secret manager. Configure a Stripe Price ID for each billable `PlanTier` and a
Stripe meter event name for every metered usage key. Price IDs and meter event
names are account-specific configuration; the repository cannot infer them.

The adapter sends the customer's email, name, and organization ID to Stripe
when creating a customer. It stores the plan tier in subscription metadata and
sends meter identifiers, customer IDs, configured event names, and usage values
when reporting usage. Review this transfer against the tenant privacy notice
and data-processing terms before enabling Stripe for customer data.

## Idempotency and webhook verification

Customer creation uses a stable organization-derived idempotency key.
Subscription creation accepts an explicit operation idempotency key; otherwise
it derives one from customer and plan. Meter event identifiers are sent to
Stripe and bounded to 100 characters. Supply `occurred_at` when reporting
delayed usage; Stripe accepts event timestamps only within its supported
35-day window. Provider errors propagate so a caller can retry with the same
operation and idempotency key.

Webhook signatures are verified over the exact raw request bytes using the
configured endpoint secret, a timestamp tolerance, and all supplied `v1`
signatures. The HTTP handler must retain the raw body and separately implement
durable event deduplication before applying billing state changes.

## Evidence boundary

Unit tests replace the transport and verify request construction, response
validation, idempotency, pagination, timestamp limits, and signature handling.
They do not contact Stripe or prove sandbox/live account configuration,
payment-method setup, tax behavior, invoice lifecycle, webhook delivery, or
reconciliation against a real account. Do not describe the adapter as
Stripe-verified in production until a protected Stripe test-mode qualification
has passed with non-production credentials and a documented result.
