"""CLI del architect: `python -m chakravyuh.architect build|evolve`.

Construye (o evoluciona) el World y publica si pasa la validación de inertness; importa el
pack de cebo como escenario activo. El proveedor y los parámetros salen de la config (prefijo
CHAKRAVYUH_) y se pueden sobreescribir por flags.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from ..config import settings
from ..world import default_world_path
from .builder import build_world
from .providers import make_provider


def _provider(name_override: str | None, model_override: str | None):
    name = name_override or settings.architect_provider
    api_key = settings.architect_api_key or settings.ai_api_key
    model = model_override or settings.architect_model
    return make_provider(name, api_key=api_key, model=model, base_url=settings.architect_base_url)


def _add_common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--provider", help="stub | api | claude_cli (default: config)")
    sp.add_argument("--model", help="provider model (api/claude_cli)")
    sp.add_argument("--brand", default="", help="site brand/identity")
    sp.add_argument("--profile", default="", help="site profile (saas/corp/ecommerce/...)")
    sp.add_argument("--goal", default="", help="specific build goal")
    sp.add_argument("--portals", type=int, default=0, help="approximate number of portals (default: config)")
    sp.add_argument("--world-path", default="", help="World path (default: config/next to the DB)")
    sp.add_argument("--no-import-bait", action="store_true", help="do not import the bait pack")
    sp.add_argument("--json", action="store_true", help="JSON output")


def _format(report: dict) -> str:
    lines = []
    ok = report.get("ok")
    lines.append(("✓ " if ok else "✗ ") + ("published" if report.get("published") else "NOT published"))
    if report.get("error"):
        lines.append(f"  error: {report['error']}")
    for pr in report.get("problems", [])[:20]:
        lines.append(f"  - {pr}")
    if report.get("world_path"):
        lines.append(f"  world: {report['world_path']}  ({report.get('files')} files)")
    if report.get("bait"):
        b = report["bait"]
        lines.append(f"  bait: {'ok' if b.get('ok') else b.get('error')} "
                     f"(scenario #{b.get('scenario_id')}, {b.get('nodes')} nodes, active={b.get('active')})")
    pres = report.get("provider_result", {})
    lines.append(f"  provider: {pres.get('provider')} steps={pres.get('steps', '-')} ok={pres.get('ok')}")
    if report.get("note"):
        lines.append(f"  note: {report['note']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(prog="chakravyuh-architect", description="Chakravyuh World AI builder")
    sub = p.add_subparsers(dest="cmd", required=True)
    _add_common(sub.add_parser("build", help="build a new World"))
    _add_common(sub.add_parser("evolve", help="evolve the current World (rotate bait, add a portal)"))
    args = p.parse_args(argv)

    world_path = args.world_path or settings.world_path or default_world_path(settings.db_path)
    import_bait = not args.no_import_bait
    if import_bait:
        from ..db import init_db

        init_db()  # idempotente: asegura el esquema antes de importar el pack

    report = build_world(
        provider=_provider(args.provider, args.model),
        world_path=world_path,
        brand=args.brand or settings.architect_brand,
        profile=args.profile,
        goal=args.goal,
        portals=args.portals or settings.architect_portals,
        import_bait=import_bait,
        seed_from_current=(args.cmd == "evolve"),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _format(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
