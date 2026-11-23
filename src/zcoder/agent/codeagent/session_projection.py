"""Session projection registry — mirrors deepseek-harness @deepseek-ai/dsh-session-projection.

Provides a capability-seam for session state projections: domain plugins register pure
fold units (ProjectionDefinition) that are eagerly driven over committed session events.
The registry owns the per-session watermark cache, change notification, and snapshot
read face; consumers consume the snapshot read face and change feed.

Architecture:
  * Whole-value event rule: state-carrying log events carry complete post-change state.
  * Eager drive: every committed event passes through every registered unit's apply().
  * Reference comparison: unchanged state reference produces zero downstream work.
  * Checkpoint/restore: persisted projection cache rows for fast session restore.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from zcoder.agent.codeagent.sessions import SessionEvent

S = TypeVar("S")


# ── ProjectionDefinition ──────────────────────────────────────────────────────


class ProjectionDefinition[K, S]:
    """One domain's state-driven computation unit: a pure synchronous fold plus
    declarations and an optional client view.

    All functions MUST be synchronous. `state` MUST be plain JSON (the
    persisted-cache precondition).
    """

    def __init__(
        self,
        key: str,
        state_schema: Callable[[Any], S],
        init: Callable[[dict[str, Any], int], S],
        apply: Callable[[S, SessionEvent], S],
        state_version: int,
        wire: ProjectionWire[S] | None = None,
    ) -> None:
        self.key = key
        self.state_schema = state_schema
        self.init = init
        self.apply = apply
        self.state_version = state_version
        self.wire = wire

    def validate_state(self, state: Any) -> S:
        """Validate persisted state before seeding a fold."""
        return self.state_schema(state)


# SessionHeader type alias for compatibility with deepseek-harness
SessionHeader = dict[str, Any]


@dataclass
class ProjectionWire[S]:
    """Client view: validates the wire payload and projects state -> value."""

    view_schema: Callable[[Any], Any]
    view: Callable[[S], Any]
    summary: bool = True


# ── ProjectionHandle ──────────────────────────────────────────────────────────


class ProjectionHandle[S]:
    """Effect-owned registration with a reader retained independently of registration."""

    def __init__(
        self,
        registry: SessionProjectionRegistry,
        key: str,
        session: Any | None = None,
    ) -> None:
        self._registry = registry
        self._key = key
        self._session = session
        self._disposed = False

    def state_of(self, session: Any) -> S:
        """Read the current state, folding new events if needed."""
        result = self._registry.state_of(session, self._key)
        if result is None:
            raise ValueError(f"No state found for session with key {self._key}")
        return result

    def reader_for(self, session: Any) -> Callable[[], S]:
        """Create a reader for one exact Session."""
        return lambda: self.state_of(session)

    def dispose(self) -> None:
        """Unregister from global drives without invalidating this reader."""
        self._disposed = True
        self._registry.release(self._key)


# ── UnitCell ──────────────────────────────────────────────────────────────────


@dataclass
class UnitCell:
    """Per-session per-unit watermark and live-drive view buffer."""

    state: Any
    observed_seq: int = -1
    views: list[Any | None] = field(default_factory=lambda: [None, None])


# ── Registration ──────────────────────────────────────────────────────────────


@dataclass
class Registration:
    """One shared unit and its per-session cells."""

    def_: ProjectionDefinition[Any, Any]
    cells: dict[Any, UnitCell] = field(default_factory=dict)
    refs: int = 0


# ── SessionProjectionRegistry ─────────────────────────────────────────────────


class SessionProjectionRegistry:
    """ctx.session_projections: the projection unit table and its drive.

    Subscribes to session events once; every committed event passes every
    registered unit's apply (eager drive). Cells build lazily — a unit
    registered after events flowed folds init over the in-memory log on first
    touch.
    """

    def __init__(self) -> None:
        self.registrations: dict[str, Registration] = {}
        self._summary_key_set: frozenset[str] | None = None
        self._listeners: list[Callable[[Any, str, Any, int], None]] = []
        self._event_listeners: list[Callable[[Any, list[dict[str, Any]], int], None]] = []
        self._deprecated_keys: set[str] = set()
        self._lock = threading.RLock()

    # ── Registration ──────────────────────────────────────────────────

    def register(
        self,
        definition: ProjectionDefinition[str, Any],
    ) -> ProjectionHandle[S]:
        """Register one domain's unit. Returns a handle for reading state."""
        with self._lock:
            key = definition.key
            existing = self.registrations.get(key)
            if existing is None or existing.refs == 0:
                registration = Registration(def_=definition, refs=1)
                self.registrations[key] = registration
                self._summary_key_set = None
            else:
                if existing.def_.state_version != definition.state_version:
                    raise ValueError(
                        f"session projection {key!r} is already registered at "
                        f"stateVersion {existing.def_.state_version}; refusing to share "
                        f"with stateVersion {definition.state_version}"
                    )
                existing.refs += 1
                registration = existing

        handle: ProjectionHandle[Any] = ProjectionHandle(self, key)
        return handle

    def release(self, key: str) -> None:
        """Release one reference; final removal removes live participation."""
        with self._lock:
            registration = self.registrations.get(key)
            if registration is None:
                return
            registration.refs -= 1
            if registration.refs == 0:
                self._summary_key_set = None

    # ── Cell management ───────────────────────────────────────────────

    def _cell_for(self, registration: Registration, session: Any) -> UnitCell:
        with self._lock:
            cell = registration.cells.get(session)
            if cell is None:
                # Lazily build: fold init over the in-memory log.
                events: list[SessionEvent] = getattr(session, "snapshot_events", lambda: [])()
                cell = self._build_cell(registration.def_, session, events)
                registration.cells[session] = cell
            else:
                self._advance_cell(registration.def_, cell, session)
            return cell

    def _build_cell(
        self,
        definition: ProjectionDefinition[Any, S],
        session: Any,
        events: list[SessionEvent],
    ) -> UnitCell:
        header = getattr(session, "header", {})
        inherited = getattr(session, "inherited_event_count", 0)
        state = definition.init(header, inherited)
        for event in events:
            state = definition.apply(state, event)
        last_seq = events[-1].event_id if events else -1
        try:
            last_seq = int(last_seq)
        except (TypeError, ValueError):
            last_seq = -1
        return UnitCell(state=state, observed_seq=last_seq)

    def _advance_cell(
        self,
        definition: ProjectionDefinition[Any, S],
        cell: UnitCell,
        session: Any,
    ) -> None:
        with self._lock:
            through_seq = getattr(session, "seq", -1)
            if cell.observed_seq >= through_seq:
                return
            events: list[SessionEvent] = getattr(session, "snapshot_events", lambda *_: [])(
                cell.observed_seq + 1, through_seq + 1
            )
            for event in events:
                previous = cell.state
                next_state = definition.apply(previous, event)
                changed = next_state is not previous
                cell.state = next_state
                cell.observed_seq = getattr(event, "event_id", cell.observed_seq + 1)
                try:
                    cell.observed_seq = int(cell.observed_seq)
                except (TypeError, ValueError):
                    cell.observed_seq = cell.observed_seq + 1
                if changed and definition.wire is not None:
                    cell.views[0] = cell.views[1]
                    cell.views[1] = definition.wire.view(next_state)

    # ── Read faces ────────────────────────────────────────────────────

    def state_of(self, session: Any, key: str) -> Any | None:
        """Read a currently registered unit's state for one session."""
        with self._lock:
            if key not in self._deprecated_keys:
                self._deprecated_keys.add(key)
            registration = self.registrations.get(key)
            if registration is None or registration.refs == 0:
                return None
            cell = self._cell_for(registration, session)
            return cell.state

    def snapshot(
        self,
        session: Any,
        keys: frozenset[str] | list[str] | None = None,
    ) -> dict[str, Any]:
        """One consistent cut over every registered client-visible unit."""
        with self._lock:
            selected = set(keys) if keys is not None else None
            values: dict[str, Any] = {}
            for key, registration in self.registrations.items():
                if registration.refs == 0:
                    continue
                if registration.def_.wire is None:
                    continue
                if selected is not None and key not in selected:
                    continue
                cell = self._cell_for(registration, session)
                values[key] = registration.def_.wire.view(cell.state)
            return values

    def checkpoint(self, session: Any) -> dict[str, dict[str, Any]]:
        """State-level checkpoint of every unit for one session."""
        with self._lock:
            rows: dict[str, dict[str, Any]] = {}
            for key, registration in self.registrations.items():
                cell = registration.cells.get(session)
                if cell is None:
                    continue
                rows[key] = {
                    "ver": registration.def_.state_version,
                    "seq": cell.observed_seq,
                    "val": cell.state,
                }
            return rows

    def restore_floor(self, checkpoint: dict[str, dict[str, Any]]) -> int | None:
        """The offset for the stored-log suffix read."""
        with self._lock:
            floor: int | None = None
            for key, registration in self.registrations.items():
                if registration.refs == 0:
                    continue
                row = checkpoint.get(key)
                if row is not None and row.get("ver") == registration.def_.state_version:
                    need = max(int(row.get("seq", -1)) + 1, 0)
                else:
                    need = 0
                floor = need if floor is None else min(floor, need)
            return max(floor - 1, 0) if floor is not None else None

    def view_checkpoint(
        self,
        checkpoint: dict[str, dict[str, Any]],
        keys: frozenset[str] | list[str] | None = None,
    ) -> dict[str, Any]:
        """Zero-I/O rung: serve schema-validated view of stored state."""
        with self._lock:
            selected = set(keys) if keys is not None else None
            values: dict[str, Any] = {}
            for key, registration in self.registrations.items():
                if registration.refs == 0:
                    continue
                if registration.def_.wire is None:
                    continue
                if selected is not None and key not in selected:
                    continue
                row = checkpoint.get(key)
                if row is None or row.get("ver") != registration.def_.state_version:
                    continue
                try:
                    state = registration.def_.validate_state(row.get("val"))
                except Exception:
                    continue
                values[key] = registration.def_.wire.view(state)
            return values

    def restore(
        self,
        checkpoint: dict[str, dict[str, Any]],
        events: list[SessionEvent],
        base_seq: int,
        header: dict[str, Any],
        inherited_event_count: int,
    ) -> dict[str, Any]:
        """Cold read: fold every persisted unit over a stored log suffix."""
        end_seq = events[-1].event_id if events else base_seq - 1
        try:
            end_seq = int(end_seq)
        except (TypeError, ValueError):
            end_seq = base_seq - 1
        before_base = base_seq - 1
        values: dict[str, Any] = {}

        with self._lock:
            for key, registration in self.registrations.items():
                if registration.refs == 0:
                    continue
                defn = registration.def_
                row = checkpoint.get(key)
                usable = False
                row_ver: Any = None
                row_seq: int = -1
                if row is not None:
                    row_ver = row.get("ver")
                    row_seq = int(row.get("seq", -1))
                    usable = row_ver == defn.state_version and row_seq >= before_base and row_seq <= end_seq
                if not usable and base_seq > 0:
                    raise ValueError(
                        f"session projection {key!r} cannot restore from seq {base_seq}: "
                        "checkpoint row missing, version-mismatched, or beyond log end"
                    )

                if usable:
                    assert row is not None
                    state = defn.validate_state(row.get("val"))
                    from_seq = row_seq
                else:
                    state = defn.init(header, inherited_event_count)
                    from_seq = before_base

                start_index = from_seq - base_seq + 1
                for index in range(start_index, len(events)):
                    event = events[index]
                    expected_seq = base_seq + index
                    if getattr(event, "event_id", None) != expected_seq:
                        raise ValueError(
                            f"session projection {key!r} cannot restore across " f"missing seq {expected_seq}"
                        )
                    state = defn.apply(state, event)

                if defn.wire is not None:
                    values[key] = defn.wire.view(state)

        return values

    # ── Change feed ───────────────────────────────────────────────────

    def on_changed(self, listener: Callable[[Any, str, Any, int], None]) -> Callable[[], None]:
        """Subscribe to per-key change feed."""
        with self._lock:
            self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def on_event_changed(
        self, listener: Callable[[Any, list[dict[str, Any]], int], None]
    ) -> Callable[[], None]:
        """Subscribe to event-level change feed."""
        with self._lock:
            self._event_listeners.append(listener)
        return lambda: self._event_listeners.remove(listener)

    # ── Summary keys ──────────────────────────────────────────────────

    def summary_keys(self) -> frozenset[str]:
        """Keys a Session summary carries (units without summary=False)."""
        with self._lock:
            if self._summary_key_set is None:
                keys = frozenset(
                    key
                    for key, reg in self.registrations.items()
                    if reg.refs > 0 and reg.def_.wire is not None and reg.def_.wire.summary
                )
                self._summary_key_set = keys
            return self._summary_key_set

    # ── Drive ─────────────────────────────────────────────────────────

    def drive(self, session: Any, event: SessionEvent) -> None:
        """Eager drive: pass one committed event through every unit."""
        with self._lock:
            observed = len(self._listeners) > 0 or len(self._event_listeners) > 0
            changes: list[dict[str, Any]] = []

            for key, registration in self.registrations.items():
                if registration.refs == 0:
                    continue
                cell = registration.cells.get(session)
                if cell is not None and cell.observed_seq >= getattr(event, "event_id", 0):
                    continue
                if cell is None:
                    events_prefix: list[SessionEvent] = getattr(session, "snapshot_events", lambda *_: [])(
                        0, getattr(event, "event_id", 0)
                    )
                    cell = self._build_cell(registration.def_, session, events_prefix)
                    registration.cells[session] = cell
                else:
                    self._advance_cell(registration.def_, cell, session)

                previous = cell.state
                next_state = registration.def_.apply(previous, event)
                changed = next_state is not previous
                cell.state = next_state
                cell.observed_seq = getattr(event, "event_id", cell.observed_seq + 1)
                try:
                    cell.observed_seq = int(cell.observed_seq)
                except (TypeError, ValueError):
                    cell.observed_seq = cell.observed_seq + 1

                if changed and registration.def_.wire is not None and observed:
                    cell.views[0] = cell.views[1]
                    cell.views[1] = registration.def_.wire.view(next_state)
                    if cell.views[0] is not cell.views[1]:
                        value = registration.def_.wire.view_schema(cell.views[1])
                        change = {"key": key, "val": value}
                        changes.append(change)
                        for listener in self._listeners:
                            listener(session, key, value, getattr(event, "event_id", 0))

            if changes:
                for evt_listener in self._event_listeners:
                    evt_listener(session, changes, getattr(event, "event_id", 0))


# ── Session Stats Projection ─────────────────────────────────────────────────
# Mirrors deepseek-harness @deepseek-ai/dsh-session-stats: whole-log turn/step
# counts and wall times served through the session-projection seam.


@dataclass
class SessionStatsTotals:
    """Accumulated whole-log figures."""

    turns: int = 0
    steps: int = 0
    llm_ms: int = 0
    tool_ms: int = 0
    ttft_ms: int = 0
    ttft_steps: int = 0
    decode_ms: int = 0
    decode_tokens: int = 0


@dataclass
class SessionStatsState(SessionStatsTotals):
    """Fold state: totals plus in-flight boundaries."""

    last_turn: int | None = None
    open_step: dict[str, Any] | None = None
    pending_calls: dict[str, int] = field(default_factory=dict)


def _usage_output_tokens(usage: Any) -> int | None:
    """Extract output tokens from usage record."""
    if not isinstance(usage, dict):
        return None
    value = usage.get("output_tokens")
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


def _first_token_time(stream_data: Any) -> int | None:
    """Extract first token time from assistant/attempt stream data."""
    if not isinstance(stream_data, dict):
        return None
    value = stream_data.get("first_token_time")
    if isinstance(value, (int, float)):
        return int(value * 1000)  # convert seconds to ms
    return None


def session_stats_init(header: dict[str, Any], inherited_event_count: int) -> SessionStatsState:
    return SessionStatsState()


def session_stats_apply(state: SessionStatsState, event: SessionEvent) -> SessionStatsState:
    kind = event.kind
    data = event.data or {}
    event_time = int(event.timestamp * 1000) if event.timestamp else 0

    if kind == "step/start":
        return SessionStatsState(
            turns=state.turns,
            steps=state.steps,
            llm_ms=state.llm_ms,
            tool_ms=state.tool_ms,
            ttft_ms=state.ttft_ms,
            ttft_steps=state.ttft_steps,
            decode_ms=state.decode_ms,
            decode_tokens=state.decode_tokens,
            last_turn=state.last_turn,
            open_step={
                "turn": data.get("turn", 0),
                "step": data.get("step", 0),
                "start_time": event_time,
                "first_token_time": None,
            },
            pending_calls=dict(state.pending_calls),
        )

    if kind == "assistant/attempt":
        open_step = state.open_step
        if open_step is None:
            return state
        if open_step["turn"] != data.get("turn") or open_step["step"] != data.get("step"):
            return state
        first = _first_token_time(data.get("stream"))
        if open_step["first_token_time"] is not None or first is None:
            return state
        new_open = dict(open_step)
        new_open["first_token_time"] = first
        return SessionStatsState(
            turns=state.turns,
            steps=state.steps,
            llm_ms=state.llm_ms,
            tool_ms=state.tool_ms,
            ttft_ms=state.ttft_ms,
            ttft_steps=state.ttft_steps,
            decode_ms=state.decode_ms,
            decode_tokens=state.decode_tokens,
            last_turn=state.last_turn,
            open_step=new_open,
            pending_calls=dict(state.pending_calls),
        )

    if kind == "assistant/message":
        open_step = state.open_step
        if open_step is None:
            return state
        if open_step["turn"] != data.get("turn") or open_step["step"] != data.get("step"):
            return state
        first_token = open_step["first_token_time"] or _first_token_time(data.get("stream")) or None
        new_state = SessionStatsState(
            turns=state.turns,
            steps=state.steps,
            llm_ms=state.llm_ms + max(0, event_time - open_step["start_time"]),
            tool_ms=state.tool_ms,
            ttft_ms=state.ttft_ms,
            ttft_steps=state.ttft_steps,
            decode_ms=state.decode_ms,
            decode_tokens=state.decode_tokens,
            last_turn=state.last_turn,
            open_step=None,
            pending_calls=dict(state.pending_calls),
        )
        if first_token is not None:
            new_state.ttft_ms += max(0, first_token - open_step["start_time"])
            new_state.ttft_steps += 1
            output_tokens = _usage_output_tokens(data.get("usage"))
            if output_tokens is not None:
                new_state.decode_ms += max(0, event_time - first_token)
                new_state.decode_tokens += output_tokens
        return new_state

    if kind == "tool/call":
        call_id = data.get("tool_call_id") or data.get("callId") or ""
        new_pending = dict(state.pending_calls)
        new_pending[call_id] = event_time
        return SessionStatsState(
            turns=state.turns,
            steps=state.steps,
            llm_ms=state.llm_ms,
            tool_ms=state.tool_ms,
            ttft_ms=state.ttft_ms,
            ttft_steps=state.ttft_steps,
            decode_ms=state.decode_ms,
            decode_tokens=state.decode_tokens,
            last_turn=state.last_turn,
            open_step=state.open_step,
            pending_calls=new_pending,
        )

    if kind == "tool/result":
        call_id = data.get("tool_call_id") or data.get("callId") or ""
        dispatched = state.pending_calls.get(call_id)
        if dispatched is None:
            return state
        new_pending = {k: v for k, v in state.pending_calls.items() if k != call_id}
        return SessionStatsState(
            turns=state.turns,
            steps=state.steps,
            llm_ms=state.llm_ms,
            tool_ms=state.tool_ms + max(0, event_time - dispatched),
            ttft_ms=state.ttft_ms,
            ttft_steps=state.ttft_steps,
            decode_ms=state.decode_ms,
            decode_tokens=state.decode_tokens,
            last_turn=state.last_turn,
            open_step=state.open_step,
            pending_calls=new_pending,
        )

    if kind == "step/end":
        new_turns = state.turns if state.last_turn == data.get("turn") else state.turns + 1
        return SessionStatsState(
            turns=new_turns,
            steps=state.steps + 1,
            llm_ms=state.llm_ms,
            tool_ms=state.tool_ms,
            ttft_ms=state.ttft_ms,
            ttft_steps=state.ttft_steps,
            decode_ms=state.decode_ms,
            decode_tokens=state.decode_tokens,
            last_turn=data.get("turn", 0),
            open_step=None,
            pending_calls=dict(state.pending_calls),
        )

    if kind == "turn/end":
        if len(state.pending_calls) == 0:
            return state
        return SessionStatsState(
            turns=state.turns,
            steps=state.steps,
            llm_ms=state.llm_ms,
            tool_ms=state.tool_ms,
            ttft_ms=state.ttft_ms,
            ttft_steps=state.ttft_steps,
            decode_ms=state.decode_ms,
            decode_tokens=state.decode_tokens,
            last_turn=state.last_turn,
            open_step=state.open_step,
            pending_calls={},
        )

    return state


def session_stats_view(state: SessionStatsState) -> dict[str, Any]:
    return {
        "turns": state.turns,
        "steps": state.steps,
        "llmMs": state.llm_ms,
        "toolMs": state.tool_ms,
        "ttftMs": state.ttft_ms,
        "ttftSteps": state.ttft_steps,
        "decodeMs": state.decode_ms,
        "decodeTokens": state.decode_tokens,
    }


def session_stats_schema(state: Any) -> Any:
    return state


session_stats_wire = ProjectionWire(
    view_schema=session_stats_schema,
    view=session_stats_view,
    summary=False,
)

session_stats_projection_definition: ProjectionDefinition[str, SessionStatsState] = ProjectionDefinition(
    key="sessionStats",
    state_schema=session_stats_schema,
    init=session_stats_init,
    apply=session_stats_apply,
    state_version=1,
    wire=session_stats_wire,
)


__all__ = [
    "ProjectionDefinition",
    "ProjectionHandle",
    "ProjectionWire",
    "SessionProjectionRegistry",
    "UnitCell",
    "Registration",
    "SessionStatsTotals",
    "SessionStatsState",
    "session_stats_projection_definition",
]
