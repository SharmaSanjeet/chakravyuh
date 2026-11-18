"""Red de seguridad de inertness del architect (defensa en profundidad).

TODO byte que el agente quiera escribir pasa por aquí ANTES de tocar disco, y el
árbol completo se re-valida ANTES de publicarse al World en vivo. El principio no
negociable: Chakravyuh solo sirve **bytes estáticos** y jamás ejecuta contenido de los
portales. Este módulo hace cumplir eso de forma mecánica (no confía en el prompt):

  1. Rutas seguras: relativas, sin `..`, sin absolutas/NUL, extensión en allowlist.
  2. Sin marcadores de ejecución del lado servidor (`<?php`, `<% %>`, shebangs…).
  3. Sin cargas/callbacks ACTIVOS a orígenes externos (script/link/img/iframe/form,
     fetch/import/XHR/WebSocket, CSS url()/@import). Todo queda same-origin: los
     "logins" postean al gate de Chakravyuh, nunca a un backend real ni a un beacon.
  4. Límites de tamaño.

El contenido SÍ puede incluir secretos/credenciales *fabricados* (son el cebo); la
invariante de "una sola credencial viva" la impone el lado del pack de escenario,
no este validador, cuyo trabajo es exclusivamente la INERTNESS.
"""

from __future__ import annotations

import os
import posixpath
import re

# Extensiones permitidas -> si es texto se escanea su contenido; binarias solo por tamaño/tipo.
_TEXT_EXTS = {
    ".html", ".htm", ".css", ".js", ".mjs", ".json", ".txt", ".md",
    ".csv", ".xml", ".svg", ".yaml", ".yml", ".webmanifest", ".map",
}
_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pdf",
}
ALLOWED_EXTS = _TEXT_EXTS | _BINARY_EXTS

MAX_TEXT_BYTES = 512 * 1024          # 512 KiB por fichero de texto
MAX_BINARY_BYTES = 4 * 1024 * 1024   # 4 MiB por binario (fuentes/imágenes)
MAX_REL_DEPTH = 10
MAX_REL_LEN = 240

# Único patrón de plantilla permitido en ficheros del World: tokens dinámicos de Chakravyuh.
_ALLOWED_DYNAMIC = re.compile(r"\{\{\s*chakravyuh\.(?:now_iso|uptime_seconds|minutes_ago)\s*\}\}")
# Placeholders del motor de escenario (SOLO válidos en cuerpos de cebo, no en ficheros del World):
# los sustituye el ScenarioEngine al servir, nunca se ejecutan.
_SCENARIO_PLACEHOLDER = re.compile(r"\{\{\s*(?:brand|slug|token|cred:[\w-]+|user:[\w-]+)\s*\}\}")

# Marcadores de ejecución del lado servidor: prohibidos en cualquier parte.
_SERVER_EXEC = [
    (re.compile(r"<\?php", re.I), "open PHP (<?php)"),
    (re.compile(r"<\?=", re.I), "PHP short-echo (<?=)"),
    (re.compile(r"<\?(?![x])", re.I), "processing instruction <? ...?>"),  # permite <?xml
    (re.compile(r"<%[-=@!]?"), "ASP/JSP/EJS scriptlet (<% %>)"),
    (re.compile(r"#!\s*/"), "script shebang (#!/...)"),
    (re.compile(r"\{%[-\s]"), "server template block ({% %})"),
    (re.compile(r"<jsp:", re.I), "JSP tag"),
]

# Cargas/callbacks ACTIVOS a orígenes externos (absolutos o protocol-relative).
_EXT = r"(?:https?:)?//"  # http://, https:// o //host
_ACTIVE_EXTERNAL = [
    (re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"]?\s*" + _EXT, re.I), "external <script src>"),
    (re.compile(r"<link\b[^>]*\bhref\s*=\s*['\"]?\s*" + _EXT, re.I), "external <link href>"),
    (re.compile(r"<iframe\b[^>]*\bsrc\s*=\s*['\"]?\s*" + _EXT, re.I), "external <iframe src>"),
    (re.compile(r"<img\b[^>]*\bsrc\s*=\s*['\"]?\s*" + _EXT, re.I), "external <img src>"),
    (
        re.compile(r"<(?:audio|video|source|track|embed|object)\b[^>]*\b(?:src|data)\s*=\s*['\"]?\s*" + _EXT, re.I),
        "external media",
    ),
    (re.compile(r"<form\b[^>]*\baction\s*=\s*['\"]?\s*" + _EXT, re.I), "external <form action>"),
    (re.compile(r"\bfetch\s*\(\s*['\"]\s*" + _EXT, re.I), "external fetch()"),
    (re.compile(r"\bimport\s*\(\s*['\"]\s*" + _EXT, re.I), "external dynamic import()"),
    (re.compile(r"\bimport\b[^;\n]*\bfrom\s*['\"]\s*" + _EXT, re.I), "external import ... from"),
    (re.compile(r"\bnew\s+WebSocket\s*\(\s*['\"]\s*wss?://", re.I), "external WebSocket"),
    (re.compile(r"\bnew\s+EventSource\s*\(\s*['\"]\s*" + _EXT, re.I), "external EventSource"),
    (re.compile(r"\.open\s*\(\s*['\"][A-Z]+['\"]\s*,\s*['\"]\s*" + _EXT, re.I), "external XMLHttpRequest"),
    (re.compile(r"@import\s+(?:url\()?\s*['\"]?\s*" + _EXT, re.I), "external CSS @import"),
    (re.compile(r"\burl\(\s*['\"]?\s*" + _EXT, re.I), "external CSS url()"),
    (re.compile(r"\bnavigator\.sendBeacon\s*\(\s*['\"]\s*" + _EXT, re.I), "external sendBeacon"),
    (re.compile(r"<(?:image|use|feimage)\b[^>]*\b(?:xlink:)?href\s*=\s*['\"]?\s*" + _EXT, re.I), "external SVG ref"),
    (re.compile(r"\bxlink:href\s*=\s*['\"]?\s*" + _EXT, re.I), "external xlink:href"),
]


class InertnessError(ValueError):
    """La ruta o el contenido viola la inertness; incluye las razones concretas."""

    def __init__(self, path: str, reasons: list[str]) -> None:
        self.path = path
        self.reasons = reasons
        super().__init__(f"{path}: " + "; ".join(reasons))


def safe_relpath(path: str) -> str:
    """Normaliza a una ruta relativa POSIX segura o lanza InertnessError.

    Rechaza absolutas, traversal (`..`), NUL, backslashes, profundidad/longitud excesivas.
    """
    reasons: list[str] = []
    raw = path or ""
    if "\x00" in raw:
        reasons.append("NUL in path")
    if "\\" in raw:
        reasons.append("backslash in path (use '/')")
    norm = raw.replace("\\", "/").lstrip("/")
    norm = posixpath.normpath(norm)
    if norm.startswith("..") or "/../" in f"/{norm}/" or norm == "." or norm == "":
        reasons.append("traversal or empty path")
    if os.path.isabs(raw) or raw.startswith("/"):
        reasons.append("absolute path")
    if len(norm) > MAX_REL_LEN:
        reasons.append(f"path too long (>{MAX_REL_LEN})")
    if norm.count("/") + 1 > MAX_REL_DEPTH:
        reasons.append(f"excessive depth (>{MAX_REL_DEPTH})")
    ext = posixpath.splitext(norm)[1].lower()
    if ext not in ALLOWED_EXTS:
        reasons.append(f"extension not allowed: {ext or '(none)'}")
    if reasons:
        raise InertnessError(path, reasons)
    return norm


def _scan_text(body: bytes, allow_scenario: bool = False) -> list[str]:
    """Escanea contenido de texto en busca de ejecución de servidor y callbacks externos.

    `allow_scenario`: True solo para cuerpos de cebo (permite `{{cred:...}}`, `{{brand}}`, etc.).
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return ["non-UTF-8 text (should be binary or valid UTF-8)"]
    reasons: list[str] = []
    for rx, label in _SERVER_EXEC:
        if rx.search(text):
            reasons.append(f"server execution marker: {label}")
    # Oculta los tokens permitidos para que no disparen el chequeo de `{{ ... }}` desconocido.
    scrubbed = _ALLOWED_DYNAMIC.sub("", text)
    if allow_scenario:
        scrubbed = _SCENARIO_PLACEHOLDER.sub("", scrubbed)
    if re.search(r"\{\{", scrubbed):
        allowed = "{{chakravyuh.*}} (+ scenario placeholders)" if allow_scenario else "{{chakravyuh.*}}"
        reasons.append(f"unknown template expression ({{{{ ... }}}}) — only {allowed} is allowed")
    for rx, label in _ACTIVE_EXTERNAL:
        if rx.search(text):
            reasons.append(f"external load/callback: {label}")
    return reasons


def validate_file(path: str, body: bytes, *, allow_scenario_placeholders: bool = False) -> str:
    """Valida ruta + contenido de UN fichero. Devuelve la ruta relativa segura o lanza.

    Es el único camino por el que un byte llega al build del World. `allow_scenario_placeholders`
    se usa solo al validar cuerpos del pack de cebo (no ficheros del World, que se sirven crudos).
    """
    rel = safe_relpath(path)  # puede lanzar
    ext = posixpath.splitext(rel)[1].lower()
    reasons: list[str] = []
    is_text = ext in _TEXT_EXTS
    limit = MAX_TEXT_BYTES if is_text else MAX_BINARY_BYTES
    if len(body) > limit:
        reasons.append(f"size {len(body)}B exceeds the {limit}B limit")
    if is_text:
        reasons.extend(_scan_text(body, allow_scenario=allow_scenario_placeholders))
    if reasons:
        raise InertnessError(path, reasons)
    return rel


def validate_manifest(manifest: dict, present_dirs: set[str]) -> list[str]:
    """Valida el manifest del World: mounts bien formados, dirs dentro del build y presentes.

    `present_dirs` = conjunto de rutas de directorio relativas POSIX que existen en el build.
    Devuelve una lista de problemas (vacía = ok).
    """
    problems: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    mounts = manifest.get("mounts")
    if not isinstance(mounts, list) or not mounts:
        return ["manifest.mounts missing or empty"]
    seen_prefixes: set[str] = set()
    for i, m in enumerate(mounts):
        if not isinstance(m, dict):
            problems.append(f"mount[{i}] is not an object")
            continue
        prefix = "/" + str(m.get("prefix", "/")).strip("/")
        if prefix in seen_prefixes:
            problems.append(f"mount[{i}] duplicate prefix: {prefix}")
        seen_prefixes.add(prefix)
        d = str(m.get("dir", ""))
        try:
            rel_dir = posixpath.normpath(d.replace("\\", "/").lstrip("/"))
        except Exception:
            problems.append(f"mount[{i}] invalid dir: {d!r}")
            continue
        if rel_dir.startswith("..") or os.path.isabs(d):
            problems.append(f"mount[{i}] dir escapes the build: {d!r}")
        elif rel_dir not in present_dirs:
            problems.append(f"mount[{i}] dir does not exist in the build: {rel_dir}")
    return problems


def validate_tree(root: str) -> list[str]:
    """Re-valida TODO el build (gate final antes de publicar). Devuelve problemas (vacía = ok).

    Recorre cada fichero por `validate_file` y valida `manifest.json`. Cualquier fichero no
    permitido o con contenido ejecutable/externo invalida la publicación entera.
    """
    problems: list[str] = []
    present_dirs: set[str] = set()
    manifest_obj: dict | None = None
    for dirpath, _dirnames, filenames in os.walk(root):
        rel_dir = posixpath.normpath(os.path.relpath(dirpath, root).replace(os.sep, "/"))
        if rel_dir != ".":
            present_dirs.add(rel_dir)
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = posixpath.normpath(os.path.relpath(abs_path, root).replace(os.sep, "/"))
            if rel == "manifest.json":
                try:
                    import json

                    manifest_obj = json.loads(open(abs_path, "rb").read().decode("utf-8"))
                except (OSError, ValueError, UnicodeDecodeError) as e:
                    problems.append(f"manifest.json unreadable: {e}")
                continue
            try:
                with open(abs_path, "rb") as f:
                    body = f.read()
                validate_file(rel, body)
            except InertnessError as e:
                problems.append(str(e))
            except OSError as e:
                problems.append(f"{rel}: could not read ({e})")
    if manifest_obj is None:
        problems.append("manifest.json missing from the build")
    else:
        problems.extend(validate_manifest(manifest_obj, present_dirs))
    return problems
