# BUG-2026-10-19-07 · Dossiers de calendario guardados con el correo de otro asistente

- **Tarea:** BUG-2026-10-19-07
- **Responsable:** FO (agente)
- **Brecha:** — (corrección de datos persistidos)
- **Estado:** implementada
- **Depende de:** BUG-2026-10-19-02 (PR #17), que corrige los dossiers nuevos

## Problema

Antes de BUG-2026-10-19-02, en una reunión con varios asistentes, el dossier de un asistente
sin correo propio se guardaba con el correo de otra persona, por dos caminos:

1. `_generate_one_person_dossier` rellenaba `person_email` con el primer correo corporativo del
   evento (descripción + participantes) y lo devolvía en `out["email"]`. PDL se consultaba con
   ese correo y `persist_calendar_dossiers` lo guardaba.
2. `persist_calendar_dossiers` usaba `parsed["person_email"]` (el del primer contacto, o el de
   la línea «Email:» de la descripción) como respaldo.

En ambos casos el dossier quedó con `subject_email` y `dossier_data.person_filters.email`
iguales al correo de otro asistente. En el peor caso, PDL devolvió el perfil de otra persona y
el informe habla de ella. El #17 corrige lo que viene; esta tarea trata **lo que ya está
guardado**.

Por qué importa además del informe ya generado: el botón de regenerar del dashboard rellena el
formulario con `person_filters.email` (o `subject_email`)
(`frontend/src/lib/person-research-from-dossier.ts`). Si no se corrige, regenerar vuelve a
consultar PDL con el correo ajeno, y vuelve a cobrar.

## Qué guarda cada dossier (modelo real)

`backend/src/dossier/db/models.py:Dossier` y `persist_calendar_dossiers`
(`services/calendar_event_dossiers.py`). Para cada asistente se guarda una fila con:

| Campo | Contenido |
|---|---|
| `subject_name` | nombre del asistente |
| `subject_email` | correo usado (el contaminado en los casos afectados) |
| `dossier_folder_id` | UUID nuevo **por cada llamada** a `persist_calendar_dossiers`: agrupa los dossiers de un mismo evento y una misma ejecución (job) |
| `dossier_data.calendar_folder.id` | el mismo UUID, dentro del JSON |
| `dossier_data.calendar_folder_role` | `"person"` o `"corporate"` |
| `dossier_data.person_filters.email` | el mismo correo que `subject_email` |
| `dossier_data.person_filters.contact_index` | posición del contacto en el evento |
| `calendar_event_id`, `dossier_data.calendar.external_event_id` | el evento |

**No se guarda** el resultado del parse (`parsed["person_email"]`, la descripción) ni qué correo
declaró cada asistente. Por eso la detección no puede comparar contra «el correo declarado»
directamente: tiene que deducirlo de las filas hermanas.

## Alcance

**Incluye:**
- Una función pura que detecta los dossiers afectados a partir de las filas guardadas.
- Una función que marca los afectados en una sesión de base de datos, en simulación por defecto.
- Un script de mantenimiento en `backend/scripts/` que la ejecuta.
- Documentación de cómo ejecutarlo, en `docs/postgresql.md` § «Mantenimiento de datos». No va en
  `db/Migracion.md`: ese archivo es el DDL (copia de `docs/sql/schema_project_dossier.sql`) y
  esta tarea no tiene DDL.

**No incluye:**
- Borrar dossiers ni regenerarlos.
- Corregir el cuerpo del informe (`dossier_data.body`): no se puede saber qué parte vino del
  perfil ajeno.
- Mostrar el aviso en la UI (ver «Tarea aparte propuesta»).
- Ejecutarlo contra ninguna base real: lo hace una persona, a mano, después de revisar la
  simulación.
- Invalidar la caché Redis de personas: su TTL es de 24 horas y las entradas de esa época ya
  expiraron.

## Diseño

### Mecanismo: script de mantenimiento, no migración de Alembic

`db/Migracion.md` y `db/schema_patches.py` describen y aplican **esquema**; las migraciones de
Alembic (`backend/alembic/versions/`) también son solo DDL y se ejecutan solas con
`alembic upgrade head` en cada despliegue. Esta tarea no cambia el esquema (todo cabe en
`dossier_data`, que es JSONB) y sí cambia **datos** con una heurística. Una migración de datos
se aplicaría sin que nadie revise la lista de afectados, sin modo de simulación y quedaría
mezclada con el historial de esquema. Un script explícito permite revisar el informe antes, se
ejecuta una vez por ambiente y se puede volver a correr sin efecto. Se sigue el patrón de los
scripts existentes (`apply_fix_dossier_credit_triggers.py`, `reset_google_calendar_integration.py`).

La lógica vive en `backend/src/dossier/services/dossiers_correo_ajeno.py` (importable y
probable); `backend/scripts/marcar_dossiers_correo_ajeno.py` es solo la entrada de línea de
comandos.

### Detección (determinista)

Universo: filas de `dossiers` con `dossier_data->>'calendar_folder_role' = 'person'`.

1. **Grupo** = `dossier_folder_id`; si es nulo, `dossier_data.calendar_folder.id`. Sin ninguno
   de los dos la fila se ignora (no se puede saber quiénes eran sus hermanos).
2. Se ignoran los grupos con **un solo** dossier de persona: con un único contacto, asignarle el
   correo corporativo del evento es el comportamiento correcto que el #17 conserva.
3. **Correo** de la fila = `subject_email` o, si es nulo, `person_filters.email`, normalizado
   (sin espacios, `casefold`). Las filas sin correo no participan.
4. Se ignoran las filas que ya llevan la marca `dossier_data.correo_sospechoso` (idempotencia).
5. Dentro del grupo se agrupan las filas por correo. Hay **colisión** cuando un mismo correo lo
   comparten filas con **nombres distintos** (normalizados: sin acentos, minúsculas, espacios
   colapsados). Dos filas con el mismo nombre normalizado son la misma persona y no colisionan.
6. En una colisión, a lo sumo una identidad es la dueña del correo. Se decide así:
   - **Dueña** = la única identidad cuyo nombre aparece en la parte local del correo: algún
     token del nombre de al menos 2 letras es igual a un token de la parte local (separada por
     `.`, `_`, `-`, `+`), o algún token de al menos 3 letras está contenido en ella
     (`jperez` contiene `perez`).
   - Si ninguna o más de una identidad cumple, **no hay dueña identificable**.
7. **Afectadas**: con dueña, todas las filas de las otras identidades
   (`motivo = "correo_de_otro_asistente"`); sin dueña, todas las filas de la colisión
   (`motivo = "correo_compartido_sin_dueno"`).

Por qué no se usa `contact_index` para elegir la dueña: el correo contaminante puede venir del
segundo contacto (Ana, índice 1, sin correo; Beto, índice 2, `beto@acme.com` en la descripción:
el código anterior le dio a Ana `beto@acme.com`). Elegir el índice menor dejaría el correo
ajeno en Ana y se lo quitaría a Beto.

Por qué, sin dueña, se marcan todas: el riesgo es asimétrico. Dejar un correo ajeno hace que
regenerar traiga y cobre el perfil de otra persona; anular uno correcto solo resta precisión a
una regeneración, y el valor original queda guardado en la marca.

Relación con la definición de la tarea («el `subject_email` coincide con el correo declarado
de otro asistente o con `person_email` del parse, y el nombre difiere»): como el parse no se
guarda, el correo declarado de otro asistente y `parsed["person_email"]` solo son observables
como el correo de una fila hermana. La colisión del paso 5 es esa condición expresada sobre lo
que sí está en la base.

### Qué se hace con cada afectado

En una sola transacción, por cada fila afectada:

- `subject_email` → `NULL`.
- `dossier_data.person_filters.email` → `null`, solo si coincide (normalizado) con el correo
  detectado.
- Se agrega `dossier_data.correo_sospechoso`:

```json
{
  "tarea": "BUG-2026-10-19-07",
  "motivo": "correo_de_otro_asistente",
  "correo_anterior": "ana.perez@acme.com",
  "person_filters_email_anterior": "ana.perez@acme.com",
  "presunto_dueno": {"dossier_id": "…", "subject_name": "Ana Pérez"},
  "comparte_con": [{"dossier_id": "…", "subject_name": "Ana Pérez"}],
  "marcado_en": "2026-10-19T12:00:00+00:00"
}
```

`presunto_dueno` es `null` cuando `motivo = "correo_compartido_sin_dueno"`. No se toca nada más:
`billing`, `body`, `status`, créditos y el resto de `dossier_data` quedan igual. El trigger de
cobro es `BEFORE INSERT`, así que un `UPDATE` no cobra. `updated_at` cambia por su trigger.

No se borra nada: el valor anterior queda en la marca y el cambio es reversible.

### Ejecución

```
python scripts/marcar_dossiers_correo_ajeno.py            # simulación (por defecto)
python scripts/marcar_dossiers_correo_ajeno.py --dry-run  # simulación, explícito
python scripts/marcar_dossiers_correo_ajeno.py --aplicar  # escribe
```

Imprime un informe JSON con `modo` (`"simulacion"` o `"aplicado"`), `revisados`,
`grupos_revisados`, `afectados` (una entrada por fila: `dossier_id`, `organization_id`,
`subject_name`, `correo_anterior`, `motivo`, `presunto_dueno`) y `ya_marcados` (cuántas filas se
saltaron por llevar la marca). En simulación no escribe ni hace `commit`.

## Criterios de aceptación

- [x] **CA1** — Dado un grupo con Ana (`ana.perez@acme.com`) y Beto con ese mismo correo,
  cuando se detecta, entonces Beto es afectado con `motivo = "correo_de_otro_asistente"` y
  presunta dueña Ana; Ana no es afectada.
- [x] **CA2** — Dado un grupo donde el correo compartido es el de quien tiene el índice mayor
  (`beto@acme.com` en Ana, índice 1, y en Beto, índice 2), entonces la afectada es Ana.
- [x] **CA3** — Dado un grupo donde dos asistentes comparten `ventas@acme.com` y ningún nombre
  aparece en el correo, entonces ambos son afectados con `motivo = "correo_compartido_sin_dueno"`
  y sin presunto dueño.
- [x] **CA4** — Dado un grupo donde cada asistente tiene un correo distinto, no hay afectados.
- [x] **CA5** — Dado un grupo con un solo asistente (con el correo corporativo del evento), no
  hay afectados.
- [x] **CA6** — Dado un grupo donde un asistente tiene correo propio y otro no tiene correo, no
  hay afectados.
- [x] **CA7** — Dos filas con el mismo nombre salvo acentos y mayúsculas, y el mismo correo, no
  son afectadas. El correo se compara sin distinguir mayúsculas.
- [x] **CA8** — El mismo correo en dos grupos distintos (eventos o ejecuciones distintas) no es
  colisión. Las filas sin grupo se ignoran. Las filas ya marcadas se ignoran.
- [x] **CA9** — Marcar un `dossier_data` devuelve uno nuevo con `correo_sospechoso`,
  `person_filters.email = null` y el resto intacto (incluido `billing`), sin modificar el
  original.
- [x] **CA10** — Contra Postgres, en simulación (por defecto y con `--dry-run`), el informe
  lista los afectados y ninguna fila cambia.
- [x] **CA11** — Contra Postgres, con `--aplicar`, solo las filas afectadas quedan con
  `subject_email` nulo y la marca; las demás (incluido el dossier corporativo y los grupos
  limpios) quedan idénticas.
- [x] **CA12** — Contra Postgres, una segunda ejecución con `--aplicar` no encuentra afectados
  y no cambia ninguna fila (idempotencia).

## Pruebas exigidas

| Categoría | Obligatoria | Qué cubre |
|---|:---:|---|
| Unitaria | ✅ | CA1–CA9: `tests/test_dossiers_correo_ajeno.py` |
| Integración | ✅ | CA10–CA12: `tests/integration/test_dossiers_correo_ajeno_integracion.py` (Postgres de `TEST_DATABASE_URL`) |
| Estrés | | Una sola pasada por ambiente; el volumen se lee en una consulta |
| Seguridad | | No cambia acceso. El script no imprime credenciales |

## Riesgos

- **Falsos negativos.** Si solo un asistente quedó con el correo de alguien que no es asistente
  con dossier (por ejemplo, el del organizador en «participantes»), no hay colisión entre filas
  y no se detecta. Con lo guardado no hay forma determinista de verlo.
- **Falsos positivos.** Dos asistentes que de verdad declararon el mismo buzón compartido
  (`ventas@`) quedan marcados como «sin dueño». Es aceptable: el correo es ambiguo para ambos y
  el valor queda en la marca.
- **Regenerar borra la marca.** La regeneración reconstruye `dossier_data` y solo conserva los
  metadatos de calendario. Es lo deseable: el informe nuevo ya no es el sospechoso.

## Tarea aparte propuesta (no se implementa aquí)

**UX: aviso de dossier sospechoso.** En el detalle del dossier, si
`dossier_data.correo_sospechoso` existe, mostrar un aviso: «Este informe se generó con el correo
de otro asistente y puede describir a otra persona. Regenéralo con el correo correcto.» Costo
bajo: el detalle ya recibe `dossier_data` completo; es un componente condicional y las cadenas
en los cinco idiomas.

## Decisiones pendientes

Ninguna para implementar. Ejecutarlo en producción queda a decisión del equipo, después de
revisar la simulación.
