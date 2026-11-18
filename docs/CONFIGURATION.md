# Configuration

All configuration is read from the environment with the `CHAKRAVYUH_` prefix (or from a
`.env` file in the working directory). Template: [`.env.example`](../.env.example).

## Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_DB_PATH` | `chakravyuh.db` | SQLite path. In Docker: `/app/data/chakravyuh.db`. |
| `CHAKRAVYUH_WEB_DIST` | *(auto)* | Path to the frontend build. Auto-detected when it sits next to the package (`web/dist`). |

## Network

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_HONEYPOT_PORT` | `8080` | Honeypot port (the maze served to agents). |
| `CHAKRAVYUH_DASHBOARD_PORT` | `5000` | Port for dashboard + API + WebSocket + ingestion. |
| `CHAKRAVYUH_PUBLIC_URL` | *(empty)* | Public URL of the server that remote sensors connect to. Required for sensor onboarding. |

## Content generation

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_SEED` | *(auto)* | Deployment seed. Empty = one is generated (anti-fingerprinting). |
| `CHAKRAVYUH_GENERATION_MODE` | `Template` | `Template` \| `Mimic` \| `Static`. |
| `CHAKRAVYUH_TARGET_URL` | *(empty)* | Real site to imitate (`Mimic` only). |
| `CHAKRAVYUH_SITE_PROFILE` | *(empty)* | Built-in profile (`saas`\|`corp`\|`ecommerce`\|`nonprofit`): realistic routes, lexicon and API collections without crawling. Empty = generic, derived from the seed. In `Mimic` mode, the crawl of `TARGET_URL` takes precedence. Generate more with `scripts/build_profile.py`. |
| `CHAKRAVYUH_REALISM_LEVEL` | `3` | 1 (light lure) .. 5 (dense lure). |
| `CHAKRAVYUH_VOCABULARY_THEME` | *(auto)* | `corporate` \| `devops` \| `saas` \| `ecommerce`. Empty = derived from the seed. |
| `CHAKRAVYUH_BRAND_NAME` | *(auto)* | Fictitious brand. Empty = derived from the seed. |
| `CHAKRAVYUH_TARPIT_DELAY_MS` | `0` | Fixed base delay per response (ms). Added on top of the adaptive tarpit. |
| `CHAKRAVYUH_ADAPTIVE_TARPIT` | `true` | Delay that grows with session intensity (coherent→lure). 0 at intensity 0 (human/unknown); only rises once an agent is confirmed. |
| `CHAKRAVYUH_TARPIT_MAX_MS` | `6000` | Maximum delay per response at intensity 3 (confirmed agent). |
| `CHAKRAVYUH_ALLOW_INFINITE_ON_CONFIRMED` | `false` | Opt-in for raw token burning: at maximum intensity the API goes back to paginating endlessly. It breaks the coherence invariant (it becomes fingerprintable again), which is why it is OFF by default. |
| `CHAKRAVYUH_SERVER_BANNER` | `nginx` | `Server` banner. `nginx` = derived from the seed. |
| `CHAKRAVYUH_TOKEN_DRAIN_ENABLED` | `true` | Enables the Token Drain maze (finite and coherent; **legacy**: effectively OFF when a World is active). |
| `CHAKRAVYUH_WORLD_ENABLED` | `true` | Serves the **World**: INERT multi-site static content (real files on disk; bytes only, never executes). The primary source; replaces the generated maze. |
| `CHAKRAVYUH_WORLD_PATH` | *(auto)* | Path of the World. Empty = `<DB directory>/world` (persistent volume). |
| `CHAKRAVYUH_WORLD_AUTOSEED` | `true` | If the World is empty, copies the packaged curated portal seed. |
| `CHAKRAVYUH_SCENARIOS_ENABLED` | `false` | Serves the active scenario (credential-reuse gate, resolved BEFORE the World). `false` = no active lure (World/maze only). `true` = active lure. Built-in packs: `realistic-ops` (recommended with World: **a single** leaked `.env.bak` → hidden ops console with mock data, no CTF look), `corp-breach`/`git-leak` (CTF-style chains). Activate it with `POST /api/scenarios/builtins/realistic-ops?activate=true`. |

### World: manifest and bulky content (genbig)

The World `manifest.json` mounts portals: `{"mounts": [{"prefix", "dir", "spa", "autoindex"}]}`.
- **`autoindex: true`** → a directory **without an `index.html`** serves a **server-style listing**
  (the "open directory" decoy) instead of a 404. Defaults to `false` (a directory without an index = 404).
- Static files **larger than 1 MiB are streamed** (real Content-Length/Range, never loaded into
  memory): you can serve heavy trees without exhausting the honeypot's RAM.

To fill a bulky tree with **REAL text** (a finite token burn, without the telltale traces of
generated/templated content) use [`scripts/genbig.py`](../scripts/genbig.py):

```bash
# /data with 50 files of 10 MiB (public-domain text, cached in ~/.cache/genbig)
python3 scripts/genbig.py <world>/sites/data --files 50 --size 10M --lang en
# numeric subdirs: /files/2023 /files/2024 /files/2025
python3 scripts/genbig.py <world>/sites/files --files 60 --size 10M \
    --subdirs 3 --subdir-prefix "" --subdir-width 4 --subdir-start 2023
```

Then add the mount with `autoindex` to the World `manifest.json` and restart the honeypot:

```json
{ "prefix": "/data", "dir": "sites/data", "autoindex": true }
```

genbig output is NOT committed: it lives in the World volume (`<DB directory>/world`).

## Detection and alerts

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_ALERT_SCORE_THRESHOLD` | `0.5` | Minimum score to raise an alert. |
| `CHAKRAVYUH_ALERT_MIN_REQUESTS` | `5` | Minimum requests in the session to raise an alert. |

## Blocking and notifications

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_ENFORCE_BLOCK` | `true` | The honeypot responds 403 to blocked IPs. |
| `CHAKRAVYUH_AUTO_BLOCK_SCORE` | `0.0` | Score-based auto-block (0 = disabled; `credential_reuse` always blocks). |
| `CHAKRAVYUH_WEBHOOK_URL` | *(empty)* | Notification webhook (HMAC-signed `X-Chakravyuh-Signature`). |
| `CHAKRAVYUH_WEBHOOK_SECRET` | *(empty)* | Secret used to sign the webhook. |
| `CHAKRAVYUH_ENABLE_IPTABLES` | `false` | Optional OS-level blocking (OFF by default). |

## Dashboard authentication (single admin)

The dashboard/API (`/api/*`) sits behind a signed-cookie session. The sensor
channel (`/ingest/*`, `/control`, `/s/*`, `/download/*`, `/healthz`) is NOT affected:
it keeps its own HMAC authentication.

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_ADMIN_USER` | `admin` | Admin user created on first startup. |
| `CHAKRAVYUH_ADMIN_PASSWORD` | *(empty)* | Admin password. Empty = one is generated and printed to the log **once**. |
| `CHAKRAVYUH_SESSION_SECRET` | *(empty)* | Cookie signing secret. Empty = generated and persisted next to the DB (stable per deployment). |
| `CHAKRAVYUH_SESSION_MAX_AGE` | `86400` | Session lifetime in seconds. |
| `CHAKRAVYUH_COOKIE_SECURE` | `false` | `true` behind TLS (admin subdomain); `false` on local/http tunnel. |

Exposure: the dashboard is published on its own TLS subdomain (e.g.
`chakravyuh-admin.…`) behind the shared Caddy — see [`deploy/caddy-admin.snippet`](../deploy/caddy-admin.snippet) —
and also remains reachable via SSH tunnel. A surface separate from the public honeypot.

## AI confirmation (optional)

The system works without this module (heuristic mode).

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_AI_ENABLED` | `false` | Enables gray-zone confirmation. |
| `CHAKRAVYUH_AI_PROVIDER` | `heuristic` | `heuristic` \| `openai` (OpenAI-compatible endpoint). |
| `CHAKRAVYUH_AI_BASE_URL` | *(empty)* | E.g. `https://openrouter.ai/api/v1`. |
| `CHAKRAVYUH_AI_API_KEY` | *(empty)* | Provider API key. |
| `CHAKRAVYUH_AI_MODEL` | *(empty)* | E.g. `anthropic/claude-haiku-5.5`. |
| `CHAKRAVYUH_AI_GRAY_ZONE_LOW` / `_HIGH` | `0.35` / `0.65` | Score range that triggers confirmation. |
| `CHAKRAVYUH_AI_CONFIRM_THRESHOLD` | `0.7` | Minimum confidence to settle the verdict. |

## Architect (AI World builder)

AI agent that builds/evolves the World's inert content + the lure. Invoked on demand
(`python -m chakravyuh.architect build|evolve`), not per request. Guide:
[`docs/ARCHITECT.md`](ARCHITECT.md).

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAKRAVYUH_ARCHITECT_PROVIDER` | `stub` | `stub` (deterministic, no AI) \| `api` (Anthropic tool-use) \| `claude_cli` (subscription-backed CLI). |
| `CHAKRAVYUH_ARCHITECT_MODEL` | *(empty)* | Provider model (e.g. `claude-sonnet-4-5` for `api`; CLI alias). |
| `CHAKRAVYUH_ARCHITECT_API_KEY` | *(empty)* | Key for `provider=api`. If empty, falls back to `CHAKRAVYUH_AI_API_KEY`. |
| `CHAKRAVYUH_ARCHITECT_BASE_URL` | `https://api.anthropic.com` | Messages API endpoint (`api`). |
| `CHAKRAVYUH_ARCHITECT_PORTALS` | `4` | Approximate number of portals to generate. |
| `CHAKRAVYUH_ARCHITECT_BRAND` | *(empty)* | Site brand/identity. Empty = the agent derives it from the brief. |

For `claude_cli`, authentication comes from the CLI itself or from `CLAUDE_CODE_OAUTH_TOKEN` (from
`claude setup-token`), inherited by the subprocess. The provider is restricted to `Read,Write,Edit`
with no bash and no network.

## Remote sensors (on the client's server)

These variables are consumed by the **agent** or the **agentless shipper**, not by the central server:
`CHAKRAVYUH_SERVER`, `CHAKRAVYUH_KEY_ID`, `CHAKRAVYUH_SECRET`, and (agent) `CHAKRAVYUH_AGENT_PORT`,
`CHAKRAVYUH_CONTROL_INTERVAL`, `CHAKRAVYUH_BEACON_JITTER`; (shipper) `CHAKRAVYUH_LOG`, `CHAKRAVYUH_BASE_PATH`,
`CHAKRAVYUH_FORMAT`, `CHAKRAVYUH_STATE`, `CHAKRAVYUH_DRY_RUN`. Details in
[`chakravyuh/agent/BUILD.md`](../chakravyuh/agent/BUILD.md) and [`chakravyuh/clients/README.md`](../chakravyuh/clients/README.md).
