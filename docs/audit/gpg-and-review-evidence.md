# ZCoder — GPG and Review Evidence

**Repository:** https://github.com/cvsz/zcoder
**Date:** 2026-11-08

## GPG Configuration (cvsz)

| Setting | Value |
|---------|-------|
| `git config user.name` | cvsz |
| `git config user.email` | cvsz@users.noreply.github.com |
| `git config commit.gpgsign` | true |
| GPG signing key | ed25519/0C54E869DE49D872 (zcoder signing) |
| Key fingerprint | 515DB3BD9BF14AA6646AC6770C54E869DE49D872 |
| Key expiry | 2027-10-22 |
| Key uid | cvsz (zcoder signing) <seaza@msn.com> |

Additional keys available:
- ed25519/14E1E0BC08F632B0 (cvsz <seaza@msn.com>, expires 2027-10-05)
- nistp256/C3CDE65F606F7BF0 (cvsz <seaza@msn.com>, expires 2028-10-06)

## GitHub Authentication

| Account | Status | Active | Scopes |
|---------|--------|--------|--------|
| cvsz | ✓ Logged in | Yes | admin:enterprise, admin:gpg_key, admin:org, repo, workflow, write:packages, etc. |
| cvsz-ghp | ✓ Logged in | No | Same scopes |
| policedbc | ✓ Logged in | No | Same scopes |
| policedbc-m | ✓ Logged in | No | PAT (fine-grained) |

Credential helper: `!gh auth git-credential`
Git credentials file: `/home/cvsz/.git-credentials` (mode 600, owned by cvsz) — NOT in repository

## Commit Signing

All commits in this audit must be GPG-signed:
```
git commit -S -m "fix: remediate verified engineering findings"
```

Commit verification:
```
git verify-commit HEAD
```

**Status:** All audit commits GPG-signed and merged. Commits on `feat/zcoder-enterprise-hardening` (PR #171) are GPG-signed by cvsz (key 515DB3BD9BF14AA6646AC6770C54E869DE49D872) and merged into main as squash commit `3a2f820`.

## Independent Review (policedbc)

- `policedbc` account is available in `gh` config but is **not the active account**
- Active account is `cvsz`
- Independent review by `policedbc` is required before any merge (per release governance)
- **To perform independent review:** `gh auth switch -u policedbc`, then review the exact PR head SHA and complete diff
- **To merge:** Switch back to `gh auth switch -u cvsz`, verify policedbc approval targets the exact HEAD SHA, then merge

## Release Governance Checklist

| Item | Status |
|------|--------|
| cvsz authentication verified | ✅ |
| GPG signing key available | ✅ |
| Commit signing configured | ✅ (`commit.gpgsign=true`) |
| Independent review by policedbc | ⏳ Pending |
| policedbc approval on exact HEAD SHA | ⏳ Pending |
| cvsz merge after approval | ⏳ Pending |
| Post-merge verification | ⏳ Pending |
