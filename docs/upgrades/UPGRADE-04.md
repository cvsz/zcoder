# UPGRADE-04: Model Context Protocol (MCP) & Context Editing Engine

## Overview
Upgrade-04 delivers standardized Model Context Protocol (MCP) server integrations and context compaction:

1. **MCP Connector Engine:**
   - Multi-transport MCP client (stdio and SSE) allowing external tool server discovery and execution.

2. **Context Management & Compaction:**
   - Sliding-window context compaction and targeted context trimming for long-running agent workflows.

3. **Tool Permission Policies:**
   - Granular allow/deny rules per MCP tool invocation.
