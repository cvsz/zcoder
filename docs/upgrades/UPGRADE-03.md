# UPGRADE-03: Server Tool Version Drift & Files API Alignment

## Overview
Upgrade-03 aligns zcoder with updated server tools and containerized code execution protocols:

1. **Server Tool Version Upgrades:**
   - Bumped tool specifications (`code_execution_20260521`, `web_search_20260318`, `web_fetch_20260318`).

2. **Files API Content Block Alignment:**
   - Refactored `claude_code_exec.py` to upload input files using `container_upload` content blocks instead of generic document blocks.

3. **Output Cache Stripping:**
   - Ensured raw tool response caches are pruned when consumed directly by sandbox execution engines.
