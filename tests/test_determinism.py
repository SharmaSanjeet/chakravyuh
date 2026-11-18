"""Determinismo y anti-fingerprint del laberinto."""

from chakravyuh import lexicon as vocab
from chakravyuh.maze import MazeGenerator, MazeOptions, kind_of
from chakravyuh.rng import SeededRandom


def test_rng_deterministic_same_seed_path():
    assert SeededRandom("s1", "/a/b").alnum(32) == SeededRandom("s1", "/a/b").alnum(32)


def test_rng_changes_with_seed():
    assert SeededRandom("s1", "/a/b").alnum(32) != SeededRandom("s2", "/a/b").alnum(32)


def test_maze_deterministic():
    opts = MazeOptions(seed="deploy-123", realism_level=4)
    gen = MazeGenerator()
    for path in ["/", "/ops/", "/ops/secrets/.env", "/api/v1/users", "/ops/README.md"]:
        a = gen.generate(opts, path)
        b = gen.generate(opts, path)
        assert a.body == b.body, f"not deterministic at {path}"
        assert a.content_type == b.content_type


def test_maze_anti_fingerprint():
    a = MazeGenerator().generate(MazeOptions(seed="deploy-A"), "/")
    b = MazeGenerator().generate(MazeOptions(seed="deploy-B"), "/")
    assert a.body != b.body


def test_dir_tree_navigable_without_name_recursion():
    # La raíz y los niveles altos son navegables, pero el árbol se afina con la profundidad
    # (puede terminar como uno real) y NUNCA repite el nombre de un ancestro (/exports/exports/).
    opts = MazeOptions(seed="deploy-123")
    gen = MazeGenerator()
    root_subdirs = [link for link in gen.links_for(opts, "/") if link.endswith("/")]
    assert root_subdirs, "the root must be navigable"
    path = root_subdirs[0]
    for _ in range(8):
        segs = [s for s in path.strip("/").split("/")]
        assert len(segs) == len(set(segs)), f"repeated path segment (recursion) at {path}"
        subs = [link for link in gen.links_for(opts, path) if link.endswith("/")]
        if not subs:
            break  # dead-end realista: aceptable por diseño
        path = subs[0]


def test_unlinked_paths_return_not_reachable():
    # Un sitio real finito: lo enlazado existe (200), lo sondeado al azar no (404).
    opts = MazeOptions(seed="deploy-123")
    gen = MazeGenerator()
    assert any(gen.is_reachable(opts, link) for link in gen.links_for(opts, "/"))
    for probe in ["/favicon.ico", "/index.php", "/wp-login.php", "/nonexistent-31404-xyz"]:
        assert not gen.is_reachable(opts, probe), f"{probe} should not be reachable"
    # Una colección de API que existe en el deployment SÍ es alcanzable; una inexistente, NO
    # (antes CUALQUIER /api/... daba 200 -> delator; ahora la API es finita y coherente).
    res = vocab.resources(gen.global_ctx(opts).theme)[0]
    assert gen.is_reachable(opts, f"/api/v2/{res}")
    assert not gen.is_reachable(opts, "/api/v2/nonexistent-collection-xyz")


def test_kind_of_classification():
    cases = {
        "/": "landing",
        "/ops/": "dir",
        "/ops/.env": "env",
        "/ops/config.yaml": "config",
        "/ops/credentials.json": "apiconfig",
        "/api/v1/users": "api",
        "/ops/README.md": "readme",
        "/ops/app.js": "js",
        "/ops/deploy.sh": "script",
        "/ops/access.log": "noise",
        "/ops/backup.sql": "sqldump",
        "/ops/data.bak": "archive",
        "/ops/acme-cli": "binary",
    }
    for path, expected in cases.items():
        assert kind_of(path) == expected, f"{path} -> {kind_of(path)} (expected {expected})"


def test_mimic_profile_biases_lexicon():
    # Un perfil Mimic debe inyectar su vocabulario en los directorios generados.
    profile = {
        "lexicon": ["widgets", "tenants"],
        "paths": ["/widgets/", "/billing/"],
        "api_prefixes": ["/api/"],
        "server_banner": "cloudflare",
    }
    opts = MazeOptions(seed="m1", mode="Mimic", profile=profile)
    gen = MazeGenerator()
    # El banner del perfil se refleja en el contexto global.
    assert gen.global_ctx(opts).banner == "cloudflare"
