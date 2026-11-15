#!/usr/bin/env python3
"""
deploy.py — ZCoder deployment smoke test (Phase 9).

ตรวจสอบว่าระบบ ZCoder ทำงานถูกต้องหลังจากติดตั้งหรือปรับใช้:
  1. GET /api/health        — backend ตอบสนองและ healthy
  2. GET /api/models        — คืนรายชื่อโมเดลที่เปิดใช้งาน
  3. POST /api/chat         — ส่ง prompt และรับคำตอบจากโมเดล
  4. Model sector health    — แต่ละ sector ที่ enabled ตอบ health check

ใช้งาน:
    python scripts/deploy.py

ตัวแปรสภาพแวดล้อมที่อ่าน:
    ZCODER_BASE_URL         backend base URL (default: http://0.0.0.0:8420)
    ZCODER_WEB_API_KEY      bearer token สำหรับ authenticated endpoints
    ZCODER_MODEL            โมเดลที่ใช้ทดสอบแชท (default: zcoder-flash)
    ZCODER_MODELS_CONFIG    path ไปยัง config/models.yaml (default: config/models.yaml)

คืนค่า exit code 0 ถ้าทุกขั้นตอนผ่าน, ไม่ใช่ศูนย์ถ้ามีขั้นตอนใดล้มเหลว
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


BASE_URL = os.getenv("ZCODER_BASE_URL", "http://0.0.0.0:8420").rstrip("/")
API_KEY = os.getenv("ZCODER_WEB_API_KEY", "")
TEST_MODEL = os.getenv("ZCODER_MODEL", "zcoder-flash")
MODELS_CONFIG = os.getenv("ZCODER_MODELS_CONFIG", "config/models.yaml")


def log(msg: str, level: str = "INFO") -> None:
    print(f"[{level}] {msg}", flush=True)


def http_get(path: str, headers: dict[str, str] | None = None, timeout: float = 10.0) -> Any:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except (urllib.error.URLError, OSError) as exc:
        return None, f"connection error: {exc}"


def http_post(path: str, payload: dict, headers: dict[str, str] | None = None, timeout: float = 30.0) -> Any:
    url = f"{BASE_URL}{path}"
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except (urllib.error.URLError, OSError) as exc:
        return None, f"connection error: {exc}"


def fail(message: str) -> None:
    log(f"FAIL: {message}", "ERROR")
    sys.exit(1)


def pass_(message: str) -> None:
    log(f"PASS: {message}")


def main() -> int:
    global TEST_MODEL
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}

    # ── 1. Health check ──────────────────────────────────────────
    status, data = http_get("/api/health", headers=headers)
    if status != 200:
        fail(f"/api/health returned HTTP {status}: {data}")
    if isinstance(data, dict) and data.get("status") != "healthy":
        fail(f"/api/health status is not healthy: {data}")
    pass_("GET /api/health -> healthy")

    # ── 2. Models list ───────────────────────────────────────────
    status, data = http_get("/api/models", headers=headers)
    if status != 200:
        fail(f"/api/models returned HTTP {status}: {data}")
    if not isinstance(data, list) or len(data) == 0:
        fail(f"/api/models returned no models: {data}")
    model_names = [m.get("id") for m in data if isinstance(m, dict)]
    pass_(f"GET /api/models -> {len(model_names)} model(s): {', '.join(model_names)}")

    # ถ้าโมเดลที่จะทดสอบไม่อยู่ในรายชื่อ ให้ใช้ตัวแรกที่เปิดใช้งาน
    if TEST_MODEL not in model_names and model_names:
        log(f"WARNING: {TEST_MODEL} not in model list, using {model_names[0]} instead", "WARN")
        TEST_MODEL = model_names[0]

    # ── 3. Chat endpoint ─────────────────────────────────────────
    status, data = http_post(
        "/api/chat",
        {"prompt": "hello", "model": TEST_MODEL, "max_tokens": 16},
        headers=headers,
    )
    if status != 200:
        fail(f"/api/chat returned HTTP {status}: {data}")
    if not isinstance(data, dict) or not data.get("response"):
        fail(f"/api/chat did not return a response: {data}")
    pass_(f"POST /api/chat -> model={TEST_MODEL}, response_len={len(data.get('response',''))}")

    # ── 4. Model sector health ───────────────────────────────────
    cfg_path = Path(MODELS_CONFIG)
    if not cfg_path.exists():
        log(f"WARNING: {MODELS_CONFIG} not found, skipping sector health check", "WARN")
        log("SMOKE TEST PASSED", "INFO")
        return 0

    with cfg_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    sectors = cfg.get("sectors", []) or []
    enabled = [s for s in sectors if s.get("enabled")]
    if not enabled:
        log("WARNING: no enabled sectors in config, skipping sector health check", "WARN")
        log("SMOKE TEST PASSED", "INFO")
        return 0

    all_healthy = True
    for sector in enabled:
        name = sector["name"]
        port = sector.get("port")
        host = sector.get("host", "0.0.0.0")
        sector_url = f"http://{host}:{port}/health"
        try:
            req = urllib.request.Request(sector_url, headers={"Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    pass_(f"sector {name} ({host}:{port}) -> healthy")
                else:
                    all_healthy = False
                    log(f"FAIL: sector {name} returned HTTP {resp.status}", "ERROR")
        except (urllib.error.URLError, OSError) as exc:
            all_healthy = False
            log(f"FAIL: sector {name} ({host}:{port}) connection error: {exc}", "ERROR")

    if not all_healthy:
        fail("one or more enabled model sectors are not healthy")

    # ── Done ─────────────────────────────────────────────────────
    log("SMOKE TEST PASSED", "INFO")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("interrupted by user", "WARN")
        sys.exit(130)
