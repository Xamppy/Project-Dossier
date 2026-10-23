"""PATCH /auth/me/password sin PostgreSQL: usuario y sesión de BD simulados.

La ruta real de FastAPI, el esquema y `change_user_password` corren completos; solo se
sustituyen las dependencias `get_current_user` y `get_db_if_configured`.
"""
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dossier.api.auth_routes import get_current_user, get_db_if_configured, router
from dossier.db.models import User
from dossier.security import hash_password, verify_password

ACTUAL = 'contraseña-actual'


@pytest.fixture(scope='module')
def hash_actual():
    return hash_password(ACTUAL)


@pytest.fixture
def cambio(hash_actual):
    user = User(email='persona@example.com', full_name='Persona Prueba', password_hash=hash_actual)
    db = Mock()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db_if_configured] = lambda: db
    return TestClient(app, raise_server_exceptions=False), user, db


@pytest.mark.parametrize('password', ['a' * 8, 'a' * 72, 'é' * 36, '🔐' * 18])
def test_cambio_hasta_72_bytes_guarda_hash_bcrypt_verificable(cambio, hash_actual, password):
    client, user, db = cambio
    response = client.patch('/auth/me/password', json={'current_password': ACTUAL, 'new_password': password})
    assert response.status_code == 204, response.text
    assert user.password_hash != hash_actual
    assert user.password_hash.startswith('$2b$')
    assert verify_password(password, user.password_hash)
    assert not verify_password(ACTUAL, user.password_hash)
    db.commit.assert_called_once()


@pytest.mark.parametrize('password', ['a' * 73, 'a' * 128, 'a' * 129, 'é' * 37, '🔐' * 19])
def test_exceso_de_bytes_devuelve_422_sin_modificar_el_hash(cambio, hash_actual, password):
    client, user, db = cambio
    response = client.patch('/auth/me/password', json={'current_password': ACTUAL, 'new_password': password})
    assert response.status_code == 422, response.text
    detail = response.json()['detail']
    assert len(detail) == 1
    assert detail[0]['loc'] == ['body', 'new_password']
    assert detail[0]['type'] == 'password_too_long_bytes'
    assert detail[0]['ctx'] == {'max_bytes': 72}
    assert '72 bytes' in detail[0]['msg']
    assert user.password_hash == hash_actual
    assert verify_password(ACTUAL, user.password_hash)
    assert db.mock_calls == []
