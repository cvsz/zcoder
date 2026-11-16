"""Context compaction engine — mirrors deepseek-harness @deepseek-ai/dsh-compaction-basic.

Provides replay-aware compaction backend with:
- Context window pressure detection (threshold ratio + headroom tokens)
- Retention policy (retain ratio + retain tokens)
- LLM-based summarization
- Multi-model compaction policies
- Automatic compaction trigger
- Compaction retries and overflow handling
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.codeagent.loop import CodeAgent


@dataclass
class CompactionConfig:
    """Compaction configuration."""

    threshold_ratio: float = 0.8
    headroom_tokens: int = 1000
    retain_ratio: float = 0.25
    retain_tokens: int = 2000
    summarization_provider: str = 'ollama'
    summarization_model: str = 'zcoder-flash'
    max_tokens: int = 4096
    compaction_retries: int = 3
    max_overflow_retries: int = 2
    model_policies: list[dict[str, Any]] = field(default_factory=list)
    auto: bool = True


@dataclass
class ResolvedCompactSpec:
    """Resolved compaction specification."""

    provider: str
    model: str
    threshold_ratio: float
    headroom_tokens: int
    retain_ratio: float
    retain_tokens: int
    summarization_provider: str
    summarization_model: str
    max_tokens: int
    compaction_retries: int
    max_overflow_retries: int


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    summary: str
    tokens_saved: int
    messages_compacted: int
    reason: str  # 'context_window_full', 'manual', 'overflow'


class CompactionEngine:
    """Base compaction engine. Subclasses override summarize()."""

    def __init__(self, config: CompactionConfig | None = None) -> None:
        self.config = config or CompactionConfig()
        self._compaction_in_progress: dict[str, bool] = {}

    def is_compacting(self, session_id: str) -> bool:
        """Check if compaction is in progress for a session."""
        return self._compaction_in_progress.get(session_id, False)

    def should_compact(
        self,
        agent: CodeAgent,
        estimated_tokens: int,
    ) -> bool:
        """Determine if compaction is needed based on context window pressure."""
        config = self.config
        context_window = agent.context_window

        # Check threshold ratio
        if estimated_tokens > int(context_window * config.threshold_ratio):
            return True

        # Check headroom
        remaining = context_window - estimated_tokens
        if remaining < config.headroom_tokens:
            return True

        return False

    def resolve_compact_spec(
        self,
        agent: CodeAgent,
        answered_route: dict[str, Any] | None = None,
    ) -> ResolvedCompactSpec:
        """Resolve the compaction target (provider/model) and policy."""
        config = self.config

        # Determine summarization target
        provider = config.summarization_provider
        model = config.summarization_model

        # Check model-specific policies
        for policy in config.model_policies:
            if policy.get('provider') == provider and policy.get('model') == model:
                return ResolvedCompactSpec(
                    provider=policy.get('provider', provider),
                    model=policy.get('model', model),
                    threshold_ratio=policy.get('threshold_ratio', config.threshold_ratio),
                    headroom_tokens=policy.get('headroom_tokens', config.headroom_tokens),
                    retain_ratio=policy.get('retain_ratio', config.retain_ratio),
                    retain_tokens=policy.get('retain_tokens', config.retain_tokens),
                    summarization_provider=policy.get('summarization_provider', config.summarization_provider),
                    summarization_model=policy.get('summarization_model', config.summarization_model),
                    max_tokens=policy.get('max_tokens', config.max_tokens),
                    compaction_retries=policy.get('compaction_retries', config.compaction_retries),
                    max_overflow_retries=policy.get('max_overflow_retries', config.max_overflow_retries),
                )

        return ResolvedCompactSpec(
            provider=provider,
            model=model,
            threshold_ratio=config.threshold_ratio,
            headroom_tokens=config.headroom_tokens,
            retain_ratio=config.retain_ratio,
            retain_tokens=config.retain_tokens,
            summarization_provider=config.summarization_provider,
            summarization_model=config.summarization_model,
            max_tokens=config.max_tokens,
            compaction_retries=config.compaction_retries,
            max_overflow_retries=config.max_overflow_retries,
        )

    def select_compactable_range(
        self,
        messages: list[dict[str, Any]],
        retain_ratio: float,
        retain_tokens: int,
    ) -> tuple[int, int]:
        """Select the range of messages to compact.

        Returns (start_index, end_index) of messages to compact.
        Always retains the last user message and some tail context.
        """
        if not messages:
            return 0, 0

        # Always keep the last message (user prompt) and retain a portion
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m.get('role') == 'user'),
            default=0,
        )

        head = messages[:last_user_idx]

        if not head:
            return 0, 0

        # Calculate how many head messages to retain
        retain_count = max(1, int(len(head) * retain_ratio))
        retain_count = min(retain_count, len(head))

        # Compact from start up to (head_len - retain_count)
        compact_end = len(head) - retain_count
        if compact_end <= 0:
            return 0, 0

        return 0, compact_end

    def assert_no_active_compaction(self, session_id: str) -> None:
        """Raise if compaction is already in progress for this session."""
        if self._compaction_in_progress.get(session_id):
            raise RuntimeError(f'Compaction already in progress for session {session_id}')

    def compact_surface_region(
        self,
        agent: CodeAgent,
        start: int,
        end: int,
        instructions: str = '',
    ) -> CompactionResult:
        """Compact a surface region of messages.

        Mirrors deepseek-harness compactSurfaceRegion: summarizes head messages
        and replaces them with a summary, keeping the tail intact.
        """
        self.assert_no_active_compaction(agent.session_id)
        self._compaction_in_progress[agent.session_id] = True

        try:
            messages = agent.messages
            if start >= end or start >= len(messages):
                return CompactionResult(
                    summary='',
                    tokens_saved=0,
                    messages_compacted=0,
                    reason='no_messages_to_compact',
                )

            head = messages[start:end]
            tail = messages[end:]

            if not head:
                return CompactionResult(
                    summary='',
                    tokens_saved=0,
                    messages_compacted=0,
                    reason='empty_head',
                )

            # Build summarization input
            transcript = self._render_transcript(head)
            summary = self._summarize(
                transcript,
                instructions,
                agent,
            )

            # Replace head with summary
            summary_message = {
                'role': 'user',
                'content': f'[Summary of earlier conversation]\n{summary.strip()}',
            }
            understanding = {
                'role': 'assistant',
                'content': 'Understood. I have the context and will continue from here.',
            }

            agent.messages = [summary_message, understanding, *tail]

            # Estimate tokens saved
            original_chars = sum(len(str(m.get('content', ''))) for m in head)
            new_chars = len(summary) + len(understanding['content'])
            tokens_saved = max(0, (original_chars - new_chars) // 4)  # rough 4 chars/token

            return CompactionResult(
                summary=summary,
                tokens_saved=tokens_saved,
                messages_compacted=len(head),
                reason='context_window_full',
            )
        finally:
            self._compaction_in_progress[agent.session_id] = False

    def _render_transcript(self, messages: list[dict[str, Any]]) -> str:
        """Render messages as a transcript for summarization."""
        lines: list[str] = []
        for m in messages:
            role = m.get('role', 'unknown')
            content = m.get('content', '')
            if role == 'tool':
                lines.append(f'[tool result] {str(content)[:500]}')
                continue
            if content:
                lines.append(f'{role}: {str(content)[:2000]}')
            for tc in m.get('tool_calls') or []:
                lines.append(
                    f'[tool call] {tc.get("function", {}).get("name", "unknown")} '
                    f'{str(tc.get("function", {}).get("arguments", ""))[:300]}'
                )
        return '\n'.join(lines)

    def _summarize(
        self,
        transcript: str,
        instructions: str,
        agent: CodeAgent,
    ) -> str:
        """Summarize transcript using the LLM. Override in subclasses."""
        prompt = (
            'Summarize this coding session so work can continue from the summary alone. '
            'Include: the user\'s goals, decisions made, files created/changed (with paths), '
            'commands run and their outcomes, open problems, and next steps. '
            'Be dense and factual.'
            + (f'\nExtra focus: {instructions}' if instructions else '')
        )
        msgs = [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': transcript},
        ]

        # Use the agent's LLM to summarize
        # This is synchronous; in production this would be async
        async def _do_summarize() -> str:
            summary = ''
            async with agent.llm.stream(msgs, []) as stream:
                async for chunk in stream:
                    if chunk.kind == 'text':
                        summary += chunk.text
            return summary.strip()

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(_do_summarize())


class BasicCompactionEngine(CompactionEngine):
    """Dependency-light compaction engine using token meter for pressure."""

    def __init__(
        self,
        config: CompactionConfig | None = None,
        llm_call: Callable[[list[dict[str, Any]], list[dict[str, Any]]], str] | None = None,
    ) -> None:
        super().__init__(config)
        self._llm_call = llm_call

    def _summarize(
        self,
        transcript: str,
        instructions: str,
        agent: CodeAgent,
    ) -> str:
        """Summarize using the configured LLM call or agent's LLM."""
        if self._llm_call:
            prompt = (
                'Summarize this coding session so work can continue from the summary alone. '
                'Include: the user\'s goals, decisions made, files created/changed (with paths), '
                'commands run and their outcomes, open problems, and next steps. '
                'Be dense and factual.'
                + (f'\nExtra focus: {instructions}' if instructions else '')
            )
            msgs = [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': transcript},
            ]
            return self._llm_call(msgs, [])

        # Fall back to agent's LLM
        return super()._summarize(transcript, instructions, agent)


__all__ = [
    'CompactionConfig',
    'ResolvedCompactSpec',
    'CompactionResult',
    'CompactionEngine',
    'BasicCompactionEngine',
]
