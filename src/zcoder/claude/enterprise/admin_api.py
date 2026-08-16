"""
claude_admin_api.py — Admin API: Usage & Cost, API keys, Spend Limits, Rate Limits, Claude Code Analytics, User Management
AI Model Coder CLI v1.38.0

Thin Admin API wrappers, combined into one module since all require the
same auth (an Admin API key, prefix sk-ant-admin..., created in the
Console — this is a different key type than the regular API key used
everywhere else in this CLI, and these calls will 401 with a normal key).

  1. Usage and Cost API — org-level historical spend/usage reporting.
     `claude_cost_optimizer.py` only ever *estimates* cost locally from
     token counts it's told about after the fact; it never calls a real
     usage/cost endpoint. This module is that missing live-data path —
     see claude_cost_optimizer.py's docstring for the cross-link the other
     direction.

  2. API key management — list/update organization API keys. Anthropic
     does not document a create-key endpoint: keys are created through
     the Console UI, where the secret is displayed exactly once, and
     that's intentional (creating a raw secret programmatically would be
     an exfiltration/security risk). So this module implements list,
     get, and update (e.g. changing status to revoke a key) — not create.
     `--admin-create-key` is deliberately not implemented; see
     cmd_admin_create_key() below for why, rather than silently no-op-ing.

  3. Spend Limits API (v1.23.0) — per-member spend governance. Claude
     Enterprise only; a Claude Console/API-only org gets a 403 from
     these endpoints. Eight endpoints across two resources: spend limits
     (list effective limits org-wide, set/get/delete a per-user
     override) and spend limit increase requests (list the queue,
     approve/deny a pending request). Requires an Admin API key with the
     read:spend_limits / write:spend_limits scopes.

  4. Rate Limits API (v1.23.0) — read-only. Two endpoints: the org's
     configured limits (grouped by model family, batches, files, skills,
     web search), and a workspace's overrides (each paired with the
     inherited org_limit). This is a different concern from
     resilience.py's client-side 429 backoff: that module *reacts* to
     being rate-limited; this one *reads what the configured limits
     are* before you ever hit them.

  5. Claude Enterprise User Management API (v1.38.0, beta) — Members,
     Invites, Groups, and read-only Custom Roles for a Claude Enterprise
     (claude.ai) organization. Member/invite endpoints are the same
     /organizations/{users,invites} paths section 2's API-key-management
     already uses for Claude Console orgs — no beta header needed there.
     Groups (/rbac_groups) and Custom Roles (/rbac_roles) are Enterprise-
     only and require the ce-user-management-2026-07-13 beta header;
     omitting it 404s rather than degrading. The API can only assign the
     "user"/"managed" roles — owner/membership_admin/primary_owner stay
     Console-managed, same as key creation in section 2 being N/A by
     design. Requires an Admin API key with read:members / write:members
     (members, invites) or read:rbac_groups / write:rbac_groups (groups);
     custom-role reads use read:members too.

CLI flags:
  --usage-report                 Print a usage report table (token counts)
  --usage-report-start DATE       Start date (YYYY-MM-DD), default: 30 days ago
  --usage-report-end DATE         End date (YYYY-MM-DD), default: today
  --usage-report-group-by FIELD   Group by field, e.g. model, api_key_id (default: model)
  --cost-report                   Print a cost report table (billed spend, not token counts)
  --cost-report-start DATE        Start date (YYYY-MM-DD), default: 30 days ago
  --cost-report-end DATE          End date (YYYY-MM-DD), default: today
  --cost-report-group-by FIELD    Group by field, e.g. model, api_key_id (default: model)
  --admin-list-keys               List organization API keys
  --admin-revoke-key ID           Revoke (set status=inactive) an API key by ID
  --admin-create-key NAME         Explains why this isn't supported (Console-only)
  --spend-limits-list             List every member's resolved effective spend limit
  --spend-limit-set USER_ID AMOUNT  Set a per-user spend limit override (decimal string, minor units)
  --spend-limit-get ID            Get one spend limit override by id
  --spend-limit-delete ID         Delete a per-user spend limit override
  --spend-limit-requests-list     List spend limit increase requests
  --spend-limit-status STATUS     Filter --spend-limit-requests-list by status (pending/approved/denied)
  --spend-limit-request-approve ID  Approve a pending increase request
  --spend-limit-request-deny ID   Deny a pending increase request
  --rate-limits                   Print the organization's configured rate limits
  --rate-limits-model MODEL       Filter --rate-limits to one model's group
  --rate-limits-workspace ID      Print one workspace's rate limit overrides (with inherited org_limit)
  --claude-code-usage-report      Print daily per-user Claude Code productivity metrics (v1.24.0)
  --claude-code-usage-report-start DATE  Date (YYYY-MM-DD) for --claude-code-usage-report, default: yesterday
  --members-list [--members-email E]     List/lookup organization members (Claude Enterprise)
  --member-get USER_ID                   Get one member by ID
  --member-role-set USER_ID ROLE         Set a member's role (user/managed)
  --member-remove USER_ID                Remove a member
  --invite-create EMAIL ROLE [--invite-rbac-groups G1,G2]  Invite someone (role: user/managed)
  --invites-list                         List organization invites
  --invite-withdraw INVITE_ID            Withdraw a pending invite
  --groups-list                          List the enterprise's groups (beta header)
  --group-create NAME                    Create a group
  --group-delete GROUP_ID                Delete a group
  --group-members-list GROUP_ID          List a group's members
  --group-member-add GROUP_ID USER_ID    Add an org member to a group
  --group-member-remove GROUP_ID USER_ID Remove a member from a group
  --roles-list                           List custom roles (read-only)
  --role-permissions-list ROLE_ID        List one custom role's permissions
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from resilience import safe_urlopen

ADMIN_BASE = "https://api.anthropic.com/v1/organizations"

# Claude Enterprise (claude.ai) User Management API (v1.38.0) — beta for all
# Claude Enterprise organizations. Per platform.claude.com/docs/en/manage-claude/
# user-management (checked 2026-07-27): member and invite endpoints are the
# *same* /v1/organizations/{users,invites} endpoints Claude Console orgs use
# (no beta header needed there — this file's existing API-key-management
# section above is exactly this for Console orgs). Group and custom-role
# endpoints (/rbac_groups, /rbac_roles) are Claude-Enterprise-only and require
# this beta header; omitting it on those returns 404, not a degraded response.
# Confirmed genuinely absent from this codebase before this cycle: grepped for
# "ce-user-management|rbac_group|rbac_role|list_members" — zero matches.
CE_USER_MANAGEMENT_BETA = "ce-user-management-2026-07-13"


class AdminApiError(Exception):
    pass


class AdminApiClient:
    """Thin client for the Admin API, following the same _post()/_get()
    pattern used throughout this project's claude_*.py modules.

    admin_api_key must be an Admin API key (sk-ant-admin...), not a
    regular API key — regular keys don't have access to this endpoint
    family and will get a 401/403.
    """

    def __init__(self, admin_api_key: str):
        self.admin_api_key = admin_api_key

    def _headers(self, beta: Optional[str] = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.admin_api_key,
            "anthropic-version": "2023-06-01",
        }
        if beta:
            headers["anthropic-beta"] = beta
        return headers

    def _get(self, path: str, params: Optional[dict] = None, beta: Optional[str] = None) -> dict:
        url = f"{ADMIN_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None},
                doseq=True,
            )
        req = urllib.request.Request(url, headers=self._headers(beta=beta), method="GET")
        try:
            with safe_urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": e.read().decode(), "status": e.code}
        except Exception as e:
            return {"error": str(e)}

    def _post(self, path: str, payload: dict, beta: Optional[str] = None) -> dict:
        req = urllib.request.Request(
            f"{ADMIN_BASE}{path}",
            data=json.dumps(payload).encode(),
            headers=self._headers(beta=beta),
            method="POST",
        )
        try:
            with safe_urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": e.read().decode(), "status": e.code}
        except Exception as e:
            return {"error": str(e)}

    def _delete(self, path: str, beta: Optional[str] = None) -> dict:
        req = urllib.request.Request(f"{ADMIN_BASE}{path}", headers=self._headers(beta=beta), method="DELETE")
        try:
            with safe_urlopen(req, timeout=60) as r:
                body = r.read().decode()
                return json.loads(body) if body else {"deleted": True}
        except urllib.error.HTTPError as e:
            return {"error": e.read().decode(), "status": e.code}
        except Exception as e:
            return {"error": str(e)}

    # ── Usage and Cost API ──────────────────────────────────────────────

    def get_usage_report(self, start: str, end: str, group_by: str = "model") -> dict:
        """Wraps the usage_report endpoint. start/end are YYYY-MM-DD."""
        return self._get(
            "/usage_report",
            params={
                "starting_at": start,
                "ending_at": end,
                "group_by": group_by,
            },
        )

    def get_cost_report(self, start: str, end: str, group_by: str = "model") -> dict:
        """Wraps the cost_report endpoint — actual billed spend, distinct
        from the token-count usage_report above."""
        return self._get(
            "/cost_report",
            params={
                "starting_at": start,
                "ending_at": end,
                "group_by": group_by,
            },
        )

    # ── CMEK external_keys (v1.25.0 — see note below) ─────────────────────
    #
    # ⚠️ Confirmation needed: the docs confirm "external_keys API
    # endpoints" exist and are Admin-API-scoped on Claude Platform
    # (explicitly called out as *unavailable* on Claude Platform on AWS),
    # but this session could not find or safely fetch the endpoint's
    # exact path, request body, or response schema. The path segment
    # below (/organizations/external_keys) is a best-effort guess by
    # analogy with every other resource in this file living under
    # /organizations/..., NOT a confirmed one. Verify against the live
    # API reference before using this against a production organization
    # — CMEK misconfiguration risk is asymmetric (see the "Revoking or
    # disabling the key makes all CMEK-protected data in that workspace
    # permanently inaccessible, with no backout path" warning in the
    # product docs), so treat these methods as a starting point to
    # correct, not a verified client.
    def create_external_key(self, workspace_id: str, provider: str, key_arn_or_id: str) -> dict:
        """Register a customer-managed encryption key (CMEK) for a
        workspace. `provider` is one of "aws_kms", "gcp_kms", or
        "azure_key_vault" per the product docs (Google Cloud KMS and
        Azure Key Vault are not available on Claude Platform on AWS —
        AWS KMS only there). Attaching a key to a workspace is
        irreversible: it cannot later be detached or swapped, and the
        workspace's data-retention setting locks in place."""
        return self._post(
            "/external_keys",
            {
                "workspace_id": workspace_id,
                "provider": provider,
                "key_arn_or_id": key_arn_or_id,
            },
        )

    def validate_external_key(self, key_id: str) -> dict:
        """Validate a registered key's permissions/purpose/algorithm
        before attaching it — mirrors the Console's "validate" step."""
        return self._post(f"/external_keys/{key_id}/validate", {})

    def attach_external_key(self, key_id: str, workspace_id: str) -> dict:
        """Attach a validated key to a workspace. Irreversible per the
        product docs: once attached, a key cannot be detached or
        swapped, and returning to zero data retention requires creating
        a new workspace and moving traffic to it."""
        return self._post(f"/external_keys/{key_id}/attach", {"workspace_id": workspace_id})

    def list_external_keys(self, workspace_id: Optional[str] = None) -> dict:
        """List registered CMEK keys, optionally filtered to one
        workspace."""
        params = {"workspace_id": workspace_id} if workspace_id else None
        return self._get("/external_keys", params=params)

    # ── Claude Code Analytics API (v1.24.0) ──────────────────────────────

    def get_claude_code_usage_report(
        self, starting_at: str, limit: int = 20, page: Optional[str] = None
    ) -> dict:
        """GET /organizations/usage_report/claude_code — one record per
        user per day: session counts, lines of code added/removed,
        commits/PRs created through Claude Code, per-editing-tool
        accept/reject counts, and a per-model token/cost breakdown. Same
        Admin API key as the org-wide Usage & Cost API above, but this is
        Claude-Code-specific and free to call regardless of plan.
        starting_at is required (YYYY-MM-DD); page is the cursor from a
        previous response's next_page for pagination."""
        return self._get(
            "/usage_report/claude_code",
            params={
                "starting_at": starting_at,
                "limit": limit,
                "page": page,
            },
        )

    # ── API key management ──────────────────────────────────────────────

    def list_api_keys(self, limit: int = 20) -> dict:
        return self._get("/api_keys", params={"limit": limit})

    def get_api_key(self, key_id: str) -> dict:
        return self._get(f"/api_keys/{key_id}")

    def update_api_key(self, key_id: str, status: Optional[str] = None, name: Optional[str] = None) -> dict:
        """status: 'active' or 'inactive'. There is no documented delete
        endpoint either — revocation is done via status, not deletion."""
        payload = {}
        if status:
            payload["status"] = status
        if name:
            payload["name"] = name
        return self._post(f"/api_keys/{key_id}", payload)

    def revoke_api_key(self, key_id: str) -> dict:
        return self.update_api_key(key_id, status="inactive")

    # ── Spend Limits API (v1.23.0, Claude Enterprise only) ───────────────

    def list_effective_spend_limits(self, limit: int = 50, page: Optional[str] = None) -> dict:
        """Every current member with their resolved effective spend limit,
        where it's inherited from (source), and their period-to-date
        spend. GET /spend_limits/effective."""
        return self._get("/spend_limits/effective", params={"limit": limit, "page": page})

    def set_spend_limit(self, user_id: str, amount: str, suppress_notification: bool = False) -> dict:
        """Set a per-user spend limit override. `amount` is a decimal
        string in minor units (cents), per the API's convention.
        `suppress_notification` is only sent when True (omitted
        otherwise) — by default Anthropic emails the member."""
        payload = {"user_id": user_id, "amount": amount}
        if suppress_notification:
            payload["suppress_notification"] = True
        return self._post("/spend_limits", payload)

    def get_spend_limit(self, spend_limit_id: str) -> dict:
        return self._get(f"/spend_limits/{spend_limit_id}")

    def delete_spend_limit(self, spend_limit_id: str) -> dict:
        """Deletes a per-user override. Seat-tier, group, and
        organization-level rows cannot be deleted through this
        endpoint — only per-user overrides."""
        return self._delete(f"/spend_limits/{spend_limit_id}")

    def list_spend_limit_increase_requests(
        self,
        status: Optional[list] = None,
        actor_ids: Optional[list] = None,
        limit: int = 50,
        page: Optional[str] = None,
    ) -> dict:
        """List spend limit increase requests, most recent first. `status`
        filters by one or more of pending/approved/denied; `actor_ids`
        filters to specific requesters."""
        params = {"limit": limit, "page": page}
        if status:
            params["status[]"] = status
        if actor_ids:
            params["actor_ids[]"] = actor_ids
        return self._get("/spend_limit_increase_requests", params=params)

    def get_spend_limit_increase_request(self, request_id: str) -> dict:
        return self._get(f"/spend_limit_increase_requests/{request_id}")

    def approve_spend_limit_increase_request(
        self, request_id: str, suppress_notification: bool = False
    ) -> dict:
        """Approving writes the same per-user spend limit row that
        set_spend_limit() writes — this resolves the pending request AND
        sets the override in one call."""
        payload = {}
        if suppress_notification:
            payload["suppress_notification"] = True
        return self._post(f"/spend_limit_increase_requests/{request_id}/approve", payload)

    def deny_spend_limit_increase_request(self, request_id: str, suppress_notification: bool = False) -> dict:
        payload = {}
        if suppress_notification:
            payload["suppress_notification"] = True
        return self._post(f"/spend_limit_increase_requests/{request_id}/deny", payload)

    # ── Rate Limits API (v1.23.0, read-only) ─────────────────────────────

    def get_org_rate_limits(self, model: Optional[str] = None) -> dict:
        """The organization's configured rate limits, grouped by model
        family/batches/files/skills/web-search. `model`, when given,
        filters to the single group that model string belongs to (404 if
        it doesn't match any group) — omitted by default, returning every
        group."""
        params = {"model": model} if model else None
        return self._get("/rate_limits", params=params)

    def get_workspace_rate_limits(self, workspace_id: str) -> dict:
        """A single workspace's rate limit *overrides* only — anything
        missing is inherited from the organization, not unlimited. Each
        present limiter is paired with the organization's value
        (org_limit) for the same limiter."""
        return self._get(f"/workspaces/{workspace_id}/rate_limits")

    # ── Claude Enterprise User Management API (v1.38.0, beta) ────────────
    #
    # Members and invites take no beta header (same endpoints Console orgs
    # already use above). Groups and custom roles require
    # CE_USER_MANAGEMENT_BETA and exist only for Claude Enterprise. The API
    # can only assign the "user"/"managed" roles — owner/membership_admin/
    # primary_owner are Console-managed and out of scope by design, same as
    # --admin-create-key above being N/A by design.

    def list_members(
        self,
        limit: int = 20,
        email: Optional[str] = None,
        before_id: Optional[str] = None,
        after_id: Optional[str] = None,
    ) -> dict:
        """GET /organizations/users. `email` filters to one member
        (case-insensitive, tolerates common address variants per the
        docs) instead of paging the whole roster."""
        return self._get(
            "/users",
            params={
                "limit": limit,
                "email": email,
                "before_id": before_id,
                "after_id": after_id,
            },
        )

    def get_member(self, user_id: str) -> dict:
        return self._get(f"/users/{user_id}")

    def update_member_role(self, user_id: str, role: str) -> dict:
        """role must be "user" or "managed" — administrative roles
        (owner/membership_admin/primary_owner) 400 here by design, same
        restriction the docs describe for invite creation below."""
        return self._post(f"/users/{user_id}", {"role": role})

    def remove_member(self, user_id: str) -> dict:
        return self._delete(f"/users/{user_id}")

    def create_invite(self, email: str, role: str, rbac_group_ids: Optional[list] = None) -> dict:
        """role must be "user" or "managed". `rbac_group_ids`, when
        given, additionally requires the caller's key to carry
        write:rbac_groups (group assignment can grant that group's
        role permissions) — the API enforces this, not this client."""
        payload = {"email": email, "role": role}
        if rbac_group_ids:
            payload["rbac_group_ids"] = rbac_group_ids
        return self._post("/invites", payload)

    def list_invites(
        self, limit: int = 20, before_id: Optional[str] = None, after_id: Optional[str] = None
    ) -> dict:
        """No status filter — the response mixes pending/accepted/expired;
        filter client-side on `status` if you only want one state."""
        return self._get(
            "/invites",
            params={
                "limit": limit,
                "before_id": before_id,
                "after_id": after_id,
            },
        )

    def get_invite(self, invite_id: str) -> dict:
        return self._get(f"/invites/{invite_id}")

    def withdraw_invite(self, invite_id: str) -> dict:
        """Only a pending invite can be withdrawn — accepted/expired
        both 400 per the docs; this client doesn't pre-check status,
        the API is the source of truth."""
        return self._delete(f"/invites/{invite_id}")

    def list_groups(self, limit: int = 20, page: Optional[str] = None) -> dict:
        return self._get("/rbac_groups", params={"limit": limit, "page": page}, beta=CE_USER_MANAGEMENT_BETA)

    def get_group(self, group_id: str) -> dict:
        return self._get(f"/rbac_groups/{group_id}", beta=CE_USER_MANAGEMENT_BETA)

    def create_group(self, name: str) -> dict:
        return self._post("/rbac_groups", {"name": name}, beta=CE_USER_MANAGEMENT_BETA)

    def rename_group(self, group_id: str, name: str) -> dict:
        """`name` is the only field this endpoint can change."""
        return self._post(f"/rbac_groups/{group_id}", {"name": name}, beta=CE_USER_MANAGEMENT_BETA)

    def delete_group(self, group_id: str) -> dict:
        """Members keep their organization membership; they just lose
        the permissions the group's attached roles granted."""
        return self._delete(f"/rbac_groups/{group_id}", beta=CE_USER_MANAGEMENT_BETA)

    def list_group_members(self, group_id: str, limit: int = 100, page: Optional[str] = None) -> dict:
        return self._get(
            f"/rbac_groups/{group_id}/members",
            params={"limit": limit, "page": page},
            beta=CE_USER_MANAGEMENT_BETA,
        )

    def add_group_member(self, group_id: str, user_id: str) -> dict:
        """The user must already be an organization member (404
        otherwise). To assign groups to someone who hasn't joined yet,
        use rbac_group_ids on create_invite() instead."""
        return self._post(
            f"/rbac_groups/{group_id}/members", {"user_id": user_id}, beta=CE_USER_MANAGEMENT_BETA
        )

    def remove_group_member(self, group_id: str, user_id: str) -> dict:
        return self._delete(f"/rbac_groups/{group_id}/members/{user_id}", beta=CE_USER_MANAGEMENT_BETA)

    def list_roles(self, limit: int = 20, page: Optional[str] = None) -> dict:
        """Custom roles are read-only through the API — defined in
        claude.ai organization settings, not writable here."""
        return self._get("/rbac_roles", params={"limit": limit, "page": page}, beta=CE_USER_MANAGEMENT_BETA)

    def get_role(self, role_id: str) -> dict:
        return self._get(f"/rbac_roles/{role_id}", beta=CE_USER_MANAGEMENT_BETA)

    def list_role_permissions(self, role_id: str, limit: int = 20, page: Optional[str] = None) -> dict:
        return self._get(
            f"/rbac_roles/{role_id}/permissions",
            params={"limit": limit, "page": page},
            beta=CE_USER_MANAGEMENT_BETA,
        )


def _default_date_range() -> tuple:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=30)
    return start.isoformat(), end.isoformat()


def cmd_usage_report(
    admin_api_key: str, start: Optional[str] = None, end: Optional[str] = None, group_by: str = "model"
):
    default_start, default_end = _default_date_range()
    start = start or default_start
    end = end or default_end
    client = AdminApiClient(admin_api_key)
    data = client.get_usage_report(start, end, group_by=group_by)
    if "error" in data:
        print(f"\033[91m✗ Usage report failed: {data['error']}\033[0m")
        if data.get("status") in (401, 403):
            print(
                "\033[93m  This endpoint requires an Admin API key (sk-ant-admin...), "
                "not a regular API key.\033[0m"
            )
        return None

    print(f"\n\033[94mUsage report — {start} to {end} (grouped by {group_by})\033[0m\n")
    rows = data.get("data", data.get("results", []))
    if not rows:
        print("  (no usage data returned for this range)")
    for row in rows:
        label = row.get(group_by, row.get("model", "?"))
        input_tok = row.get("input_tokens", row.get("uncached_input_tokens", "?"))
        output_tok = row.get("output_tokens", "?")
        print(f"  {label:<28} in={input_tok:<12} out={output_tok}")
    print()
    return data


def cmd_cost_report(
    admin_api_key: str, start: Optional[str] = None, end: Optional[str] = None, group_by: str = "model"
):
    """--cost-report: actual billed spend (cost_report), distinct from
    the token-count-based --usage-report above. Mirrors cmd_usage_report
    one-for-one; get_cost_report() already existed on AdminApiClient but
    had no CLI flag wired to it until now."""
    default_start, default_end = _default_date_range()
    start = start or default_start
    end = end or default_end
    client = AdminApiClient(admin_api_key)
    data = client.get_cost_report(start, end, group_by=group_by)
    if "error" in data:
        print(f"\033[91m✗ Cost report failed: {data['error']}\033[0m")
        if data.get("status") in (401, 403):
            print(
                "\033[93m  This endpoint requires an Admin API key (sk-ant-admin...), "
                "not a regular API key.\033[0m"
            )
        return None

    print(f"\n\033[94mCost report — {start} to {end} (grouped by {group_by})\033[0m\n")
    rows = data.get("data", data.get("results", []))
    if not rows:
        print("  (no cost data returned for this range)")
    for row in rows:
        label = row.get(group_by, row.get("model", "?"))
        amount = row.get("amount", row.get("cost", "?"))
        currency = row.get("currency", "usd")
        print(f"  {label:<28} {amount} {currency}")
    print()
    return data


def cmd_cmek_list(admin_api_key: str, workspace_id: Optional[str] = None):
    """--cmek-list: list registered CMEK external keys.

    ⚠️ See the "CMEK external_keys" section of AdminApiClient — the
    exact endpoint shape used here is a best-effort guess pending
    confirmation against the live API reference, not a verified client.
    """
    client = AdminApiClient(admin_api_key)
    data = client.list_external_keys(workspace_id=workspace_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to list CMEK keys: {data['error']}\033[0m")
        if data.get("status") in (401, 403):
            print(
                "\033[93m  This endpoint requires an Admin API key (sk-ant-admin...), "
                "not a regular API key.\033[0m"
            )
        return None

    print(
        "\n\033[94mCMEK external keys\033[0m  "
        "\033[93m(unverified endpoint shape — see docs/37_upgrade_v1.25.0_audit_and_impl.md)\033[0m\n"
    )
    for k in data.get("data", []):
        print(
            f"  {k.get('id', '?')}  workspace={k.get('workspace_id', '?')}  "
            f"provider={k.get('provider', '?')}  status={k.get('status', '?')}"
        )
    print()
    return data


def cmd_claude_code_usage_report(admin_api_key: str, starting_at: str, limit: int = 20):
    """--claude-code-usage-report: daily, per-user Claude Code productivity
    metrics (sessions, lines of code, commits/PRs, per-model cost) — a
    dedicated report distinct from the org-wide --usage-report/--cost-report
    above, though it shares the same Admin API key and client class."""
    client = AdminApiClient(admin_api_key)
    data = client.get_claude_code_usage_report(starting_at, limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Claude Code usage report failed: {data['error']}\033[0m")
        if data.get("status") in (401, 403):
            print(
                "\033[93m  This endpoint requires an Admin API key (sk-ant-admin...), "
                "not a regular API key.\033[0m"
            )
        return None

    print(f"\n\033[94mClaude Code usage report — {starting_at}\033[0m\n")
    rows = data.get("data", [])
    if not rows:
        print("  (no Claude Code activity for this date)")
    for row in rows:
        actor = row.get("user_actor") or row.get("api_actor") or {}
        # Avoid clear-text user email / API-key-name output.
        actor_label = actor.get("type") or ("user" if row.get("user_actor") else "api_key")
        core = row.get("core_metrics", {})
        num_sessions = core.get("num_sessions", "?")
        loc = core.get("lines_of_code", {})
        added = loc.get("added", "?")
        removed = loc.get("removed", "?")
        commits = core.get("commits_by_claude_code", "?")
        prs = core.get("pull_requests_by_claude_code", "?")
        cost_total = sum(
            mb.get("estimated_cost", {}).get("amount", 0) for mb in row.get("model_breakdown", []) or []
        )
        print(
            f"  {actor_label:<32} sessions={num_sessions:<4} "
            f"+{added}/-{removed}  commits={commits}  prs={prs}  "
            f"cost={cost_total}"
        )
    print()
    return data


def cmd_admin_list_keys(admin_api_key: str, limit: int = 20):
    client = AdminApiClient(admin_api_key)
    data = client.list_api_keys(limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Failed to list API keys: {data['error']}\033[0m")
        if data.get("status") in (401, 403):
            print(
                "\033[93m  This endpoint requires an Admin API key (sk-ant-admin...), "
                "not a regular API key.\033[0m"
            )
        return None

    print("\n\033[94mOrganization API keys\033[0m\n")
    for key in data.get("data", []):
        # expires_at (v1.24.0): the API surfaces this field now that the
        # Console lets a key be created with an expiration. Print a clear
        # placeholder instead of the literal string "None" when absent —
        # there's still no create-key API endpoint (expiration is set at
        # creation in the Console UI only), this is a read-only addition.
        expires_at = key.get("expires_at") or "never"
        print(
            f"  {key.get('id', '?')}  {key.get('name', '')}  "
            f"status={key.get('status', '?')}  expires={expires_at}"
        )
    print()
    return data


def cmd_admin_revoke_key(admin_api_key: str, key_id: str):
    client = AdminApiClient(admin_api_key)
    data = client.revoke_api_key(key_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to revoke key {key_id}: {data['error']}\033[0m")
        return None
    print(f"\033[92m✓ Key {key_id} set to inactive\033[0m")
    return data


def cmd_admin_create_key(name: str):
    """--admin-create-key deliberately does not call an API — there is no
    documented create-key endpoint. Anthropic API keys are generated
    through the Console UI, where the secret is displayed exactly once;
    creating them programmatically isn't supported, almost certainly so a
    raw secret is never returned to a script that could log or leak it.
    This prints that explanation instead of silently failing or faking
    a response."""
    print(
        f"\033[93mℹ Can't create API key {name!r} via the Admin API — there is no "
        "documented create-key endpoint.\033[0m"
    )
    print(
        "  API keys are generated through the Console UI (a secret is shown once, "
        "on purpose). Use --admin-list-keys / --admin-revoke-key for the parts of "
        "key management that are actually supported programmatically."
    )
    return None


def _wrong_key_hint(data: dict, extra: str = ""):
    if data.get("status") in (401, 403):
        print(
            f"\033[93m  This endpoint requires an Admin API key (sk-ant-admin...), "
            f"not a regular API key.{' ' + extra if extra else ''}\033[0m"
        )


# ── Spend Limits API (v1.23.0, Claude Enterprise only) ──────────────────


def cmd_spend_limits_list(admin_api_key: str, limit: int = 50):
    client = AdminApiClient(admin_api_key)
    data = client.list_effective_spend_limits(limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Failed to list spend limits: {data['error']}\033[0m")
        _wrong_key_hint(data, "This API also requires a Claude Enterprise organization.")
        return None

    print("\n\033[94mEffective spend limits\033[0m\n")
    for row in data.get("data", []):
        user = row.get("user_id", "?")
        amount = row.get("amount", "?")
        source = row.get("source", "?")
        spent = row.get("period_to_date_spend", "?")
        print(f"  {user:<28} limit={amount:<12} source={source:<12} spent={spent}")
    print()
    return data


def cmd_spend_limit_set(user_id: str, amount: str, admin_api_key: str, suppress_notification: bool = False):
    client = AdminApiClient(admin_api_key)
    data = client.set_spend_limit(user_id, amount, suppress_notification=suppress_notification)
    if "error" in data:
        print(f"\033[91m✗ Failed to set spend limit: {data['error']}\033[0m")
        _wrong_key_hint(data)
        return None
    print(f"\033[92m✓ spend limit set\033[0m  user_id={user_id}  amount={amount}")
    return data


def cmd_spend_limit_get(spend_limit_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.get_spend_limit(spend_limit_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to get spend limit {spend_limit_id}: {data['error']}\033[0m")
        return None
    print(f"  {data}")
    return data


def cmd_spend_limit_delete(spend_limit_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.delete_spend_limit(spend_limit_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to delete spend limit {spend_limit_id}: {data['error']}\033[0m")
        return None
    print(f"\033[92m✓ spend limit {spend_limit_id} deleted\033[0m")
    return data


def cmd_spend_limit_requests_list(admin_api_key: str, status: Optional[str] = None):
    client = AdminApiClient(admin_api_key)
    status_filter = [status] if status else None
    data = client.list_spend_limit_increase_requests(status=status_filter)
    if "error" in data:
        print(f"\033[91m✗ Failed to list spend limit increase requests: {data['error']}\033[0m")
        _wrong_key_hint(data, "This API also requires a Claude Enterprise organization.")
        return None

    print("\n\033[94mSpend limit increase requests\033[0m\n")
    for row in data.get("data", []):
        print(
            f"  {row.get('id', '?')}  user={row.get('actor', {}).get('user_id', '?')}  "
            f"status={row.get('status', '?')}  requested={row.get('requested_amount', '?')}"
        )
    print()
    return data


def cmd_spend_limit_request_approve(request_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.approve_spend_limit_increase_request(request_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to approve request {request_id}: {data['error']}\033[0m")
        return None
    print(f"\033[92m✓ request {request_id} approved\033[0m")
    return data


def cmd_spend_limit_request_deny(request_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.deny_spend_limit_increase_request(request_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to deny request {request_id}: {data['error']}\033[0m")
        return None
    print(f"\033[92m✓ request {request_id} denied\033[0m")
    return data


# ── Rate Limits API (v1.23.0, read-only) ─────────────────────────────────


def cmd_rate_limits(admin_api_key: str, model: Optional[str] = None):
    client = AdminApiClient(admin_api_key)
    data = client.get_org_rate_limits(model=model)
    if "error" in data:
        print(f"\033[91m✗ Failed to get rate limits: {data['error']}\033[0m")
        _wrong_key_hint(data)
        return None

    print("\n\033[94mOrganization rate limits\033[0m" + (f" (model={model})" if model else "") + "\n")
    for group in data.get("data", data.get("rate_limits", [])):
        label = group.get("model_group", group.get("name", "?"))
        print(f"  {label}")
        for limiter in group.get("limits", []):
            print(f"    {limiter.get('type', '?'):<24} {limiter.get('value', '?')}")
    print()
    return data


def cmd_rate_limits_workspace(workspace_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.get_workspace_rate_limits(workspace_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to get rate limits for workspace {workspace_id}: " f"{data['error']}\033[0m")
        _wrong_key_hint(data)
        return None

    print(f"\n\033[94mWorkspace rate limit overrides — {workspace_id}\033[0m\n")
    groups = data.get("data", data.get("rate_limits", []))
    if not groups:
        print("  (no overrides — this workspace inherits every organization limit)")
    for group in groups:
        label = group.get("model_group", group.get("name", "?"))
        print(f"  {label}")
        for limiter in group.get("limits", []):
            print(
                f"    {limiter.get('type', '?'):<24} "
                f"value={limiter.get('value', '?'):<12} org_limit={limiter.get('org_limit', '?')}"
            )
    print()
    return data


# ── Claude Enterprise User Management API (v1.38.0, beta) ───────────────

_CE_HINT = "This API also requires a Claude Enterprise (claude.ai) organization."


def cmd_members_list(admin_api_key: str, limit: int = 20, email: Optional[str] = None):
    client = AdminApiClient(admin_api_key)
    data = client.list_members(limit=limit, email=email)
    if "error" in data:
        print(f"\033[91m✗ Failed to list members: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None

    print("\n\033[94mOrganization members\033[0m\n")
    rows = data.get("data", [])
    if not rows:
        print("  (no members found" + (f" matching {email}" if email else "") + ")")
    for m in rows:
        print(
            f"  {m.get('id', '?'):<28} {m.get('email', '?'):<32} "
            f"role={m.get('role', '?'):<16} added={m.get('added_at', '?')}"
        )
    if data.get("has_more"):
        print(f"  ... more available, last_id={data.get('last_id', '?')}")
    print()
    return data


def cmd_member_get(user_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.get_member(user_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to get member {user_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\n\033[94mMember {user_id}\033[0m")
    print(f"  email: {data.get('email', '?')}")
    print(f"  name:  {data.get('name', '?')}")
    print(f"  role:  {data.get('role', '?')}")
    print(f"  added: {data.get('added_at', '?')}\n")
    return data


def cmd_member_role_set(user_id: str, role: str, admin_api_key: str):
    """role must be "user" or "managed" — the API 400s on anything else,
    including the administrative roles, which can only be assigned in
    claude.ai organization settings."""
    client = AdminApiClient(admin_api_key)
    data = client.update_member_role(user_id, role)
    if "error" in data:
        print(f"\033[91m✗ Failed to update role for {user_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\033[92m✓ {user_id} role set to {data.get('role', role)}\033[0m")
    return data


def cmd_member_remove(user_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.remove_member(user_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to remove member {user_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\033[92m✓ Removed member {user_id}\033[0m (seat, if any, returned to the pool)")
    return data


def cmd_invite_create(email: str, role: str, admin_api_key: str, rbac_group_ids: Optional[list] = None):
    client = AdminApiClient(admin_api_key)
    data = client.create_invite(email, role, rbac_group_ids=rbac_group_ids)
    if "error" in data:
        print(f"\033[91m✗ Failed to invite {email}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(
        f"\033[92m✓ Invited {email} as {data.get('role', role)}\033[0m "
        f"(id={data.get('id', '?')}, expires={data.get('expires_at', '?')})"
    )
    return data


def cmd_invites_list(admin_api_key: str, limit: int = 20):
    client = AdminApiClient(admin_api_key)
    data = client.list_invites(limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Failed to list invites: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print("\n\033[94mOrganization invites\033[0m\n")
    rows = data.get("data", [])
    if not rows:
        print("  (no invites found)")
    for inv in rows:
        print(
            f"  {inv.get('id', '?'):<28} {inv.get('email', '?'):<32} "
            f"role={inv.get('role', '?'):<10} status={inv.get('status', '?')}"
        )
    print()
    return data


def cmd_invite_withdraw(invite_id: str, admin_api_key: str):
    """Only a pending invite can be withdrawn — accepted/expired both
    400 server-side."""
    client = AdminApiClient(admin_api_key)
    data = client.withdraw_invite(invite_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to withdraw invite {invite_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\033[92m✓ Withdrew invite {invite_id}\033[0m")
    return data


def cmd_groups_list(admin_api_key: str, limit: int = 20):
    client = AdminApiClient(admin_api_key)
    data = client.list_groups(limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Failed to list groups: {data['error']}\033[0m")
        if data.get("status") == 404:
            print(
                f"\033[93m  A 404 here usually means the {CE_USER_MANAGEMENT_BETA} beta "
                f"header wasn't accepted — confirm this is a Claude Enterprise "
                f"organization.\033[0m"
            )
        else:
            _wrong_key_hint(data, _CE_HINT)
        return None
    print("\n\033[94mEnterprise groups\033[0m\n")
    rows = data.get("data", [])
    if not rows:
        print("  (no groups found)")
    for g in rows:
        print(
            f"  {g.get('id', '?'):<32} {g.get('name', '?'):<24} "
            f"source={g.get('source_type', '?'):<8} roles={len(g.get('roles') or [])}"
        )
    print()
    return data


def cmd_group_create(name: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.create_group(name)
    if "error" in data:
        print(f"\033[91m✗ Failed to create group {name!r}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\033[92m✓ Created group {data.get('name', name)}\033[0m (id={data.get('id', '?')})")
    return data


def cmd_group_delete(group_id: str, admin_api_key: str):
    """Members keep organization membership; they just lose the
    permissions this group's attached roles granted. SCIM-provisioned
    groups can't be deleted through the API — the request returns 400."""
    client = AdminApiClient(admin_api_key)
    data = client.delete_group(group_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to delete group {group_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\033[92m✓ Deleted group {group_id}\033[0m")
    return data


def cmd_group_members_list(group_id: str, admin_api_key: str, limit: int = 100):
    client = AdminApiClient(admin_api_key)
    data = client.list_group_members(group_id, limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Failed to list members of group {group_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\n\033[94mGroup {group_id} — members\033[0m\n")
    rows = data.get("data", [])
    if not rows:
        print("  (no members in this group)")
    for m in rows:
        print(f"  {m.get('user_id', '?'):<28} {m.get('email', '?')}")
    print()
    return data


def cmd_group_member_add(group_id: str, user_id: str, admin_api_key: str):
    """The user must already be an organization member (404 otherwise).
    To assign groups to someone who hasn't joined yet, invite them with
    --invite-create's rbac_group_ids instead."""
    client = AdminApiClient(admin_api_key)
    data = client.add_group_member(group_id, user_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to add {user_id} to group {group_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\033[92m✓ Added {data.get('email', user_id)} to group {group_id}\033[0m")
    return data


def cmd_group_member_remove(group_id: str, user_id: str, admin_api_key: str):
    client = AdminApiClient(admin_api_key)
    data = client.remove_group_member(group_id, user_id)
    if "error" in data:
        print(f"\033[91m✗ Failed to remove {user_id} from group {group_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\033[92m✓ Removed {user_id} from group {group_id}\033[0m")
    return data


def cmd_roles_list(admin_api_key: str, limit: int = 20):
    """Custom roles are read-only through the API — created/edited in
    claude.ai organization settings, not here."""
    client = AdminApiClient(admin_api_key)
    data = client.list_roles(limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Failed to list roles: {data['error']}\033[0m")
        if data.get("status") == 404:
            print(
                f"\033[93m  A 404 here usually means the {CE_USER_MANAGEMENT_BETA} beta "
                f"header wasn't accepted — confirm this is a Claude Enterprise "
                f"organization.\033[0m"
            )
        else:
            _wrong_key_hint(data, _CE_HINT)
        return None
    print("\n\033[94mCustom roles\033[0m\n")
    rows = data.get("data", [])
    if not rows:
        print("  (no custom roles found)")
    for r in rows:
        print(f"  {r.get('id', '?'):<32} {r.get('name', '?')}")
    print()
    return data


def cmd_role_permissions_list(role_id: str, admin_api_key: str, limit: int = 20):
    client = AdminApiClient(admin_api_key)
    data = client.list_role_permissions(role_id, limit=limit)
    if "error" in data:
        print(f"\033[91m✗ Failed to list permissions for role {role_id}: {data['error']}\033[0m")
        _wrong_key_hint(data, _CE_HINT)
        return None
    print(f"\n\033[94mRole {role_id} — permissions\033[0m\n")
    rows = data.get("data", [])
    if not rows:
        print("  (no permissions found — role may only grant features not enabled " "for this organization)")
    for p in rows:
        resource = p.get("resource", {})
        r_type = resource.get("type", "?")
        r_detail = (
            resource.get("connector_id") or resource.get("tool_name") or resource.get("organization_id") or ""
        )
        print(f"  {r_type:<16} {r_detail:<28} action={p.get('action', '?')}")
    print()
    return data
