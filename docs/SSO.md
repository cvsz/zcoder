# ZCoder Enterprise Single Sign-On (SSO / OIDC)

## 1. Multi-Tenant OIDC Configuration
Each organization can configure its own Identity Provider (IdP) independently:
- Verified OpenID Connect Discovery via standard `.well-known/openid-configuration`.
- SSRF-protected endpoint validation.
- Cryptographic JWT signature verification with automatic JWKS key rotation.
- Domain claiming workflow preventing identity spoofing.

## 2. Claims Mapping
IdP tokens map to ZCoder `RequestContext`:
```json
{
  "sub": "user_9921",
  "email": "developer@enterprise.com",
  "org_id": "org_corp_1",
  "roles": ["Developer"]
}
```
