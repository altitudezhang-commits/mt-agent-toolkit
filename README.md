A modular CLI toolbox for babysitting a personal AI agent: self-healing health checks, quota radar, pluggable data sources.

# mt — Agent Toolkit

One CLI entry point (`mt`) plus lazily loaded subcommand modules. Pure Python standard library, zero third-party dependencies: a new module is one file under `mtcore/modules/` and one line in the registry, and it never slows down or breaks the existing modules.

## Modules

### `mt health` (included)

Unified health check with self-healing for the local services an agent depends on:

- **FreeLLMAPI** — authenticated liveness probe (the unified key is read at runtime from the router's own sqlite DB into memory only; it is never printed or logged). A `401`/no-data response means *degraded*, not dead — restarting cannot fix an application-layer problem, so it is reported, not restarted. Only a total no-response is judged **down**, which triggers the idempotent `start.sh`, a 5-second wait, and a re-probe with the same standard.
- **PerkRadar / n8n** — probe-only in this version (their restarts are owned by an external keepalive, to avoid two systems racing to restart the same service).

Exit code: `0` = everything healthy (including healed), `1` = something is still wrong.

Configuration is via environment variables: `MT_FREELLMAPI_HOME` (router checkout, default `~/freellmapi`), `MT_FREELLMAPI_URL`, `MT_PERKRADAR_URL`, `MT_N8N_URL`.

### Roadmap

- `mt quota` — one-screen view of upcoming free-tier expiries across services, non-zero exit when something expires within 48 hours.
- `mt x` — social data source status (credits/balance per provider) with config-only source switching.

## Usage

```bash
./mt health            # probe + heal
./mt health --no-heal  # probe only
```

## License

MIT — see `LICENSE`.
