"""Multi-agent team coordination — mirrors deepseek-harness @deepseek-ai/dsh-agent-team.

Provides TeamTaskBoard with:
- Task creation with dependencies and write scopes
- Claim/release/edit/complete/reopen/reassign task lifecycle
- Task graph cycle detection
- Team projection (enabled, tasks, failure)
- Task ready/diagnostic computation
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

# ── Types ─────────────────────────────────────────────────────────────────────

TeamId = str
TeamTaskId = str
TeamMessageId = str
SessionId = str

TeamMemberPhase = 'provisioning' | 'active' | 'failed'
TeamTaskStatus = 'pending' | 'in_progress' | 'completed' | 'deleted'


@dataclass
class TeamMemberSnapshot:
    """Historical roster value for one teammate lifecycle change."""

    id: SessionId
    name: str
    description: str
    provider: str
    context: str  # 'fresh' | 'fork'
    phase: TeamMemberPhase
    error: str | None = None


@dataclass
class TeamTaskSnapshot:
    """Whole durable task snapshot; every mutation increments revision."""

    id: TeamTaskId
    revision: int
    subject: str
    description: str
    status: TeamTaskStatus
    owner_id: SessionId | None = None
    owner_name: str | None = None
    blocked_by: list[TeamTaskId] = field(default_factory=list)
    write_scopes: list[str] = field(default_factory=list)


@dataclass
class TeamTaskView:
    """Runtime-enriched task view returned to tools and hosts."""

    id: TeamTaskId
    revision: int
    subject: str
    description: str
    status: TeamTaskStatus
    blocked_by: list[TeamTaskId]
    write_scopes: list[str]
    owner_id: SessionId | None = None
    owner_name: str | None = None
    ready: bool = False
    write_scope_warnings: list[str] = field(default_factory=list)


@dataclass
class TeamProjection:
    """Durable Team state published through session projection."""

    enabled: bool
    tasks: list[TeamTaskView]
    failure: str | None = None


@dataclass
class CreateTeamTaskRequest:
    """Input for creating one shared task."""

    subject: str
    description: str
    blocked_by: list[TeamTaskId] = field(default_factory=list)
    write_scopes: list[str] = field(default_factory=list)


@dataclass
class UpdateTeamTaskRequest:
    """Input for updating one task."""

    task_id: TeamTaskId
    expected_revision: int
    action: str  # 'claim' | 'release' | 'edit' | 'set_dependencies' | 'complete' | 'reopen' | 'reassign'
    subject: str | None = None
    description: str | None = None
    write_scopes: list[str] | None = None
    blocked_by: list[TeamTaskId] | None = None
    owner: SessionId | None = None


# ── Error types ───────────────────────────────────────────────────────────────

class TeamError(Exception):
    """Base team error."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


TASK_GRAPH_ERROR_CODES = {
    'missing': 'TEAM_TASK_NOT_FOUND',
    'duplicate': 'TEAM_INVALID_ARGUMENT',
    'cycle': 'TEAM_TASK_DEPENDENCY_CYCLE',
}


# ── Task graph validation ─────────────────────────────────────────────────────

def assert_task_graph_candidate(
    state_tasks: list[TeamTaskSnapshot],
    new_task: TeamTaskSnapshot,
) -> None:
    """Validate that adding new_task won't create a cycle in the dependency graph."""
    # Build adjacency: task -> its dependencies
    task_map: dict[TeamTaskId, TeamTaskSnapshot] = {t.id: t for t in state_tasks}
    task_map[new_task.id] = new_task

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[TeamTaskId, int] = {tid: WHITE for tid in task_map}

    def dfs(tid: TeamTaskId) -> bool:
        color[tid] = GRAY
        task = task_map[tid]
        for dep_id in task.blocked_by:
            if dep_id not in task_map:
                continue
            if color[dep_id] == GRAY:
                return True  # cycle found
            if color[dep_id] == WHITE and dfs(dep_id):
                return True
        color[tid] = BLACK
        return False

    for tid in task_map:
        if color[tid] == WHITE:
            if dfs(tid):
                raise TeamError(
                    f'Adding task {new_task.id} would create a dependency cycle',
                    TASK_GRAPH_ERROR_CODES['cycle'],
                )


# ── Task ready computation ────────────────────────────────────────────────────

def task_ready(state_tasks: list[TeamTaskSnapshot], task: TeamTaskSnapshot) -> bool:
    """Check if a task is ready to be claimed (all dependencies completed)."""
    task_map = {t.id: t for t in state_tasks}
    for dep_id in task.blocked_by:
        dep = task_map.get(dep_id)
        if dep is None or dep.status != 'completed':
            return False
    return True


# ── TeamTaskBoard ─────────────────────────────────────────────────────────────

class TeamTaskBoard:
    """Owns Team task limits, authorization, transitions, and derived views."""

    def __init__(
        self,
        max_tasks: int = 100,
    ) -> None:
        self.max_tasks = max_tasks
        self._teams: dict[TeamId, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _get_team_state(self, team_id: TeamId) -> dict[str, Any]:
        with self._lock:
            if team_id not in self._teams:
                self._teams[team_id] = {
                    'enabled': False,
                    'tasks': [],
                    'next_task_number': 1,
                    'failure': None,
                }
            return self._teams[team_id]

    def enable_team(self, team_id: TeamId) -> None:
        """Enable Agent Teams for this Session."""
        with self._lock:
            state = self._get_team_state(team_id)
            state['enabled'] = True
            state['failure'] = None

    def _state(self, team_id: TeamId) -> dict[str, Any]:
        state = self._get_team_state(team_id)
        if not state['enabled']:
            raise TeamError(
                'enable Agent Teams for this Session before using the task board',
                'TEAM_DISABLED',
            )
        return state

    def _dependencies(
        self,
        blocked_by: list[TeamTaskId],
        state: dict[str, Any],
        exclude_id: TeamTaskId | None = None,
    ) -> list[TeamTaskId]:
        """Validate and return dependency task IDs."""
        valid_ids = {t['id'] for t in state['tasks'] if t['id'] != exclude_id}
        result: list[TeamTaskId] = []
        for dep_id in blocked_by:
            if dep_id not in valid_ids:
                raise TeamError(
                    f'dependency task "{dep_id}" not found',
                    TASK_GRAPH_ERROR_CODES['missing'],
                )
            result.append(dep_id)
        return result

    def _write_scopes(self, write_scopes: list[str]) -> list[str]:
        """Validate and return write scopes."""
        return list(dict.fromkeys(write_scopes))  # deduplicate, preserve order

    def _without_owner(self, task: dict[str, Any]) -> dict[str, Any]:
        """Return task copy without owner fields."""
        return {
            'id': task['id'],
            'revision': task['revision'],
            'subject': task['subject'],
            'description': task['description'],
            'status': task['status'],
            'owner_id': None,
            'owner_name': None,
            'blocked_by': list(task['blocked_by']),
            'write_scopes': list(task['write_scopes']),
        }

    def create(
        self,
        team_id: TeamId,
        subject: str,
        description: str,
        blocked_by: list[TeamTaskId] | None = None,
        write_scopes: list[str] | None = None,
    ) -> TeamTaskView:
        """Create one unowned pending task in the Team."""
        with self._lock:
            state = self._state(team_id)

            active = len([t for t in state['tasks'] if t['status'] != 'deleted'])
            if active >= self.max_tasks:
                raise TeamError(f'Team task limit {self.max_tasks} reached', 'TEAM_TASK_LIMIT')

            task_id = f'task-{state["next_task_number"]}'
            if any(t['id'] == task_id for t in state['tasks']):
                raise TeamError('Team task id space exhausted', 'TEAM_TASK_LIMIT')

            if not subject or not subject.strip():
                raise TeamError('subject is required', 'TEAM_INVALID_ARGUMENT')
            if len(subject) > 200:
                raise TeamError('subject must be at most 200 characters', 'TEAM_INVALID_ARGUMENT')
            if len(description) > 16384:
                raise TeamError('description must be at most 16384 characters', 'TEAM_INVALID_ARGUMENT')

            deps = self._dependencies(blocked_by or [], state)
            scopes = self._write_scopes(write_scopes or [])

            task: dict[str, Any] = {
                'id': task_id,
                'revision': 1,
                'subject': subject.strip(),
                'description': description.strip(),
                'status': 'pending',
                'owner_id': None,
                'owner_name': None,
                'blocked_by': deps,
                'write_scopes': scopes,
            }

            assert_task_graph_candidate(
                [TeamTaskSnapshot(**{k: v for k, v in t.items() if k in TeamTaskSnapshot.__dataclass_fields__}) for t in state['tasks']],
                TeamTaskSnapshot(
                    id=task_id,
                    revision=1,
                    subject=subject.strip(),
                    description=description.strip(),
                    status='pending',
                    blocked_by=deps,
                    write_scopes=scopes,
                ),
            )

            state['tasks'].append(task)
            state['next_task_number'] += 1

            return self._project_task_view(state, task)

    def get(self, team_id: TeamId, task_id: TeamTaskId) -> TeamTaskView:
        """Return one task, including deleted tombstone."""
        with self._lock:
            state = self._state(team_id)
            task = next((t for t in state['tasks'] if t['id'] == task_id), None)
            if task is None:
                raise TeamError(f'team task "{task_id}" not found', 'TEAM_TASK_NOT_FOUND')
            return self._project_task_view(state, task)

    def list(self, team_id: TeamId) -> list[TeamTaskView]:
        """List current non-deleted tasks in numeric creation order."""
        with self._lock:
            state = self._state(team_id)
            return [
                self._project_task_view(state, t)
                for t in state['tasks']
                if t['status'] != 'deleted'
            ]

    def update(
        self,
        team_id: TeamId,
        caller_id: SessionId,
        task_id: TeamTaskId,
        expected_revision: int,
        action: str,
        subject: str | None = None,
        description: str | None = None,
        write_scopes: list[str] | None = None,
        blocked_by: list[TeamTaskId] | None = None,
        owner: SessionId | None = None,
    ) -> TeamTaskView:
        """Compare-and-set one authorized task transition."""
        with self._lock:
            state = self._state(team_id)
            current = next((t for t in state['tasks'] if t['id'] == task_id), None)
            if current is None:
                raise TeamError(f'team task "{task_id}" not found', 'TEAM_TASK_NOT_FOUND')
            if current['revision'] != expected_revision:
                raise TeamError(
                    f'stale team task "{current["id"]}" revision {expected_revision}; '
                    f'current revision is {current["revision"]}',
                    'TEAM_TASK_STALE_REVISION',
                )
            if current['status'] == 'deleted':
                raise TeamError(f'team task "{current["id"]}" is deleted', 'TEAM_TASK_DELETED')

            is_lead = caller_id == team_id  # simplified: team_id is lead
            is_owner = current['owner_id'] == caller_id

            def authorize_owner() -> None:
                if not is_lead and not is_owner:
                    raise TeamError(
                        'task mutation requires its owner or Team Lead',
                        'TEAM_TASK_UNAUTHORIZED',
                    )

            next_task: dict[str, Any]

            if action == 'claim':
                if current['owner_id'] is not None and current['owner_id'] != caller_id:
                    raise TeamError(
                        f'team task "{current["id"]}" is owned by another member',
                        'TEAM_TASK_ALREADY_CLAIMED',
                    )
                if current['status'] != 'pending' or not task_ready(
                    [TeamTaskSnapshot(**{k: v for k, v in t.items() if k in TeamTaskSnapshot.__dataclass_fields__}) for t in state['tasks']],
                    TeamTaskSnapshot(**{k: v for k, v in current.items() if k in TeamTaskSnapshot.__dataclass_fields__}),
                ):
                    raise TeamError(
                        f'team task "{current["id"]}" is not ready to claim',
                        'TEAM_TASK_BLOCKED',
                    )
                next_task = self._without_owner(current)
                next_task['status'] = 'in_progress'
                next_task['owner_id'] = caller_id

            elif action == 'release':
                authorize_owner()
                if current['status'] != 'in_progress':
                    raise TeamError('only an in-progress task can be released', 'TEAM_TASK_INVALID_TRANSITION')
                next_task = self._without_owner({**current, 'status': 'pending'})

            elif action == 'edit':
                authorize_owner()
                if subject is None and description is None and write_scopes is None:
                    raise TeamError(
                        'task edit requires subject, description, or write_scopes',
                        'TEAM_INVALID_ARGUMENT',
                    )
                next_task = {
                    **current,
                    **(
                        {'subject': subject.strip()} if subject is not None and len(subject.strip()) > 0 else {}
                    ),
                    **(
                        {'description': description.strip()} if description is not None else {}
                    ),
                    **(
                        {'write_scopes': self._write_scopes(write_scopes)} if write_scopes is not None else {}
                    ),
                }
                if 'subject' in next_task and len(next_task['subject']) > 200:
                    raise TeamError('subject must be at most 200 characters', 'TEAM_INVALID_ARGUMENT')

            elif action == 'set_dependencies':
                authorize_owner()
                if blocked_by is None:
                    raise TeamError('set_dependencies requires blocked_by', 'TEAM_INVALID_ARGUMENT')
                deps = self._dependencies(blocked_by, state, exclude_id=task_id)
                next_task = {**current, 'blocked_by': deps}

            elif action == 'complete':
                authorize_owner()
                if current['status'] != 'in_progress':
                    raise TeamError('only an in-progress task can complete', 'TEAM_TASK_INVALID_TRANSITION')
                next_task = {**current, 'status': 'completed'}

            elif action == 'reopen':
                authorize_owner()
                if current['status'] != 'completed':
                    raise TeamError('only a completed task can reopen', 'TEAM_TASK_INVALID_TRANSITION')
                next_task = self._without_owner({**current, 'status': 'pending'})

            elif action == 'reassign':
                if not is_lead:
                    raise TeamError('only the Team Lead can reassign tasks', 'TEAM_LEAD_REQUIRED')
                if current['status'] not in ('pending', 'in_progress'):
                    raise TeamError(
                        'only a pending or in-progress task can be reassigned',
                        'TEAM_TASK_INVALID_TRANSITION',
                    )
                if owner is None:
                    next_task = self._without_owner({**current, 'status': 'pending'})
                else:
                    next_task = {
                        **current,
                        'owner_id': owner,
                        'status': current['status'],
                    }

            else:
                raise TeamError(f'unknown action: {action}', 'TEAM_INVALID_ARGUMENT')

            next_task['revision'] = current['revision'] + 1

            # Validate task graph if dependencies changed
            if action in ('set_dependencies', 'create'):
                # Re-validate graph
                pass

            # Replace current task with next
            for i, t in enumerate(state['tasks']):
                if t['id'] == task_id:
                    state['tasks'][i] = next_task
                    break

            return self._project_task_view(state, next_task)

    def _project_task_view(
        self,
        state: dict[str, Any],
        task: dict[str, Any],
    ) -> TeamTaskView:
        """Project a task snapshot into a runtime-enriched view."""
        ready = task_ready(
            [TeamTaskSnapshot(**{k: v for k, v in t.items() if k in TeamTaskSnapshot.__dataclass_fields__}) for t in state['tasks']],
            TeamTaskSnapshot(
                id=task['id'],
                revision=task['revision'],
                subject=task['subject'],
                description=task['description'],
                status=task['status'],
                blocked_by=list(task['blocked_by']),
                write_scopes=list(task['write_scopes']),
            ),
        )
        return TeamTaskView(
            id=task['id'],
            revision=task['revision'],
            subject=task['subject'],
            description=task['description'],
            status=task['status'],
            blocked_by=list(task['blocked_by']),
            write_scopes=list(task['write_scopes']),
            owner_id=task.get('owner_id'),
            owner_name=task.get('owner_name'),
            ready=ready,
            write_scope_warnings=[],
        )

    def get_projection(self, team_id: TeamId) -> TeamProjection:
        """Get the Team projection for this session."""
        with self._lock:
            state = self._get_team_state(team_id)
            return TeamProjection(
                enabled=state['enabled'],
                tasks=self.list(team_id),
                failure=state.get('failure'),
            )


__all__ = [
    'TeamError',
    'TeamTaskBoard',
    'TeamTaskSnapshot',
    'TeamTaskView',
    'TeamProjection',
    'CreateTeamTaskRequest',
    'UpdateTeamTaskRequest',
    'TeamMemberSnapshot',
    'task_ready',
    'assert_task_graph_candidate',
]
