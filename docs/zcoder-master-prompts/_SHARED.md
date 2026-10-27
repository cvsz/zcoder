# Shared rules (apply to every cycle prompt)

1. Language: code, comments, identifiers, docs, commit text in English.
2. Facts in each prompt are CLAIMS dated 2026-10-25 from platform.claude.com release notes. Before coding, re-verify each one you touch against the live docs and record any drift in the cycle's upgrade note. Never implement from memory.
3. Methodology (existing, keep): dual grep before confirming a gap; strike through false positives instead of deleting them; new behavior is opt-in with `None` defaults; document what was intentionally excluded and why.
4. Scope: one bounded slice per cycle. Do not widen scope, do not "fix everything".
5. Preserve every existing gate: tests, lint, security checks, version-sync, local-only push default.
6. Verification: run the full test suite and lint on touched files. Report counts exactly. Report failures that pre-exist separately (prove with a stash/baseline run). Never claim 100%; list what is verified and what is not.
7. Cross-file docs each cycle: CHANGELOG, ROADMAP, CHECKLIST, IMPLEMENTATION_CHECKLIST, README, pyproject version, a versioned docs/ upgrade note, and the next cycle's prompt file.
8. Deliverables: patch + full-source zip + short report. STOP there.
9. Never commit, push, approve, or merge. Never switch accounts or self-approve. A human performs GPG commit, push, independent review and merge.
10. Never fabricate completed work, test results, API behavior, prices, or model IDs. If a fact cannot be verified, mark it UNVERIFIED in code comments and docs.
11. Secrets: never write keys, tokens, or credentials into code, tests, logs, or docs.
