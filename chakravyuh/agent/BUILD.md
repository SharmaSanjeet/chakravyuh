# Packaging the Chakravyuh remote agent

The agent (`chakravyuh.agent`) is distributed as a **self-contained binary** (PyInstaller
`--onefile`) so a client can run it without installing Python or any dependencies. It does
not need the DB, FastAPI, or pydantic-settings: only stdlib + `httpx` + the pure modules
`chakravyuh.maze`, `chakravyuh.scenarios` and `chakravyuh.security`.

## Entry point / running

```bash
python -m chakravyuh.agent        # from the repo (development)
./chakravyuh-agent-linux-amd64    # packaged binary
```

Environment variables:

| Variable                  | Default | Description                                              |
|---------------------------|---------|----------------------------------------------------------|
| `CHAKRAVYUH_SERVER`           | —       | Central server URL (required)                            |
| `CHAKRAVYUH_KEY_ID`           | —       | Sensor key id (required)                                 |
| `CHAKRAVYUH_SECRET`           | —       | Sensor HMAC secret (required)                            |
| `CHAKRAVYUH_AGENT_PORT`       | `8080`  | Local honeypot port                                      |
| `CHAKRAVYUH_CONTROL_INTERVAL` | `30`    | Seconds between control beacons / event submissions      |
| `CHAKRAVYUH_BEACON_JITTER`    | `0.3`   | Symmetric jitter (±fraction) over the interval           |

## Build dependency

```bash
.venv/bin/pip install pyinstaller
```

> Note: `chakravyuh.scenarios` imports SQLAlchemy at module level (it shares dataclasses with
> the server ORM). PyInstaller detects and bundles it; the agent does **not** use it at
> runtime. To slim down the binary you can exclude modules it never touches (see `--exclude-module`).

## Building per platform

PyInstaller does **not cross-compile**: you must build on (or emulate) each OS/arch.
The output name must be `chakravyuh-agent-<os>-<arch>` and be copied to
`chakravyuh/agent/dist/` — the server serves them from there at `GET /download/agent/{os-arch}`
(see `chakravyuh/api/__init__.py::download_agent`).

Common options (include the forge template DLL and trim weight):

```
COMMON="--onefile --name chakravyuh-agent \
  --add-data chakravyuh/assets/portal_template.dll:chakravyuh/assets \
  --hidden-import httpx \
  --exclude-module fastapi --exclude-module uvicorn \
  --exclude-module pydantic --exclude-module pydantic_settings \
  chakravyuh/agent/__main__.py"
```

(On Windows, the `--add-data` separator is `;` instead of `:`. If the template DLL is
missing, the forge degrades to a decoy PE and the build still works — omit the `--add-data`.)

### linux/amd64

```bash
# On an x86_64 Linux machine/container:
pyinstaller $COMMON
mv dist/chakravyuh-agent chakravyuh/agent/dist/chakravyuh-agent-linux-amd64
```

### linux/arm64

```bash
# On an aarch64 Linux machine/container (or QEMU: docker run --platform linux/arm64 ...):
pyinstaller $COMMON
mv dist/chakravyuh-agent chakravyuh/agent/dist/chakravyuh-agent-linux-arm64
```

Example with Docker + buildx for arm64:

```bash
docker run --rm --platform linux/arm64 -v "$PWD":/src -w /src python:3.11-slim bash -c "
  pip install -e . pyinstaller &&
  pyinstaller $COMMON &&
  cp dist/chakravyuh-agent /src/chakravyuh/agent/dist/chakravyuh-agent-linux-arm64"
```

### windows/amd64

```powershell
# On Windows x64 (PowerShell). Note the `;` in --add-data:
pyinstaller --onefile --name chakravyuh-agent `
  --add-data "chakravyuh/assets/portal_template.dll;chakravyuh/assets" `
  --hidden-import httpx `
  --exclude-module fastapi --exclude-module uvicorn `
  --exclude-module pydantic --exclude-module pydantic_settings `
  chakravyuh/agent/__main__.py
move dist\chakravyuh-agent.exe chakravyuh\agent\dist\chakravyuh-agent-windows-amd64
```

## Expected output

```
chakravyuh/agent/dist/
  chakravyuh-agent-linux-amd64
  chakravyuh-agent-linux-arm64
  chakravyuh-agent-windows-amd64     # (the .exe is renamed without the extension)
```

The server maps `GET /download/agent/{os-arch}` → `chakravyuh/agent/dist/chakravyuh-agent-<os-arch>`
and serves it as `filename="chakravyuh-agent"`. If the binary is missing, it responds 404
("build pending"), so these artifacts must be generated and committed (or uploaded to
the CI artifact store) before downloads are published.

## Quick verification

```bash
CHAKRAVYUH_SERVER=http://localhost:5000 CHAKRAVYUH_KEY_ID=ck_x CHAKRAVYUH_SECRET=s \
  ./chakravyuh-agent-linux-amd64   # must preflight /healthz and open port 8080
```
