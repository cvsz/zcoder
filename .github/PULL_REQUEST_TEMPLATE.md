## Summary

Describe the bounded change and why it is needed.

## Scope

- [ ] One bounded vertical slice only
- [ ] No unrelated refactor or broad rewrite
- [ ] Backward-compatibility impact documented

## Validation

- [ ] Ruff
- [ ] Black
 - [ ] Python 3.10
 - [ ] Python 3.11
 - [ ] Python 3.12
- [ ] Bandit / security
- [ ] Docker build/smoke where applicable
- [ ] CodeQL
- [ ] Dependency Review
- [ ] Release Gate
- [ ] Helm
- [ ] SDK / TypeScript

## Security review

- [ ] Trust boundaries reviewed
- [ ] User/model-controlled source-to-sink paths reviewed
- [ ] Filesystem/network/permission/secret impacts reviewed
- [ ] No tests, coverage thresholds, permissions, or security gates weakened
- [ ] No production data or third parties used for security validation

## Operations / release

- [ ] Configuration or migration impact documented
- [ ] Rollback path documented when behavior/storage/config changed
- [ ] Observability/audit impact considered
- [ ] Exact final head must be green before merge

## Documentation

- [ ] README / SECURITY / ARCHITECTURE / exec-planning / CHANGELOG updated where applicable

## Notes for reviewers

Call out the highest-risk assumption, unresolved blocker, or follow-up slice. Do not merge while hosted verification is pending or red.
