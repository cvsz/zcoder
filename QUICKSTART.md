# Quickstart

## Run from source with a local GGUF model

Start llama.cpp in a separate terminal:

```bash
llama-server \
  --model /home/cvsz/zgpu/qwen-7b-q4km.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096
```

Then install and run ZCoder:

```bash
make setup
export ZCODER_BASE_URL=http://127.0.0.1:8080/v1
export ZCODER_MODEL=zqwen2.5-coder-7b-instruct-q4_k_m
zcoder -p "Write a function to reverse a string"
```

For a smaller model, load `/home/cvsz/zgpu/qwen-1.5b-q4km.gguf` in the server.
See [Local inference configuration](docs/guides/LOCAL-INFERENCE.md) for
details and endpoint checks.

## Choose the installation directory

The destination is an exact virtual-environment path, not a parent directory.
Choose it before installation; Python virtual environments are not generally
relocatable after creation. Paths may contain spaces. Explicit relative paths
are resolved against the directory from which you invoke the command.

```bash
./setup.sh --install-dir "$HOME/Apps/zcoder"
"$HOME/Apps/zcoder/bin/zcoder" --version
```

On Windows (Command Prompt):

```bat
setup.bat --install-dir "D:\Apps\ZCoder"
"D:\Apps\ZCoder\Scripts\zcoder.exe" --version
```

With no `--install-dir`, the setup script creates the repository `venv` and
installs an editable package. The `ZCODER_VENV` environment variable is also
supported.

## Build a standalone executable

Python is required to build the executable, but not to run it:

```bash
./build.sh --dist-dir "$HOME/Downloads/zcoder-release"
"$HOME/Downloads/zcoder-release/zcoder" --version
```

On Windows:

```bat
build.bat --dist-dir "D:\Releases\ZCoder"
"D:\Releases\ZCoder\zcoder.exe" --version
```

Builds produce platform-specific executables and do not bundle model weights.
Create and validate separate artifacts on Linux, macOS, and Windows.
Platform signing, notarization, and release attestations are separate release
requirements.

## Basic commands

```bash
# Generate from a prompt
zcoder -p "Write a Python function to reverse a string"

# Analyze a source file
zcoder -f mycode.py -p "Explain this and suggest improvements"

# Start the terminal interface
zcoder --tui

# Run local liveness checks
zcoder --health-check

# Inspect available commands
zcoder --help
```

The prompt, file, interactive, and route flows use the configured local model
server. Some optional legacy operations are still being migrated; their use
does not imply that every ZCoder feature is local-only.
