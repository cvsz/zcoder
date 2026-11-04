# Model catalog migration to v1.60.0

## Source review

The supplied `/home/cvsz/zcoder-v1.60.0.zip` contains 306 files. Its
`docs/55_upgrade_v1.60.0_model_catalog_5_5.md` explicitly says the archive
uses a separate flat-tree lineage and that only model-catalog changes were
ported between that lineage and the modular repository. The archive members
were extracted under `/home/cvsz/zcoder-v1.60.0/`; all 306 archived files
matched their ZIP members byte-for-byte.

The archive proposed four model IDs and upgrade targets. Current model
context, output limits, default effort, and public list prices were checked
against Anthropic's official model overview and model-specific pages on
2026-10-26. This is metadata only; ZCoder local inference remains routed to
loopback model endpoints, and this work did not make an Anthropic API call.

References: [official model overview](https://platform.claude.com/docs/en/models/overview),
[Fable 5.1 overview](https://platform.claude.com/docs/en/models/fable-5-1/overview),
and [Haiku 5.5 overview](https://platform.claude.com/docs/en/models/haiku-5-5/overview).
The Docker build tool was updated after the [uv 0.13.5 release](https://github.com/astral-sh/uv/releases/tag/0.13.5)
addressed the [compromised root certificate advisory](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62).

## Changes

- Added catalog entries and `--upgrade-target` choices for Fable 5.1, Opus
  5.5, Sonnet 5.5, and Haiku 5.5.
- Extended local-only outbound enforcement to all hosted model API domains
  currently configured in the repository, including Voyage embeddings; local
  mode still permits unrelated GitHub integrations.
- Marked superseded Fable 5, Opus 5, Sonnet 5, Opus 4.8, and Haiku 4.5 rows
  as `legacy`, retaining their metadata for existing configurations.
- Recorded Haiku 5.5's two input-size pricing tiers. Its legacy scalar
  `price_in` and `price_out` fields represent rates through 100k input tokens;
  callers must read `pricing_tiers` for higher input sizes.
- Did not extend fast-mode, service-tier, inference-geo, computer-use, or
  model-specific API modules; those capabilities are independently gated and
  were not established by the source archive.

## Validation

Validation on the current worktree:

- Full PostgreSQL-backed suite: `1637 passed` using `zcoder_db` on PostgreSQL
  16.15.
- Focused catalog/version/local-model suites: `22 passed`; the catalog suite
  was rerun after adding the CLI dry-run preview case: `5 passed`.
- Local-only provider policy, local model integrations, and live local CLI
  tests: `26 passed`, including pre-network blocking of Anthropic, Voyage,
  Gemini, xAI, Groq, OpenRouter, Cerebras, and OpenAI API endpoints.
- `ruff check .`: passed; `black --check .`: passed (345 files);
  `mypy src/zcoder`: passed (168 source files).
- `/tmp/zcoder-uv-0.13.5 lock --check`: passed. `pip-audit` against the
  locked runtime requirements and all locked groups/extras found no known
  vulnerabilities. Bandit and actionlint passed.
- Wheel `zcoder-1.60.0-py3-none-any.whl` built and passed ZIP integrity and
  metadata checks. Installing it into an isolated target and running the CLI
  printed `ZCoder CLI v1.60.0`; an import check confirmed the packaged
  local-only guard rejects Voyage API access.
- Docker image `zcoder:1.60.0-audit` built with `uv sync --locked`; running
  its CLI with `ZCODER_LOCAL_MODE=1` printed `ZCoder CLI v1.60.0`.

## Release and GitHub state

The repository release gate still reports `NOT QUALIFIED` with
`VERSION_INTEGRITY`, `TEST_ACCOUNTING`, `PITR`, `SECURITY`, and `FINAL` as
`UNKNOWN`; evidence has not been imported for this uncommitted candidate.
GitHub `main` protection currently requires 18 strict status checks. The
latest visible completed workflow runs are attached to older commits, not
this worktree. Repository Actions variables and secrets are empty, including
the `ZCODER_PITR_EVIDENCE_JSON` input required to qualify production PITR.
That value requires real recovery evidence and was not fabricated. Therefore
no commit, push, approval, merge, or deployment was made.

These checks do not establish real local-model inference, hosted CI, or
production qualification. The repository-wide release gate remains the
authoritative source for those outstanding criteria.
