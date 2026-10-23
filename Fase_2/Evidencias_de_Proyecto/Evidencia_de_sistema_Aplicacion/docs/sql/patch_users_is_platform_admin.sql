-- Parche rápido si el modelo SQLAlchemy ya incluye `is_platform_admin` pero la BD antigua no.
-- Ejecutar contra la misma base que usa el backend (p. ej. psql -d Dossier -f ...).

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE;
