"""El exceso de bytes se rechaza antes de verificar la contraseña actual o tocar la BD."""
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dossier.api.auth_routes import get_current_user, get_db_if_configured, router
from dossier.db.models import User
from dossier.security import hash_password

ACTUAL = 'contraseña-actual'


@pytest.mark.parametrize('current_password', [ACTUAL, 'incorrecta'])
@pytest.mark.parametrize('password', ['a' * 73, 'é' * 37, '🔐' * 19])
def test_rechazo_no_revela_si_la_password_actual_es_correcta(password, current_password):
    """Mismo 422 con la contraseña actual buena o mala: no sirve de oráculo ni produce 500."""
    original = hash_password(ACTUAL)
    user = User(email='persona@example.com', full_name='Persona Prueba', password_hash=original)
    db = Mock()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_if_configured] = lambda: db
    response = TestClient(app, raise_server_exceptions=False).patch(
        '/auth/me/password', json={'current_password': current_password, 'new_password': password},
    )
    assert response.status_code == 422, response.text
    assert response.json()['detail'][0]['type'] == 'password_too_long_bytes'
    assert user.password_hash == original
    assert db.mock_calls == []
