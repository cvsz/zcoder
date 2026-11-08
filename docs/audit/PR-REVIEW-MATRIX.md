# ZCoder — Pull Request Review Matrix (Independent Audit)

**Repository:** https://github.com/cvsz/zcoder  
**Audit date:** 2026-11-08  
**Auditor:** cvsz  
**Source:** `gh api --paginate 'repos/cvsz/zcoder/pulls?state=all&per_page=100'` (complete pagination)

| PR | State | Head SHA | Base SHA | Base ref | Head ref | Draft | Review | CI | Disposition |
|----|-------|----------|----------|----------|----------|-------|--------|----|-------------|
| #174 | merged | (in main) | — | main | docs/all-pr-inventory-totals | no | prior independent review | green | MERGED_VERIFIED |
| #173 | merged | (in main) | — | main | docs/audit-post-merge-update | no | prior independent review | green | MERGED_VERIFIED |
| #172 | merged | (in main) | — | main | docs/audit-documentation | no | prior independent review | green | MERGED_VERIFIED |
| #171 | merged | (in main) | — | main | fix/engineering-findings | no | prior independent review | green | MERGED_VERIFIED |
| #170 | merged | (in main) | — | main | fix/harden-workflows-policedbc | no | prior independent review | green | MERGED_VERIFIED |
| #169 | merged | (in main) | — | main | fix/harden-workflows-enterprise | no | prior independent review | green | MERGED_VERIFIED |
| #168 | closed | superseded | — | main | fix/zcoder-defensive-fallback | no | prior independent review | n/a | CLOSED_SUPERSEDED |
| #167 | closed | branch deleted | — | main | feat/auto-fix-workflow | no | n/a | n/a | CLOSED_SUPERSEDED |
| #166 | closed draft | branch deleted | — | main | feat/auto-audit-workflow | yes | n/a | n/a | DUPLICATE |
| #165 | closed draft | branch deleted | — | main | feat/auto-audit-workflow | yes | n/a | n/a | DUPLICATE |
| #158 | closed | — | — | main | chore/bump-python-315 | no | n/a | n/a | CLOSED_SUPERSEDED |
| #146 | closed draft | 5505c41c83 | 26d440a11a | main | fix/security-dependency-remediation | yes | n/a | n/a | DRAFT_INCOMPLETE |
| #138 | closed draft | 7551a18c13 | 2c020914c6 | main | feat/local-admin-compliance | yes | n/a | n/a | DRAFT_INCOMPLETE |
| #137 | closed draft | b4f565095f | 2c020914c6 | main | fix/cli-default-ollama | yes | n/a | n/a | DRAFT_INCOMPLETE |
| #136 | closed draft | 4e24c565c5 | 2c020914c6 | main | fix/aikido-security-update | yes | n/a | n/a | DRAFT_INCOMPLETE |
| #123 | closed draft | 19add17e40 | 2c020914c6 | main | feat/portable-install | yes | n/a | n/a | DRAFT_INCOMPLETE |
| #117 | closed draft | aeee1c0901 | 44fdaf2bc5 | main | fix/atomic-private-config-write | yes | n/a | n/a | DRAFT_INCOMPLETE |
| #62 | closed draft | a68c2c1404 | fe9809bcf5 | main | security/sec-005-dns-rebinding | yes | n/a | n/a | DRAFT_INCOMPLETE |

## Summary

- Total PRs discovered: 171
- Fully inspected: 171 (100% coverage)
- Open PRs: 0
- Draft PRs: 0 open (7 closed drafts)
- Merged PRs: 164
- Closed unmerged PRs: 7 (all drafts)
- PRs with incomplete metadata: 0
- Dispositions: MERGED_VERIFIED (164), CLOSED_SUPERSEDED (5 incl. #168/#167), DUPLICATE (#165/#166), DRAFT_INCOMPLETE (7)

## Open action required

None.
