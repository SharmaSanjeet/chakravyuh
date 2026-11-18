# Architect — AI World builder

The **architect** is an AI agent that **builds and evolves the content of the
[World](#what-is-the-world)**: a realistic site made of several static, inert portals +
a **lure** placed on the attacker's hunting path. It is invoked **on demand** (not per
request): it provisions or refreshes the content and then stops.

> Do not confuse it with `chakravyuh/agent/`, which is the **remote sensor** (edge). The architect
> (`chakravyuh/architect/`) **produces files**; the sensor reports hits.

## Security principle (non-negotiable)

Chakravyuh **only serves static bytes and never executes** portal content. The
architect therefore produces **exclusively inert static files** (HTML/CSS/JS/
JSON/SVG/…), and this is **mechanically enforced**, not trusted to the prompt:

1. **Validation on write** (`validate.py`) — every file goes through: safe path (no
   traversal/absolute paths, extension allowlist), **no server-side code** (`<?php`,
   `<% %>`, `{% %}`, shebangs), **no external loads/callbacks** (everything *same-origin*: the
   “logins” post to the Chakravyuh gate, not to a backend or an external domain), and size limits.
2. **Final gate** — before publishing, the **entire tree is re-validated** on disk. If anything
   fails, **nothing is published** and the live World stays intact.
3. **Atomic publication** — the build is assembled in a *staging* area and swapped in at once.

The content may include **fabricated** secrets/credentials (they are the lure); the
“one live credential” invariant is enforced by `plant_bait`, not by the inertness validator.

## What is the World

A tree of real files + a `manifest.json` that mounts one or more **portals** under
different URL prefixes (like a server hosting several websites):

```
world/
  manifest.json                 # {"mounts":[{"prefix":"/docs","dir":"sites/docs","spa":false}, ...]}
  sites/console/index.html      # portals: static + mock data (api/*.json)
  sites/docs/index.html
  sites/status/summary.json
```

Health/status endpoints can use dynamic tokens that **Chakravyuh fills in when serving**
(so they do not look “frozen”): `{{chakravyuh.now_iso}}`, `{{chakravyuh.uptime_seconds}}`,
`{{chakravyuh.minutes_ago}}`. See [`CHAKRAVYUH_WORLD_*`](CONFIGURATION.md#content-generation).

## Hunting-path doctrine (the lure)

A goal-driven pentest agent (Strix/PentAGI style) enumerates, always looking for the same things:
an **environment backup with credentials** (`/.env`, `/.env.bak`, `/env.bak`, `/api/env.bak`…),
an **admin/ops console** (`/ops`, `/admin`, `/internal/ops`…) and a **login** to post to
(`/api/login`, `/auth/login`…). The architect plants the lure **right there** with `plant_bait`:

- **a single live credential** (a honeytoken);
- the backup (leak) is leaked on those routes and includes the `{{cred:KEY}}` placeholder and the gate URL;
- the console (gate) demands that token (401 Bearer without it; 200 with it);
- `robots.txt` reveals the routes as a decoy.

When the attacker reuses the token against the gate, Chakravyuh fires **`credential_reuse`** and
**blocks** them. The lure is imported as the active scenario (see [scenarios](CONFIGURATION.md)).

## Providers

Configurable via `CHAKRAVYUH_ARCHITECT_PROVIDER` (or `--provider`):

| Provider | AI | Notes |
|-----------|----|-------|
| `stub` | no | Deterministic, zero cost. Builds a valid World + lure. Ideal for tests and as the default build without AI. |
| `api` | Anthropic Messages API | *Tool-use* loop with **our tools** (`write_file`, `set_manifest`, `plant_bait`…). **It has no shell**: the model can only call those sandboxed tools → it cannot pivot. Requires `CHAKRAVYUH_ARCHITECT_API_KEY`. |
| `claude_cli` | `claude` CLI (subscription) | Sandboxed `claude -p` subprocess (`Read,Write,Edit`, no bash/network, `--add-dir` to the staging area). Builds via files + a `_architect_bait.json` that we ingest via `plant_bait`. Requires CLI auth or `CLAUDE_CODE_OAUTH_TOKEN`. |

The `api` provider's tools **never throw**: they return `{"ok": false, "reasons": [...]}`
so the agent can **self-correct**. Every write is validated; the sandbox caps the number of
files and the number of bytes.

## Usage (CLI)

```bash
# New build (provider from config, or --provider)
python -m chakravyuh.architect build --brand "Auralis" --profile saas

# Evolve the current World (rotates the lure, refreshes mock data, adds/varies a portal)
python -m chakravyuh.architect evolve

# Options: --provider stub|api|claude_cli  --model  --brand  --profile
#          --goal  --portals N  --world-path PATH  --no-import-bait  --json
```

The build publishes the World (if it passes validation) and **imports the lure pack** as the active
scenario. **Restart/reload the honeypot process** so it serves the new World (the World is
loaded at startup).

### `api` provider (Anthropic)

```bash
export CHAKRAVYUH_ARCHITECT_PROVIDER=api
export CHAKRAVYUH_ARCHITECT_API_KEY=sk-ant-...
export CHAKRAVYUH_ARCHITECT_MODEL=claude-sonnet-4-5   # optional
python -m chakravyuh.architect build --brand "Auralis"
```

### `claude_cli` provider (subscription)

Generate a long-lived token with your subscription and pass it via the environment:

```bash
claude setup-token            # interactive flow (browser); prints a sk-ant-oat...
export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat...
python -m chakravyuh.architect build --provider claude_cli --brand "Auralis" --profile saas
```

The CLI writes the World files + `manifest.json` + a `_architect_bait.json` (a build
artifact with the lure spec; **not** published: it is ingested via `plant_bait` and deleted).

> **Isolation (important).** Run any AI build in a **clean** environment (no SSH keys
> or real `.env` files in the reachable `$HOME`/cwd). The `api` provider has no shell; the
> `claude_cli` is restricted to `Read,Write,Edit` with no bash/network, but environment isolation is the
> main defense.

## Verification (what a correct build checks)

- The published tree passes `validate_tree` (clean inertness) and serves real bytes at every portal;
  anything missing → a **real 404**.
- The lure works end-to-end: `GET /ops` without a token → **401**; `GET /.env` leaks the token →
  `GET /ops` with `Authorization: Bearer <token>` → **200** + `credential_reuse`.
- Zero external references; health/status endpoints with `{{chakravyuh.*}}`.

## Deployment (VPS)

1. Run the build on the server (or upload it) pointing `CHAKRAVYUH_WORLD_PATH` at the persistent volume.
2. Restart the honeypot container to reload the World.
3. The lure pack has already been imported and is active in the DB.

## Files

```
chakravyuh/architect/
  validate.py   inertness safety net (path + content + manifest + tree)
  tools.py      BuildSandbox: bulletproof tools (write_file/set_manifest/plant_bait…)
  providers.py  stub | api (Anthropic tool-use) | claude_cli + safe dispatch
  prompt.py     prompt engineering (system + brief) with the hunting-path doctrine
  builder.py    orchestrates, re-validates the tree and publishes atomically + imports the lure
  main.py       CLI: python -m chakravyuh.architect build|evolve
```
