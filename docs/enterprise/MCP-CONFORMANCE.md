# MCP 2026-07-28 Conformance & Security

## Specification
ZCoder implements the Model Context Protocol (MCP) 2026-07-28 specification.

## Transports
- In-memory / Stdio transport.
- Security-wrapped tool registry with explicit JSON schema validation.

## Security Policies
- MCP tools execute in sandboxed handlers.
- File system and execution boundaries prevent unauthorized privilege escalation or credential access.
