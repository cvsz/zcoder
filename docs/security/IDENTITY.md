# ZCoder Secrets Management & Identity Provider (OIDC) Integration

## OIDC Authentication Flow
1. Users authenticate via external OpenID Connect identity provider (Okta, Keycloak, Google Workspace, Azure AD, Auth0).
2. The incoming JWT bearer token is validated server-side by `auth_oidc.OidcValidator`:
   - Cryptographic signature verified against JWKS endpoint.
   - Standard claims validated: `iss` (issuer), `aud` (audience), `exp` (expiration), `nbf` (not before).
3. The user's role is extracted from JWT claims and mapped to `VIEWER`, `OPERATOR`, or `ADMIN`.
4. Role permissions are enforced server-side by `auth_oidc.RbacPolicy` for every operation (mutations require `OPERATOR`+, admin tasks require `ADMIN`).

## Secret Rotation Policy
- **Database Credentials**: Managed via Kubernetes Secret reference or External Secrets Operator (Vault / AWS Secrets Manager). Applications use connection pool with auto-reconnect upon credential update.
- **GitHub App Private Key**: Loaded via file mount or environment variable reference; rotated by uploading new PEM to secret store.
- **Anthropic API Key**: Injected via secret reference `ANTHROPIC_API_KEY`.
- **Break-Glass Admin**: Configured via `ZCODER_BREAK_GLASS_SECRET` with mandatory structured audit logging on every activation.
