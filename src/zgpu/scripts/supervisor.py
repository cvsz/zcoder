#!/usr/bin/env python3
"""Unified supervisor for all 4 zGPU services."""

from __future__ import annotations

import logging
import sys
import threading
import time

from zgpu.cluster.worker.cpu_worker import run_cpu_worker
from zgpu.compiler.service import run_compiler_service
from zgpu.dashboard.server import run_dashboard
from zgpu.llm.server import run_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("zGPU-Supervisor")


def main():
    services = [
        ("LLM Server (8880)", run_server, {"port": 8880}),
        ("Dashboard (9000)", run_dashboard, {"port": 9000}),
        ("Compiler Studio (9100)", run_compiler_service, {"port": 9100}),
        ("CPU Worker (9200)", run_cpu_worker, {"port": 9200}),
    ]

    threads = []
    for name, func, kwargs in services:
        t = threading.Thread(target=func, kwargs=kwargs, name=name, daemon=True)
        t.start()
        threads.append(t)
        log.info("Started %s", name)

    log.info("All zGPU services are active and running!")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Received interrupt, shutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()
