"""
Aplica el parche SQL `fix_dossier_credit_triggers.sql` usando la misma conexión que la API.

Uso (desde backend/, con `.env` configurado como `main.py`):

    python scripts/apply_fix_dossier_credit_triggers.py

En Windows suele no estar `psql` en el PATH; este script evita depender de él.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dossier.config import load_env  # noqa: E402


def _strip_sql_comments(sql: str) -> str:
    """Quita líneas que son solo comentarios `--` (el DDL del repo no usa strings con --)."""
    out_lines: list[str] = []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def extract_patch_statements(sql: str) -> list[str]:
    """
    Extrae sentencias del parche en orden fijo (sin partir por `;` dentro de plpgsql).
    """
    sql = sql.replace("\r\n", "\n")
    sql = re.sub(r"^\s*BEGIN\s*;\s*", "", sql, flags=re.IGNORECASE | re.MULTILINE)
    sql = re.sub(r"^\s*COMMIT\s*;\s*", "", sql, flags=re.IGNORECASE | re.MULTILINE)
    sql = _strip_sql_comments(sql)
    sql = sql.strip()

    out: list[str] = []

    def _take(pattern: str, flags: int = re.DOTALL | re.IGNORECASE) -> None:
        m = re.search(pattern, sql, flags)
        if not m:
            raise ValueError(f"No coincide el patrón del parche: {pattern[:80]}…")
        stmt = m.group(1).strip()
        if not stmt.endswith(";"):
            stmt += ";"
        out.append(stmt)

    _take(r"(DROP TRIGGER IF EXISTS\s+trg_credit_ledger_after_dossier_insert\s+ON\s+dossiers\s*;)")
    _take(
        r"(CREATE OR REPLACE FUNCTION\s+fn_debit_credits_on_dossier\s*\(\)\s*"
        r"RETURNS TRIGGER AS \$\$[\s\S]+?\$\$\s*LANGUAGE plpgsql\s*;)"
    )
    _take(
        r"(CREATE OR REPLACE FUNCTION\s+fn_credit_ledger_after_dossier_insert\s*\(\)\s*"
        r"RETURNS TRIGGER AS \$\$[\s\S]+?\$\$\s*LANGUAGE plpgsql\s*;)"
    )
    _take(r"(DROP TRIGGER IF EXISTS\s+trg_debit_credits\s+ON\s+dossiers\s*;)")
    _take(
        r"(CREATE TRIGGER\s+trg_debit_credits\s+"
        r"BEFORE INSERT ON dossiers\s+"
        r"FOR EACH ROW EXECUTE FUNCTION\s+fn_debit_credits_on_dossier\s*\(\)\s*;)",
        flags=re.IGNORECASE,
    )
    _take(
        r"(CREATE TRIGGER\s+trg_credit_ledger_after_dossier_insert\s+"
        r"AFTER INSERT ON dossiers\s+"
        r"FOR EACH ROW EXECUTE FUNCTION\s+fn_credit_ledger_after_dossier_insert\s*\(\)\s*;)",
        flags=re.IGNORECASE,
    )

    return out


def main() -> int:
    load_env()

    from sqlalchemy import text

    from dossier.db import is_database_configured
    from dossier.db.connection import get_engine

    sql_path = Path(__file__).resolve().parent / "fix_dossier_credit_triggers.sql"
    if not sql_path.is_file():
        print(f"ERROR: No existe {sql_path}")
        return 1

    if not is_database_configured():
        print("ERROR: Configura DATABASE_URL o POSTGRES_* en .env (igual que la API).")
        return 1

    raw = sql_path.read_text(encoding="utf-8")
    try:
        statements = extract_patch_statements(raw)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    if not statements:
        print("ERROR: No se obtuvieron sentencias SQL del archivo.")
        return 1

    engine = get_engine()
    print("Aplicando parche de triggers (credit_ledger / dossiers)…")
    try:
        with engine.begin() as conn:
            for i, stmt in enumerate(statements, 1):
                conn.execute(text(stmt))
                head = stmt.replace("\n", " ")[:72]
                print(f"  [{i}/{len(statements)}] OK — {head}…")
    except Exception as e:
        print(f"ERROR al ejecutar SQL: {e}")
        return 1

    print("\nParche aplicado. Reinicia la API (`python main.py`) y vuelve a generar un dossier.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
