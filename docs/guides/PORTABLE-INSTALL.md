# Portable Installation and Standalone Builds

## Requirements

- Python 3.12 or newer.
- A supported operating system and architecture. PyInstaller artifacts are platform-specific; build on each target OS rather than cross-compiling.
- Network access for installing dependencies. The installer does not silently enable paid provider routes.

## Install into a selected directory

### Linux / macOS

```bash
bash scripts/setup.sh --install-dir "$HOME/Apps/zcoder"
"$HOME/Apps/zcoder/bin/zcoder" --version
```

The explicit path is resolved relative to the current working directory when it is not absolute. Without `--install-dir`, the installer preserves the existing `ZCODER_VENV` behavior and defaults to the repository's `venv` directory.

### Windows

```bat
scripts\setup.bat --install-dir "D:\Apps\ZCoder"
"D:\Apps\ZCoder\Scripts\zcoder.exe" --version
```

The selected directory contains a Python virtual environment and the installed package. Custom-path installs are non-editable so the installed command does not depend on the checkout remaining in place.

## Build a standalone executable

### Linux / macOS

```bash
bash scripts/build.sh \
  --dist-dir "$HOME/Downloads/zcoder-release" \
  --work-dir "$HOME/zcoder-build-work" \
  --build-venv "$HOME/zcoder-build-venv"
```

The result is `zcoder` under the selected distribution directory.

### Windows

```bat
scripts\build.bat --dist-dir "D:\Releases\ZCoder" --work-dir "D:\Build\ZCoder" --build-venv "D:\Build\ZCoderVenv"
```

The result is `zcoder.exe` under the selected distribution directory.

### Safe output behavior

- Existing output files are preserved unless `--force` is explicitly supplied.
- The installer refuses work, output, and build-venv paths that overlap, preventing PyInstaller work files from colliding with the executable or virtual environment.
- On POSIX systems, `.env` is restricted to mode `0600`. A symlink or non-file `.env` is rejected rather than following a path that may point outside the checkout.
- Intermediate work files, build dependencies, and final output can be placed in separate user-selected directories.
- The standalone binary is OS/architecture-specific and must be tested on its target platform before release.

## Environment-variable overrides

- `ZCODER_VENV`: default installation virtual environment.
- `ZCODER_DIST_DIR`: standalone output directory.
- `ZCODER_WORK_DIR`: PyInstaller intermediate work directory.
- `ZCODER_BUILD_VENV`: virtual environment used for packaging.

Command-line options take precedence over these environment variables.

## Verification

Run the installer regression tests and the full CI suite. A successful PyInstaller invocation is not, by itself, proof that every provider, optional native dependency, or target OS works in production.
