# Agregar una fuente de noticias

Guía para conectar otra API de prensa (Factiva, LexisNexis, Event Registry, Perigon u otra) sin
tocar el resto del sistema. Decisión de diseño: [`UX-ADMIN-02`](../../specs/proposals/UX-ADMIN-02-fuentes-noticias.md).

## Cómo funciona

Cada fuente es un **adaptador**: un archivo en `backend/src/dossier/news/proveedores/` que expone
`PROVEEDOR`. Al arrancar, la API descubre todos los adaptadores de esa carpeta. Para cada dossier,
el sistema:

1. Elige las fuentes según los ajustes del administrador: activa, empresas o personas,
   profundidad mínima, planes y si su clave está configurada.
2. Las consulta **en paralelo**, cada una con un tiempo máximo (25 s) y su máximo de noticias.
3. Respeta el **límite diario** de cada fuente (sin carreras entre dossiers simultáneos).
4. Junta los resultados, elimina duplicados y **filtra homónimos**.
5. Pasa las menciones a la IA como datos externos (nunca como instrucciones) y las muestra en la
   tarjeta «Prensa» con su procedencia.
6. Cobra los **créditos extra** de las fuentes que respondieron. Si una falla, el dossier sale
   igual y esa fuente no se cobra.

Hoy vienen instaladas **GDELT** (gratis, sin clave) y **NewsAPI** (clave gratis del plan
Developer en newsapi.org).

## Pasos

### 1. Copia la plantilla

```bash
cd backend/src/dossier/news/proveedores
cp _plantilla.py mi_fuente.py
```

El nombre no debe empezar con `_`: esos archivos se ignoran.

### 2. Completa los datos de la fuente

| Atributo | Qué es | Ejemplo |
|---|---|---|
| `clave` | Identificador estable: minúsculas, números y `_`, de 2 a 40, empieza con letra. No se cambia una vez en uso (es la llave de sus ajustes) | `factiva` |
| `nombre` | Lo que ve el administrador y lo que se cita como fuente en el dossier | `Dow Jones Factiva` |
| `descripcion` | Qué cubre, idiomas y costo, para que el administrador decida | `Prensa de pago global, archivo desde 1980` |
| `variable_clave` | Variable de entorno con la clave de la API, o `None` si no usa clave | `FACTIVA_API_KEY` |
| `activo_por_defecto` | Déjalo en `False`: la fuente aparece apagada y la activa el administrador | `False` |

### 3. Escribe `buscar(consulta, limite)`

Recibe la consulta ya armada (por ejemplo `"Ana Pérez" "Acme"` o `Acme Corp`) y devuelve una lista
de `ArticuloNoticia`:

| Campo | Obligatorio | Formato |
|---|---|---|
| `titulo` | Sí | Titular de la nota |
| `url` | Sí | Enlace público a la nota |
| `medio` | No | Nombre del medio |
| `publicado` | No | Fecha ISO 8601 (`2026-11-01T10:00:00Z`) |
| `resumen` | No | Bajada o extracto. Si la API no trae, deja `None`: el sistema arma uno genérico |

Reglas:

- **Consulta vacía:** devuelve `[]` sin llamar a la API.
- **Cualquier fallo** (red, HTTP, formato inesperado): lanza `ProveedorNoticiasError` con un
  mensaje **sin la clave ni la respuesta completa**. El sistema lo anota y sigue con las demás.
- **La clave va en una cabecera**, nunca en la URL: las URL quedan en los logs. Usa
  `self.clave_api()`, que la lee del entorno y avisa si falta.
- Pon un `timeout` en la llamada HTTP (la plantilla usa 20 s).
- Una nota sin título o sin URL se descarta.

### 4. Configura la clave en el servidor

En el `.env` del backend o en el gestor de secretos del hosting:

```bash
FACTIVA_API_KEY=...
```

Nunca en el código ni en la base de datos. El panel de administración solo muestra si la clave
está configurada y el nombre de la variable.

### 5. Corre las pruebas de contrato

```bash
cd backend
.venv/Scripts/python -m pytest tests/test_news_proveedores.py -q
```

Recorren **todas** las fuentes instaladas, incluida la nueva: datos válidos, consulta vacía sin
red y fallo HTTP informado como `ProveedorNoticiasError`. Si el adaptador no cumple el contrato,
la API lo omite al arrancar y lo anota en el log («Fuente de noticias … omitida»).

Para probar el formato de la respuesta, agrega una prueba propia con una respuesta fija, como las
de `tests/test_news_client.py`.

### 6. Reinicia la API y configúrala en el panel

La fuente aparece **apagada** en **Administración → Fuentes de noticias**. Ahí el administrador
de plataforma decide:

| Ajuste | Para qué |
|---|---|
| Activa | Encenderla o apagarla sin tocar código |
| Usar en Empresas / Personas | En qué tipo de dossier se consulta |
| Profundidad mínima (empresas) | Por ejemplo, una API cara solo en dossiers *Deep*. Las personas siempre son de profundidad básica |
| Planes | Free, Pro o Enterprise |
| Créditos extra por dossier | De 0 a 20. Se cobran solo si la fuente responde, sumados al costo por profundidad |
| Máximo de noticias | De 1 a 50 por consulta |
| Límite diario de consultas | Vacío = sin límite. Se reinicia cada día (UTC). Al llegar al tope la fuente se omite, sin cobro |

Cada cambio queda en `audit_logs` (`ADMIN news_source_settings`) con el valor anterior y el nuevo.

## Qué ve el usuario

- En **Personas** y **Empresas**, el resumen muestra las fuentes de prensa que se usarán y el costo
  máximo: «3 (hasta 2 por prensa)». El extra solo se cobra si la fuente responde.
- En el avance de Personas aparece la etapa «Buscar menciones en prensa».
- En el dossier, la tarjeta «Prensa» lista las menciones con su medio, fecha y enlace.

## Dónde está cada pieza

| Pieza | Archivo |
|---|---|
| Contrato del adaptador | `backend/src/dossier/news/proveedores/base.py` |
| Descubrimiento y validación | `backend/src/dossier/news/proveedores/registro.py` |
| Plantilla | `backend/src/dossier/news/proveedores/_plantilla.py` |
| Consulta en paralelo, cupo diario y deduplicación | `backend/src/dossier/news/agent.py` |
| Selección según los ajustes, uso diario | `backend/src/dossier/services/news_sources.py` |
| Tablas `news_source_settings` y `news_source_usage`; cobro extra en el trigger | `src/dossier/db/schema_patches.py` (`NEWS_SOURCE_PATCHES`) y la migración `d4f6a8c2e0b3` |
| Panel | `frontend/src/components/admin/NewsSourcesPanel.tsx` |
