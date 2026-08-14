# ZCoder SCIM 2.0 Identity Provisioning

## 1. Supported Endpoints
Compliant with RFC 7643 / RFC 7644:
- `GET /scim/v2/Users`: List & filter provisioned users.
- `POST /scim/v2/Users`: Provision new user.
- `PUT/PATCH /scim/v2/Users/{id}`: Modify attributes or deactivate.
- `GET /scim/v2/Groups`: List provisioned groups and member associations.
- `POST /scim/v2/Groups`: Provision groups and map to ZCoder enterprise roles.

## 2. Non-Destructive User Deactivation
Setting `"active": false` suspends the user's active session and prevents new job submissions while preserving historical audit records and job lineage.
