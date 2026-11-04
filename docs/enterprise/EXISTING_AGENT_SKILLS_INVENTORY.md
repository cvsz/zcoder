# Existing Agent and Skills Inventory

**Generated:** 2026-11-04
**Repository:** `/home/cvsz/zcoder`
**Purpose:** Inventory of all existing agents and skills for the AUSI ecosystem implementation

## Agent Definitions

### Agent System Prompts (`src/zcoder/agent/personalities.py`)

| Agent Role | System Prompt | Purpose |
|------------|--------------|---------|
| `code_generator` | "You are a full-project code generation agent. Produce complete, runnable code for the request, not a partial sketch." | Full-project code generation |
| `code_reviewer` | "You are a code review agent. Focus on correctness, readability, and maintainability; call out concrete issues with line-level detail." | Code review and quality assessment |
| `testing_agent` | "You are a testing agent. Produce comprehensive test suites, covering edge cases and failure modes, not just the happy path." | Test generation and validation |
| `documentation_agent` | "You are a documentation agent. Write clear docs, READMEs, and API references aimed at a reader new to this codebase." | Documentation engineering |
| `optimizer` | "You are a performance optimization agent. Identify concrete bottlenecks and propose measurable improvements." | Performance optimization |
| `security_auditor` | "You are a security audit agent. Review for vulnerabilities (injection, auth, secrets handling, unsafe deserialization, etc.) and rate severity for each finding." | Security auditing |
| `full_stack` | "You are a full-stack engineering agent. Consider frontend, backend, and data-layer concerns together when responding." | Full-stack engineering |

### Personality Styles (`src/zcoder/agent/personalities.py`)

| Style Name | Description | When to Use |
|------------|-------------|-------------|
| `precise` | Be concise, technical, and precise. Avoid fluff. | Technical discussions, API calls |
| `teaching` | Explain concepts clearly, step by step, as if teaching a beginner. | Onboarding, education, learning |
| `creative` | Be inventive and think outside the box. | Brainstorming, creative problem-solving |
| `socratic` | Ask probing questions and guide the user to discover answers. | Socratic dialogue, discovery-based learning |
| `pragmatic` | Focus on practical, working solutions over theory. | Production Deadlines, pragmatic solutions |

### Agent Registry

**Location:** `src/zcoder/agent/personalities.py` (lines 18-34)

**Registry format:**
```python
AGENT_SYSTEM_PROMPTS = {
    "code_generator": "...",
    "code_reviewer": "...",
    "testing_agent": "...",
    "documentation_agent": "...",
    "optimizer": "...",
    "security_auditor": "...",
    "full_stack": "...",
}
```

**Usage:** CLI `--agent` flag, `--list-agents` flag, and system prompt injection

## Skills Inventory

### Skill Files (`skills/` directory)

| Skill File | Name | Description | Key Features |
|------------|------|-------------|------------|
| `skills/agy.skill` | `agy` | Agy Super Agentic Intelligence Skill | Codebase investigation, enterprise implementation, systematic analysis |
| `skills/gemini.skill` | `gemini` | Gemini Super Agentic Intelligence Skill | Google Gemini model integration, multimodal analysis, code generation |
| `skills/codex.skill` | `codex` | Codex Super Agentic Intelligence Skill | OpenAI Codex model integration, code generation, refactoring |
| `skills/kilo.skill` | `kilo` | Kilo Super Agentic Intelligence Skill | Kilo provider model routing, diverse model support, flexible investigation |
| `skills/claude.skill` | `claude` | Claude Super Agentic Intelligence Skill | Anthropic Claude model integration, advanced reasoning, tool use |
| `skills/z-git.skill` | `z-git` | Z-Git Skill | Git integration and multi-account merge release protocol |

### Skill Details

#### 1. `agy.skill`

**Activation Criteria:** Assigned to perform deep analysis and independent real implementations

**Core Directives:**
1. Comprehensive systems investigation & root cause analysis
2. Universal fix, upgrade, and full independent implementation
3. Validation and testing until zero errors remain

**Language Policy:**
- Thai for general communication
- English for technical work (code, comments, docs, commits)

**Agent Capabilities:**
- Codebase investigation and architecture analysis
- Bug detection and resolution
- Feature implementation
- Code quality improvement
- Test generation and validation
- Documentation updates

**Agent Subdirectory (`skills/agy/agents/`):**
- `openai.yaml` - Agent interface configuration
  ```yaml
  interface:
    display_name: "Agy Super Full-Stack & Architect Agent"
    short_description: "Agy AI Full-Stack Developer & Systems Architect agentic skill for universal codebase investigation, enterprise production-grade implementation, and multi-account GPG audit/merge release protocol"
    default_prompt: "Use $agy to perform deep codebase investigation, enterprise-grade production fixes, validation tests, and multi-account GitHub audit/merge releases."
  ```

#### 2. `gemini.skill`

**Activation Criteria:** Perform deep analysis and independent real implementations using Google Gemini models

**Core Directives:**
1. Google Gemini model integration (gemini-1.5-flash, gemini-1.5-pro, gemini-1.0-pro)
2. Comprehensive systems investigation & root cause analysis
3. Universal fix, upgrade, and full independent implementation
4. Validation and testing using Gemini-assisted test generation

**Model Selection Guidance:**
- `gemini-1.5-flash` for rapid prototyping and simple tasks
- `gemini-1.5-pro` for complex analysis and code generation
- `gemini-1.0-pro` for legacy compatibility

**Agent Capabilities:**
- Gemini model-assisted codebase investigation
- Multimodal analysis (code, images, diagrams)
- Intelligent code generation and refactoring
- Bug detection and resolution using Gemini reasoning
- Test case generation
- Documentation creation and updates
- Prompt engineering for optimal Gemini performance

#### 3. `codex.skill`

**Activation Criteria:** Perform deep analysis and independent real implementations using OpenAI Codex models

**Core Directives:**
1. OpenAI Codex model integration (codex, code-davinci-002, code-davinci-003, gpt-4-codex, gpt-4o-mini)
2. Comprehensive systems investigation & root cause analysis
3. Universal fix, upgrade, and full independent implementation
4. Validation and testing using Codex-assisted test generation

**Model Selection Guidance:**
- `code-davinci-002` for simple code completion
- `code-davinci-003` for moderate complexity tasks
- `gpt-4-codex` or `gpt-4o-mini` for complex code generation and analysis

**Agent Capabilities:**
- OpenAI Codex model-assisted codebase investigation
- Code generation and completion in multiple programming languages
- Code explanation and documentation generation
- Bug detection and resolution using code analysis
- Test case generation
- Refactoring and optimization suggestions
- Architecture analysis and recommendations
- Prompt engineering for optimal Codex performance

#### 4. `kilo.skill`

**Activation Criteria:** Perform deep analysis and independent real implementations using the Kilo provider's extensive model catalog

**Core Directives:**
1. Kilo provider model integration (vast catalog including Claude, Gemini, GPT, LLaMA, Mistral, and many other AI models)
2. Comprehensive model routing & selection
3. Comprehensive systems investigation & root cause analysis
4. Universal fix, upgrade, and full independent implementation
5. Validation and testing using most appropriate Kilo model

**Model Selection Guidance:**
- **Coding/Development:** `kilo/openai/gpt-5`, `kilo/anthropic/claude-opus-4.1`, `kilo/mistralai/codestral-2508`
- **Reasoning/Analysis:** `kilo/nvidia/nemotron-3.5-super-vl`, `kilo/deepseek/deepseek-v4-pro`
- **Fast/Simple Tasks:** `kilo/kilo-auto/efficient`, `kilo/kilo-auto/small`
- **Vision/Multimodal:** `kilo/google/gemini-3.5-flash`, `kilo/nvidia/nemotron-3.5-super-vl`
- **Specialized:** Domain-specific models from the Kilo catalog

**Agent Capabilities:**
- Kilo provider model routing and selection across hundreds of models
- Intelligent task-to-model matching for optimal performance
- Codebase investigation using model-specific strengths
- Multi-model comparison and validation
- Code generation and refactoring using best-fit models
- Debugging and analysis with specialized reasoning models
- Multimodal analysis using vision-capable models
- Access to latest models from Anthropic, OpenAI, Google, NVIDIA, and more
- Kilo auto-balanced routing (`kilo/kilo-auto/balanced`, `kilo/kilo-auto/efficient`, `kilo/kilo-auto/free`)

#### 5. `claude.skill`

**Activation Criteria:** Perform deep analysis and independent real implementations using Anthropic Claude models

**Core Directives:**
1. Anthropic Claude model integration (claude-opus-4.1, claude-sonnet-4.5, claude-haiku-4.5, claude-fable-5.1)
2. Comprehensive systems investigation & root cause analysis
3. Universal fix, upgrade, and full independent implementation
4. Validation and testing using Claude-assisted test generation

**Model Selection Guidance:**
- `claude-haiku-4.5` for rapid prototyping and simple tasks
- `claude-sonnet-4.5` for complex analysis and code generation (balanced choice)
- `claude-opus-4.1` for peak performance on complex tasks

**Agent Capabilities:**
- Anthropic Claude model-assisted codebase investigation
- Advanced reasoning and chain-of-thought processing
- Code generation and refactoring in multiple programming languages
- Code explanation and documentation generation
- Bug detection and resolution using sophisticated analysis
- Test case generation
- Architecture analysis and recommendations
- Tool use and API integration assistance
- Prompt engineering for optimal Claude performance

#### 6. `z-git.skill`

**Activation Criteria:** Git integration and multi-account merge release protocol

**Note:** The skill file appears to be binary/encrypted (PKZIP format), containing:
- `SKILL.md` - Skill metadata
- `agents/openai.yaml` - Agent interface configuration
- Potentially other binary content

**Interface (from YAML excerpt):**
```yaml
interface:
  display_name: (binary content)
  short_description: (binary content)
  default_prompt: (binary content)
```

## MCP (Model Control Protocol) Integration

### MCP Servers

No dedicated MCP servers currently implemented in the repository. The skills system provides equivalent functionality through:

- Skill files with embedded system prompts
- Agent registry with system prompt definitions
- Makefile targets for OpenCode integration

### Tool Integration

Skills integrate with the following through the agent framework:

| Integration | Status | Notes |
|-------------|--------|-------|
| `MCP tool integration` | ⚠️ | Not explicitly implemented, but architecture supports it |
| Git integration | ✅ | Via `skills/z-git.skill` and `zcoder.agent.integrations.git` |
| File operations | ✅ | Via `zcoder.agent.tools` and `zcoder.infrastructure.filesystem` |
| Code execution | ✅ | Via `zcoder.agent.capabilities.code` |
| Web search | ⚠️ | Configured via environment variables, not skill-integrated |
| Database access | ✅ | Via `zcoder.services` and PostgreSQL adapters |

## Provider Compatibility Matrix

### Verified Provider Capabilities

| Provider | CLI/API | Models Listed | Free Models | Key Integration |
|----------|---------|---------------|-------------|-----------------|
| **OpenCode** | ✅ Makefile | ✅ Yes (10 targets) | ✅ Yes (`opencode/nemotron-3.5-lightning-free`) | Full Makefile integration |
| **NVIDIA** | ✅ `.env` config | ✅ Yes (`opencode-nvidia-models`) | ✅ Yes (`kilo/nvidia/nemotron-3.5-super-vl:free`) | API key + base URL in .env |
| **Google Gemini** | ✅ `.env` config | Partially | ✅ Yes (`gemini-2.5-flash-lite`) | API key + base URL in .env |
| **OpenAI/OpenRouter** | ✅ `.env` config | Partially | ✅ Yes (`openrouter/free`) | API key + base URL in .env |
| **Kilo** | ✅ `.env` config | ✅ Yes (`opencode-kilo-models`) | ✅ Yes (`kilo/nvidia/nemotron-3.5-super-vl:free`) | API key + base URL in .env |
| **Anthropic Claude** | ✅ Built-in | ✅ Yes (registry.py) | ❌ No (commercial) | Model catalog + API integration |
| **xAI/Groq/Cerebras** | ✅ `.env` config | Partially | Varies | Configured in .env |
| **Local/GGUF** | ✅ Scripts | ✅ Yes (llama.cpp) | ✅ Yes (local only) | `scripts/local_postgres.py`, models/ directory |

### Free-Tier Eligibility

| Provider | Free Model Available | Free Tier Limits | Notes |
|----------|---------------------|------------------|-------|
| OpenCode | ✅ `opencode/nemotron-3.5-lightning-free` | Unknown | Requires OPENCODE_API_KEY |
| NVIDIA | ✅ `kilo/nvidia/nemotron-3.5-super-vl:free` | Unknown | Via Kilo gateway |
| Google Gemini | ✅ `gemini-2.5-flash-lite` | Unknown | Via GEMINI_API_KEY |
| OpenRouter | ✅ `openrouter/free` | Unknown | Via OPENROUTER_API_KEY |
| Kilo | ✅ `kilo/nvidia/nemotron-3.5-super-vl:free` | Unknown | Via Kilo gateway |
| Anthropic Claude | ❌ | N/A | Commercial only |
| xAI/Groq | ✅ Varies | Unknown | Via API keys in .env |

## Testing Inventory

### Unit Tests (~135 files)

Key test files related to agents and skills:

- `test_skills_registry.py` - Skills registry behavior
- `test_agent_messaging_adapter.py` - Agent messaging
- `test_agent_runtime.py` - Agent runtime execution
- `test_claude_models_deprecation.py` - Model deprecation tracking
- `test_claude_skills_api.py` - Claude Skills API
- `test_codeagent_skill_slash.py` - Code agent slash commands
- `test_subagent_registry.py` - Subagent registry
- `test_subagent_tool_validation.py` - Subagent tool validation

### Integration Tests (~20 files)

- `test_postgres_store.py` - PostgreSQL store integration
- `test_postgres_multiprocess.py` - Multi-process PostgreSQL
- `test_source_of_truth_conformance.py` - Source of truth conformance
- `test_upgrade_fence_multiprocess.py` - Upgrade fence testing

### E2E Tests (Multiple suites)

- `test_enterprise_suite.py` - Enterprise product scenarios
- `test_fleet_e2e.py` - Fleet execution scenarios
- `test_continuous_engineering_*.py` - Continuous engineering workflows

## Documentation Inventory

### Root-Level Documents (Conventional Entry Points)

| File | Status | Purpose |
|------|--------|---------|
| `README.md` | ✅ | Project entry point |
| `AGENTS.md` | ✅ | Workflow conventions |
| `SECURITY.md` | ✅ | Security guidelines |
| `QUICKSTART.md` | ✅ | Quick start guide |
| `ARCHITECTURE.md` | ✅ | Repository architecture |

### Docs Taxonomy

| Directory | Contents | Status |
|-----------|----------|--------|
| `docs/architecture/` | ADRs, architecture decisions | ✅ Populated |
| `docs/security/` | Security assessments | ✅ Populated |
| `docs/compliance/` | Compliance documents | ✅ Populated |
| `docs/operations/` | Runbooks, operations guides | ✅ Populated |
| `docs/enterprise/` | Enterprise configurations | ✅ Populated |
| `docs/guides/` | Usage guides | ✅ Populated |
| `docs/upgrades/` | Upgrade instructions | ✅ Populated |
| `docs/prompts/` | Prompt templates | ✅ Populated |

### Missing Documentation (per ausi-master-prompt.md §12)

Documents that need to be created to complete the documentation taxonomy:

1. `AUSI_ARCHITECTURE.md` - AUSI-specific architecture document
2. `PROVIDERS.md` - Provider compatibility and integration guide
3. `MODEL_ROUTING.md` - Model routing and cost optimization
4. `MULTI_AGENT_ORCHESTRATION.md` - Multi-agent orchestration documentation
5. `TESTING.md` - Testing strategy and execution guide
6. `TROUBLESHOOTING.md` - Troubleshooting guide

## GitHub Governance Status

| Governance Item | Status | Evidence |
|-----------------|--------|----------|
| Branch inspection before changes | ✅ | `git status` checked before modifications |
| Uncommitted work preserved | ✅ | 14 modified files, 22 untracked preserved |
| Feature branch usage | ✅ | Current branch: `feat/makefile-opencode-prompt` |
| Signed commits | ⚠️ | Not configured (check GPG status) |
| Branch protection not bypassed | ✅ | Working on feature branch |
| Independent review not auto-approving | ✅ | No self-approval policy |
| `policedbc` for independent review | ⚠️ | Concept understood, not implemented |
| `cvsz` for authorized merge | ⚠️ | Concept understood, not configured |

## Summary Tables

### Skills Quick Reference

| Skill | Provider | Free Model | Key Focus | Make Target |
|-------|----------|------------|-----------|-------------|
| agy | Generic/Universal | N/A | Codebase investigation, implementation | N/A |
| gemini | Google Gemini | `gemini-2.5-flash-lite` | multimodal, code gen | N/A |
| codex | OpenAI Codex | N/A | Code generation, refactoring | N/A |
| kilo | Kilo provider | `kilo/nvidia/nemotron-3.5-super-vl:free` | Model routing, diverse models | N/A |
| claude | Anthropic Claude | N/A | Advanced reasoning, tool use | N/A |
| z-git | Git operations | N/A | Git integration, merge protocol | N/A |

### Agent Quick Reference

| Agent Role | CLI Flag | System Prompt Source | Best For |
|------------|----------|----------------------|----------|
| code_generator | `--agent code_generator` | `AGENT_SYSTEM_PROMPTS` | Full project code generation |
| code_reviewer | `--agent code_reviewer` | `AGENT_SYSTEM_PROMPTS` | Code review with line-level detail |
| testing_agent | `--agent testing_agent` | `AGENT_SYSTEM_PROMPTS` | Comprehensive test suites |
| documentation_agent | `--agent documentation_agent` | `AGENT_SYSTEM_PROMPTS` | Documentation writing |
| optimizer | `--agent optimizer` | `AGENT_SYSTEM_PROMPTS` | Performance bottleneck identification |
| security_auditor | `--agent security_auditor` | `AGENT_SYSTEM_PROMPTS` | Security vulnerability review |
| full_stack | `--agent full_stack` | `AGENT_SYSTEM_PROMPTS` | Full-stack engineering concerns |

### Makefile OpenCode Targets Quick Reference

| Target | Description | Free Model |
|--------|-------------|------------|
| `make opencode` | Run OpenCode CLI (loads .env) | Uses `OPENCODE_MODEL` |
| `make opencode-prompt PROMPT` | Execute prompt via OpenCode | Uses `OPENCODE_MODEL` |
| `make opencode-free-prompt PROMPT` | Execute prompt using 100% Free Model | Uses `OPENCODE_FREE_MODEL` = `opencode/nemotron-3.5-lightning-free` |
| `make opencode-bg PROMPT` | Run OpenCode prompt in background | Uses `OPENCODE_MODEL` |
| `make opencode-free-bg PROMPT` | Run OpenCode free model in background | Uses `OPENCODE_FREE_MODEL` |
| `make opencode-models` | List all available OpenCode models | N/A |
| `make opencode-free-models` | List all free models (NVIDIA, OpenCode, Kilo) | Reports free models |
| `make opencode-nvidia-models` | List NVIDIA Nemotron & NIM models | Reports NVIDIA models |
| `make opencode-kilo-models` | List Kilo models & free routers | Reports Kilo models |
| `make opencode-all` | Display all skills and models | Reports all skills + models |