# LangGraph en Project Dossier (guía explícita)

Este documento explica **qué es LangGraph** en este repo y **dónde tocar** si quieres conectar APIs reales (Companies House, SEC).

## ¿Qué problema resuelve?

Antes, `generar_dossier_ejecutivo` era **un solo paso**: un prompt a OpenAI. Eso no modela:

- varias fuentes de datos (**UK** y **USA**) que pueden fallar o tardar por separado;
- ejecutar fuentes **en paralelo**;
- unir resultados y **sintetizar** con otro modelo (aquí: **Gemini**).

**LangGraph** describe un **flujo con estado**: nodos que leen/escriben un diccionario compartido y aristas que definen el orden (y el paralelismo).

## Archivos relevantes

| Archivo | Rol |
|--------|-----|
| `backend/src/dossier/graphs/corporate_dossier_graph.py` | Define el **estado**, los **nodos** (agentes + síntesis), el **grafo** y `run_corporate_dossier_langgraph`. |
| `backend/src/dossier/services/corporate_registry_context.py` | Obtiene **datos reales** UK (perfil + filing history CH) y US (submissions SEC). Opcional: análisis Gemini del **primer filing descargable** CH y del **primer HTML** de filing SEC (`DOSSIER_CORPORATE_*_FILING_GEMINI`). |
| `backend/src/dossier/companies_house/prompt_templates.py` | Texto del prompt Gemini para análisis de documento CH (compartido CLI + pipeline). |

Si ves **429 / RESOURCE_EXHAUSTED** (cuota free tier), define `DOSSIER_CORPORATE_CH_FILING_GEMINI=0` y/o `DOSSIER_CORPORATE_SEC_FILING_GEMINI=0` en `.env` para omitir el análisis por documento (CH y/o SEC) y dejar solo la síntesis final (menos peticiones por dossier).
| `backend/src/dossier/llm/text_generate.py` | Llamada de **texto** al LLM (sin subir PDF/HTML). |
| `backend/src/dossier/services/openai_dossier.py` | Punto de entrada `generar_dossier_ejecutivo`: por defecto LangGraph+Gemini; opcional legacy OpenAI. |

## Topología del grafo (dibujo mental)

1. Desde `START` salen **dos aristas** a la vez:
   - nodo `agent_corporate_uk`
   - nodo `agent_corporate_usa`  
   → se ejecutan **en paralelo** (mismo superpaso).

2. La arista  
   `add_edge(["agent_corporate_uk", "agent_corporate_usa"], "synthesize_gemini")`  
   significa: **no ejecutes la síntesis hasta que los dos hayan terminado** (fan-in).

3. `synthesize_gemini` lee el estado, llama a Gemini y escribe `final_dossier_markdown`.

4. `END` termina la ejecución.

## Estado (`CorporateDossierState`)

Campos típicos:

- **Entrada**: `tema_reunion`, `participantes`, `descripcion`, `jurisdiction_scope` (`uk_only` | `us_only` | `dual`)
- **Salidas de agentes**: `uk_corporate_context`, `us_corporate_context`
- **Salida final**: `final_dossier_markdown`
- **Errores**: `agent_errors` (lista; la síntesis puede añadir entradas si Gemini falla)

Cada nodo devuelve solo un **fragmento** del estado; LangGraph los **fusiona** con el estado anterior.

Si la API recibe `resolution` (empresa UK o SEC elegida en el dashboard), `dossier_routes` pasa `jurisdiction_scope` explícito (`uk_only` / `us_only`) a `run_corporate_dossier_langgraph`, de modo que **no** se consulta el registro del otro país. Sin `resolution`, el alcance se infiere del texto (`infer_jurisdiction_scope`) y puede quedar `dual` si el brief es ambiguo.

## Cómo enganchan Companies House y SEC

Los nodos `_node_agent_corporate_uk` y `_node_agent_corporate_usa` delegan en
`corporate_registry_context.py`:

- **UK**: si existe `COMPANIES_HOUSE_API_KEY`, intenta extraer el **company number**
  del brief (p. ej. tras elegir empresa en el dashboard) o buscar por el término entre « ».
  Llama a `get_company_profile` y una muestra de `get_filing_history` (`companies_house/cli.py`).
- **US**: deduce **CIK** (explícito en el brief, o vía ticker / nombre con el índice SEC)
  y descarga `https://data.sec.gov/submissions/CIK{cik}.json`, resumiendo los filings recientes.

Si falta clave o no se puede resolver la entidad, el Markdown indica el motivo; Gemini
sigue pudiendo redactar con lo disponible.

### Ajustes avanzados

- Para más detalle UK (officers, charges), amplía `build_uk_corporate_context_markdown`.
- Para enlazar a un 10-K concreto, amplía `build_us_corporate_context_markdown` reutilizando
  rutas de `dossier/sec_edgar/cli.py` (índice + documento principal).

## Variables de entorno

- **Obligatoria (ruta por defecto)**: `GEMINI_API_KEY` (o `GOOGLE_API_KEY`).
- **Modelo**: `GEMINI_MODEL` (por defecto coherente con `dossier/gemini/analyze.py`).
- **Timeout texto**: `GEMINI_TEXT_TIMEOUT_MS` (por defecto 120000).
- **Legacy solo OpenAI**: `DOSSIER_LEGACY_OPENAI=1` + `OPENAI_API_KEY`.

## Paquete `dossier` y la carpeta `src/`

El código importable vive en **`backend/src/dossier`**. Desde `backend/`, `python main.py` añade `src` a `sys.path`. Para otros puntos de entrada, define `PYTHONPATH=src` en ese proceso.
## Ampliaciones típicas (siguiente iteración)

- **Checkpoint / memoria**: `MemorySaver` de LangGraph para conversaciones multi-turno (no usado aún).
- **Streaming**: `graph.compile().stream(...)` para enviar progreso al frontend (WebSockets).
- **Más agentes**: añadir nodo `agent_news` y otro fan-in `["uk","us","news"], "synthesize_gemini"` o una cadena distinta según producto.


Los comandos Python de esta guía se ejecutan desde `backend/`; la documentación SQL permanece en `docs/` en la raíz del repositorio.
