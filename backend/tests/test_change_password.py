"""Contrato de cambio de contraseña: la nueva contraseña cabe en 72 bytes UTF-8 de bcrypt."""
import pytest
from pydantic import TypeAdapter, ValidationError

from dossier.schemas.auth import ChangePasswordRequest

ACTUAL = 'contraseña-actual'


@pytest.mark.parametrize('password', ['a' * 8, 'a' * 72, 'é' * 36, '🔐' * 18, 'ñ' * 30 + 'a' * 4 + '🔐' * 2])
def test_nueva_password_valida_se_conserva_exactamente(password):
    body = ChangePasswordRequest(current_password=ACTUAL, new_password=password)
    assert body.new_password == password


@pytest.mark.parametrize('password', ['a' * 73, 'a' * 128, 'a' * 129, 'é' * 37, '🔐' * 19, 'a' * 71 + 'é'])
def test_nueva_password_mayor_a_72_bytes_se_rechaza_con_mensaje(password):
    with pytest.raises(ValidationError) as error:
        ChangePasswordRequest(current_password=ACTUAL, new_password=password)
    detalles = error.value.errors()
    assert len(detalles) == 1
    detalle = detalles[0]
    assert detalle['loc'] == ('new_password',)
    assert detalle['type'] == 'password_too_long_bytes'
    assert detalle['ctx'] == {'max_bytes': 72}
    assert '72 bytes' in detalle['msg']


def test_nueva_password_minimo_de_ocho_caracteres_se_conserva():
    with pytest.raises(ValidationError) as error:
        ChangePasswordRequest(current_password=ACTUAL, new_password='é' * 7)
    assert error.value.errors()[0]['type'] == 'string_too_short'


@pytest.mark.parametrize('actual', ['a' * 73, 'é' * 64, 'a' * 128])
def test_password_actual_no_aplica_limite_de_bytes(actual):
    # Solo verifica: bcrypt 5 devuelve False (401) y no se fija ningún hash nuevo.
    body = ChangePasswordRequest(current_password=actual, new_password='nueva-segura')
    assert body.current_password == actual


def test_tipo_compartido_es_el_mismo_contrato_que_el_registro():
    from dossier.schemas.auth import NewPassword

    adapter = TypeAdapter(NewPassword)
    assert adapter.validate_python('é' * 36) == 'é' * 36
    with pytest.raises(ValidationError) as error:
        adapter.validate_python('é' * 37)
    detalle = error.value.errors()[0]
    assert detalle['type'] == 'password_too_long_bytes'
    assert detalle['ctx'] == {'max_bytes': 72}
