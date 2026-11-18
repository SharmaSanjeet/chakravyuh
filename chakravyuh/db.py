"""Capa de datos: engine SQLite + sesiones + inicialización/seed.

Síncrono a propósito (SQLite). Los endpoints `def` de FastAPI corren en su
threadpool, así que cada petición usa su propia `Session`. El HTTP saliente
(mimic, LLM, webhooks) sí es async y vive en otros módulos.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base, DetectionRule, HoneypotConfig, Sensor

_engine = create_engine(
    f"sqlite:///{os.path.abspath(settings.db_path)}",
    future=True,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=_engine, class_=Session, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """Dependencia FastAPI: cede una Session y la cierra al terminar."""
    with SessionLocal() as s:
        yield s


# 14 reglas conductuales/CTF (las 4 fuertes se alimentan del motor de escenarios).
_SEED_RULES = [
    (1, "Moderate timing", "Inter-request intervals 2-30s; the LLM pauses while reasoning.", 0.15, "cadence_check"),
    (2, "Predictable sequence", "Sequential access to every file (curl→file→exec).", 0.25, "serial_fetch"),
    (3, "Bulk download", "Downloads EVERY listed file without discriminating.", 0.15, "mass_pull"),
    (4, "Literal README", "Executes the README commands verbatim, in order.", 0.20, "bait_reading"),
    (5, "JS deobfuscation", "Accesses endpoints only visible after deobfuscating JS.", 0.10, "script_unwrap"),
    (6, "User-Agent / headers", "Known crawler/AI-client User-Agents.", 0.05, "client_signature"),
    (
        7,
        "Breadcrumb following",
        "Follows the generated link chain deeper and deeper.",
        0.10,
        "trail_following",
    ),
    (8, "Deep descent", "Goes 5+ levels down following configs/.env (not human).", 0.15, "deep_descent"),
    (
        9,
        "Wide fan-out",
        "Follows nearly every link on each page (~total coverage).",
        0.15,
        "wide_fanout",
    ),
    (10, "No asset rendering", "Never requests CSS/JS/img/favicon: there is no browser.", 0.10, "no_asset_render"),
    (
        11,
        "Credential reuse",
        "Presented a honeytoken planted at a gate: near certainty.",
        0.35,
        "credential_reuse",
    ),
    (12, "Hidden path access", "Accessed an unlinked route (hints/fuzzing).", 0.20, "hidden_path_access"),
    (
        13,
        "Decompile follow-up",
        "Downloaded a binary and followed a route embedded in it.",
        0.20,
        "binary_decompile_followup",
    ),
    (14, "Auth brute force", "Multiple failed attempts against a gate.", 0.10, "auth_bruteforce"),
]


def init_db() -> None:
    """Crea el esquema y siembra reglas, honeypot por defecto y escenario builtin."""
    Base.metadata.create_all(_engine)
    with SessionLocal() as s:
        if s.scalar(select(DetectionRule).limit(1)) is None:
            s.add_all(
                DetectionRule(id=i, name=n, description=d, weight=w, rule_type=rt, is_active=True)
                for (i, n, d, w, rt) in _SEED_RULES
            )
        seed = settings.seed or uuid.uuid4().hex
        if s.scalar(select(HoneypotConfig).limit(1)) is None:
            s.add(
                HoneypotConfig(
                    id=1,
                    name="Honeypot Web Server",
                    type="HTTP",
                    port=settings.honeypot_port,
                    is_active=True,
                    token_drain_enabled=settings.token_drain_enabled,
                    generation_mode=settings.generation_mode,
                    seed=seed,
                    target_url=settings.target_url,
                    realism_level=max(1, min(settings.realism_level, 5)),
                    tarpit_delay_ms=settings.tarpit_delay_ms,
                    server_banner=settings.server_banner,
                    lexicon_theme=settings.lexicon_theme,
                    brand_name=settings.brand_name,
                )
            )
        # Sensor `local`: el propio honeypot visto como sensor (mismo seed).
        if s.scalar(select(Sensor).where(Sensor.kind == "local").limit(1)) is None:
            s.add(
                Sensor(
                    name="local",
                    kind="local",
                    enabled=True,
                    status="online",
                    seed=seed,
                    generation_mode=settings.generation_mode,
                    realism_level=max(1, min(settings.realism_level, 5)),
                    lexicon_theme=settings.lexicon_theme,
                    brand_name=settings.brand_name,
                    covered_url=f"http://localhost:{settings.honeypot_port}",
                    covered_app="local honeypot",
                    base_path="/",
                )
            )
        s.commit()

    # Siembra el escenario CTF incorporado (import diferido: evita ciclo de importación).
    from .scenarios import seed_builtin

    with SessionLocal() as s:
        seed_builtin(s)
