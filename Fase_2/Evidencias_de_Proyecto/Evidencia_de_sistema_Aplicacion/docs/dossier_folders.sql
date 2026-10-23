-- Carpetas de dossiers (agrupa empresa + persona del mismo evento de calendario).
-- Ejecutar una vez en PostgreSQL si la columna aún no existe.

ALTER TABLE dossiers
    ADD COLUMN IF NOT EXISTS dossier_folder_id UUID;

CREATE INDEX IF NOT EXISTS idx_dossiers_folder
    ON dossiers (dossier_folder_id)
    WHERE dossier_folder_id IS NOT NULL;
