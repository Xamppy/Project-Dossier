"""
Hash y verificación de contraseñas con bcrypt.

Nunca guardamos la contraseña en claro: solo el hash (irreversible).
bcrypt incorpora "salt" automáticamente por cada hash.
"""
from __future__ import annotations

import bcrypt


def hash_password(plain_password: str) -> str:
    """Devuelve un string ASCII seguro para guardar en `password_hash`."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("ascii")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Comprueba si la contraseña coincide con el hash almacenado."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except ValueError:
        return False
