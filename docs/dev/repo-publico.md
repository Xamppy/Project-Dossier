# Copia pública del repositorio

El repositorio de trabajo es privado: [`Xamppy/Project-Dossier`](https://github.com/Xamppy/Project-Dossier).
Hay una copia pública de solo lectura en
[`Xamppy/Project-Dossier-public`](https://github.com/Xamppy/Project-Dossier-public).

## Por qué existe

- El docente y los evaluadores del proyecto APT (Duoc UC) tienen que poder ver el código y las
  ejecuciones de la CI sin tener acceso al repo de trabajo.
- El historial del repo privado tuvo datos personales: los RUT de los integrantes, en el PDF
  original de la Guía Fase 1. Borrarlos de `main` no los quita de los commits viejos. La copia
  pública se genera **reescribiendo el historial** sin esos archivos, para que no queden en
  ninguna versión.
- No tiene licencia de uso: todos los derechos quedan reservados por los autores (ver la nota del
  README).

Cómo está configurada la copia pública:

| Ajuste | Estado | Motivo |
|--------|--------|--------|
| Rama | Solo `main`, sin tags | El trabajo en curso queda en el privado |
| CI (`ci.yml`) | Activa | El docente ve ejecuciones en verde |
| Imágenes Docker (`imagenes.yml`) | **Deshabilitado** | Para que no publique imágenes en ghcr desde la copia |
| Issues, Wiki, Projects | Desactivados | Se gestionan en el privado |
| Dependabot | Activo (lee `.github/dependabot.yml`) | Abre PR en la copia. **No se mezclan ahí**: se cierran, y la actualización se hace en el privado |

## Cómo sincronizarla

La copia **no se actualiza sola**. Para llevar a la copia pública lo que entró en `main` del
privado:

```bash
# Requisitos: git-filter-repo, Python con PyMuPDF y, si se puede, gitleaks.
uv tool install git-filter-repo

scripts/sincronizar_repo_publico.sh          # clona, filtra y verifica; no sube nada
scripts/sincronizar_repo_publico.sh --push   # además hace push forzado de main al público
```

El script automatiza lo que se hizo a mano la primera vez:

1. `git clone --bare --no-local --single-branch --branch main` del privado en una carpeta temporal.
2. `git filter-repo --path "<archivo con datos personales>" --invert-paths` por cada archivo de
   la lista `RUTAS_EXCLUIDAS` del script.
3. Verificación de **todo** el historial: regex de RUT sobre `git log --all -p` y sobre el texto
   extraído de cada PDF y DOCX de cualquier commit. Si queda un RUT, el script se detiene sin
   subir nada. Después corre gitleaks, si está instalado.
4. Con `--push`: `git push --force` de `main` al repo público.

**Los SHA cambian, y es lo esperado.** filter-repo reescribe los commits, así que los
identificadores de la copia pública no coinciden con los del privado. Por eso el push al público
siempre es forzado y nadie debe trabajar sobre la copia pública: sus commits se reemplazan en
cada sincronización.

Si la variable `PYTHON` no apunta a un intérprete con PyMuPDF, la revisión de PDF falla y el
script se detiene. Ejemplo: `PYTHON=/ruta/a/venv/python scripts/sincronizar_repo_publico.sh`.

### Lo que sigue en commits viejos de la copia

El filtro solo quita los archivos de la lista. Algunos commits antiguos todavía traen ejemplos
con datos de terceros, que se limpiaron de `main` en el PR #30: el correo del User-Agent de la
SEC y nombres de personas y empresas reales en ejemplos y pruebas. Esos datos ya eran públicos en
el repositorio original del curso, y por eso se aceptó dejarlos. Si alguna vez hay que quitarlos,
se puede usar `git filter-repo --replace-text`.

## Advertencia: nunca subir datos personales

> Ni RUT, ni correos, ni teléfonos, ni direcciones de personas reales, **en ningún archivo**:
> código, pruebas, fixtures, documentos, PDF, capturas de pantalla ni mensajes de commit.

- En ejemplos y pruebas se usan datos ficticios: «Valeria Ruiz Prueba», «Empresa Ejemplo SpA»,
  correos `@example.com`.
- Borrar un dato en un commit nuevo **no basta**: sigue en el historial. Si se cuela uno, hay
  que retirarlo de `main` y agregar el archivo a `RUTAS_EXCLUIDAS`. Después se vuelve a
  sincronizar la copia pública. Si el dato ya llegó a la copia, avisa al equipo.
- Antes de subir documentos del curso (guías, informes), revisa que no traigan tablas de
  antecedentes personales. Para tachar un dato en un PDF hay que redactarlo de verdad, por
  ejemplo con PyMuPDF (`add_redact_annot` más `apply_redactions`). Un rectángulo dibujado encima
  deja el texto debajo.
