# v1.38.0 — Claude Enterprise User Management API, plus a wiring gap this cycle found in itself

## What shipped

Re-fetched Anthropic's release notes and found a genuine, previously
unimplemented feature: the Claude Enterprise (claude.ai) User Management
API, beta since July 14, 2026. Confirmed absent before this cycle — a
grep for `ce-user-management|rbac_group|rbac_role` across the whole tree
came back empty.

Added full client + CLI coverage in `claude_admin_api.py`:

- **Members** — `list_members`/`get_member`/`update_member_role`/
  `remove_member`. Same `/organizations/users` paths Console orgs
  already use; no beta header.
- **Invites** — `create_invite`/`list_invites`/`get_invite`/
  `withdraw_invite`, with optional `rbac_group_ids` on creation so a
  new member can land in a group on acceptance instead of a separate
  follow-up call. Same no-beta-header `/organizations/invites` paths.
- **Groups** — `list_groups`/`get_group`/`create_group`/`rename_group`/
  `delete_group`/`list_group_members`/`add_group_member`/
  `remove_group_member`, all under `/rbac_groups`, requiring the new
  `ce-user-management-2026-07-13` beta header.
- **Custom Roles** — `list_roles`/`get_role`/`list_role_permissions`,
  read-only (`/rbac_roles`), same beta header. Roles themselves are
  created/edited in claude.ai org settings only, not through the API.

19 new `AdminApiClient` methods, 15 new `cmd_*` functions, 30 new tests
in `tests/test_claude_admin_api.py` (14 pre-existing + 30 new = 44 total
in that file).

## The gap this cycle found in its own work

The client and `cmd_*` layer landed correctly, but none of it was ever
given CLI flags in `main.py` — the same class of miss that motivated
`tests/test_cli_wiring.py` back in v1.31.0. That test is parametrized
over every `claude_*.py` module, so `claude_admin_api.py` should have
caught this automatically; it didn't, because the wiring pass and the
test run happened before the CE User Management commit landed, and the
version bump, `CHANGELOG.md` entry, and this writeup were never done as
part of the same commit — so the module sat fully implemented and fully
tested at the function level, but unreachable from the CLI, with the
README already describing a `v1.38.0` that didn't otherwise exist:
`main.py`'s `VERSION` and `pyproject.toml` still read `1.37.0`, and the
doc this file replaces was a dangling reference.

Fixed this cycle:

- Added a new argparse group, "Claude Enterprise User Management
  (v1.38.0, beta)", with 15 command flags (`--members-list`,
  `--member-get`, `--member-role-set`, `--member-remove`,
  `--invite-create`, `--invites-list`, `--invite-withdraw`,
  `--groups-list`, `--group-create`, `--group-delete`,
  `--group-members-list`, `--group-member-add`,
  `--group-member-remove`, `--roles-list`, `--role-permissions`) plus
  two modifier flags (`--members-email`, `--invite-rbac-groups`), and a
  dispatch block that requires `--admin-api-key`/`ANTHROPIC_ADMIN_API_KEY`
  the same way the existing Admin API commands do.
- `tests/test_cli_wiring.py`'s parametrized sweep now passes for
  `claude_admin_api.py` (previously failed on
  `cmd_members_list` first, since `_cmd_functions()` returns them in
  source order). Added 7 targeted tests: flag parsing for
  `--members-list`/`--members-email`, `--member-role-set`,
  `--invite-create` with `--invite-rbac-groups`, `--group-member-add`,
  `--roles-list`/`--role-permissions`, the missing-admin-key error path,
  and one end-to-end dispatch test (`--members-list` reaches
  `cmd_members_list` with the right arguments).
- Bumped `main.py`'s `VERSION` and `pyproject.toml`'s `version` to
  `1.38.0` to match what the README already claimed.
- Added the `CHANGELOG.md` entry this doc is linked from.

## What was checked and found to be non-issues

Re-confirmed as already correctly implemented rather than re-asserted:
mid-conversation tool changes on Opus 5, server-side fallback
`"default"` mode, API key `expires_at`, the `agent-memory-2026-07-22`
header, and the Opus 4.7 fast-mode removal.

## Test suite

488 passing after this cycle (test_tui.py's asyncio-marker collection
issue and test_webapp_server.py's fastapi dependency are pre-existing
environment gaps unrelated to this change, not new failures).
