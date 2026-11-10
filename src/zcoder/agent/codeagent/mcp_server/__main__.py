"""Allow ``python -m zcoder.agent.codeagent.mcp_server`` to launch the MCP server."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from zcoder.agent.codeagent.mcp_server import MCPServer, run_http, run_stdio


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="zcoder-mcp-server")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport")
    parser.add_argument("--http", action="store_true", help="Use HTTP/SSE transport (default)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8422, help="HTTP port (default: 8422)")
    args = parser.parse_args()

    server = MCPServer(Path.cwd())
    if args.stdio:
        asyncio.run(run_stdio(server))
    else:
        run_http(server, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
