# Agente de registros corporativos europeos

Cobertura, límites y costo del agente que consulta registros mercantiles de Europa continental
(brecha B2, objetivo OE4). Decisión de origen: [ADR 0003](architecture/decisions/0003-fuente-registros-europeos.md).
Tarea: S2.7.

## Qué hace

Dado el nombre de una empresa, consulta en paralelo los registros de **Francia** y **Alemania**,
normaliza cada resultado al modelo común `RegistroCorporativo` (el mismo de Reino Unido y Estados
Unidos) y lo entrega con su cita de origen (`CorporateRecordCitation`: proveedor, URL pública,
identificador y fecha de consulta).

| Pieza | Archivo |
|---|---|
| Cliente HTTP | `backend/src/dossier/eu_registry/client.py` |
| Normalización | `backend/src/dossier/eu_registry/mapper.py` |
| Agente (paralelo por país, deduplicación) | `backend/src/dossier/eu_registry/agent.py` |
| Nodo del grafo y fuentes consultadas | `backend/src/dossier/graphs/corporate_dossier_graph.py` (`agent_corporate_eu`) |

## Cobertura por país

| País | Fuente | Estado | Identificador | URL pública que se cita |
|---|---|---|---|---|
| Francia | API Recherche d'entreprises (data.gouv.fr) | **Verificada en vivo** | SIREN (o SIRET si falta) | Ficha del Annuaire des Entreprises: `https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}` |
| Alemania | Handelsregister vía OffeneRegister.de (API tipo Datasette) | **Sin verificar**: el servicio respondió HTTP 502 al revisar su esquema (12-09-2026) | Número del registro (`company_number`) | `opencorporates_url` de la fila, si viene |
| Otros países | — | Fuera de alcance | — | — |

Datos que entrega cada país:

- **Francia:** razón social, estado (`etat_administratif`), forma jurídica, fecha de creación,
  domicilio de la sede, código de actividad y directivos (`dirigeants`).
- **Alemania:** razón social, estado, forma jurídica, fecha de constitución, domicilio y la fila
  completa en `datos_brutos`. Los nombres de columna siguen el formato habitual de los volcados que
  republica OffeneRegister, pero no están confirmados. Si difieren, los campos quedan vacíos sin
  romper nada.

Para que el agente consulte Europa, el dossier corporativo debe tener una empresa objetivo y el
usuario no debe haber elegido un registro de Reino Unido o de Estados Unidos. Con esa elección, el
nodo queda en `agents_skipped` sin llamar a la red, para no mezclar homónimos.

## Límites

| Límite | Valor | Dónde |
|---|---|---|
| Tiempo de espera por país | 10 s (criterio CA-B2.4) | `client.py`, `DEFAULT_TIMEOUT` |
| Resultados por consulta | 5 por defecto; el cliente acota entre 1 y 25 | `agent.py`, `LIMITE_POR_DEFECTO` |
| Tasa de la API francesa | 7 llamadas por segundo; la administración puede bajarla si hay sobrecarga ([ficha en data.gouv.fr](https://www.data.gouv.fr/dataservices/672cf684c3488a0c533f7094)) | Proveedor |
| Coincidencia | La razón social debe contener todas las palabras buscadas; si no, el registro no entra al informe | `corporate_dossier_graph.py`, `_coincide_con_empresa` |

**Limitaciones conocidas:**

- **Alemania sin verificar.** Si el servicio sigue sin responder, el agente lo registra como
  fuente con resultado `error` y el dossier se genera con Francia y las demás fuentes. La base,
  la tabla y la URL del servicio se cambian por variables de entorno (`EU_REGISTRY_DE_API_BASE`,
  `EU_REGISTRY_DE_DATABASE`, `EU_REGISTRY_DE_TABLE`), sin tocar código.
- **Tribunal de registro alemán.** El criterio CA-B2.2 pide el número HRB/HRA y el tribunal de
  registro. El tribunal no se separa en un campo propio: queda como prefijo del identificador
  (por ejemplo `K1101R_HRB000001`).
- **Homónimos.** La coincidencia por palabras evita la mayoría de los falsos positivos de la
  búsqueda difusa francesa, pero una empresa cuyo nombre esté contenido en otra más larga (por
  ejemplo «Acme» dentro de «Acme Holding Nord») pasa el filtro.
- **Caché.** Un dossier servido desde la caché de Redis no vuelve a consultar los registros: no
  trae fuentes consultadas nuevas.

## Tolerancia a fallos y trazabilidad

- Cada país se consulta por separado: si uno falla (HTTP, tiempo de espera o formato inesperado),
  el otro se entrega igual.
- Si fallan los dos, o el agente lanza una excepción, el nodo queda en `agents_failed` y el dossier
  se genera con las demás fuentes (criterio CA-B2.4).
- Cada dossier corporativo guarda en `dossier_data["fuentes_consultadas"]` qué registro consultó,
  para qué jurisdicción, cuándo y con qué resultado (`consultada`, `sin_resultados` o `error`).
  `data_sources_used` lista las fuentes que respondieron (S2.4 y S2.5).

## Costo por consulta

| Fuente | Costo | Cuenta o clave |
|---|---|---|
| Recherche d'entreprises (Francia) | 0 USD | No requiere: acceso abierto |
| OffeneRegister.de (Alemania) | 0 USD | No requiere |

Las alternativas comerciales evaluadas cobran más de 500 USD al mes (OpenCorporates) o por
consulta (North Data, entre 0,10 y 0,50 EUR), según el ADR 0003. El costo de un dossier corporativo
lo pone la síntesis con DeepSeek, no los registros.

## Pruebas

| Archivo | Qué cubre |
|---|---|
| `tests/test_eu_registry_client.py` | Llamadas HTTP y errores del cliente |
| `tests/test_eu_registry_mapper.py` | Normalización de filas francesas y alemanas, completas y vacías |
| `tests/test_eu_registry_agent.py` | Consulta de ambos países, filtro por jurisdicción, fallo de un país y cita de origen |
| `tests/test_corporate_graph_eu_news.py` | Nodo del grafo, alcance y homónimos de razón social |
| `tests/test_contraste_jurisdicciones.py` | Una empresa por jurisdicción (UK, US, FR y DE) con el mismo contrato, empresa no encontrada y datos incompletos (S2.6) |
| `tests/test_corporate_fuentes_consultadas.py` | Fallo del agente con dossier emitido y fuentes consultadas por jurisdicción (S2.4 y S2.5) |
