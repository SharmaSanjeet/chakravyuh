"""Configuración de tests: DB temporal aislada antes de importar chakravyuh."""

import os
import tempfile

import pytest

# La config se lee al importar chakravyuh.config, así que fijamos el entorno ANTES.
# El prefijo es CHAKRAVYUH_ y el campo db_path -> variable CHAKRAVYUH_DB_PATH.
_tmp = tempfile.mkdtemp(prefix="chakravyuh-test-")
os.environ["CHAKRAVYUH_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["CHAKRAVYUH_AI_ENABLED"] = "false"
os.environ["CHAKRAVYUH_ENFORCE_BLOCK"] = "false"
# World desactivado por defecto en los tests: así los tests del honeypot siguen ejercitando el
# laberinto legacy. El World se prueba aparte (tests/test_world.py) montándolo explícitamente.
os.environ["CHAKRAVYUH_WORLD_ENABLED"] = "false"
# Admin de prueba con contraseña conocida (si no, bootstrap_admin genera una aleatoria).
os.environ["CHAKRAVYUH_ADMIN_PASSWORD"] = "test-admin-pw"

TEST_ADMIN_USER = "admin"
TEST_ADMIN_PASSWORD = "test-admin-pw"


@pytest.fixture(autouse=True)
def _auth_bypass():
    """Desactiva la guarda de sesión del dashboard en los tests (la API se prueba sin login).

    Los tests de autenticación quitan este override para ejercitar la guarda REAL:
        app.dependency_overrides.pop(require_user, None)
    """
    from chakravyuh.api import app
    from chakravyuh.api.auth import require_user

    app.dependency_overrides[require_user] = lambda: {"username": "test", "role": "admin", "uid": 0}
    yield
    app.dependency_overrides.pop(require_user, None)
