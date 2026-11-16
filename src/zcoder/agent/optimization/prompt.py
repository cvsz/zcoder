"""Local prompt optimizer and A/B tester.

Improves a prompt using meta-prompting, scores it, runs A/B tests
between two versions, and tracks a prompt library.

CLI flags:
  --optimize PROMPT         Rewrite a prompt to be clearer and more effective
  --score-prompt PROMPT     Score a prompt 0-100 for clarity, specificity, and completeness
  --ab-test                 With --prompt and --v2: A/B test two prompt variants
  --ab-task TASK            Task description to judge both variants against
  --prompt-lib-add          Save current --prompt to the library (use --tag for a label)
  --prompt-lib-list         List saved prompts
  --prompt-lib-get TAG      Retrieve a saved prompt by tag
  --optimize-advanced       Advanced optimization with context-aware heuristics
  --predict-model         Predict best model for the prompt based on task type
"""

import json
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from zcoder.agent.optimization.local_tokens import _is_code_model_specific

PROMPT_LIB_PATH = Path.home() / ".zcoder" / "prompt_library.json"

# Advanced optimization heuristics by prompt type
_PROMPT_TYPE_HEURISTICS = {
    "code": {
        "patterns_to_expand": [
            (r"\bdef\s+(\w+)\b", r"def \1(\n    \"\"\"\"\"\"\"\"\n    \n)\1:"),
            (r"\bclass\s+(\w+)\b", r"class \1:\n    pass  # \1 class"),
        ],
        "patterns_to_trim": [
            (r"^\s+$", ""),  # Remove empty lines
            (r"\n+$", "\n"),  # Trim trailing newlines,
        ],
    },
    "creative": {
        "patterns_to_expand": [
            (r"\{% expand %\}", ""),  # Remove placeholder markers
        ],
        "patterns_to_trim": [
            (r"\bvery\s+\w+", r"\1"),  # Remove "very" as intensifier (often vague)
            (r"\breally\s+\w+", r"\1"),  # Remove "really" as intensifier,
        ],
    },
    "analysis": {
        "patterns_to_expand": [
            (r"\b(?:what|how|why)\s+(?:should|can|must)\b", r"\1 consider:\n- \2"),
        ],
        "patterns_to_trim": [
            (r"\b(?:just|really|very)\s+", ""),  # Remove filler adjectives,
        ],
    },
}

# Context-aware optimization rules
_CONTEXT_RULES: dict[str, list[tuple[re.Pattern, str | Callable[[re.Match[str]], str]]]] = {
    "technical": [
        (re.compile(r"\n{3,}", re.MULTILINE), "\n\n"),  # Collapse triple+ newlines
        (re.compile(r" {2,}", re.MULTILINE), " "),  # Collapse multiple spaces,
    ],
    "documentation": [
        (re.compile(r"^## .+", re.MULTILINE), lambda m: m.group(0) + "\n"),  # Ensure heading has newline,
        (re.compile(r"^\* .+", re.MULTILINE), lambda m: m.group(0).rstrip("*")),  # Clean bullet lists,
    ],
}

# Prompt type detection heuristics
_TYPE_INDICATORS = {
    "code": ["def ", "class ", "function ", "import ", "return ", "=>"],
    "creative": ["imagine", " suppose", " dream", " fantasy"],
    "analysis": ["analyze", " examine", " evaluate", " compare"],
}


def _detect_prompt_type(prompt: str) -> str:
    """Detect the type of prompt for context-aware optimization."""
    prompt_lower = prompt.lower()
    type_scores: dict[str, int] = {}

    for ptype, indicators in _TYPE_INDICATORS.items():
        score = sum(1 for ind in indicators if ind.lower() in prompt_lower)
        type_scores[ptype] = score

    # Return the type with the highest score, or "general" if none match
    if max(type_scores.values(), default=0) > 0:
        return max(type_scores, key=lambda k: type_scores[k])
    return "general"


def _apply_context_rule(
    optimized: str,
    pattern: re.Pattern,
    replacement: str | Callable[[re.Match[str]], str],
) -> str:
    """Apply a single context-aware replacement rule.

    mypy cannot infer the return type of ``re.Pattern.sub`` when ``repl`` is a
    ``str | Callable`` union, so we centralize the call here with an explicit
    ``str`` return annotation.
    """
    return cast(str, pattern.sub(replacement, optimized))


def optimize_advanced(
    prompt: str,
    model: str = "claude-sonnet-5",
) -> str:
    """Apply advanced context-aware prompt optimization heuristics.

    Uses model-specific and context-aware rules to optimize prompts
    without changing their semantic meaning.

    Args:
        prompt: The prompt to optimize
        model: Target model for model-specific heuristics

    Returns:
        Optimized prompt
    """
    prompt_type = _detect_prompt_type(prompt)
    optimized = prompt

    # Apply type-specific heuristics
    if prompt_type in _PROMPT_TYPE_HEURISTICS:
        heuristics = _PROMPT_TYPE_HEURISTICS[prompt_type]

        # Expand patterns (add useful structure)
        for pattern_str, replacement in heuristics.get("patterns_to_expand", []):
            optimized = re.sub(pattern_str, replacement, optimized)

        # Trim patterns (remove inefficiencies)
        for pattern_str, replacement in heuristics.get("patterns_to_trim", []):
            if callable(replacement):
                optimized = re.sub(pattern_str, replacement, optimized)
            else:
                optimized = re.sub(pattern_str, replacement, optimized)

    # Apply context-aware rules based on detected context
    context = _detect_context(prompt)
    if context in _CONTEXT_RULES:
        for pattern, replacement in _CONTEXT_RULES[context]:
            optimized = _apply_context_rule(optimized, pattern, replacement)

    # Remove excessive whitespace (universal rule)
    optimized = "\n".join(line.rstrip() for line in optimized.split("\n"))
    optimized = re.sub(r"\n\n+", "\n\n", optimized)

    return optimized


def _detect_context(prompt: str) -> str:
    """Detect the context type of a prompt for rule application."""
    prompt_lower = prompt.lower()

    # Check for documentation patterns
    if any(k in prompt_lower for k in ["README", "docs", "documentation", "api reference"]):
        return "documentation"

    # Check for technical code patterns
    if any(k in prompt_lower for k in ["function", "method", "class", "api", "endpoint"]):
        return "technical"

    return "general"


def predict_best_model_for_prompt(
    prompt: str,
    available_models: list[str] | None = None,
) -> dict:
    """Predict the best model for a given prompt based on content analysis.

    Args:
        prompt: The prompt to analyze
        available_models: List of available models. If None, uses defaults.

    Returns:
        Dict with recommended model and rationale
    """
    if available_models is None:
        available_models = [
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        ]

    # Detect prompt type and task characteristics
    prompt_type = _detect_prompt_type(prompt)

    # Analyze prompt features
    features: dict[str, Any] = {
        "type": prompt_type,
        "has_code": _is_code_model_specific(
            prompt, available_models[0] if available_models else "claude-sonnet-5"
        ),
        "word_count": len(prompt.split()),
        "has_complex_constraints": any(
            k in prompt.lower() for k in ["must", "should", "without", "ensure", "guarantee"]
        ),
    }

    # Model recommendations based on prompt characteristics
    recommendations: list[dict] = []

    for model in available_models:
        model_rec: dict = {"model": model, "rationale": "", "score": 0.0}

        if model == "claude-opus-5":
            model_rec["rationale"] = (
                "Best for complex reasoning, difficult problems, " "when quality trumps speed"
            )
            model_rec["score"] = 0.8 if features["has_complex_constraints"] else 0.5

        elif model == "claude-sonnet-5":
            model_rec["rationale"] = (
                "Best for general-purpose tasks, good balance of "
                " intelligence and speed, especially for code"
            )
            model_rec["score"] = 0.9 if features["has_code"] else 0.7

        elif model == "claude-haiku-4-5-20251001":
            model_rec["rationale"] = (
                "Best for simple tasks, high speed, cost-effective " "for straightforward prompts"
            )
            model_rec["score"] = 0.6 if features["has_code"] else 0.8

        recommendations.append(model_rec)

    # Sort by score (descending)
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    return {
        "prompt_type": prompt_type,
        "features": features,
        "recommendations": recommendations,
    }


def cmd_optimize_advanced(
    prompt: str,
    model: str,
    api_key: str,
) -> str:
    """CLI command for advanced prompt optimization.

    Args:
        prompt: The prompt to optimize
        model: Target model name
        api_key: Anthropic API key
    """
    # Apply advanced optimization
    optimized = optimize_advanced(prompt, model)

    # Predict best model
    prediction = predict_best_model_for_prompt(prompt, [model])

    print(f"\n\033[94mOriginal Prompt Type:\033[0m {prediction['prompt_type']}")
    print(
        f"\033[94mFeatures:\033[0m code={prediction['features']['has_code']}, "
        f"words={prediction['features']['word_count']}"
    )

    print("\n\033[94mOptimized Prompt:\033[0m")
    print(optimized)

    print(f"\n\033[94mModel Prediction:\033[0m {prediction['recommendations'][0]['model']}")
    print(f"  Rationale: {prediction['recommendations'][0]['rationale']}")

    return optimized


class OptimizeCache:
    """LRU cache for prompt optimization results."""

    def __init__(self, max_size: int = 128):
        self._cache: OrderedDict[tuple, str] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._max_size = max_size

    def get(self, key: tuple) -> str | None:
        if key in self._cache:
            self._hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, key: tuple, value: str) -> None:
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0


_optimize_cache = OptimizeCache()


def _strip_json_fence(text: str) -> str:
    """Remove an optional Markdown JSON/code fence without character stripping."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json")
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```")
    if cleaned.rstrip().endswith("```"):
        cleaned = cleaned.rstrip().removesuffix("```")
    return cleaned.strip()


def _call(client, model: str, system: str, user: str, max_tokens: int = 2048) -> str:
    client.model = model
    client.max_tokens = max_tokens
    return client.generate(user, system=system).strip()


def optimize(prompt: str, client=None, model: str = "zqwen2.5-coder-7b-instruct-q4_k_m") -> str:
    if not client:
        # Offline rule-based prompt enhancement - not cached
        lines = [line.strip() for line in prompt.strip().splitlines() if line.strip()]
        enhanced = "Act as an expert software engineer.\n\nTask:\n" + "\n".join(lines)
        if not any(k in prompt.lower() for k in ("return", "output", "format")):
            enhanced += "\n\nRequirements:\n- Output clean, complete, and production-ready code\n- Include type hints and handle error conditions"
        return enhanced

    system = (
        "You are an expert prompt engineer. Rewrite the user's prompt to be "
        "clearer, more specific, and more likely to get a great response from an AI. "
        "Return ONLY the improved prompt — no commentary, no explanation."
    )
    try:
        # Use client id as part of cache key to isolate different clients
        client_id = id(client)
        cache_key = (prompt, model, client_id)

        cached = _optimize_cache.get(cache_key)
        if cached is not None:
            return cached

        result = _call(client, model, system, f"Prompt to improve:\n{prompt}")

        _optimize_cache.set(cache_key, result)

        return result
    except Exception as exc:
        return f"[ERROR] Local prompt optimization failed: {exc}"


def get_optimize_cache_stats() -> dict:
    """Get cache statistics for the optimize function."""
    return _optimize_cache.stats()


def clear_optimize_cache() -> None:
    """Clear the optimize function cache."""
    _optimize_cache.clear()


def score(prompt: str, client=None, model: str = "zqwen2.5-coder-7b-instruct-q4_k_m") -> dict:
    if not client:
        # High quality offline deterministic scoring heuristics
        words = prompt.strip().split()
        word_count = len(words)
        has_context = any(k in prompt.lower() for k in ("in", "for", "using", "with", "format", "as"))
        has_code_spec = any(
            k in prompt.lower() for k in ("python", "function", "class", "api", "test", "sql", "def")
        )
        has_constraints = any(
            k in prompt.lower() for k in ("must", "only", "return", "should", "without", "no")
        )

        clarity = min(100, max(40, 50 + (10 if word_count >= 5 else -20)))
        specificity = min(100, max(30, 40 + (30 if has_code_spec else 0) + (15 if has_context else 0)))
        completeness = min(
            100, max(30, 40 + (25 if has_constraints else 0) + (15 if word_count >= 10 else 0))
        )
        total = int((clarity + specificity + completeness) / 3)
        feedback = (
            "Add explicit output constraints and expected data types for optimal accuracy."
            if total < 80
            else "Well structured prompt with clear context."
        )
        return {
            "clarity": clarity,
            "specificity": specificity,
            "completeness": completeness,
            "total": total,
            "feedback": feedback,
        }

    system = (
        "You are a prompt quality evaluator. Score this prompt on three dimensions "
        "(each 0-100): clarity, specificity, completeness. "
        'Return ONLY a JSON object: {"clarity": N, "specificity": N, "completeness": N, '
        '"total": N, "feedback": "one sentence of the most impactful improvement"}. '
        "Total = average of the three scores."
    )
    try:
        raw = _call(client, model, system, f"Prompt to score:\n{prompt}", max_tokens=512)
        return json.loads(_strip_json_fence(raw))
    except Exception as exc:
        return {"error": f"Local prompt scoring failed: {exc}"}


def ab_test(prompt_a: str, prompt_b: str, task: str, client, model: str) -> dict:
    def run(prompt: str) -> tuple[str, float]:
        t0 = time.time()
        return _call(client, model, "", prompt, max_tokens=2048), round(time.time() - t0, 2)

    resp_a, time_a = run(prompt_a)
    resp_b, time_b = run(prompt_b)

    judge_prompt = (
        f"Task: {task}\n\n"
        f"Response A:\n{resp_a}\n\n"
        f"Response B:\n{resp_b}\n\n"
        "Which response better completes the task? Reply ONLY with a JSON object: "
        '{"winner": "A" or "B" or "tie", "reason": "one sentence", '
        '"score_a": 0-100, "score_b": 0-100}'
    )
    judge_raw = _call(
        client, model, "You are an objective evaluator of AI responses.", judge_prompt, max_tokens=512
    )
    try:
        judgment = json.loads(_strip_json_fence(judge_raw))
    except json.JSONDecodeError:
        judgment = {"winner": "unknown", "reason": judge_raw}

    return {
        "prompt_a": prompt_a,
        "response_a": resp_a,
        "time_a": time_a,
        "prompt_b": prompt_b,
        "response_b": resp_b,
        "time_b": time_b,
        "judgment": judgment,
    }


def _load_lib() -> dict:
    if PROMPT_LIB_PATH.exists():
        try:
            with open(PROMPT_LIB_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_lib(lib: dict):
    PROMPT_LIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMPT_LIB_PATH, "w") as f:
        json.dump(lib, f, indent=2)


def lib_add(prompt: str, tag: str) -> str:
    lib = _load_lib()
    lib[tag] = {"prompt": prompt, "added": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _save_lib(lib)
    return tag


def lib_list() -> list[dict]:
    lib = _load_lib()
    return [{"tag": k, "added": v.get("added", ""), "preview": v["prompt"][:80]} for k, v in lib.items()]


def lib_get(tag: str) -> str | None:
    return _load_lib().get(tag, {}).get("prompt")


def cmd_optimize(prompt: str, api_key: str, model: str):
    from zcoder.services.coder import Coder

    client = Coder(model=model)
    improved = optimize(prompt, client, model)
    print("\n\033[94mOriginal:\033[0m")
    print(prompt)
    print("\n\033[92mOptimized:\033[0m")
    print(improved)
    return improved


def cmd_score(prompt: str, api_key: str, model: str):
    from zcoder.services.coder import Coder

    client = Coder(model=model)
    result = score(prompt, client, model)
    if "error" in result:
        print(f"\033[91mError: {result['error']}\033[0m")
        return
    print("\n\033[94mPrompt Score\033[0m")
    print(f"  Clarity:       {result.get('clarity', '?')}/100")
    print(f"  Specificity:   {result.get('specificity', '?')}/100")
    print(f"  Completeness:  {result.get('completeness', '?')}/100")
    print(f"  \033[1mTotal:         {result.get('total', '?')}/100\033[0m")
    print(f"  Feedback:      {result.get('feedback', '')}\n")


def cmd_ab_test(prompt_a: str, prompt_b: str, task: str, api_key: str, model: str):
    from zcoder.services.coder import Coder

    client = Coder(model=model)
    result = ab_test(prompt_a, prompt_b, task, client, model)
    j = result["judgment"]
    print("\n\033[94mA/B Test Results\033[0m")
    print(f"  Winner:  \033[1m{j.get('winner', '?')}\033[0m  — {j.get('reason', '')}")
    print(f"  Score A: {j.get('score_a', '?')}/100  (response in {result['time_a']}s)")
    print(f"  Score B: {j.get('score_b', '?')}/100  (response in {result['time_b']}s)")
    print(f"\n\033[90m--- Response A ---\033[0m\n{result['response_a'][:400]}...")
    print(f"\n\033[90m--- Response B ---\033[0m\n{result['response_b'][:400]}...")


def cmd_prompt_lib_list():
    entries = lib_list()
    if not entries:
        print("Prompt library is empty. Use --prompt-lib-add with --tag to save prompts.")
        return
    print(f"\n\033[94mPrompt Library ({len(entries)} entries)\033[0m")
    for entry in entries:
        print(f"  \033[1m{entry['tag']:<20}\033[0m {entry['preview']}")
    print()
