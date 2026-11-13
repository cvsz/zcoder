"""Telemetry plugin for zcoder plugin system.

Implements `telemetry.log` and `telemetry.mark` events with tier gate,
compatible with claude-code's telemetry plugin.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from zcoder.agent.plugin.events import HookEvent
from zcoder.agent.plugin.hook_bus import HookBus, HookContext, HookResult
from zcoder.agent.plugin.tier import PluginTier

logger = logging.getLogger(__name__)


@dataclass
class TelemetryEvent:
    """A telemetry event to be sent."""

    event: str
    props: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""


@dataclass
class TelemetryMark:
    """A feature mark to be sent."""

    feature: str
    kind: str  # ok, sad, bad
    reason: str | None = None
    props: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""


@dataclass
class TelemetryPlugin:
    """Telemetry plugin that queues and flushes events."""

    hook_bus: HookBus | None = None
    event_queue: list[TelemetryEvent] = field(default_factory=list)
    mark_queue: list[TelemetryMark] = field(default_factory=list)
    session_id: str = ""
    enabled: bool = True
    _flush_task: asyncio.Task | None = None
    _flush_interval: float = 5.0  # seconds
    _max_batch_size: int = 100

    def set_session(self, session_id: str):
        """Set current session ID."""
        self.session_id = session_id

    def log(self, event: str, props: dict[str, Any]):
        """Queue a telemetry event."""
        if not self.enabled:
            return
        # Validate: snake_case event name, finite values
        if not self._validate_event_name(event):
            logger.warning(f"Invalid telemetry event name: {event}")
            return
        self.event_queue.append(
            TelemetryEvent(
                event=event,
                props=props,
                session_id=self.session_id,
            )
        )
        self._maybe_flush()

    def mark(self, feature: str, kind: str, reason: str | None = None, props: dict[str, Any] | None = None):
        """Queue a feature mark."""
        if not self.enabled:
            return
        if kind not in ("ok", "sad", "bad"):
            raise ValueError(f"Invalid mark kind: {kind}. Must be 'ok', 'sad', or 'bad'")
        if kind in ("sad", "bad") and not reason:
            raise ValueError(f"Reason required for {kind} mark")

        self.mark_queue.append(
            TelemetryMark(
                feature=feature,
                kind=kind,
                reason=reason,
                props=props or {},
                session_id=self.session_id,
            )
        )
        self._maybe_flush()

    def _validate_event_name(self, name: str) -> bool:
        """Validate event name is snake_case."""
        import re

        return bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))

    def _maybe_flush(self):
        """Flush if batch size reached."""
        if len(self.event_queue) + len(self.mark_queue) >= self._max_batch_size:
            self.flush()

    async def flush(self):
        """Send queued events to ingest."""
        if not self.event_queue and not self.mark_queue:
            return

        events = self.event_queue[:]
        marks = self.mark_queue[:]
        self.event_queue.clear()
        self.mark_queue.clear()

        # Send to OTel or Anthropic ingest
        # For now, log to debug
        logger.debug(f"Telemetry flush: {len(events)} events, {len(marks)} marks")
        for event in events:
            logger.debug(f"  Event: {event.event} props={event.props}")
        for mark in marks:
            logger.debug(f"  Mark: {mark.feature} kind={mark.kind} reason={mark.reason}")

    def disable(self):
        """Disable telemetry."""
        self.enabled = False
        if self._flush_task:
            self._flush_task.cancel()

    async def start_periodic_flush(self):
        """Start periodic flush task."""

        async def _flush_loop():
            while self.enabled:
                await asyncio.sleep(self._flush_interval)
                await self.flush()

        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(_flush_loop())

    async def stop_periodic_flush(self):
        """Stop periodic flush task."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass


@dataclass
class TelemetryHooks:
    """Hook handlers for telemetry events."""

    plugin: TelemetryPlugin
    hook_bus: HookBus

    def __post_init__(self):
        self.hook_bus.register(HookEvent.TELEMETRY_LOG, self._on_log)
        self.hook_bus.register(HookEvent.TELEMETRY_MARK, self._on_mark)

    async def _on_log(self, context: HookContext) -> HookResult:
        event = context.args.get("event", "")
        props = context.args.get("props", {})

        # Gate: only built-in tier or engine can call
        if context.origin_tier not in (PluginTier.PREPEND, PluginTier.APPEND, PluginTier.BUILTIN):
            return HookResult(
                blocked=True,
                message="Telemetry log restricted to org/builtin",
                deny_reason="telemetry_gate",
            )

        self.plugin.log(event, props)
        return HookResult()

    async def _on_mark(self, context: HookContext) -> HookResult:
        feature = context.args.get("feature", "")
        kind = context.args.get("kind", "")
        reason = context.args.get("reason")
        props = context.args.get("props", {})

        if context.origin_tier not in (PluginTier.PREPEND, PluginTier.APPEND, PluginTier.BUILTIN):
            return HookResult(
                blocked=True,
                message="Telemetry mark restricted to org/builtin",
                deny_reason="telemetry_gate",
            )

        try:
            self.plugin.mark(feature, kind, reason, props)
        except ValueError as e:
            return HookResult(
                blocked=True,
                message=str(e),
                deny_reason="telemetry_validation",
            )
        return HookResult()


def create_telemetry_plugin(hook_bus: HookBus | None = None) -> TelemetryPlugin:
    """Create telemetry plugin."""
    return TelemetryPlugin(hook_bus=hook_bus)
