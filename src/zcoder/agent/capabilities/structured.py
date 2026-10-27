"""
claude_structured.py — Structured Outputs
ZCoder CLI v1.30.0

Force Claude to respond in validated JSON matching a schema.
Uses the output_config.format parameter — GA on the Claude API for
Claude Fable 5, Claude Mythos 5, Claude Opus 4.8, Claude Mythos Preview,
Claude Opus 4.7, Claude Opus 4.6, Claude Sonnet 5, Claude Sonnet 4.6,
Claude Sonnet 4.5, Claude Opus 4.5, and Claude Haiku 4.5. No beta header
required (the old structured-outputs-2025-11-13 header still works
during Anthropic's transition period, but sending it unconditionally on
every request is dead weight now that GA doesn't need it — removed in
v1.30.0, see docs/42_upgrade_v1.30.0.md).

Modes:
  • json_object   — Any valid JSON object (no schema)
  • json_schema   — Strict JSON matching a given JSON Schema
  • Tool schemas  — strict:true on tool input_schema

CLI flags:
  --structured             Enable JSON output mode
  --schema FILE            Path to a JSON Schema file
  --schema-inline TEXT     Inline JSON Schema string
  --structured-extract     Extract structured data from text/files
"""

import json
from pathlib import Path

from zcoder.services.coder import Coder


class StructuredCoder:
    """Local model client for structured JSON outputs."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-5", max_tokens: int = 4096):
        # `api_key` stays in the constructor for source compatibility. Local
        # inference does not read or transmit it.
        self.api_key = ""
        self.model = model
        self.max_tokens = max_tokens

    def _generate_json(self, prompt: str, system: str | None = None) -> dict:
        result = Coder(model=self.model, max_tokens=self.max_tokens).generate(
            prompt,
            system=(system or "") + "\nReturn only one valid JSON object. Do not use markdown fences.",
        )
        if not isinstance(result, str) or result.startswith("[ERROR]"):
            raise RuntimeError(result if isinstance(result, str) else "Local model returned no text")
        return json.loads(result)

    # ── JSON object mode ──────────────────────────────────────────────────

    def json_object(self, prompt: str, system: str | None = None) -> dict:
        """Return any valid JSON object. No schema enforcement."""
        return self._generate_json(prompt, system)

    # ── JSON schema mode ──────────────────────────────────────────────────

    def json_schema(self, prompt: str, schema: dict, name: str = "output", system: str | None = None) -> dict:
        """Return JSON validated against a JSON Schema."""
        schema_prompt = (
            f"Return JSON conforming exactly to this JSON Schema named {name}:\n"
            f"{json.dumps(schema, ensure_ascii=False)}\n\n{prompt}"
        )
        parsed = self._generate_json(schema_prompt, system)
        self._validate(parsed, schema)
        return parsed

    # ── Extract structured data from content ──────────────────────────────

    def extract(self, content: str, schema: dict, instruction: str = "") -> dict:
        """Extract structured data from unstructured text."""
        prompt = (
            f"Extract structured data from the following content.\n"
            f"{('Instructions: ' + instruction) if instruction else ''}\n\n"
            f"Content:\n{content}"
        )
        return self.json_schema(
            prompt,
            schema,
            system="Extract exactly the fields defined in the schema. "
            "If a field is missing from the content, use null.",
        )

    # ── Code analysis structured ──────────────────────────────────────────

    def analyse_code(self, code: str, language: str = "") -> dict:
        """Return a structured code analysis report."""
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "language": {"type": "string"},
                "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                            "line": {"type": ["integer", "null"]},
                            "description": {"type": "string"},
                        },
                        "required": ["severity", "description"],
                    },
                },
                "suggestions": {"type": "array", "items": {"type": "string"}},
                "security_flags": {"type": "array", "items": {"type": "string"}},
                "test_coverage": {"type": "string"},
            },
            "required": ["summary", "complexity", "issues", "suggestions"],
        }
        prompt = f"Analyse this {language} code:\n```\n{code}\n```"
        return self.json_schema(
            prompt,
            schema,
            name="code_analysis",
            system="You are a senior code reviewer. Be concise and precise.",
        )

    # ── Validation ────────────────────────────────────────────────────────

    def _validate(self, data: dict, schema: dict):
        """Lightweight required-field check."""
        required = schema.get("required", [])
        missing = [r for r in required if r not in data]
        if missing:
            raise ValueError(f"Schema validation: missing required fields: {missing}")


# ── CLI entry points ───────────────────────────────────────────────────────


def cmd_structured(
    prompt: str,
    api_key: str,
    model: str,
    schema_path: str | None = None,
    schema_inline: str | None = None,
    pretty: bool = True,
) -> dict:
    sc = StructuredCoder(api_key=api_key, model=model)

    if schema_path:
        schema = json.loads(Path(schema_path).read_text())
        print(f"\033[94mℹ Structured output (schema from {schema_path})\033[0m\n")
        result = sc.json_schema(prompt, schema)
    elif schema_inline:
        schema = json.loads(schema_inline)
        print("\033[94mℹ Structured output (inline schema)\033[0m\n")
        result = sc.json_schema(prompt, schema)
    else:
        print("\033[94mℹ Structured output (JSON object mode)\033[0m\n")
        result = sc.json_object(prompt)

    indent = 2 if pretty else None
    print(json.dumps(result, indent=indent, ensure_ascii=False))
    return result


def cmd_structured_analyse(file_path: str, api_key: str, model: str) -> dict:
    code = Path(file_path).read_text()
    lang = Path(file_path).suffix.lstrip(".")
    print(f"\033[94mℹ Structured code analysis: {file_path}\033[0m\n")
    sc = StructuredCoder(api_key=api_key, model=model)
    result = sc.analyse_code(code, lang)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def cmd_structured_extract(content_file: str, schema_path: str, api_key: str, model: str) -> dict:
    content = Path(content_file).read_text()
    schema = json.loads(Path(schema_path).read_text())
    print(f"\033[94mℹ Extracting structured data from {content_file}\033[0m\n")
    sc = StructuredCoder(api_key=api_key, model=model)
    result = sc.extract(content, schema)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result
