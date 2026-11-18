"""Generación server-side de scripts e instrucciones de instalación.

Todo lo que el usuario pega en su servidor sale de aquí, con la clave y la URL ya
embebidas. El onboarding es: crear sensor → copiar un comando → ✓ conectado.
"""

from __future__ import annotations

from .config import settings


def server_url() -> str:
    return (settings.public_url or f"http://localhost:{settings.dashboard_port}").rstrip("/")


def one_command(token: str) -> str:
    """Comando principal (curl | sh) para el asistente."""
    return f"curl -fsSL {server_url()}/s/{token} | sh"


def inspect_command(token: str) -> str:
    """Alternativa 'inspeccionar primero': descargar + ver checksum antes de ejecutar."""
    url = f"{server_url()}/s/{token}"
    return (
        f"curl -fsSL {url} -o chakravyuh-install.sh && sha256sum chakravyuh-install.sh "
        "&& less chakravyuh-install.sh && sh chakravyuh-install.sh"
    )


def agent_install_script(key_id: str, secret: str) -> str:
    """Script POSIX que instala el agente como binario autocontenido + servicio."""
    srv = server_url()
    return f"""#!/bin/sh
set -eu
# Chakravyuh agent installer. Review this script before running it.
SERVER="{srv}"
KEY_ID="{key_id}"
SECRET="{secret}"

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "unsupported architecture: $ARCH"; exit 1 ;;
esac

DIR="${{CHAKRAVYUH_DIR:-/opt/chakravyuh}}"
mkdir -p "$DIR"
echo "[chakravyuh] preflight: testing connectivity to $SERVER ..."
if ! curl -fsS -o /dev/null "$SERVER/healthz"; then
  echo "[chakravyuh] ERROR: $SERVER is unreachable. Open HTTPS egress to that host."; exit 1
fi
echo "[chakravyuh] downloading agent ($OS/$ARCH) ..."
curl -fsSL "$SERVER/download/agent/$OS-$ARCH" -o "$DIR/chakravyuh-agent"
chmod +x "$DIR/chakravyuh-agent"
cat > "$DIR/agent.env" <<EOF
CHAKRAVYUH_SERVER=$SERVER
CHAKRAVYUH_KEY_ID=$KEY_ID
CHAKRAVYUH_SECRET=$SECRET
EOF
chmod 600 "$DIR/agent.env"

if command -v systemctl >/dev/null 2>&1; then
  cat > /etc/systemd/system/chakravyuh-agent.service <<EOF
[Unit]
Description=Chakravyuh Agent
After=network.target
[Service]
EnvironmentFile=$DIR/agent.env
ExecStart=$DIR/chakravyuh-agent
Restart=always
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload && systemctl enable --now chakravyuh-agent
  echo "[chakravyuh] agent installed and started (systemd service)."
else
  echo "[chakravyuh] no systemd; start it manually: env \\$(cat $DIR/agent.env) $DIR/chakravyuh-agent &"
fi
"""


def agentless_steps(sensor_id: int, key_id: str, secret: str, base_path: str, bundle_count: int) -> dict:
    """Pasos y snippets para el modo sin instalación (ZIP + cron)."""
    srv = server_url()
    cron = (
        f"*/5 * * * * CHAKRAVYUH_SERVER={srv} CHAKRAVYUH_KEY_ID={key_id} CHAKRAVYUH_SECRET={secret} "
        f"/opt/chakravyuh/chakravyuh-ship.sh >/dev/null 2>&1"
    )
    return {
        "steps": [
            f"Download the shipper script: curl -fsSL {srv}/download/shipper/{sensor_id} "
            "-o /opt/chakravyuh/chakravyuh-ship.sh && chmod +x /opt/chakravyuh/chakravyuh-ship.sh",
            f"Download and unzip the {bundle_count} bundles wherever you want to serve the lure "
            f"(under {base_path}). Links are on the sensor tab.",
            "Apply the safe-serving config (plain text, no execution) we provide per web server type.",
            "Add the scheduled cron job below to ship the lure logs.",
        ],
        "cron": cron,
        "shipper_url": f"{srv}/download/shipper/{sensor_id}",
        "note": "The script only ships log lines matching the lure prefix; do a dry run first.",
    }
