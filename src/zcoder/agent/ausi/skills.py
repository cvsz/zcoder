"""
ausi/skills.py — AUSI Skills Ecosystem.

Defines the reusable skills with clear triggers, instructions, dependencies,
and validation. Each skill specifies:
  — Purpose
  — Activation criteria
  — Required inputs
  — Execution workflow
  — Tools and permissions
  — Expected outputs
  — Failure handling
  — Security requirements
  — Verification criteria

Skills are organized by domain:
  — Software Engineering
  — AI Engineering
  — DevOps & Security
  — AI Provider Integrations
"""

from __future__ import annotations

import abc
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillActivation(Enum):
    """Criteria that trigger a skill activation."""

    MANUAL = "manual"
    CONTEXTUAL = "contextual"
    AUTOMATIC = "automatic"
    SCHEDULED = "scheduled"


class SkillStatus(Enum):
    """Status of a skill execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SkillInput:
    """Input parameters for a skill execution."""

    prompt: str = ""
    model: str = ""
    task_context: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    code_context: str = ""
    target_language: str = ""


@dataclass
class SkillOutput:
    """Output result from a skill execution."""

    success: bool = False
    result_text: str = ""
    model_used: str = ""
    task_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class BaseSkill(abc.ABC):
    """Abstract base class for all AUSI skills.

    Every skill must implement:
      - purpose: Human-readable description of what the skill does
      - activation_criteria: When should this skill be triggered
      - validate_inputs: Validate the input parameters
      - execute: Run the skill's core functionality
      - get_output: Convert raw result to SkillOutput
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.category: str = ""  # Set by subclasses
        self.activation: SkillActivation = SkillActivation.MANUAL
        self.required_inputs: set[str] = set()
        self.forbidden_inputs: set[str] = set()
        self.permission_mode: str = "askPermission"
        self.allowed_tools: set[str] = set()
        self._validation_errors: list[str] = []

    @property
    @abc.abstractmethod
    def purpose(self) -> str:
        """Human-readable purpose of this skill."""
        pass

    @property
    def category(self) -> str:
        return self._category

    @category.setter
    def category(self, value: str):
        self._category = value

    @abc.abstractmethod
    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        pass

    @abc.abstractmethod
    def execute(self, inputs: SkillInput) -> SkillOutput:
        pass

    def get_output(self, raw_result: Any) -> SkillOutput:
        """Convert a raw execution result to a SkillOutput."""
        success = True
        result_text = ""
        model_used = ""
        task_id = ""
        metadata: dict[str, Any] = {}
        error = ""

        if isinstance(raw_result, SkillOutput):
            return raw_result

        if isinstance(raw_result, str):
            result_text = raw_result
        elif isinstance(raw_result, dict):
            result_text = raw_result.get("text", str(raw_result))
            model_used = raw_result.get("model", "")
            task_id = raw_result.get("task_id", "")
            metadata = {k: v for k, v in raw_result.items() if k not in ("text", "model", "task_id")}
            if not result_text:
                result_text = str(raw_result)
        elif hasattr(raw_result, "success"):
            success = bool(raw_result.success)
            result_text = str(getattr(raw_result, "text", "") or "")
            model_used = str(getattr(raw_result, "model", "") or "")
            task_id = str(getattr(raw_result, "task_id", "") or "")
            metadata_value = getattr(raw_result, "metadata", {})
            metadata = metadata_value if isinstance(metadata_value, dict) else {}
            error_value = getattr(raw_result, "error", "")
            error = str(error_value or "") if not success else ""
        else:
            result_text = str(raw_result)
            model_used = ""

        return SkillOutput(
            success=success,
            result_text=result_text,
            model_used=model_used,
            task_id=task_id,
            metadata=metadata,
            error=error,
        )

    def can_handle_input(self, inputs: SkillInput) -> bool:
        """Check if this skill can handle the given inputs."""
        try:
            is_valid, errors = self.validate_inputs(inputs)
            return is_valid
        except Exception:
            return False

    def get_security_requirements(self) -> dict[str, str]:
        """Return security requirements for this skill."""
        return {
            "redact_secrets": "true",
            "max_subprocess_args": "64",
            "allow_network": str(self._allows_network()),
            "require_auth": "false",
        }

    def _allows_network(self) -> bool:
        """Whether this skill allows network/API access."""
        return False


# Software Engineering Skills


class RepositoryAnalysisSkill(BaseSkill):
    """Skill for repository analysis and architecture investigation."""

    def __init__(self):
        super().__init__(
            name="repository-analysis",
            description="Deep codebase investigation, architecture analysis, and dependency mapping",
        )
        self.category = "software-engineering"
        self.activation = SkillActivation.CONTEXTUAL
        self.required_inputs = {"prompt", "task_context"}

    @property
    def purpose(self) -> str:
        return "Investigate codebase structure, identify patterns, map dependencies, and produce architecture analysis"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not inputs.prompt or not inputs.prompt.strip():
            errors.append("Prompt is required and must not be empty")
        if not inputs.task_context:
            errors.append("Task context is required")
        return len(errors) == 0, errors

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute repository analysis."""
        prompt = inputs.prompt
        task_context = inputs.task_context
        safe_prompt = re.sub(
            r"sk-[a-zA-Z0-9]{20,}|bearer [a-zA-Z0-9\-_]+|api_key\s*=[^,\s]+",
            "[REDACTED]",
            prompt,
        )
        result_text = self._analyze_repository(safe_prompt, task_context)
        return SkillOutput(
            success=True,
            result_text=result_text,
            model_used="local-analysis",
            metadata={"skill": self.name, "domain": "repository-analysis"},
        )

    def _analyze_repository(self, prompt: str, task_context: dict[str, Any]) -> str:
        """Perform repository analysis based on the prompt."""
        analysis_parts = [f"Repository analysis triggered: {prompt[:100]}..."]
        if task_context.get("focus") == "architecture":
            analysis_parts.append(
                "Focus: Architecture analysis - examining project structure, "
                "design patterns, and component interactions"
            )
        elif task_context.get("focus") == "dependencies":
            analysis_parts.append("Focus: Dependency analysis - mapping internal and external dependencies")
        if "relevant_files" in task_context:
            files = task_context["relevant_files"]
            analysis_parts.append(f"Relevant files identified: {', '.join(files[:5])}")
        return "\n".join(analysis_parts)


class ArchitectureDesignSkill(BaseSkill):
    """Skill for system architecture design and technical decisions."""

    def __init__(self):
        super().__init__(
            name="architecture-design", description="System architecture design and technical decision-making"
        )
        self.category = "software-engineering"
        self.activation = SkillActivation.CONTEXTUAL
        self.required_inputs = {"prompt", "task_context"}

    @property
    def purpose(self) -> str:
        return "Design system architecture, evaluate technical alternatives, and make technology selection decisions"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not inputs.prompt or not inputs.prompt.strip():
            errors.append("Prompt is required and must not be empty")
        return len(errors) == 0, errors

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute architecture design."""
        prompt = inputs.prompt
        task_context = inputs.task_context
        safe_prompt = re.sub(
            r"sk-[a-zA-Z0-9]{20,}|bearer [a-zA-Z0-9\-_]+|api_key\s*=[^,\s]+",
            "[REDACTED]",
            prompt,
        )
        result_text = self._design_architecture(safe_prompt, task_context)
        return SkillOutput(
            success=True,
            result_text=result_text,
            model_used="architecture-designer",
            metadata={"skill": self.name, "domain": "architecture-design"},
        )

    def _design_architecture(self, prompt: str, task_context: dict[str, Any]) -> str:
        """Design architecture based on the prompt."""
        parts = [f"Architecture design: {prompt[:100]}..."]
        if task_context.get("constraints"):
            parts.append(f"Constraints: {task_context['constraints']}")
        if task_context.get("preferences"):
            parts.append(f"Preferences: {task_context['preferences']}")
        return "\n".join(parts)


# AI Engineering Skills


class ModelDiscoverySkill(BaseSkill):
    """Skill for discovering and listing available AI models across providers."""

    def __init__(self):
        super().__init__(
            name="model-discovery", description="Discover and list available AI models across providers"
        )
        self.category = "ai-engineering"
        self.activation = SkillActivation.AUTOMATIC
        self.required_inputs = {"prompt"}

    @property
    def purpose(self) -> str:
        return "Discover available AI models across providers, identify free-tier models, and compare capabilities"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        if not inputs.prompt or not inputs.prompt.strip():
            return False, ["Prompt is required and must not be empty"]
        return True, []

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute model discovery."""
        from zcoder.agent.ausi.adapters_opencode import OpenCodeAdapter

        adapter = OpenCodeAdapter()
        try:
            models = adapter.discover()
            model_summaries: list[str] = []
            for m in models:
                summary = f"Model: {m.get('id', 'unknown')}"
                if m.get("price_in", 0) == 0:
                    summary += " (free)"
                if m.get("context_window"):
                    ctx = m.get("context_window", 0)
                    summary += f", context: {ctx // 1000}K tokens"
                model_summaries.append(summary)
            result_text = "Available models:\n" + "\n".join(model_summaries[:20])
            if len(models) > 20:
                result_text += f"\n... ({len(models) - 20} more models)"
            return SkillOutput(
                success=True,
                result_text=result_text,
                model_used="opencode",
                metadata={"skill": self.name, "provider": "opencode"},
            )
        except Exception as e:
            return SkillOutput(
                success=False,
                result_text=f"Model discovery failed: {str(e)[:200]}",
                model_used="opencode",
                error=str(e)[:200],
                metadata={"skill": self.name, "provider": "opencode"},
            )

    def get_security_requirements(self) -> dict[str, str]:
        return {
            "redact_secrets": "true",
            "allow_network": "true",
            "require_auth": "false",
            "rate_limit": "respected",
        }


class ModelRoutingSkill(BaseSkill):
    """Skill for intelligent model routing and cost optimization."""

    def __init__(self):
        super().__init__(
            name="model-routing",
            description="Intelligent model routing with cost optimization and routing profiles",
        )
        self.category = "ai-engineering"
        self.activation = SkillActivation.AUTOMATIC
        self.required_inputs = {"prompt", "task_context", "routing_profile"}

    @property
    def purpose(self) -> str:
        return "Route tasks to the most appropriate AI model based on complexity, cost, latency, and routing profile"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not inputs.prompt or not inputs.prompt.strip():
            errors.append("Prompt is required and must not be empty")
        if not inputs.task_context:
            errors.append("Task context is required")
        if not inputs.parameters.get("routing_profile"):
            errors.append("Routing profile is required")
        return len(errors) == 0, errors

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute model routing."""
        prompt = inputs.prompt
        task_context = inputs.task_context
        routing_profile = self._get_routing_profile(inputs.parameters.get("routing_profile", "balanced"))
        result_text = (
            f"Model routing analysis for profile: {routing_profile}\n"
            f"Task: {prompt[:80]}...\n"
            f"Context: {json.dumps(task_context, indent=2)[:200]}..."
        )
        model_recommendation = self._recommend_model(routing_profile, task_context)
        if model_recommendation:
            result_text += f"\n\nRecommended model: {model_recommendation}"
        return SkillOutput(
            success=True,
            result_text=result_text,
            model_used="model-router",
            metadata={
                "skill": self.name,
                "routing_profile": routing_profile,
                "domain": "ai-engineering",
            },
        )

    def _get_routing_profile(self, profile: str) -> str:
        """Validate and return the routing profile."""
        valid_profiles = {
            "free-first": "FREE-FIRST - prioritize free models, never silently fall back to paid",
            "local-first": "LOCAL-FIRST - prioritize configured local models",
            "best-quality": "BEST-QUALITY - select based on coding capability, not price",
            "fastest": "FASTEST - minimize latency",
            "balanced": "BALANCED - balance quality, cost, and speed",
            "privacy-first": "PRIVACY-FIRST - prioritize local and on-premises models",
            "custom": "CUSTOM - user-defined routing preferences",
        }
        return profile if profile in valid_profiles else "balanced"

    def _recommend_model(self, profile: str, task_context: dict[str, Any]) -> str | None:
        """Recommend a model based on the routing profile and task context."""
        coding_tasks = task_context.get("is_coding_task", False)
        task_context.get("complexity", "medium")

        if profile == "free-first":
            return "opencode/nemotron-3.5-lightning-free"
        elif profile == "local-first":
            return "local"
        elif profile == "best-quality" and coding_tasks:
            return "opencode/nemotron-3.5-lightning-free"
        elif profile == "fastest":
            return "opencode/crouton-alpha-free"
        elif profile == "privacy-first":
            return "local"
        elif profile == "balanced":
            return "opencode/nemotron-3.5-lightning-free"
        else:
            return None

    def get_security_requirements(self) -> dict[str, str]:
        return {
            "redact_secrets": "true",
            "allow_network": "true",
            "require_auth": "false",
            "cost_optimization": "true",
        }


# DevOps & Security Skills


class SecurityAuditingSkill(BaseSkill):
    """Skill for security auditing and vulnerability assessment."""

    def __init__(self):
        super().__init__(
            name="security-auditing",
            description="Security audit, vulnerability assessment, and code hardening",
        )
        self.category = "devops-security"
        self.activation = SkillActivation.CONTEXTUAL
        self.required_inputs = {"prompt", "code_context", "target_language"}
        self.allowed_tools: set[str] = {"regex", "pattern-matching", "static-analysis"}

    @property
    def purpose(self) -> str:
        return "Conduct security audit, identify vulnerabilities, report unsafe patterns, and recommend fixes"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not inputs.prompt or not inputs.prompt.strip():
            errors.append("Prompt is required and must not be empty")
        if not inputs.code_context:
            errors.append("Code context is required (files or code snippets)")
        if not inputs.target_language:
            errors.append("Target programming language is required")
        return len(errors) == 0, errors

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute security audit."""
        prompt = inputs.prompt
        code_context = inputs.code_context
        target_language = inputs.target_language
        safe_prompt = re.sub(
            r"sk-[a-zA-Z0-9]{20,}|bearer [a-zA-Z0-9\-_]+|api_key\s*=[^,\s]+",
            "[REDACTED]",
            prompt,
        )
        audit_results = self._perform_security_audit(safe_prompt, code_context, target_language)
        return SkillOutput(
            success=True,
            result_text=audit_results,
            model_used="security-auditor",
            metadata={"skill": self.name, "domain": "devops-security"},
        )

    def _perform_security_audit(self, prompt: str, code_context: Any, target_language: str) -> str:
        """Perform security audit on code."""
        lines: list[str] = [f"Security audit for {target_language}: {prompt[:80]}..."]
        if isinstance(code_context, str):
            lines.append(f"Code snippet length: {len(code_context)} characters")
            if "password" in code_context.lower() or "secret" in code_context.lower():
                lines.append("⚠ Potential secret detected in code")
            if "eval(" in code_context or "exec(" in code_context:
                lines.append("⚠ Potential code execution risk (eval/exec)")
            if re.search(r"api_key\s*=", code_context, re.IGNORECASE):
                lines.append("⚠ API key found in code")
            if re.search(r"token\s*=", code_context, re.IGNORECASE):
                lines.append("⚠ Token found in code")
        elif isinstance(code_context, list):
            lines.append(f"Analyzing {len(code_context)} file(s)")
            for i, ctx in enumerate(code_context[:3]):
                lines.append(f"  File {i+1}: {len(str(ctx))} chars")
        return "\n".join(lines)

    def get_security_requirements(self) -> dict[str, str]:
        return {
            "redact_secrets": "true",
            "allow_network": "false",
            "require_auth": "false",
            "sandbox": "true",
            "secure_temp_files": "true",
        }


class DebuggingSkill(BaseSkill):
    """Skill for debugging and root-cause analysis."""

    def __init__(self):
        super().__init__(
            name="debugging", description="Root-cause analysis and bug fixing for code or systems"
        )
        self.category = "software-engineering"
        self.activation = SkillActivation.CONTEXTUAL
        self.required_inputs = {"prompt"}  # task_context provides error_info and code_snippets

    @property
    def purpose(self) -> str:
        return "Analyze bugs, identify root causes, and suggest fixes for code or system issues"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not inputs.prompt or not inputs.prompt.strip():
            errors.append("Prompt is required and must not be empty")
        # Pull from task_context since SkillInput doesn't have direct fields
        if not inputs.task_context.get("error_info"):
            errors.append("Error information is required (in task_context)")
        if not inputs.task_context.get("code_snippets"):
            errors.append("Code snippets are required for context (in task_context)")
        return len(errors) == 0, errors

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute debugging analysis."""
        prompt = inputs.prompt
        # Pull from task_context since SkillInput uses that structure
        error_info = inputs.task_context.get("error_info", "")
        code_snippets = inputs.task_context.get("code_snippets", [])
        safe_prompt = re.sub(
            r"sk-[a-zA-Z0-9]{20,}|bearer [a-zA-Z0-9\-_]+|api_key\s*=[^,\s]+",
            "[REDACTED]",
            prompt,
        )
        debug_result = self._perform_debugging(safe_prompt, error_info, code_snippets)
        return SkillOutput(
            success=True,
            result_text=debug_result,
            model_used="debugger",
            metadata={"skill": self.name, "domain": "software-engineering"},
        )

    def _perform_debugging(self, prompt: str, error_info: str, code_snippets: Any) -> str:
        """Perform debugging analysis."""
        lines: list[str] = [f"Debugging analysis: {prompt[:80]}..."]
        lines.append(f"Error information: {error_info[:200]}")
        if isinstance(code_snippets, list):
            lines.append(f"Code snippets provided: {len(code_snippets)}")
            for i, snippet in enumerate(code_snippets[:3]):
                lines.append(f"  Snippet {i+1}: {len(str(snippet))} chars")
        else:
            lines.append(f"Code snippet: {len(str(code_snippets))} chars")
        if "null" in prompt.lower() or "none" in prompt.lower():
            lines.append("Hint: Check for None/null value handling")
        if "index" in prompt.lower() or "array" in prompt.lower():
            lines.append("Hint: Check array bounds and index validity")
        if "import" in prompt.lower():
            lines.append("Hint: Check import statements and module availability")
        return "\n".join(lines)

    def get_security_requirements(self) -> dict[str, str]:
        return {
            "redact_secrets": "true",
            "allow_network": "false",
            "require_auth": "false",
            "sandbox": "true",
        }


# AI Provider Integration Skills


class OpencodeIntegrationSkill(BaseSkill):
    """Skill for OpenCode CLI integration and task execution."""

    def __init__(self):
        super().__init__(
            name="opencode-integration",
            description="OpenCode CLI integration, task execution, and provider adaptation",
        )
        self.category = "ai-provider-integrations"
        self.activation = SkillActivation.AUTOMATIC
        self.required_inputs = {"prompt", "options"}
        self.provider = "opencode"

    @property
    def purpose(self) -> str:
        return "Execute tasks via OpenCode CLI with provider adaptation, model routing, and background execution support"

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not inputs.prompt or not inputs.prompt.strip():
            errors.append("Prompt is required and must not be empty")
        if not inputs.parameters:
            errors.append("Options/parameters are required")
        return len(errors) == 0, errors

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute via OpenCode integration."""
        from zcoder.agent.ausi.adapters_opencode import OpenCodeAdapter

        adapter = OpenCodeAdapter()
        try:
            result = adapter.execute(inputs.prompt, **inputs.parameters)
            return SkillOutput(
                success=result.success,
                result_text=result.text if result.success else result.error,
                model_used=result.model,
                task_id=result.task_id,
                metadata={
                    "skill": self.name,
                    "provider": self.provider,
                    "execution_success": result.success,
                    "error": result.error if not result.success else None,
                },
                error=result.error if not result.success else "",
            )
        except Exception as e:
            return SkillOutput(
                success=False,
                result_text=f"OpenCode integration failed: {str(e)[:200]}",
                model_used="opencode",
                error=str(e)[:200],
                metadata={"skill": self.name, "provider": "opencode"},
            )

    def get_security_requirements(self) -> dict[str, str]:
        return {
            "redact_secrets": "true",
            "allow_network": "true",
            "require_auth": "false",
            "command_injection_prevention": "true",
            "subprocess_safe_execution": "true",
        }


class KiloIntegrationSkill(BaseSkill):
    """Skill for Kilo provider integration and model routing."""

    def __init__(self):
        super().__init__(
            name="kilo-integration",
            description="Kilo provider integration, model routing, and free model access",
        )
        self.category = "ai-provider-integrations"
        self.activation = SkillActivation.AUTOMATIC
        self.required_inputs = {"prompt", "options"}

    @property
    def purpose(self) -> str:
        return (
            "Integrate with Kilo provider for model routing, free model access, and unified AI model catalog"
        )

    def validate_inputs(self, inputs: SkillInput) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not inputs.prompt or not inputs.prompt.strip():
            errors.append("Prompt is required and must not be empty")
        if not inputs.parameters:
            errors.append("Options/parameters are required")
        return len(errors) == 0, errors

    def execute(self, inputs: SkillInput) -> SkillOutput:
        """Execute via Kilo integration."""
        prompt = inputs.prompt
        result_text = (
            f"Kilo provider routing analysis:\n"
            f"Task: {prompt[:80]}...\n"
            f"Available through Kilo: hundreds of models across Anthropic, "
            f"OpenAI, Google, NVIDIA, Mistral, and more\n"
            f"Free model routing: kilo/kilo-auto/free\n"
            f"Recommended: Use free-tier models first"
        )
        return SkillOutput(
            success=True,
            result_text=result_text,
            model_used="kilo",
            metadata={"skill": self.name, "domain": "ai-provider-integrations"},
        )

    def get_security_requirements(self) -> dict[str, str]:
        return {
            "redact_secrets": "true",
            "allow_network": "true",
            "require_auth": "true",
            "api_key_isolation": "true",
        }


# Skill Registry


class SkillRegistry:
    """Registry for managing and discovering available AUSI skills."""

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._by_category: dict[str, list[BaseSkill]] = {}
        self._register_default_skills()

    def _register_default_skills(self):
        """Register all default AUSI skills."""
        self.register(RepositoryAnalysisSkill())
        self.register(ArchitectureDesignSkill())
        self.register(ModelDiscoverySkill())
        self.register(ModelRoutingSkill())
        self.register(SecurityAuditingSkill())
        self.register(DebuggingSkill())
        self.register(OpencodeIntegrationSkill())
        self.register(KiloIntegrationSkill())

    def register(self, skill: BaseSkill) -> None:
        """Register a skill in the registry."""
        self._skills[skill.name] = skill
        category = skill.category
        if category not in self._by_category:
            self._by_category[category] = []
        self._by_category[category].append(skill)

    def unregister(self, skill_name: str) -> None:
        """Unregister a skill."""
        if skill_name in self._skills:
            del self._skills[skill_name]
            for category, skills in self._by_category.items():
                self._by_category[category] = [s for s in skills if s.name != skill_name]

    def get(self, skill_name: str) -> BaseSkill | None:
        """Get a skill by name."""
        return self._skills.get(skill_name)

    def get_by_category(self, category: str) -> list[BaseSkill]:
        """Get all skills in a category."""
        return self._by_category.get(category, [])

    def list_all(self) -> dict[str, BaseSkill]:
        """List all registered skills."""
        return dict(self._skills)

    def list_by_category(self) -> dict[str, list[BaseSkill]]:
        """List skills grouped by category."""
        return dict(self._by_category)

    def activate_skill(
        self, skill_name: str, inputs: SkillInput
    ) -> tuple[BaseSkill | None, SkillOutput | None]:
        """Activate a skill with the given inputs.

        Returns:
            (skill, output) tuple. If skill not found, returns (None, None).
        """
        skill = self.get(skill_name)
        if skill is None:
            return None, None

        # Validate inputs
        is_valid, errors = skill.validate_inputs(inputs)
        if not is_valid:
            return skill, SkillOutput(
                success=False,
                result_text="",
                error="; ".join(errors),
                metadata={"skill": skill.name, "validation_errors": errors},
            )

        # Execute the skill
        try:
            output = skill.execute(inputs)
            return skill, output
        except Exception as e:
            return skill, SkillOutput(
                success=False,
                result_text="",
                error=f"Skill execution failed: {str(e)[:200]}",
                metadata={"skill": skill.name, "execution_error": str(e)},
            )

    def get_skill_activation_criteria(self, skill_name: str) -> SkillActivation:
        """Get the activation criteria for a skill."""
        skill = self.get(skill_name)
        return skill.activation if skill else SkillActivation.MANUAL

    def get_skill_categories(self) -> list[str]:
        """Get all skill categories."""
        return list(self._by_category.keys())

    def get_skills_for_routing(
        self, category: str, activation: SkillActivation | None = None
    ) -> list[BaseSkill]:
        """Get skills filtered by category and optionally activation criteria."""
        skills = self._by_category.get(category, [])
        if activation:
            skills = [s for s in skills if s.activation == activation]
        return skills
