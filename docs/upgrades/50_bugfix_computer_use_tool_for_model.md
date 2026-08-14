# Bugfix — `computer_use_tool_for_model()` didn't exist

## What was broken

`claude_tools.py` defined `SERVER_TOOLS["computer_use"]`, the
`COMPUTER_USE_TOOL_VERSIONS` / `_COMPUTER_USE_2025_01_24_MODELS` lookup
tables, and a call site in `generate_with_server_tools()`:

```python
if name == "computer_use":
    tool, beta = computer_use_tool_for_model(self.model)
```

but the function itself had no `def` line. Its docstring and body were
indented at the same level as `check_retired_tool_version()`'s body, so
Python parsed them as unreachable statements tacked onto the end of that
*other* function (dead code after its `return`, which is legal syntax —
no `IndentationError`, no import-time failure). The name
`computer_use_tool_for_model` was never bound at module scope.

Net effect: `import claude_tools` succeeded, the full test suite passed,
but calling `generate_with_server_tools(..., ["computer_use"])` — or
anything else that referenced `computer_use_tool_for_model` — raised
`NameError: name 'computer_use_tool_for_model' is not defined` at
runtime. There was no test covering the `"computer_use"` branch, which is
why this shipped unnoticed.

## Fix

- Restored the missing `def computer_use_tool_for_model(model: str,
  width: int = 1024, height: int = 768):` line so the function is a real,
  callable module member again.
- `generate_with_server_tools()`'s `computer_use` branch now passes
  `SERVER_TOOLS["computer_use"]`'s `display_width_px` /
  `display_height_px` through explicitly instead of relying only on the
  function's hardcoded defaults, so a future change to the `SERVER_TOOLS`
  default doesn't silently diverge from what actually gets sent.
- Added 5 new tests in `tests/test_claude_tools.py`:
  - `computer_use_tool_for_model` exists and is callable
  - current-generation models get the `2025-11-24` pairing
  - older models (e.g. `claude-sonnet-4-5`) get the `2025-01-24` pairing
  - custom width/height are honored
  - `generate_with_server_tools(..., ["computer_use"])` builds a valid
    tool dict end-to-end without raising

## Also fixed while auditing for bugs (not features)

- `claude_admin_api.py`: `_default_date_range()` used
  `datetime.utcnow()`, which is deprecated in current Python and
  scheduled for removal. Switched to
  `datetime.now(timezone.utc).date()` (behavior-identical here since
  only `.date()` is used). This was surfacing as a `DeprecationWarning`
  on every test run touching usage/cost reporting.

## What was checked and found to be non-issues

- `ruff`/`pyflakes` also flagged ~30 "f-string is missing placeholders"
  warnings across the tree (e.g. `f"✓ Committed."`) — cosmetic only, no
  functional effect, left as-is rather than churning unrelated diffs.
- A few "local variable assigned but never used" cases
  (`claude_memory.py`'s `prot`, `artifacts.py`'s `meta`,
  `claude_files.py`'s `crlf`) are harmless dead/unused values, not logic
  bugs — the code paths that used them still behave correctly without
  them. Left alone for the same reason.

## Test suite

485 passing before this cycle; 490 after (+5, all in
`tests/test_claude_tools.py`). No regressions.
