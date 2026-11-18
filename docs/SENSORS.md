# Sensors: deploying Chakravyuh on remote servers

A **sensor** is a point where Chakravyuh's lure is served. There are three types:

| Type | What it is | Capabilities | Host footprint |
|------|--------|-------------|-------------------|
| `local` | Chakravyuh's own honeypot (:8080) | Everything | — |
| `agent` | Self-contained binary on the remote server | Infinite maze + tar-pit + **credential/CTF gates** + telemetry | Process + port + outbound beacon |
| `agentless` | Static ZIP + cron that ships logs | **Behavioral detection** (no live gates) | Files only + a sporadic cron (maximum stealth) |

Rule of thumb: use **agent** when you need CTF/credential reuse; use **agentless** when you cannot (or do not want to) install anything, or when stealth comes first.

## Registering a sensor (1 command)

1. Dashboard → **Sensors → Add sensor**. The wizard recommends the mode with 3 questions and creates the sensor.
2. Copy the **one-time command** shown (it is displayed **only once** and carries the embedded key):

   ```sh
   curl -fsSL https://YOUR-CHAKRAVYUH/s/<token> | sh
   ```

   Prefer to review it before running? Use the **inspect** option: download the script, verify its `sha256`, and read it before running it.
3. The wizard stays at *"waiting for first check-in…"* and switches to **✓ connected** as soon as the sensor checks in (over WebSocket).

### Agent mode

The installer runs **preflight** checks (connectivity to Chakravyuh and clock), downloads the binary for your `os/arch`, writes the config with the key (permissions `600`) and installs a service (`systemd` on Linux, a Windows service on Windows). From then on, the agent serves the lure and sends signed telemetry.

> Agent binaries are produced by CI (`release.yml`, PyInstaller) and attached to the
> GitHub Release; the GHCR Docker image already embeds them (linux amd64/arm64), so
> `GET /download/agent/{os-arch}` works with no extra steps. Manual build: [`chakravyuh/agent/BUILD.md`](../chakravyuh/agent/BUILD.md).

### Agentless mode

1. Download the **shipping script** and the **bundles** (several ZIPs, each with a different structure/count — no patterns).
2. Unpack the bundles wherever you want to serve the lure (e.g. under `/lure`).
3. Apply the **safe-serving** snippet (included in each bundle, for nginx/apache/caddy) that serves the content as **plain text, no execution**.
4. Add the **scheduled task** the wizard gives you (it reads only the lines under the lure prefix and ships them signed):

   ```
   */5 * * * * CHAKRAVYUH_SERVER=... CHAKRAVYUH_KEY_ID=... CHAKRAVYUH_SECRET=... /opt/chakravyuh/chakravyuh-ship.sh
   ```

   Run a **dry run** (`CHAKRAVYUH_DRY_RUN=1`) to see what would be shipped before activating it.

## Security

- Each sensor has its own **symmetric key**; HMAC signing in both directions (sensor shipments **and** control responses), so a MITM cannot forge either a shipment or a "disable". Timestamp-based anti-replay window.
- **Least-privilege** key (ingestion + control of its own sensor only), **revocable/rotatable** in one click from the dashboard. The key lives on a host that can be attacked: by design it is low-value.
- All ingestion is treated as **hostile**: validation, rate-limiting, dedup and prefix filtering. The agentless mode ships only lure lines (no real user traffic).

## Operation

- **Status**: the Sensors page shows online/offline (by last check-in), sessions and alerts per sensor, version and last shipment. A sensor that goes silent may mean it was found: Chakravyuh flags it.
- **Toggle on/off and rotate the seed**: done live; the agent and the cron poll `/control` and apply it.
- **Decommission**: revokes the key and retires the sensor. For agentless, delete the lure with the `uninstall.sh` included in the bundle (it uses the `MANIFEST.json`).

## Limitations of this release

- Agentless mode detects **behavior**, not credential reuse against live gates (that requires the agent).
- Remote servers must be able to **reach** the Chakravyuh server (outbound HTTPS). The installer validates connectivity; for environments with closed egress, a store-and-forward relay will arrive in a future release.
