"""
zcoder.session.replay — Session replay engine.

Replays session events to reconstruct model-visible requests. Given a session
log, the replayer can reconstruct the sequence of model requests that were
made, including tool calls and their results, allowing the same conversation
to be replayed deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zcoder.session.event import EventType, SessionEvent
from zcoder.session.logger import SessionEventStore


@dataclass(frozen=True)
class ModelRequest:
    """Reconstructed model request from session events.

    @param event_id - the event id that triggered this request
    @param timestamp - when the request was made
    @param system - system prompt
    @param messages - conversation messages (user/assistant/tool)
    @param model - model name
    @param parameters - model parameters (temperature, max_tokens, etc.)
    @param tool_calls - tool calls made in this request
    """

    event_id: str
    timestamp: str
    system: str | None
    messages: list[dict[str, Any]]
    model: str | None
    parameters: dict[str, Any]
    tool_calls: list[dict[str, Any]]


@dataclass(frozen=True)
class ReplayedSession:
    """Result of replaying a session.

    @param session_id - the session id
    @param events - all session events in order
    @param model_requests - reconstructed model requests
    @param tool_results - tool results recorded during the session
    """

    session_id: str
    events: list[SessionEvent]
    model_requests: list[ModelRequest]
    tool_results: list[dict[str, Any]]


# ── Convenience functions ─────────────────────────────────────────────────────


def replay_session(store: SessionEventStore, session_id: str) -> ReplayedSession:
    """Replay a session by id (convenience wrapper around SessionReplay).

    @param store - session event store
    @param session_id - session id to replay
    @returns ReplayedSession with all events and reconstructed model requests
    """
    return SessionReplay(store).replay(session_id)


class SessionReplay:
    """Replays session events into model-visible requests.

    Folds through session events in order, reconstructing model requests
    from the sequence of user messages, tool results, and tool calls.
    """

    def __init__(self, store: SessionEventStore) -> None:
        self.store = store

    def replay(self, session_id: str) -> ReplayedSession:
        """Replay a session by id.

        @param session_id - session id to replay
        @returns ReplayedSession with all events and reconstructed model requests
        """
        events = self.store.get_events(session_id, include_ignorable=False)
        return self.replay_events(session_id, events)

    def replay_events(self, session_id: str, events: list[SessionEvent]) -> ReplayedSession:
        """Replay from an explicit list of events.

        @param session_id - session id for the result
        @param events - ordered list of session events
        @returns ReplayedSession
        """
        model_requests: list[ModelRequest] = []
        tool_results: list[dict[str, Any]] = []

        # Accumulator state
        current_messages: list[dict[str, Any]] = []
        system_prompt: str | None = None
        model_name: str | None = None
        parameters: dict[str, Any] = {}
        pending_tool_calls: list[dict[str, Any]] = []

        for event in events:
            kind = event.event_type
            payload = event.payload

            if kind == EventType.SYSTEM_MESSAGE:
                system_prompt = payload.get("content")
                current_messages = [{"role": "system", "content": system_prompt}] if system_prompt else []

            elif kind == EventType.USER_MESSAGE:
                current_messages.append({"role": "user", "content": payload.get("content", "")})

            elif kind == EventType.ASSISTANT_MESSAGE:
                current_messages.append(
                    {
                        "role": "assistant",
                        "content": payload.get("content", ""),
                    }
                )
                # Emit a model request when we see an assistant message
                # (this represents a completed turn)
                model_requests.append(
                    ModelRequest(
                        event_id=str(event.event_id),
                        timestamp=event.timestamp,
                        system=system_prompt,
                        messages=list(current_messages),
                        model=model_name,
                        parameters=dict(parameters),
                        tool_calls=list(pending_tool_calls),
                    )
                )
                pending_tool_calls = []

            elif kind == EventType.TOOL_CALL:
                pending_tool_calls.append(
                    {
                        "name": payload.get("toolName", ""),
                        "arguments": payload.get("arguments", {}),
                        "event_id": str(event.event_id),
                    }
                )
                current_messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {"name": payload.get("toolName", ""), "arguments": payload.get("arguments", {})}
                        ],
                    }
                )

            elif kind == EventType.TOOL_RESULT:
                tool_results.append(
                    {
                        "tool_name": payload.get("toolName", ""),
                        "result": payload.get("result"),
                        "event_id": str(event.event_id),
                    }
                )
                current_messages.append(
                    {
                        "role": "tool",
                        "content": str(payload.get("result", "")),
                        "tool_call_id": payload.get("tool_call_id", ""),
                    }
                )

            elif kind == EventType.REQUEST_HEADER:
                # Capture model info from request header if present
                header = payload.get("header", {})
                if header.get("model"):
                    model_name = header["model"]
                if header.get("parameters"):
                    parameters.update(header["parameters"])

        return ReplayedSession(
            session_id=session_id,
            events=events,
            model_requests=model_requests,
            tool_results=tool_results,
        )
