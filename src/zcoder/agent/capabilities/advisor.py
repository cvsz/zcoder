"""Local two-pass advisor and executor generation."""

from zcoder.services.coder import Coder


def build_advisor_tool(
    advisor_model: str | None = None,
    max_uses: int | None = None,
    max_tokens: int | None = None,
    cache_ttl: str | None = None,
) -> dict:
    """Build local advisor settings while preserving the historical helper API.

    ``cache_ttl`` is accepted for source compatibility but has no effect: the
    local model client does not use provider prompt-cache directives.
    """
    del cache_ttl
    if max_uses is not None and max_uses < 1:
        raise ValueError("max_uses must be at least 1")
    if max_tokens is not None and max_tokens < 1:
        raise ValueError("max_tokens must be at least 1")
    return {
        "type": "local_advisor",
        "name": "advisor",
        "model": advisor_model,
        "max_uses": max_uses,
        "max_tokens": max_tokens,
    }


class AdvisorCoder:
    """Generate local advisor guidance, then a local executor response."""

    def __init__(self, api_key: str = "", executor_model: str | None = None, max_tokens: int = 4096):
        # Kept for callers that still pass the old argument. Local inference
        # neither reads nor forwards API credentials.
        del api_key
        self.executor_model = executor_model
        self.max_tokens = max_tokens
        self.executor = Coder(model=executor_model, max_tokens=max_tokens)

    def run(
        self,
        prompt: str,
        advisor_tool: dict,
        extra_tools: list[dict] | None = None,
        system: str | None = None,
        max_advisor_calls: int = 10,
        verbose: bool = True,
    ) -> str:
        """Run one local advisor pass followed by one local executor pass."""
        del max_advisor_calls
        if extra_tools:
            raise ValueError("Local advisor mode does not support extra provider tools")
        if advisor_tool.get("type") != "local_advisor":
            raise ValueError("advisor_tool must be created by build_advisor_tool()")

        advisor_model = advisor_tool.get("model") or self.executor_model
        advisor = Coder(
            model=advisor_model,
            max_tokens=advisor_tool.get("max_tokens") or min(self.max_tokens, 1024),
        )
        advisor_prompt = (
            "Review the task independently. Identify important constraints, likely failure modes, "
            "and a concise recommended approach. Do not answer the task or invent facts.\n\n"
            f"Task:\n{prompt}"
        )
        guidance = advisor.generate(
            advisor_prompt,
            system="You are a careful technical advisor. Return concise, actionable guidance.",
        )
        if not isinstance(guidance, str) or guidance.startswith("[ERROR]"):
            return guidance if isinstance(guidance, str) else "[ERROR] Local advisor returned no text"

        if verbose:
            preview = guidance[:200]
            print(f"\033[90m  [local advisor] {preview}{'...' if len(guidance) > 200 else ''}\033[0m")

        executor_prompt = (
            f"Task:\n{prompt}\n\n"
            f"Independent advisor guidance:\n{guidance}\n\n"
            "Complete the task. Treat the guidance as input to evaluate, not as verified fact."
        )
        result = self.executor.generate(executor_prompt, system=system)
        if not isinstance(result, str):
            return "[ERROR] Local executor returned no text"
        return result


def cmd_advisor(
    prompt: str,
    api_key: str,
    executor_model: str,
    advisor_model: str | None = None,
    max_uses: int | None = None,
    advisor_max_tokens: int | None = None,
):
    resolved_advisor_model = advisor_model or executor_model
    print(
        f"\033[94mℹ Local advisor | executor={executor_model} " f"advisor={resolved_advisor_model}\033[0m\n"
    )
    advisor_tool = build_advisor_tool(
        advisor_model=resolved_advisor_model,
        max_uses=max_uses,
        max_tokens=advisor_max_tokens,
    )
    client = AdvisorCoder(api_key=api_key, executor_model=executor_model)
    result = client.run(prompt, advisor_tool)
    print(result)
    return result
