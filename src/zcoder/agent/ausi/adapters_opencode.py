"""
ausi/adapters_opencode.py — OpenCode CLI adapter for AUSI.

Wraps the OpenCode CLI (installed at ~/.opencode/bin/opencode) as a
BaseProviderAdapter, exposing the consistent AUSI interface.

Make targets already implemented:
  make opencode            — Interactive OpenCode CLI
  make opencode-prompt     — Execute a prompt (with free model fallback)
  make opencode-free-prompt — Execute using 100% free model
  make opencode-bg         — Run prompt in background
  make opencode-free-bg    — Run free model prompt in background
  make opencode-models     — List all available models
  make opencode-free-models — List free models
  make opencode-nvidia-models — List NVIDIA models
  make opencode-kilo-models — List Kilo models
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404  # required to run the local OpenCode CLI without a shell
import time
from typing import Any

from .adapters import (
    AdapterResult,
    BaseProviderAdapter,
    ProviderCapabilities,
    ProviderStatus,
)


class OpenCodeAdapter(BaseProviderAdapter):
    """Adapter that wraps the OpenCode CLI as an AUSI provider.

    Uses the `opencode` command-line tool installed at
    ~/.opencode/bin/opencode (or discovered via PATH).

    Wraps these OpenCode Make targets:
      - make opencode            — Interactive CLI
      - make opencode-prompt     — Execute prompt (with fallback)
      - make opencode-free-prompt — Free model only
      - make opencode-bg         — Background execution
      - make opencode-free-bg    — Free model background

    The adapter automatically uses the free model when the configured model
    fails or times out, ensuring FREE-FIRST behavior.
    """

    #: Name of this adapter instance
    adapter_name = "opencode"

    #: Default model — falls back to free model if configured model unavailable
    default_model: str = "opencode/nemotron-3.5-lightning-free"

    #: Free model fallback — used when configured model times out or fails
    free_model: str = "opencode/nemotron-3.5-lightning-free"

    def __init__(self, **kwargs):
        super().__init__(
            name=self.adapter_name,
            provider="opencode",
            **kwargs,
        )
        # Configure capabilities based on what we can actually do
        self.capabilities = ProviderCapabilities(
            supports_discover=True,
            supports_health_check=True,
            supports_list_models=True,
            supports_execute=True,
            supports_execute_background=True,
            supports_get_task_status=False,  # Not directly supported
            supports_cancel_task=False,  # Not directly supported
            supports_get_capabilities=True,
        )

    def _get_opencode_bin(self) -> str:
        """Find the OpenCode binary path."""
        bin_path = os.getenv("OPENCODE_BIN", "")
        if bin_path:
            return bin_path
        # Try common locations
        for candidate in [
            "/home/cvsz/.opencode/bin/opencode",
            os.path.expanduser("~/.opencode/bin/opencode"),
        ]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        # Fallback to PATH discovery without spawning a helper process.
        discovered = shutil.which("opencode")
        if discovered:
            return discovered
        raise RuntimeError("OpenCode binary not found")

    def _get_default_model(self) -> str:
        """Return the default model for this adapter."""
        return self.default_model

    def _run_opencode(self, prompt: str, model: str | None = None) -> AdapterResult:
        """Run a prompt via the OpenCode CLI.

        Args:
            prompt: The prompt/task to execute
            model: Model identifier. If None, uses self.default_model

        Returns:
            AdapterResult with the response text
        """
        model = model or self._get_default_model()
        opencode_bin = self._get_opencode_bin()

        # Strip any potential credentials from the prompt
        safe_prompt = self._strip_credentials(prompt)

        try:
            result = subprocess.run(  # nosec B603  # resolved local opencode binary, argv list, no shell
                [opencode_bin, "run", "-m", model, safe_prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                # OpenCode outputs to stdout; extract the response text
                # The output may include build markers like "> build · model-name"
                # We need to extract just the model's response text
                output = result.stdout
                # Try to extract the actual response (skip build markers)
                # Look for the last substantial line of text
                lines = output.strip().split("\n")
                # Filter out build marker lines
                text_lines = []
                for line in lines:
                    # Skip lines that are just build markers
                    if line.startswith("> build ·"):
                        continue
                    # Skip empty lines at the start/end
                    if line.strip() and not line.startswith(">"):
                        text_lines.append(line.strip())

                if text_lines:
                    # Join the response text, taking care about encoding
                    text = " ".join(text_lines)
                else:
                    text = output.strip()

                return AdapterResult(
                    success=True,
                    text=text,
                    model=model,
                    provider=self.provider,
                )
            else:
                # Command failed (timeout or error)
                stderr = result.stderr or ""
                return AdapterResult(
                    success=False,
                    text="",
                    model=model,
                    provider=self.provider,
                    error=f"OpenCode command failed (exit code {result.returncode}): {stderr[:200]}",
                )
        except subprocess.TimeoutExpired:
            return AdapterResult(
                success=False,
                text="",
                model=model,
                provider=self.provider,
                error="OpenCode command timed out after 120 seconds",
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                text="",
                model=model,
                provider=self.provider,
                error=f"Error running OpenCode: {str(e)[:200]}",
            )

    # ── AUSI interface implementations ──────────────────────────

    def discover(self) -> list[dict[str, Any]]:
        """List available OpenCode models by querying the CLI.

        Returns model information organized by provider.
        """
        try:
            opencode_bin = self._get_opencode_bin()
            result = subprocess.run(  # nosec B603  # resolved local opencode binary, argv list, no shell
                [opencode_bin, "models"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                # Parse the model listing output
                output = result.stdout
                models = self._parse_opencode_models(output)
                return models
            else:
                # Fall back to known OpenCode models
                return self._get_fallback_models()
        except Exception:
            return self._get_fallback_models()

    def _parse_opencode_models(self, output: str) -> list[dict[str, Any]]:
        """Parse the output of `opencode models` command.

        The output format consists of provider names followed by model listings.
        """
        models = []
        lines = output.split("\n")
        current_provider = None

        for line in lines:
            line = line.strip()
            # Check if this line is a provider header
            # Format: "provider_name/provider_model"
            # or just a category header
            if line and not line.startswith(" ") and "/" in line:
                # Could be a provider ID like "agentrouter/claude-opus-4-8"
                # or a model ID
                parts = line.split("/", 1)
                if len(parts) == 2:
                    # Check if the first part looks like a provider
                    # (all lowercase, no special chars)
                    if parts[0].islower() and len(parts[0]) > 0:
                        current_provider = parts[0]
                    else:
                        current_provider = None
                        # This might be a model ID
                        models.append(
                            {
                                "id": line,
                                "name": line,
                                "provider": self.provider,
                                "context_window": None,
                                "price_in": None,
                                "price_out": None,
                                "tier": None,
                            }
                        )
                else:
                    current_provider = None
            elif line and current_provider and not any(c.isupper() or c in ":/ " for c in line):
                # This looks like a model under the current provider
                models.append(
                    {
                        "id": line,
                        "name": line,
                        "provider": current_provider,
                        "context_window": None,
                        "price_in": None,
                        "price_out": None,
                        "tier": None,
                    }
                )
            elif line and (":free" in line or ":free" in line.lower()):
                # Free model marker
                if current_provider:
                    models.append(
                        {
                            "id": line,
                            "name": line,
                            "provider": current_provider,
                            "context_window": None,
                            "price_in": None,
                            "price_out": None,
                            "tier": None,
                        }
                    )

        # Deduplicate by ID
        seen = set()
        deduped = []
        for m in models:
            mid = m.get("id", "")
            if mid and mid not in seen:
                seen.add(mid)
                deduped.append(m)

        return deduped or self._get_fallback_models()

    def _get_fallback_models(self) -> list[dict[str, Any]]:
        """Return fallback model list when OpenCode CLI is unavailable.

        Returns known OpenCode models based on the CLI output we've seen.
        """
        return [
            {
                "id": "opencode/crouton-alpha-free",
                "name": "Crouton Alpha Free",
                "provider": self.provider,
                "context_window": None,
                "price_in": None,
                "price_out": None,
                "tier": None,
            },
            {
                "id": "opencode/pulse-alpha-free",
                "name": "Pulse Alpha Free",
                "provider": self.provider,
                "context_window": None,
                "price_in": None,
                "price_out": None,
                "tier": None,
            },
            {
                "id": "opencode/nemotron-3.5-super-vl-free",
                "name": "Nemotron 3.5 Super VL Free",
                "provider": self.provider,
                "context_window": None,
                "price_in": None,
                "price_out": None,
                "tier": None,
            },
            {
                "id": "opencode/flint-40b-free",
                "name": "Flint 40B Free",
                "provider": self.provider,
                "context_window": None,
                "price_in": None,
                "price_out": None,
                "tier": None,
            },
        ]

    def health_check(self) -> dict[str, str]:
        """Check OpenCode CLI health by running a simple command."""
        try:
            opencode_bin = self._get_opencode_bin()
            result = subprocess.run(  # nosec B603  # resolved local opencode binary, argv list, no shell
                [opencode_bin, "models"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                self._status = ProviderStatus.HEALTHY
                self._last_health_check = time.time()
                return {
                    "status": ProviderStatus.HEALTHY,
                    "latency_ms": str(int((time.time() - self._last_health_check) * 1000)),
                    "details": "OpenCode CLI responding correctly",
                }
            else:
                self._status = ProviderStatus.DEGRADED
                return {
                    "status": ProviderStatus.DEGRADED,
                    "error": "OpenCode CLI returned non-zero exit code",
                    "details": result.stderr[:200] if result.stderr else "unknown error",
                }
        except FileNotFoundError:
            self._status = ProviderStatus.UNHEALTHY
            return {
                "status": ProviderStatus.UNHEALTHY,
                "error": "OpenCode binary not found",
                "details": "Cannot locate opencode CLI at expected paths",
            }
        except subprocess.TimeoutExpired:
            self._status = ProviderStatus.DEGRADED
            return {
                "status": ProviderStatus.DEGRADED,
                "error": "OpenCode CLI health check timed out",
                "details": "The CLI did not respond within 30 seconds",
            }
        except Exception as e:
            self._status = ProviderStatus.UNHEALTHY
            return {
                "status": ProviderStatus.UNHEALTHY,
                "error": str(e)[:200],
                "details": "Unexpected error during health check",
            }

    def list_models(self) -> list[dict[str, Any]]:
        """List available models via the OpenCode CLI."""
        return self.discover()

    def execute(self, prompt: str, model: str | None = None, **options) -> AdapterResult:
        """Execute a prompt via OpenCode CLI.

        Uses the configured model (or free model fallback if the configured
        model fails).
        """
        # First try the configured model
        result = self._run_opencode(prompt, model or self._get_default_model())

        # If the configured model fails, try the free model (FREE-FIRST behavior)
        if not result.success and model != self.free_model:
            free_result = self._run_opencode(prompt, self.free_model)
            if free_result.success:
                # Free model succeeded - update result to reflect free model
                free_result.model = self.free_model
                return free_result
            # Both failed; return the original error
            return result

        return result

    def execute_background(
        self, prompt: str, model: str | None = None, **options
    ) -> tuple[str, dict[str, Any]]:
        """Execute a prompt asynchronously via OpenCode CLI.

        Starts a background OpenCode process and returns a task ID.
        """
        model = model or self._get_default_model()
        opencode_bin = self._get_opencode_bin()

        # Strip credentials from prompt
        safe_prompt = self._strip_credentials(prompt)

        try:
            # Use nohup to background the process
            env = os.environ.copy()
            # Ensure OpenCode can run
            proc = subprocess.Popen(  # nosec B603  # resolved local opencode binary, argv list, no shell
                [
                    opencode_bin,
                    "run",
                    "-m",
                    model,
                    safe_prompt,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            # Return the PID as the task ID, with basic metadata
            task_id = f"opencode-{proc.pid}"
            metadata = {
                "pid": proc.pid,
                "model": model,
                "provider": self.provider,
                "start_time": time.time(),
                "status": "queued",
            }

            return (task_id, metadata)
        except Exception as e:
            return ("", {"error": str(e)[:200], "status": "failed"})

    def get_task_status(self, task_id: str) -> AdapterResult:
        """Check status of a background OpenCode task.

        For the OpenCode adapter, task status is limited - we can only check
        if the process is still running by looking at the PID file.
        """
        # Try to read the PID file
        pid_file = os.getenv("OPENCODE_PID_FILE", ".opencode.pid")
        try:
            if os.path.exists(pid_file):
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                # Check if process is still running
                try:
                    os.kill(pid, 0)  # Signal 0 just checks existence
                    return AdapterResult(
                        success=True,
                        text="",
                        model="",
                        provider=self.provider,
                        task_id=task_id,
                        # We don't have detailed status, just that it's running
                    )
                except ProcessLookupError:
                    # Process has finished
                    return AdapterResult(
                        success=True,
                        text="",
                        model="",
                        provider=self.provider,
                        task_id=task_id,
                        error="Task completed (process no longer running)",
                    )
            else:
                # No PID file - task may have completed or not started
                return AdapterResult(
                    success=True,
                    text="",
                    model="",
                    provider=self.provider,
                    task_id=task_id,
                    error="No PID file found - task status unknown",
                )
        except ValueError:
            return AdapterResult(
                success=False,
                text="",
                model="",
                provider=self.provider,
                task_id=task_id,
                error="Invalid PID in status file",
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                text="",
                model="",
                provider=self.provider,
                task_id=task_id,
                error=f"Error checking task status: {str(e)[:200]}",
            )

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a background OpenCode task.

        For OpenCode, cancellation is limited - we can try to kill the process
        by PID if we can extract it from the task_id.
        """
        # Try to extract PID from task_id (format: opencode-PID)
        match = re.match(r"opencode-(\d+)", task_id)
        if match:
            pid = int(match.group(1))
            try:
                os.kill(pid, 9)  # SIGKILL
                return True
            except ProcessLookupError:
                # Process already finished
                return True
            except PermissionError:
                return False
            except Exception:
                return False
        else:
            # Can't identify the process to cancel
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Return the capabilities for this OpenCode adapter.

        OpenCode supports most AUSI operations natively through its CLI.
        """
        # Enhance the base capabilities with OpenCode-specific support
        caps = super().get_capabilities()
        caps.supports_execute_background = True
        caps.supports_get_task_status = True  # Can check PID-based status
        caps.supports_cancel_task = True  # Can kill process by PID
        return caps
