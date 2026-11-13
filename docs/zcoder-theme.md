# ZCODER — UNIVERSAL ENTERPRISE AI CODING CONTROL PLANE
## ADMINLTE-INSPIRED FULL MASTER IMPLEMENTATION PROMPT

PROJECT: ZCoder
REPOSITORY: https://github.com/cvsz/zcoder
DESIGN REFERENCE: https://github.com/ColorlibHQ/AdminLTE
DEFAULT BRANCH: main

PRODUCT:
Enterprise AI Coding Platform
Local-First · Self-Hosted · Zero-Cost-First · Multi-Agent · Enterprise Control Plane

MISSION:

Independently audit, design, implement, integrate, upgrade, test and complete the ZCoder Enterprise Admin Dashboard.

Transform ZCoder into a unified AI Engineering Control Plane for managing:

- AI agents
- Coding sessions
- Engineering tasks
- LLM providers
- Local models
- Model lifecycle
- GitHub repositories
- Pull requests
- Coding workflows
- Subagents
- MCP servers
- Tools
- Skills
- Hooks
- Memory
- RAG
- Sandboxes
- Approvals
- Policies
- Tenants
- Users
- RBAC
- Usage and costs
- Workers and queues
- Infrastructure
- Logs and metrics
- Security
- Audit
- Backup and recovery
- Deployments

This is a full working implementation assignment.

Do not stop after generating a proposal, architecture diagram, UI mockup, screenshots, static HTML or documentation.

Implement actual functional pages and integrate them with existing backend services.

---

# PHASE 0 — CANONICAL GOVERNANCE AND SECURITY

## Mandatory first action

Read the canonical ZEAz policy:

https://github.com/cvsz/zeaz/blob/main/zeaz.md

Read it together with:

- `AGENTS.md`
- `README.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODEX.md`
- `CLAUDE.md`
- `OPENCODE.md`
- `GEMINI.md`
- `CHECKLIST.md`
- `IMPLEMENTATION_CHECKLIST.md`
- `FINAL-AUDIT-REPORT.md`
- `docs/architecture/ARCHITECTURE.md`
- `docs/engineering/ROADMAP.md`
- `docs/engineering/exec-planning.md`

Also inspect the nearest nested `AGENTS.md` files before modifying any subtree.

Follow repository security, release, testing, language, local inference and governance policies.

Do not weaken existing security requirements.

## Core non-negotiable principles

1. Local-first execution remains supported.
2. Self-hosted operation must not require a commercial API.
3. Zero-cost routing must never silently fall back to paid models.
4. Source code and secrets must remain tenant-isolated.
5. Agent execution must be bounded by policy and resource budgets.
6. Mutating operations must enforce explicit approval obligations.
7. Sandboxes must maintain filesystem and network boundaries.
8. External tool output is untrusted input.
9. MCP tools require capability and trust validation.
10. Model artifacts must not automatically be treated as trusted executables.
11. All security-sensitive actions must be auditable.
12. Client-side authorization must never replace backend authorization.
13. Model availability must not be confused with model capability.
14. Tests and documentation must not fabricate runtime evidence.
15. Existing CLI and TUI compatibility must be preserved.

---

# PHASE 1 — DEEP REPOSITORY AUDIT

Inspect the entire repository before modifying code.

Priority areas:

- `src/zcoder/`
- `tests/`
- `docs/`
- `deploy/`
- `scripts/`
- `.github/`
- `pyproject.toml`
- `uv.lock`
- `Makefile`
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`

Inspect the actual source modules for:

## Core
- `core/`
- Exceptions.
- Resilience.
- Security.
- Policy.
- Types.
- Configuration.

## Agent runtime
- CodeAgent.
- Agent executor.
- Agent orchestration.
- Sessions.
- Subagents.
- Memory.
- Hooks.
- Skills.
- Commands.

## AI and providers
- Provider adapters.
- Provider router.
- Local inference.
- Ollama.
- llama.cpp.
- Model catalog.
- Hardware profiler.
- Model download.
- Model verification.
- Cost classification.
- Fallback policy.

## Engineering
- Code editing.
- Filesystem operations.
- Bash execution.
- Python execution.
- Git operations.
- GitHub integration.
- Pull request workflows.
- Test execution.
- Validation workflows.

## Enterprise
- Tenants.
- Organizations.
- Projects.
- RBAC.
- Identity.
- Sessions.
- API keys.
- SCIM.
- Quotas.
- Billing.
- Audit.
- Approval.
- Database.
- Backup and restore.

## Infrastructure
- Workers.
- Durable jobs.
- Outbox.
- Fencing.
- Scheduler.
- PostgreSQL.
- SQLite.
- Docker.
- Kubernetes and Helm where present.
- Prometheus.
- OpenTelemetry.

Identify all existing API routes, page templates, schemas, services, database models, authorization boundaries and frontend capabilities.

Do not guess API endpoints.

Build a capability matrix containing:

- Domain.
- Existing implementation.
- Existing API.
- Existing UI.
- Permission.
- Data source.
- Tests.
- Missing functionality.
- Security risk.
- Completion evidence.

Preserve existing user changes and working interfaces.

---

# PHASE 2 — ADMINLTE-INSPIRED DESIGN SYSTEM

Reference:
https://github.com/ColorlibHQ/AdminLTE

Review the current AdminLTE release, framework compatibility and MIT license before integration.

Use AdminLTE as the design and UX reference.

Do not blindly copy its full implementation or introduce unnecessary dependencies.

Build an original ZCoder theme.

## 2.1 Visual identity

Product identity:

ZCODER ENGINEERING CONTROL PLANE

Style:
- Enterprise administration.
- Modern developer tooling.
- Professional AI operations.
- Technical precision.
- High information density.
- Clean layouts.
- Responsive cards.
- Consistent data tables.

Color direction:
- Graphite/dark sidebar.
- Light neutral content surface.
- Blue primary actions.
- Carefully selected semantic status colors.
- Dark theme support.

## 2.2 Design tokens

Implement centralized tokens:

- Primary colors.
- Secondary colors.
- Semantic colors.
- Backgrounds.
- Borders.
- Typography.
- Font sizes.
- Spacing.
- Radius.
- Shadows.
- Z-index.
- Breakpoints.
- Animation.
- Status indicators.

Provide:
- Light theme.
- Dark theme.
- Theme persistence.
- Reduced motion.
- Accessible contrast.

## 2.3 Main application layout

Sidebar:
- ZCoder logo.
- Navigation groups.
- Nested navigation.
- Active states.
- Permission-aware links.
- Collapsible desktop layout.
- Responsive mobile drawer.

Top navigation:
- Breadcrumbs.
- Global search.
- Command palette.
- Runtime status.
- Provider status.
- Notification center.
- User profile.
- Theme controls.

Main content:
- Page header.
- Contextual description.
- Action toolbar.
- Filter toolbar.
- Cards.
- Charts.
- Tables.
- Forms.
- Dialogs.

Footer:
- Application version.
- Runtime version.
- Environment.
- API status.
- Database status.
- Local inference status.
- Last synchronization.

Only display actual verified runtime state.

---

# PHASE 3 — DASHBOARD INFORMATION ARCHITECTURE

Implement the following functional routes, adapting to actual existing API and domain boundaries.

## 3.1 Executive Dashboard

Route: `/admin`

Display:

KPI cards:
- Total engineering tasks.
- Active agents.
- Running sessions.
- Queued jobs.
- Active workers.
- Completed tasks.
- Failed tasks.
- Pending approvals.
- Local models available.
- Provider availability.
- API health.
- Database health.

Charts:
- Task execution over time.
- Task success/failure ratio.
- Agent utilization.
- Queue throughput.
- Job latency p50/p95/p99.
- Provider distribution.
- Model usage.
- Cost over time.
- API latency.
- Worker activity.

Activity timeline:
- Task created.
- Agent started.
- Tool invocation.
- Approval requested.
- Approval completed.
- Test execution.
- GitHub operation.
- Workflow completed.
- Worker recovered.
- Deployment operation.

Every metric must have an actual source, unit and timestamp.

Do not fabricate counts, costs, status or performance.

## 3.2 AI Agent Center

Route: `/admin/agents`

Implement:
- Agent catalog.
- Agent details.
- Agent role.
- Agent version.
- Runtime.
- Capabilities.
- Tools.
- Policy.
- Resource budgets.
- Status.
- Current task.
- Session.
- Execution history.
- Failure history.
- Performance.

Supported agent operations must respect backend policy.

Do not create a parallel agent engine in the frontend.

## 3.3 Agent Sessions

Route: `/admin/sessions`

Implement:
- Sessions.
- Session details.
- Conversation history.
- Context metadata.
- Token usage where supported.
- Model.
- Provider.
- Workspace.
- Session status.
- Resume.
- Rewind.
- Branch.
- Export where permitted.

Preserve the existing session lifecycle.

Protect conversation history and source-code content with tenant isolation.

## 3.4 Engineering Tasks

Route: `/admin/tasks`

Implement:
- Task inventory.
- Description.
- Priority.
- Status.
- Tenant.
- Project.
- Repository.
- Agent assignment.
- Model assignment.
- Resource budget.
- Retry count.
- Lease.
- Fencing token metadata.
- Created date.
- Start date.
- Completion date.
- Error information.

Support:
- Search.
- Filtering.
- Pagination.
- Sorting.
- Task details.
- Execution timeline.
- Cancellation where supported.
- Retry where policy allows.
- Approval inspection.

Never allow frontend code to modify durable job storage directly.

## 3.5 Task Orchestration

Route: `/admin/orchestration`

Implement:
- Workflow inventory.
- Workflow execution.
- State machines.
- Dependencies.
- Task graph.
- Subagent execution.
- Parallelism.
- Retry policies.
- Timeout.
- Resource limits.
- Approval gates.
- Workflow history.

Visualize dependencies and execution state.

Use existing orchestration services and transition rules.

## 3.6 AI Model Center

Route: `/admin/models`

Implement:
- Model catalog.
- Installed models.
- Model version.
- Provider.
- Model family.
- Parameter count where verified.
- Quantization.
- Context length.
- Artifact size.
- Hardware requirements.
- Download status.
- Integrity verification.
- Loadability.
- Runtime status.

Model lifecycle must reflect the real backend:

CATALOG
→ DISCOVERED
→ DOWNLOADING
→ DOWNLOADED
→ VERIFIED
→ LOADABLE
→ LOADED

With explicit FAILED and REMOVED states.

Controls:
- Discover.
- Download.
- Verify.
- Load.
- Unload.
- Remove.

Destructive or resource-intensive operations require authorization and confirmation.

Never treat catalog presence as proof that model weights are installed.

Never treat loaded model status as proof of successful inference.

## 3.7 Provider Management

Route: `/admin/providers`

Implement:
- Provider catalog.
- Provider adapters.
- Local endpoint.
- Cloud endpoint where policy permits.
- Provider capabilities.
- Availability.
- Latency.
- Timeout.
- Circuit breaker.
- Retry state.
- Provider quota.
- Cost class.
- Last inference.
- Error history.

Cost classes:

- FREE_LOCAL
- FREE_REMOTE
- CUSTOMER_KEY
- PAID_PLATFORM
- UNKNOWN

Policy modes:

- ZERO_COST_ONLY
- PREFER_ZERO_COST
- PERMIT_PAID

Never silently switch from zero-cost mode to paid infrastructure.

Provider health and runtime availability must be independently represented.

Do not expose provider credentials.

## 3.8 Provider Routing

Route: `/admin/routing`

Implement:
- Routing rules.
- Default provider.
- Local model preference.
- Route-specific providers.
- Model fallback ordering.
- Cost policy.
- Capability compatibility.
- Availability policy.
- Failure explanation.
- Routing decision history.

The server-side router is authoritative.

Every routing decision should be auditable.

A paid fallback must be prohibited unless explicitly permitted by tenant policy and user authorization.

## 3.9 Local AI Infrastructure

Route: `/admin/local-ai`

Implement:
- Ollama.
- llama.cpp.
- llama-server.
- vLLM where supported.
- OpenAI-compatible local endpoint.
- Local inference health.
- Endpoint configuration.
- Model runtime.
- Hardware profile.
- Context configuration.
- Concurrency.
- Memory utilization.

Local endpoint defaults may include:
- Ollama: 127.0.0.1:11434.
- llama.cpp: 127.0.0.1:8080.

Never expose private local inference ports publicly as a side effect of dashboard deployment.

## 3.10 Hardware Management

Route: `/admin/hardware`

Display:
- Operating system.
- CPU.
- CPU cores.
- Available RAM.
- Total RAM.
- GPU inventory.
- VRAM.
- GPU utilization where available.
- Disk.
- Model storage.
- Runtime compatibility.

Hardware profiling results must include timestamps and source.

Distinguish:
- Detected.
- Compatible.
- Configured.
- Available.
- Currently utilized.

## 3.11 GitHub Engineering Center

Route: `/admin/github`

Implement:
- Repository inventory.
- Repository details.
- Branches.
- Commits.
- Pull requests.
- Reviews.
- Workflow runs.
- CI status.
- Code scanning.
- Dependency alerts where supported.
- Deployment status.
- Release inventory.

GitHub operations must use existing integrations and credential handling.

Do not expose PATs.

Do not use frontend-only permission checks.

## 3.12 Repository Workspace

Route: `/admin/workspaces`

Implement:
- Organization.
- Tenant.
- Project.
- Repository.
- Workspace root.
- Branch.
- Worktree.
- Source files.
- Recent changes.
- Git status.
- Task association.
- Agent association.

Filesystem navigation must preserve safe-resolve and containment rules.

No arbitrary path access.

No cross-tenant workspace access.

## 3.13 Code Engineering

Route: `/admin/code`

Implement:
- Source browsing.
- Code inspection.
- Change summaries.
- Diff preview.
- Edit proposals.
- Patch review.
- Test status.
- Validation status.
- Git change status.

Use existing code-agent capabilities.

Apply explicit policy before modifying source files.

Never execute arbitrary untrusted code in the Web Console process.

All execution must pass through the designated sandbox and capability boundaries.

## 3.14 Tool Management

Route: `/admin/tools`

Implement:
- Tool catalog.
- Tool descriptions.
- Input schemas.
- Output schemas.
- Permissions.
- Capability scopes.
- Trust level.
- Availability.
- Invocation history.
- Error history.
- Timeout.
- Rate limit.

Support existing tools:
- Read.
- Write.
- Edit.
- Glob.
- Grep.
- LS.
- Bash.
- WebFetch.
- Other registered tools.

Treat all external tool output as untrusted data.

## 3.15 MCP Center

Route: `/admin/mcp`

Implement:
- MCP server inventory.
- Server details.
- Transport.
- Endpoint.
- Health.
- Server capabilities.
- Tool discovery.
- Resource discovery.
- Trust policy.
- Approval policy.
- Invocation logs.
- Connection failures.

Enforce:
- Server allowlists where configured.
- URL validation.
- SSRF defenses.
- Tool trust policies.
- Output validation.
- Capability boundaries.

Do not execute tools merely because a server advertises them.

## 3.16 Skills and Commands

Routes:
- `/admin/skills`
- `/admin/commands`

Implement:
- Skill catalog.
- Installation.
- Inspection.
- Version.
- Source.
- File containment.
- Activation.
- Removal.
- Command catalog.
- Metadata.
- Permissions.

Do not execute untrusted skill content automatically.

## 3.17 Hooks

Route: `/admin/hooks`

Implement:
- Hook inventory.
- Lifecycle events.
- Configuration.
- Trigger conditions.
- Permission.
- Execution result.
- Timeout.
- Failure state.
- Audit.

Preserve fail-closed behavior.

## 3.18 Memory and RAG

Routes:
- `/admin/memory`
- `/admin/rag`

Implement:
- Memory scopes.
- Enterprise memory.
- User memory.
- Project memory.
- Session memory.
- Document inventory.
- Retrieval configuration.
- Index health.
- Retrieval result metadata.
- Source references.
- Tenant boundaries.
- Retention policy.

Support existing local-first retrieval and document trust mechanisms.

Do not expose secrets or private memory across tenants.

## 3.19 Sandbox Management

Route: `/admin/sandboxes`

Implement:
- Sandbox inventory.
- Execution state.
- Filesystem scope.
- Network policy.
- Tool permissions.
- Environment isolation.
- Resource limits.
- Execution logs.
- Cleanup status.
- Failure diagnostics.

Enforce filesystem containment and network restrictions.

Never let a dashboard setting bypass sandbox policy.

## 3.20 Policy and Approval Center

Routes:
- `/admin/policies`
- `/admin/approvals`

Display:
- Policies.
- Policy versions.
- Obligations.
- Approvals.
- Pending requests.
- Approval reason.
- Requesting actor.
- Resource.
- Expiration.
- Decision.
- Audit history.

Support approval-aware operations.

Do not allow users to approve operations outside their permissions.

A policy enforcement failure must not silently permit execution.

## 3.21 Multi-Tenant Administration

Routes:
- `/admin/tenants`
- `/admin/organizations`
- `/admin/projects`

Implement:
- Tenant directory.
- Organization hierarchy.
- Project ownership.
- Tenant status.
- Resource quotas.
- Concurrent job limits.
- Monthly budget.
- Repository limits.
- Usage summaries.
- Tenant isolation.

All reads and mutations must be tenant scoped.

Never retrieve all tenant records into the browser and perform filtering client-side.

## 3.22 Identity and Access Management

Routes:
- `/admin/users`
- `/admin/roles`
- `/admin/permissions`
- `/admin/identity`

Implement:
- Users.
- Roles.
- Permissions.
- OIDC.
- JWT sessions.
- API keys.
- SCIM provisioning.
- Session history.
- Access reviews.
- Break-glass administration.

Use backend authorization as the authority.

## 3.23 Quotas and Cost Management

Routes:
- `/admin/quotas`
- `/admin/usage`
- `/admin/billing`

Implement:
- Token usage.
- Model usage.
- Task consumption.
- Worker consumption.
- Provider cost.
- Tenant cost.
- Monthly budget.
- Quota enforcement.
- Billing integration where implemented.

Clearly distinguish:
- Free local inference.
- Free remote inference.
- Customer-owned API costs.
- Platform-paid costs.
- Unknown cost.

Never invent cost estimates as actual charges.

Never trigger paid inference from a dashboard operation without authorization.

## 3.24 Worker and Queue Operations

Routes:
- `/admin/workers`
- `/admin/queues`

Implement:
- Active workers.
- Queued jobs.
- Running jobs.
- Failed jobs.
- Lease expirations.
- Retry count.
- Fencing rejections.
- Outbox pending.
- Outbox deliveries.
- Worker health.
- Queue throughput.
- Job duration.

Preserve durable job state transitions.

Never change worker leases or fencing tokens directly from frontend code.

## 3.25 Observability

Routes:
- `/admin/observability`
- `/admin/metrics`
- `/admin/logs`
- `/admin/traces`

Integrate existing Prometheus and OpenTelemetry facilities.

Use existing observability metrics where available:

- zcoder_jobs_queued
- zcoder_jobs_running
- zcoder_job_duration_seconds
- zcoder_jobs_total
- zcoder_jobs_failed_total
- zcoder_worker_active
- zcoder_worker_lease_expirations
- zcoder_worker_fencing_rejections
- zcoder_outbox_pending
- zcoder_outbox_failures
- zcoder_outbox_deliveries
- zcoder_webhooks
- zcoder_webhooks_duplicate
- zcoder_db_pool_in_use
- zcoder_db_pool_available
- zcoder_db_query_latency_seconds
- zcoder_db_errors
- zcoder_backup_last_success_timestamp
- zcoder_backup_last_restore_drill_timestamp
- zcoder_api_requests
- zcoder_api_errors
- zcoder_api_duration_seconds
- zcoder_cost_usd
- zcoder_maintenance_campaigns

Maintain compatibility with:
`docs/observability/dashboard.json`

## 3.26 Backup and Disaster Recovery

Route: `/admin/backup`

Implement:
- Backup inventory.
- Backup status.
- Backup timestamp.
- Backup integrity.
- SHA-256 manifest.
- PostgreSQL backup.
- SQLite backup where supported.
- Restore rehearsal.
- Point-in-time recovery.
- WAL status.
- RPO and RTO evidence.
- Retention policy.

Destructive restore operations must require elevated authorization and explicit confirmation.

Never run recovery against a production database without the required execution approval.

## 3.27 Deployment and Release Management

Routes:
- `/admin/deployments`
- `/admin/releases`

Implement:
- Deployment inventory.
- Deployment history.
- Version.
- Artifact metadata.
- Artifact signatures.
- Provenance.
- Release gates.
- Rollback readiness.
- Rollback history.
- Artifact revocation.
- Release evidence.

Preserve signed artifact and supply-chain verification requirements.

Do not claim a deployment succeeded based on submission of a deployment request.

## 3.28 Security Center

Route: `/admin/security`

Implement:
- Security events.
- Authentication events.
- Authorization denials.
- Secret scan results.
- Dependency alerts.
- Vulnerability findings.
- Sandbox policy.
- Tool trust.
- Tenant isolation checks.
- Supply chain status.
- Security regression tests.

Display severity, evidence and remediation status.

Never render credential values or raw secret-bearing logs.

## 3.29 Audit Center

Route: `/admin/audit`

Implement:
- Immutable event timeline.
- Actor.
- Tenant.
- Resource.
- Action.
- Request ID.
- Correlation ID.
- Timestamp.
- Result.
- Evidence reference.
- Export.

Audit records must remain append-only.

Do not expose an edit or delete interface for immutable audit records.

## 3.30 Settings

Route: `/admin/settings`

Implement:
- General settings.
- Runtime settings.
- Model settings.
- Provider settings.
- Policy settings.
- Appearance.
- Notifications.
- Observability.
- Integration configuration.

Respect configuration precedence and secret-management rules.

Never write secrets into browser local storage or publicly accessible configuration endpoints.

---

# PHASE 4 — API AND BACKEND INTEGRATION

Use existing FastAPI endpoints and services.

Inspect all current routes from:
- Existing API entry points.
- OpenAPI specification where enabled.
- Domain route registration.
- Services.
- Schemas.
- Existing Web Console.

Do not invent route contracts.

Build a route mapping between each dashboard page and:
- Backend endpoint.
- Service.
- Schema.
- Required permissions.
- Tenant scope.
- Failure behavior.

Implement:
- Typed request/response contracts.
- Central API client.
- Authentication lifecycle.
- CSRF.
- Timeout.
- Cancellation.
- Safe retries for idempotent GET requests.
- Structured error handling.
- Correlation IDs.
- Pagination.
- Filtering.
- Response validation.

Never blindly retry a mutating operation.

Use backend services, not direct SQL from browser code.

---

# PHASE 5 — FRONTEND IMPLEMENTATION STRATEGY

Preserve the repository's existing Web Console architecture.

Inspect frontend technology before implementation.

If the current Web Console is server-rendered or vanilla JavaScript, extend it coherently.

If an existing TypeScript/React application already exists, reuse it.

Do not introduce an unnecessary Next.js application or create multiple competing frontend stacks.

AdminLTE may be integrated through:
- Compatible static assets.
- Existing templates.
- Reusable layout components.
- Compatible CSS and JavaScript modules.

Pin dependencies and verify licenses.

Do not embed the development server into production.

---

# PHASE 6 — COMPONENT FACTORY

Implement reusable components:

Layout:
- AdminLayout.
- AdminSidebar.
- AdminNavbar.
- Breadcrumb.
- PageHeader.
- PageToolbar.
- CommandPalette.

Statistics:
- InfoBox.
- SmallBox.
- MetricCard.
- StatusCard.
- TrendCard.

Agent:
- AgentCard.
- AgentStatus.
- AgentTimeline.
- SessionPanel.
- TaskCard.

AI:
- ModelCard.
- ProviderCard.
- RoutingDecisionCard.
- LocalRuntimeCard.

Enterprise:
- TenantCard.
- UserTable.
- RoleBadge.
- PermissionMatrix.
- ApprovalCard.
- PolicyEditor.

Operations:
- QueueMonitor.
- WorkerCard.
- JobTimeline.
- DeploymentCard.
- BackupCard.
- HealthIndicator.

Development:
- RepositoryCard.
- BranchTable.
- PullRequestCard.
- DiffViewer.
- TestResultsPanel.

Observability:
- MetricsChart.
- LogViewer.
- TraceViewer.
- LatencyChart.
- CostChart.

Forms:
- FormField.
- Input.
- Select.
- Checkbox.
- FormSection.
- ErrorSummary.
- ConfirmationDialog.

All components must have consistent type contracts and reusable behavior.

---

# PHASE 7 — COMMAND CENTER

Implement a global command palette.

Suggested commands:
- Open dashboard.
- Find task.
- Find agent.
- Open session.
- Inspect provider.
- Discover local model.
- Inspect repository.
- Inspect pull request.
- Open approval queue.
- View system health.
- Open settings.

Commands must enforce the same permissions as ordinary routes.

Keyboard shortcuts must be discoverable and accessible.

---

# PHASE 8 — REAL-TIME OPERATIONS

Inspect existing streaming implementation before selecting WebSocket, SSE or polling.

Implement:
- Live job status.
- Agent state updates.
- Worker heartbeats.
- Queue changes.
- Approval notifications.
- Provider state.
- Deployment state.
- Metrics refresh.

Requirements:
- Bounded reconnect backoff.
- Heartbeat.
- Stale connection detection.
- Event deduplication.
- Event ordering.
- Reconciliation after reconnect.
- Cleanup of inactive subscriptions.

A lost connection must not be presented as a successful operation.

---

# PHASE 9 — SECURITY ARCHITECTURE

Follow `SECURITY.md` and the canonical ZEAz policy.

Preserve all existing SEC-001 through SEC-011 and subsequent controls.

Audit:
- SSRF.
- Path traversal.
- Sandbox escape.
- Network policy bypass.
- CodeAgent filesystem containment.
- WebFetch SSRF.
- MCP/tool trust boundaries.
- RAG tenant isolation.
- Secret environment inheritance.
- Authorization and approval.
- CI and supply chain.
- Point-in-time recovery.

Frontend must never be the source of truth for security enforcement.

All high-impact operations must be authorized server-side.

All external content must be treated as untrusted.

---

# PHASE 10 — LOCAL-FIRST AND COST GOVERNANCE

Critical requirement:

The Web Console must preserve the local-first and zero-cost-first contract.

Implement visible indicators for:

- Local mode.
- Active inference endpoint.
- Loaded model.
- Provider cost class.
- Routing policy.
- Paid provider permission.
- Current inference availability.

ZERO_COST_ONLY:
- Paid providers must be blocked.
- UNKNOWN cost routes must be blocked.
- No silent cloud fallback.

PREFER_ZERO_COST:
- Prefer local/free routes.
- Paid fallback must still require explicit configured permission and authorization.

PERMIT_PAID:
- Permit only approved paid routes.
- Record cost attribution.
- Enforce tenant and budget policies.

Never assume a provider is free just because its API responds successfully.

---

# PHASE 11 — PERFORMANCE

Implement:
- Route-level loading.
- Lazy-loaded charts.
- Pagination.
- Efficient state updates.
- Cancellable requests.
- Controlled polling.
- Real-time subscription cleanup.
- Memory leak prevention.
- Large table optimization.
- Log streaming bounds.
- Metric aggregation.

Avoid excessive API requests.

Use server-side aggregation for large data volumes.

Measure actual performance.

---

# PHASE 12 — ACCESSIBILITY

Target WCAG 2.2 AA.

Implement:
- Semantic HTML.
- Keyboard navigation.
- Visible focus.
- Accessible labels.
- Dialog focus management.
- Accessible tables.
- Chart summaries.
- Screen-reader status.
- Reduced motion.
- Accessible error messaging.

Never communicate status by color alone.

---

# PHASE 13 — TESTING

Use existing testing infrastructure.

Backend:
- pytest.
- Existing test fixtures.
- Unit tests.
- Integration tests.
- PostgreSQL tests.
- Security regression tests.

Frontend:
- Existing browser tests.
- JavaScript tests where configured.
- Playwright if already supported or justified.
- Accessibility checks.

Required tests:

1. Admin authentication.
2. Unauthorized access.
3. Tenant isolation.
4. Agent inventory.
5. Session rendering.
6. Task list.
7. Task state.
8. Worker lease.
9. Stale fencing token rejection.
10. Queue state.
11. Model catalog.
12. Local model verification.
13. Provider routing.
14. ZERO_COST_ONLY rejection.
15. Paid fallback rejection.
16. MCP tool trust.
17. Sandbox restrictions.
18. Approval enforcement.
19. GitHub integration permissions.
20. Secret masking.
21. Audit immutability.
22. Backup integrity.
23. Restore rehearsal.
24. Deployment status.
25. API errors.
26. Real-time reconnect.
27. Mobile navigation.
28. Theme switching.
29. Keyboard accessibility.
30. No credential disclosure in browser output.

Do not make live paid-model calls during ordinary CI.

Use mocks only for appropriate isolated tests and clearly distinguish mocked evidence from real local inference.

---

# PHASE 14 — DEPLOYMENT

Preserve current deployment paths.

Support:
- Local development.
- Docker.
- Docker Compose.
- PostgreSQL.
- Existing self-hosted inference services.
- Kubernetes/Helm if already implemented.

Inspect actual deployment files before changes.

Preserve:
- Shared zpostgressql lifecycle.
- Dedicated zcoder_db.
- Read-only GGUF mount.
- Loopback-only local inference.
- Secret file mounts.
- Network namespace isolation.

Security:
- Non-root containers.
- No embedded credentials.
- Restricted network exposure.
- Health checks.
- Graceful shutdown.
- Persistent state.
- Backup and restore.
- Rollback capability.

Do not expose the llama-server port to the LAN or public network through dashboard changes.

---

# PHASE 15 — MULTI-AGENT IMPLEMENTATION

Use specialized engineering agents for independent workstreams.

Suggested agents:

1. Architecture Agent.
2. AdminLTE UI/UX Agent.
3. Dashboard Shell Agent.
4. Agent Runtime Integration Agent.
5. Model and Provider Agent.
6. GitHub Integration Agent.
7. Tenant and IAM Agent.
8. Queue and Worker Agent.
9. Observability Agent.
10. Policy and Approval Agent.
11. Security Agent.
12. Testing Agent.
13. DevOps Agent.
14. Independent Review Agent.

Every agent must:
- Read repository instructions.
- Own a defined scope.
- Follow source architecture.
- Preserve security boundaries.
- Add tests.
- Report evidence.

Avoid concurrent edits to shared files.

Do not make independent reviewers approve their own work.

Use local inference and available zero-cost models for eligible coding tasks.

No silent switch to paid providers when local inference is unavailable.

---

# PHASE 16 — DOCUMENTATION

Create:

- `docs/admin-dashboard/INDEX.md`
- `docs/admin-dashboard/ARCHITECTURE.md`
- `docs/admin-dashboard/DESIGN-SYSTEM.md`
- `docs/admin-dashboard/ROUTES.md`
- `docs/admin-dashboard/API-MAPPING.md`
- `docs/admin-dashboard/COMPONENTS.md`
- `docs/admin-dashboard/SECURITY.md`
- `docs/admin-dashboard/OPERATIONS.md`
- `docs/admin-dashboard/TEST-PLAN.md`
- `docs/admin-dashboard/DEPLOYMENT.md`
- `docs/admin-dashboard/IMPLEMENTATION-REPORT.md`

Update:
- `README.md`
- `docs/observability/dashboard.json` when necessary.
- `IMPLEMENTATION_CHECKLIST.md`.
- `CHECKLIST.md`.
- Relevant architecture and operations documentation.

Follow Thai documentation conventions and retain English technical identifiers.

Distinguish source implementation, unit-test evidence, integration evidence, real local inference, hosted CI and production evidence.

---

# PHASE 17 — VALIDATION

Inspect Makefile and existing scripts for canonical validation targets.

At minimum:

```bash
ruff check .
black --check .
mypy src/zcoder --ignore-missing-imports
bandit -r src/zcoder -ll
pytest --cov --cov-report=term-missing
```

Use repository-native validation targets when they provide broader coverage.

Validate:
- Frontend build.
- Frontend lint.
- API contracts.
- Docker build.
- Docker Compose.
- PostgreSQL integration.
- Security checks.
- Dependency checks.
- Release gates.
- Reproducibility.

For PostgreSQL-backed tests, use the repository helper:

```bash
python scripts/local_postgres.py status
python scripts/local_postgres.py run -- python -m pytest tests/integration -q
```

Do not expose database credentials.

Record exact command, environment, test counts and exit code.

Never disable checks or lower thresholds to make the build pass.

---

# PHASE 18 — FINAL COMPLETION CRITERIA

The dashboard is complete only when:

- AdminLTE-inspired layout works.
- Authentication works.
- Navigation works.
- Tenant boundaries work.
- Agent inventory works.
- Session management works.
- Task monitoring works.
- Model management works.
- Provider routing works.
- Local inference visibility works.
- Zero-cost controls work.
- GitHub integration works.
- MCP management works.
- Tool permissions work.
- Approval workflow works.
- Enterprise IAM works.
- Queue and worker monitoring work.
- Observability works.
- Backup status works.
- Deployment status works.
- Security controls remain intact.
- All tests pass or blockers are clearly documented.
- Documentation is updated.
- Existing CLI and TUI still work.

Do not declare complete functionality when only the UI exists.

Do not claim production readiness based solely on mocked endpoints or source-level checks.

---

# PHASE 19 — FINAL REPORT

Provide:

1. Executive summary.
2. Original architecture.
3. Design system.
4. Implemented dashboard routes.
5. Functional page inventory.
6. Backend integration map.
7. Agent runtime status.
8. Local AI integration status.
9. Provider and cost-policy implementation.
10. GitHub integration.
11. Security and authorization improvements.
12. Tenant isolation test results.
13. Queue and worker test results.
14. PostgreSQL results.
15. Frontend build results.
16. Accessibility results.
17. Performance results.
18. Files changed.
19. Known defects.
20. External dependencies.
21. CI evidence.
22. Deployment evidence.
23. Commit SHAs.
24. PR URL.
25. Rollback instructions.

FINAL STANDARD:

ENTERPRISE-GRADE
LOCAL-FIRST
ZERO-COST-FIRST
SECURE-BY-DESIGN
TYPE-SAFE
MULTI-TENANT
OBSERVABLE
TESTED
MAINTAINABLE

Execute the complete implementation independently.

Make reasonable engineering decisions based on actual repository source.

Do not stop after planning, audit or UI scaffolding.

Deliver working, tested, secured and documented functionality with traceable evidence.