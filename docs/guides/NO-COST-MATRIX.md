# Local Inference and Storage Matrix

The primary coding prompt path uses the local llama.cpp server. This matrix
describes that path and the local persistence choices; it does not claim that
every optional integration in the repository has completed migration.

## Local architecture

```text
ZCoder CLI / API
      |
      +---- local llama.cpp server ---- GGUF model
      |
      +---- SQLite (single-user default)
      |
      +---- PostgreSQL container zPostgreSQL (shared local service)
```

## Runtime and persistence

| Area | Local implementation | Notes |
|---|---|---|
| Inference | llama.cpp with GGUF | Loopback endpoint at `127.0.0.1:8080/v1` by default |
| Model selection | `ZCODER_MODEL` | Defaults to `zqwen2.5-coder-7b-instruct-q4_k_m` |
| Single-user persistence | SQLite | Default for the local installation |
| Shared PostgreSQL | Docker container `zPostgreSQL` | Applications use separate databases and roles |
| ZCoder PostgreSQL database | `zcoder_db` | Provisioned by `make postgres-setup` |
| Artifacts | Local filesystem | Subject to filesystem permissions and available disk space |
| Telemetry | Configured local collector or local storage | Configure endpoints and retention explicitly |

## Local model server

```bash
llama-server \
  --model /home/cvsz/zgpu/qwen-7b-q4km.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --ctx-size 4096
```

Set `ZCODER_MODEL` to a local request label when needed. The model file loaded
by the server determines the actual inference weights.

## Boundaries

- Local inference uses local compute and storage resources; it is not resource
  free.
- A missing model server is reported as an error. ZCoder does not fabricate a
  successful model response.
- Specialized features that still use legacy remote clients are not covered
  by this local matrix and must be migrated or disabled before a complete
  local-only release can be claimed.
- Never store database credentials in source control. Use per-application
  roles and databases on the shared PostgreSQL service.
