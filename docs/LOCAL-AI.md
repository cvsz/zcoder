# Local AI Architecture & Execution Guide

## Overview
ZCoder includes a native Local AI execution stack capable of running offline with zero third-party commercial API keys.

## Providers
- **Ollama**: Default local provider (`http://127.0.0.1:11434`).
- **vLLM**: High-throughput OpenAI-compatible server.
- **Generic OpenAI-Compatible**: Any loopback service implementing standard completions.

## Hardware Profiling
The hardware profiler assesses CPU, RAM, and GPU/VRAM to conservatively estimate model fit (e.g. 7B Q4 models on ~16GB RAM systems).
