"""Authenticated local administration, compliance and agent API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from zcoder.api.auth import (
    AuthenticationUnavailable,
    RequestAuthenticationError,
    authenticate_request,
)
from zcoder.services.local_control import LocalAgentRunner, LocalControlStore

router = APIRouter(prefix="/local/v1", tags=["local-control"])
_store_instance: LocalControlStore | None = None


class RoleGrant(BaseModel):
    role: Literal["admin", "operator", "auditor"]


class TaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=32768)


class TaskDecision(BaseModel):
    approve: bool


def _get_store() -> LocalControlStore:
    global _store_instance
    if _store_instance is None:
        database = Path(
            os.environ.get(
                "ZCODER_LOCAL_CONTROL_DATABASE",
                "~/.local/share/zcoder/local-control.sqlite3",
            )
        ).expanduser()
        database.parent.mkdir(parents=True, exist_ok=True)
        store = LocalControlStore(database)
        bootstrap_subject = os.environ.get("ZCODER_LOCAL_BOOTSTRAP_ADMIN_SUBJECT", "").strip()
        organization_id = os.environ.get("ZCODER_LOCAL_ORGANIZATION_ID", "").strip()
        if bootstrap_subject and organization_id:
            with store._connect() as db:
                empty = db.execute("SELECT 1 FROM principals LIMIT 1").fetchone() is None
            if empty:
                store.bootstrap_admin(bootstrap_subject)
        _store_instance = store
    return _store_instance


def _actor(request: Request) -> str:
    expected_org = os.environ.get("ZCODER_LOCAL_ORGANIZATION_ID", "").strip()
    if not expected_org:
        raise HTTPException(status_code=503, detail="Local control organization is not configured")
    try:
        context = authenticate_request(request.headers)
    except AuthenticationUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc
    except RequestAuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if context.organization_id != expected_org:
        raise HTTPException(status_code=403, detail="Identity is outside the configured local organization")
    return context.principal_id


def _invoke(action):
    try:
        return action()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/principals")
def list_principals(request: Request):
    actor = _actor(request)
    rows = _invoke(lambda: _get_store().list_principals(actor))
    return {"principals": [{"principal": name, "role": role} for name, role in rows]}


@router.put("/admin/principals/{principal}")
def grant_principal_role(principal: str, body: RoleGrant, request: Request):
    actor = _actor(request)
    _invoke(lambda: _get_store().grant_role(actor, principal, body.role))
    return {"principal": principal, "role": body.role}


@router.get("/compliance/audit")
def export_audit(request: Request):
    actor = _actor(request)
    store = _get_store()
    rows = _invoke(lambda: store.audit_records(actor))
    verified = _invoke(lambda: store.verify_audit_chain(actor))
    return {
        "verified": verified,
        "records": [
            {
                "sequence": row[0],
                "timestamp": row[1],
                "actor": row[2],
                "action": row[3],
                "subject": row[4],
                "previous_hash": row[5],
                "entry_hash": row[6],
            }
            for row in rows
        ],
    }


@router.post("/tasks", status_code=201)
def create_task(body: TaskRequest, request: Request):
    actor = _actor(request)
    _invoke(lambda: _get_store().create_task(actor, body.task_id, body.description))
    return _invoke(lambda: _get_store().get_task(actor, body.task_id))


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    actor = _actor(request)
    return _invoke(lambda: _get_store().get_task(actor, task_id))


@router.post("/tasks/{task_id}/decision")
def decide_task(task_id: str, body: TaskDecision, request: Request):
    actor = _actor(request)
    _invoke(lambda: _get_store().decide_task(actor, task_id, body.approve))
    return _invoke(lambda: _get_store().get_task(actor, task_id))


@router.post("/tasks/{task_id}/run")
def run_task(task_id: str, request: Request):
    actor = _actor(request)
    try:
        response = LocalAgentRunner(_get_store()).run(actor, task_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"task_id": task_id, "result": response}
