🔍 วิเคราะห์โครงสร้างโปรเจกต์ zcoder 

ปัญหาที่พบในโครงสร้างปัจจุบัน

🔴 ปัญหาวิกฤต (Critical)

| ปัญหา | รายละเอียด |
|--------|------------|
| Flat File Explosion | มีไฟล์ Python 100+ ไฟล์ วางกองอยู่ที่ root ทั้งหมด ไม่มี package hierarchy เลย ทำให้ navigation ยากมาก และ IDE auto-import สับสน |
| ไม่มี Python Package | ไม่มีโฟลเดอร์ src/zcoder/ หรือ zcoder/ ทั้งที่มี pyproject.toml และ zcoder.egg-info อยู่ → แสดงว่า build system กับ source layout ไม่สอดคล้องกัน |
| Build Artifacts ถูก commit เข้า repo | dist/, zcoder.egg-info/, pycache/, .db-shm, .db-wal ไม่ควรอยู่ใน version control |
| ไม่พบ .gitignore | ใน tree ไม่มี .gitignore → เป็นสาเหตุที่ artifacts ถูก commit เข้ามา |

🟡 ปัญหาโครงสร้าง (Structural)

| ปัญหา | รายละเอียด |
|--------|------------|
| 50+ ไฟล์ claude* เรียงกันเป็นพืด | claudeopus5.py, claudesonnet5.py, claudecode.py, claude_vision.py ฯลฯ ทั้งหมดอยู่ระดับเดียวกัน ไม่มี grouping ตาม concern |
| Domain Models กระจายอยู่ root | engineeringmodels.py, portfoliomodels.py, tenant_models.py ควรอยู่ใน domain layer แยกต่างหาก |
| Store/Repository layer ปนกับ business logic | postgresstore.py, sqliteengineering_store.py อยู่ระดับเดียวกับ coder.py, main.py |
| Interface layer ปนกับ core | tui.py, tuistreaming.py, sdkclient.py (UI/SDK) อยู่ระดับเดียวกับ security.py, resilience.py (core) |
| Tests เป็น flat list | tests/ มี 60+ ไฟล์เรียงกัน ไม่แยก unit/integration/e2e |
| Docs ไม่มี taxonomy | docs/ มีทั้ง upgrade notes, runbooks, security docs, compliance docs ปนกันหมด |
| Build scripts อยู่ root | build.sh, setup.sh, build.bat, setup.bat ควรอยู่ใน scripts/ |

🟠 ปัญหาการตั้งชื่อ (Naming)

| ปัญหา | ตัวอย่าง |
|--------|----------|
| Inconsistent prefix | บางไฟล์ใช้ claude prefix, บางไฟล์ใช้ engineering, บางไฟล์ไม่มี prefix |
| ซ้ำซ้อนกับโฟลเดอร์ | ถ้าจัดเข้าโฟลเดอร์แล้ว ชื่อ claude_code.py ใน claude/code.py จะซ้ำซ้อน |
| ไฟล์ที่ชื่อคลุมเครือ | coder.py, cowork.py, skills.py, personalities.py ไม่สื่อหน้าที่ชัดเจน |

โครงสร้างใหม่ที่เสนอ (Production-Ready)

ใช้หลักการ Clean Architecture ผสม Domain-Driven Design:

zcoder/
│
├── .gitignore                          # ← เพิ่มใหม่ (สำคัญมาก!)
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── Makefile
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE
├── CHECKLIST.md
├── IMPLEMENTATION_CHECKLIST.md
│
├── src/
│   └── zcoder/                         # Python package หลัก
│       ├── init.py
│       ├── main.py                     # Entry point
│       │
│       ├── config/                     # ⚙️ Configuration Layer
│       │   ├── init.py
│       │   ├── settings.py             # ← config.py
│       │   ├── production.py           # ← production_config.py
│       │   └── logging.py              # ← logging_config.py
│       │
│       ├── core/                       # 🏗️ Core / Cross-cutting
│       │   ├── init.py
│       │   ├── exceptions.py           # ← exceptions.py
│       │   ├── security.py             # ← security.py
│       │   ├── resilience.py           # ← resilience.py
│       │   ├── health.py               # ← health.py
│       │   └── utils.py                # ← utils.py
│       │
│       ├── domain/                     # 🧠 Domain Layer (DDD)
│       │   ├── init.py
│       │   ├── models/
│       │   │   ├── init.py
│       │   │   ├── engineering.py      # ← engineering_models.py
│       │   │   ├── intelligence.py     # ← intelligence_models.py
│       │   │   ├── portfolio.py        # ← portfolio_models.py
│       │   │   ├── product.py          # ← product_models.py
│       │   │   ├── residency.py        # ← residency_models.py
│       │   │   ├── tenant.py           # ← tenant_models.py
│       │   │   └── legacyjob.py       # ← legacyjob_models.py
│       │   ├── services/
│       │   │   ├── init.py
│       │   │   ├── policyengine.py    # ← policyengine.py
│       │   │   ├── controlplane.py    # ← controlplane.py
│       │   │   └── deployment.py       # ← deployment_engine.py
│       │   └── interfaces/             # Repository interfaces (Ports)
│       │       ├── init.py
│       │       └── engineeringstore.py # ← engineeringstore_interface.py
│       │
│       ├── claude/                     # 🤖 Claude Integration Layer
│       │   ├── init.py
│       │   ├── models/                 # Model-specific implementations
│       │   │   ├── init.py
│       │   │   ├── registry.py         # ← claude_models.py
│       │   │   ├── preflight.py        # ← claudemodelpreflight.py
│       │   │   ├── opus5.py            # ← claude_opus5.py
│       │   │   ├── sonnet5.py          # ← claude_sonnet5.py
│       │   │   ├── haiku45.py          # ← claude_haiku45.py
│       │   │   ├── fable5.py           # ← claude_fable5.py
│       │   │   └── mythos5.py          # ← claude_mythos5.py
│       │   ├── capabilities/           # Feature capabilities
│       │   │   ├── init.py
│       │   │   ├── code.py             # ← claude_code.py
│       │   │   ├── codeexec.py        # ← claudecode_exec.py
│       │   │   ├── vision.py           # ← claude_vision.py
│       │   │   ├── thinking.py         # ← claude_thinking.py
│       │   │   ├── structured.py       # ← claude_structured.py
│       │   │   ├── search.py           # ← claude_search.py
│       │   │   ├── embeddings.py       # ← claude_embeddings.py
│       │   │   ├── stream.py           # ← claude_stream.py
│       │   │   ├── citations.py        # ← claude_citations.py
│       │   │   └── advisor.py          # ← claude_advisor.py
│       │   ├── tools/                  # Tool integrations
│       │   │   ├── init.py
│       │   │   ├── registry.py         # ← claude_tools.py
│       │   │   ├── mcp.py              # ← claudemcpconnector.py
│       │   │   ├── plugins.py          # ← claude_plugins.py
│       │   │   └── sandbox.py          # ← claude_sandbox.py
│       │   ├── integrations/           # External service integrations
│       │   │   ├── init.py
│       │   │   ├── github.py           # ← claude_github.py
│       │   │   ├── git.py              # ← claude_git.py
│       │   │   ├── files.py            # ← claude_files.py
│       │   │   ├── excel.py            # ← claude_excel.py
│       │   │   ├── powerpoint.py       # ← claude_powerpoint.py
│       │   │   ├── chrome.py           # ← claude_chrome.py
│       │   │   └── wif.py              # ← claude_wif.py
│       │   ├── orchestration/          # Workflow & routing
│       │   │   ├── init.py
│       │   │   ├── router.py           # ← claude_router.py
│       │   │   ├── workflow.py         # ← claude_workflow.py
│       │   │   ├── agentssdk.py       # ← claudeagents_sdk.py
│       │   │   ├── batch.py            # ← claude_batch.py
│       │   │   ├── live.py             # ← claude_live.py
│       │   │   ├── interactive.py      # ← claude_interactive.py
│       │   │   └── sessions.py         # ← claude_sessions.py
│       │   ├── optimization/           # Cost & prompt optimization
│       │   │   ├── init.py
│       │   │   ├── cost.py             # ← claudecostoptimizer.py
│       │   │   ├── prompt.py           # ← claudepromptoptimizer.py
│       │   │   └── tokens.py           # ← claude_tokens.py
│       │   ├── memory/                 # Memory & caching
│       │   │   ├── init.py
│       │   │   ├── memory.py           # ← claude_memory.py
│       │   │   └── cache.py            # ← claude_cache.py
│       │   ├── rag/                    # RAG & research
│       │   │   ├── init.py
│       │   │   ├── engine.py           # ← claude_rag.py
│       │   │   └── research.py         # ← claude_research.py
│       │   ├── eval/                   # Evaluation & testing
│       │   │   ├── init.py
│       │   │   ├── eval.py             # ← claude_eval.py
│       │   │   ├── evals.py            # ← claude_evals.py
│       │   │   └── outputstyles.py    # ← claudeoutput_styles.py
│       │   ├── enterprise/             # Enterprise features
│       │   │   ├── init.py
│       │   │   ├── adminapi.py        # ← claudeadmin_api.py
│       │   │   ├── compliance.py       # ← claudecomplianceapi.py
│       │   │   ├── skills.py           # ← claudeskillsapi.py
│       │   │   ├── settings.py         # ← claude_settings.py
│       │   │   ├── hooksperms.py      # ← claudehookspermsplan.py
│       │   │   └── metrics.py          # ← claude_metrics.py
│       │   └── personalities.py        # ← personalities.py
│       │
│       ├── infrastructure/             # 🔌 Infrastructure Layer
│       │   ├── init.py
│       │   ├── stores/
│       │   │   ├── init.py
│       │   │   ├── postgres.py         # ← postgres_store.py
│       │   │   ├── postgreseng.py     # ← postgresengineering_store.py
│       │   │   ├── enterprisepg.py    # ← enterprisepostgres_store.py
│       │   │   ├── sqliteeng.py       # ← sqliteengineering_store.py
│       │   │   └── portfolio.py        # ← portfolio_store.py
│       │   ├── observability/
│       │   │   ├── init.py
│       │   │   └── otel.py             # ← observability_otel.py
│       │   ├── auth/
│       │   │   ├── init.py
│       │   │   ├── oidc.py             # ← auth_oidc.py
│       │   │   └── scim.py             # ← scim_service.py
│       │   └── artifacts.py            # ← artifacts.py
│       │
│       ├── services/                   # 📋 Application / Service Layer
│       │   ├── init.py
│       │   ├── agentruntime.py        # ← agentruntime.py
│       │   ├── coder.py                # ← coder.py
│       │   ├── engineeringorch.py     # ← engineeringorchestrator.py
│       │   ├── engineeringworker.py   # ← engineeringworker.py
│       │   ├── githuborch.py          # ← githuborchestrator.py
│       │   ├── maintenanceintel.py    # ← maintenanceintelligence_service.py
│       │   ├── portfolioscheduler.py  # ← portfolioscheduler.py
│       │   ├── backuprestore.py       # ← backuprestore.py
│       │   ├── cowork.py               # ← cowork.py
│       │   └── skills.py               # ← skills.py
│       │
│       ├── api/                        # 🌐 API Layer
│       │   ├── init.py
│       │   ├── public/
│       │   │   ├── init.py
│       │   │   └── v1.py               # ← publicapiv1.py
│       │   └── anthropicconformance.py # ← anthropicconformance.py
│       │
│       ├── interfaces/                 # 🖥️ Interface / Presentation Layer
│       │   ├── init.py
│       │   ├── cli/
│       │   │   ├── init.py
│       │   │   ├── tui.py              # ← tui.py
│       │   │   └── streaming.py        # ← tui_streaming.py
│       │   └── sdk/
│       │       ├── init.py
│       │       └── client.py           # ← sdk_client.py
│       │
│       ├── enterprise/                 # 🏢 Enterprise Platform
│       │   ├── init.py
│       │   ├── nocostplatform.py     # ← nocostplatform.py
│       │   └── localaistack.py       # ← localaistack.py
│       │
│       └── worker/                     # ⚡ Background Workers
│           ├── init.py
│           └── process.py              # ← worker_process.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/                           # Unit tests
│   │   ├── test_config.py
│   │   ├── test_utils.py
│   │   ├── test_security.py
│   │   ├── test_resilience.py
│   │   ├── testclaudemodels.py
│   │   ├── testclaudestructured.py
│   │   ├── testclaudethinking.py
│   │   └── ...
│   ├── integration/                    # Integration tests
│   │   ├── testpostgresstore.py
│   │   ├── testpostgresmultiprocess.py
│   │   ├── testsqliteengineering_store.py
│   │   ├── testauthoidc.py
│   │   └── ...
│   └── e2e/                            # End-to-end tests
│       ├── testfleete2e.py
│       ├── testdurabilityrestart.py
│       ├── testhardcrash.py
│       ├── testupgradesuites/
│       │   ├── testupgrade11evidence.py
│       │   ├── testupgrade12product.py
│       │   └── ...
│       └── testwebappserver.py
│
├── webapp/
│   ├── backend/
│   │   └── server.py
│   ├── frontend/
│   │   ├── app.js
│   │   ├── index.html
│   │   └── style.css
│   ├── README.md
│   └── requirements-web.txt
│
├── deploy/
│   ├── helm/
│   │   └── zcoder/
│   │       ├── Chart.yaml
│   │       ├── values.yaml
│   │       └── templates/
│   │           ├── deployment.yaml
│   │           ├── _helpers.tpl
│   │           └── service-pdb-netpol.yaml
│   ├── docker/
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   └── k8s/                            # ← ถ้ามี raw manifests
│
├── docs/
│   ├── architecture/
│   │   ├── ARCHITECTURE.md
│   │   ├── DATA-FLOW.md
│   │   └── HA-BOUNDARIES.md
│   ├── security/
│   │   ├── SECURITY.md
│   │   ├── API-KEYS.md
│   │   ├── ENCRYPTION.md
│   │   ├── IDENTITY.md
│   │   ├── KEY-MANAGEMENT.md
│   │   ├── SSO.md
│   │   ├── SCIM.md
│   │   └── SERVICE-ACCOUNTS.md
│   ├── compliance/
│   │   ├── COMPLIANCE-EVIDENCE.md
│   │   ├── CONTROL-CATALOG.md
│   │   ├── DATA-RESIDENCY.md
│   │   ├── EVIDENCE-MODEL.md
│   │   ├── MULTI-TENANCY.md
│   │   ├── POLICY.md
│   │   ├── QUOTAS.md
│   │   ├── REGIONS.md
│   │   └── RETENTION.md
│   ├── operations/
│   │   ├── deployment.md
│   │   ├── KUBERNETES.md
│   │   ├── SLO.md
│   │   ├── DISASTER-RECOVERY.md
│   │   ├── BILLING.md
│   │   ├── USAGE-METERING.md
│   │   ├── observability.md
│   │   └── runbooks/
│   │       ├── API-KEY-COMPROMISE.md
│   │       ├── QUOTA-INCIDENT.md
│   │       ├── SCIM-FAILURE.md
│   │       ├── SSO-LOCKOUT.md
│   │       ├── TENANT-ISOLATION-INCIDENT.md
│   │       └── USAGE-METERING-ERROR.md
│   ├── enterprise/
│   │   ├── ENTERPRISE-FEATURE-MATRIX.md
│   │   ├── ENTERPRISE-RBAC.md
│   │   ├── ORGANIZATIONS.md
│   │   └── MCP-CONFORMANCE.md
│   ├── guides/
│   │   ├── QUICKSTART.md
│   │   ├── LOCAL-AI.md
│   │   └── projectsandartifacts.md
│   ├── upgrades/                       # ← ย้าย upgrade docs มารวมกัน
│   │   ├── v1.10.0.md
│   │   ├── v1.10.2.md
│   │   ├── ...
│   │   └── v1.40.0.md
│   └── prompts/                        # ← ย้าย .prompt files มารวมกัน
│       ├── Upgrade-01.prompt
│       ├── ...
│       └── zcoderauditprompts.md
│
├── scripts/
│   ├── build.sh
│   ├── build.bat
│   ├── setup.sh
│   ├── setup.bat
│   └── release_gate.py
│
└── spec/
    ├── ai-coder.spec
    └── anthropic-conformance.yaml

เหตุผลในการย้ายไฟล์แต่ละกลุ่ม

📦 กลุ่มที่ 1: Source Code → src/zcoder/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| ทุกไฟล์ .py ที่ root | src/zcoder/ | ใช้ src layout ตามมาตรฐาน Python packaging (PEP 517/518) ทำให้ pip install -e . ทำงานถูกต้อง และป้องกัน accidental import จาก working directory |

📦 กลุ่มที่ 2: Configuration → config/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| config.py | config/settings.py | แยก config ออกจาก business logic, รองรับ multi-environment (dev/staging/prod) |
| production_config.py | config/production.py | Production-specific settings อยู่ในกลุ่มเดียวกัน |
| logging_config.py | config/logging.py | Logging config เป็น infrastructure concern แต่จัดกลุ่มกับ config อื่นเพื่อให้ง่ายต่อการค้นหา |

📦 กลุ่มที่ 3: Core → core/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| exceptions.py | core/exceptions.py | Custom exceptions เป็น cross-cutting concern ที่ทุก layer ต้องใช้ |
| security.py | core/security.py | Security primitives (hashing, encryption helpers) เป็น core concern |
| resilience.py | core/resilience.py | Circuit breaker, retry logic เป็น cross-cutting |
| health.py | core/health.py | Health check endpoint logic |
| utils.py | core/utils.py | Shared utilities |

📦 กลุ่มที่ 4: Domain Models → domain/models/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| engineering_models.py | domain/models/engineering.py | DDD Principle: Domain models ต้องอยู่ใน domain layer, ไม่มี dependency กับ infrastructure |
| portfolio_models.py | domain/models/portfolio.py | เช่นเดียวกัน |
| tenant_models.py | domain/models/tenant.py | Multi-tenancy models เป็น core domain concept |
| product_models.py | domain/models/product.py | Product domain |
| residency_models.py | domain/models/residency.py | Data residency models |
| intelligence_models.py | domain/models/intelligence.py | Intelligence/AI models |
| legacyjobmodels.py | domain/models/legacy_job.py | Legacy models ที่อาจต้อง deprecate ในอนาคต |

📦 กลุ่มที่ 5: Claude Integration → claude/ (sub-packages)

นี่คือกลุ่มที่ใหญ่ที่สุด (50+ ไฟล์) การแยกเป็น sub-packages ช่วยดังนี้:

| Sub-package | ไฟล์ที่รวม | เหตุผล |
|-------------|-----------|--------|
| claude/models/ | claudemodels.py, claudeopus5.py, claudesonnet5.py, claudehaiku45.py, claudefable5.py, claudemythos5.py, claudemodelpreflight.py | Model-specific code อยู่ด้วยกัน → เพิ่ม model ใหม่แค่เพิ่มไฟล์ในโฟลเดอร์นี้ |
| claude/capabilities/ | claudecode.py, claudecodeexec.py, claudevision.py, claudethinking.py, claudestructured.py, claudesearch.py, claudeembeddings.py, claude_stream.py | Feature capabilities แยกจาก model implementations |
| claude/tools/ | claudetools.py, claudemcpconnector.py, claudeplugins.py, claude_sandbox.py | Tool integrations เป็น concern เดียวกัน |
| claude/integrations/ | claudegithub.py, claudegit.py, claudefiles.py, claudeexcel.py, claudepowerpoint.py, claudechrome.py | External service integrations |
| claude/orchestration/ | clauderouter.py, claudeworkflow.py, claudeagentssdk.py, claudebatch.py, claudelive.py, claudeinteractive.py, claudesessions.py | Workflow & routing logic |
| claude/optimization/ | claudecostoptimizer.py, claudepromptoptimizer.py, claude_tokens.py | Cost & prompt optimization |
| claude/memory/ | claudememory.py, claudecache.py | Memory & caching |
| claude/rag/ | clauderag.py, clauderesearch.py | RAG pipeline |
| claude/eval/ | claudeeval.py, claudeevals.py, claudeoutputstyles.py | Evaluation framework |
| claude/enterprise/ | claudeadminapi.py, claudecomplianceapi.py, claudeskillsapi.py, claudesettings.py, claudehookspermsplan.py, claude_metrics.py | Enterprise-specific Claude features |

📦 กลุ่มที่ 6: Infrastructure → infrastructure/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| postgres_store.py | infrastructure/stores/postgres.py | Clean Architecture: Infrastructure layer implement repository interfaces ที่กำหนดใน domain layer |
| sqliteengineeringstore.py | infrastructure/stores/sqlite_eng.py | เช่นเดียวกัน |
| engineeringstoreinterface.py | domain/interfaces/engineering_store.py | Interface (Port) ต้องอยู่ใน domain layer, Implementation (Adapter) อยู่ใน infrastructure |
| auth_oidc.py | infrastructure/auth/oidc.py | Auth provider เป็น infrastructure concern |
| scim_service.py | infrastructure/auth/scim.py | SCIM provisioning เป็น infrastructure |
| observability_otel.py | infrastructure/observability/otel.py | OpenTelemetry เป็น infrastructure |

📦 กลุ่มที่ 7: Interfaces → interfaces/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| tui.py | interfaces/cli/tui.py | Terminal UI เป็น presentation layer |
| tui_streaming.py | interfaces/cli/streaming.py | เช่นเดียวกัน |
| sdk_client.py | interfaces/sdk/client.py | SDK client เป็น interface สำหรับ external consumers |
| publicapiv1.py | api/public/v1.py | Public API endpoints แยกจาก internal services |

📦 กลุ่มที่ 8: Tests → tests/{unit,integration,e2e}/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| testconfig.py, testutils.py, test_security.py | tests/unit/ | Unit tests ที่ test isolated units |
| testpostgresstore.py, testauthoidc.py | tests/integration/ | Tests ที่ต้อง connect กับ external resources |
| testfleete2e.py, testdurabilityrestart.py, testhardcrash.py | tests/e2e/ | End-to-end tests |
| testupgrade11evidencesuite.py ... testupgrade20*.py | tests/e2e/testupgrade_suites/ | Upgrade validation suites อยู่ในกลุ่มเดียวกัน |

📦 กลุ่มที่ 9: Documentation → docs/ (reorganized)

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| ARCHITECTURE.md, DATA-FLOW.md, HA-BOUNDARIES.md | docs/architecture/ | Architecture docs อยู่ด้วยกัน |
| SECURITY.md, API-KEYS.md, ENCRYPTION.md, SSO.md, SCIM.md | docs/security/ | Security-related docs |
| COMPLIANCE-EVIDENCE.md, CONTROL-CATALOG.md, DATA-RESIDENCY.md | docs/compliance/ | Compliance & governance docs |
| deployment.md, KUBERNETES.md, SLO.md, DISASTER-RECOVERY.md, runbooks | docs/operations/ | Operations & runbooks |
| 19upgradev1.10.0.md ... 53upgradev1.40.0_*.md | docs/upgrades/ | Upgrade notes เรียงตาม version |
| Upgrade-01.prompt ... Upgrade-23.prompt | docs/prompts/ | Prompt templates อยู่ด้วยกัน |

📦 กลุ่มที่ 10: Build & Scripts → scripts/

| ย้ายจาก | ย้ายไป | เหตุผล |
|---------|---------|--------|
| build.sh, build.bat | scripts/build.sh, scripts/build.bat | Build scripts ไม่ควรอยู่ root |
| setup.sh, setup.bat | scripts/setup.sh, scripts/setup.bat | Setup scripts เช่นเดียวกัน |
| releasegate.py | scripts/releasegate.py | Release automation script |

📦 กลุ่มที่ 11: ต้องลบออกจาก Version Control

| ไฟล์/โฟลเดอร์ | เหตุผล |
|--------------|--------|
| dist/ | Build output → สร้างใหม่ได้ตลอด |
| zcoder.egg-info/ | Package metadata → สร้างใหม่ตอน pip install -e . |
| pycache/ | Compiled bytecode → สร้างใหม่อัตโนมัติ |
| crashtest.db-shm, crashtest.db-wal | SQLite WAL files → เป็น test artifacts |
| durabilitytest.db-shm, durabilitytest.db-wal | เช่นเดียวกัน |

.gitignore ที่ต้องเพิ่ม

Python
pycache/
*.py[cod]
*$py.class
*.so
*.egg-info/
dist/
build/
*.egg

Virtual environments
.venv/
venv/
env/

IDE
.idea/
.vscode/
*.swp
*.swo

Database
*.db
*.db-shm
*.db-wal

OS
.DS_Store
Thumbs.db

Environment
.env
.env.local

Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

mypy
.mypy_cache/

Dependency Rules (Clean Architecture)

┌─────────────────────────────────────────────┐
│              interfaces/ (CLI, SDK)          │  ← Presentation
│              api/ (REST endpoints)           │
├─────────────────────────────────────────────┤
│              services/ (Application logic)   │  ← Application
├─────────────────────────────────────────────┤
│              domain/ (Models, Services,      │  ← Domain
│                       Interfaces/Ports)      │
├─────────────────────────────────────────────┤
│              infrastructure/ (Stores, Auth,  │  ← Infrastructure
│                              Observability)  │
└─────────────────────────────────────────────┘

กฎสำคัญ: Dependency ต้องชี้ เข้าข้างใน เท่านั้น
interfaces/ → services/ → domain/ ← infrastructure/
domain/ ห้าม import จาก infrastructure/, interfaces/, หรือ api/
infrastructure/ implement interfaces ที่กำหนดใน domain/

แผนการ Migrate (แนะนำให้ทำทีละ step)

| Step | งาน | ความเสี่ยง |
|------|-----|-----------|
| 1 | เพิ่ม .gitignore + ลบ build artifacts ออกจาก git | 🟢 ต่ำ |
| 2 | สร้าง src/zcoder/ + ย้าย main.py, config.py, exceptions.py, utils.py | 🟢 ต่ำ |
| 3 | ย้าย domain models → domain/models/ | 🟡 ปานกลาง (ต้อง update imports) |
| 4 | ย้าย infrastructure (stores, auth) → infrastructure/ | 🟡 ปานกลาง |
| 5 | จัดกลุ่ม claude_* → claude/ sub-packages | 🟡 ปานกลาง (ไฟล์เยอะสุด) |
| 6 | ย้าย interfaces (tui, sdk) → interfaces/ | 🟢 ต่ำ |
| 7 | จัด tests → unit/integration/e2e | 🟢 ต่ำ |
| 8 | จัด docs → หมวดหมู่ | 🟢 ต่ำ |
| 9 | Update pyproject.toml ให้ชี้ src/zcoder | 🟡 ปานกลาง |
| 10 | รัน tests ทั้งหมด + verify CI/CD | 🔴 สูง (final validation) |

💡 คำแนะนำ: แต่ละ step ควรเป็น 1 commit แยกกัน เพื่อให้ง่ายต่อการ revert ถ้ามีปัญหา และควรทำใน branch แยก (refactor/restructure) ก่อน merge เข้า main

generate ไฟล์ mapping script (Python/Bash) สำหรับย้ายไฟล์อัตโนมัติ ช่วยเขียน pyproject.toml ใหม่ให้สอดคล้องกับ src layout 
