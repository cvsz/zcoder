# Troubleshooting Guide

This guide covers common issues when using ZCoder and how to resolve them.

## 1. ZCoder won't start

### Symptom: `zcoder: command not found`

**Cause:** ZCoder is not installed or not on your PATH.

**Solution:**

```bash
# Check if zcoder is installed
which zcoder || pip show zcoder

# Install from source
pip install -e .

# Or run directly from source
python -m zcoder.main -p "test"
```

### Symptom: `ModuleNotFoundError: No module named 'zcoder'`

**Cause:** The zcoder package is not installed or the virtual environment is not activated.

**Solution:**

```bash
# Activate the virtual environment
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Or install globally
pip install -e .
```

## 2. Local inference issues

### Symptom: `Connection refused` or `ERR_CONNECTION_REFUSED`

**Cause:** The Ollama server is not running or not on the expected port (11434).

**Solution:**

```bash
# Check if Ollama is running
curl -s http://127.0.0.1:11434/api/version

# Start Ollama
ollama serve

# Check ZCODER_BASE_URL
echo $ZCODER_BASE_URL
```

### Symptom: Model not found or model load fails

**Cause:** The GGUF model file doesn't exist or is not accessible.

**Solution:**

```bash
# Check if the model file exists
ls -la /path/to/model.gguf

# Check ZCODER_MODEL
echo $ZCODER_MODEL

# Check ZCODER_MODELS_DIR
echo $ZCODER_MODELS_DIR
```

### Symptom: `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING`

**Cause:** Node.js version incompatibility with pnpm/corepack.

**Solution:** Node.js >= 24.9.0 is required for pnpm. Use Node.js 24.9+ or install dependencies manually.

## 3. Docker issues

### Symptom: `docker compose up` fails

**Cause:** Docker is not running or the image is not built.

**Solution:**

```bash
# Check Docker is running
docker info

# Build the image
docker compose build zcoder

# Check logs
docker compose logs zcoder
docker compose logs ollama
```

### Symptom: Model file not found in container

**Cause:** The `ZCODER_MODELS_DIR` points to a directory that doesn't exist or doesn't contain the model.

**Solution:**

```bash
# Check if the model file exists on the host
ls -la /zdata/models/

# Update .env with the correct path
ZCODER_MODELS_DIR=/correct/path/to/models
```

## 4. Database issues

### Symptom: PostgreSQL connection fails

**Cause:** PostgreSQL container is not running or credentials are incorrect.

**Solution:**

```bash
# Check PostgreSQL status
make postgres-status

# Start PostgreSQL
make postgres-setup

# Check connection
docker exec -it zpostgresql psql -U zcoder -d zcoder_db -c "SELECT 1"
```

### Symptom: Redis connection fails

**Cause:** Redis container is not running.

**Solution:**

```bash
# Check Redis status
docker exec -it zredis redis-cli ping

# Start Redis
docker compose up -d zredis
```

## 5. Session issues

### Symptom: Sessions not persisting

**Cause:** Session store directory is not writable or doesn't exist.

**Solution:**

```bash
# Check session directory
ls -la ~/.zcoder/sessions/

# Create if missing
mkdir -p ~/.zcoder/sessions
```

### Symptom: Session events missing

**Cause:** Session events are logged but not projected correctly.

**Solution:** Check that session events are being logged with the correct format. Session events use JSON with `kind`, `data`, `eventId`, and `timestamp` fields.

## 6. Authentication and credentials

### Symptom: API key errors

**Cause:** ZCoder uses local inference by default and does not require API keys. If you're seeing API key errors, you may be using a remote provider.

**Solution:**

```bash
# Use local inference (default)
unset ZCODER_PROVIDER
unset ANTHROPIC_API_KEY

# Or enable local-only mode
export ZCODER_LOCAL_MODE=1
```

### Symptom: Credential resolution fails

**Cause:** The credential reference cannot be resolved.

**Solution:** Check that the environment variable or secret file exists and is accessible.

```bash
# Check if the credential env var is set
echo $MY_API_KEY

# Or check the secrets file
cat ~/.config/zcoder/postgresql.password
```

## 7. Performance issues

### Symptom: Slow responses

**Cause:** The model may be too large for your hardware, or the context window is too large.

**Solution:**

```bash
# Use a smaller/faster model
export ZCODER_MODEL=zcoder-flash

# Reduce context window
export ZCODER_CTX_SIZE=4096

# Enable PostgreSQL for session persistence
export ZCODER_POSTGRES_HOST=zpostgresql
```

## 8. Build and installation issues

### Symptom: `pip install -e .` fails

**Cause:** Missing build dependencies or Python version incompatibility.

**Solution:**

```bash
# Check Python version (>=3.12 required)
python --version

# Install build dependencies
pip install -e ".[dev]"

# Or use the setup script
./setup.sh
```

### Symptom: Build fails on Windows

**Cause:** Windows-specific build issues.

**Solution:** Use `setup.bat` or `build.bat` instead of shell scripts.

## 9. Getting help

If this guide doesn't resolve your issue:

1. Run `zcoder --health-check` to diagnose local issues
2. Check the logs: `docker compose logs` (for Docker) or `~/.zcoder/logs/` (for local)
3. Search existing issues: https://github.com/cvsz/zcoder/issues
4. Create a new issue with:
   - Your OS and version
   - ZCoder version (`zcoder --version`)
   - The command you ran
   - The full error message
   - Steps to reproduce

## Quick diagnosis commands

```bash
# Health check
zcoder --health-check

# Version info
zcoder --version

# Check environment
echo "ZCODER_BASE_URL=$ZCODER_BASE_URL"
echo "ZCODER_MODEL=$ZCODER_MODEL"
echo "ZCODER_LOCAL_MODE=$ZCODER_LOCAL_MODE"

# Test model connection
curl -s http://127.0.0.1:11434/api/tags

# Check Docker services
docker compose ps

# Check PostgreSQL
make postgres-status
```